# Venom categories and show favourites — 2026-09-14

## Deployed

- Provider category metadata is exposed through standard Jellyfin `/Genres`, scoped to the existing private libraries. At verification: **78 populated movie categories and 36 populated series categories**. Source lists contain 78 movie/51 series groups, 128 distinct names (a shared name overlaps). Unimported/empty categories do not appear in scoped browsing.
- Examples include Arabic, Action, Drama, Ramadan 2022–2026, Netflix, anime and country-specific groups. Original provider labels are retained.
- Added a light `Browse provider categories` dialog to Habibi's Venom Movies/Series pages in Jellyfin Web: small category-name/count grid, then one paginated native title list. Does not preload previews for every group. Native stock Genres view remains available as a fallback.
- Added `Favourite shows` / `Favourite movies` shortcuts using native `/list?type=Series|Movie&IsFavorite=true&tag=Venom+TV`. Existing server favourite flags remain authoritative; no device-local parallel list.
- Exporter now retains all `category_ids` plus primary `category_id`, deduplicated. Existing series metadata can update without fetching episode details again during its weekly cooldown. Paths and playback URLs remain unchanged.
- Reconciliation service on media CT102: `venom-jellyfin-category-index.service` and `.timer`, every 30 minutes. Metadata only; no streams started. Repeat verified with **zero** extra genre refreshes.

## Root causes and repair

Individual Movie/Series DTOs had `Genres: ["Venom: …"]`, but category entities had not been created by Jellyfin's end-of-scan GenresValidator. Library import remains in progress; do not confuse this fix with completion of all series imports.

`GET /Genres/{name}` is unsuitable for arbitrary provider names: Jellyfin 12 treats `-` as the legacy slug character. Many legitimate names returned empty DTOs. Added an administrator-only bounded endpoint to the existing pinned Live TV Categories plugin:

`POST /VenomCategories/Maintenance/Register` with an array of at most 1000 `Venom: ` names, max 512 chars each, no control characters. It calls the standard library manager's `GetGenre`, without SQL modifications.

New genre entities also need their normal metadata lifecycle to populate `PresentationUniqueKey`; otherwise Jellyfin 12 collapses new genres into one group. The helper queues a one-time `MetadataRefreshMode=None&ImageRefreshMode=None` per genre, recording acknowledgements in `category-refresh-requested.json`. No external scrapers, artwork replacement or movie scans requested. A rare interrupted queued refresh can be repaired by the normal full scan; state records queued, not completed, work.

The plugin DLL is upstream **0.3.0.0 + local maintenance controller**, not an upstream release. Pin with source patch. One Jellyfin restart loaded it; library scan was resumed. No permissions were broadened, library IDs changed or media files moved.

## Moonfin: what works and what still needs the app

Confirmed current session: Moonfin for Android **2.5.1**. Inspected exact 2.5.1 source:

- Its library genre screen calls standard `/Genres` with `parentId`: the repaired category data is available to that screen. On phone open Venom Movies/Series, choose its Genres browsing option. Handset rendering has **not** been remotely verified.
- Favourites already supports Series and uses server user-data. Its home-style favourite rows omit empty types, so Shows appears after a show is favourited. The new Jellyfin Web shortcut is not a native Moonfin UI modification.
- Its Live TV guide uses fixed programme filters (Sports, Kids etc.), not provider M3U groups. Merely adding server genre metadata cannot replace that native screen. Existing `/LiveTvCategories` API already has 304 groups and paginated channels, ready for a native integration.
- A custom Moonfin APK is required for the requested provider-group channel screen unless upstream adds support. Asked user whether they accept installing a custom APK; no APK built/installed this turn. Do not claim native Live TV categories are fixed.

Sources: [Moonfin 2.5.1 genre screen](https://github.com/Moonfin-Client/Moonfin-Core/blob/2.5.1/lib/ui/screens/browse/library_genres_screen.dart), [guide filters](https://github.com/Moonfin-Client/Moonfin-Core/blob/2.5.1/lib/data/viewmodels/live_tv_guide_view_model.dart), [favourites types](https://github.com/Moonfin-Client/Moonfin-Core/blob/2.5.1/lib/data/viewmodels/favorites_view_model.dart).

## Verification

- .NET tests: 30 passed, including bounded-input and administrator policy checks; build zero warnings/errors. Initial test fixture lacked Controller runtime assembly; added test-only package references and reran successfully.
- Exporter tests: 6 passed. Navigation policy/route tests passed.
- API category summaries: Movies 0.201s, Series 0.188s in warm smoke check. Sample category title pages 0.059s / 0.048s; timings are samples, not guarantees.
- Temporarily favourited a series, verified the exact filtered endpoint returns it, restored previous flag in `finally`, verified restoration.
- Regular Habibi web token was denied maintenance POST (401). Administrator registration succeeded.
- Browser verified category dialog, category links and favourites route. Initial category link used unsupported `id`; fixed to legacy route's `genreId`, added regression assertion.
- Reconciliation verified healthy; second run queued no extra work. Server health returned Healthy after restart.

## Files and rollback

Local sources under `ops/`: `venom-jellyfin-category-index.py`, service/timer, exporter and tests, `venom-jellyfin-navigation.js`, `test-venom-jellyfin-navigation.cjs`, `venom-category-smoke.py`.

Custom controller: `ops/live-tv-categories-review/Jellyfin.Plugin.LiveTvCategories/Controllers/VenomCategoryMaintenanceController.cs`.

Deployment: `/data/config/iptv-venom/`, and `/data/config/jellyfin/data/plugins/Live TV Categories_0.3.0.0/`.

Backups in `/data/config/iptv-venom/backups/`: `LiveTvCategories-0.3.0.0-upstream.dll`, `venom-jellyfin-export-before-multi-category.py`, original web shell `live-categories-index-before-navigation.html`.

To revert: disable category timer first, restore upstream DLL and restart Jellyfin; restore exporter backup if desired. Restore original web shell to remove all navigation customization. Do not delete genre entities: they are normal metadata and required by clients.

Public fork integration mirror updated locally. **Not committed or pushed this turn.** Preserve unrelated pending changes when publishing. No credentials in mirrored files.
