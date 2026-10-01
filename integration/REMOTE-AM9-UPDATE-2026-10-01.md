# Remote standalone-SD AM9 — October 1 update and UI verification

The owner authorized the OS update first, followed by search/Venom repairs, with
HDMI connected. Only the remote standalone-SD AM9 was updated; the original
hybrid SD/SSD appliance is not covered by this operation.

## OS layer completed

Installed official CoreELEC 22 Amlogic-no `nightly_20261001`, Kodi 22 RC1
revision `69b25a6585c47c6d7cc6e24aa3498beb288ea4f1`, kernel 5.15.196.
This remains a nightly, not a stable-release or unattended-update endorsement.

| Artifact | SHA-256 |
| --- | --- |
| Official update tar | `88ca13f6baa2b8295cc8ec3514737c32b20bcdf39891e10fe6789a03fd335c60` |
| KERNEL | `838db3af53f227e118d0422dd9180736318ac1a5675b5e5fa585247bf4f8c30a` |
| SYSTEM | `bcbfc38d612311e76e9574be0a87d5fda03892751f98537484e207bbbe930d9a` |

Build ID: `52ea38499abdf784bcddddd2d11debcc5c057ad1`.

The on-device download matched an independent official download. Compared with
September 29, the reviewed AM9 Pro stock DTB, Dolby loader, updater, CoreELEC
repository, Kodi addon interface manifests and CEC setting schema were unchanged.
Private fresh Kodi/config/SQLite/Tailscale and boot backups were copied off-box
before staging. The guarded SD-only updater checked the intended identity,
partitions, prior payloads, manual-update setting, backup, free space and Dolby
module. After reboot the exact live KERNEL/SYSTEM hashes matched; the same SD
mounts, Kodi, Tailscale and all 59 custom manifest entries were intact.

Future updates require the same candidate review and device-specific guarded
procedure, not a filename substitution in a historical updater. Do not use this
standalone-SD procedure on the hybrid box or flash Android for a Kodi UI issue.

## Actual search/UI findings

The earlier September 30 verification queried a plugin route, not the on-screen
keyboard. That evidence did **not** prove the user-visible search experience.
On October 1, after the OS update, the operator opened Arctic Search, selected
the keyboard, entered `A Quiet Place`, submitted it, waited for rendering and
captured the actual screen. Both owned films appeared under Movies; Venom
results remained separate. Repeating after the UI repair returned the two
owned results in approximately three seconds. The screenshots are private
deployment evidence, not committed library inventories.

The original broad outage was not reproduced for the correctly spelled title
after the update. The query `a quite place` had no result in the pre-update
plugin test: arbitrary spelling correction is not implemented. Do not attribute
all earlier search failures to that spelling without evidence.

Actual log/code faults were reproduced and repaired by the additive
[UI reliability overlay](release/ui-reliability/README.md): asynchronous Venom
grid focus, invalid rating predicates, and Discover's unrestricted ownership
index. After deployment, the on-screen search screenshot visibly showed the
first film's IMDb badge and the sequel's provider-neutral score. No invalid
rating-expression errors occurred in the fresh log. Cold category selection
placed focus on a populated channel card without an extra Right press.

Actual playback also exposed a hidden-window singleton leak: after Stop returned
to Home, reopening Venom was ignored. Revision 2 explicitly retires the remote
browser before handing playback to Jellyfin. It does not modify local PVR
handoff. Discover's measured popular-movie bridge/render work fell from the
previous logged 221 seconds to 3.627 seconds (whole plugin request 5.965 seconds).
These are separate live samples, not a controlled network benchmark.

## Acceptance boundary

The maintained regression suite, 74 repaired remote/local browser contracts,
four new overlay checks, and 18 search/installer checks passed. These are source
tests, not a substitute for device playback. The private execution record keeps
channel playback observations, screenshots, timings, protected settings checks
and rollback paths. This update does not claim every IPTV provider stream works,
that provider quality labels are accurate, or that all HDMI/audio/Dolby Vision
combinations were retested.

One live channel reached the hardware decoder; another advanced beyond 40
seconds using the HEVC hardware decoder in fullscreen. The hardware video plane
was absent from the composite screenshot, so this is decoder/timeline evidence,
not visual HDR/audio acceptance. The owner took over to watch TV before the final
revision2 stop/reopen cycle and Movies/Series UI checks. Those checks remain
pending; all further remote input and restarts stopped at handoff.

The source chain, exact-cohort installer and rollback procedure are preserved;
private credentials, device identity, live logs and recovery archives stay out
of Git. Local-PVR deployment of the new UI overlay is not yet accepted.
