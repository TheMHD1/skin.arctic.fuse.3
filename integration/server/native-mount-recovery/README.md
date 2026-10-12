# Native media mount startup recovery

The existing read-only AM9 movie/show bind mounts can be skipped at boot when
the ZFS media dataset imports after `zfs-mount.service` completes. Their
`AssertPathIsMountPoint` correctly prevents exporting empty source directories,
but systemd does not retry an assertion-skipped mount. The existing NFS
`RequiresMountsFor` dependency then leaves the NFS server inactive too. Kodi
reports missing native files and its sync confirmation can obscure Venom.

`recover.py` and the accompanying oneshot service recover only these existing
mounts after verifying the exact source dataset, configured read-only units and
resulting read-only filesystems. NFS is started only after both checks pass.
An already-active mount/service is not restarted. The helper does not import
pools, modify exports, write media, change networking or recreate Kodi databases.

## Reviewed deployment and verification

Deploy on the existing Proxmox media-export host only. Back up the two mount
units, existing NFS dependency drop-in, listener configuration and exact exports
outside Git. Confirm their native paths match the helper's constants and the
existing LAN-only TCP listener and client-scoped read-only exports remain valid.
Unknown paths, unit overrides or source filesystems require review, not relaxed
guards. The reviewed mount units retain their original source assertion.

Install `recover.py` as `/usr/local/sbin/am9-media-mount-recovery.py` mode0644
and the service under `/etc/systemd/system/`. Create a root-owned mode0600
`/etc/am9-media-mount-recovery.env` containing the exact export host's private
`AM9_NFS_HOST` value. Run `systemd-analyze verify` on the installed service,
then daemon-reload and enable/start **only** `am9-media-mount-recovery.service`.
Do not restart Proxmox, Kodi or an active NFS daemon for this installation.

Source readiness polling is limited to 60 seconds per attempt. Native systemd
failure retries wait 5 minutes and allow at most 6 starts per 45 minutes, then stop
with an inspectable failure. There is no resident periodic watchdog or unlimited
retry loop. A successful oneshot remains exited; future manual dataset removal
requires explicit operator recovery, not automatic remounting during maintenance.

Check source/target `findmnt` output, read-only target options, NFS active state,
the restricted listener and a real Kodi VFS read. Systemd "active" alone does not
prove a remote file is readable. After a future planned host restart, repeat
these checks; boot ordering has fixture coverage, not a performed host reboot.

October 12 deployment passed eight isolated regressions, unit validation and
live idempotent execution on the export host. The local appliance's original
missing native episode was readable through Kodi VFS after restoration. This
server fix benefits both native-original cohorts; the remote appliance was not
changed or live-tested in this repair. It does not affect the remote Venom HTTPS
transport or replace its separate private-access policy.

## Rollback and updates

Disable/stop only this oneshot and retire its exact service/helper/private env
files after preserving the deployment receipt. Leave the already-mounted media
and NFS server running; do not unmount active playback paths. The original
mount units, export ACLs and listener were not edited by this repair. Keep them
and the separate remote-original manifest mount unchanged.

Updates must preserve/review these exact paths, dataset, assertion and native
NFS dependencies. Run `python3 -m unittest discover -s
integration/server/native-mount-recovery`; the full integration checker runs the
same suite. Configured-unit validation deliberately uses `systemctl cat`:
properties of an active bind mount report the kernel ZFS source/type, not its
configured `What`/`Type`.
