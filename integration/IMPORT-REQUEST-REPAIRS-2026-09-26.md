# Import publication, request handoff and privacy — September 26

The native configuration repairs and import/subtitle publication refactor are
deployed and accepted within the test boundaries below. Exact media
inventories, user IDs, keys, rollback archives and live logs remain private.

## Native settings and request handoff

- Future ARR title folders now include year/provider identity, using the native
  fields preserved in [ARR maintenance](server/arr-maintenance/README.md).
  Existing media was not bulk-renamed. One proven wrong Jellyfin provider match
  was corrected through native Identify after checking authoritative IDs.
- An automatic-search indexer was repeatedly holding otherwise successful
  searches for roughly 107 seconds. Its Prowlarr application profile now has
  `enableAutomaticSearch=false`, with `enableInteractiveSearch=true` and
  `enableRss=true` retained. Other indexers remain unchanged. Rebuild this
  configuration by identifying the affected indexer in the current deployment,
  privately backing up its indexer/profile settings, creating a separate native
  App Profile with these fields, assigning only that indexer, and running native
  `ApplicationIndexerSync`. Verify the resulting automatic/interactive/RSS
  flags in both Sonarr and Radarr. Do not hard-code a copied indexer/profile ID.
  Roll back by restoring that indexer's previous profile assignment and syncing;
  do not overwrite other profiles or disable all torrent sources.
- Closely spaced approved requests for two seasons of one show exposed a
  handoff gap: an already-running native series search did not cover the later
  season. The [external recovery worker](server/arr-request-search/README.md)
  conservatively checks recent approved requests against exact ARR identity,
  monitoring, aired missing episodes, search history and current work. It
  journals before issuing at most one native `SeasonSearch` per request/season.
  An uncertain POST is retained for review, never blindly repeated. The first
  deployed applying run made no changes because its candidate episodes were
  already imported; a future live recovery remains a separate acceptance test.
- A separate acceptance check found native Seerr Movies/Shows availability
  selections disabled. The [guarded selection helper](server/arr-maintenance/README.md)
  enables only verified native library IDs, preserving every other scope and
  setting. Seerr's native recent scan then reconciled newly imported requested
  seasons. Its existing five-minute metadata poll remains responsible for
  subsequent availability; no extra scanner or timer was installed. An initial
  Seerr full metadata-catalog reconciliation handles older corrected identities;
  it is not a Jellyfin filesystem scan. In Seerr 3.4.1, a bare GET to
  `/settings/jellyfin/library` unexpectedly disables all selections: safe audits
  must use `/settings/jellyfin`, as covered by the helper's regressions.

## Request privacy and approval

Native permissions remove `ADMIN`, `MANAGE_REQUESTS` and `REQUEST_VIEW` from
every account except the designated owner. Default permissions must also omit
these bits. Preserve unrelated permission bits. One requester additionally
received native normal/4K request and auto-approval permissions with explicit
unlimited movie/TV quotas; this does not bypass configured ARR quality profiles
or create a missing 4K service mapping.

Native permissions correctly restrict the request list but did not filter
foreign embedded requests in movie/TV metadata or global request counts. The
[version-pinned Seerr overlay](server/seerr-request-privacy/README.md) closes
those response-level gaps without changing the database or shared catalogue.
Live tests verified own-only ordinary-user results, foreign request rejection,
and complete owner results. Both the image pin and startup guard must be rebased
and tested for a future Seerr version; never simply remove the guard to upgrade.

Before changing permissions, retain private GET responses for each affected
account and its quota settings. Apply supported per-user APIs, omitting a null
username rather than writing it, and compare readback. To restore selected
settings, merge the recorded fields into current native settings; do not restore
the entire application database. Test native and embedded request visibility
after restoring or upgrading. Removing only the overlay reopens the embedded
data leak even if list permissions are still restrictive.

## Publication investigation

Download completion, ARR import, compatibility-view availability, Jellyfin
indexing and request availability are separate states. HTTP 204 for a refresh
does not prove the item has reached the client.

The original import hook woke a whole-library compatibility reconciliation.
That process reread unrelated managed-subtitle content before reaching newly
imported files. Under storage load this delayed new episodes by many minutes.
Adding durable notification intent alone was insufficient: the notifier also
shared the full reconciler's lock. Read-only storage checks found no pool read,
write or checksum errors; the worker was moving through slow reads, not proved
permanently stuck on one corrupt subtitle.

The deployed [exact-import worker](server/dovi/README.md) spools native ARR
Download events, validates current ARR identity/path, and reconciles only the
imported video and its sidecars. A bounded native history backfill recovers missed
events. New probe state and notification state are separate from the slow full
repair job. The latter remains a periodic repair backstop, not the import path.
Conversion completion also hands off its exact canonical file through this queue.

For an existing title, publication uses native exact-item refresh. For a new
title, [Library Experience 1.2](server/library-experience-plugin/README.md)
resolves/creates only the direct child of a verified native physical library
parent, then refreshes that title. Native `Library/Media/Updated` was unsuitable:
for an unknown title it can climb to the library root and recursively validate
unrelated titles. No new Jellyfin server-core patch is needed for this repair.
An empty new library needs its normal initial bootstrap scan first.

An HTTP acceptance is not completion. The durable publisher verifies the exact
expected file paths and playable native media sources before acknowledging work.
An additive per-view commit journal prevents sending or acknowledging a title
while a link/removal is uncommitted, including a process crash between staging
intent and replacing the file. Same-fingerprint repair completes the outstanding
commit without resetting retries. A nonblocking title lock defers overlapping
mutation; no filesystem lock is held across network calls or probes.
The [subtitle publisher](server/subtitle-publication/README.md) likewise publishes
provider arrivals before AI work, retains the managed AI-track verifier, refreshes
only the owning item, and verifies served subtitle content. It handles atomic
provider replacements without leaving the compatibility view on an old inode.
The old Bazarr full-scan and global scan pause/resume paths were removed after
confirming no outstanding resume obligation.

Retries are finite: up to eight failed attempts, with delays of 30 seconds,
2 minutes, 10 minutes, 30 minutes, 2 hours, 6 hours and 12 hours, plus a 48-hour
maximum job age. Shared outage cooldowns and bounded batches reduce repeated
calls. Terminal failures remain auditable; unchanged duplicate events cannot
reset their budget. A genuinely changed source can create new work.

### Acceptance

- Focused regressions: 46 reconciler, 10 fast-import/helper, 34 subtitle,
  18 request-search, 2 native naming, 5 Seerr selection, 11 Seerr privacy and
  38 plugin tests.
- [Real Jellyfin end-to-end fixture](server/publication-e2e/ACCEPTANCE.md):
  11 assertions plus four harness safety tests. The actual maintained workers
  published a new Movie and Episode, retained stable IDs on duplicate discovery,
  rejected provider conflicts, and served both initial and atomically replaced
  Arabic subtitles. Unrelated anchors were unchanged; the global scan stayed
  idle with an unchanged execution result throughout these publication tests.
- Production: the delayed series' exact native episode sources were recovered
  and indexed. A genuine provider subtitle arrival was replayed without changing
  source bytes and passed exact-item/served-SRT verification. A subsequent
  managed subtitle was verified automatically by the deployed worker.
  Both native ARR custom-script tests returned success with Download enabled;
  a replayed existing import through the actual container hook automatically
  reached the validated view and drained publication without editing media.
  Native Seerr reconciliation subsequently marked all four affected requests
  completed with correct title/season identities. The readiness worker queued
  their durable events, but no matching message-capable sessions were active;
  this is not evidence that an on-screen notification was delivered or seen.

These checks prove real indexing and HTTP subtitle publication, not a new
download from an indexer, GPU generation, client UI or physical playback. Existing
scheduled/backstop scans remain legitimate and are not canceled by these workers.
No test suite guarantees every future upstream change; the pinned upgrade gates
and repeatable acceptance fixture are part of the maintenance contract.

## Preservation and update boundary

These changes do not require a new Jellyfin server-core fork or custom client
APK. Native naming/indexer/permission settings, external workers and any plugin
extension have independent rollback boundaries. Keep the exact source set,
tests, service files and private configuration together. Review supported API
and plugin compatibility on upgrades; source preservation alone does not prove
runtime compatibility or client visibility.
