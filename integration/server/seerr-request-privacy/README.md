# Seerr request privacy overlay

Source-tested overlay for the reviewed Seerr 3.4.1 compiled server cohort.
Deployed September 26 with a pinned image and verified ordinary-user, requester
and owner API responses: ordinary users saw no foreign embedded requests and
received 403 on foreign direct request routes; own list/count/detail remained
available, while the owner retained complete results. These checks did not
create a new test request. This directory does not itself deploy,
change permissions, or contain real accounts/configuration. The exact three
upstream SHA-256 pins are in `build-overlay.js`.

Seerr's native request list, request detail and user-request routes enforce
`ADMIN`, `MANAGE_REQUESTS` or `REQUEST_VIEW`. However movie/TV detail and media
relations expose `mediaInfo.requests` without those checks, and `/request/count`
returns global totals. Removing permission bits alone leaves these disclosures.

The middleware runs after native `checkUser`, before API handlers. It uses
native `hasPermission([MANAGE_REQUESTS, REQUEST_VIEW], {type: 'or'})`, including
native ADMIN bypass. Signed users without those permissions receive only their
own embedded request relations, across TV/movie/search/discover/collection/media
and issue responses. Standalone embedded foreign request objects become null.
Shared media availability, season availability and catalogue data remain visible:
the catalogue is shared, so the existence of available/requested media is not
private. Other users' identities, request IDs and request records are filtered.

Serialization creates a response DTO before filtering. It never changes ORM
entities or persists a filtered relation, so subscribers and administrator API
integrations continue to receive complete data. The count patch adds a viewer
inner join: subsequent status `.where()` calls cannot erase this restriction.
Native request list pagination/counts are already scoped and remain untouched.
The user directory/profile's other-user `requestCount` is omitted, while one's
own count remains visible. User profiles and generic catalogue counts otherwise
remain unchanged.

## Build and test

Extract only `package.json`, `dist/routes/index.js`, `dist/routes/request.js`, and
`dist/lib/permissions.js` from the exact clean image into a private local staging
directory, preserving their relative paths. Never extract settings/databases.
The builder rejects wrong versions, changed compiled source, ambiguous anchors,
and an existing output directory. It writes only a new caller-selected stage.

```sh
node --test integration/server/seerr-request-privacy/test_privacy.js
SEERR_PRIVACY_CLEAN_APP=/private/clean-app node --test integration/server/seerr-request-privacy/test_privacy.js
node integration/server/seerr-request-privacy/build-overlay.js /private/clean-app /private/new-overlay
```

The clean-input test builds the real pinned compiled cohort, checks JavaScript
syntax, accepts the guarded stage and proves startup refusal after helper drift.
Fixture tests cover own/foreign/reduced/single nested requests, every visibility
permission, administrator preservation, serialization/immutability, viewer-ID
validation, exact anchors and count-query scoping.

## Install and recreate guard

Keep the existing private image/configuration/webhook/deployment unchanged.
Privately back up the current Compose definition and any existing overlays.
Use four read-only file mounts from the built stage:

| Generated file | Container target |
| --- | --- |
| `dist/routes/index.js` | `/app/dist/routes/index.js` |
| `dist/routes/request.js` | `/app/dist/routes/request.js` |
| `dist/middleware/requestPrivacy.js` | `/app/dist/middleware/requestPrivacy.js` |
| `privacy-startup-guard.js` | `/app/privacy-startup-guard.js` |

Append `--require=/app/privacy-startup-guard.js` to existing `NODE_OPTIONS`
(preserve existing options). The preload checks package name/version, all three
patched/helper files, and native permissions against the exact generated hashes
on **every start/recreate**. A changed image refuses startup; never bypass the
guard to make an update look supported. Keep `SEERR_PRIVACY_APP_ROOT` unset in
production. No secrets or special user names are embedded in the overlay.

Atomic replacement of bind-mounted files requires a container recreate to
replace mounted inodes. Use the existing deployment's normal recreate path;
verify the in-container hashes against generated `manifest.json`. Do not
overwrite the application's config volume or databases.

Apply native per-user/default permission changes separately through supported
APIs: only the designated owner may retain ADMIN/MANAGE_REQUESTS/REQUEST_VIEW.
Any account retaining any of those permissions can still see all requests.
Use `X-API-Key` and the officially supported `X-API-User` server header privately
to test representative users; never expose the admin API key to a client.
Test `/request`, `/request/count`, other-user `/user/:id/requests`, a foreign
`/request/:id`, and movie/TV detail for media requested by two different users.
Verify an ordinary user sees their own requests only, foreign direct routes
return 403, owner/integration calls retain the complete data, new own requests
still work, and shared availability remains intact. Record sanitized outcomes
and private rollback location; local tests alone are not live acceptance.

## Updates and rollback

Compiled pins intentionally fail closed. For a new image, review native request
serialization, permission semantics and count query, rebase anchors/pins against
its clean output, and rerun fixtures plus the real clean-input test. Reapply the
generated mounts/preload to the new image. For a source rebuild, port the same
middleware insertion after `router.use(checkUser)` in `server/routes/index.ts`
and the conditional viewer inner join in the count handler; regenerate compiled
output and review new hashes rather than allowing a compiler to erase the fix.

Rollback restores the compatible previous Compose/overlays and NODE_OPTIONS,
then recreates the container and verifies readiness. Permission changes are
independent: removing the overlay reopens embedded-data leakage even while
native request-list restrictions remain. Restore previous settings only if the
owner explicitly wants the previous visibility policy. No media or database
rollback is needed for this response-only overlay.

Repository preservation: parent maintainer must add this source map to
`CUSTOMIZATIONS.md`, stage the reviewed changes, regenerate/verify the release
source manifest, and commit/push the reviewed release. This bounded component
does not edit those shared files itself.
