# Kodi XC movie and episode metadata checks

The reviewed Dispatcharr XC movie/episode endpoints accepted GET but rejected
HEAD with 405. Kodi uses HEAD to inspect a file before opening it; fallback GET
checks can create competing short-lived sessions and exhaust the provider's
single playback slot. The actual failure returned 503 at provider-profile
selection, not missing episode identity. A retry after an appliance reboot
reproduced it, so a released old live stream alone did not explain the failure.

This overlay accepts HEAD on the two native XC endpoints only. It preserves
network policy, saved-password authentication, movie/series entitlement and
active provider relation checks before returning metadata. HEAD creates no
provider request, stream slot, session or redirect. Actual GET and the separate
FUSE HEAD route remain unchanged. This is not a provider-limit bypass or a
claim that metadata success proves provider availability.

The response uses an empty streaming response so normal middleware does not
invent Content-Length 0 for an unknown-size file. GET owns the real file size,
seek/range behavior and stream-slot lifecycle. No false full-file length is
published and there is no new polling or retry loop.

## Exact source and deployment

Reviewed image: `ghcr.io/dispatcharr/dispatcharr:0.31.0` with digest
`sha256:f81924fa3dbfeb463b3908be7e086bf58aacbd2ba56062bfb555ee3a471acf8f`.
Base VOD views SHA256:
`915398069f95d0bfa6ac11e4125a9b3cb4485cbbc34e101cf1e955af0e0efec5`.
Built VOD views SHA256:
`f3559ab217d0a13113f77a192af2159aac5f0803a572ac1264f46f338b163420`.

`build.py` requires the exact input bytes and alters only the HTTP import and
two XC functions. Its public extracted fixture is test-only, not an installable
module. Ten regressions execute the transformed actual XC functions covering
authorized metadata, no slot-producing GET call, no fake size, invalid/missing
passwords, network/entitlement denial, missing relations and unchanged GET.

```sh
python3 -m unittest discover -s integration/server/vod-xc-head
python3 integration/server/vod-xc-head/build.py /PRIVATE/views.before.py /PRIVATE/views.built.py
```

For installation, place `build.py` and `install.py` together in a private staging
directory on the reviewed single-service Media host. The installer requires
root, its explicitly supplied exact hostname, the pinned image and the existing
live-TS mount anchor. Run without `--apply` first. The apply step privately backs
up original source/Compose bytes, adds exactly one read-only VOD source mount,
validates Compose, recreates **only Dispatcharr**, then verifies in-container
bytes. Existing live-proxy mounts and all unrelated configuration are retained.
Caught installation failures restore the original Compose and recreate its
original container. Power loss during deployment requires the private backup.

```sh
python3 /PRIVATE/staging/install.py --host PRIVATE_EXPECTED_HOST --compose /PRIVATE/compose.yml
python3 /PRIVATE/staging/install.py --host PRIVATE_EXPECTED_HOST --compose /PRIVATE/compose.yml --apply
```

Before updating Dispatcharr, extract the candidate's stock module and rebase
this small transform/tests against it. Do not retain the old whole-module mount
under a new image or relax the source/digest guard. Native client addon cohorts
and their receipts are unchanged. Server repair applies to both cohorts; this
operation did not change the remote appliance or certify its playback.

## Acceptance and rollback

October 12 deployed source/read-only mount and image pins passed. Actual native
episode HEAD returned 200 without a size or body; incorrect password returned 401
and nonexistent episode 404. The provider counter was unchanged by these checks.
The appliance's subsequent bounded Range GET returned 206 and 65,536 actual
media bytes from the formerly failing episode without interrupting its library
playback. This is transport acceptance, not a complete native Kodi playback test.
Arabic/English keyboard selection is a separate native Kodi policy.

The local appliance subsequently played the requested episode from its genuine
4K native library file. That playback is not acceptance of the Venom route;
the owner's active library playback was preserved. Record any bounded native
Venom GET/stream check separately, and repeat cold play/seeking/stop/reopen on
Kodi during a later authorized idle window before claiming full UI acceptance.

For rollback, restore this host's saved Compose bytes and recreate only
Dispatcharr when interruption is authorized. Keep all persistent data, original
live mounts and image pins. Retain the private newly generated overlay as
evidence; do not replace current episode IDs or delete media/catalogue entries.
