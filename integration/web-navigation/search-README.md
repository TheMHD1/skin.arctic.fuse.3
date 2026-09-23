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
and Shows appear first, then Venom Movies — Not HD and Venom Shows — Not HD,
then owned Episodes and
the existing people, music, video and Live TV rows. Unknown Venom-named views
and non-media collection types are excluded from movie/show scope. If views
are unavailable, the scoped media rows return empty; there is no all-library
fallback. Search cards retain the exact Jellyfin item IDs for playback.

Library-local search and Seerr/Enhanced Discover are unchanged. The labels
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
still work and that a restricted user receives no unauthorized rows.

The focused Vitest suite (3 tests), changed-file ESLint, TypeScript check and
Webpack production build passed. The live mobile search showed owned Movies
and Shows before separate provider rows with Discover below, and no console
errors on the accepted reload.

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
