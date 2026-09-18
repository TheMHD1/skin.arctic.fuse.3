# Ugoos hybrid boot repair and updates — 2026-09-18

## Failure and cause

Ugoos had no wireless technology in ConnMan; Arctic could not reach Jellyfin.
Ethernet connected at 192.168.50.237. PCIe still detected BCM43752, ruling out
an absent PCIe device. `modprobe dhdpci` failed with Exec format error;
kernel log reported cfg80211 exporting a symbol already owned by the kernel.
Running kernel was built September 11 while SSD SYSTEM was September 16.
SD kernel SHA256 was 11491191...; SSD kernel c9ad92aa.... Stock updates had
updated SSD /flash but the bootloader still loaded the kernel from SD.

## Repair/update

Official September 18 Amlogic-no tar independently downloaded over HTTPS and
hashed against the package already downloaded by CoreELEC:
`3ce33cc666a47e95ad755da119a9b1346bb01b66f6ebbb61575dc5f2c493e756`.
Internal SYSTEM/KERNEL MD5 checks passed. Saved previous SD boot files under
`/storage/upgrade-staging/hybrid-repair-20260918/sd`.
Staged matching SYSTEM/kernel/AM9 Pro DTB on SD, then rebooted through the
standard CoreELEC updater for SSD. After boot copied updater DTB, dtb.xml,
device trees and boot support files to SD; preserved hybrid config.ini.

Installed CoreELEC 22.0-Piers nightly 20260918, kernel 5.15.196 built Sept 18,
Kodi 22.0-BETA2 (21.90.802). Both kernels now hash
`f663b93ae782c9b50ed8d9df3bb007f8f39aa9b4b00da10ed19a11323831db3a`.
SYSTEM hashes to `98cc1a4f4cdce8c558ec9750f1cc6731b5d363676cb7dc56d175f2637b713d7c`.
Final DTBs match `7661ff398b9e7bc38317810fcc6177986ad341fb56af1ed4ca39346ac5b7eba9`.

CoreELEC updates now **manual**: never use an unattended stock update on this
hybrid arrangement without synchronizing both external boot partitions.
No internal Android flash, no partition recreation, no userdata reset.
Manufacturer latest published firmware is Android 14 v2.2.0, matching the
user's previously reported Android version; full Android A/B state was not
re-audited during this CoreELEC repair.

## Add-ons and custom ports

Repositories refreshed; installed versions match the newest available from
each installed add-on's configured origin:

- Jellyfin for Kodi 2.2.0+py3
- Arctic Fuse 3.3.1
- TMDb Helper 6.17.3
- Skin Variables 2.2.4
- Jurialmunkey module 0.2.35
- InputStream Adaptive 22.3.21.1
- Up Next 1.1.9+matrix.1

Upstream automatic updates had replaced custom Jellyfin and skin source.
Ported early next-episode preparation onto Jellyfin 2.2.0, honoring its new
enableUpNext setting. Retained upstream's new multiple-segment implementation
instead of applying the old segment patch. Restored explicit unsynced IPTV
path filtering and sync queue accounting. Consolidated version-specific patch:
`patches/jellyfin-2.2.0-habibi.patch` (base a1aeda1352eb49c16d8da877121ea2068a7a7508).
Do NOT stack this patch with the older 2.1.0 patches.

Restored custom Venom home entry/browser routing, Live TV submenu additions,
and KodiSeerr RunPlugin widget actions onto Arctic 3.3.1. Generated templates
rebuilt. KodiSeerr 4.5 and the two custom companion add-ons retained their
existing source. No newer KodiSeerr package was listed in its configured repo.

Added Kodi's USER_DISABLED_AUTO_UPDATE rule (1) only for Arctic, Jellyfin and
KodiSeerr, which contain reviewed custom changes. Other add-ons retain their
existing update policy. Source update checks remain possible, but custom
add-on upgrades need port/review before installation. Private rollback files
and database snapshot: `/storage/upgrade-staging/addon-port-20260918`.

## Verification and remaining limits

- Wi-Fi technology returned automatically and connected to CoreELEC-AM9.
- SSH restored on Wi-Fi 192.168.50.169; Ethernet remains available.
- HTTP request explicitly bound to wlan0 reached Jellyfin 12.0.0 successfully.
- Jellyfin authenticated and opened its WebSocket after the source port.
- Home widgets loaded resume, next-up, favorites, movies and shows.
- No failed systemd units; add-on DB quick_check OK.
- Four next-episode unit tests; three sync-worker tests; path-exclusion tests
  passed on the newly ported source. Python compilation and four skin XML
  parses passed. Source integrity guard updated for only the reviewed files;
  no remaining source/version mismatches.

Physical TV navigation, DV/FEL, Atmos/DTS:X, lip-sync and natural episode-end
autoplay still require viewing acceptance. Do not equate these automated
checks with a full audiovisual acceptance pass. CoreELEC's keyboard-layout
and changelog UI API warnings remain upstream; neither blocked networking
or Jellyfin loading. Existing proprietary Dolby module ABI warnings remain;
module load alone is not a new Dolby playback certification.

Sources: https://relkai.coreelec.org/?dir=Amlogic-no/ce-22,
https://github.com/jellyfin/jellyfin-kodi/releases/tag/v2.2.0,
https://www.ugoos.com/firmware-update-android-14-v-2-2-0-for-am8-sk1-am9-am9-pro-sk4-and-x5m-pro
