# October 2 remote catch-up — staged, not deployed

This additive repair follows remote R6 → R7 → search-priority → remote-originals
→ UI reliability revision2. It is for the exact reviewed remote cohort, not a
local-PVR overlay, blank-device installer, firmware update or userdata clone.
The appliance was offline during preparation; no live change is claimed.

## Source repairs

The r2 category-OK fix did not cover section changes, empty category responses,
search, bookmarks or grid refresh/series return. These paths could still request
focus on an unpopulated list. `overlay.py` keeps focus on an existing button or
populated category list, moves it away before clearing a grid, and restores grid
focus only when the accepted asynchronous generation supplies real entries.
Reinitializing an empty chooser/grid also keeps usable focus.
An empty category response leaves a retry message and a usable top button.
Empty results do not restore a stale selection. Worker cancellation, exact
Jellyfin IDs, HTTPS transport, remote-originals policy and shared favourites are
unchanged. This repairs reproducible source-level focus faults; it is **not proof
that every user-reported freeze, network stall or hardware fault is resolved**.

The [backup migration](../../device-backup/README.md) preserves the device's
regulatory hint and its own ConnMan network recovery state. It retains the
private worker's identity, idle policy, SQLite consistency, retention and paths.

The title search needed no new matching algorithm: the current signed-in remote
account returned the two owned films for both `Quiet Place` and `A Quiet Place`.
Two new generic search regressions lock in partial-title/article omission and
owned-library scoping. Physical on-screen verification of both queries is pending.

## Guarded plan and deployment

Copy this directory, `../kodi/transaction.py` and `../../device-backup/` preserving
their relative layout to a private staging area. Use the intended host and the
full SHA-256 of the previously reviewed private worker (recorded privately):

```sh
python3 install.py --expected-hostname APPLIANCE \
  --snapshot-worker .config/PRIVATE-WORKER.py --expected-worker-sha256 REVIEWED-SHA256
```

It validates all current integrity entries, the full r2 manifest, browser source,
snapshot policy and private worker. It plans exactly four writes: backup policy,
worker, browser and addon manifest. Both starting and final addon manifests are
hash-pinned. A different source, generated manifest or worker requires review;
do not bypass a guard. A no-change final plan also checks policy/worker drift.

Add `--apply` only after a fresh private backup and current playback check. Apply
uses the existing idle-only transaction with one Kodi stop/start and readiness
check. It installs the policy before the worker. No reboot, network restart,
database restore or firmware operation is performed. Retain the printed private
rollback directory. On caught errors the transaction restores changed originals;
power loss/SIGKILL requires manual recovery. For rollback while idle, stop Kodi,
restore the four files as a set, start Kodi, verify old manifest and backup policy.

## Verification

```sh
python3 integration/release/remote-catchup/test_remote.py
python3 integration/release/remote-catchup/test_installer.py
python3 -m unittest integration/test-library-search.py \
  integration/device-backup/test_policy.py integration/device-backup/test_worker_overlay.py
python3 integration/check.py
```

The browser runner reconstructs common plus remote source and the prior r2 layer
before this repair. It runs79 contracts, including strict assertions rejecting
focus on empty controls. Its sole superseded historical assertion expected an
empty bookmark grid to receive focus immediately; identity/category assertions
remain. Installer tests cover idempotency, file ordering, final-manifest/worker
drift and unsafe/wrong cohort rejection. The exact saved59-entry cohort also
passed a four-file plan and pinned final-hash/idempotency check privately.

Live acceptance still requires cold launch, section switching, category OK,
search/empty results, series return, Back during loading, real channel switching,
Stop→reopen, VOD/episode playback and a verified private snapshot. See the
[remaining-issues checklist](../../REMOTE-AM9-CATCHUP-2026-10-02.md).
