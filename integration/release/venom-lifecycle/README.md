# Paired Venom window lifecycle repair

`am9-shared-20261008.5` composes the [Home entry repair](../venom-entry/README.md)
and all earlier paired shared/UX/performance layers. Local native PVR and remote
exact-Jellyfin transport retain their separate private account/network profiles.
This is not firmware, a cloned userdata tree or an automatic fleet updater.

## Additional defect and repair

Actual Arctic-menu entry exposed a gap that direct Browser launches had not
proved: after Home, the owner flag could clear yet an old Python window remained
the active interface. Kodi RPC/SSH stayed responsive; neither Kodi nor CoreELEC
crashed. Merely clearing the open flag was insufficient acceptance.

The browser now avoids navigating to a previous window when Home has already
hidden it. Final cleanup only leaves the native Venom hub; it does not override
later Search, Discover or fullscreen navigation. An explicit
Home over background video also retires the browser without stopping that
player. Fullscreen video and temporary modal dialogs do not trigger retirement.
The same narrow changes are applied to both transport sources.

Native `Window.close()` navigates to the previous window; it is not a harmless
hide operation. When Home has already deactivated the Python browser, normal
cleanup must **not** call that native close again and resurrect old history.
The final repair gates that call on current Home state. The hub also checks its
owner property **before** queueing its automatic script launch. Without that
guard, Back returned to the hub and queued another browser after the old owner
was released. The first two live candidates failed repeated navigation; neither
is an accepted release. The installer migrates only those complete pinned remote
candidates after full source, receipt and identity validation. Unknown
interim sources still fail closed.

The network worker, bounded optional-favourite lane, cancellation/generation
policy, confirmed-mutation completion, local PVR stop/poll/open and remote
exact-ID stop/poll/resolve remain unchanged. No force-clearing another owner,
UI-thread sleep, resident watchdog, provider-limit change or Kodi binary patch
is introduced. A provider playback failure remains distinct from UI failure.

## Rebuild, install and rollback

The commands below reproduce this historical layer. For the complete current
release use the [short transaction installer](../library-transactions/README.md)
rather than replaying historical patch commands:

```sh
python3 integration/release/venom-lifecycle/install.py --profile /PRIVATE/device.json
python3 integration/release/venom-lifecycle/install.py --profile /PRIVATE/device.json --apply
```

Stage `integration/release` and `integration/device-backup` in their relative
layout, with only that box's private shared-AM9 profile. The plan composes any
pending predecessor release. It validates full source/manifest, hardware,
account/server/transport and parent receipts, protects CEC/keymaps/network,
refuses active/paused playback, journals privately, uses one Kodi stop/start and
requires an empty final plan. Unknown/partial sources require review, not force.

| Cohort | Inventory | Whole manifest SHA-256 |
| --- | --- | --- |
| Local native PVR | 57 files | `0e575a1c026a288ec5c3002748b507116f462a5481a52339d55fc6b9b9bfece1` |
| Remote Jellyfin HTTPS | 61 files | `5e401cebbaea1d63e8971762f1ddc0010c16d6ccf5065c4fbe687401a8a7e0a1` |

Retain the printed transaction directory. While idle and Kodi stopped, restore
its recorded changed files and prior manifest together; remove only newly
created paths in `change-paths.json`; start Kodi and verify the former cohort.
Caught errors use transaction recovery. Power loss/SIGKILL needs inspection.
Do not restore another box's settings, network, database or boot media.

```sh
python3 integration/release/venom-lifecycle/test_browser.py
python3 integration/release/venom-lifecycle/test_install.py
python3 integration/check.py
python3 integration/release/verify-preservation.py
```

The 128 paired browser contracts include background-video Home retirement,
fullscreen/modal preservation, the hub guard and executable main-loop teardown:
cleanup must never override later navigation. Existing critical-mutation,
stale-request, pagination, favourite and
transport contracts are rerun. Full saved-cohort builders reproduce local57 and
remote61 outputs and a no-change second plan. Source tests do not replace device
acceptance or prove physical HDMI/HDR/audio output.

## Deployment and acceptance

Remote deployment and actual transition results belong to
[the October8 OS/UX record](../../REMOTE-AM9-UPDATE-2026-10-08.md). Local output
is prepared, not deployed. Their firmware, account and network differences stay
intentional. Git publication does not automatically deliver an offline update.

Acceptance must include the visible Home tab, categories/grids, Back during
loading, Home→reentry with/without background playback, same-channel selection,
different-channel retunes, live→owned movie and owned movie→live, stop→reopen,
and stable Kodi PID/restart count/OS boot ID. Require advancing fresh hardware
frames, not merely Player.Open success or provider resolution labels. Physical
TV-off/on, DV/FEL/JBL output and long-run WAN/provider outages remain separate.
