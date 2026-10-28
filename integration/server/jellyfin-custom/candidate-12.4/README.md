# Jellyfin 12.4 candidate — source compatibility record

This is a candidate only. It must not replace the running 12.1 custom image
until every gate below is passed in a disposable stack.

## Pinned upstream evidence

- Official release: `v12.4`, released 2026-10-26.
- Resolved source revision: `83d0d0e7f76e23e2e085c8ff67d28b772d35967d`.
- Both maintained server patches apply cleanly with `git apply --check` to that
  exact source: `../../../../patches/jellyfin-12.1-onepace.patch` and
  `../continue-watching.patch`.

An isolated bounded official .NET 10 SDK container applied both patches and
ran the maintained targeted server-test selection successfully (exit 0).
The separate version-specific Library Experience candidate project compiled the
reviewed source against this exact patched checkout with zero warnings and
zero errors. Its 12.4-only guard is a separate candidate patch so the existing
12.1 source cannot accidentally be broadened.

## Isolated runtime acceptance

The included `Dockerfile` was built in a disposable context from freshly built
server DLLs and the 12.4-guarded Library Experience DLL. It uses the official
`jellyfin/jellyfin:12.4` base pinned at
`sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771`.
The resulting local-only test image digest was
`sha256:742c5f0a1d9374780a97d62a9c7d94d457a276c08a87cf56e2f9ffd44291af2c`.

A blank named config/cache volume and loopback-only port were used; no
production database, configuration, plugins, paths or credentials were read.
It started healthy as Jellyfin `12.4.0`, loaded **Library Experience
Maintenance 1.2.0.0**, seeded the plugin DLL into the mounted config without
overwriting an existing DLL, and exposed all four plugin routes in OpenAPI:

- `GET /Habibi/LibraryExperience/Ratings`
- `POST /Habibi/LibraryExperience/DiscoverTitle`
- `POST /Habibi/LibraryImportDate/{itemId}`
- `POST /Habibi/LibraryImportDate/RefreshLatestDates`

Unauthenticated routes returned `401`, not `404`; no privileged mutation was
performed in the blank test library. This proves server startup, assembly load,
endpoint registration and the exact 12.4 compatibility guard path—not media
or production-data behavior.

## Candidate build procedure

Use a new disposable checkout, apply the two patches, copy the three maintained
server regression tests exactly as the 12.1 preparer does, then use the .NET
SDK declared by Jellyfin 12.4's `global.json` to run the server and naming
tests. Build the Library Experience plugin against the exact same checkout.
The present plugin has an intentional 12.1 revision guard; do not weaken it.
Create a separate 12.4 candidate project/guard after reviewing compilation and
API differences, then exercise DiscoverTitle, ratings, import date and access
tests.

For a disposable acceptance image, stage these files outside the repository:
`Emby.Naming.dll`, `Emby.Server.Implementations.dll`,
`Jellyfin.Server.Implementations.dll`, the 12.4-guarded
`Jellyfin.Plugin.LibraryExperience.dll`, and `meta.json` as
`LibraryExperience.meta.json`; then build this directory as the Docker context.
The entrypoint seeds the plugin only if no administrator-managed copy exists.

For production, rebase this exact recipe onto a reviewed version-matched
LinuxServer base so existing hardware runtime and operational mount behavior
are preserved. Keep private mounts, web changes and the prior image digest
available for rollback. Never combine 12.1 assemblies/plugins with 12.4.

## Required disposable acceptance

### Plugin source checkpoint, October28

`jellyfin-enhanced-12.13-habibi.patch` targets official Enhanced12.13.0.0,
commit `ef1ac3c7917421fecf1211249980f037ee524d3d`, with net10/Jellyfin12
dependencies. It ports owned→Discover→Venom placement and a detached-page-aware,
30-second bounded, animation-frame-coalesced watcher. The old Tabs patch is not
carried over verbatim: current upstream has a shared active-tab predicate and
native-tab deep-link/reconciliation handling that must remain intact.
Clean apply, .NET build, 864 upstream backend tests and five maintained search
JavaScript tests passed in isolation. This is not plugin runtime acceptance.

KodiSyncQueue16's existing bounded-catchup patch applied cleanly to its official
net10/Jellyfin12 source and 11 isolated tests passed. IntroSkipper12.0.6's
net10/web build passed; its test execution still requires FFmpeg/Git in the
disposable SDK environment. No plugin was copied into production. Full plugin
runtime loading and the version-matched custom web port remain pending.

1. Existing user Resume and Next Up API behavior, paging, library access and
   rewinds; no database mutation in the test stack.
2. DOVI exact discovery, subtitle publication and the new exact artwork queue.
3. Kodi Sync Queue, Jellyfin Enhanced and Intro Skipper compatibility. Their
   currently retained custom artifacts/version checks are still 12.1-era and
   were intentionally not copied into this blank image; they require their own
   exact 12.4 ABI/runtime gate before a production cutover.
4. Hardware direct-play/transcode smoke tests including HDR/PGS samples.
5. Web/mobile artwork, Seerr request-to-Jellyfin visibility and Live TV.

No release image, binary, config, credential or production database belongs in
this directory.
