# Remote AM9 CoreELEC update and Venom navigation repair

The remote AM9 was updated from the October 6 nightly to
`22.0-Piers_nightly_20261008` using the normal CoreELEC update mechanism on its
standalone SD card. Its account, Wi-Fi, restricted remote access, audiovisual
settings and shared integrations were preserved. The Venom Home tab required a
separate skin repair; firmware alone did not fix its disabled state.

The shared release is `am9-shared-20261008.7`, built on the published
`f8beb6d769a2b338fde5edd8b2eec7f6b8e79a6d` source. It composes the existing shared,
UX and performance layers plus the Home entry, browser lifecycle, collection
removal and short-sync-transaction repairs.
The remote profile is installed. The local native-PVR profile is prepared, not
deployed. A Git push does not distribute changes automatically to another box.

## Firmware and boot media verification

The [official Amlogic-no CoreELEC 22 nightly directory](https://relkai.coreelec.org/?dir=Amlogic-no/ce-22)
provided the October 8 archive. This is a nightly release, not a stable release.
The platform remained `Amlogic-no.aarch64`, with build ID
`5b2970d67edf13285386d9588abdb40a5fca8bd6`, kernel `5.15.196` and Kodi 22 RC1.

| Artifact | SHA-256 |
| --- | --- |
| Update archive | `493d15b5562e25ce727a199ef2f3898e62cb6f8a5948d04f9db2c4a071e03f27` |
| Installed KERNEL | `0d20deadfa3243a17df1fd3254e6076f432772bbc9c6793f17b364bfd9b4f43b` |
| Installed SYSTEM | `4fb5d98fc2f87da0b876720af69099515482d4284b5d21086b482c2bd5fdb415` |
| Retained AM9 Pro device tree | `0716528f0d5a8927bc3ddc4d92a1d2167249ef40d5ce96a3674a80528b30e804` |
| Retained Dolby module | `f6c26659a255447685ceac9441e399c999b1fae9c6435c48d70e14a14dd7f8f7` |

Before staging, the updater checked the appliance identity, standalone SD layout,
partition identities, former kernel and SYSTEM hashes, idle playback and a fresh
consistent backup. Both embedded archive checksums passed. Sixty selected OS
contracts were compared, including addon interfaces, CEC definitions and the
Dolby loader. The updater bytecode was unchanged apart from its Python cache
header. The device tree matched byte for byte, and the bootloader updater matched
the previously reviewed version.

The archive was staged atomically for the normal updater and the box rebooted
once. No raw flashing, formatting, Android replacement or host reboot was used.
This procedure is **not** permission to apply the same standalone-SD updater to
the local SSD/SD hybrid appliance.

After boot, kernel and SYSTEM matched the approved archive, the update directory
was empty, the Dolby module was loaded and no systemd unit had failed. The
preexisting 4,020 source-file hashes were unchanged by the OS update. All 61
integration manifest entries and the account, transport, menu, CEC, keymap,
awake/OLED and audiovisual contracts matched the pre-update capture. Canadian
Wi-Fi regulation and the 5 GHz connection remained intact.

The private backup includes the box's own network and remote-access state,
bundled dependency sources and nine SQLite databases checked for consistency.
Boot/configuration archives were also transferred off-device and checksummed.
The final integration snapshot was verified both on-device and off-device,
including all 62 source entries, seven integration receipts, four dependencies
and all nine consistent databases. The original pre-update snapshot remains
available off-device separately.
Device addresses, hardware identifiers, credentials, playback inventories,
screenshots and raw logs stay outside this public repository.

## Why Venom was disabled

`Home_ControlList_Item_1107` required `System.HasPVRAddon + PVR.HasTVChannels`.
The remote HTTPS profile intentionally does not populate Kodi's native PVR
database, so its Venom tab was disabled even though its addon and server
categories worked. Direct script launches bypassed this gate and did not prove
the Home menu worked.

The [Home entry overlay](release/venom-entry/README.md) requires the enabled
Venom addon and configured Venom tab for that route. An ordinary native PVR tab
still requires PVR and channels. The source is pinned, the change is confined to
one predicate, and 32 boolean combinations are tested.

## Why repeated navigation reopened an old browser

Two lifecycle paths interacted with Kodi's window history:

- Native `Window.close()` navigates to the previous window. Calling it after
  Home had already hidden the browser could navigate away from Home again.
- Returning to the Arctic Venom hub invoked its unconditional `RunScript` onload.
  That script could run after the departing browser released its singleton,
  opening another browser without a new user selection.

The [Kodi Window implementation](https://raw.githubusercontent.com/xbmc/xbmc/master/xbmc/interfaces/legacy/Window.cpp)
establishes the native close behavior. The automatic relaunch was identified by
the actual Arctic-menu sequence and its corresponding browser-launch logs.
Kodi RPC and SSH remained responsive during these failures; the box had not
crashed or suffered a CoreELEC hang.

The [lifecycle overlay](release/venom-lifecycle/README.md) skips native close
when Home is already active. Its hub onload checks that the browser owner is
empty **before** queueing another launch. Home also retires a browser over
background video without stopping that video. Fullscreen and temporary modal
dialogs retain their normal behavior. Cleanup only leaves an active Venom hub;
it must not override later Search, Discover or fullscreen navigation.

The first two live lifecycle candidates failed repeated navigation and are not
accepted builds. The installer recognizes only their exact whole manifests,
browser hashes and receipts for migration to the final source. Unknown or
partially modified devices fail closed.

## Live acceptance

The final `.7` build passed the following actual-control checks on the remote
appliance. The normal Arctic Home entry was used for navigation and playback;
catalogue-specific tests also exercised direct section launches. Decoder checks
required at least three seconds of sustained new frames, allowing the old
codec's counter to reset during a handoff. An accepted API request alone was
not counted as playback. The private TCP diagnostic reader was also corrected
to parse concatenated Kodi announcements and UTF-8 fragments; that diagnostic
fix was not treated as a remedy for the real SQLite stall.

| Flow | Acceptance |
| --- | --- |
| Actual Home tab; three Home→reopen→Back cycles | Passed; browser ownership cleared; no spontaneous relaunch |
| Live/movie/series categories and grids | Passed; 339 live groups, 45-card sample channel grid, 80-card movie/series UI pages |
| Back during a fresh request, then reopen | Passed; cancelled work did not steal the new window |
| Three Home/reopen cycles over ongoing live video | Passed; video remained active and interface responsive |
| Select the already playing channel again | Passed; new decoded frames and responsive controls |
| Live→owned 4K movie→live | Passed on final build |
| Live channel A→different channel B→A | Passed on final build |
| Stop→Home→reopen | Passed on final build |
| Venom's own movie→live | Passed; advancing 1920×804 movie frames |
| Venom series episode→live | Both formerly failing samples played and returned to live after server freshness repair |
| Shared favourite context menu, toggle and restore | Passed; original state restored and completed favourite grid populated |
| Owned title search / keyboard modal launch guard | Passed after the OS update; final `.7` movie test also used typed search |
| Movie UI page 2 and next server page; series episode grid | Passed after the OS update; final `.7` basic grids repeated |

Search accepted full and partial titles, punctuation/spacing variants and shows.
The owned section was selected when it had results; a deliberate alternative
section stayed selected until the query changed. A private screenshot confirmed
the owned movie results and rating badges, not merely plugin/API output.

Final `.7` sample grid loads were approximately 0.9 seconds for live and 2.1–2.6
seconds for movie/series after category selection. Normal menu entry including
remote calls was about 3.1–5.2 seconds. Sample live starts/retunes ranged roughly
9–21 seconds; the 4K owned movie started in about 14 seconds. Representative GUI
RPC checks including SSH overhead took about 0.36–0.47 seconds. These are
bounded samples, not percentile or provider-wide performance guarantees.

No unexpected Kodi restart, CoreELEC reboot or multi-minute shutdown stall
occurred in that final transition matrix. Readback found exactly six reviewed
source/manifest changes and no changes to account, network, AV, CEC, keymap,
update-pin or dependency settings. The remote62 source manifest had zero drift
and the current installer returned an empty plan. Local58 was reproduced from
the complete saved cohort plus its pinned unmodified movie-model source, but
has not been deployed or live-tested.

An isolated 200-commit WAL probe on the device's SD card measured a mean 3.65 ms,
p95 5.42 ms and maximum 7.63 ms per simple commit. It did not open a Kodi database.
Per-item commits can add bulk-sync I/O; the probe establishes a modest device
commit budget, not a full-library throughput benchmark. The final build passed
the complete integration checker, the paired builders and the original-lock
reproduction/repair tests.

Existing missing optional studio-logo resources and early attempts to focus an
empty category control still appeared in logs. Completed categories obtained
focus and the tested controls worked. One sampled channel had a transient
decoder starvation warning before normal frames advanced. These were not
silently relabelled as clean logs or fixed provider behavior.

Provider errors are distinct from a blocked interface. A successful sample does
not establish that every provider stream works indefinitely. Physical DV/FEL,
HDR and JBL passthrough confirmation still requires the connected display and
receiver; remote software checks do not certify their output.

## Jellyfin collection removal

Startup also exposed an existing Jellyfin for Kodi `RemovedWorker` dispatch bug.
A removed `BoxSet` had no handler and caused `UnboundLocalError`. An unknown
type after a valid item could reuse the prior item's handler. The shared
[collection removal overlay](release/library-removal/README.md) uses an explicit
handler map for each database and routes collections to the existing supported
set-removal method. Unsupported types are skipped with a warning, and queue
accounting and stop/error semantics are preserved. No user collection was
deleted to manufacture a test event.

## Playback shutdown and SQLite contention

Earlier movie→live acceptance also caught a separate, intermittent multi-minute
stall. Native traces showed Kodi's main thread waiting for player-shutdown
jobs, while its settings-write job waited in SQLite. A Jellyfin update worker
was in an HTTPS read. This is distinct from the menu lifecycle bug: SSH remained
healthy, but Kodi's GUI/RPC could stop responding. Subsequent samples recovered
without a reboot; that alone was not treated as a fix.

The [short transaction release](release/library-transactions/README.md) addresses
confirmed unsafe source boundaries: sync workers now commit each completed
item before subsequent queue/GUI waits, and collection pages are fetched before
its first SQL write. Real isolated SQLite tests reproduce the original writer
block and verify the new boundaries. The exact network call during the observed
stall was not captured, so identifying it specifically as a collection fetch
remains an inference. No Kodi binary, server fork, database schema, journal
policy or lowered busy timeout was introduced.

## Server episode freshness

The extra episode checks exposed a separate server-side freshness defect. The
[maintained revision-aware exporter](server/VENOM-SERIES-FRESHNESS.md) now
refreshes links when active backend episode IDs change, instead of retaining
them for the weekly success cooldown. Both sampled series were refreshed by
the generic exporter, not manual URL edits. Both formerly failed episodes then
played with advancing frames: one at 1280×640 in 12.9 seconds, and the original
sample at 1280×544 in 10.0 seconds. Each switched back to live TV in about
12 seconds without a Kodi restart.
Failure-dialog acknowledgement, Home return and subsequent owned-movie→live
playback also succeeded. The remaining catalogue is being handled by the
existing bounded timer; not every provider episode has been stream-tested.

## Rebuild and rollback

Use [the latest shared installer](release/library-transactions/install.py), which
composes all preceding shared layers, rather than replaying historical edits:

```sh
python3 integration/release/library-transactions/install.py --profile /PRIVATE/device.json
python3 integration/release/library-transactions/install.py --profile /PRIVATE/device.json --apply
python3 integration/check.py
python3 integration/release/verify-preservation.py
```

Retain that device's private profile and the transaction directory printed by
the installer. It validates identity, account, transport, full source and
historical receipts; it refuses active or paused playback and uses one Kodi
stop/start. Firmware and integration rollback are separate operations. Restore
only the affected appliance's own recorded boot or integration files while
idle; never copy another box's account, network, database or boot layout.

The [updating guide](UPDATING.md) and [customizations index](CUSTOMIZATIONS.md)
identify the current build layers. Unrelated preexisting Dolby reconciler edits
were not included in this release.
