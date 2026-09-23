# Library-only Home, source-aware ratings and search priority

## Scope and status

The requested Top Rated Movies and Top Rated Shows are **owned Jellyfin library
rows**, not Discover recommendations or Venom provider content. They and the
user-specific Favorites row are deployed in the version-matched Jellyfin Web
12.1 bundle. The official mobile wrapper receives the server-hosted Web changes;
a native client with its own Home renderer does not automatically gain these
rows. No custom APK or new native-app fork was built.

Search order in the Web integration is owned Movies / Shows, Discover on Seerr,
then secondary Venom Movies — Not HD / Venom Shows — Not HD. Other stock search
types remain functional; Venom is last. This needs both the Web row marker/order
patch and the Enhanced placement patch. Merely reordering the Web rows leaves
Enhanced treating provider Movie/Series cards as the primary catalogue.

## Sources and rebuild order

1. Jellyfin Web `fae41f33eb7cd636a9ef68984adb82bb247a6e1b` (12.1), retaining
   the separately version-matched Live TV Categories overlay. Apply
   `web-navigation/search-jellyfin-web-12.1.patch`, then
   `web-home-library/jellyfin-web-12.1-owned-home.patch`. Build production Web
   and publish through `web-navigation/install-bundle.py`, retaining private
   backups and existing local navigation script tags. Do not replace a newer
   server's Web with this version-pinned bundle.
2. Enhanced `daf5b10c09d017941e29a79a0a45d0ab31c34abc` (12.7): apply
   `patches/jellyfin-enhanced-12.7-tabs.patch` and
   `patches/jellyfin-enhanced-12.7-search-priority.patch`; build the net10 plugin.
   Deploy only `Jellyfin.Plugin.JellyfinEnhanced.dll`, preserving its private
   settings. Do not copy build dependency DLLs into the server.
3. Build `server/library-experience-plugin/` 1.1.0 against pinned Jellyfin 12.1
   (`ee91c75e777da41a9c4f4855e70adc604fbf2ef8`). Its authenticated batch endpoint
   reads a local filtered ratings index. Retain the previous plugin outside the
   active plugins tree; deploy the DLL and matching meta.json in the new version
   directory, restart during an authorized interruption, then verify Active and
   an actual authenticated GET. A DLL existing on disk is not activation proof.
4. Install `server/imdb-library-ratings/` on the media host, with its private
   key-file path and output directory, then enable the six-hour systemd timer.
   Follow that component's README for private ownership, bounds and rollback.
5. Kodi's version-guarded search/rating overlay is maintained separately in
   `release/search-priority/`. Do not install the legacy repository-root skin
   ZIP on a current Arctic 3.3.1 device. See that directory's final acceptance
   record for local deployment versus staged remote-house work.

No Jellyfin server core change is needed for these new Home/rating features.
Existing Continue Watching/Next Up core fixes remain a separate maintained
patch stack. No new HomeSectionType enum values or user Home preferences are
written. The CoreELEC firmware hold remains in force.

## Rating semantics and performance

The official personal/non-commercial IMDb dataset is refreshed in the background,
filtered to existing owned-library IMDb IDs, and atomically published as small
JSON. No title guessing, IMDb page scraping, full IMDb database or per-poster
external lookup is used. The first live run matched **201 of 202 distinct owned
IMDb IDs**, took about four seconds wall time, peaked at 24.6 MiB memory, and
retained about 8.3 MiB including its single compressed cache. Different library
items/versions can share an IMDb ID; these are distinct IDs, not an inventory count.

Top Rated uses actual IMDb score when available, otherwise the existing generic
library CommunityRating. Ties use source/vote count/name/ID for stable ordering.
The Web section note states this fallback. Existing Enhanced/Seerr poster badges
are retained; a generic library star is **not** newly claimed to be IMDb. The
separate Kodi badge path prefers named IMDb, named TMDb, then generic scores.
Missing/unrated titles are not assigned made-up scores. IMDb data is attributed
and subject to [IMDb's non-commercial dataset terms](https://www.imdb.com/interfaces/).

Normal Home loads independently. Favorites does not wait on IMDb; optional
Top Rated lookup has a bounded deadline, batches at most 100 IDs and caches by
server/user/scope. A metadata query is limited to owned permitted library parents,
exact Movie/Series types and bounded pagination. User/server identity is checked
again before rendering. Existing card actions, shared Jellyfin favorites and
item IDs are preserved. Empty Favorites stays hidden until that account has an
owned movie/show favorite; the ordinary Favorites view remains unchanged.

The bridge allows only a concrete authenticated user, not a query-string user
override. Pinned 12.1 has an important edge case: specifying ItemIds skips the
normal automatic top-parent scope. The plugin therefore applies the stock
SearchManager-style access filter first, then loads only permitted exact IDs.
Responses are private/no-store; there is no global index endpoint.

## Verification and rollback

- Clean pinned Web/Home/Enhanced patch reconstruction and five placement/
  idempotence cases: `python3 web-navigation/check-web-patches.py` from this folder.
- Web: five Home logic tests, three scoped-search tests, TypeScript, changed-file
  ESLint/Stylelint and production Webpack build passed. The build emits its
  existing bundle-size warnings; no zero-warning claim is made.
- Plugin: 17 executed tests including SQLite maintenance, lifecycle/DI, explicit
  JSON casing, local-index validation/freshness and access filtering.
- Updater: five fixture tests, successful initial live run and enabled timer.
- Live bridge: HTTP 200 with distinct IMDb/community values; anonymous 401;
  a restricted account requesting an inaccessible provider movie receives zero
  items. Cold three-item request observed at 168 ms from the maintenance browser;
  this is not a general device/network performance guarantee.
- Mobile-size Web: 24 Top Rated Movies and 24 Top Rated Shows, all IDs verified
  against permitted owned-library parents and descending effective scores. Each
  displayed row had 23 actual IMDb scores plus one library fallback at acceptance.
  Existing Continue Watching, Next Up and Recently Added rows remained visible.
  Mixed search confirmed owned rows, then Discover, then Venom. Fresh authorized
  Home/search had no console errors. Restricted Home worked; an existing plugin
  probe of administrator-only `/Plugins` returns 403, unrelated to rating access.
- Live Favorites canary: temporarily removed one existing favorite, observed it
  disappear from Home, restored the original favorite, and observed it return.
  The account's final favorite state is unchanged; refresh used the normal
  websocket/debounced mechanism rather than a page reload.

Rollback Web using its private changed-file backup; keep old hashed assets while
open clients may still reference them. Restore the prior Enhanced/maintenance
plugin directories and restart if reverting the server side. Disable the IMDb
timer to stop background updates; its absence causes score fallback, not broken
playback. No watch history, downloaded media, library metadata score or source
subtitle is rewritten by this rollout. Private backups, inventory, credentials,
browser state and device profiles must never be published with the source.
