# Remote-house AM9 parity — September 26, 2026

This is the remote-house catch-up/rebuild record. Its source and safe policy
belong in this fork; device profiles, identities, URLs, inventories, logs and
recovery archives remain in the private operations record.

## Preserve the remote boundary

The same user-facing experience does not mean an identical userdata directory.
Keep the remote device's own Jellyfin/Seerr authentication, client identity,
network configuration, database, permissions and backup destination.

- Jellyfin and Seerr use their configured certificate-verified public HTTPS
  endpoints. Changing houses must not require access to the original LAN.
- Venom uses its reviewed remote-Jellyfin overlay and existing remote marker;
  native library playback remains disabled. No private provider/PVR credentials
  or original-house NFS mappings should be copied into this profile.
- The remote route retains the server's compatible Dolby Vision publication.
  It does **not** implement original P7/FEL delivery over a new private network.
- A standalone SD installation must use the normal, reviewed CoreELEC update
  path; never reuse the original device's exact hybrid SD/SSD script or UUIDs.
- Audio passthrough/refresh/seek/Up Next preferences can share the reviewed
  baseline. HDMI calibration, physical CEC behavior and lip-sync need that
  device's actual display/speaker chain.

## Controlled source migration

### CoreELEC target

The owner requested the newest compatible official build during deployment.
The live [official nightly listing](https://relkai.coreelec.org/?dir=Amlogic-no/ce-22)
showed `22.0-Piers_nightly_20260926` for Amlogic-no/aarch64. This is still a
nightly, not a stable release. The earlier same-as-local September22 step and
the later September26 step use the same normal standalone-SD updater, not the
hybrid recovery procedure. Android is not flashed or changed.

Reviewed package:
`CoreELEC-Amlogic-no.aarch64-22.0-Piers_nightly_20260926.tar` from the
[official download](https://relkai.coreelec.org/Amlogic-no/ce-22/CoreELEC-Amlogic-no.aarch64-22.0-Piers_nightly_20260926.tar).

| File | Locally verified SHA256 |
| --- | --- |
| Tar | `3c083fd66f235fdbe0df4a6b3c888e471540966e61f611edda2de08feca5e466` |
| KERNEL | `e08b9029bf58147355b98ef75d62c6f8a82527386ba9941ec607f6f092f289c5` |
| SYSTEM | `1210c0d0d2049e4b9fddd5c6315c9101f72790e8a1b6e04594eaa22b82e6a90e` |

Both embedded MD5 checks passed; these SHA256 values are local observations,
not an upstream-published signature. Validate exact hardware, card/mount/UUID
identity, source version, preserved device config and free space first. Back up
boot/config files and the device's own consistent Kodi snapshot off-box. Transfer
outside `.update`, verify the complete file, then atomically move it into
`.update` and use the normal reboot/update. Never write the remote appliance's
private UUIDs or scripts into this public fork. Afterward verify the running
build, kernel/SYSTEM hashes, empty update directory, network, Kodi and Dolby
module load, not just the version label.

September22→26 compatibility inspection found the same AM9 Pro stock DTB,
kernel module version5.15.196 and Dolby loader bytes; Kodi's Python/GUI,
InputStream, PVR and binary-main ABI manifests are unchanged. The existing
external Dolby module is preserved, including its known cross-build warning;
successful load is checked separately from HDMI/FEL acceptance.

Relevant upstream changes are [HDR/DV GUI compositing](https://github.com/CoreELEC/xbmc/commit/d3223282db7a69d5641684a7af8dd301373c50b8),
[GUI peak luminance](https://github.com/CoreELEC/xbmc/commit/b099b15afab9053879733fa9f713bc9cb10875d2),
[hardware-plane timing after internal pause](https://github.com/CoreELEC/xbmc/commit/97eeb9ca3c748c88d775eda0971d26ba330571be),
[OSD HDR bypass](https://github.com/CoreELEC/common_drivers/commit/dc8d2939a7b0204e9b54a3234b8edd338b17e1bd)
and [DV display-luminance conversion](https://github.com/CoreELEC/common_drivers/commit/23b23cb6b709d53a5b7cb2cc6984f0c4d16bb125).
These are expected picture/overlay/sync improvements, not proof of a difference
on a disconnected TV. The direct AMLCodec comparison was unchanged; do not call
this a newly demonstrated FEL/seek fix. The Kodi history was rebased, so the raw
hundreds-of-commits comparison is not a valid list of all-new changes.

### Addon sequence

The historical remote baseline first needs the existing
[`release/kodi/`](release/README.md) remote R6 bundle: general library search,
secure HTTPS defaults and bounded remote Venom work/caching/favourites.
Next apply the reviewed remote Home/search and search-priority overlays, using
the remote device's own generated nodes rather than another box's GUIDs.
The exact migration guards and tests are maintained with those installers.

The existing source versions remain Arctic3.3.1, Jellyfin-for-Kodi2.2.0+py3,
Home1.1.0 and Venom1.3.1. Version equality alone is insufficient: whole-file
hashes, the live integrity manifest, runtime route policy and per-device profile
must also match. Unknown or partial cohorts must stop for review.

Merge the [always-awake/OLED policy](device-policy/always-awake/README.md)
separately: zero idle shutdown/display-off timers, black screensaver after three
minutes including paused/static-audio screens, and CEC standby ignored while
retaining ordinary CEC controls. Merge only policy fields; do not overwrite the
other device's physical addresses or controller settings.

## Verification and rebuild limitations

Headless verification covers source integrity, service readiness, authenticated
HTTPS access, authorized library scopes, server-backed listing/search/rating
routes, IPTV categories, bounded pagination/artwork, settings persistence and
private backups. An accepted request/session command is not proof of an on-TV
notification. Empty Continue Watching is valid for an account without progress.

Physical picture/audio, remote-control interaction, HDMI HDR/DV negotiation,
receiver Atmos/DTS:X indication, TV-off/on behavior, subtitle rendering and
throughput on the eventual outside network remain separate acceptance gates.
Do not force EDID, clone a resolution whitelist or claim those tests passed
without that hardware.

### Deployment and headless acceptance

The standalone remote device is running the verified September26 image. Remote
R6 (11 changed paths), R7 (9 paths) and search/ratings (13 paths) were deployed
through separate guarded transactions, each with a private rollback snapshot
and a zero-change follow-up plan. The original local/hybrid AM9 was read-only
throughout this work and remains on September22.

Authenticated tests of the installed code and actual Kodi plugin routes passed:

- Continue Watching used descending last-watch activity, not download date;
  recently added movies/shows used newest-added order. Next Up returned the
  account's eligible row. An empty Favourites result was valid for this user.
- Owned-library movie/show search worked, including spaced/joined title forms;
  Venom search remained separate. Actual Kodi routes returned populated lists.
- All 30 sampled owned movie cards had real IMDb ratings from the bounded batch
  endpoint. This is a sample, not a guarantee that every title has IMDb data.
- Public, certificate-verified HTTPS access worked for Jellyfin and Seerr;
  owned-media byte-range delivery returned206 without a private-address redirect.
  It did not start playback or change the user's watched state.
- Remote Venom movie/series categories, bounded first-page listings, artwork,
  Live TV categories and sampled exact Jellyfin channel IDs were reachable.
  No real channel switching or HDMI playback was claimed in this headless pass.
- All three checked Kodi/Jellyfin SQLite databases passed `quick_check`.
  Wired and wireless profiles remain DHCP. The six awake/OLED settings and
  merge-only CEC policy survived restarts. Explicit screensaver activation
  reported screensaver active and DPMS off, with Kodi/SSH still available.

The CEC adapter registered, but the attempted configuration-read trace was
inconclusive without HDMI. TV-off/on, the real three-minute idle transition and
physical CEC acceptance therefore remain pending. Shared server-side
import/subtitle/notification repairs already apply to authorized remote users;
do not install duplicate server jobs on the AM9. Notification session capability
was confirmed, not an on-screen request-ready delivery.

### Two inherited issues found during the final log review

The old clone's broad backup exclusion removed the legitimate
`slyguy.dependencies/resources/modules/urllib3/packages` source directory.
Restore the four missing files from the exact official0.0.30 addon archive;
the independently installed global urllib3 addon is unrelated. The official
archive SHA256 observed for this repair was
`ff651f4ca1a6afb963868dc0a962064236b5c9c726a04b9425e43916fb3cb7f2`.
The [bounded backup exclusion policy](device-backup/README.md) prevents future
snapshots from repeating that omission. SlyGuy's actual Kodi shared service
started successfully after restoration, with no Python traceback. Trailer
resolver/playback and physical menu interaction still need separate acceptance.

The poster-rating indicator also needed a default `poster_rating=false` for
callers that do not supply the parameter. Without it, Kodi parsed a bare `!`
condition. The search-priority overlay now emits that default on fresh builds
and provides a guarded two-file Objects/manifest migration from the single
known old output hash. A regression checks migration, idempotence and rejection
of unexpected transformed bytes. This late repair is not yet deployed on the
read-only local device; it is preserved for that device's next reviewed update.

The remote two-file repair applied successfully and replanned to zero. A fresh
startup had no Python traceback or missing-operand/boolean-parser errors. Two
upstream XKB Compose-file errors remain in the headless image (optional composed
physical-keyboard input); this is not a claim of an entirely error-free OS log.
No failed system services or database integrity errors were found.
Two optional studio-logo assets were also unavailable when library cards were
loaded; this does not block listings or playback and was not patched by adding
unverified artwork. The final54-entry live source manifest had zero drift after
reconciling the already-reviewed Skin Variables whitespace rewrite.

## Recovery

Take and verify a private, per-device addon/settings/SQLite-consistent backup
before changing source. OS updates require a separate boot backup and exact
official package verification. Retain an off-device recovery copy. Each addon
transaction records its own changed-file rollback directory. Restore those
matched sources/manifests while Kodi is stopped; never restore another user's
database, token, device GUID, host key or network configuration.

The final private snapshot includes all four restored dependency files, the
worker's new policy import/module and all54 tracked source files with zero
manifest drift. All nine archived SQLite databases passed `quick_check` after
private temporary extraction. A matching-SHA256 off-device copy was retained on
the media server. Existing daily idle-only backups still keep three local
snapshots; this does not configure ongoing offsite delivery after relocation.
