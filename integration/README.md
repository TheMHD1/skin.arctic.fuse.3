# Arctic + Jellyfin integration

Personal non-commercial integration branch maintained by TheMHD1. Arctic Fuse 3
is by jurialmunkey. This is not an official Jellyfin, KodiSeerr or Arctic release.

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
- Example Discover nodes, offline regression tests and version/hash guard.

## Known-good source bases

| Component | Version | Source |
| --- | --- | --- |
| Arctic Fuse 3 | 3.2.19 | `c656db95c9b119f8de7fef73346e0a31f1e280d3` |
| Jellyfin for Kodi | 2.1.0+py3 | `00c33dba4658ceeaefb37ed7f1d1037e5c98feb1` |
| KodiSeerr | 4.5 | `8d23b6c14473f747080719884cd998fa98a17fc6` |
| Up Next | 1.1.9+matrix.1 | Unmodified; configured separately |

Tested on CoreELEC with Kodi22 beta/Piers. Other platforms/versions require live
verification. This branch retains Arctic's upstream addon ID/version to minimize
skin setting migration: it is a **source integration branch**, not a separate
automatic-update repository. Do not install both variants under the same ID.

## Install / update

For another device, start with [SECOND-UGOOS.md](SECOND-UGOOS.md). It documents
the setup, private/public backup boundary, audio/UI preferences and the complete
request-to-Jellyfin-to-Kodi notification path. `settings-reference.json` is a
redacted reference inventory, not a file to import into Kodi.

Read [UPDATING.md](UPDATING.md) before deploying. Never deploy during playback,
including paused playback. Never copy an entire Kodi userdata directory from GitHub.
There are no accounts, API keys, databases, device IPs or personal logs in this repo.
Authenticate Jellyfin and Seerr locally; keep Seerr settings private and prefer a
restricted user account when configuring a new installation.

Run `python integration/check.py`. It uses temporary upstream checkouts, verifies
patch application, then runs tests. It does not connect to Kodi or submit requests.
Copy the companion directory to Kodi's addons folder; apply the third-party patches
only to the matching sources after `git apply --check` succeeds. Preserve addon
licenses. Enable the companion, Jellyfin for Kodi, KodiSeerr and Up Next in Kodi.
Add the example Discover widget/submenu nodes through Arctic's shortcut manager,
or merge them into existing user nodes; do not overwrite unrelated shortcuts.

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
