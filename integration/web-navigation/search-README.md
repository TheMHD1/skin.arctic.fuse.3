# Jellyfin Web 12.1 owned and Venom search rows

Status: built, deployed and checked in an authenticated mobile-size browser,
including owned/provider matches and restricted-account visibility. Apply only to the reviewed Jellyfin Web
12.1 source cohort, after the Live TV Categories web overlay has been rebased
for that same version. The maintained patch is `search-jellyfin-web-12.1.patch`.

The shared search route used by the 12.1 web app obtains `/Users/{id}/Views`
through Jellyfin's authenticated SDK. Global search classifies accessible
movie, TV and mixed media library views into owned and exact-name Venom
libraries. It queries each parent with `ParentId`, `Recursive`, `SearchTerm`
and an explicit item type before applying a per-library limit. Owned Movies
and Shows appear first, followed by owned Episodes and
the existing people, music, video and Live TV rows. Venom Movies — Not HD and
Venom Shows — Not HD are last. Unknown Venom-named views
and non-media collection types are excluded from movie/show scope. If views
are unavailable, the scoped media rows return empty; there is no all-library
fallback. Search cards retain the exact Jellyfin item IDs for playback.

Library-local scoping is unchanged. The paired
`../patches/jellyfin-enhanced-12.7-search-priority.patch` keeps Seerr Discover
after the owned Movie/Series rows and before the secondary Venom catalogue,
including when only Venom matches. Native rows carry an explicit DOM marker;
the plugin never guesses ownership from translated headings or moves React's
own result rows. The labels
`Venom Movies — Not HD` and `Venom Shows — Not HD` are deliberately literal in this personal
integration; other stock row names use Jellyfin translations. The same source
route serves modern and legacy web search. Native clients that render their
own UI are unaffected by these headings; no custom APK is supplied.

Use Jellyfin Web commit `fae41f33eb7cd636a9ef68984adb82bb247a6e1b`.
Apply from a clean Jellyfin Web 12.1 tree with `git apply --check` followed by
`git apply` for the patch. Build the same pinned 12.1 web source, then include
its resulting bundle in the version-matched Live TV Categories web package.
Do not install a standalone old web tree over a newer server. Verification:
run `npx vitest run src/apps/legacy/features/search/api/fetchScopedMedia.test.ts
--config vite.config.ts`, `npx eslint` on the changed search files, and
`npx tsc --noEmit --pretty false --incremental false`. On an authenticated
browser, test owned-only, Venom-only, mixed-library, and restricted users with
a query that has matches in both catalogues. Confirm Discover and item playback
still work and that a restricted user receives no unauthorized rows. Rebuild
Enhanced from commit `daf5b10c09d017941e29a79a0a45d0ab31c34abc` (12.7), applying
the maintained tabs patch then the search-priority patch. Deploy only its plugin
DLL, not build-time dependency DLLs. Run `node test-search-priority.cjs
/path/to/patched/je-source` from this directory; five ordering/idempotence cases
cover owned+provider, provider-only, owned-only and empty results.

The earlier rollout passed its focused Vitest suite (3 tests), ESLint, TypeScript
and Webpack build, but put Discover below provider rows. The September 23 paired
priority correction supersedes that ordering; see the Home/ratings release record
for current deployment and browser acceptance rather than treating the earlier
placement as the desired result.

`install-bundle.py --help` describes the deployment helper. Supply a tar archive
whose root is the compiled Web output, its SHA-256, exact server version, current
served Web directory and a new private backup directory. It retains old hashed
assets for open clients, preserves existing local `venom-`/`habibi-` custom script
tags, and publishes the index last. This is not a universal installer for every
server image. Retain the backup and original image for recovery; an interrupted
deployment requires inspection, not an assumption of automatic rollback.

Rollback the source patch with `git apply --reverse` on the exact patched
source and rebuild/reinstall the prior matching web bundle. Preserve private
deployment backups and account-specific acceptance records outside this fork.
