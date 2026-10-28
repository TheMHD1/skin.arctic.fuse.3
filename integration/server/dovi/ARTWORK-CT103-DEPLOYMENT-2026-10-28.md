# CT103 exact artwork publication deployment — 2026-10-28

This is a versioned deployment plan for the additive exact-item artwork
publisher. It is deliberately **not** a claim that it is live. The publisher
belongs on ARR CT103 alongside the DOVI reconciler; CT102 hosts Jellyfin and
must not be used as an indirect executable path for CT103.

## Invariants

- CT103 canonical source media is `/data/media/{movies,shows}/<title>`.
- CT102's Jellyfin bind mounts must expose the same title using the exact same
  path spelling. Do not translate a `/tank/...` or `jellyfin-view/...` path at
  runtime and do not use a symlink guess.
- The worker obtains the item only by its accepted Jellyfin ID, verifies that
  exact path, and exits complete when `Primary` is already present. It never
  enumerates a library and it never replaces an existing image.
- The worker's private URL reaches CT102 Jellyfin and its `token_file` is the
  already protected CT103 Jellyfin token-file reference. Keep the config and
  token root-owned and mode `0600`; do not copy either into Git or a unit file.
- The DOVI caller and worker use CT103-local executable/config/state paths:
  `/data/config/_dovi/artwork-publication/`. `state_db` must also be under that
  private CT103 tree, not under the media bind mount.

## Required source set

Install the reviewed `integration/server/artwork-publication/` source as:

```
/data/config/_dovi/artwork-publication/artwork-publication.py
/data/config/_dovi/artwork-publication/config.json       # private, 0600
/etc/systemd/system/artwork-publication.service
/etc/systemd/system/artwork-publication.timer
```

The private `fast-import.json` on CT103 must contain both explicit absolute
paths, or neither while the feature is intentionally disabled:

```json
"artwork_enqueue": "/data/config/_dovi/artwork-publication/artwork-publication.py",
"artwork_config": "/data/config/_dovi/artwork-publication/config.json"
```

`dovi-import-fast.py` forwards that exact pair to every bounded scoped
reconciliation. The notify-only service must receive the same pair in an
override for its `ExecStart`; otherwise previously durable outbox rows would
not enqueue artwork. Keep `--apply --notify-jellyfin --notify-only` and the
existing protected DOVI token mechanism intact.

The CT103 notify override must reset (not append to) its existing `ExecStart`,
while retaining the already deployed bridge flag:

```ini
[Service]
ExecStart=
ExecStart=/data/config/_dovi/dovi-library-view.py --apply --notify-jellyfin --notify-only --new-title-bridge --artwork-enqueue /data/config/_dovi/artwork-publication/artwork-publication.py --artwork-config /data/config/_dovi/artwork-publication/config.json
```

Use the exact existing `ExecStart` as the baseline if it has additional
reviewed private arguments; do not replace its `EnvironmentFile`, token parser,
timer cadence, or timeout settings.

## Preflight before enabling either timer

1. Stop or hold only the relevant DOVI publication/import timers while copying
   source and making the existing runtime backups. Do not alter media or run a
   whole-library Jellyfin scan.
2. On CT103 and CT102 independently select a known canonical movie and series;
   query its exact Jellyfin ID and confirm Jellyfin returns a `Path` spelling
   exactly equal to CT103's canonical title root (or a movie file directly
   beneath it). A mismatch is a hard stop.
3. Confirm the private worker config uses that reachable CT102 URL, the
   protected existing token-file reference, an absolute CT103 state-db path,
   and media root `/data/media`. Verify config/token ownership and modes
   without printing their contents.
4. Run `test_artwork_publication.py`, `test_dovi_reconciler.py`, and
   `test_fast_import.py` before copying and again against staged source. These
   are mock-only; they are not production proof.
5. Validate the staged executable with `python3 -m py_compile`; use
   `systemd-analyze verify` on staged units. Do not start a worker yet.

## Controlled activation and proof

Reload systemd, install the notify-only override and fast config as one
reviewed transaction, then enable the artwork timer only after preflight
succeeds. Use one newly imported test title whose Jellyfin item has no Primary.
Verify with exact-ID requests and worker status only: one job, at most one item
refresh while `verifying`, completion when Primary appears, and no
library-refresh request. A title with an existing Primary must complete without
a refresh POST. Retain the SQLite state and journal as private rollback evidence.

To roll back, disable only `artwork-publication.timer`, remove the two explicit
DOVI artwork arguments/fast-config keys together, and retain the worker state
database. Do not delete pending/dead jobs or replace the existing DOVI
publication database: re-enabling with the same paths preserves bounded retry
and age evidence.
