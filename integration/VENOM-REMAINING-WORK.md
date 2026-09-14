# Existing-app scope — 2026-09-14

This supersedes the custom Moonfin implementation proposal. User explicitly
rejected APK/client development. Do not build or maintain a replacement app.
Custom review checkout, APKs, isolated Flutter, newly installed Dart dependencies,
NDKs 27.0/28.2, Android 34 platform and Gradle 8.14.5-specific cache were moved to
desktop Trash; preview stopped. Shared Java, Android SDK, NDK 27.1 and preexisting
Gradle tools retained. Trash is recoverable and still consumes disk until emptied.
Nothing was installed on a phone.

## Remaining acceptance checks

1. Measure favourite-channel startup through provider, gateway and Jellyfin;
   separate first bytes/decoded video from actual client first picture. Tune
   supported settings only with before/after evidence; preserve original quality.
2. Clean live names across clients using persistent gateway overrides, preserving
   channel IDs, URLs, meaningful numbers, quality and Arabic. Verify favourites
   survive refresh and updater identity resolution still works before broad rollout.
3. Expand ten curated groups using the 660 candidates, high-quality primaries
   first and backups below. Only add freshly decoder-tested channels; all users,
   preserve personal favourite removals. Verify actual published group counts.
4. Provider categories/order for channels, movies and series; no empty categories;
   shared account favourites, grids and useful artwork on supported existing apps.
5. Kodi sync-loop/performance and staged Venom improvements need live device
   verification. Ugoos is reachable again; category browsing verified below.
6. Stock Moonfin native menus cannot consume the custom category endpoint. Use
   its supported server data/favourites; do not claim web changes affect native UI.
7. Keep cautious background testing; no dead classification from congestion,
   short timeout or single failure. Multi-day evidence before reversible hiding.
8. Package/document server integrations and regressions separately from upstream
   app files. Inventory existing patched plugin/web/Kodi dependencies; do not
   claim updates are unbreakable. Check compatibility before upgrading patches.
9. Added by user: check AM9/CoreELEC/Kodi/Jellyfin updates after the current
   category/naming work, preserving custom integrations.

## Live-device follow-up, 2026-09-14

User clarified naming is wrong in Jellyfin, not Kodi. No extra Kodi label
cleanup was enabled. Venom browser now gets custom AND provider live categories
from the server instead of relying solely on PVR group import. Server returned
314 groups (ten curated, 304 provider). Custom groups are pinned, then All
channels, then provider order. Existing native shared IDs/playback are retained.
Visually verified custom category sidebar, Arabic News (30 channels, logos and
favourite stars) and English Sports (36 channels). Measured category list load
0.114s, Arabic News selection 0.206s, English Sports selection 0.425s. These
are browsing times, NOT video startup measurements.
Provider navigation also visually verified: Saudi Arabia opened 44 channels
with logos in 0.271s; provider categories appear below the pinned custom groups.

Also found launch could be refused while a modal dialog was active, leaving
the browser singleton set indefinitely. Added a five-second activation timeout
to release it and allow a later retry; does not forcibly close user dialogs.
Device backup: /storage/upgrade-staging/venom-categories-20260914/browser.before.py.

Jellyfin direct metadata-name pass is running using full-item backups and the
normal metadata update API, preserving IDs and unrelated metadata. At 03:26 UTC,
525 names were changed with all 11,249 IDs and channel numbers unchanged.
The audit saw 12 favourite differences from the old baseline; do not reset user
choices. Each direct update separately verifies its favourite stayed unchanged.
Pass is not yet complete. Gateway overrides alone were insufficient to deliver
mobile-visible names promptly because the full guide refresh is slow.
Follow-up: the first pass processed all 1,242 targets, but a still-running guide
refresh with the old catalogue reverted some names (999 remained at readback).
Cancelled that stale guide through the supported scheduled-task DELETE API;
confirmed Idle, then reran the idempotent name pass. Do not equate updates issued
with final visible count. Exact TSN readback now returns TSN 1 FHD (number 9328),
TSN 1 HD (9329), TSN 2 FHD (9330), etc. Stock clients may display the separate
channel number beside the cleaned name. Numbers are retained for stable mapping.
Reruns now use a paged name snapshot to skip clean items efficiently, still
reading and verifying the complete DTO for every actual write.
Final readback after the repair confirms all 1,242 target names changed; all
11,249 native channel IDs and channel numbers remain unchanged. Kodi's latest
deployed browser relaunch loaded categories in 0.105s. Compatibility manifest
updated only for this verified browser file (SHA256
3d43b90b583c4f3e2f7b424fc0ebaa72ccd7277d8737881170ac6dc96ff26598).

Update inventory: installed CoreELEC 22.0-Piers nightly 20260913, bundled Kodi
22.0-BETA2 (21.90.802), Jellyfin for Kodi 2.1.0+py3, Arctic Fuse 3.2.19,
Jellyfin Server 12.0.0. GitHub latest-release APIs confirm the add-on, skin and
server versions are current. CoreELEC nightly 20260914 is already downloaded in
/storage/.update, pending reboot. No firmware reboot was performed in this pass.

Confirmed at this audit: checker and presence timers enabled, 202 channels tested,
174 working and 28 inconclusive. This is a snapshot, not a completed scan.
No reliable higher distinct-stream capacity was proven by previous tests.

## Current implementation evidence

### CoreELEC update and real web verification, 2026-09-14

User explicitly requested update, post-update checks and clean shutdown. Checked
the downloaded archive's SYSTEM and KERNEL against its embedded MD5 files; both
matched. Reboot installed CoreELEC 22.0-Piers nightly 20260914, build
d9c37aa11432bd670c66ba41e12a3e9f69feb784. Kodi remains 22.0-BETA2 (21.90.802),
now git e332e9a8701738b5d811438eae073b6dc64000a8. Update staging directory is
empty; Kodi active; compatibility checker says all verified fixes intact.
Venom sidebar visually confirmed after reboot, loading categories in 0.096s.
Issued systemctl poweroff; device subsequently unreachable over SSH. Leave it
off until user turns it on. Server testing does not require the Ugoos.

Used the real browser at 412x915 on BOTH LAN Jellyfin and the public address
https://jellyfin.phinexuspanel.org/web/. Public Habibi sign-in via Quick Connect
succeeded. Visually verified category-first page, 314 groups, ten custom groups
first, Arabic News grid, and English Sports grid showing cleaned TSN names.
Channel number remains a separate standard card prefix, e.g. 9328 TSN 1 FHD.
Pre-login unauthenticated websocket 403 retries were present; no new websocket
errors found in the post-login navigation log. Do not confuse those with failed
authenticated category loading.

Moonfin: the old localhost:4174 browser tab is an abandoned custom preview,
NOT the stock installed app; it must not be used as production verification.
Shared native IDs, cleaned server names, Live TV access and account favourites
are verified server-side for all 26 users. Stock Moonfin's custom category-menu
support remains unverified/unsupported as previously documented. No app/APK
rebuild or replacement performed. Do not claim native Moonfin menu parity.

Browser screenshots: output/playwright/venom-public-mobile-categories.png,
venom-public-english-sports.png, venom-mobile-after.png, ugoos-post-update.png
in the local workspace (not public GitHub assets).

### All-account verification and tester correction, 2026-09-14

Read-only account audit verified all 26 accounts: Live TV enabled, all 397
curated native IDs visible, all 397 currently favourited, no unseeded IDs.
Provider-order audit separately confirmed all 26 receive ten pinned custom
groups plus 304 provider groups, source order preserved and no empty groups.
These verify server data, not identical native Moonfin/Jellyfin layouts.

Found a tester timeout bug: the nominal 55-second retry still set FFmpeg's
network-read timeout to 20 seconds. Changed it to match the requested probe
budget, retaining the outer hard deadline. Six regression tests pass, including
22/55-second budgets. No automatic hiding or concurrent provider probes added.
290 channels had observations at audit: 222 recently working, 68 inconclusive;
no channel met the evidence threshold for permanent hiding.
Controlled retry of gateway channel 6105 (idle gate and checker lock held)
lasted 47.74s instead of the previous ~20.3s. It still decoded no frames and
remains inconclusive; this validates the longer opportunity, not channel health.

### Native VOD category and list audit

Read-only `venom-vod-category-check.py` verified Habibi's 78 movie provider
categories and 41 series provider categories. Each returned a nonempty native
title query of the correct Movie/Series type, and the title's Genres contained
the requested category (ignoring surrounding whitespace). This avoids treating
an ignored filter or a generic nonempty result as successful category matching.
No empty provider categories found for this account. This is not an all-account
VOD-permission audit or a rendered Moonfin UI test; existing library restrictions
were not broadened. Provider Ramadan groups exist in native series filters.

Live TV list requests returned 48 channels in 0.055s and 200 in 0.095s. Movie
title page 0.339s; series title page 0.161s. Native category/filter requests in
this sample ranged 0.27–1.47s. These are server API timings, not video startup or
phone image-render timings. No change was needed to the tested category data.

Network check: local route to 192.168.50.169 is directly through Wi-Fi wlp1s0,
source 192.168.50.20. Neighbour resolution for .169 is FAILED and CoreELEC.local
did not resolve. Kodi remains unreachable; do not claim deployment or device
validation is complete.

### Full provider-category audit

`venom-provider-order-check.py` verified all 26 accounts: ten pinned collections,
304 provider categories, exact known source order, zero unranked groups and zero
empty categories in the returned Live TV summaries. This checks the provider
categories, not only the curated groups. Regression test rejects alphabetical
reordering, missing pinned groups and empty categories. This does not claim
identical rendering inside stock Moonfin or validate VOD category completeness.

### Measured-quality ordering — current follow-up

Real checker observations now confirm gateway channel 6013 (Sky Cinema
Select/Oscars 4K) decoded at 1920x1080, and 6014 (Sky Cinema Select UHD) at
1280x720. Source labels therefore cannot be treated as measured resolution.
Curator now takes fresh successful decoded geometry (at most seven days old)
before label rank, while keeping backups in lower variant tiers. Missing,
malformed, failed or stale measurements fall back to labels; untested channels
are not deleted or newly approved. Measurements do not prove native mastering
quality, bitrate, absence of upscaling, or long-session reliability.

Ten curation tests pass, including a 4K-labelled 1080p variant ranking below
an HD-labelled genuinely 2160p variant, and invalid/stale measurement rejection.
Promoter completed, publishing 390 unique channels / ten groups / 304 provider
categories. All 26 account seed runs completed, each with 390 previously seeded
IDs and zero new additions in this rerun; personal removals were not re-added.
The category plugin's five-minute cache may delay API-visible reordering.
This supersedes the earlier note that ordering was exclusively label-based.

### Resolution evidence and queued name propagation — 02:57 UTC

Checker now captures original decoded width/height from a pre-scale FFmpeg
showinfo filter in the SAME existing three-frame probe. Checksums disabled;
no second stream or download. Only numeric geometry is retained, never raw
stderr/URLs. Five checker tests pass; deployed Jellyfin FFmpeg synthetic test
confirmed 1920x1080 input is reported rather than 16x16 diagnostic output.
Already-running batch was not restarted; first real-channel geometry record is
pending its next invocation. Current quality ordering still uses provider labels;
do not claim resolution-based ranking has already been applied.

Guide still running (11.373% at audit) with a daily interval trigger. Its initial
channel snapshot predates the bulk overrides. New
`venom-name-guide-refresh.service/.timer` checks every ten minutes and requests
one follow-up only when guide is Idle and override-ledger fingerprint changed.
Requests coalesced with a six-hour minimum gap; it never cancels the running
guide or alters the existing daily schedule. First run correctly deferred with
guide_state=Running. Policy test covers running/cancelling/unknown state,
unchanged fingerprint and cooldown. A successful request is not proof the guide
finished; read-back remains necessary, with the normal daily task as fallback.

Latest native manifest at audit: 388 unique channels. Three newly seeded
favourites explain the three differences from the older Habibi snapshot; IDs
remain stable. Only one renamed channel visible so far. No claim of complete
clean-name propagation or actual-resolution ranking yet.

### Artwork/guide refresh slowdown — 02:53 UTC

RefreshGuide is running, not dead: progress moved from 10.525% while examining
channels. Recent logs repeatedly report failures converting channel logo URLs
from the gateway; sequential image waits are delaying metadata propagation.
The previous guide run took about 103 minutes. No repeated restart was performed.

Deployed artwork-only nginx settings: connect 2s, send/read 5s, cache-lock wait
5s for live logos, VOD logos, VOD images and programme posters. Previously these
locations inherited 75s connect/300s read from streaming defaults. Existing stale
images can additionally serve during upstream 500/502/503/504 responses. Read
timeout is an inactivity timeout, not a strict end-to-end deadline; cold slow
logos can temporarily fail and retry later. No fake successful placeholder,
new auth bypass, image-cache purge or video-stream timeout change was added.

`nginx -t` passed; graceful reload completed. Diff against the saved live config
contains only those four artwork blocks. Working cached logo 412: HTTP200 in
0.010s after reload (0.035s before; cache timing is not a cold-fetch benchmark).
Missing logo 476 returned HTTP404 in 0.216s. Those checks prove existing success
and failure routes still respond, not an overall playback speed improvement.

Persistent config `/data/config/iptv-venom/nginx/default`; backup
`backups/nginx-before-artwork-timeouts-20260914.conf`. Restore that file, validate
with `docker exec dispatcharr nginx -t`, then gracefully reload to roll back.
Source `ops/dispatcharr-nginx.conf` uses NGINX_PORT placeholder rendered to 9191.
Reference: https://nginx.org/en/docs/http/ngx_http_proxy_module.html .

### Follow-up: all-account verification and persistent maintenance

`venom-verify-collection-order.py --all-users` completed successfully for all 26
accounts. For every account it resolves accessible native IDs first, then checks
all ten category API pages for exact membership, total counts and ordering. Each
account received the 385-channel manifest. This proves server API behaviour, not
stock Moonfin menu support or rendered client behaviour. User favourites were
not changed by this read-only audit.

`venom-channel-names.service/.timer` is enabled on media CT102, running after boot
and every six hours thereafter. It uses the built-in persistent gateway override
table, not modified container source. It has a five-minute bound and exclusive
file lock. First service run: Result=success, ExecMainStatus=0. Eight regression
tests pass, including manual-name preservation and updating our old override
when a provider later supplies a new already-clean name. The previous version
would have left the obsolete override in that latter case; this is fixed.

Installed scripts are `/data/config/dispatcharr/venom-channel-names.py` and
`venom-channel-name-overrides.py`. Recovery ledger is
`/data/config/dispatcharr/venom-name-overrides.json` (private). Pause automation
with `systemctl stop venom-channel-names.timer`; existing names persist. Never
clear other override fields to undo a name. Recheck ChannelOverride API/model
compatibility before a gateway major update; do not blindly patch upstream code.

At this audit the guide refresh had only published the first canary name. Do
not equate 1,242 gateway changes with 1,242 verified Jellyfin changes. Both local
SSH and a media-server network check could not reach Ugoos 192.168.50.169.
Checker snapshot: 226 tested, 196 working, 30 inconclusive, no automatic hiding.

Latest: canary renamed in Jellyfin successfully, all 11,249 channel IDs stable
and zero Habibi favourite changes. Applied remaining 1,241 gateway overrides
(1,242 total). Other app refresh/read-back remains pending, not a completed
all-client verification. Curated native groups now 385 unique channels: Arabic
news 30/general 37/movies 36/kids 25/sports 107; Canada 30; English news 26/kids
28/movies 30/sports 36. All 26 accounts have Live TV access. Updated guide
maintenance so name-only overrides do not prevent future exact EPG mappings.
These updates supersede the intermediate canary-only status below.

- Seven name/curation tests pass. Seeder supports cleaned names plus exact channel
  number, fails on collisions, preserving IDs across persistent gateway renaming.
- Gateway built-in ChannelOverride.name is untouched by upstream auto-sync. New
  script `venom-channel-name-overrides.py` defaults to dry run, preserves manual
  names/other overrides, records original values before changes. Dry run found
  1,242 eligible names. Only gateway channel 553 was applied as a canary. Full
  rollout is NOT done; Jellyfin guide refresh is still running. Do not re-trigger
  it repeatedly. First intermediate verification: all 11,249 IDs and favourites
  stable, zero renames visible yet.
- Startup test: favourite Al Jazeera (UK NEWS HD), PlaybackInfo 10.73s, first HLS
  segment a further 0.31s (11.04s total). Repeated BBC WORLD NEWS: PlaybackInfo
  0.05s, first HLS segment 4.40s (4.45s total). Jellyfin logs attribute the slow
  first preparation to media-info probing; cached repeat probe took 0.0146s.
  Earlier BBC 15.15s test overlapped checker shutdown, so is NOT a clean baseline.
  Tests force 1.5Mbps mobile transcoding; they do not measure native client display
  buffering or direct-play quality. No probe setting or playback quality changed.
- Checker paused for isolation and subsequently resumed. Both checker/presence
  timers active. No client fork, quota increase or automatic hiding deployed.

Implementation references: Dispatcharr built-in overrides verified in installed
ChannelOverride model and effective M3U output, plus
https://dispatcharr.github.io/Dispatcharr-Docs/channels/ . Jellyfin upstream
M3uParser derives channel identity from stream URL, not display name; actual
canary read-back still required, not inferred solely from upstream source.
