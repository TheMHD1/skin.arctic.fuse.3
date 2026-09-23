# AM9 Pro hybrid CoreELEC update — September 23

## Scope and release

The owner explicitly lifted the firmware hold for the local AM9 Pro. The target
is the official `CoreELEC-Amlogic-no.aarch64-22.0-Piers_nightly_20260922.tar`,
updating the previously working September 18 nightly on the same branch. This
is an in-place CoreELEC update, not a fresh image, Android flash, repartition,
SD/SSD layout migration, addon source port or second-device deployment.

The exact-device installation/verification record is private. See the acceptance
section below for the final result; preparation alone is not deployment.

| Artifact | SHA256 |
| --- | --- |
| Official update tar | `5f017e56449a7a0e1fbcf348a9e8a2412c31d89a72820a10e66937b482293729` |
| Target KERNEL | `d83e05f7d38fdfab53207fb999d9f4a7d2dccf76217bf8e75ff94a81c93d0483` |
| Target SYSTEM | `c9ed75891261c0a8ad16a2229b050b34a9470dfbf662cfe5f1e733954d38e3c6` |
| Stock AM9 Pro DTB | `0716528f0d5a8927bc3ddc4d92a1d2167249ef40d5ce96a3674a80528b30e804` |

The freshly downloaded HTTPS tar matched the previously staged tar. Its internal
SYSTEM/KERNEL MD5 checks also passed. The stock AM9 Pro DTB and updater script
are byte-identical to the September 18 versions. A configured final `dtb.img`
can differ from the stock DTB because the updater reapplies `dtb.xml` settings.

## Why a normal one-partition update is insufficient

The bootloader reads the SD kernel, but `/flash` and `/storage` resolve to SSD.
Both external boot partitions have the same COREELEC label (and cloned FAT UUID).
A normal updater can therefore replace SSD SYSTEM/kernel without replacing the
SD kernel. The resulting kernel/module mismatch previously broke Wi-Fi. See
[the September 18 recovery](UGOOS-HYBRID-RECOVERY-2026-09-18.md).

Do not assume a boot label identifies the actual hardware boot source. Inspect
`/proc/mounts`, `/proc/cmdline`, `blkid`, `dtname`, `uname -a` and both copies'
SHA256 values. Preserve each partition's own `config.ini`, the explicit SSD
storage UUID, USB-storage quirk and `dovi.ko`. Do not copy a generic image or
configuration over either partition.

## Reproducible controlled procedure

1. Check the official release for the existing Amlogic-no / ce-22 branch. AM9 Pro
   nightlies from September 10 require Android 2.2.0 and the corresponding AM9
   Pro DTB. This box already used that firmware/DTB combination; no Android
   upgrade is part of this procedure. Inspect package scripts and DTB differences
   before applying this runbook to any later release.
2. Verify exact device identity, physical partitions, storage UUID, free space,
   healthy filesystems, expected old hashes and an empty `/storage/.update`.
   Check that no BL301 injection is installed. Save the current U-Boot
   environment with `fw_printenv` to a private file; never publish it.
3. Verify the maintained Kodi source cohort in plan-only mode. Stop Kodi for a
   consistent snapshot. Back up **both complete boot-file trees**, `.kodi`,
   `.config`, persistent `.cache` settings and network/SSH identity. Transient
   log, core-dump and timeshift caches need not be copied. Retain access-controlled
   device-local copies and an independently checksum-verified off-device copy.
   Check gzip archives and Kodi SQLite databases before proceeding.
4. Extract the pinned official tar into private SSD staging, not either FAT
   partition. Validate its SYSTEM/KERNEL checksums and hardware-specific DTB.
   Before any writes, recheck the direct rollback files against the unchanged
   live files, not just the archive checksum. Require Kodi stopped and update
   directory empty again. CoreELEC here lacks `cmp`; compare SHA256 values rather
   than assuming desktop tools are present.
5. Stage matching SYSTEM, kernel, AM9 Pro DTB and checksum sidecars onto the SD
   boot partition. There is insufficient FAT space for two SYSTEM images, so
   its in-place copy has a power-loss window; the verified off-device backup is
   essential. Smaller kernel/DTB files can be copied under temporary names,
   read-back verified and renamed. Leave config.ini/dovi.ko unchanged. On a
   caught staging error, unstage the update and restore the old SD boot set;
   never reboot deliberately into a partially staged set.
6. Move the verified tar into `/storage/.update`, recheck its hash and `sync`.
   Reboot normally so the stock updater handles SSD. Do not disconnect power,
   SD or SSD during staging/update. The stock updater refreshes external boot
   support files and may update the existing U-Boot environment via `fw_setenv`;
   “no Android flashing” does **not** mean no internal environment writes.
7. After SSH returns, require target `/etc/os-release`, matching live kernel
   build, correct mounts/storage UUID, expected SSD kernel/SYSTEM hashes and no
   remaining staged update. Synchronize the updater's finalized `dtb.img`,
   `dtb.xml`, `aml_autoscript`, `cfgload`, `cfgload_env`, `recovery.img`, checksum
   sidecars and device trees from SSD to SD using read-back verification. Do
   not overwrite config.ini, calibration, resolution or custom Dolby module.
8. Verify both kernel/SYSTEM/final-DTB hashes, preservation hashes, Wi-Fi module
   loading, network reachability, failed units, Kodi startup, Jellyfin login,
   Home API and custom-source integrity. A second normal reboot verifies the
   finalized SD boot files instead of only the intermediate update boot.

This is not power-failure-atomic. If the box cannot boot, connect the external SD
and SSD to a maintenance host, identify each by the **private recorded** layout
and UUID, mount them, and restore both old boot-file sets as a coherent pair.
Move any remaining update tar out of `.update` before retrying. Do not flash
Android or restore another device's identity to solve an external-media mismatch.
Only restore Kodi/database configuration if needed for a demonstrated migration
problem; restoring it unnecessarily discards subsequent local changes.

## Manual update policy

Keep `settings/updates/AutoUpdate=manual` in the CoreELEC settings file. The
build-pinned updater honors it: with notifications enabled it asks before
downloading. However, accepting a download leaves a tar staged for a later
reboot even if the immediate reboot is declined. On this hybrid layout, future
updates need this coordinated two-partition workflow. The nightly website's
general automatic-update warning is not an accurate description of this pinned
manual-mode code path.

## Acceptance

Installed successfully on the local AM9 Pro, then passed a second normal reboot
with a new boot ID and no update staged. The final device returned to Arctic
Home. This does not update or certify the remote-house device.

- CoreELEC `22.0-Piers_nightly_20260922`, build
  `1ee9e47d823cb923d2291766bb132f2d57f83cdd`.
- Kernel `5.15.196`, built September 22, 01:32:56 IDT.
- Kodi `22.0-BETA2`, revision `3de1f35efd63b69ad2e6cd0bb8d6f637c9d92f4d`.
- SD and SSD kernel/SYSTEM match the target hashes above. Final configured DTB
  matches on both: `7661ff398b9e7bc38317810fcc6177986ad341fb56af1ed4ca39346ac5b7eba9`.
- Both original config.ini files, SSD storage identity and custom Dolby module
  hashes preserved. All GUI setting values unchanged; audio/video settings were
  not reset. Update mode remains manual and `.update` is empty.
- Arctic 3.3.1, Jellyfin 2.2.0+py3, Home 1.1.0, Venom 1.3.1,
  InputStream Adaptive 22.3.21.1 and IPTV Simple 22.6.4.3 remain enabled.
  Maintained source installer reports zero replacements after both boots.
- Wi-Fi driver loads, and a request explicitly bound to wlan0 reaches Jellyfin
  12.1. Home API returned 30 movies and 30 IMDb ratings. Kodi's PVR manager starts.
  Main addon, video and Jellyfin databases pass SQLite quick_check after update.
- No failed systemd units on the final completed boot. A check during shutdown
  briefly saw unavailable Kodi/SD mounts; it was not counted as a completed boot
  check. Final checks waited for a changed boot ID and mounted storage.

The owner manually rebooted once during preflight, before boot-file writes.
Both old boot sets were rechecked unchanged before restarting the procedure.
This was not treated as an unexplained firmware crash.

Known upstream keyboard/locale warnings and the proprietary Dolby module's
existing ABI warnings remain. Module loading and API checks do not certify TV
picture, DV/FEL, Atmos/DTS:X, lip-sync or natural episode-end autoplay. Those
physical playback checks were not repeated for this OS update. No unrelated
skin/addon source changes were made to hide existing warnings.

## Official evidence

- [CoreELEC Amlogic-no / ce-22 nightly index](https://relkai.coreelec.org/?dir=Amlogic-no/ce-22)
- [CoreELEC update procedure](https://wiki.coreelec.org/coreelec:updates)
- [AM9 Pro firmware/DTB prerequisite, maintainer discussion](https://discourse.coreelec.org/t/ugoos-am9-pro-soc-s6-s905x5-j/58183?page=20)
- [Hybrid boot kernel mismatch and USB-boot discussion](https://discourse.coreelec.org/t/ugoos-am9-pro-guide-tutorial-sd-usb-hybrid-boot-setup/58839?page=2)
- [September 22 pinned updater implementation](https://github.com/CoreELEC/service.coreelec.settings/blob/7cf25c6eb3648e0d5539104adbed0d2d2c464637/src/resources/lib/modules/updates.py)
- [CoreELEC September 18–22 source comparison](https://github.com/CoreELEC/CoreELEC/compare/b4c2888f6b4b...1ee9e47d823cb923d2291766bb132f2d57f83cdd)
