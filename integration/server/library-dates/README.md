# Import-date repair runbook

Status: source and local tests only. The historical dates have **not** been
applied by this repository stage. `repair.py` works with the reviewed
`/Habibi/LibraryImportDate/{itemId}` endpoint, now intended to be supplied by
the version-matched `Habibi.LibraryExperience` plugin. Do not use an older
core-API implementation that invokes `UpdateToRepositoryAsync` for this
bulk operation: Jellyfin's `MetadataEdit` path can run metadata savers and
rewrite NFO files. The plugin must persist only `DateCreated` with the same
expected-path and expected-date guards, and its own tests/build must pass.

`export-arr.py` reads Radarr `MovieFiles.DateAdded` and Sonarr
`EpisodeFiles.DateAdded` from private read-only SQLite connections. It emits
absolute path, resolved path, source and UTC date records. `repair.py` matches
only exact full paths or an existing media-file path's resolved symlink
target. It excludes `.strm`, Venom-named libraries and non-movie/show media.
The candidate plan stores each Jellyfin item ID, exact path, old UTC date and
verified Arr date; it never writes directly to the Jellyfin DB. The live
rehearsal reported 12,374 owned items, 4,103 exact matches and 4,050 proposed
changes, but these counts do not substitute for a new plan after any library
scan or source change.

Episode parent identities deliberately are not trusted from the offline import
evidence. Immediately before changing an Episode, the apply reads its current
authenticated Jellyfin item, requires an exact 32-hex `SeriesId`, and durably
stores that relationship in the private journal. It records that Series as
pending before the date POST. After the item batch, it calls the plugin's
`RefreshLatestDates` route in sorted batches of at most 500 IDs. The route
recomputes each submitted `Series.DateLastMediaAdded` from current local
episodes; Movies never enqueue a parent refresh.

## Private apply, resume and rollback

Run the exporter and planner on the media host with private output paths. The
Jellyfin key is read from a private file and sent using Jellyfin 12's
`Authorization: MediaBrowser Token="…"` header. Review the resulting plan
and take a private database/configuration backup before apply.

```sh
python3 export-arr.py --config-root /private/arr-config > /private/imports.json
python3 repair.py --url http://jellyfin-internal:8096 --key-file /private/jellyfin-key \
  --imports /private/imports.json --plan /private/import-date-plan.json
python3 repair.py --url http://jellyfin-internal:8096 --key-file /private/jellyfin-key \
  --plan /private/import-date-plan.json --apply --backup /private/import-date-journal.json
```

`--backup` is an exclusive, mode-0600 durable journal containing the full
original plan and per-item progress. It is created before the first POST.
The script verifies each item's live type, exact path and previous date with
a fresh Jellyfin item query, records `attempting` on disk, POSTs only one
date, and verifies the desired date with another query before recording
`applied`. If the desired date was already present before the POST, it records
`already_desired` and does not count that as its own change. Any unknown
path/date stops the run. The apply preflight also rejects old dates before
2000, because the repair endpoint would refuse to reverse them.

For `--set-import-policy`, the tool backs up the full current metadata
configuration and performs a second equality GET immediately before POSTing
the copy with only `UseFileCreationTimeForDateAdded=false`. Drift stops without
a write. Jellyfin exposes no conditional-write token for this configuration,
so an administrator must still avoid concurrent metadata-settings edits in the
small interval between that second GET and POST.

Each successful derived-date response must report exactly the submitted count
before that batch is removed from `pending_series_refresh`. If the response is
lost after the server commits, resume safely repeats the idempotent
recomputation without reposting the Episode date. Before sending a pending
parent ID, resume verifies it is still the exact parent of an Episode recorded
in this plan, so edited journal data cannot refresh an unrelated Series.

If the process or connection fails, keep the journal and use an explicit
resume. A POST that committed before its response was lost is recognized by
the fresh desired-date read, so it is not sent again:

```sh
python3 repair.py --url http://jellyfin-internal:8096 --key-file /private/jellyfin-key \
  --plan /private/import-date-plan.json --apply --resume --backup /private/import-date-journal.json
```

Resume first completes any pending Series recomputation left by an interrupted
run, then continues item changes. Journals created by the earlier CLI schema
remain supported: rows in `attempting`, `applied`, `rolling_back`, or
`rolled_back` state have their current Episode parent identity derived once and
are conservatively queued for recomputation. A failed run that is not resumed
can therefore leave derived Series ordering stale even though its durable
journal is sufficient to repair it; do not discard the journal.

To reverse only the changes recorded by this journal, while paths and dates
still match, use:

```sh
python3 repair.py --url http://jellyfin-internal:8096 --key-file /private/jellyfin-key \
  --rollback --backup /private/import-date-journal.json
```

Rollback runs in reverse order and journals each step. Rows marked
`already_desired` are deliberately left alone. If a file, symlink target,
item date or API behavior drifted, stop and investigate; restoring the
private pre-apply database backup may be needed. A path/date pair does not
prove that the bytes of a replaced file are unchanged. Keep import export,
plan, journal and database backup private; they contain paths and inventory.
One apply/rollback process per journal is enforced with a private lock file.
Rollback also records affected Episode parents before reversing their dates
and recomputes those Series after the reverse batch; a lost refresh response is
handled by repeating rollback with the same journal.

## Verification and rebuild

Run `python3 -m unittest discover -s integration/server/library-dates -p
'test_*.py' -v` and `python3 -m py_compile
integration/server/library-dates/{export-arr,repair}.py`. Build and test
the exact Jellyfin 12.1 companion plugin source, then stage against an
idle, backed-up server. Check a bounded sample of persisted `DateCreated`
values and Recently Added order before any full apply. A source-only test or
HTTP 204 is not proof of database readback or app ordering. The maintained
plugin, CLI, tests, build/install and rollback procedure belong together in
the fork for future rebuilds; no production deployment is claimed here.
