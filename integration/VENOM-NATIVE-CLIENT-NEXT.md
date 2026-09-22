# Native client follow-up — 2026-09-14

## SUPERSEDED — custom app cancelled by user

Custom APK/client work and preview have been stopped and removed to Trash.
No phone installation occurred. Historical implementation notes below are not
the current deployment or plan. See VENOM-REMAINING-WORK.md: existing apps only.

## Update at 02:17 UTC

Moonfin native category UI and API integration are now implemented in the review
checkout. Flutter 3.44.1/Dart 3.12.1 installed in the isolated local toolchain path.
13 API tests and two widget tests pass; targeted analysis is clean; release web
build succeeds. Real-server desktop and phone-width previews show categories,
logos, clean labels, correct quality order, and favourites. Actual favourite
remove/add roundtrip was verified in Jellyfin and restored to the original state.

Preview: http://192.168.2.186:4174, user service `moonfin-categories-preview.service`.
Detailed record and index: `ops/moonfin-core-review/HABIBI-CATEGORIES.md` and
`SITE_INDEX.md`. No Android APK has been signed or installed. Earlier audit notes
below describe the starting state, not the current implementation.

## Kodi

`ops/plugin.video.venom.tv/browser.py` has pending server-ordered curated groups
and channel-only display cleanup. It retains raw entry labels, parameters and
native IDs for playback matching/favourites. Movie titles are not transformed.
Eleven offline regression tests pass, including raw-identity preservation.
Ugoos 192.168.50.169 returned “No route to host”; none of this pending source
has been deployed or marked verified on the device.

## Moonfin

Exact 2.5.1 source cloned to `ops/moonfin-core-review`, commit
`f18c45b1fbf9b63871b4f93237179f9706154763`.

- `lib/ui/screens/livetv/live_tv_screen.dart` hardcodes Guide, Recordings,
  Schedule and Series Recordings; it does not discover the category plugin.
- `lib/data/viewmodels/live_tv_guide_view_model.dart::_fetchChannels` requests
  all channels with SortName, then locally sorts. It does not call LiveTvCategories.
- Native favourites already use the authenticated user's mark/unmark endpoints.
- Next implementation: capability-detected category browser using server summaries
  and paged existing channel DTOs, preserving server order and native favourites;
  channel-only display labels; fallback to existing UI if plugin unavailable.
- Flutter/Dart are not installed on the local PATH. Upstream CI pins Flutter
  3.44.1; pubspec requires Dart ^3.11.0. No APK was built or installed, and no
  source changes have been made to this checkout yet.

## Runtime promotion

At 02:02:58 UTC the first automatic promotion completed: 332 native channels,
up from 312. The next checker batch started normally. An immediate order audit
verified the unchanged Arabic news/general/drama/kids collections, then saw the
expanded sports collection still cached. The plugin caches snapshots for five
minutes; repeat the audit after expiry before attributing this to an ordering bug.
The read-only audit is `ops/venom-verify-collection-order.py`.
