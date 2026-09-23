# Jellyfin Web 12.1 owned Home rows

Deployed and checked in mobile-size authenticated Web, including a restricted
account. See [the release record](../HOME-RATINGS-2026-09-23.md) for evidence and
remaining native-client boundaries.

Apply `jellyfin-web-12.1-owned-home.patch` to the exact reviewed Jellyfin Web
12.1 source **after** the maintained permission-scoped search patch, because
the Home module reuses its `classifySearchLibraries` helper. This patch changes
only `src/components/homesections/`; it does not add `HomeSectionType` values or
write user Home preferences. The three extra rows are transient client DOM:
Favorites, Top Rated Movies and Top Rated Shows. They mount ahead of the first
Latest Media section, or immediately after Next Up if Latest Media is absent.
The ordinary Home sections load first; optional row failures hide only these
rows.

Library enumeration starts with the signed-in user's permission-filtered
`getUserViewsQuery`. Each owned movie/show/mixed view is queried separately
before pagination, with exact Movie/Series type checks, ID deduplication and a
2,000-item-per-kind safety limit. Venom and Discover views are excluded; there
is no root/global item query. Favorites read the current user's
`UserData.IsFavorite` and refresh on `markfavorite` events. Existing
`emby-itemscontainer` and `cardBuilder` preserve standard card actions.

Top Rated prefers the authenticated plugin response
`GET /Habibi/LibraryExperience/Ratings?ids=...`, using at most 100 exact
Jellyfin IDs per call and no per-card requests. The expected response is
`{items:{id:{imdb:{rating,votes},community}},source,fetchedAt}`. A missing,
stale (over eight days), invalid or slow (1.8-second batch timeout) IMDb result
falls back to Jellyfin's generic `CommunityRating`; the UI explicitly says
“IMDb where available; otherwise library score.” Generic scores are **not**
labeled IMDb or TMDb. The plugin must enforce the caller's item access and
never return unauthorized item ratings. The client rechecks user/server
identity before and after requests; ratings cache is bounded to four
server/user/scope entries and five minutes. Item lists are not cached across
favorite changes. Favorites do not wait for the optional ratings request; the
Top Rated rows have a three-second overall ratings deadline. Jellyfin item IDs
are normalized to lowercase 32-hex before rating lookup. This adds no
credentials or custom native-app UI.

From the Jellyfin Web 12.1 source root, verify with:

```sh
git apply --check /path/to/jellyfin-web-12.1-owned-home.patch
git apply /path/to/jellyfin-web-12.1-owned-home.patch
npx tsc --noEmit --pretty false
npx vitest run src/components/homesections/sections/ownedHomeLogic.test.ts
npx eslint src/components/homesections/homesections.js src/components/homesections/sections/ownedLibrary.ts src/components/homesections/sections/ownedHomeLogic.ts src/components/homesections/sections/ownedHomeLogic.test.ts
npx stylelint src/components/homesections/homesections.scss
npm run build:development
```

Before deployment, preserve the current Web bundle privately. Verify with a
regular user who can see owned and Venom views: only owned Movie/Series appear
in the three rows, favoriting/unfavoriting updates Favorites, scores fall back
if the ratings endpoint is unavailable, and Next Up/Latest Media still load.
Repeat for a user without owned-library access and after account switching.
Build/tests alone are source validation, not live acceptance. Roll back
by restoring the private prior bundle and, in source, `git apply -R` this
patch. Rebase and re-run tests for future Jellyfin Web versions.
