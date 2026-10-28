# Seerr 3.5.1 privacy-overlay candidate

Version-specific candidate, built from the exact compiled files from the
3.5.1 image. Production remains unchanged until the complete deployment
transaction and request/subtitle integrations are verified.

- Official source tag `v3.5.1` resolves to
  `564bfb08b54caa374bddaf820abfd226e5e69151`.
- The source-level privacy anchors still exist in this tag:
  `router.use(checkUser);` in `server/routes/index.ts`, and the request count
  route/query in `server/routes/request.ts`.
- The existing overlay protects compiled `dist` JavaScript and is intentionally
  pinned to 3.4.1 hashes. It must fail on 3.5.1; do not bypass that guard.
- A separate 3.5.1 builder now pins the three files extracted from the official
  image digest `sha256:d8fab675b55ad293ded98fd71efcfd46054cbad9746534ae1cc4794a88c0b3be`.
  It generated a four-file guarded overlay from the clean extraction; all
  generated JavaScript passed `node --check`.

Rebase the middleware insertion and count viewer restriction against a clean,
private extraction of only the four allowed app files from the exact 3.5.1
image. Update the version and all upstream/generated hashes in a new
version-specific builder, run fixture plus clean-input tests, and require the
startup guard in a disposable container. Confirm ordinary user, requester,
owner and integration API behavior before considering the production recreate.
No image extraction, settings, database, API key or generated overlay is
stored here.

## Isolated native-route acceptance (October28)

`runtime-fixture.js` ran inside that exact image with the four generated
read-only overlay mounts, `NODE_ENV=test`, a disposable config directory,
`--network none`, and no published ports. It requires SQLite `:memory:`
before initializing native entities. Synthetic fixture inserts disable
notification/ARR subscribers. The actual native authentication and routes
proved owner full list/count, both ordinary users' own list/count/detail,
foreign direct-request and user-request403, and unauthenticated403. Shared
media availability and unfiltered ORM relations remained unchanged.

The fixture also runs the generated startup guard before route loading.
Execute with the official immutable image above, mounting each generated
file at the targets documented in the parent README, and mount this fixture
read-only at `/tmp/runtime-fixture.js`. Set `CONFIG_DIRECTORY` to a disposable
path, use `--entrypoint node` and command `/tmp/runtime-fixture.js`. No real
account/token/settings/database is required or permitted. This is native API
and middleware acceptance, not a complete Next.js UI, actual new-download
or live webhook delivery test.
