# Venom performance and endless Kodi updates — 2026-09-13

This is a historical implementation and validation record. For the current
supported device-update scope and source-of-truth paths, see
[CUSTOMIZATIONS.md](CUSTOMIZATIONS.md).

## September 22 source follow-up — staged, not installed

The older input-callback queue below still ran network requests synchronously
in the script loop. A new independently reviewed source patch adds one bounded
data worker, latest-request replacement/cancellation, generation-guarded result
application, and safe close/navigation behavior. It also replaces the separate
favourite refresh thread with that same worker, preserves confirmed mutations
and their refresh acknowledgment, and fixes asynchronous bookmark continuation.
Only data-read PVR RPC runs in the worker; GUI and playback operations stay on
the main loop. Cached PVR IDs receive fresh exact validation with exact Jellyfin
fallback; duplicate channel metadata resolution was removed. No fixed Stop or
sleep, stream-limit, quality, decoder or GPU changes are included.

Final verification: 29 browser, seven shared-favourites and eleven TV tests;
full integration/patch/XML/compile checker passed. These are source-level proofs,
not measured AM9 switching improvement. An in-flight socket still has its bounded
eight-/20-second timeout; cooperative chunk/page cancellation keeps it away from
the GUI loop. Closed-window favourite mutations finish their bounded commit
before script teardown.

Payload staged on Media CT102 at
`/data/config/coreelec-staging/iptv-performance-20260922/`, including reviewed
hashes, baseline provenance and installation/rollback cautions. Recheck actual
device addon versions/hashes, back up code and integrity manifest, then apply
only while idle and update reviewed integrity entries. Physical category,
favourite, Back/reopen and A→B→C playback tests remain pending while AM9 is off.
No deployment or GitHub push is claimed by this source follow-up.

The server artwork cache was independently measured working; warmed responses
are sub-millisecond to low-millisecond. No duplicate cache service or speculative
provider tuning was added. Detailed cross-server audit lives in the operations
record `exec-iptv-performance-2026-09-22.md` outside the public fork.

## September 22 remote-house overlay — source/staged only

Moustafa's remote build has a separate HTTPS/Jellyfin catalogue route. Preserve
it with `patches/venom-remote-performance.patch` applied to the reviewed common
Venom source, plus `remote-venom/remote_catalogue.py`. Do not install Omar's raw
browser/default files over a box carrying `remote-native.json`.

The overlay adds the same bounded worker and cancellation without loading the
private PVR playlist/gateway credentials. Live groups and channels come from
Jellyfin; exact channel playback cancels stale navigation and opens the known
Jellyfin ID on the main loop, with no PVR enumeration or redundant resolution.
Movie/series requests retain scoped provider genres and 160-title remote pages.
Snapshots/cache keys include the server offset and search query. Back restores
offset/query/page/selection, and navigation controls cannot become favourites.
Confirmed favourites retain the acknowledged critical mutation path. Old private
provider/PVR bookmarks fail closed and can be removed/reselected in the browser.

`test-venom-remote.py` applies the maintained patch in a temporary tree and runs
44 regressions: 29 common/local plus 15 remote tests including authentication
isolation, stale-result cancellation, critical favourite completion and both
cached/asynchronous selection restoration. The full integration checker includes
these tests. Deployment must validate per-host cohorts, marker and hashes, and
back up/replace the helper alongside browser/default/shared_favorites and the
integrity manifest. It must not change remote connection or AV settings.

The Media-host r2 bundle and read-only saved-setup plans are documented outside
the public fork in `ops/kodi-device-bundle-20260922/`. Actual remote-user API
checks succeeded for movie/series categories/pages and live groups. No powered-
off AM9 was installed/tested, no player-startup improvement is measured yet, and
no remote P7 route or GitHub push is implied.

## Historical September 13 deployment

Deployed Venom browser 1.3.1 on the Ugoos, with maintained Jellyfin-for-Kodi 2.1.0 patches. No firmware, audio, HDR, scaling, passthrough or provider stream-quality changes. IPTV access remains Habibi-only. Shared Jellyfin favourites remain server-authoritative.

## Causes confirmed

- Jellyfin's previous global scan failed during post-scan inherited-value updates with SQLite disk-full errors. The current huge IPTV import/scan was generating hundreds of library-change events every ~15 seconds. The percentage was not a fixed job: newly arriving events changed its denominator.
- Kodi's existing IPTV exclusion was applied after complete metadata downloads and after starting/opening database writers. This caused pointless Movie/Series/Season/Episode writer churn despite the two Venom libraries not being selected for Kodi local sync.
- KodiSyncQueue's catch-up endpoint still returned HTTP 500 with `No space left on device` for its LiteDB log, although the container had 28 GiB available and only 21% inode use. Restarting Jellyfin recovered the endpoint without deleting either LiteDB file. The main library scan was cancelled for the restart and explicitly started again afterward; it remains background work, not claimed complete here.
- Browser rendering performed synchronous shared-favourite network requests. Searches/revisits reconstructed catalogue entries repeatedly. A fresh All movies load measured 6.517 seconds for 27,935 titles.

## Changes

1. Downloader probes `Path` first when explicit exclusions exist. Only eligible IDs get complete metadata and reach local writer queues. Missing paths and explicitly selected libraries retain normal processing. Progress counts accepted local work, not excluded IPTV events. Both updated-item and user-data queues use the filter.
2. Completion checks include input/output queues, not just thread lists. Successfully handled excluded-only batches advance the catch-up watermark without opening progress UI or refreshing the home screen. Failed download batches do not advance that watermark.
3. Venom input callbacks enqueue slow actions; the script processes them separately. Paging/rendering never calls the network. Shared stars refresh via a separate client/thread, with a 30-second polling interval, existing timeout/cooldown, and generation protection against stale pre-mutation snapshots. Favourite mutations still verify the server response. Automatic legacy-favourite migration no longer runs on browser launch; retained local/pending entries remain accessible in their dedicated category.
4. Five-minute in-memory category/series caching is bounded to four categories and approximately 35,000 entries (a single oversized source remains displayable). Only 80 cards are instantiated per page. Movies/series use a larger 5-column, 2-row poster grid; channels retain wide logo cards. Back restores the previous series/list selection and breadcrumb. Shared series episode lists now paginate beyond the previous silent 500-episode cutoff, with an explicit 10,000-episode safety limit.
5. Exporter writes durable dirty generations only when catalogue content changes. Refresh helper acknowledges a generation only after successful queue submission, keeps dirty work if already Active/Queued, and avoids requeueing unchanged exports. A lock prevents overlapping helper instances. Existing 8-GiB space protection remains. The six-hour global scan schedule is unchanged; this change removes redundant exporter-triggered scans, not all server scans.

## Verification

- Before fix: database writers started repeatedly every ~1–3 seconds during excluded-library scans.
- After fix: live event probes reported eligible=0 for excluded IPTV batches, without spawning those writers. Kodi's `jellyfin_sync` flag cleared and `Library.IsScanningVideo` returned false while Jellyfin continued indexing.
- After final restart: catch-up retrieval completed without HTTP 500. A real normal-library item had received=1 / eligible=1; the Movie user-data writer started and completed normally.
- Movie page navigation measured 0.061 and 0.190 seconds on-device. These are action timings, not a claim that every poster downloads within that time. Category-list load measured 0.006 seconds from cache. First full movie listing remained 6.517 seconds.
- Screenshot verified larger poster grid. Existing native playback routes were unchanged; this pass did not rebenchmark stream decoding or every provider title.
- Tests: 8 browser, 7 shared favourites, 11 catalogue, 3 sync-download, 5 exporter, 3 refresh-generation checks, plus the full clean-upstream Arctic/Jellyfin/KodiSeerr integration suite. Read-only live integrity check returned no drift after approved hashes were updated.
- Final restart sample: 1,519 event IDs probed, only one eligible for local syncing; normal user-data processing completed. Zero ERROR lines in that Kodi log snapshot; sync flag empty and local video scanning false. Remaining background event probes are expected while the server scan progresses (43.8% at one later check).

## Remaining limits / follow-up

- Server catalogue indexing still needs to finish; do not repeatedly restart or manually refresh all libraries. Dirty generations allow a necessary follow-up scan when content changes during an existing scan.
- Some provider/gateway posters are incorrect or absent (visible examples among numeric movie titles). Browser size/layout is fixed, but no speculative bulk artwork reassignment was applied. Provider metadata mapping needs separate source verification before changing tens of thousands of items.
- KodiSyncQueue returned an empty catch-up set immediately after recovery; events it failed to persist during the disk-full period cannot be assumed recovered. The resumed server scan and live updates continue to republish changes. No Kodi database reset was performed.
- Cold catalogue/network requests can still take seconds. Cached paging is fast, not an offline guarantee.
- The changes are stored in the local GitHub fork checkout; not committed or pushed by this pass.

## Recovery / maintenance

Ugoos pre-change backup: `/storage/upgrade-staging/venom-performance-20260913/` (browser add-on, library.py, downloader.py). Server scripts backed up under `/data/config/iptv-venom/backups/performance-20260913/`. Consistent stopped KodiSyncQueue pair: `/data/config/jellyfin/backups/kodisync-recovery-20260913/stopped/`. Do not restore that event-history pair over a running Jellyfin process.

Maintained sources: `ops/plugin.video.venom.tv`, `ops/venom-jellyfin-library.py`, `ops/venom-jellyfin-downloader.py`, exporter/helper scripts. Public fork mirrors browser, server helpers and tests under `integration/`; apply `jellyfin-sync-performance.patch` after the existing Jellyfin patches. The verified-build manifest now includes downloader.py. Do not blindly reapply patches after upstream upgrades; run `integration/check.py` first. Production services remain on the media server/Ugoos, not this development machine.

Research references: [Kodi conditional item layouts](https://kodi.wiki/view/Container_Item_Layout), [Jellyfin-for-Kodi source](https://github.com/jellyfin/jellyfin-kodi), [KodiSyncQueue source](https://github.com/jellyfin/jellyfin-plugin-kodisyncqueue), [LiteDB disk-error report](https://github.com/litedb-org/LiteDB/issues/2614). Local API/log evidence, not the upstream report alone, confirmed this incident's recovery.
