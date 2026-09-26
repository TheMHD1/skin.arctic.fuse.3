# Dolby Vision compatibility and scoped publication

These maintained sources preserve the P7 master → separate P8.1 compatibility
copy → Jellyfin library-view workflow, with the September 26 scoped import and
publication repair now deployed. They do not change a user's access rights or
enable original P7 for every device. Kodi original selection is a separate
opt-in, documented in [CUSTOMIZATIONS](../../CUSTOMIZATIONS.md).

| Repository source | Existing private runtime target |
| --- | --- |
| `dovi-library-view-20260922.py` | `/data/config/_dovi/dovi-library-view.py` |
| `dovi-retry-state-20260922.py` | `/data/config/_dovi/dovi-retry-state.py` |
| `subtitle_view_filter.py` | `/data/config/_dovi/subtitle_view_filter.py` |
| `dovi-process-queue-20260922.sh` | `/data/config/_dovi/process-queue.sh` (sanitized reference; verify actual service ExecStart) |
| `dovi-import-fast.py` | `/data/config/_dovi/dovi-import-fast.py` |
| `jf-notify.sh` | ARR's private mounted import hook (Sonarr and Radarr) |

The original reconciler, retry helper and subtitle filter matched the ARR
server byte-for-byte during the September 22 preservation; that historical
comparison is not a fingerprint for the later repaired reconciler. The worker reference
contains a deliberately **redacted** API key; it is not directly deployable.
Its private Jellyfin/notification endpoints and credential must be provisioned
locally, never committed. The reconciler currently reads the worker's literal
`JK` assignment; do not substitute an environment expression without adapting
and testing that parser. Never use a redaction marker as a real credential.

The worker needs `mediainfo`, `ffmpeg`, `ffprobe`, `mkvmerge`, `dovi_tool`,
`jq`, `curl` and `flock`. Retain the existing private systemd service/timer,
mounts, permissions, queue/database and scoped scratch paths; review their
actual configuration before a new-server deployment. The source is not a
complete OS/container provisioning package. The worker's default is live;
**do not execute it on a real host for commissioning, even with MODE=dryrun**.
Dry-run skips conversion but still creates directories/logs, cleans scratch
jobs and drains/consumes the real queue. Validate syntax with `bash -n` only.
Behavioral commissioning requires an adapted copy in a disposable namespace
with every path and endpoint isolated, not just a MODE environment variable.

## Repairs retained

- Failed/blank media probes remain unknown, rather than being mistaken for SDR
  and exposing a P7 original through the compatibility view.
- Per-file probe cooldown and retry-state fingerprints prevent repeated costly
  work on unchanged failures; changed files get a fresh opportunity.
- Reconciler appends and worker queue snapshots share a local-filesystem lock.
- Subtitle hiding/retirement requires valid replacement markers and hashes.

`dovi-worker-queue-lock.patch` records the focused worker change. Do not apply
it again to the included already-patched worker. The isolated regression:

```sh
python3 integration/server/dovi/test_dovi_reconciler.py
bash -n integration/server/dovi/dovi-process-queue-20260922.sh
```

Tests use temporary fake media/queues and a stub for the separately maintained
subtitle publisher. They do not run conversions or prove every source is good.
The current isolated suites pass forty-six reconciler and ten fast-worker/helper
cases. The production repair includes the import hook and remounted hook in
both ARR containers, separate `import-probe.sqlite` and `publication.sqlite`,
the scoped worker and independent thirty-second publisher, and the final
companion-ready handoff. The private converter was changed with the guarded
transform between runs; no conversion was interrupted.

Real Jellyfin acceptance also passed eleven assertions in an isolated fixture,
including new movie/episode playable-file indexing, provider identity guards,
duplicate events, subtitle replacement/serving, durable acknowledgement and
unchanged unrelated items, with no publication-time global library scan. See
[the acceptance record](../publication-e2e/ACCEPTANCE.md) for pinned artifacts
and limits: this is established-library synthetic SDR/API acceptance, not
download-client, ARR-hook, physical playback or client-UI proof.

## Durable, scoped publication (September 26 deployed repair)

The import hook queues an exact native event after ARR has imported an episode
or movie into the canonical library. The fast worker starts scoped reconciliation;
it does not start a whole-library sweep for a normal import. Download-client completion
alone does not prove import success. Season packages generate the normal
episode imports; publication does not wait for a complete season.

The reconciler commits a revisioned `notification_outbox` row, coalesced to the
containing movie/show title directory, in the separate private
`publication.sqlite` before view hardlink replacement or removal. Full-sweep
probe state remains in `library-view.sqlite`; scoped probes use
`import-probe.sqlite`. A scoped import also stages a stable, deduplicated intent
when the validated view hardlink already exists.

View changes first persist a per-view mutation marker and leave the title in
`staging`. Only successful atomic link/unlink completion removes that marker;
the title becomes dispatchable when all its markers are committed. An unchanged
link repair can finalize the same fingerprint after a crash without resetting
attempts or age. A removal interrupted after unlink can recover from proven
absence while its view parent remains available. Superseding a view mutation
and completing an older marker uses fingerprint comparison, so an older writer
cannot finalize newer work. Publisher dispatch and verification also defer
nonblockingly while a title commit lock is held; no title lock is held across
HTTP, probing or subtitle hashing. The additive marker table leaves preexisting
outbox rows compatible and does not rewrite existing retry/verification state.

HTTP 2xx records queued acceptance, not completion. Video publication remains
in `await_index` until bounded exact-target queries find every expected
canonical video in a local Jellyfin MediaSources path. Only then does a
revision-checked acknowledgement remove the intent. Verification does not
repost the refresh. Sidecar/deletion-only intents without video expectations
can acknowledge accepted delivery; they do not claim playable-video proof.
A failed POST or missing token retains intent subject to the retry/age limits
below. A crash between intent, link and acceptance can result in a duplicate
targeted refresh; duplicate source fingerprints do not reset the retry budget.
This proves native item indexing for verified videos, not client UI or physical
playback visibility.

A root-level file with no containing title directory, a path outside the two
configured media roots, or a lexical traversal is never staged for publication.
Its otherwise-valid view hardlink may still be reconciled, but the publisher
logs and skips the unsupported scope instead of broadening it to a media-library
root refresh.

The first changed title is published immediately after its validated video link
is created. `notification_receipts(folder,sent_at)` persists a sixty-second
minimum interval between accepted refreshes of the same title. Later changes
stay dirty for a trailing refresh, including across separate reconciler runs;
forcing a flush does not bypass that interval. Pending sidecars are checked
before the next video probe, every five seconds during traversal, and at
completion. A failed folder is tried once per run to avoid repeated network
waits. The original P7/unknown-probe gate, hardlink paths, subtitle filtering and
cleanup grace remain authoritative.

For each due title, the publisher uses supported `GET /Items` with a bounded
Series/Movie search and `Fields=Path`. A display name alone never selects a
target: a Series must have the exact title path; a Movie must uniquely occupy
that exact directory. If display-name search misses a localized/renamed title,
the publisher resolves the owning library using exact location containment
from `/Library/VirtualFolders`, then paginates `/Items` under that library's
`ItemId` with only Series/Movie types and Path fields. It caches that title
catalog once per process; no global IPTV inventory or media filesystem scan is
performed. Pagination is bounded at twenty thousand title rows; overflow or
API failure retains delivery intent for investigation rather than issuing a
global refresh. The lookup is cached only for that process and performed
only for pending publication, never for every video encountered in a scan.
An identified title uses `POST /Items/{id}/Refresh` with
`metadataRefreshMode=Default`, `imageRefreshMode=None`,
`replaceAllMetadata=false` and `replaceAllImages=false`. This updates neither
provider IDs nor replacement preferences. In reviewed Jellyfin 12.1,
`ProviderManager.RefreshItem` calls `Folder.ValidateChildren` with recursive
validation enabled by default; the HTTP endpoint has no `recursive` parameter.
New titles require the optional scoped discovery bridge described below.
Neither `/Library/Media/Updated` nor `/Library/Refresh` is a fallback: these can
recurse the containing library when a title is not yet indexed.

The supplied `dovi-library-notify.service` and `.timer` drain only due outbox
rows every thirty seconds using `--apply --notify-jellyfin --notify-only`.
They never walk or probe media and use the existing private worker-token parser.
Publisher runs use `/run/dovi-library-notify.lock`, independent of the full
scan process lock. Probe state and publication state are separate databases;
the publisher never waits for the full-library hashing sweep. Short per-title
locks serialize link/removal commits only, not media probing or subtitle hashing.
The full scan and existing fifteen-minute repair timer remain a backstop.

The regression cases cover failure replay with unchanged links, notification
before a later probe, committed intent before interrupted link/removal,
post-link interruption, dry-run suppression, withholding P7/unknown inputs,
persistent title coalescing, lock contention, notify-only scan suppression,
exact/ambiguous and localized lookup, owning-library pagination, supported
refresh flags, root/outside/corrupt scope rejection, refusal of library-wide
fallback, queued-versus-verified acknowledgement and bounded retries. All paths, databases,
queues and HTTP calls in these cases use temporary fixtures or mocks.

For future deployment or rollback, follow the quiescent-writer and migration
procedure below; do not treat the old probe database as the active publication
store. No ARR direct-to-Jellyfin connection or client restart is required.
Verify eligible imports through the canonical file, validated view hardlink,
queued refresh and exact local Jellyfin Episode/Movie source path. Inspect
retained intents and dead-letter audit through read-only SQLite when delivery
fails, and keep media inventories private.

## Exact-import fast path (September 26)

`jf-notify.sh` queues immutable native Download events (app, native title ID,
canonical title and imported video), rather than starting a full sweep. Other
events retain the full repair trigger. `dovi-import-fast.py` claims events
durably, validates the native ARR title ID/path/provider identity, groups up to
five due titles, and invokes scoped reconciliation. Only imported videos and
same-stem companion/sidecar files are examined; unrelated subtitle digests and
media are untouched. Scoped runs do not delete orphan links. Unknown probes and
P7 without a validated P8 companion remain withheld. Exact native history
`downloadFolderImported` records from the last 24 hours provide automatic
backfill, bounded to 2,000 metadata records per app. Durable event enqueue
precedes history checkpoint advancement. Claimed events survive a process crash.

Install the fast oneshot/path/timer together. The path provides prompt queue
activation; the thirty-second timer handles backfill and due retries. No
long-lived daemon is required. The private JSON config must contain:

```json
{
  "media_root": "/data/media",
  "spool": "/data/media/compatibility/.dovi-import-queue",
  "claims": "/data/media/compatibility/.dovi-import-working",
  "state_db": "/data/config/_dovi/import-fast.sqlite",
  "scoped_state": "/data/config/_dovi/import-probe.sqlite",
  "notification_state": "/data/config/_dovi/publication.sqlite",
  "reconciler": "/data/config/_dovi/dovi-library-view.py",
  "worker_lock": "/run/dovi-import-fast.lock",
  "reconcile_lock": "/run/dovi-import-scope.lock",
  "publication_lock": "/run/dovi-library-notify.lock",
  "title_locks": "/run/dovi-library-title-locks",
  "new_title_bridge": true,
  "arr_instances": [
    {"name": "sonarr", "url": "PRIVATE_SONARR_URL", "key_file": "PRIVATE_KEY_FILE"},
    {"name": "radarr", "url": "PRIVATE_RADARR_URL", "key_file": "PRIVATE_KEY_FILE"}
  ]
}
```

Keep config/key files private. Spool and claims must share a filesystem for
atomic rename; only the incoming spool is ARR-writable, claims/state remain
root-owned. The hook creates temporary events outside the watched spool before
atomic rename. Defaults retain the existing view/compatibility roots and token
parser; optional config keys `view_root`, `compatibility_root`, `queue`,
`queue_lock`, `retry_state`, `worker`, and `jellyfin` forward explicit overrides.

New-title publication requires LibraryExperience 1.2's supported scoped bridge
`POST /Habibi/LibraryExperience/DiscoverTitle`: owning library ID, exact logical
canonical parent path, direct child name, Series/Movie kind and native ARR
provider IDs. A missing bridge, ambiguous mapping or 409 retains intent; no root
scan is attempted. Existing title refresh retains native API flags above.
Host view paths must never be sent as Jellyfin paths when bind mounts expose
them at canonical `/data/media/shows` or `/data/media/movies` locations.

HTTP acceptance is only **queued**, not end-to-end completion. Publication
retains expected canonical video paths in `await_index`, then performs bounded
Episode/Movie metadata queries under the exact target ID. Only matching local
MediaSources paths acknowledge that revision. Verification polling does not
repost the refresh. CAS revision checks prevent an acknowledgement from losing
an import arriving during HTTP work. Fast job `view-ready` means a validated
link and durable publication intent, not Jellyfin/client visibility.

Actual failures are capped at eight attempts and 48 hours. Delays taper through
30 seconds, 2 minutes, 10 minutes, 30 minutes, 2 hours, 6 hours, 12 hours with
10% jitter, then become retained terminal dead letters. Identical source
fingerprints never reset attempts/age; changed source content creates a new
revision. P7 companion wait and lock/cooldown deferrals do not spend attempts,
but still expire at 48 hours. Unknown probes do spend a bounded local retry
budget. Publication makes at most five due deliveries/checks per run; auth or
transport outage opens a shared circuit and stops batch fanout. Native history
read failures also taper and terminally stop polling until a genuinely new
import reactivates that app. Logs report queued, verified, pending and dead counts.

Migration: first stop path/timers and wait for **all legacy full/publisher
oneshots to exit**; legacy code has neither the new per-title locks nor separate
publication DB. Back up SQLite consistently and retain old sources. Install
the complete new reconciler/helper/hook/unit set, preserving runtime names and
permissions. Run `migrate-publication.py --source PRIVATE_OLD_PROBE_DB
--destination /data/config/_dovi/publication.sqlite` once while quiescent.
It opens the source read-only, copies old outbox/receipts, rejects unsafe scopes,
and records an idempotent migration marker. Do not copy an old database over a
newer publication database. Enable the plugin bridge only after its endpoint
is installed; add `--new-title-bridge` to the publisher ExecStart (the worker
config controls its own scoped runs). Reload systemd, restore the full backstop,
and enable fast path/timer plus publisher timer. Do not run an old legacy writer
concurrently with new workers. Rollback must likewise quiesce all writers and
retain new publication intents and dead-letter audit for recovery.

Isolated tests: `python3 test_dovi_reconciler.py` (46 cases),
`python3 test_fast_import.py` (10 cases). These use temporary fixtures and mocked
HTTP/probes, never live media or refreshes. They cover unchanged validated view
backfill, revision CAS, terminal fingerprint dedup/reactivation, queued index
verification without repost, local-media proof, claim recovery, history replay
checkpointing, P7 waiting and unknown-probe caps, alongside original gate tests.

Validated conversion completion now calls `dovi-import-fast.py --config PRIVATE_CONFIG
--companion-ready CANONICAL_FILE`. It recovers a journaled native mapping and
revalidates current ARR identity/path; an older unjournaled title uses one bounded
native title-catalog exact-path lookup. It durably queues the scoped event and
releases nonterminal companion waits immediately. The fingerprint includes the
actual companion signature: a duplicate completion cannot reset terminal retry
budgets, while a genuinely replaced companion creates new work. The scoped
reconciler still independently probes/gates the companion; this handoff cannot
link an unvalidated P7 source. Unknown mapping is logged and left to the periodic
repair backstop, never a root Jellyfin notification or new full-sweep trigger.

The preserved converter is **sanitized, not an installable private replacement**.
Use `patch-worker-publication.py --source PRIVATE_RUNTIME_WORKER --output PRIVATE_STAGE`
to transform the private worker: guarded exact legacy refresh-block and trigger
matching, removing all direct Jellyfin HTTP, retaining every credential line
verbatim. It refuses an unexpected/already-patched worker and in-place output.
Review the private staged diff and `bash -n` locally, then replace only between
conversion runs; never interrupt or swap the currently running conversion.
The transformer emits no credential data. Companion completion creates no new
daemon or additional timer.

Pending expectations from an ARR rename/upgrade are pruned only for genuinely
absent canonical child files while the canonical root and exact title remain
present. New video expectations still require native local MediaSources proof.
A missing title/root fails closed and cannot turn an unavailable mount into a
successful acknowledgement.

## Recovery and known limits

Stop the appropriate timer/worker before replacing a reviewed source set;
retain private previous sources and consistent queue/database backups. Restore
compatible source and configuration together. Never overwrite/delete original
media to repair a companion. The September 22 preservation was read-only. The
later September 26 scoped publication deployment and isolated acceptance are
recorded above; neither changes the commissioning precautions for the
sanitized converter reference.

Source-to-companion provenance invalidation is still pending: a profile-valid
old companion can outlive a changed original. Do not describe profile checks
as complete provenance validation. The two known corrupt Friends originals
remain withheld, not repaired by this change. Moustafa's remote P7 route is
also still pending enrollment and real-device/throughput acceptance.
