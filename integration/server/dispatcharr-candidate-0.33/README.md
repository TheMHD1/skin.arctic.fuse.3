# Dispatcharr 0.33 semantic-port candidate

Target: official `v0.33.0`, commit
`2fa13a6707bdf0dae87e0c494bcd3ca282cdeb3e`; verified official image
`ghcr.io/dispatcharr/dispatcharr:0.33.0` digest
`sha256:96bc548978c68e684677da7895692eeeefb7f0b2edfa38311dac2b702c61d236`.

`dispatcharr-0.33-habibi.patch` is the semantic port of all four maintained
0.31 patches. It deliberately does not force-apply the old hunks. Apply only
to that exact release with:

```sh
git apply --check integration/server/dispatcharr-candidate-0.33/dispatcharr-0.33-habibi.patch
git apply integration/server/dispatcharr-candidate-0.33/dispatcharr-0.33-habibi.patch
```

## Preserved behavior

- Redacts synthetic/transformed XC credential URLs and transform inputs from
  this live transform path; supports `.ts` to `.m3u8` transport rewrites
  against current account credentials and the real stream ID.
- Fails closed for new shared-provider owners if Redis/lock acquisition is
  unavailable; ordinary contention remains a follower path.
- Emits a standards-valid 188-byte MPEG-TS null packet for a quiet attached
  client. Keepalive is downstream-client state, not an inference from the
  owner worker's upstream health.
- Uses a bounded 3–15 second capacity-admission budget based on shutdown grace;
  it never releases/preempts another viewer's slot.
- Allows authenticated XC `HEAD` probes, returning only transport metadata and
  never invoking `stream_ts`, registering a client, or reserving a provider
  stream.
- Preserves native XC movie/episode `HEAD`: after authentication, entitlement,
  and active-relation validation, it returns metadata without calling
  `stream_vod` or creating a provider request, session, redirect, or slot.

## Validation performed

- `git apply --check` passed on a fresh official v0.33.0 checkout.
- Python compilation and `git diff --check` passed.
- In a disposable official AIO image with a fresh named data volume, the
  focused Django suite passed: **63 tests** (the previous 58 live-path tests
  plus five exact XC VOD `HEAD` regressions):

  ```text
  apps.m3u.tests.test_credential_transform
  apps.channels.tests.test_ts_proxy_keepalive
  apps.proxy.live_proxy.tests.test_xc_hls
  apps.proxy.live_proxy.tests.test_habibi_033_regressions
  apps.proxy.vod_proxy.tests.test_xc_head_metadata
  ```

`test_habibi_033_regressions.py` is retained beside the patch for easy review;
the same file is included by the patch.

## Deployment gate

Before a live update, snapshot the Dispatcharr data,
build an image from the exact patched tree, and run a disposable smoke test for
native PVR, XC TS/HLS and a provider-capacity follower. Do not reuse the
disposable test volume or copy any provider configuration into source.

The upstream release has unrelated URL-bearing log sites, including VOD and
input-manager diagnostics. This candidate eliminates credential exposure in
the maintained transform path; it is not a claim that upstream has a complete
repository-wide URL-redaction policy. Treat a broader log-redaction audit as a
separate security change so it can be reviewed without widening this media
compatibility update.

## Candidate build and isolated transport fixture

The production container must **not** be recreated from the upstream image with
the old 0.31 bind mounts.  Build a new image from the exact source tree, after
applying this patch, and remove those version-specific Python-file mounts from
the candidate compose service.  Retain the existing nginx directory mount,
resource limits, loopback/LAN bindings, and all environment settings.  The
candidate image must be pinned by the digest produced by the local build; the
upstream 0.33.0 digest above is the immutable base/reference, not the patched
image's digest.

An operator can reproduce the candidate without using an unreviewed moving tag:

```sh
git clone --branch v0.33.0 --depth 1 https://github.com/Dispatcharr/Dispatcharr.git dispatcharr-0.33
cd dispatcharr-0.33
test "$(git rev-parse HEAD)" = 2fa13a6707bdf0dae87e0c494bcd3ca282cdeb3e
git apply --check /path/to/dispatcharr-0.33-habibi.patch
git apply /path/to/dispatcharr-0.33-habibi.patch
docker build --pull=false \
  --build-arg REPO_OWNER=dispatcharr --build-arg REPO_NAME=dispatcharr \
  --build-arg BASE_TAG=0.33.0 \
  -t dispatcharr-habibi-candidate:0.33.0-2fa13a-vodhead \
  -f docker/Dockerfile .
docker image inspect dispatcharr-habibi-candidate:0.33.0-2fa13a-vodhead \
  --format '{{.Id}}'
```

For promotion, reference that exact retained local artifact in the candidate
compose service and verify its image ID before start. Keep the old
`0.31.0@sha256:f81924fa3dbfeb463b3908be7e086bf58aacbd2ba56062bfb555ee3a471acf8f`
image and the prior compose file. Remove only the six version-specific 0.31
Python source mounts; retain the Dispatcharr `/data` and nginx directory mounts
with their existing read/write modes. Do not use an image-name-only pull as a
substitute for the build verification above.

`run-isolated-fixture.sh` performs a synthetic-only acceptance run.  It creates
an empty disposable data directory and never mounts the live Dispatcharr data,
nginx directory, provider configuration, or a media path.  It covers:

- authorised XC `HEAD` (metadata only) and denied `HEAD` through the Django
  route fixture;
- proof that `HEAD` does not invoke `stream_ts`, reserve a stream, or register
  a client;
- owner and follower quiet-buffer behavior, including the 188-byte null TS
  keepalive packet and the five-empty-read gate;
- Redis-unavailable new-owner denial, while contention remains a follower
  decision;
- bounded 3–15 second capacity admission, and no retry for non-capacity
  errors;
- the live nginx location's `uwsgi_buffering off`, 300-second stream timeouts,
  and absence of credential-bearing request URLs in the synthetic log capture.

It is not a substitute for a real provider, a client playback test, or a
production database migration.  Its fake account/channel identifiers and URLs
are intentionally non-routable.

The fixture refuses a dirty checkout before applying the patch in place. Its
disposable AIO container and cleanup container both use Docker `--network none`;
PostgreSQL and Redis communicate only within that container. The caller may use
a separate clean checkout for each run.

## Assembled-image evidence (local, 2026-10-28)

The patched exact checkout was built with its upstream `docker/Dockerfile`,
using the pinned `0.33.0` base. The current local-only candidate tag is
`dispatcharr-habibi-candidate:0.33.0-2fa13a-vodhead`; this build produced image
ID `sha256:4156cb520182a3cb6a952936046182c8348113c60d49efd033172a4b18ccf7cd`.
That is a local artifact identifier, not a published registry digest.

It then booted on loopback with an empty disposable `/data`, the candidate
nginx configuration, and no production bind mounts, providers, media, or
credentials.  The assembled nginx/uWSGI/Redis/Postgres application returned
HTTP 200 for the UI; an unauthorised synthetic XC `HEAD` returned HTTP 401.
`nginx -T` confirmed the active `/live/` route has `uwsgi_buffering off` and
the expected 300-second read/send timeouts.  The upstream entrypoint rewrites
its generated nginx configuration at startup, so the isolated configuration
directory has to be a writable disposable copy—matching the live compose
mount's read/write behaviour.  Do not mount the production nginx directory
read-only for this image.

The authorised-`HEAD` no-allocation assertion is covered by the focused Django
suite, not a provider-backed HTTP runtime fixture.  A synthetic media upstream
and real provider playback are deliberately outside this candidate gate.

## Controlled data rollback requirement

Dispatcharr 0.33 can run Django migrations when pointed at an existing data
directory. Before production promotion, stop only Dispatcharr, then take an
application-consistent archive of its `/data` directory **and the writable
nginx tree** to storage with enough free space; record the image/config digest
before starting the patched candidate. The entrypoint can rewrite generated
nginx files, so restoring data without nginx is not a complete rollback. Do not
roll an old image forward against a migrated database. A rollback is the paired
restoration of that stopped-data/nginx archive and the retained 0.31
image/compose file, followed by nginx syntax and local health checks. Provider
secrets, URLs, live data archives, and logs stay private and are never copied
into this repository.

## Private promotion gate

The read-only preflight on 2026-10-28 found six version-bound Python mounts in
the live `dispatcharr` service (not seven): live proxy server, XC credentials,
XC URL utilities, live admission views, TS generator, and VOD XC HEAD views.
The persistent `/data` and writable nginx mounts are separate and must remain.
Two additional Python files in the private patch directory are build tooling,
not live mounts.

The guarded private promotion tool is
`ops/media-maintenance-20261028/update-dispatcharr.sh`. Its default mode only
inspects the exact running image, mount contract, compose syntax, continuity
counts, and aggregate data manifest. Its explicit `--apply` mode requires a
locally loaded candidate image with the recorded immutable ID, a separately
approved XC `HEAD` URL, and an archive directory mounted outside the CT root.
It stops Dispatcharr before archiving its full `/data`, retains its prior
compose/image evidence, removes exactly those six source mounts, and restores
the archived full data plus the original compose/image if migration or health
acceptance fails. It never issues a provider GET or playback request.

Rollback additionally verifies the saved Compose checksum and the restored
active `/live/` nginx block before declaring recovery complete. A rollback
failure exits with a distinct status and writes a private `ROLLBACK-FAILED.txt`
receipt in the retained archive directory; it requires manual recovery rather
than being treated as a successful rollback.

The normal archive destination is outside the CT root. If no safe external
mount is available, the private tool has a deliberately noisy exception:
`DISPATCHARR_ALLOW_ROOT_ARCHIVE=1`. It still refuses unless the CT root has more
than twice the full data-plus-nginx state size plus 2 GiB and more than 20 GiB
total free space. That exception is for a short-lived, immediately copied-off
rollback archive; it is not a default destination for provider configuration.

The separate profile-6 bounded input-retry policy is not a Dispatcharr model or
mount; this candidate does not read, modify, or replace it.

## October28 controlled production result

The exact patched `4156cb52…` image was subsequently promoted after the full
stopped-data/nginx snapshot. All channel IDs, provider/profile settings digests
and continuity counts matched the pre-update state. The actual UI returned200,
the active nginx streaming contract passed, and an existing authorized native
XC metadata-only HEAD returned200 without a provider GET. The compressed
rollback archive was copied to external host storage and its SHA-256 and zstd
integrity verified. Old image and Compose recovery remain retained.
Client playback, long-running provider behavior and physical output acceptance
remain separate from those deployment checks.
