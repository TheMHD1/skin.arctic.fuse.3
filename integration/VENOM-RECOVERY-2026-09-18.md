# Venom playback and category recovery — September 18, 2026

## Current fix: playback rejected as a favourite mismatch

The message “No exact Jellyfin match yet. Favourite unchanged” could appear
while playing a channel, not only when changing favourites. The browser's
playback lookup required both the Jellyfin channel name and number to equal
Kodi PVR's local values. Those independently maintained numbers can differ.
Ordinary MBC 3 was Jellyfin channel 5842 but Kodi PVR channel 3896; its higher
quality variants happened to match, hiding the general failure in earlier tests.

`plugin.video.venom.tv/browser.py` now keeps the native PVR fast path when there
is exactly one matching name/number. Otherwise it delegates the selected
channel's exact, validated Jellyfin item ID to Jellyfin-for-Kodi's existing
Live TV playback route. This covers missing, renamed, renumbered and ambiguous
local entries without fuzzy matching or changing favourites. Generic lookup
errors no longer misleadingly describe every failed action as a favourite edit.

This is a shared routing fix, not an MBC-only exception. Ordinary MBC 3 played
through the exact-ID route on the actual Ugoos: decoder startup was about
0.85 seconds after Player.Open, with 1920x1080 HEVC video and AAC audio.
Sixteen browser tests passed, including native matching, fallback cases and
invalid-ID rejection. This does not claim every provider stream was tested.
The user requested no further playback interruptions; additional live channel
tests were stopped rather than disturbing their viewing.

Deployed browser SHA256:
`9960d5abf16547daa59166dd51bd089aa025d4f46b344ec2d28d7dd0a2f27a29`.
The device's verified-build manifest was updated. Browser rollback copy:
`/storage/upgrade-staging/sync-category-performance-20260918/browser-before-identity.py`.

## Earlier category timeouts and endless catch-up

Two separate server bottlenecks were repaired before the playback routing fix:

- KodiSyncQueue repeatedly performed per-item lookups for a large IPTV catch-up
  backlog. Client timeouts left server work running, with 24 simultaneous
  PopulateLibraryInfo stacks and roughly 576% container CPU in one snapshot.
  Batched lookups, cancellation checks and explicit opt-in excluded path roots
  now avoid downloading unsynced Venom movies/series during catch-up. Visibility
  checks remain in place; removals remain available for local cleanup. Selected
  libraries override exclusions, and missing paths are not silently discarded.
- Live TV category pages looked up channels individually. Bounded batch lookup
  now retains the requested quality order and current user visibility checks.

Ugoos-to-server measurements before/after:

| Page | Before | After |
| --- | ---: | ---: |
| Arabic news, 45 channels | 1.101 s | 0.086 s |
| beIN, 100 channels | 2.206 s | 0.149 s |
| MBC, 93 channels | 1.953 s | 0.128 s |

All 37 custom groups' first-page API requests passed, taking 0.023–0.257 s.
This measures listing requests, not every channel's provider startup time or
every later page. A real news grid opened with artwork; a sampled news channel
played through native PVR. Provider “UHD” branding was not treated as proof of
actual 4K: that sample decoded at 1920x1080.

The September 14 backlog was replayed through native add-on notifications after
an inadvertently skipped large-update prompt. The client processed 1,985 updates,
two user-data items and nine removals, finished its queues and saved a new sync
watermark. No manual database cursor rewrite or library reset was used. One
caught, separate episode metadata IntegrityError (“The Pecking Order”, Physical
-100 path) remained in that log; this is not a claim of zero errors everywhere.
Server CPU returned to idle (0.09% in one sample).

## Jellyfin 12.1 web compatibility and ordering

The category plugin's exact web-version guard still targeted 12.0 and disabled
its custom client after the server upgrade. Its bundled web client was rebuilt
from official Jellyfin web 12.1, commit
`fae41f33eb7cd636a9ef68984adb82bb247a6e1b`, with reviewed local overlays.
The guard now requires 12.1.0.0, rather than being bypassed. Modern and legacy
category navigation preserve server ordering instead of alphabetizing away
the custom groups' priority. Authenticated browser verification showed the
custom categories first and actual channel cards. Stale service-worker caching
was cleared in the maintenance browser only; user app data was not cleared.
Native Moonfin applications were not rebuilt or given unsupported custom UI.

## Maintained patches and checks

- `patches/jellyfin-2.2.0-habibi.patch`: consolidated client patch against
  Jellyfin-for-Kodi `a1aeda1352eb49c16d8da877121ea2068a7a7508`.
- `patches/kodisyncqueue-16-bounded-catchup.patch`: server changes against
  KodiSyncQueue 16 source at `a1cdd8d`, built with .NET 10 and Jellyfin 12.1
  dependencies. Eleven server tests passed.
- `patches/live-tv-categories-12.1-performance.patch`: apply to category-browser
  upstream `580a46e5d77655d6bfe4f00621524dbd808f9cc7` with our existing collection
  overlays. Includes batching, web preparation/version guard and order changes.
  Thirty-four C# tests, 25 JavaScript source/contract tests and four modern
  utility tests passed; the official 12.1 production web build completed.
- `python3 integration/check-catchup.py`: checks the consolidated patch against
  a clean pinned 2.2 checkout, five catch-up contract tests, Python compilation
  and 16 browser routing tests. Passed after final test-file isolation.
  The older `check.py` remains a legacy 2.1 suite, not proof of a complete 2.2
  integration regression run. Do not stack old 2.1 patches onto the 2.2 patch.

Server/client custom components must be retained together during upgrades.
The custom server plugin packages have automatic updates disabled. Rebase and
rebuild from pinned source; do not overwrite a new release with old binaries.
Revalidate native and fallback playback, shared favourites, visibility rules,
custom ordering, catch-up completion and web compatibility before deployment.

## Backups and rollback

On the media LXC, `/root/backups/update-20260918/` contains:

- `sync-category-performance/`: prior plugin files and consistently stopped
  KodiSyncQueue LiteDB database/log pair.
- `category-web-12.1/`: preceding plugin and bundled web client.
- `category-web-order/`: preceding web assets.

On Ugoos, `/storage/upgrade-staging/sync-category-performance-20260918/` holds
previous client sources. Restore compatible files as a set while services are
stopped; never restore a live database/log pair piecemeal. Restore the matching
web client and guard together. Firmware, display calibration, audio sync,
passthrough, HDR/Dolby Vision settings and provider stream quality were not
changed during these repairs. Do not interrupt active playback for verification
without renewed user permission.
