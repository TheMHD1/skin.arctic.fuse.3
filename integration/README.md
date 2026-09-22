# Arctic + Jellyfin integration

Personal non-commercial integration branch maintained by TheMHD1. Arctic Fuse 3
is by jurialmunkey. This is not an official Jellyfin, KodiSeerr or Arctic release.

The durable feature/version/status inventory is
[CUSTOMIZATIONS.md](CUSTOMIZATIONS.md). The portable builder and guarded update
source start at `release/README.md`. They intentionally exclude credentials,
userdata, private device profiles, generated payloads and rollback archives.

Current acceptance boundary: the local/LAN AM9 cohort has accepted revision r6
client changes; the separately tested remote-house cohort is staged but not
deployed. A CoreELEC update remains held and is not authorized by these addon
instructions. Historical records describing both devices as offline or r5 as
current are retained only as history.

## Layout

- The skin change is deliberately small: KodiSeerr widget request/detail actions
  use RunPlugin instead of attempting video playback. Real movies use PlayMedia;
  show folders use ActivateWindow. Ordinary Arctic widgets are unaffected.
- `plugin.video.habibi.resume/`: Jellyfin Home companion, reading the existing
  signed-in Jellyfin-for-Kodi account. Server-backed resume/favorites, episode
  browsing, title formatting, pagination, latest-show ordering and refresh service.
- `patches/kodiseerr.patch`: exact-ID Jellyfin playback and Favorites integration,
  fresh request guards, safe success reporting, bounded caching and quieter probes.
- `patches/jellyfin-kodi.patch`: prepare next episode at startup and retain distinct
  subtitle/media-segment intervals. Up Next still owns prompts/cancel/still-watching.
- `patches/jellyfin-tls-secure-default.patch` and
  `patches/jellyfin-native-originals.patch`: the reviewed 2.2 TLS default and
  narrow native-library original-path policy. The native helper is required;
  this is not a global HTTP/STRM/PVR switch.
- Example Discover nodes, offline regression tests and version/hash guard.
- Optional `plugin.video.venom.tv/` and native IPTV poster hub. See
  [VENOM-PACKAGE.md](VENOM-PACKAGE.md) for private setup requirements and
  reproducible package checks. Version 1.3 adds a category/sidebar grid and
  shared Jellyfin-account favourites. See [current verified scope and limits](VENOM-REMAINING-WORK.md),
  especially the distinction between web categories and stock Moonfin menus.
  Apply `jellyfin-iptv-update-filter.patch`
  after `jellyfin-kodi.patch` to cover deliberately unsynced Season updates too.
- `patches/venom-remote-performance.patch` and `remote-venom/`: the distinct
  Jellyfin/HTTPS-only remote cohort. Never replace it with the local PVR build.
- `patches/dispatcharr-live-admission.patch`,
  `patches/dispatcharr-disconnected-keepalive.patch` and
  `server/dispatcharr-nginx.conf`: version-specific Dispatcharr 0.31 transport
  source. Server deployment remains a separately guarded operation.
- `server/jellyfin-custom/` and `server/dovi/`: portable server patch/test source.
  Production databases, media, queues, Compose files and credentials are not
  public release inputs.

## Current reviewed cohort

| Component | Version | Source |
| --- | --- | --- |
| Arctic Fuse 3 | 3.3.1 on accepted devices | Reviewed upstream 3.3.1 source plus `patches/arctic-3.3.1-habibi.patch`; the repository root remains a legacy 3.2.19 baseline |
| Jellyfin for Kodi | 2.2.0+py3 | Exact upstream commit pinned by the release builder |
| Home companion | 1.1.0 | `plugin.video.habibi.resume/` |
| Venom TV | 1.3.1 | Local and remote cohorts are separately hash-checked |
| KodiSeerr | 4.5 | `8d23b6c14473f747080719884cd998fa98a17fc6` |
| Up Next | 1.1.9+matrix.1 | Unmodified; configured separately |

The repository-root skin tree and its `addon.xml` deliberately remain the legacy
3.2.19 integration baseline. **Do not package or install that root tree as the
current 3.3.1 skin, and do not change its addon version alone.** Current devices
use reviewed upstream 3.3.1 source plus `patches/arctic-3.3.1-habibi.patch`, then
the r6 search/template overlay. The release installer assumes a reviewed 3.3.1
cohort already exists; it does not perform this base migration. Jellyfin 2.1.0
patches are likewise historical and must not be stacked with the current 2.2
cohort. Tested on CoreELEC with Kodi 22/Piers; other platforms require live
verification. The maintained skin retains Arctic's upstream addon ID to minimize
setting migration; do not install both variants under the same ID.

## Install / update

For another device, start with [SECOND-UGOOS.md](SECOND-UGOOS.md). A new device
must first be commissioned with its own OS, identities, accounts, settings and
base addons. The exact-cohort release installer is an update overlay and should
reject a blank or unknown installation. `settings-reference.json` is a redacted
reference inventory, not a file to import into Kodi.

Read [UPDATING.md](UPDATING.md) before deploying. Never deploy during playback,
including paused playback. Never copy an entire Kodi userdata directory from GitHub.
There are no account passwords, API keys, user databases or personal logs in this
repo. Some server automation has deployment-specific paths and private network
addresses; review those before adapting it to another server.
Authenticate Jellyfin and Seerr locally; keep Seerr settings private and prefer a
restricted user account when configuring a new installation.

Run `python3 integration/check.py` for the complete source integration. Use
`integration/release/README.md` to build a hash-pinned payload and guarded staging
envelope from clean inputs. Generated payloads and real private profiles are not
committed. Run `python3 integration/release/verify-preservation.py` before release
handoff. For manual development, apply third-party patches only to their exact
matching source after `git apply --check`; preserve licenses and never overwrite
unrelated shortcuts or userdata.

Configure Up Next for automatic playback, include watched episodes for rewatches,
120-second prompt, three-episode still-watching check. Preserve personal settings
where they differ. Intro/outro buttons require compatible server media segments.

## Trailers and backups

Optional SlyGuy Trailers adds Watch trailer actions. Home supplies provider IDs,
with an IMDb trailer route where possible; discovery-only titles use the addon's
lookup. No autoplay previews. External trailer availability can change. We
use direct PlayMedia IMDb routes for exact-ID context actions: SlyGuy's generic
script can otherwise misinterpret an IMDb route's video_id as a YouTube ID.
The generic script remains the fallback for titles without a known IMDb ID.
This repo does not bundle SlyGuy binaries or replace the YouTube addon.
Install/enable InputStream Adaptive from the device's matching CoreELEC/Kodi
repository as well: YouTube/DASH trailer results can require it even when direct
IMDb trailers already work. Do not use a binary built for another Kodi major
version or CPU architecture. Normal OK on an unavailable Discover title opens
the request action; Watch trailer is a separate context-menu action.

Back up Kodi configuration, addon source and custom CoreELEC files to a private
server. Make online SQLite backup copies instead of copying live library DB/WAL
files. Exclude rebuildable thumbnails/TMDb caches. Keep multiple versions, protect
credentials in backups, and test restoration in a separate directory. The update
guard is not a backup and cannot restore missing settings.

## Scope and limitations

Main Discover/Requests matching uses exact `(media type, TMDb ID)` pairs and only
the first signed-in Jellyfin account. No fuzzy-title playback fallback. Generic
upstream KodiSeerr screens outside these routes may retain their original behavior.
Favorites for not-yet-owned titles are not Jellyfin Favorites. CommunityRating is
not IMDb Top250. Newly added show ordering uses returned DateLastMediaAdded.

The startup integrity guard warns after addon version/file changes. It never
reapplies old patches automatically. Its example baseline represents the tested
build; regenerate a deployment baseline only after reviewing/testing the intended
files. Keep backups and live-device tests separate from offline CI.

## Licensing

Arctic remains CC BY-NC-SA4.0; see the root LICENSE.txt. The companion is MIT.
KodiSeerr patches derive from yocksers/KodiSeerr (MIT); Jellyfin patches derive
from jellyfin/jellyfin-kodi (GPL-3.0). Their upstream licenses continue to apply.
Do not remove upstream credits or treat this fork as a commercial redistribution.
