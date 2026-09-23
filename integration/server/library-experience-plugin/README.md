# Library Experience Maintenance plugin

This plugin provides two narrow, administrator-only repair operations for
Jellyfin 12.1:

- atomically change only `BaseItems.DateCreated` for an exact local Movie or
  Episode ID, path and prior UTC timestamp;
- after an Episode batch, recompute `DateLastMediaAdded` for at most 500 exact
  Series IDs from their current, dated, non-virtual local Episode rows.

It does not run a metadata refresh, call metadata savers, write NFO files,
change watch history, scan a library, or accept arbitrary paths or SQL. The
in-memory item/Series field is changed only after the database transaction
commits. Season does not support `DateLastMediaAdded` in Jellyfin 12.1, so the
derived refresh deliberately updates Series only.

## User-scoped local ratings bridge (1.1.0)

`GET /Habibi/LibraryExperience/Ratings?ids=<comma-delimited-guid-list>` is a
separate authenticated read-only bridge for Home, search and Discover. It accepts
one to 100 distinct Jellyfin item GUIDs; malformed, empty, or oversized requests
return 400. The endpoint takes the concrete user only from Jellyfin's authenticated
`Jellyfin-UserId` claim. It deliberately has no `userId` query parameter and a
userless API key returns 401 rather than becoming an administrator/global query.

Submitted IDs are first filtered with Jellyfin's stock user access filter (the
same `IItemQueryHelpers.ApplyAccessFiltering` path used by the pinned search
manager), then loaded as non-virtual Movies/Series. This is intentional: in 12.1
an `ItemIds` `GetItemList` query alone bypasses automatic library-scope filtering.
Library sharing, visibility and parental restrictions therefore decide the result.
Inaccessible, nonexistent and non-Movie/Series IDs are omitted. The route returns
`Cache-Control: private, no-store` and `Vary: Authorization`; it never exposes
paths, users, tokens, library listings or a global ratings index.

The compact response is shaped as follows (properties use normal Jellyfin JSON
camel case):

```json
{
  "items": {
    "0123456789abcdef0123456789abcdef": {
      "imdb": { "rating": 8.2, "votes": 1234 },
      "community": 7.7
    }
  },
  "source": "IMDb non-commercial datasets",
  "fetchedAt": "2026-09-23T00:00:00+00:00"
}
```

`imdb` is omitted when no valid local IMDb rating is available. `community` is
only the accessible item's Jellyfin `CommunityRating`; it is generic item metadata,
not a fabricated TMDb value. `fetchedAt` is null when the local IMDb index is not
usable. Clients must fail open and must not infer a provider that is absent.

The plugin makes no external request. A separately maintained local updater writes
`PluginConfigurationsPath/library-experience/imdb-library-ratings.json` atomically.
The file is limited to 2 MiB, cached by modification time under a lock (with
freshness rechecked on every cached read), and must have this validated schema:
`schema` 1, UTC `fetched_at` no more than 14 days old, exact
`https://datasets.imdbws.com/title.ratings.tsv.gz` `source_url`, and a `ratings`
object mapping bounded IMDb `tt...` IDs to finite 0–10 `rating` and positive
integer `votes`.
Any malformed, stale, unauthorized, missing, or oversized file supplies no IMDb
ratings rather than triggering a per-card lookup.

## Source pin, build and tests

Build against the exact Jellyfin source revision
`ee91c75e777da41a9c4f4855e70adc604fbf2ef8` (12.1). `JellyfinSourceRoot` may
point to a clean checkout or the reviewed patch stack reconstructed by
`../jellyfin-custom/prepare.py`; CI uses that fresh reconstruction, not an
arbitrary dirty working tree. The source guard checks the Git revision, not
every uncommitted source byte, so use the preparer for reproducible builds.
The endpoint also checks the installed
`MediaBrowser.Controller` assembly is exactly `12.1.0.0` and otherwise returns
HTTP 503 without writing anything. Rebuild and retest for every Jellyfin
minor-version change.

```sh
dotnet build integration/server/library-experience-plugin/Jellyfin.Plugin.LibraryExperience.csproj \
  -c Release -p:JellyfinSourceRoot=/path/to/jellyfin-12.1
dotnet run --project integration/server/library-experience-plugin/tests/Jellyfin.Plugin.LibraryExperience.Tests.csproj \
  -c Release -p:JellyfinSourceRoot=/path/to/jellyfin-12.1 -- -noLogo -noColor
```

The executable test suite uses a real in-memory SQLite database. It verifies
the one-column update, unchanged unrelated fields, exact path/date concurrency
guards including database type/virtual drift, local-file rejection, elevation
policy, Series derived-date update and plugin lifecycle metadata. The deployed
1.0.0 build passed eleven tests; the 1.1.0 suite adds ratings parsing, cached
freshness, current-user context, permission-query and rejection coverage (17 tests
total).

Deploy only `Jellyfin.Plugin.LibraryExperience.dll` and `meta.json` from
`bin/Release/net10.0/` to a dedicated plugin directory. Do not copy its
source-build Jellyfin dependency DLLs over the server. Restart Jellyfin only
during an approved window (or explicit authorized interruption), then verify the plugin and both routes are
registered before submitting a repair batch.

The deployed September 23 plugin is Active and passed a live path-conflict
HTTP 409 test plus one journaled movie-date update/readback. An initial build
failed plugin lifecycle initialization; the maintained generic `BasePlugin`
constructor and lifecycle regression test address that. If Jellyfin disabled a
failed earlier build, replacing the DLL alone does not enable it: use the
supported `/Plugins/{pluginId}/{version}/Enable` API and restart, then check
`/Plugins` reports Active. Never assume a DLL present on disk means routes load.

## Safe repair sequence

1. Take a consistent database/config backup and retain the prior image/plugin
   directory. Export each candidate's item ID, exact path and current UTC
   `DateCreated`, plus the affected Series IDs.
2. POST one guarded item update at a time to
   `/Habibi/LibraryImportDate/{itemId}` with `ExpectedPath`,
   `ExpectedDateCreated` and `DateCreated`. A stale cache/database identity
   returns HTTP 409 and changes nothing.
3. After the item batch succeeds, POST the distinct affected IDs to
   `/Habibi/LibraryImportDate/RefreshLatestDates` as `SeriesIds` (1–500 per
   request). The transaction rolls back the entire request on a concurrent
   parent-date change.
4. Read the changed items and Series through the normal API and verify Latest
   ordering on at least two users. Retain the before/after audit privately.

Authorization is Jellyfin's `RequiresElevation` policy; API keys and real paths
must never be committed here. Rate/batch orchestration is provided by the
source-preserved `../library-dates/repair.py`; its plans and journals are private.

Rollback the plugin by restoring/removing its dedicated directory and
restarting Jellyfin. Plugin rollback does not revert committed dates: submit a
new guarded request using the recorded before-values, or restore the database
only if a broad repair was wrong. A database restore also loses newer viewing
and metadata changes, so prefer exact compensating updates.
