# Shared AM9 responsiveness and acceptance

`am9-shared-20261008.2` is a paired, additive Kodi repair for the reviewed
local-PVR and remote-HTTPS AM9 cohorts. It retains their common worker,
cancellation, caching, pagination, exact playback identity and account-backed
favourites. Device identities, firmware, libraries and AV calibration are not
cloned. Source tests are separate from live-device and physical acceptance.

## Repairs

Pressing Kodi Home could hide Venom without calling its close handler. The
hidden browser retained the open flag indefinitely and ignored later launches,
even while Kodi RPC and SSH still worked. The common process loop now retires
that owner at idle Home. Temporary modal dialogs and active media preserve the
existing lifecycle, including local PVR fullscreen. A confirmed favourite change
can still finish before close; its completion is not starved by repeated Home
checks. The ordinary finally handler releases the singleton. Remote playback
still closes before HTTPS handoff; local Stop/poll/Open is untouched.
Launch also refuses an active modal dialog. Cleanup tolerates a window whose
`onInit` never ran, as can happen when an update prompt blocks its activation.
The Home service uses Kodi's supported `System.HasActiveModalDialog` condition,
so background refreshes and selection work pause while the keyboard is open.

Remote live switching now uses the same bounded handoff discipline already
present for local native channels: stop the old video, poll its departure in
the existing UI loop, then close the browser and resolve the exact Jellyfin
channel. Previously the new plugin could request a stream while the previous
one was still playing. The twenty-five-second stop deadline, Back/new-selection
cancellation and unexpected-player checks prevent a late replacement. No sleep
or provider call is added to an input callback, and no PVR lookup is introduced
on a remote box. This is orderly sequential switching, not a concurrency-limit
bypass. The local native-PVR handoff implementation is unchanged.

Combined search remembers a selected section. The Home service now chooses the
first available owned result once after a new committed query settles, waiting
for owned Movie/Show widgets and a nonempty owned row. Provider-only results do
not consume the reset. The thirty-second deadline retains the skin's fallback
on a library miss or outage. A queued `Control.Move` message selects the hidden
selector without changing keyboard focus, accessing native controls through
Python or making network requests. Explicit selector interaction, other
search modes, unchanged-query return, blank text and the deadline
are respected. Discover and Venom routes remain separate. There is no arbitrary
spelling correction or title-specific alias. The helper runs in the existing
one-second Home loop, not another service or background updater.

The read-only inventory also records a small skin-policy allowlist and semantic
menu routes alongside complete source/generated-menu hashes, global settings,
CEC, Up Next and account/transport evidence. Full URLs, search text and credential
parameters are omitted from semantic routes; the evidence remains private.

## One guarded update

Use the existing shared-AM9 private profile for the intended box. Stage the
`integration/release` and `integration/device-backup` trees with their relative
layout, plus ONLY that device's profile. Do not stage the repository-root skin.

```sh
python3 integration/release/ux-round/install.py --profile /PRIVATE/device.json
python3 integration/release/ux-round/install.py --profile /PRIVATE/device.json --apply
```

The default is read-only. The installer composes any pending October2 paired
repairs into the same transaction, rather than requiring separate patch runs.
Known original55, shared-local55 and shared-remote59 inputs retain the predecessor's
full manifest/profile guards; output is exact pinned local56 or remote60.
An unknown source, existing foreign helper, modified manifest or receipt fails
closed. Apply refuses active/paused playback, backs up changed files privately,
uses one Kodi stop/start and requires an empty final plan. No OS reboot,
network restart, firmware flash or user database replacement occurs.

The private transaction directory contains `change-paths.json`. Roll back while
idle: stop Kodi, restore the saved changed files and previous manifest together,
remove ONLY newly created files identified by that journal, then start Kodi and
verify the previous source cohort. Caught exceptions/interruption use transaction
rollback; power loss or forced process termination requires manual inspection.
Each box has its own receipt and acceptance record. A Git push is not fleet
delivery. An offline member remains pending.

For a new box, [CUSTOMIZATIONS.md](../../CUSTOMIZATIONS.md#new-device-versus-exact-cohort-update)
remains the commissioning entry point: correct official hardware image, pinned
base addons, unique identities and authentication, then reviewed release layers
and this combined update. This is not a blank-device image/bootstrap. Include
both [awake/OLED](../../device-policy/always-awake/README.md) and the appropriate
[remote startup policy](../../device-policy/remote-startup/README.md), and the
device's own network/remote-access recovery policy. Do not replay chat patches.

## Regression and live acceptance

```sh
python3 integration/release/ux-round/test_browser.py
python3 integration/release/ux-round/test_search.py
python3 integration/release/ux-round/test_install.py
python3 integration/check.py
python3 integration/release/verify-preservation.py
```

The browser suite covers both transport cohorts, unchanged worker/cancellation/
mutation core, deferred focus, empty lists, paging and Home departure. Search
tests cover debounce, incomplete rows, deliberate selection, timeout, unchanged
query return, delayed owned responses and the hidden-selector message. Installer tests cover reproducible outputs,
full final-manifest pinning, existing-helper rejection, idempotency and secrecy.
Known interim candidates migrate only after their complete manifests, receipts
and all three component pins validate; unknown edits are never forced through.
Actual remote-control acceptance must cover entry, Home→reentry, Back during
loading, A→B→A decoded playback, Stop→reopen, movies/series/episodes, typed queries,
manual section choice and screen saver. Separately test physical TV-off/on,
HDMI DV/FEL/audio, subtitle selection, intro and next episode.

Kodi window labels and a hardcoded Python-window ID are not reliable identities:
new windows can receive another ID while a cancelled old worker retires. Use the
observed Python window, actual focus/control content and GUI captures. Distinguish
an inactive browser owner, RPC/UI stall, changed Kodi PID and changed CoreELEC
boot ID. A successful Player.Open or codec info label alone is not decoded video.
Provider HTTP failures must not be reported as UI freezes or silently fixed by
changing the requested channel.

Kodi's [GUI API](https://xbmc.github.io/docs.kodi.tv/master/kodi-dev-kit/group__python__xbmcgui.html)
and [Window API](https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d4/d17/group__python__xbmcgui__window.html)
define the supported window/control operations. This layer adds no custom Kodi
binary or alternate IPTV identity route.
Kodi's [built-in GUI control commands](https://kodi.wiki/view/List_of_built-in_functions#GUI_control_built-in's)
document `Control.Move`; [the implementation](https://github.com/xbmc/xbmc/blob/master/xbmc/interfaces/builtins/GUIControlBuiltins.cpp)
sends the move through the GUI message path. The supported modal condition is
listed in [Kodi's boolean conditions](https://kodi.wiki/view/List_of_boolean_conditions).

An earlier device candidate used Python `Window.getControl(...).selectItem` on
the native skin selector and Kodi segfaulted during the expanded search test.
That candidate was withdrawn, not accepted as a successful repair. A subsequent
`SetFocus` candidate could leave the hidden selector on Venom; it was superseded
by the queued move and delayed-owned-row guard. The device remained SSH-accessible
and its CoreELEC boot ID did not change. Preserve these failures in acceptance
history; a final manifest is not evidence that every candidate was stable.

## Deployment status

The remote sixty-file output is installed and the guarded follow-up plan is
empty. The original/local fifty-six-file output reproduces from its private
saved baseline; live deployment remains pending because its network is
unreachable. Both profiles use the same generic repairs, not cloned settings.
No firmware upgrade or CoreELEC reboot occurred in this round.

The feature comparison found all six Home/search node definitions, generated
Arctic menus and Up Next source/settings equal to the recorded local device.
The rating XML difference is covered by the pending paired local release.
Account, HTTPS versus local PVR transport, display whitelist and remote-only
unused-PVR startup behavior are intentionally different. Awake/OLED/CEC policy,
keymaps, AV settings and remote access were retained on the deployed box.

| Feature | Included in both derived builds | October 8 acceptance |
| --- | --- | --- |
| Background network worker and superseded-request cancellation | Yes, unchanged common implementation | Both transport contracts; live Back during a request |
| Bounded source cache and local 80-card pagination | Yes | Movies grid and UI page changes; remote next 160-title chunk |
| Account-backed favourites | Yes, unchanged mutation/identity policy | Regression coverage; real selector choice preserved; no new favourite mutation |
| Venom owner release after Home and ordered playback handoff | Yes, local native path retained and remote exact-ID path brought into the same stop/poll discipline | Home exit, clear flag and reopen; popup guard; decoded playback recorded separately |
| Empty-list/deferred-focus handling | Yes | Regression coverage and categories/grid navigation |
| Owned search separate from Discover/Venom | Yes | Keyboard submitted full/partial title, spacing variants and a show; owned section selected |
| Delayed search selector reset | Yes | Slow response, manual alternative section, next query resetting to owned results |
| Rating visibility and bounded Discover ownership lookup | Yes | Corrected XML/lookup regressions; actual search capture shows IMDb corner badges |
| Next episode, intro, subtitles and DV7/FEL policy | Existing code/config retained | No new physical AV/episode-end acceptance in this round |

Typed queries `Office`, `A Quiet Place`, `Quiet Place`, `spider man` and
`spiderman` selected their owned rows without a restart. A deliberate Venom
selection remained selected until a new query. The keyboard stayed open when
a Venom launch was attempted beneath it. Home→Venom reentry took about one
second in the recorded check. Final typed searches settled in roughly five to
eight seconds over this network; these are bounded observations, not a WAN
performance guarantee. Some catalogue requests still wait on server/network
timeouts even though Back and the Kodi interface remain usable.
One late post-retune search recheck returned no cards after a timeout. The same
signed-in `Users/.../Views` call timed out at ten seconds outside Kodi, then
recovered for both Home and independent read-only client headers. Retyping
`Quiet Place` selected the owned `A Quiet Place` row in about five-and-a-half
seconds without restarting Kodi. This intermittent endpoint stall remains a
backend/network reliability limit, not a fixed-by-selector claim; the helper
does not bypass fresh view authorization or persist a cross-user catalogue to
conceal it.

The direct replacement test before the ordered handoff took about thirty-four
to thirty-six seconds to report the next item, with stale decoder state and a
later input timeout; it was not accepted as decoded playback. After the repair,
an A→B→A test without manual Stop reached the correct fresh decoder dimensions
for every target in about fourteen, sixteen and seventeen seconds. The final
Al Jazeera leg advanced from thirteen to ninety-six frames over three seconds,
with zero decoder/drop/hardware errors. Its provider label says eight-K, but
the actual stream was H264 1920×1080 at twenty-five fps. BBC Arabic opened as
720×576; its frame counter did not advance in the subsequent short sample, so
sustained playback on that source remains unproven. Menu/input RPC and Kodi PID
remained responsive/stable. These timings are individual observations, not a
controlled two-times-faster benchmark or provider availability guarantee.

The final follow-up Home input returned normally after test Stop. Do not treat
remaining provider stalls, empty EPG, or a late Jellyfin player-not-playing
callback during retune as a repaired source or a CoreELEC crash. No channel was
removed or substituted to make acceptance pass.

The final sixty-file snapshot was copied off-device with matching SHA256.
All tracked sources, four selected bundled dependency members, nine SQLite
quick checks and the device's own ConnMan/regdomain/Tailscale recovery state
passed verification. Final inventory has zero source drift, no failed services
and unchanged protected/account/AV/CEC/menu settings. The black screensaver
reported active with DPMS false and SSH/Kodi still reachable. Test playback
was stopped and the box was left running at Home. The targeted suites passed
121 browser/transport, seven search and four installer tests; the full clean-
source integration check and 415-file preservation check also passed, with
the five existing optional integration skips unchanged.

The first series browse returned its flat remote episode list. A test harness
mistakenly treated that list as a season selector and attempted one episode;
the provider playback failed and displayed Kodi's normal error dialog. This
was not a CoreELEC hang, and was not accepted as successful VOD playback.
The corrected browse-only check covers the list without changing the route.
Physical TV-off/on, complete hand-held remote typing and HDMI DV/FEL/audio,
episode-end/intro/subtitle behavior still require onsite acceptance.
