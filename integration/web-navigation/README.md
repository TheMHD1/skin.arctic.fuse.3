# Jellyfin Venom navigation — 2026-09-14

Follow-up: [Moonfin categories and favourites](MOONFIN-CATEGORIES.md) repairs provider genre indexing, adds lightweight category browsing and favourite-show shortcuts. The pending category-index limitation below describes the earlier state.

## Outcome and remaining work

Installed Live TV Categories **0.3.0.0**, matching Server/Web **12.0.0** exactly. Added a small Habibi-only navigation customization in its bundled web shell. This affects clients loading server-hosted Jellyfin Web, including the official Android mobile wrapper. It does not add category UI to native Moonfin/Android TV/Swiftfin applications.

Live TV now presents 304 provider groups first, then bounded channel pages. Habibi's modern Live TV selector shows Categories and Channels, hiding Guide, Recordings, Schedule and Series. No tuner/channel IDs, favourites, stream URLs, playback profiles, recordings or library contents were deleted or rewritten.

Venom Movies selector was verified with Movies and Favorites only while its genre index is incomplete. Venom Series selector was verified with Shows only; its favourites remain accessible through normal item actions and Home favourites. Irrelevant Suggestions/Collections/Studios/Upcoming/Playlists and the giant Episodes view are hidden only in the two Venom libraries. Normal libraries and other accounts are not targeted.

**Movie/series provider categories are still pending, not fixed or declared complete.** Individual NFO/imported items contain their provider genre (`Venom: ...`) and tag, but `/Genres` and `/Items/Filters2` do not yet expose them. The global catalogue scan is still running. A scoped five-minute readiness check reveals the Categories/Genres option when provider genres become available. Until then an explicit indexing notice is shown instead of an empty genre screen. If the index remains empty after a successful complete scan, investigate the server normalization/post-scan step; do not keep issuing full rescans or manufacture categories.

## Evidence

- Before: `/LiveTv/Channels` already handled bounded requests efficiently: 48 channels in 0.143 s; 200 in 0.057 s on a warm request. Channel DTO Genres/Tags were empty. The stock channel endpoint does not preserve provider groups as a browsing filter.
- Movies: 27,935 indexed titles, example items have provider genres/tags, but Genres/Filters2 genre lists empty.
- Series: 3,542 titles indexed at audit, with only five conventional genres and no provider genres in the normalized filter list. Initial import/index remains incomplete.
- New plugin startup matched **11,249 channels to 304 groups, zero unmatched tuner records**.
- Warm category summary: **0.035 s**. A 50-channel page from a 128-channel group: **0.083 s** with current-program lookup disabled for this timing. These are API timings, not phone-radio, artwork or first-video-frame timings.
- Authentication checks: unauthenticated category endpoint returned 401; a user without Live TV permission returned 403 even when the request was made through the administrator audit helper with that user selected.
- Real authenticated browser as Habibi: 304 category tiles; selector only Categories/Channels; Movies/Favorites only for Venom Movies; Shows only for Venom Series. Both movie and show pages displayed **1–50**, not 1–100. No browser console errors in the final navigation snapshots (one existing warning).
- Upstream JavaScript/package suite: 25/25 passed. Local policy tests passed for account/library scoping, hidden menu policy and genre readiness. C# tests were inspected but not executed locally; deployment/API checks validated the installed DLL against this server.
- Enhanced injection remained present and the Downloads page was registered after installation. This is not an exhaustive retest of all plugins or playback formats.

## Page-size and UI implementation

Source: `ops/venom-jellyfin-navigation.js`; tests: `ops/test-venom-jellyfin-navigation.cjs`.

The one-time local setting is `<HabibiUserId>-libraryPageSize = 50`, matching Jellyfin's own userSettings/appSettings implementation. `<HabibiUserId>-venom-page-policy-v1` records the previous value. Later manual user changes are respected. Returning-user preferences are initialized before the main app mounts; close/reopen or reload existing clients to apply the updated shell. No API response is truncated or pagination offset monkey-patched.

The helper recognizes only known English modern-view menus and exact Venom library IDs. Unrecognized menus/languages/routes fail open to stock UI. It uses the logged-in user's normal API client for a small Genres readiness request, not an admin key. No provider credentials or access tokens are transmitted to another service. Native client settings/layouts are not forced.

## Deployment, source and rollback

Production plugin directory:
`/data/config/jellyfin/data/plugins/Live TV Categories_0.3.0.0/`

Upstream package: `https://github.com/JeKaQM/jellyfin-live-tv-category-browser/releases/download/v0.3.0.0/Jellyfin.Plugin.LiveTvCategories_0.3.0.0.zip`

Manifest MD5 verified: `2fa4c24399b9cc8bf587457ef69bf11b`. The plugin serves a complete version-pinned web tree from its own `web/`; stock `/usr/share/jellyfin/web` remains intact. The plugin validates exact server version and falls back to API-only on mismatch. Its own source adds category browsing to both modern and legacy clients; our menu simplification is verified on the modern English view.

`web/venom-jellyfin-navigation.js` is loaded early by a script tag in the plugin's `web/index.html`, currently `?v=2` for cache invalidation. Keep this isolated and recheck after any plugin/web upgrade. Do not blindly apply the old shell to a new release. Stock package remains in `ops/live-tv-categories-package/`; reviewed source is `ops/live-tv-categories-review/`.

Original plugin web shell backup:
`/data/config/iptv-venom/backups/live-categories-index-before-navigation.html`.

To remove only the navigation customization, restore that index file, reload the client, and restore the previous local page-size value recorded by the marker if desired. No Jellyfin restart is required for that shell change. To remove the entire category plugin, disable/uninstall it and restart Jellyfin; stock web serving returns. Do not move/delete unrelated plugin or user-data directories.

The global scan was cancelled for the one plugin-install restart and explicitly restarted afterward. No playback session was active at the initial check. At a later check the scan was running at 43.7%; completion is not claimed.

Maintained public-safe copy: `ops/arctic-fuse-fork/integration/web-navigation/`, with `SITE_INDEX.md`. No GitHub push this turn. Actual UI preview/acceptance used the existing Jellyfin endpoint; a disposable local asset server (PID 2482148, port 4173) returned HTTP 200 and was stopped immediately. No new permanent service remains on the development host.

Private browser evidence: `output/playwright/venom-*-verified.yml` and `venom-*-final.yml`; do not publish account/library screenshots or browser authentication state.

## References

- [Live TV Categories release and compatibility](https://github.com/JeKaQM/jellyfin-live-tv-category-browser)
- [Category bridge architecture](https://github.com/JeKaQM/jellyfin-live-tv-category-browser/blob/main/docs/architecture.md)
- [Jellyfin Live TV setup](https://jellyfin.org/docs/general/server/live-tv/setup-guide/)
- [Jellyfin Web page-size implementation](https://github.com/jellyfin/jellyfin-web/blob/v12.0/src/scripts/settings/userSettings.js)
