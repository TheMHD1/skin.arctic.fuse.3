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

### Jellyfin Web 12.4 custom source gate

The two maintained Web feature patches were tested against exact upstream
Jellyfin Web `v12.4` revision
`0a580ce8df89282dfd120b6d5efb8e106da23bd5`. They apply cleanly without a
conflict; this is an intentional version-scoped port, not an assertion that
they apply to later 12.x versions. The patches preserve:

- signed-in-user, permission-scoped owned-library search before the large
  Venom catalogue is limited, and a `data-habibi-catalogue="venom"` marker
  for the secondary provider rows;
- owned Home rows for recently watched content, favourites and ratings while
  retaining Jellyfin-owned rows and authorization boundaries.

Run the reproducible candidate gate in a disposable exact checkout:

```sh
bash integration/server/jellyfin-custom/candidate-12.4/build-web-12.4-candidate.sh /path/to/jellyfin-web-v12.4
```

It runs `npm ci`, TypeScript checking, the 12 custom search/Home regressions
and the production Web build. The present gate passed all 12 targeted tests.
A blank, loopback-only official Jellyfin 12.4 runtime served that generated
Web directory, was healthy, and served the generated bundle/index without
server errors. This validates build/static delivery, not authenticated
desktop/mobile/Kodi rendering against a real library.

## Required disposable acceptance

### Plugin source checkpoint, October28

`jellyfin-enhanced-12.13-habibi.patch` targets official Enhanced12.13.0.0,
commit `ef1ac3c7917421fecf1211249980f037ee524d3d`, with net10/Jellyfin12
dependencies. It ports owned→Discover→Venom placement and a detached-page-aware,
30-second bounded, animation-frame-coalesced watcher. The old Tabs patch is not
carried over verbatim: current upstream has a shared active-tab predicate and
native-tab deep-link/reconciliation handling that must remain intact.
Clean apply, .NET build, 864 upstream backend tests and five maintained search
JavaScript tests passed in isolation. This source checkpoint is deliberately
limited to compile/unit evidence; the later **Plugin ABI/runtime gate** records
the separately completed blank-runtime acceptance.

KodiSyncQueue16's existing bounded-catchup patch applied cleanly to its official
net10/Jellyfin12 source and 11 isolated tests passed. IntroSkipper12.0.6's
net10/web build passed; its test execution still requires FFmpeg/Git in the
disposable SDK environment. No plugin was copied into production. Full plugin
runtime loading and the version-matched custom web port were completed in a
blank runtime; authenticated real-client acceptance remains pending.

1. Existing user Resume and Next Up API behavior, paging, library access and
   rewinds; no database mutation in the test stack.
2. DOVI exact discovery, subtitle publication and the new exact artwork queue.
3. Real-client acceptance. The custom Web source has passed its exact 12.4
   build/runtime delivery gate, and Jellyfin Enhanced's supported request-time
   injection has passed against stock 12.4 Web. Production still requires
   authenticated desktop/mobile/Kodi checks against actual private libraries.
4. Hardware direct-play/transcode smoke tests including HDR/PGS samples.
5. Web/mobile artwork, Seerr request-to-Jellyfin visibility and Live TV.

No release image, binary, config, credential or production database belongs in
this directory.

## Plugin ABI/runtime gate — completed only in a disposable stack

The following independent plugins were compiled against their maintained
official sources and then loaded together by a blank, loopback-only Jellyfin
12.4 container. No production configuration, database, media, library path,
token or account was mounted.

| Plugin | Exact source | Build / unit result | Blank 12.4 runtime result |
| --- | --- | --- | --- |
| Jellyfin Enhanced | upstream `12.13.0.0` `ef1ac3c7917421fecf1211249980f037ee524d3d` plus `jellyfin-enhanced-12.13-habibi.patch` | `net10.0`; backend suite **864/864** passed | Loaded and initialized; its startup task completed and the 12.4 `/web/index.html` contained its supported `JellyfinEnhanced/script` injection. |
| Kodi Sync Queue | upstream v16 `a1cdd8db9b61df82af49e12172a745de12a8fe05` plus the retained bounded-catchup patch | `net10.0`; **11/11** custom regressions passed | Loaded and created its blank LiteDB repository. `LiteDB.dll` 5.0.21 must ship adjacent to its plugin DLL; a DLL-only trial correctly failed and is not a deployment recipe. |
| Intro Skipper | upstream `12.0/v12.0.6.0` `da3d8d50af3418ecd1ba80c58eefa48df5b5e2b4` | `pnpm` web build and `net10.0` DLL build passed | Loaded and probed the official bundled FFmpeg 8.1.3 successfully when `/usr/lib/jellyfin-ffmpeg` is first on `PATH`. The candidate Dockerfile enforces that path. |

The combined container reached `Healthy` on `127.0.0.1` using the exact
official 12.4 base digest above. This is an assembly-load/startup gate only.
Production still needs a version-matched LinuxServer image, private
configuration migration/readback, real FFmpeg path verification for Intro
Skipper, Kodi catch-up acceptance and browser/Kodi/mobile visual acceptance.

## Native publication E2E — completed in a synthetic isolated fixture

The assembled local image `habibi/jellyfin:12.4-publication-e2e-candidate-20261028`
has immutable local image ID
`sha256:d977052e4951a283120bac3fd8acc462bffdcbff3d7977581a1d7ca326e5eec6`.
It combines the pinned server revision, generated Web tree, Library Experience
candidate DLL and all three tested plugins. The private build context was
`/tmp/jf124-publication-context.HJX5og`; its `ARTIFACTS.sha256` is the exact
assembly/Web provenance record and must be recreated rather than deployed from
`/tmp`.

The existing publication fixture was copied privately and version-gated to
12.4; no production path, database, account, token or media was mounted. Its
full acceptance passed: new Movie and Episode discovery, stable duplicate
identity, provider-conflict `409`, Arabic SRT arrival, atomic A→B replacement
and VTT serving, empty outbox/deadletter state, preserved unrelated anchors,
and an unchanged global library-scan execution result. The candidate Library
Experience DLL SHA-256 was
`966e035e0f17d21c070e411c2bb22b79cda394262221d5e39773a3b851778457`.

## Production migration and rollback requirements

Jellyfin 12.4 database changes are **not** safely reversible in place. Before
any controlled production canary, stop Jellyfin and take one consistent private
snapshot of the complete config/data tree, including SQLite main, `-wal` and
`-shm` files, plugin configurations, metadata/database state and the exact
12.1 image/plugin/Web artifact references. Do not merely save a Docker tag.
If rollback is required, stop 12.4, restore that entire consistent pre-12.4
snapshot while stopped, restore the exact 12.1 server image, 12.1-only Library
Experience artifact and prior Web assets, then start 12.1. Never start 12.1
against a database that 12.4 has opened or migrated. Validate health, plugin
load, a private exact-title lookup and one client playback after either change.
