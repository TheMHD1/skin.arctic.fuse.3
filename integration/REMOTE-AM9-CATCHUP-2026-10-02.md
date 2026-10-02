# Remote AM9 remaining issues and parity checklist — October 2

This records **all known outstanding remote-box acceptance items** from the
search/Venom/Arctic discussion, including older speed/switching complaints. It
does not assert that undiscovered faults are covered. The remote box is offline
at preparation time; source tests and server API checks are not device acceptance.

## What the saved comparison establishes

Compared the September26 original-device audit with the remote October1 OS audit.
All compared general Kodi settings match except the display whitelist, which is
physical-display dependent. Home/search shortcut hashes match. Jellyfin segment/
intro/stream/sync settings and Up Next settings match. Remote Native mode stays
off globally; the separate layout-gated original-P7 transport remains opt-in.
The differing browser/API/playutils source files are the documented remote
cohort, not evidence those features were omitted. Platform-matched binary addons
on the remote box are newer; do not downgrade them merely to match a local list.

This is a **saved** comparison, not a fresh read of either appliance. Compare live
settings/source hashes again before deployment. Preserve each device's own account,
host keys, Tailscale state, Wi-Fi, network route, display calibration and library
scopes. Never copy the original hybrid-SD/SSD boot configuration to standalone SD.

## Shared repair baseline — owner requirement

The original/local AM9's maintained repairs are the baseline. The remote build
must carry every applicable repair, with only explicitly reviewed account,
network/transport, hardware/version adjustments or genuinely new fixes. An
independent reduced set of "remote repairs" is not acceptable. The R6 builder
already derives both Venom variants from the same common source and patch stack;
R7 Home/search and search-priority use the same payload for both cohorts.

Saved-source comparison additionally found all seven Home companion source files
equal, all25 request/discovery addon files equal before the October1 additive
bridge repair, and identical Jellyfin player, library, downloader, helper/utils
and service code. This establishes inherited playback/intro/next-episode and
sync repairs at that saved point, not proof of current physical behaviour.

| Shared repair family | Preserved implementation and remote requirement |
| --- | --- |
| Home/resume/latest/ratings and separated library search | Same Home companion, R7 and search-priority source; each device keeps its own account/scopes |
| Discover/request actions, duplicate/error guards and trailers | Same maintained KodiSeerr/Arctic patch stack and trailer dependencies; authenticate per device |
| Player, intro/segments, next episode, subtitles and sync-loop filtering | Same consolidated Jellyfin2.2 repair stack and shared player/library/downloader code; retain Up Next configuration |
| Venom workers, cancellation, bounded cache, category-first UI and shared favourites | Common browser/shared-favourites source; remote overlay changes catalogue/playback access, not these guarantees |
| Seeking/audio/OLED/awake behaviour | Same ±30-second keymap/helper and capability-appropriate settings; merge the device's own CEC profile and display modes |
| Native DV/original quality | Same quality objective; local Native path versus separately approved remote manifest/private route with HTTPS fallback |
| Backups/update preservation | Shared exclusion/root-selection policy where applicable; device-specific worker, boot media and credentials remain private |

New October1–2 generic improvements (bounded owned Discover index, valid rating
predicates/defaults, additional empty-list focus guards and explicit network
backup coverage) are **shared candidates**, not intended permanent differences.
Their recorded states remain: reviewed remote r2 deployed, October2 remote layer
staged; the later [shared AM9 audit/release](release/shared-am9/README.md) now
provides a reviewed local port and paired guarded plans. Exact original55 and
remote59 private fixtures pass; neither paired layer has been deployed. The remote
browser close-before-HTTPS playback fix is transport-specific: preserve the
local Stop/poll/Open PVR handoff that already passed local acceptance.

Before declaring remote parity complete, use a current local inventory plus the
maintained repair sources, classify each fix as identical, reviewed equivalent,
new/shared pending, or justified device-specific, and resolve unexplained gaps.
Test actual behaviour as well as hashes. The offline preparation does not satisfy
that final live acceptance gate.

## Outstanding work, in execution order

| Area | Current evidence/status | Live acceptance required |
| --- | --- | --- |
| Venom entry freeze/lag | October1 activation deadline and playback singleton fixes deployed; extra empty-container focus repair staged October2 | Cold entry, repeated exit/reentry, top-button section switching; inspect timed logs and GUI focus, distinguish stalled requests from Kodi crash |
| Channel switching and Stop/reopen | Local device previously accepted; remote HTTPS route differs; final r2 stop/reopen test was interrupted by viewer handoff | Play→Stop→reopen and A→B→A, same-channel reopen; measure request/first decoded frame and UI responsiveness without altering provider limits |
| Movies/Series | Remote160-title paging source tests pass; full device UI sequence pending | Provider categories, page/filter/recent sorting, show→episodes→Back, actual movie and episode playback |
| Arctic slowdown/Discover | Owned-root bridge repair deployed October1; measured bridge sample3.627s versus prior221s, not a controlled benchmark | Cold/warm Home, Search and Discover; correlate slow requests/errors with UI timestamps, confirm no repeated catalogue-wide work |
| Library search | Current remote account finds both owned films for `Quiet Place` and `A Quiet Place`; regression added; October1 screenshot proved only the latter | Type and submit both queries in actual Arctic keyboard, verify owned Movies first and separate Discover/Venom rows, capture screenshots |
| Custom Live TV groups | October2 server readback returned302 provider categories and **zero curated collections for both accounts**; stored1413 curated IDs match none of11841 current native live-channel IDs | Repair stale server collection identities using guarded exact source/channel mapping, retain rollback and user choices; verify custom groups pinned above provider groups on remote UI |
| Names/artwork/favourites | Historical server naming/artwork/shared-ID repairs documented; current device rendering pending | Verify meaningful names, Arabic glyphs, grid logos and authenticated add/remove favourites; confirm same-account results elsewhere without resetting user choices |
| Wi-Fi recovery/backup | Canada hint installed October1; same SSID roamed to5GHz with960+Mbps negotiated rate; user confirmed playback recovered. Root-selection migration staged | Verify current band, no viewer-interrupting reboot solely for a test; at next authorized reboot verify native regulatory loader; inspect new snapshot and copy off-box |
| Other shared features | Saved Home rows, segment/next-episode settings, ±30s seek, audio passthrough, always-awake/black OLED policy agree | Current Home refresh/resume, next episode prompt/auto-play, intro button, trailer, seek both directions, subtitles and TV-off/on when practical |
| Remote original DV/audio | Layout-gated native selection/read acceptance; October1 P7/FEL decoder channels, DV output and TrueHD7.1 observed with normally advancing timeline after5GHz change | Representative original/HTTPS-fallback playback; onsite LG/JBL confirmation when available; do not weaken compatibility or identity gates |

No new firmware update is part of this catch-up. The remote standalone SD is
already on reviewed20261001/Kodi22RC1. Keep manual-update policy and exact source
guards. No custom native phone APK or full server-library scan is proposed.

## Prepared payload and recording rule

[Remote catch-up source/installer](release/remote-catchup/README.md) changes four
files only, after the existing r2 overlay. Private saved-cohort verification is
complete; installation and UI/playback/snapshot acceptance are pending until the
box is online. Keep credentials, raw logs, screenshots, real profiles and recovery
archives in the private operations record. After each acceptance, record its
timestamp, installed source hashes, rollback location, exact test and result.
Update this checklist rather than marking a whole area fixed from one RPC success.

The later October2 round confirmed the awake policy's six settings and eight
CEC overrides match in the live original and saved remote configurations. This
is not a missing transfer; remote live load/TV-cycle verification is still needed.
Both accounts still have zero curated server collections. A promotion attempt
shrinks the native set to34 channels, triggering the publisher's200-channel
minimum and a failed channel-checker result. Retain that loss guard until full
exact identity rebinding is repaired; do not publish the shrunken set as success.
