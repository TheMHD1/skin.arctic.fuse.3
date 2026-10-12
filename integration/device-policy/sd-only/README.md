# AM9 migration to standalone SD

The original AM9 can use its existing SD card for both CoreELEC boot files and
persistent `/storage`, without the USB SSD. This conversion preserves its own
recovered settings, databases and complete local-PVR repair cohort. It does not
clone the remote appliance, format the card, modify Android or change AV policy.

## Prerequisites

Identify the exact maintenance host, reader/physical device, capacity, both card
partition UUIDs and original boot hashes through private deployment records.
Reader serials alone are insufficient. Require explicit authority for conversion,
healthy card filesystems, enough free ext4 space, an independent verified source
snapshot and complete off-card archives of the card's existing boot/storage trees.
Back up the original SSD separately; an interrupted or padded image is not a
verified recovery image.

Keep Kodi offline. Read the original storage readonly without journal replay,
capture it to a protected directory on the server, and verify every regular file's
bytes, permissions, ownership, symlink target and extended attributes. Preserve
SQLite WAL/SHM/journal companions and check databases on temporary copies. Do not
follow absolute runtime symlinks into the maintenance host.

`storage.py` supplies exact-selector conversion and private inventory checks.
It is not an unattended physical-disk installer. A private deployment wrapper
must validate exact mountpoints, physical identity, UUIDs, old hashes, capacity
and backups before using any writable mount or mirroring operation.

```sh
python3 integration/device-policy/sd-only/test_storage.py
python3 integration/device-policy/sd-only/storage.py inventory \
  --root /PRIVATE/recovered-storage --manifest /PRIVATE/source-inventory.json
python3 integration/device-policy/sd-only/storage.py verify \
  --root /PRIVATE/mounted-card-storage --manifest /PRIVATE/source-inventory.json
```

Inventories contain private paths and must remain outside this public repository.

## Conversion

1. Validate both card filesystems while unmounted. Save and test complete private
   boot/storage archives, including ACLs, xattrs and numeric ownership.
2. Capture the appliance's recovered storage to an independent server directory.
   Compare its full private inventory with the offline original. Verify the
   existing paired source receipt and databases before writing the card.
3. Mount only the exact card ext4 partition writable and copy the complete
   recovered tree with metadata and symlinks preserved. An exact mirror may
   replace the card's old minimal bootstrap; require its off-card backup first.
   Never point a destructive mirroring operation at an inherited mount or host root.
4. Verify the card against the complete source inventory. Retire only identified
   obsolete hybrid instructions/manual repair files to protected off-card
   recovery material; keep their hashes and the full original snapshot.
5. Change only the active `coreelec` storage selector in card `config.ini` from
   the SSD UUID to the card's ext4 UUID. The helper rejects an unexpected,
   duplicate or ambiguous selector and removes only the retired adapter's exact
   `usb-storage.quirks=174c:55aa:u` token. Preserve `quiet`, `toram`, CEC,
   calibration, configured DTB, `dovi.ko`, remote control and all other settings.
   Update the standalone-SD preset if present; archive the obsolete hybrid preset.
6. For a separately authorized firmware update, use a reviewed official tar with
   verified package/internal hashes in the card's own `.update`. Keep the
   existing coherent kernel/SYSTEM pair until the normal CoreELEC updater runs.
   The retired SSD must be absent: its cloned FAT UUID could otherwise select
   the wrong `/flash`. Do not run the old two-copy hybrid staging script.
7. Verify the final full-copy inventory, then sync, cleanly unmount and check both
   filesystems again. Remount readonly and cold-read operational configuration,
   paired source/account receipt, databases, selector, coherent boot files and
   staged tar. Finally unmount all removable-media partitions for handoff.

## October 12 acceptance

The original card was converted in place. Its full source capture matched
16,530 entries on the original recovered storage; the card's copied tree passed
the same complete byte/metadata inventory before final staging. The final tree
passed a second full inventory, with only three archived obsolete hybrid
instruction/repair files removed and the reviewed update tar added. All58
`am9-shared-20261008.7` source files and all14 databases passed. A read-only own-user
Jellyfin request authenticated successfully with the preserved Kodi identity.

The card's coherent September22 kernel/SYSTEM, configured DTB, Dolby module,
remote control and calibration remain preserved. Its active storage selector
and standalone preset now select the card's own ext4 UUID; the old hybrid preset
and instructions are archived off-card. The reviewed October12 tar is staged
for the normal standalone-SD updater, **not yet installed on the box**. Final
unmounted filesystem/cold-read acceptance remains distinct from actual box
boot, network, Kodi UI, binary-addon and HDMI acceptance. The13 isolated helper
regressions and full integration suite passed.

Both final unmounted filesystem checks passed. Cold mounted verification covered
206 operational/source/database entries and repeated the local58 source/account
planner and all14 SQLite checks. Actual device startup and completion of the
staged firmware remain pending until the card is returned to the appliance.

The remote AM9 already uses standalone SD and receives no storage, account,
network or firmware changes from this conversion. Its optional 5 GHz policy
and remote62 receipt remain separate. Shared repair source is unchanged.

## Rollback and future updates

### Interrupted update recovery

A clean FAT/ext4 check does not establish that the firmware files are complete.
After the owner's first boot was interrupted on October12, the card contained
the correct new kernel but only181,403,648 of388,501,504 bytes of the new
`SYSTEM`. Both readonly filesystem checks passed. Keep the saved userdata;
this failure does not require formatting or an Android firmware flash.

With the appliance powered off, identify the exact card again and mount both
partitions readonly (ext4 with `noload`). Preserve a complete off-card boot
archive and the failed `.update` directory before writes. Verify an independent
official package and its internal payload hashes. The reviewed October12 pins are:

- Official tar SHA256: `937b5ab3986ab6ebf310dc11bd4c59f195c94507ec5872a63f6fef2ccd4c08f9`.
- `target/KERNEL` SHA256: `64d9f8aec0f3f061d5d7415851e69220f3770f1b3ea5e0619610ada01c34839f`.
- `target/SYSTEM` SHA256: `b6e7322f2a474c5ff604f821564c763137181b17221c8a3602917d011b073d96`.

Restore a coherent `kernel.img`/`SYSTEM` pair and their official MD5 sidecars,
not only the kernel. A payload already matching its reviewed hash needs no
rewrite. Small files can use checked temporary-file replacement; FAT may lack
space for a second complete `SYSTEM`, so an in-place replacement requires the
verified independent recovery archive and stable maintenance-host power first.
Preserve the standalone storage selector, configured DTB/`dtb.xml`, Dolby module,
remote settings, account and complete local repair source. Verify that the
candidate's stock AM9 device tree matches the preserved stock input before
reusing the configured DTB. A different device tree requires separate review.

The pinned upstream init detects `.update/.tmp` as a failed update, cleans the
update files and skips installation; it does **not** restore the overwritten
partial boot payload. After the coherent boot pair is repaired and all failed
update entries have been independently archived/verified, retire only the exact
reviewed failed entries. Leave one hash-verified official tar in `.update` so the
normal updater can finish its on-device bootloader/DTB steps. Never blindly clear
an unknown update directory, suppress compatibility checks or run the native
bootloader script on the maintenance server.

`boot_integrity.py` checks both expected boot hashes without modifying files.
Its six regressions reject truncation, same-size corruption, mixed releases,
missing files, links and incomplete expected hashes. Physical media/mount guards,
settings, MD5 sidecars and updater state remain separate private deployment checks.

```sh
python3 integration/device-policy/sd-only/test_boot_integrity.py
```

Sync and unmount both partitions, repeat filesystem checks, then cold-read the
boot pair, staged tar, device settings, shared source and database copies before
handoff. Keep the retired SSD absent. Leave power connected throughout the next
normal boot/update and automatic reboot. Firmware files prepared offline are
not live OS, Kodi or HDMI acceptance. The same checks apply to the remote
standalone-SD cohort, but do not authorize changing its media or private identity.

Recovery execution and cold-read acceptance are recorded separately from the
earlier migration receipt; the original offline snapshot remains unchanged.
The original card's repair passed both final unmounted filesystem checks and
cold boot-pair/MD5/tar verification. All206 operational entries still matched
the original saved state; local58 and all14 SQLite checks passed again. All
removable partitions were unmounted for handoff. Actual boot, native updater
completion and Kodi/HDMI acceptance remain pending. The remote card was untouched.

Subsequent October 12 live acceptance supersedes those handoff-pending fields:
the original appliance boots CoreELEC22 nightly20261012 / Kodi22RC1; its running
kernel and `SYSTEM` match both pins above, `.update` is empty, and `/flash` plus
`/storage` resolve to the card. All 58 shared source hashes match. Actual Home,
Venom category artwork/grid, two hardware-decoded 1080p channels, switching and
stop/Home/reopen passed. The previously missing native episode also passed a
Kodi VFS byte read after the server's mount repair. This is not full physical
DV/audio/HDMI acceptance or a new backup-run result; those remain separate.

Keep the old SSD disconnected during SD-only use. For offline rollback, restore
the exact card's saved boot/storage archives as a coherent pair while all
appliance processes are stopped, and remove the newly staged tar before booting
an older release. A rollback to hybrid operation also requires independently
verified SSD hardware/transport; restoring its selector does not fix USB resets.
Ordinary caught configuration errors can restore the saved selector; power loss
during FAT writes or storage mirroring requires the independent archives.

After successful boot, verify `/flash` and `/storage` are on this card, the live
kernel matches `/etc/os-release`, `.update` is empty, and both final boot hashes
match the intended release. Check addon API compatibility, Home/search,
Venom switching, audio/DV/subtitles, awake/OLED policy and an actual backup run.
Keep CoreELEC updates manual and patched addon auto-updates disabled. Normal
single-card updates avoid the hybrid kernel/SYSTEM mismatch but do not certify
future nightlies or replace exact-source addon rebase/regression checks.

References: [CoreELEC updates](https://wiki.coreelec.org/coreelec:updates),
[CoreELEC backups](https://wiki.coreelec.org/coreelec:backup),
[reviewed October12 source](https://github.com/CoreELEC/CoreELEC/commit/a3896e23e6).
The failed-update behavior is in the pinned
[CoreELEC init script](https://github.com/CoreELEC/CoreELEC/blob/a3896e23e6fadbde70f03edc839d4a99dd41c54a/packages/sysutils/busybox/scripts/init).
