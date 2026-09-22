# Venom category/grid layout — 2026-09-13

## Phased plan and status

1. Audit old navigation, favourites, performance and client capabilities — done.
2. Deploy category-first Kodi browser and grid navigation — done.
3. Test remote favourites, native playback, series hierarchy and sync isolation — done.
4. Apply supported Jellyfin preferences; audit mobile limitations — partial.
   Phone-native settings need on-device verification. Jellyfin category indexes
   need rechecking after queued scans finish; not declared fully fixed.
5. Added on user request: shared account favourites — deployed in Venom 1.3.0.
   See the final-phase details below, superseding initial 1.2 local-only favourites.

## Kodi changes

Venom TV 1.2.0 adds browser.py and resources/skins/Default/1080i/VenomBrowser.xml.
Arctic Custom_1107_LiveTV.xml launches it only when the section is named Venom TV.
The original generic PVR layout remains for non-Venom use. Venom no longer loads
the old hidden PVR widgets or opens the empty guide as its main entry.

- Four tabs: Live TV / Movies / Series / Favourites.
- Provider categories at left, four-column grid at right, 80 items per page.
- Category selection requires OK: focus/scrolling never fetches every group.
- Search in the chosen category (choose All for global search); previous/next
  page, A–Z/recent ordering for movies and series.
- Menu/context action or hold OK opens favourites. Initial 1.2 local-only media
  favourites were replaced by Jellyfin-authoritative favourites in phase 5 below.
- Series open seasons and then episodes within the grid. Back walks the hierarchy,
  then returns focus to categories, then closes to Home.
- Live playback uses Kodi PVR Player.Open(channelid), retaining native audio/video
  processing. Movie/episode playback retains the existing gateway plugin resolver.
- Arabic letters retained; unsupported decorative emoji removed from display
  labels only. Original provider identity/data is not rewritten.
- Legacy plugin directories default to Arctic poster-wall view 512; widgets are
  excluded from that view-mode action.
- Cache reuse, only 80 GUI items at once, background artwork loading, and no
  EPG requests for browsing. Missing/incorrect provider art is not invented.

## Background sync performance repair

Found repeated Kodi errors in TVShows.season: an IPTV season update attempted to
look up a parent show that was deliberately not synced. The earlier exclusion in
find_library did not cover this direct Season update route.

Added excluded_stream_item at the UpdateWorker dispatch boundary, using the
existing ExcludedLibraryPaths policy. It skips only those explicit unsynced paths;
explicit Whitelist selection overrides exclusion. Normal paths, missing paths and
similarly named sibling directories are not filtered. Queue task_done is retained.

Private source: ops/venom-jellyfin-library.py. Public reproducible patch:
integration/patches/jellyfin-iptv-update-filter.patch, applied after jellyfin-kodi.patch.
Kodi was restarted with no active player to load the persistent Python service.
No further parent-season errors appeared in the inspected post-restart log window.

## Verification and timings

- Full integration/check.py passed against pinned clean upstream sources.
- Eleven catalogue tests plus five new grid/exclusion/XML tests passed.
- Real remote ContextMenu opened Add to Venom favourites; channel was added,
  saved, then removed with the same menu. Test favourite was not left behind.
- Actual Live TV playback reached fullscreen using the internal player, H264
  720x576 with AAC audio on the sampled source; test stream explicitly stopped.
  This verifies routing, not a promise of HD quality for that SD provider source.
- Visual checks: category sidebar, channel grid, movie grid, series, season,
  episode grids. Private screenshots are in ops/venom-browser-*.png and Ugoos
  /storage/upgrade-staging/venom-layout-20260913/. Do not publish private screenshots.
- Kodi category list ~0.02s; all 11,249 channels ~0.89–0.98s; all-movie first page
  ~1.57s; series first page ~0.81s; sampled seasons ~0.13s and episodes ~0.18s.
  These are handler timings, not cold-poster download or phone-radio benchmarks.
- Jellyfin server API first 80 movie items ~0.74s, series ~0.54s during indexing.

## Jellyfin and Moonfin — changes and remaining limits

Habibi-only supported DisplayPreferences keys set to Poster:
`<VenomMoviesId>-movies-view` and `<VenomSeriesId>-series-_view`.
Both IPTV libraries added to Habibi LatestItemsExcludes to avoid giant catalogue
imports filling generic Home latest rows. Direct libraries, favourites, resume,
next-up, permissions and other users unchanged. Backup before change is under
/data/config/iptv-venom/backups/habibi-grid-before-*.json.

Do not claim sidebar parity on mobile. Moonfin native layout is client-controlled;
there is no active Moonbase/Moonfin server plugin to sync its settings. A screenshot
of the handset Live TV and view options was requested; no phone settings changed.
Jellyfin's live landing-tab and page-size preferences are local client settings
in v12; changing a server CustomPrefs field does not force them on every device.
For now choose Live TV > Channels and set library page size around 100 locally.

Jellyfin's live channels expose empty Genres/Tags in the audited API. Movie item
metadata does contain provider categories in Genres/Tags, but the movie Genres
and Filters2 indexes returned empty; series genres returned only five. At that
check normal Shows was Active and both Venom libraries Queued. Recheck indexes
after scans finish before diagnosing a persistent Jellyfin12 indexing regression.
No duplicate 11k-channel library, mass per-channel metadata rewrite, global CSS
override or extra client plugin was installed to mask this gap.

Storage remained around 30 GiB free; previous WAL and low-space safeguards retained.

## Phase 5: shared favourites (Venom 1.3.0)

Added shared_favorites.py on Kodi only; no new server daemon, admin key, custom
database write or phone plugin. Uses the currently selected Jellyfin-for-Kodi
Servers[0] user token. Users/{user}/FavoriteItems/{id} POST/DELETE is followed by
item read-back before reporting success. The shared list queries the same user's
IsFavorite items, including Movie, Series, Episode and TvChannel.

- Menu add/remove in the Venom grid now explicitly says Jellyfin favourites
  (all devices). The favourite star is derived from the server list.
- Favourites tab shows All shared / Channels / Movies / Series, including ordinary
  Jellyfin-library titles. Refresh favourites fetches changes made elsewhere.
  List is refreshed on entry; grid badge cache is 15 seconds. This is shared state,
  not a promise that every client's already-open screen repaints instantly.
- Native Venom movies/series/episodes match exact managed catalogue paths, not
  just names. Native channels match BOTH number and name. Ambiguous or unindexed
  items fail closed; no false "saved" confirmation and no wrong-title favourite.
- Shared channel playback maps back to native Kodi PVR. Shared normal-library
  movie/episode playback delegates to Jellyfin-for-Kodi; series browse server episodes.
- Existing local media favourites are migrated in small bounded batches, removing
  the local entry only after server confirmation. Failures retain the entry, log
  a pending-match message and defer retries. Local category bookmarks are not
  Jellyfin media; they remain accessible in Local bookmarks / pending sync.
- Legacy plugin context actions also use Jellyfin for media favourites. Category
  bookmarks remain explicitly labelled local. No local-only fallback pretends to
  be synchronized when the server is unavailable.
- Network failures use a short retry cooldown to avoid repeated eight-second
  waits on each grid action. Browsing/playback do not require favourite writes.

Verification: seven shared-favourite unit cases plus a server-star UI regression
passed. Real API tests on Ugoos covered channel, Venom movie, Venom series and an
ordinary-library movie: add from one client, read from a fresh client, remove from
the second client and observe that removal in a forced Kodi refresh. Original
states were restored in finally for every test item. This validates shared server
state; the physical Moonfin/Jellyfin handset UI still needs refresh/on-device check.

Final on-TV verification after the user-authorized Kodi restart: All shared
favourites rendered the same seven server items, including one live channel and
ordinary-library movies/shows, with server-backed stars. Menu correctly displayed
"Remove from Jellyfin favourites (all devices)" for the selected shared channel;
the menu was dismissed without removing the user's favourite. Private evidence:
ops/venom-shared-favourites.png and ops/venom-shared-menu.png. Deployed integrity
check returned no mismatches. Six browser tests, seven shared-favourite tests and
eleven legacy catalogue tests passed with the full pinned-upstream integration suite.
Generic Kodi shortcut bookmarks are still local; use the explicitly labelled
Jellyfin favourites action for cross-device media favourites.

Source and tests are included in the public-safe fork working tree; no push made.
The primary API implementation is Jellyfin's UserLibraryController in v12.0.

## Recovery / reproducibility (files)

Before-files are under /storage/upgrade-staging/venom-layout-20260913/ on Ugoos:
original Venom addon, Custom_1107_LiveTV.xml, jellyfin-library.py. Restore matched
files with Kodi stopped if needed; do not flash firmware. Existing user favourites
must be preserved independently of addon rollback.

Public-safe source/tests mirrored into ops/arctic-fuse-fork/integration, with
reviewed integrity hashes. No GitHub commit/push was performed in this phase.

## Primary references

- [Kodi built-in view controls](https://kodi.wiki/view/List_of_Built_In_Functions)
- [Kodi JSON-RPC/PVR API](https://kodi.wiki/view/JSON-RPC_API/v13)
- [Moonfin personalization and client settings](https://github.com/Moonfin-Client/Moonfin-Core/wiki/User-Guide)
- [Jellyfin12 movie view preference implementation](https://github.com/jellyfin/jellyfin-web/blob/v12.0/src/apps/legacy/controllers/movies/movies.js)
- [Jellyfin12 series view preference implementation](https://github.com/jellyfin/jellyfin-web/blob/v12.0/src/apps/legacy/controllers/shows/tvshows.js)
- [Jellyfin12 local landing-tab implementation](https://github.com/jellyfin/jellyfin-web/blob/v12.0/src/apps/modern/features/libraries/utils/path.ts)
