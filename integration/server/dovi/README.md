# Preserved Dolby Vision compatibility-service source

These are the September 22 maintained service sources, not a new deployment.
They preserve the existing P7 master → separate P8.1 compatibility copy →
Jellyfin library-view workflow. They do not change a user's access rights or
enable original P7 for every device. Kodi original selection is a separate
opt-in, documented in [CUSTOMIZATIONS](../../CUSTOMIZATIONS.md).

| Repository source | Existing private runtime target |
| --- | --- |
| `dovi-library-view-20260922.py` | `/data/config/_dovi/dovi-library-view.py` |
| `dovi-retry-state-20260922.py` | `/data/config/_dovi/dovi-retry-state.py` |
| `subtitle_view_filter.py` | `/data/config/_dovi/subtitle_view_filter.py` |
| `dovi-process-queue-20260922.sh` | `/data/config/_dovi/process-queue.sh` (sanitized reference; verify actual service ExecStart) |

The first three files' SHA-256 hashes were compared read-only with the ARR
server during preservation and matched byte-for-byte. The worker reference
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
Ten reconciler cases passed before deployment and again during preservation.

## Recovery and known limits

Stop the appropriate timer/worker before replacing a reviewed source set;
retain private previous sources and consistent queue/database backups. Restore
compatible source and configuration together. Never overwrite/delete original
media to repair a companion. The retained services were healthy after the
September 22 reboot, but this preservation pass neither ran nor restarted them.

Source-to-companion provenance invalidation is still pending: a profile-valid
old companion can outlive a changed original. Do not describe profile checks
as complete provenance validation. The two known corrupt Friends originals
remain withheld, not repaired by this change. Moustafa's remote P7 route is
also still pending enrollment and real-device/throughput acceptance.
