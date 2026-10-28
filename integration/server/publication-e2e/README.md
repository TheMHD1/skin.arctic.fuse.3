# Isolated real-Jellyfin publication acceptance

This opt-in harness runs the maintained scoped media reconciler, new-title
Library Experience plugin and raw-subtitle arrival worker against a real,
disposable Jellyfin server. It does not contact production, download media,
use production accounts, start an AI/GPU engine, or change system timers.

Reviewed cohort: Jellyfin 12.1 custom image
`jellyfin-custom:12.1-onepace-20260918`, native source commit
`ee91c75e777da41a9c4f4855e70adc604fbf2ef8`, and plugin 1.2.0.0 with its exact
Controller assembly guard. The image must already exist locally; the harness
never pulls an image. A different reviewed cohort requires an explicit `--image`
and `--expected-version` choice plus its rebuilt matching plugin DLL/metadata.
Only the reviewed12.1 and12.4 versions are accepted; an arbitrary version string
cannot bypass the native server check or matching plugin ABI metadata guard.

## Run

Build the plugin using its pinned-source instructions first. The host needs
Python 3, Docker, FFmpeg with libx264/AAC, and FFprobe.

```sh
python3 integration/server/publication-e2e/test_harness.py
python3 integration/server/publication-e2e/run.py
python3 integration/server/publication-e2e/run.py --run
```

For12.4, add `--expected-version 12.4 --image ALREADY_LOCAL_REVIEWED_IMAGE
--plugin-dll PRIVATE_BUILT_DLL --plugin-meta MATCHING_META_JSON`. A private
`--fixture-parent` with enough free space avoids a small `/tmp` tmpfs. These
options remain side-effect-free without `--run`.

Optional `--artwork` also sends the actual reconciler's accepted IDs through
the executable exact-artwork enqueue path. A missing Primary must produce one
native item-only image refresh, stay in verification without reposting, then
complete when the fixture uploads a synthetic local image through Jellyfin's
normal elevated image API. The latter simulates image arrival, **not an external
metadata/image-provider download**. No household artwork is removed for a test.
The all14-plugin LinuxServer12.4 candidate
`sha256:024764b09599bc10c1284a80abc5a970e7a6b6c91dc5b8ed4c0158f10eda68f9`
passed all13 assertions including these two artwork checks on October28.
The subsequent full-feature image, including rebuilt custom Moonbase and the
merged Live TV Categories Web bundle,
`sha256:b2faebcb6d0f9f4ee3172072e9caa58a0970f462c495314c1ec8c9a7ca8da34f`,
also passed all13 assertions with normal fixture cleanup. This does not upgrade
production or prove physical category-screen/client playback acceptance.

Without `--run` this prints a plan and performs no fixture construction or
Docker calls. An explicit run creates randomly named temporary directories,
one owned container and one owned **internal** Docker network. Docker internal
networks do not publish ports, so an ephemeral HTTP relay binds only
`127.0.0.1`; its forward target is that private container. This independently
blocks external catalog access. Native library settings also disable remote
providers, realtime monitoring, metadata saving and image extraction. No host
media, config, credentials, Docker socket or production database is mounted.

The image uses `/config/data/plugins`; the harness copies only the locally
built DLL and manifest there. Native startup APIs create a fixture-only admin
with a random password/token. Those values are never printed. Temporary
worker/post-sub config files containing the token have mode 0600. Container
logs and database files are private fixture artifacts, not committed evidence.

Native APIs first add empty Movies and Shows libraries. One **initial fixture
scan** is then allowed to establish their physical roots using an unrelated
anchor movie and episode. Jellyfin skips wholly empty physical roots, leaving
no native parent Folder and no `PhysicalFolderIds`; the plugin intentionally
fails closed in that state. This is an established-library import endpoint,
not a replacement for commissioning an entirely empty new library. The anchor
items also provide unrelated-title preservation assertions. The initial
scheduled task execution result is captured.
After that, every acceptance step requires the scan task to remain Idle with
the identical execution result. New movie and episode files are generated only
after this baseline. Compatibility view directories are bind-mounted onto
Jellyfin's canonical media paths, just as in the deployed path namespace.

## Assertions

- A real tiny movie and series episode pass through the actual maintained
  scoped-file reconciler, view hardlink, plugin discovery and native indexed
  file media source, without another global scan.
- Duplicate events preserve one exact native item ID and do not duplicate
  native items.
- Synthetic provider IDs supplied through the actual reconciler survive native
  creation; a duplicate plugin call returns the existing ID with `Created=false`,
  a conflicting ID returns 409 without overwriting it, and unauthenticated
  discovery is rejected by the real server's elevation policy.
- Actual `subtitle-raw-arrival.py arrival/work` durably records an Arabic SRT,
  creates its allowed view entry, resolves and refreshes only its exact native
  episode, and acknowledges only after `served_exact` succeeds. That verifier
  uses `subtitle-jellyfin-sync.normalized`: UTF-8 BOM, CRLF and trailing
  whitespace normalize to the same SRT cues. Native VTT serving is checked too.
- Atomic replacement of subtitle A with B must complete and serve B, not stale
  cached A. Neither revision needs an AI engine or complete season.
- The media outbox drains with no deadletters, after native file-source
  indexing, not merely an accepted HTTP response.

Only fixture SQLite due/cooldown timestamps are advanced to keep the run
bounded; no production retry state, server clock or retry implementation is
modified. Synthetic video is known SDR. A small fixture `mediainfo` adapter
validates it with real FFprobe and emits the explicit SDR separator: **this is
not HDR/Dolby Vision probe/conversion acceptance**. This harness also does not
exercise an ARR hook, a real downloader, client playback, GPU generation or
physical device output. Those require separate unit/real-device evidence.

Cleanup removes only the exact generated container/network and temporary
directory, including after normal Python exceptions. `--keep` retains the
private fixture directory for investigation, but still removes its container,
network and loopback relay. Forced process death can leave owned resources;
inspect their exact `publication-e2e-...` names before manual cleanup. Never
use a broad cleanup or production container name.
If LinuxServer S6 leaves root-owned fixture directories, cleanup uses an
entrypoint-overridden, network-disabled helper mounting only the exact generated
fixture to repair its ownership before deletion. It has no parent/media mount.
Six cheap safety tests cover no-run behavior, generated identities, scan
invariants, exact cleanup targets and that permission-repair boundary.

## Update/recreate acceptance

Rebuild the plugin from the new reviewed native source before changing
Jellyfin. Its ABI/version guard must not be bypassed. Run plugin unit tests,
publisher/arrival tests, these safety tests, and this real-server harness with
the explicitly chosen local image. A failing plugin load, authorization,
physical-root identity check, path resolver, API serialization contract,
subtitle indexing/serving, idempotency or scan invariant blocks acceptance.
The summary records the actual immutable Docker image ID and plugin SHA-256,
not a mutable tag alone. Preserve source changes/pins and rebuild instructions
in the release manifest; do not commit generated DLLs, fixture tokens, media,
databases or raw logs. Isolated acceptance supplements, not replaces, the
production exact-title canary and client playback checks.
