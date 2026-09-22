# Site Index

- Generated: 2026-09-14T01:16:30+00:00
- Project: `integration/web-navigation`
- Package manager: unknown

## Top-level Files
- `MOONFIN-CATEGORIES.md`
- `README.md`
- `SITE_INDEX.md`
- `test-venom-jellyfin-navigation.cjs`
- `venom-jellyfin-navigation.js`

## Route Hints
- `venom-jellyfin-navigation.js:95`: identify ranked category cards.
- `venom-jellyfin-navigation.js:99`: sort ranked cards by server order.
- `venom-jellyfin-navigation.js:102-103`: preserve unrelated cards while applying that order.
- `venom-jellyfin-navigation.js:125`: identify menu items for navigation updates.

## Feature Summary
- All authenticated accounts: simplified Live TV navigation and per-user page-size default; existing permissions remain authoritative.
- Live TV cards follow server collection/provider order; unique-channel counter excludes repeated collection memberships.
- Venom VOD category dialog and native shared favourite shortcuts; caches cleared on account switch.
- Actual preview/acceptance endpoint is the existing Jellyfin /web/; static asset preview HTTP 200 verified on port 4173 (PID 3229933), then stopped.
- See ../VENOM-ALL-USERS-ROLLOUT.md for deployment state, tests, incomplete clients and rollback.
