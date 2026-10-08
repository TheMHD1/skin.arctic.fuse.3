# Shared Jellyfin collection removal repair

`am9-shared-20261008.6` composes the complete
[Venom lifecycle release](../venom-lifecycle/README.md). It changes one pinned
Jellyfin for Kodi file in both profiles; it does not change the server, accounts,
library preferences, playback transport or firmware.

## Defect and behavior

Live startup logs contained `UnboundLocalError` in `RemovedWorker` when a removed
`BoxSet` arrived. The dispatch had no collection branch and did not reset its
handler for each item. An unsupported type after a supported item could reuse
the previous item's removal handler instead of merely failing to log.

Each worker now has an explicit handler map for its Kodi database. `BoxSet`
uses the existing `Movies.remove` collection path, which already removes set
artwork, movie membership and the Jellyfin reference without deleting its
movies. Unsupported or wrong-database types are skipped with a warning. Each
queue item remains balanced by the original `finally: task_done()` path. Errors,
stop requests and library-exit behavior keep their existing semantics.

Only `RemovedWorker.run` changes. All existing IPTV exclusions, bounded sync,
resume, native Dolby originals and playback code remain byte-equivalent outside
that method.

## Build and installation

This layer is composed by the newer
[short transaction release](../library-transactions/README.md); use its installer
for the current complete shared build. The commands below test or reproduce
this individual historical layer.

```sh
python3 integration/release/library-removal/test_worker.py
python3 integration/release/library-removal/test_install.py
python3 integration/release/library-removal/install.py --profile /PRIVATE/device.json
python3 integration/release/library-removal/install.py --profile /PRIVATE/device.json --apply
```

The worker tests reconstruct the pinned Jellyfin 2.2.0 source with the maintained
patches and execute the real patched worker using isolated queues/databases.
They cover unknown-first and unknown-after-valid items, every supported type,
wrong-database items, missing type/ID, handler failure, queue balance, stop/exit,
source drift and preservation of all other AST definitions. Installation tests
cover both profiles, idempotency, identity failures, source/receipt drift,
symlinks and protected network settings.

| Profile | Whole manifest SHA-256 |
| --- | --- |
| Local native PVR, 57 files | `f7e917da286f8b2c781a137a3ac2bffbbececbe756d2f72b0333576a26ae4a99` |
| Remote Jellyfin HTTPS, 61 files | `b085afd82f4e2a6f48a89036022044beb090900015e425c557b69ae7d560801f` |

The guarded installer composes pending predecessor layers, retains their
historical receipts, protects account/transport/network/CEC/keymap state and
refuses active or paused playback. One Kodi stop/start activates the update.
Use the printed transaction directory for rollback: while idle and Kodi stopped,
restore its recorded files and prior manifest together, remove only newly
created paths listed in `change-paths.json`, then restart and verify the former
profile. Never copy another box's userdata or boot media.

Remote installation and live checks are recorded in
[the October 8 update record](../../REMOTE-AM9-UPDATE-2026-10-08.md). Local output
is reproducible and prepared, not deployed. No actual user collection was
deleted to manufacture a test event.
