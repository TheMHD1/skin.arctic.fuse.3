# Original AM9 hybrid recovery — October 12

## Scope and safety boundary

The original/local appliance failed to start after an abrupt power removal.
Its own SD and SSD were attached to the maintenance host for recovery and
catch-up to the complete `am9-shared-20261008.7` local-PVR source cohort.
This is not an Android flash, repartition, standalone-SD conversion or clone of
the remote-house appliance. Keep the private account, network, SSH identity,
storage UUID, audio settings, calibration and boot configuration separate.

The existing hybrid layout boots the SD kernel but mounts SSD `/flash` and
`/storage`. Both FAT boot filesystems have the same UUID. Resolve physical
devices using private serial/layout records, not a boot UUID or label alone.
Never apply the remote-house standalone-SD updater to this layout.

## Evidence and independent recovery acceptance

- Both original boot trees matched the previously accepted September 22 kernel,
  SYSTEM and configured device tree. This incident was not a demonstrated new
  kernel/SYSTEM mismatch. Both FAT checks and the SD ext4 check passed.
- The SSD's storage filesystem refused mounting with `Structure needs cleaning`.
  Damaged group descriptors and a small cluster of configuration inodes were
  confirmed on a complete disk-image copy, independent of USB read failures.
- The maintenance USB adapter also produced read errors/resets. Disabling UAS
  only for that adapter did not eliminate large-request failures. A complete
  direct-I/O, 64 KiB capture succeeded without skipped or padded read regions.
  The original image's full size and SHA256 were recorded privately. The image
  remains unrepaired and access-controlled, independently of all test copies.
- An independent copy was repaired with journal recovery and `e2fsck -fy`, then
  passed a separate full `e2fsck -fn`. The 55-file maintained source inventory
  matched; all 14 SQLite databases, including retained historical copies,
  passed `quick_check`. WAL/journal companions were copied to temporary private
  directories before SQLite verification; readonly filesystem inspection must
  not discard a database's uncheckpointed WAL by using immutable mode.
- The physical SSD repair then passed its own separate full filesystem check,
  and all 14 databases passed again. Four lost configuration directories
  (`timesyncd.conf.d`, `tmpfiles.d`, `udev.rules.d`, `wireguard`) were restored
  from the original appliance's October 2 backup. The three `lost+found` files
  exactly matched WireGuard sample files in that backup; they remain preserved.
  GUI settings, CEC overrides, stored hostname and Jellyfin identity matched
  the pre-repair capture byte for byte. No library/database reset was needed.
- Bulk USB reads still produced I/O failures after the port move and temporary
  transfer-size reduction. A complete buffered diagnostic read returning success
  is not adapter acceptance if the kernel still logs read failures. Firmware
  writes remain held until a reliable connection is established; filesystem
  acceptance must not be confused with hardware/transport acceptance.

Passing a repaired image does not certify the real SSD, USB adapter, Kodi
startup or HDMI playback. Recheck the physical partition after repair; do not
continue to firmware staging if filesystem verification or USB I/O is failing.

## Controlled recovery sequence

1. Identify the exact maintenance host, disk serial/capacity, partition layout
   and private storage UUID. Confirm that target partitions are unmounted.
   Check kernel I/O logs, SMART evidence and both boot-file hashes. Avoid a host
   reboot or unloading a global driver used by unrelated disks.
2. Keep a verified complete original image and both complete boot-file trees
   off the appliance. Test recovery on an independent writable image. Preserve
   failed-check evidence privately; filesystem check logs can contain enormous
   single bitmap-difference lines, so truncate each displayed line.
3. Only after successful image acceptance, repair the identified physical
   storage partition. Run a separate full verification before mounting it
   writable. Inspect databases and configuration on the real recovered media.
4. Restore only missing/demonstrably damaged configuration from this appliance's
   own latest valid backup. Do not restore an entire old database/userdata tree
   merely because several unrelated configuration inodes were damaged. Extract
   only required regular files/directories with archive safety checks; absolute
   runtime/service symlinks are not grounds to bypass archive link protections.
   Preserve existing device-side timer/service links separately.
5. Use the [offline source installer](release/offline-recovery/README.md),
   preserving all existing shared-release identity/source guards. Require its
   second plan to be empty. The local target is the 58-file manifest SHA256
   `017158ff49a9ebeb8ca0079a1fa50d68ee30225c30ad9759bb84fafd793cf60c`.
   This is the same repair release as the remote cohort, not its network/PVR
   configuration. Preserve rollback copies and private deployment records.
6. Stage the official reviewed firmware using the coordinated
   [hybrid procedure](COREELEC-HYBRID-UPDATE-2026-09-23.md), not a stock one-copy
   update. The SD gets matching kernel/SYSTEM/checksum files and SSD storage
   gets the verified tar in `.update` for the normal updater on first boot.
   Preserve each boot partition's own config.ini, storage selection, Dolby
   module and calibration. An unchanged stock DTB permits retaining the
   already configured DTB during offline staging; do not blindly carry it to
   a release whose stock DTB changed. Finalize both copies after the updater.
7. Sync and cleanly unmount every attached partition before physical handoff.
   Boot normally with both original SD and SSD; do not press recovery/maskrom
   or remove power during updating. Staging is not completed installation.
8. On the actual device, verify hardware identity, target OS/kernel, correct
   mounts, empty `.update`, both final boot sets, manual-update policy, network,
   addon compatibility, generated menus, account, source convergence and
   database checks. Test search and Venom/Home/playback transitions. Preserve
   awake/OLED, CEC, 30-second seeking and audio settings; physical AV remains
   distinct from source/API checks.

## Reviewed firmware and addon boundaries

| Artifact | SHA256 |
| --- | --- |
| Official `CoreELEC-Amlogic-no.aarch64-22.0-Piers_nightly_20261012.tar` | `937b5ab3986ab6ebf310dc11bd4c59f195c94507ec5872a63f6fef2ccd4c08f9` |
| Target KERNEL | `64d9f8aec0f3f061d5d7415851e69220f3770f1b3ea5e0619610ada01c34839f` |
| Target SYSTEM | `b6e7322f2a474c5ff604f821564c763137181b17221c8a3602917d011b073d96` |
| Stock AM9 Pro DTB | `0716528f0d5a8927bc3ddc4d92a1d2167249ef40d5ce96a3674a80528b30e804` |

The official package's internal MD5 checks passed. Its source build is
`a3896e23e6fadbde70f03edc839d4a99dd41c54a`. The stock AM9 DTB remains unchanged.
Compared with the accepted October 8 system, CEC policy, Dolby loader and
bootloader update script are unchanged; the CoreELEC updater module body also
matches after excluding its timestamp header. Kodi addon APIs changed for
InputStream, main and game; binary-addon compatibility still needs live checks.

Jellyfin for Kodi 2.2.0 is already the reviewed current upstream release.
Arctic 3.3.12 is available upstream, but the maintained 3.3.1 patch does not
apply cleanly to its Live TV XML. Keep the maintained skin until an exact rebase,
paired source-manifest update and live acceptance have been completed. Installing
stock 3.3.12 or changing version strings would lose or invalidate the repairs.
Publication of this recovery helper does not deploy a new skin to either box.

## Rollback and acceptance record

The unrepaired complete SSD image, SD boot archive, this appliance's configuration
backup and changed-addon rollback tree stay private. Restore coherent boot sets
and move any staged update out of `.update` before retrying an old release.
An addon rollback restores only its recorded changed-file set and prior receipts,
not account/network identities or databases. FAT SYSTEM replacement is not
power-failure atomic; independent verified recovery material is mandatory.

Independent-image and physical filesystem/database acceptance passed. The exact
22-file shared update was applied to the original SSD, with a private changed-file
rollback tree. The final 58-file manifest matched the target pin and a second plan
was empty. After sync/unmount, a fresh readonly mount passed all 58 source hashes,
the complete shared planner/account checks, all 14 database checks and the preserved
GUI/CEC/account byte comparisons. A final full physical filesystem check and both
FAT checks passed. All SD/SSD partitions were cleanly unmounted for handoff.

Firmware remains **unstaged** because maintenance USB I/O is still unreliable;
both boot copies retain the accepted September 22 kernel/SYSTEM/configured DTB.
There is no update left in `.update`. A reliable direct USB2 connection or different
adapter is needed before proceeding with maintenance-host firmware staging.
Alternatively, reconnect and verify the recovered appliance first, then separately
review its own actual I/O path before executing the coordinated hybrid update.
No Android/internal firmware flash or root filesystem reformat was performed.
Real-device boot/UI/audio acceptance and online binary-addon checks remain pending.
Do not interpret this record or a Git push as final appliance acceptance.

## Official references

- [CoreELEC nightly index](https://relkai.coreelec.org/?dir=Amlogic-no/ce-22)
- [CoreELEC updates](https://wiki.coreelec.org/coreelec:updates)
- [Reviewed CoreELEC source commit](https://github.com/CoreELEC/CoreELEC/commit/a3896e23e6)
- [Jellyfin for Kodi 2.2.0](https://github.com/jellyfin/jellyfin-kodi/releases/tag/v2.2.0)
- [Arctic Fuse 3.3.12](https://github.com/jurialmunkey/skin.arctic.fuse.3/releases/tag/v3.3.12)
- [Linux per-device filesystem request limit](https://www.kernel.org/doc/html/v5.15/block/queue-sysfs.html#max-sectors-kb-rw)

The maintenance host temporarily limited requests for the exact external SSD
to 64 KiB, following successful small-request capture. This is an observed
recovery workaround, not proof of permanent adapter health or a generic AM9
performance recommendation. Keep the appliance's existing adapter quirk;
do not add a global host disk policy or silently throttle both appliances.
