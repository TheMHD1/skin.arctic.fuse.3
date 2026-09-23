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
policy, Series derived-date update and plugin lifecycle metadata. Eleven tests
passed on the deployed build.

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
