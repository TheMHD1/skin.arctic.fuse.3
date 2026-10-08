# Paired short library-sync transactions

`am9-shared-20261008.7` composes the complete
[collection removal release](../library-removal/README.md). It changes two
hash-pinned Jellyfin for Kodi files, identically for local native-PVR and remote
HTTPS profiles. Firmware, server, account, playback transport, queue ordering,
IPTV exclusions and database schema remain unchanged.

## Failure evidence and bounded repair

A live movie→Venom transition stalled for several minutes. Native thread traces
showed Kodi's main thread waiting in `CVideoPlayer` destruction for its outbound
jobs, while `StoreVideoSettings` waited in SQLite. Concurrent Jellyfin sync was
waiting on an HTTPS read. SSH and the OS remained alive; it was a blocked Kodi
interface, not a CoreELEC crash. The exact Python network call was not captured
during that stall, so attributing that individual wait to collection fetching
is an inference, not a completed Python-stack proof.

Source inspection established two unsafe transaction boundaries:

- Update, userdata and removal workers retained a write transaction across the
  whole batch, including empty-queue and subsequent network/GUI waits.
- Collection sync wrote the collection row before iterating its remote movie
  pages. A slow later page could therefore retain the write lock for the entire
  HTTP retry period.

The pinned [upstream collection implementation](https://raw.githubusercontent.com/jellyfin/jellyfin-kodi/v2.2.0/jellyfin_kodi/objects/movies.py)
contains that write-before-fetch order. SQLite permits only one concurrent
writer; WAL does not provide concurrent write transactions. See
[SQLite transactions](https://www.sqlite.org/lang_transaction.html).

Workers now commit both existing connections after each dequeued item, before
the stop-property check or the next queue wait. A nested `finally` balances the
queue even on exit or commit failure. Excluded items are acknowledged exactly
once. Successful items keep their internal transaction boundary. Partial
handler writes still follow the existing commit-on-error policy; no new rollback
or silent data deletion policy is introduced. The two databases remain separate
transactions, as before; this is not distributed atomicity.

Collection movie pages are materialized before its first SQL write. The existing
membership, artwork and reference operations then consume those same pages.
An exception during a first or later fetch cannot leave a partially written
collection. Other movie/episode/model methods are unchanged. This repair does
not claim that every addon or every single-item network path is now incapable
of blocking a transaction.

## Rebuild, install and rollback

This is the current shared installer; it composes pending predecessor layers in
one guarded transaction rather than requiring historical live edits:

```sh
python3 integration/release/library-transactions/test_transactions.py
python3 integration/release/library-transactions/test_install.py
python3 integration/release/library-transactions/install.py --profile /PRIVATE/device.json
python3 integration/release/library-transactions/install.py --profile /PRIVATE/device.json --apply
python3 integration/check.py
python3 integration/release/verify-preservation.py
```

Stage `integration/release` and `integration/device-backup` in their relative
layout. Retain only that device's private profile and printed transaction backup.
The installer checks identity/account/transport, complete source/manifest,
source pins and receipts, preserves network/CEC/keymaps and refuses active or
paused playback. `movies.py` joins the preserved source inventory. One Kodi
stop/start activates the change; a second plan must be empty.

| Profile | Inventory | Whole manifest SHA-256 |
| --- | --- | --- |
| Local native PVR | 58 files | `017158ff49a9ebeb8ca0079a1fa50d68ee30225c30ad9759bb84fafd793cf60c` |
| Remote Jellyfin HTTPS | 62 files | `32465a8959dc4bd3e2e97c4f19a57ee21f88dee164cfd595a56585622701230f` |

Nine regression tests execute the actual pinned workers/model methods with
isolated SQLite. They reproduce the original writer lock, verify a second
writer can proceed between items and before GUI waits, test all three workers
and both database types, collection removal dispatch, exclusion/queue balance,
errors/stop/exit, paginated fetch ordering and network failures, and preserve
unrelated AST definitions. Four installer tests cover both profiles,
idempotency, new-source snapshot protection, source/receipt/identity drift and
symlinks. Complete saved-cohort builders reproduce both manifests; the older
limited local fixture obtains unmodified `movies.py` from the pinned clean
upstream build, not from another user's live userdata.

Rollback while idle: stop Kodi, restore the transaction's recorded changed
files and prior manifest together, remove only newly created paths listed in
`change-paths.json`, restart and verify the former cohort. Firmware rollback is
separate. Never copy another box's account, database, network or boot layout.

Remote installation and actual acceptance are recorded in
[the October 8 update record](../../REMOTE-AM9-UPDATE-2026-10-08.md). Local output
is prepared, not deployed. Source tests and a short live test cannot guarantee
that every upstream stream or long-running provider outage is healthy.
