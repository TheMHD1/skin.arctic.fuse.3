# Venom episode identity freshness

Two actual remote Kodi episode selections failed with HTTP 404 even though
their series/episode cards were present. The exported `.strm` files referred to
episode IDs with no active relation in Dispatcharr. Movie and live playback
worked, and the Kodi process remained responsive. This was a server catalogue
freshness defect, not proof of a CoreELEC or browser freeze.

Dispatcharr can refresh episode details after 24 hours, while our successful
series exports used a seven-day cooldown. Backend episode identities could
change during that interval without updating the corresponding stream files.
The episode stream route correctly requires an active relation for the internal
`Episode.id`; changing that route to accept unrelated external IDs would not be
a safe fix. The XC series ID is **M3USeriesRelation.id**, not `Series.id`. An
early diagnostic using the latter table was discarded; it does not establish
that a series was deleted.

## Repair and bounds

`venom-series-revisions.py` reads active episode identities from the existing
Dispatcharr container. It groups them by their shared Series and maps them to
the XC series-relation IDs, matching the detail endpoint's multi-provider
semantics. Sorted, deduplicated identity hashes detect rotation without testing
or downloading every stream.

The exporter stores a revision for each successfully exported series. A missing
or changed revision bypasses the weekly cooldown. Stable revisions keep it.
The stored revision comes from the detail response actually written to disk,
not from the snapshot before fetching: fetching can itself refresh the backend
IDs. That prevents a perpetual self-triggered refresh loop. Failed/empty detail
responses retain their six-hour backoff. A revision-audit failure is logged and
falls back to the former bounded schedule; it does not erase content.

The helper caps 50,000 series relations, 500,000 episode identities, a 20-second
query deadline and an 8 MiB output. It adds no credentials, public endpoint,
resident watchdog or new dependency. Source assumes the reviewed Dispatcharr
0.31 model/endpoint cohort; an image update must rerun the query and identity
tests. Its existing Docker/container dependency is explicit, not a new service.

Existing exporter locks, free-space guard, maximum duration, series-count limit,
atomic file writes, dirty-generation publication, stream-session identity,
provider credentials and time/CPU/memory limits remain. Files are replaced only
when different; no video or removed-provider file is deleted. This is not a
provider-wide availability guarantee or stale-title quarantine policy.

## Deployment, verification and rebuild

Keep these files together:

- `venom-jellyfin-export.py`
- `venom-series-revisions.py`
- `venom-series-freshness-install.py`
- `test-venom-series-revisions.py`

```sh
python3 integration/server/test-venom-series-revisions.py
# On the reviewed media server, from a staging directory containing both payloads:
python3 /PRIVATE/staging/venom-series-freshness-install.py
python3 /PRIVATE/staging/venom-series-freshness-install.py --apply
```

The installer checks the server identity, exact old/new source bytes, symlinks,
free space and the export lock. It refuses an active native export, privately
backs up existing code and a consistent progress database, installs the helper
before the importing exporter, and requires an empty final plan. It does not
restart Docker, Jellyfin, Kodi or the host.

| Artifact | SHA-256 |
| --- | --- |
| Former exporter | `60705b4c0beafc976ad7094fa9bfd2aa70821f016aaa73f9f0a624498573ae33` |
| Current exporter | `75df0447a2d32fe6db8909f28cd7f9c1a63e50aaf07ef1eb3a5e864f7b39fac8` |
| Revision helper | `482a7fe059cdbaa9f579765f7dba6f1ea350dfca483744164d7cc36a96e759cb` |

The optional repeatable `--series-id` flag limits a verification pass to selected
XC relation IDs; it is not a per-title repair or a manual URL replacement. The
same maintained algorithm handles every default timer pass. Seven regressions
cover hashing, identity rotation, stable/no-audit fallback, error backoff,
relation-versus-Series identity domains, multi-provider grouping, bounded
parsing, post-fetch revision storage, installer drift/idempotency and preserved
exporter safeguards.

The October 8 deployment refreshed both failed sample series, writing 16
episode links in a bounded 19.3-second pass including unchanged movie-catalogue
processing. Their stored revisions subsequently matched a fresh backend audit.
Only the two tested Jellyfin episode items were explicitly refreshed for immediate
acceptance; the existing coalesced library publisher handles normal batches.
Both formerly failing episodes subsequently played through the actual Kodi UI
and switched back to live TV with advancing frames and no Kodi restart.
The playback and episode→live acceptance are recorded in
[the remote AM9 update record](../REMOTE-AM9-UPDATE-2026-10-08.md).

The native timed exporter continued the general repair independently. An early
readback showed 220 processed series and 4,724 episode links; that is progress,
not a claim that all 9,124 catalogue entries were completed or stream-tested.
It keeps the existing 30-minute native pass and subsequent timer scheduling.
Do not wait for the whole catalogue before verifying the specific UI repairs,
or silently turn this into unbounded monitoring.

## Rollback

Wait for the native export to become idle and acquire its export lock. Restore
the affected server's own recorded exporter/helper files; remove the helper
only if the backup shows it was newly created. The new `series_revision` table
is additive and ignored by the former exporter. A consistent private database
backup is available if state rollback is actually required. Newly valid stream
URLs do not need to be replaced with obsolete URLs merely to roll back code.
Retain native dirty-generation publication; never restore another server's
credentials, catalogue state, library policies or databases.
