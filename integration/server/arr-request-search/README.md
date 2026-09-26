# Approved TV season-search recovery

This is a bounded external worker using supported Seerr/Sonarr APIs. It adds no
Seerr core patch, webhook, listener or persistent daemon. Source and eighteen
isolated tests passed. The worker and timer were deployed September 26: the
read-only preflight and first applying run found four eligible request/season
pairs with no aired missing files, so issued no search. A future normal-request
recovery canary remains separate; installation alone does not prove a dropped
request has been recovered in production.
It does not replace native searches, import-rescue or download-client handling.

The worker considers only TV requests created within the last 24 hours that
remain approved, with approved requested seasons, and are at least three
minutes old. It selects the mapped Sonarr instance from Seerr's normal/4K
`media.serviceId` and series from `externalServiceId`, verifies exact TVDB
identity, and requires a known path under configured roots. Series and season
must remain monitored. Available, blocked/deleted, completed, declined, pending,
failed, unmapped and unmonitored requests are excluded.

At least one monitored, aired episode in the requested season must lack a
file. Future/unknown-airdate episodes do not qualify. If every such missing
episode's `lastSearchTime` is at or after `request.createdAt`, native searching
already covered the request and recovery does nothing. Sonarr's JSON omits
`lastSearchTime` when it is null; that represents no recorded search. Malformed
nonempty timestamps fail closed.

An active command targeting the same series or any of its episodes, an active
global MissingEpisodeSearch, or an existing download queue item for the season
also defers recovery. A same-series queue item without known season metadata
defers the series conservatively. Queue pages and Seerr snapshots must be
complete within their bounded pages before action. Five request/season pairs
are inspected per run; a durable cursor rotates fairly through recent pairs.

Immediately before submission, the worker refetches the request, monitoring,
episodes/search times, command queue and download queue. It commits an
`attempting` SQLite row keyed by request ID and season *before* posting the
supported scoped command:

```json
{"name":"SeasonSearch","seriesId":"<mapped integer>","seasonNumber":"<requested integer>"}
```

The actual values are integers obtained from fresh API records, never title
guesses. It reads the accepted command back, checks exact name/series/season,
and records status. If the POST response is lost, uncertain intent remains;
later runs may match a command queued since that attempt but never blindly
resubmit. A crash after journalling and before POST can therefore leave a
safe, uncertain hold even when no command exists. Failed/aborted commands also
remain recorded, rather than triggering repeated searches. Operators may
investigate these private rows; deleting the journal would defeat the duplicate
guard. Logs contain only outcome counts, including uncertainty and read errors.

The fresh checks reduce races but cannot atomically prevent a user from
changing monitoring between the final GET and POST; these APIs offer no
conditional SeasonSearch transaction. Native Sonarr policy still applies to
the scoped search. A queued/completed command proves a search was accepted/run,
not that a release was found, downloaded, imported or visible in Jellyfin.

## Private configuration and deployment

Create a protected JSON configuration and key files outside Git. The instance
URL must identify the exact configured Seerr Sonarr service; obtain its service
ID and URL from current private settings, not a guessed default. Normal and 4K
mapping IDs may select separate configured instances. This illustrative config
contains no deployment credentials or real service IDs:

```json
{
  "seerr_url": "http://seerr-internal:5055",
  "seerr_key_file": "/private/arr-request-search/seerr-api-key",
  "state_db": "/private/arr-request-search/state.sqlite3",
  "sonarr_instances": [
    {
      "service_id": 0,
      "url": "http://sonarr-internal:8989",
      "key_file": "/private/arr-request-search/sonarr-api-key",
      "allowed_roots": ["/private/media/shows"]
    }
  ]
}
```

Restrict configuration, keys, journal and backups to the service user, with
mode 0700 directories and mode 0600 files. Real requests, paths, IDs, credentials,
logs and SQLite files do not belong in this repository.

Run without `--apply` first:

```sh
python3 worker.py --config /private/arr-request-search/config.json
```

Dry-run sends GET requests only and uses an in-memory copy of any existing
journal; it creates no lock, state file, directory or persisted cursor. Inspect
the outcome counts and private mapping. Review `would-search` candidates before
enabling the applying timer. Use `--apply` to enable the narrow command POST.
Applying runs share a nonblocking private state lock and use synchronous
SQLite commits. The supplied service sets a restrictive umask, calls the worker
with `--apply`, and has a five-minute timeout. Its timer starts a minute after
boot and a minute after each run completes. Adjust the illustrative ExecStart
paths to the verified private installation, reload systemd and enable/start
the timer only after the dry-run checks. No native service restart is required.

Validation:

```sh
python3 -m unittest discover -s integration/server/arr-request-search -p 'test_*.py' -v
python3 -m py_compile integration/server/arr-request-search/worker.py
```

Eighteen isolated cases cover dropped burst searches, native searches already
sent, monitoring/cancellation/completion, active commands, existing downloads,
future episodes, age bounds, fresh cancellation, uncertain POST reconciliation,
exact identity/path/mapping, default dry-run, five-pair cursor fairness, and
read-only journal copies. Tests use temporary/in-memory state and fake APIs.

Before updating source, stop only this timer, let its oneshot exit, retain a
private source/config backup and a consistent SQLite backup, then install the
reviewed worker. Roll back by disabling this timer and restoring the previous
worker/config as needed. Retain the current journal; do not restore an older
database over newer attempts. This worker does not change native request,
monitoring, queue or media state apart from its explicitly guarded SeasonSearch.

Runtime schema evidence was checked against Seerr 3.4.1's installed
`server/constants/media.ts` / `entity/SeasonRequest.ts` and Sonarr
4.0.20.3014's supported request/series/episode/command/queue responses. Future
schema/version changes require rerunning the guarded dry-run and tests; these
files are not a wholesale Seerr or Sonarr configuration backup.
