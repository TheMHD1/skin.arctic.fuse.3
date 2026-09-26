# Reproducing this Kodi / Arctic setup

Originally captured 2026-09-13 and updated after the September 22 r6 acceptance.
This is a commissioning reference, not a firmware image or a one-click installer.
Never import the redacted settings JSON as Kodi settings. See
[CUSTOMIZATIONS.md](CUSTOMIZATIONS.md) for the current feature/status inventory.

For the current remote-house build, the
[September 26 catch-up record](REMOTE-AM9-PARITY-2026-09-26.md) supersedes the
historical remote-not-installed/firmware-held statements below. Preserve its
separate HTTPS route and standalone SD storage. The September26
[import/subtitle publication repairs](IMPORT-REQUEST-REPAIRS-2026-09-26.md)
also supersede the older full-reconciliation notification timings in this guide:
exact imports and subtitles now have targeted, verified, finite-retry publishers.
Do not install duplicate server workers on a client.

The accepted local/LAN device and the remote-house device are intentionally
different cohorts. The local r6 cohort has physical search, native-original and
IPTV handoff acceptance. The remote r6 overlay is source-tested but not installed;
it remains Jellyfin/HTTPS-only with Native mode disabled. Do not infer that the
held CoreELEC update or remote P7 routing is included in either addon cohort.

## What is preserved, and where

- This public fork: custom skin source, Jellyfin Home companion, pinned Jellyfin
  and KodiSeerr patches, regression tests, widget examples, timeline seek script
  and keymap, safe settings inventory, installation/update/rollback instructions.
- `release/`: portable, hash-pinned payload builders and guarded exact-cohort
  update source. It does not contain a real device profile or generated payload.
- `settings-reference.json`: installed addon IDs/versions and explicit saved Kodi
  and selected addon settings. Numeric values retain Kodi's enum representation;
  arbitrary strings, identities and credentials are redacted. Installed does not
  imply enabled. Implicit defaults are defined by the pinned addon versions.
- Private media-server backup: full Kodi userdata/settings, addon source, online
  SQLite database copies and CoreELEC custom configuration. Full private values
  belong there, not on GitHub. Thumbnails, transient files and rebuildable caches
  are intentionally excluded. Firmware/whole-disk images are not included.
- Do not clone connection identities, SSH host keys, network state, tokens,
  backup keys, notification history or the old box's hardware calibration.

## Second-box preparation

1. Confirm the second Ugoos model and hardware revision. If not the same model,
   use its supported CoreELEC image/device tree and validate HDR/audio separately.
   The reviewed cohort is AM9 Pro on CoreELEC 22 / Kodi 22. The exact OS build is
   a private deployment choice; a later CoreELEC nightly remains deliberately held.
   Do not flash Android or copy the first box's boot media merely for a skin setup.
2. Give the second device a unique hostname, network address and remote-access
   identity. Install CoreELEC onto the intended media using its normal procedure.
   Do not blindly clone the first box's hybrid SSD/SD mounts or identifiers.
3. Install matching addon dependencies. Use the inventory as reference; native
   binaries such as InputStream Adaptive must match the platform and Kodi major.
4. Install the reviewed base cohort first: Arctic 3.3.1, Jellyfin for Kodi
   2.2.0+py3, Home companion 1.1.0 and, when wanted, Venom TV 1.3.1. Follow
   [UPDATING.md](UPDATING.md), run `python3 integration/check.py`, then use
   `release/README.md` to build a payload. The guarded installer is for a known
   cohort; it is not a substitute for these blank-device steps. Build Arctic
   from reviewed upstream 3.3.1 source plus
   `patches/arctic-3.3.1-habibi.patch`. The repository-root skin is a legacy
   3.2.19 baseline: do not install it as 3.3.1 or edit only its addon version.
5. Sign in to Jellyfin for Kodi with the desired account. Using the same account
   shares resume positions, watched status and Jellyfin Favorites between boxes.
   Let each installation create its own client/device identity and library DB.
6. Configure KodiSeerr against the existing Seerr service using private settings;
   authenticate locally. Do not create a new Radarr/Sonarr stack for this box.
   Preserve server quality profiles. Current default profiles are Ultra-HD;
   a profile name is not a guarantee of a particular release's availability.
7. Import/merge `home-widgets.json`, `home-videos-only.json`, and the Discover
   widget/submenu examples into the matching script.skinvariables node names.
   Set HomeSwitcher.Home.Shortcut.Path = ActivateWindow(videos), and name hub
   1101 Discover. Keep unrelated per-device shortcuts if any.
8. For exact visual preferences, use the private Arctic settings.xml as a
   reference or selectively restore it with Kodi stopped. Do not overwrite all
   guisettings.xml blindly: audio devices, resolution/calibration and CEC can
   differ even between identical boxes on different TVs.
9. Copy `ugoos-osd-seek.py` to `/storage/.config/ugoos-osd-seek.py` and
   `zz-habibi-osd-seek.xml` to Kodi userdata/keymaps. It changes left/right to
   -/+30 seconds only on Arctic's focused video timeline (control 8200); ordinary
   navigation is unchanged. Re-check the control ID after major skin upgrades.
10. Create a private deployment profile from the redacted release example. Review
    the no-write plan and exact version/source/manifest checks; do not bypass a
    refusal on a new or drifted installation. Apply while idle, retain its backup,
    rebuild templates with `no_reload=true`, then restart/reload only while idle
    (paused playback also counts as active).
11. Validate playback, resume across phone/boxes, subtitles, HDR, audio sync,
    next-episode prompt/autoplay, requests, Favorites, and both IMDb and YouTube
    trailer paths. Generate a reviewed per-device integrity baseline afterward.
12. Set up a separate private backup destination for the second device. Do not
    point two devices at the same rsync mirror or copy the first backup identity.

## Experience settings

Optional IPTV additions are documented in [VENOM-PACKAGE.md](VENOM-PACKAGE.md).
Install Venom 1.3.1, label/enable the native Live TV hub as Venom TV, and use the
Default (Unicode) interface font. Configure IPTV Simple privately and authorize
the second device's network route. Merge optional Home scopes and unsynced-library
path exclusions using the second installation's own authenticated server/library
selection. The gateway uses one independent upstream stream at a time; higher
distinct-stream capacity has not been established reliably. Native channel,
movie and series favourites use the signed-in Jellyfin account and are shared.
Category bookmarks and pending legacy local state are device-local. Do not
assume every direct provider-playback route reports cross-device resume state.

Home uses server-backed Continue Watching, Next Up, Latest Movies, Latest Shows,
Favorites and Top Rated. Latest Shows uses DateLastMediaAdded ordering; Top Rated
is Jellyfin CommunityRating, not IMDb Top 250. Home opens Videos directly; Music
and Pictures are removed from the Home submenu. Discover is separate.

Arctic 3.3.1 (reviewed upstream source plus the maintained patch, not the legacy
repository-root tree); Jellyfin for Kodi 2.2.0+py3; KodiSeerr 4.5; Home companion
1.1.0; Venom TV 1.3.1 when enabled; Up Next 1.1.9+matrix.1. See the inventory for
the remaining installed addons. Older 3.2.19/2.1.0 patches are historical and
must not be stacked onto this source cohort.

Up Next: enabled, automatic mode 0, stopAfterClose=false, includeWatched=true,
playedInARow=3, customAutoPlayTime=false, autoPlaySeasonTime=120. Preserve the
patched Jellyfin startup handoff; configuring Up Next alone is not the full fix.
Jellyfin mediaSegmentsEnabled=true, skipIntroductionMode=2; server segment
support is also required. Prompt timing and subtitle polling are separate.

Jellyfin playback: playFromStream=true, playFromTranscode=false; codec-specific
forced transcoding disabled. syncDuringPlay=false: local library sync may wait
until playback ends. markPlayed=90. Use the reference client mode; do not add a
server GUID to playback routes (the default client registry key is different).

Audio reference: HDMI passthrough enabled for AC3, EAC3, DTS, TrueHD and DTS-HD;
AC3 transcoding off; stereo upmix off; refresh adjustment enum 2 and refresh delay
3 seconds. These are capabilities of the first TV/speaker chain, not a promise
that every HDMI device supports them. Reference GUI screenmode is DESKTOP.
Subtitle font size 42, vertical margin 4.95, style overrides off. Preserve user
language/font preferences privately; test Arabic shaping on the second screen.

Trailers: SlyGuy Trailers plus InputStream Adaptive (reference 22.3.21.1).
Known IMDb IDs use direct trailer routes; discovery-only titles may resolve to
YouTube adaptive streams. Normal OK on unavailable media opens its request
action. Long-press OK -> Watch trailer does not submit a request. No autoplay
previews, global YouTube redirects or library-wide trailer scraping enabled.

## Request-to-playable flow and notifications

Discover request -> Seerr approval/search -> Radarr/Sonarr download and import ->
custom server reconciliation -> Jellyfin library update -> Kodi/Jellyfin sync
and widget refresh. Total download time is not fixed: approval, release/seed
availability, file size, downloader speed and queued processing all matter.

Verified server configuration:

- Radarr and Sonarr import/upgrade hooks publish a durable reconciliation trigger.
- An active path watcher launches the worker; a timer retries/reconciles 15 minutes
  after its previous run finishes, plus up to 30 seconds jitter. Worker timeout
  is 30 minutes. The worker notifies Jellyfin via Library/Media/Updated.
- Jellyfin library realtime monitoring is off; do not assume an inotify fallback.
- Seerr download status sync runs every minute. Its Jellyfin recently-added scan
  runs every five minutes; full scan daily at 03:00 server time.
- Seerr webhook agent is enabled for custom automation. Email, browser push,
  Telegram and the other configured personal notification agents are disabled.
  The webhook is not evidence of a phone notification or direct Kodi push.

Verified Kodi configuration:

- KodiSeerr polls requests every 300 seconds and shows a five-second toast when
  a tracked media status changes to available. Declined alerts enabled;
  approved/processing alerts disabled. First run records a baseline, avoiding
  notifications for the entire existing library.
- The current notifier reads the default /request response without pagination
  and detects status 5, not partial-availability status 4. It is therefore not a
  guaranteed notification for every old request or every newly added episode.
- Home and Discover refresh on entry and every 60 seconds while idle and without
  a modal dialog. Home also schedules refresh after library events/player stop.
- Jellyfin for Kodi has its own server connection/library synchronization;
  syncDuringPlay=false can defer the local-library update while watching.

When healthy, new imports should trigger server processing promptly, but the
five-minute Seerr scan and five-minute Kodi poll can add roughly ten minutes to
the availability toast after Jellyfin sees the item. This is an estimate, not an
SLA; Kodi must be running and the request must be covered by the notifier.

The final September 22 fleet record supersedes the original capture's transient
worker/storage note: the maintained reconciliation and service-health checks
completed after coordinated maintenance. That operational result still does not
belong in a new Kodi device profile. Server media, queues, databases, paths and
credentials remain private and must be verified independently rather than copied
from this public guide.

## Upgrade versus replacement

For an existing reviewed box, build the public release and use its guarded
transaction with the matching private profile. It should refuse unknown addon
versions, partial local/remote cohorts, active or paused playback, source drift,
manifest drift and changed settings during shutdown.

For a replacement or truly new box, complete every preparation step above first.
Create new client and backup identities, authenticate locally, validate that
device's AV/network/PVR capabilities, and only then establish a reviewed cohort.
Never reuse another box's private profile merely to satisfy the installer.
