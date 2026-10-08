# Paired AM9 performance release

`am9-shared-20261008.3` follows the [shared UX repair](../ux-round/README.md).
It is one common feature release with exact local-PVR and remote-HTTPS outputs,
not a firmware image, account clone or automatic fleet updater.

## Changes and limits

Venom's periodic shared-favourite read previously occupied the same replaceable
worker as category and grid loading. Navigation could queue behind its current
HTTP read even when the old generation was cancelled. `favorite_refresh.py`
gives this optional read one separate bounded `LatestWorker` lane. The existing
foreground worker, critical favourite-write ordering, generation checks,
network deadlines and local/remote playback handoff remain intact.

The optional lane waits two seconds after initialization, starts only while the
foreground is idle, allows one active read and one replaceable pending job, and
starts at most once per thirty seconds. Navigation does not wait for it.
Mutation and close invalidate its generation; a pre-mutation result cannot
overwrite confirmed new stars, and late closed-window results are not applied.
An error preserves the last known keys and reports the existing offline status.
There is no new resident service, thread per key or infinite retry queue.

Favourite-key reads retain Path/ChannelInfo and exact item identity, but disable
images, user-data DTOs and total counts they never consume. The actual favourite
page still requests its full artwork/user-data response. Summary and full-page
caches are distinct; one cannot silently replace the other. Existing 500-item
paging, 10,000-item safety limit, current-user filtering and exact mutation
confirmation are retained.

The Home client's authorized-library scope lookup sets the supported
`IncludeExternalContent=false` option on Views. This classification read does
not need the Live TV/channel-folder DTO. It still queries the current user's
authorized libraries; it neither adds a cross-user cache nor changes item
permission checks, Home ordering, search matching, ratings or playback policy.

## Build, update and rollback

Stage `integration/release` and `integration/device-backup` in their relative
layout, with only the intended box's private shared-AM9 profile. Use this latest
installer, which composes a pending earlier shared/UX release in one idle
transaction:

```sh
python3 integration/release/performance/install.py --profile /PRIVATE/device.json
python3 integration/release/performance/install.py --profile /PRIVATE/device.json --apply
```

Full source-manifest, hostname, hardware MAC, account, server, transport,
network/keymap/peripheral inputs, helper and receipt guards fail closed.
Unknown/partial cohorts require review, not a forced install. The predecessor
UX receipt remains historical evidence; the new performance receipt describes
the new manifest. Rerun the latest installer to verify an empty final plan.

| Cohort | Complete output inventory | Whole-manifest SHA-256 |
| --- | --- | --- |
| Local native PVR | 57 entries | `857e91d76f7cd41782fa7b73e56e0fcf8ecfb2d185afee09e4174015ec78d867` |
| Remote exact Jellyfin HTTPS | 61 entries | `f89430cd3d0620cbe8186d60fb88b7b684d24eaaaf07218823a71239aff62678` |

Apply refuses active or paused playback, journals originals privately, performs
one Kodi stop/start and checks readiness. It does not reboot CoreELEC, change
boot media, restart networking, restore a database or change AV calibration.
For rollback, keep the printed transaction directory: while idle, stop Kodi,
restore its recorded changed files and prior manifest as a set, remove only
new files identified by `change-paths.json`, start Kodi and verify the prior
cohort. Caught failures use transactional recovery; power loss/SIGKILL needs
operator recovery. Never roll back by copying another box's userdata.

For blank-device commissioning, retain the [new-device procedure](../../CUSTOMIZATIONS.md#new-device-versus-exact-cohort-update),
including unique identities, AV settings, always-awake/OLED policy, remote
startup and private network/backup provisioning. This installer is additive.
Future addon updates must rebase both transports and these common features.

## Acceptance on October 8

Both complete saved cohorts reproduce pinned outputs, preserve private
account/server/transport files and are idempotent. The remote box received all
six changes and has zero source drift. The original/local box is unreachable:
its fourteen-write composed update is prepared and tested, **not deployed**.

On the actual remote Kodi interface, movie/show category grids loaded in about
2.0/2.5 seconds after selection, pagination and the next server chunk worked,
series episodes opened, Back during loading cancelled cleanly, and Home cleared
the owner flag before reentry. Warm live-category and first-grid readiness were
about 0.39/0.38 seconds. These are observations on that device/network, not
universal speed guarantees. Optional reads logged approximately 0.65–0.86
seconds separately, without occupying foreground navigation.

Keyboard-submitted Office, full/partial Quiet Place and Spider-Man spacing
variants returned owned results with the correct source selector. Deliberate
Venom source selection remained selected until the next committed query.
There was no unexpected Kodi restart or CoreELEC reboot during these checks.
A real favourite-menu remove/add round-trip was confirmed by the server and
visible star, restoring the exact original account state. A sampled channel
opened in 7.8 seconds and decoded 1920×1080/25 fps with advancing frames and no
drop/hardware-error count. Its provider name said 8K; this is not proof of 8K.
Stop returned Home with the owner flag clear. The earlier switching acceptance
remains separate; upstream channel errors, longer-run buffering and physical
HDMI DV/FEL/audio are not proved by this sample or by grid/RPC success.

The final private off-device snapshot verifies all 61 pinned sources, the new
and parent receipts, four bundled-dependency probes, nine SQLite quick checks,
and that box's network/regdomain/Tailscale recovery state. No private archive,
account identifier or credentials are included in Git.

```sh
python3 integration/release/performance/test_browser.py
python3 integration/release/performance/test_refresh.py
python3 integration/release/performance/test_queries.py
python3 integration/release/performance/test_install.py
python3 integration/check.py
python3 integration/release/verify-preservation.py
```

The browser suite runs 123 contracts across both transports, including a real
blocked optional worker with foreground navigation completing independently.
Other tests cover delayed/lost/stale results, close, mutation invalidation,
minimal DTOs versus full artwork, bounded paging, whole-cohort drift, existing
foreign helpers/receipts, source reproduction and private receipt boundaries.
Shared worker, render, cancel, identity and playback AST contracts are preserved.

The companion [server/web/Proxmox optimization](../../server/performance/README.md)
uses native configuration plus a small version-pinned Enhanced patch; it is not
an APK or a new Jellyfin server-core fork.
