# Portable September 22 source release

The later optional [remote-originals layer](remote-originals/README.md) adds
restricted-network P7 selection after the complete remote parity chain. It is
separate from the local Native branch in the historical R6 builder below.

For the subsequent local R7 Home/search rollout, use
[`library-experience/README.md`](library-experience/README.md). The original R6
builder below intentionally uses preserved historical inputs in
`kodi/baseline-r6/`; current Home source must not silently alter its hashes.
Server/Web/notification changes are indexed in
[`../LIBRARY-EXPERIENCE-2026-09-22.md`](../LIBRARY-EXPERIENCE-2026-09-22.md).

This directory preserves the reviewed Kodi/Jellyfin/Arctic changes as source,
builders and fail-closed update tooling. It is not a blank-device installer and
does not contain credentials, device identities, private paths, userdata,
runtime manifests, backups, logs, firmware, or provider configuration.

## Build and verify

From the fork root, either let the builder fetch the pinned Jellyfin commit or
give it a clean checkout at that exact commit:

```sh
python3 integration/release/kodi/build.py --output /tmp/habibi-payload
python3 integration/release/kodi/test_release.py /tmp/habibi-payload
python3 integration/release/handoff/test_profile.py
python3 integration/release/handoff/test_http_retry.py
```

The builder applies `jellyfin-2.2.0-habibi.patch`, the secure-TLS patch and the
native-original patch in order, installs the reviewed native helper, takes Home
search and Venom sources from this checkout, applies the remote Venom overlay in
a temporary tree, and verifies every output hash. With `--jellyfin-source`, it
requires the pinned commit and an entirely clean checkout, then clones only its
committed object. Generated payloads are release artifacts and are not committed.

The older installed-cohort sample was moved out of the installable add-on to
`integration/examples/verified-build-20260914.json` and is explicitly historical.
The builder never copies it. The guarded installer requires the target device's
live manifest and updates that exact manifest transactionally from the files it
actually replaces. A new-device baseline is generated only after that device's
complete reviewed installation and acceptance; this release does not guess one.

## Guarded existing-device update

Copy `kodi/install.py`, `kodi/transaction.py`, `kodi/rebuild.py`, a generated
payload, and a private profile based on `kodi/profile.example.json` into one
staging envelope. Run on the target only while idle:

```sh
python3 install.py --profile private-profile.json --payload payload
# Review the plan, confirm Kodi is idle, then explicitly apply:
python3 install.py --profile private-profile.json --payload payload --apply
```

The installer accepts only reviewed addon versions and complete source cohorts.
Every touched Home, search-template, Jellyfin HTTP, Venom and native-original
source is checked against an allowed whole-file hash and its existing live
manifest entry. Already-installed files receive the same checks. Hardware,
account, hostname, routing marker, Native/add-on mode and path mappings must
match the private profile. It snapshots all read inputs, checks idle state twice,
backs up replacements, revalidates after Kodi stops, writes atomically, and
rolls back on ordinary errors or an interactive `KeyboardInterrupt`.

Power loss, kernel failure, `SIGKILL`, or storage loss can interrupt Python
without running rollback. Retain the printed backup and inspect/restore it
manually before retrying. `SIGTERM` is not claimed as guaranteed recovery.
After success, run `rebuild.py` through Kodi and complete physical search,
TLS, IPTV switching, direct-play, seek/resume, subtitle, audio and HDR checks.

Remote output is supported through the exact R6 bridge followed by the remote
R7 and search-priority overlays. It is not evidence that a remote device was
deployed or physically accepted; see [the remote parity record](../REMOTE-AM9-PARITY-2026-09-26.md). Use
`kodi/profile.remote.example.json`: it binds an approved public HTTPS hostname,
requires verified TLS/no native paths, and the installer never creates,
removes, or copies the private remote marker.

## Deliberate remaining boundaries

- The Dispatcharr 0.31 admission/transport source patches and nginx template
  remain canonical under `integration/patches/` and `integration/server/`.
  This release does not turn deployment-specific container mounts, credentials
  or image state into a universal server installer.
- The hybrid CoreELEC updater is exact-device maintenance. Firmware tarballs,
  disk UUIDs, MACs and boot-media layout are intentionally not public payloads.
- A new device must first install the documented matching addon versions,
  authenticate locally, create its own live integrity manifest and private
  profile, and establish its own safe media mappings. This updater will refuse
  an unreviewed or blank source tree rather than bootstrap it.

See `../SECOND-UGOOS.md` for the setup entry point, `../UPDATING.md` for update
policy, and `handoff/README.md` for the separate bounded live-profile retry.
