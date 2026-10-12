# Offline AM9 source recovery

This installer applies the existing complete paired `am9-shared-20261008.7`
source plan when an appliance's own ext4 storage is attached to a maintenance
host. It does not copy another appliance's profile, skip source guards, repair
a filesystem, update firmware or establish live acceptance. Both local native
PVR and remote HTTPS account/transport guards remain in the shared planner.

Use after hardware reads are reliable, filesystem recovery has been tested on
an independent copy, and the recovered storage passes filesystem checks. Keep
the unrepaired whole-disk image and both boot-file trees independently off the
appliance. A truncated image or a recovery operation that skipped unreadable
regions is not a verified backup.

The private device profile needs an additional `offline_recovery` object with
`maintenance_host`, `storage_uuid` and `disk_serial`. These fields belong only
in private deployment material. The installer checks the actual host, exact
writable ext4 mount target, partition UUID and physical parent-disk serial.
An inherited mount, foreign disk, symlink, wrong account, unreviewed source or
partially applied receipt fails closed. The recorded wireless MAC is not live
hardware evidence while the box is disconnected; recheck it on the actual box
after reconnection.

```sh
python3 integration/release/offline-recovery/test_install.py
python3 integration/release/offline-recovery/install.py \
  --root /PRIVATE/mounted-storage --profile /PRIVATE/device.json
python3 integration/release/offline-recovery/install.py \
  --root /PRIVATE/mounted-storage --profile /PRIVATE/device.json --apply \
  --recovery-image /INDEPENDENT/whole-disk.img --recovery-sha256 REVIEWED_SHA256
```

Before apply, verify the full image size against its recorded original disk
capacity and review its read/capture log. The tool verifies its independently
recorded SHA256 but cannot infer that an incomplete image represents the whole
disk. It never calls systemctl or assumes that a host-side Kodi service is the
appliance. All source/config snapshots are revalidated before replacement.
Changed files receive a private rollback copy, original mode/ownership is
preserved, and each replacement is atomic. Ordinary errors and interactive
interruption restore changed files and remove only paths newly introduced by
this transaction. Power loss and forced process death still require manual
recovery from the backup; multi-file deployment is not power-failure atomic.

Eight isolated tests cover physical/mount/host rejection, inherited and readonly
mounts, symlinks, source/staging drift, mode preservation, image checksum,
parent/backup symlinks, interrupted-write rollback and final-plan convergence. The complete paired
source planner retains its separate real-SQLite and both-cohort regressions.

An empty second plan proves installed source convergence, not successful Kodi
startup. After physical reconnection, verify actual hardware identity, network,
boot/kernel/SYSTEM consistency, account, addon dependencies, database checks,
awake/OLED policy, generated menus and real search/IPTV/playback transitions.
Run the documented skin-template rebuild only through the appliance's Kodi.
Keep the other cohort's applied/accepted/pending record separate.

For addon rollback, keep Kodi stopped and restore the recorded changed-file set,
including the prior manifest/receipts, from the printed transaction backup.
Remove only previously absent files identified in `change-paths.json`; do not
replace databases or network identities for an addon source rollback. Firmware
and filesystem rollback are independent operations.
