# Reproducible LinuxServer candidate

## Immutable inputs

| Input | Pin / SHA-256 |
| --- | --- |
| LinuxServer AMD64 base | `lscr.io/linuxserver/jellyfin@sha256:50b431edbea22045f97c5d662b4ab22a48e0aeab1e186702ec2a02bf70dd0eec` (`12.4ubu2604-ls57`) |
| Server source | `83d0d0e7f76e23e2e085c8ff67d28b772d35967d` |
| Web source | `0a580ce8df89282dfd120b6d5efb8e106da23bd5` |
| Library Experience DLL | `966e035e0f17d21c070e411c2bb22b79cda394262221d5e39773a3b851778457` |
| Jellyfin Enhanced DLL | `cfa55d354b8c323682914df41823e9da84847d6b88664278beb1fdd2f43d1733` |
| Kodi Sync Queue DLL | `fb6f00fbc3a470c54fddfa17f6de279671aceaf96641bccae8b8e73073937632` |
| LiteDB | `ae31ac6a93549217b9e8b81497d1ee831658ade6df9e1ee20f2838f22de5e218` |
| Intro Skipper DLL | `db74239e451010e8c57166a80a45bbd1326cb8fd890cc1f0e20ca784a45f5777` |

## Final candidate evidence

The final all-feature candidate is
`habibi/jellyfin:12.4-linuxserver-allfeatures-final-r2`, image ID
`sha256:917d9be9b12bde44abee36c4c19ea6a0949907e8072c3772cd1d58eaeedc361a`.
Its exact Web 12.4 build passed TypeScript and 18 focused Home/search/Live-TV
tests; the server and Live-TV plugin Web trees were compared as complete
manifests before the image build. Native publication acceptance passed all 13
synthetic real-Jellyfin checks. The retained custom Moonbase snapshot has 201
reviewed regular files and its digest-pinned SDK build passed 341 tests; its
six retained historical test files excluded for their incompatible 10.10 fake are not implied by
that count. The reproduced Moonfin DLL SHA-256 is
`be85afefe7e315a3cdddc3f76c5118e333b176895b3fdaf1b902d6cacfaee45a`.
The excluded historical files are `FakeLibraryManager.cs`,
`GamesServiceTests.cs`, `ArtworkPriorityTests.cs`, `GameArtworkCatalogTests.cs`,
`GameArtworkReconciliationServiceTests.cs` and `SimilarItemsScoringTests.cs`.
The builder validates exact file-set equality, copies only those manifest-listed
files to a writable temporary build tree, and builds as the caller's UID with
the immutable .NET SDK image pinned in the script. `artifacts.sha256` excludes
itself and is checked after generation.

The Dockerfile retains LinuxServer `/init`, `/config`, PUID/PGID behavior and
`/dev/dri` layout. It replaces Web at `/usr/share/jellyfin/web` and retains
LinuxServer FFmpeg at `/usr/lib/jellyfin-ffmpeg/ffmpeg`, first on PATH.

Build in a private directory outside Git containing the patched server DLLs,
12.4-guarded Library Experience DLL/meta (`targetAbi: 12.4.0.0`), generated
Web `dist` as `jellyfin-web/`, and versioned Enhanced, KodiSyncQueue (with
LiteDB) and IntroSkipper plugin folders. Hash every context file, then run:

```sh
DOCKER_BUILDKIT=1 docker build --pull=false -t habibi/jellyfin:12.4-linuxserver-candidate-YYYYMMDD PRIVATE_CONTEXT
```

Copy this directory's `Dockerfile` and `root/` tree into that private context,
including `root/custom-cont-init.d/60-habibi-jellyfin-candidate` (SHA-256
`62cb09148792cdf12e25a6c4e1222f74104191b0ede471ab5e27e5f0d3596507`).
The hook uses the LinuxServer data layout and seeds only absent plugin folders;
it does not replace the required stopped plugin transaction below.
The IntroSkipper artifact's package-directory label is 12.0.6, but the actual
loaded assembly reports **12.0.5.0**; the DLL hash above, not that directory
label, identifies the reviewed artifact.

## Mandatory stopped plugin transaction

The image seed hook only creates an **absent** directory. This is safe for
blank fixtures but does not upgrade an existing plugin: the live Library
Experience directory declares ABI 12.1.0.0 and would otherwise remain active.
Before a canary, stop Jellyfin; take one consistent private `/config` snapshot
including DB/WAL/SHM, plugins and XML; hash the old files; move only reviewed
replacement binary directories for **all 14 reviewed installed plugins** to a
dated rollback directory (including Library Experience, Enhanced, Intro
Skipper, Kodi Sync Queue, custom Moonbase, custom Live TV Categories and
Reports 20); atomically copy the reviewed replacement folders; preserve all
`configurations/*.xml`; then start and require load-log,
native publication, authenticated-route and playback gates. Rollback is
stopped-only and restores the complete pre-12.4 config snapshot plus exact
12.1 image/artifacts; never open a 12.4-migrated DB with 12.1.

## Full feature artifact set

Official catalog ZIP SHA-256s: AniDB13
`c4ae61a88ac5bd27f50e2fc309aa1b61a8ec237f4f73a2c89d0d45c1030dfaf3`,
Artwork3 `273de912edd6d65a37a7b354cdab3cd5be4f115d700e1d8cb54a8a2f0b0b17af`,
ChapterSegments5 `b8dc37e2f3522495e5a41d1d04d21506840f06d659ffe1189532d70e4aae5337`,
Fanart15 `7b51a3525bf9b6c67b7d43c753a80e4443b23d6c5e4e84055b02b72a59e1938d`,
LocalIntros5 `2af91b7681baf1605a8bc344714a38f69c5e6993996a8f5e56230fe001657ac1`,
PlaybackReporting19 `6599f6d84406e170a176d5177ddea04af682ddb2f34fe9424392f2a81a511180`,
Reports20 `98375bba5c2dcfc753dfeb73b3f9f495c01acca567c50e7852cb99521a26cc5a`,
and Moonbase2.4 `2dadff3d8f4f797e18b394bf9825173f9bc2f49022d6a0220ef5fb6eb4fbd35b`.
Anime Filler 1.0.0.3 must include its declared `HtmlAgilityPack.dll`.

Rebuild Live TV Categories from upstream `580a46e5d77655d6bfe4f00621524dbd808f9cc7`,
this directory's `live-tv-categories-12.4-packages.patch`, the retained
12.1-performance patch, and all collection overlays/tests. Its category Web
bundle must remain in the plugin package; the separate custom Web build does
not prove category-UI behavior. Because the Live TV plugin serves a complete
Web bundle, its 12.4 Web port must also include the retained owned-Home and
owned→Discover→Venom search patches/tests before packaging; a stock category
bundle would silently discard those custom features. Shokofin is configuration-only here and is not
removed, disabled or included among the 14 installed-plugin artifacts.

For the 12.4 category Web port, begin with exact Web commit
`0a580ce8df89282dfd120b6d5efb8e106da23bd5`, apply the existing owned
Home/search candidate patch chain, then apply the category route overlay and
the 12.4 package/Web-guard patches. Required checks are `tsc --noEmit` and the
combined owned Home (9), search (3), and category order/API utility (4) tests.
The generated plugin `web/index.html` must be copied from the same merged Web
`dist/` directory used for the image. Verify that copy with `cmp -s` or
`sha256sum` at package time. Webpack's generated build-id query string is not
stable across otherwise identical clean builds, so an old standalone
`index.html` hash is not an integrity pin.

The complete route overlay is stored as ordinary reviewable TypeScript under
`live-tv-web-12.4-overlay/`: the replacement Live TV route, four category
implementation/test files, and three native library-page integration/test files.
It is not an untracked workspace copy. From a
pristine checkout at that exact Web commit, run
`build-livetv-web-12.4-candidate.sh /path/to/web`. The script verifies the
revision and pristine Git status, applies the maintained general patches, copies
the route overlay, performs TypeScript and all four targeted test suites, and
generates the `dist/` bundle that must be copied into the rebuilt Live TV
Categories plugin package. It must never be applied on top of a previously
modified Web checkout.
