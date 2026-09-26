# Remote original P7 layer — September 26, 2026

Apply this additive layer **after** the remote R6 → R7 → search/ratings release.
It preserves global `useDirectPaths=0`, the remote Venom marker, public HTTPS,
account/device identity, and `data.json.paths=null`. Only the explicit private
`remote-originals.json` opt-in permits the new, guarded original-file branch.
It does not modify the original local AM9 cohort or Jellyfin's server core.

Prerequisites are the [restricted private network](../../device-policy/private-tailnet/README.md),
the exact read-only NFS export/bridge, and the
[automatically refreshed compatibility manifest](../../remote-native-originals/README.md).
Do not enable this option merely because the box can SSH or display a DV logo.

## Build and install

```sh
python3 integration/release/remote-originals/build.py --output /tmp/remote-originals-payload
python3 integration/release/remote-originals/test_release.py /tmp/remote-originals-payload
python3 integration/remote-native-originals/test_remote_native_originals.py
python3 -m unittest discover -s integration/device-policy/private-tailnet
```

The builder fetches pinned Jellyfin-for-Kodi source, applies the reviewed2.2/TLS
patches, recreates the exact historical remote HTTP condition, verifies the
whole-file hash, then inserts the optional original-file hook. `--input` may
instead supply the exact already reviewed remote source; drift is rejected.
The local Native patch is deliberately not blindly stacked on the remote variant.

Copy this directory's `build.py`/`install.py` plus sibling
`../kodi/transaction.py` with their relative layout, the generated payload,
the existing private remote profile, and a reviewed native opt-in configuration.
On the idle target:

```sh
python3 integration/release/remote-originals/install.py \
  --profile private-device-profile.json --config private-native-profile.json \
  --payload payload
# Review identity, paths, source hashes and planned changes before applying.
python3 integration/release/remote-originals/install.py \
  --profile private-device-profile.json --config private-native-profile.json \
  --payload payload --apply
```

The installer checks every existing tracked source against the device manifest,
the exact Jellyfin version, remote account/HTTPS route, disabled global Native
mode, hardware identity and private configuration. Only complete reviewed source
cohorts are accepted; the first headless test cohorts are explicitly enumerated
to permit their safe semantic-normalization repair. It transactionally backs up
files, stops Kodi once, rechecks all inputs, installs, updates the device's
integrity manifest, restarts and verifies RPC readiness. A second identical run
is a no-op. Power loss still requires manual recovery; keep off-device backups.

The original remote installers are not weakened to accept arbitrary drift.
When updating another component, preserve these additional manifest entries and
rebase this layer explicitly. Never regenerate an integrity manifest merely to
hide a source mismatch, or reinstall stock Jellyfin over the gated addon.

## Runtime contract and acceptance

Jellyfin12 inserts external subtitles before its container streams and renumbers
all indexes. The producer still checks exact P7/P8 container track indexes;
the runtime check validates unique Jellyfin indexes but compares ordered embedded
track semantics, excluding external sidecars. It normalizes only equivalent
representations: PGS codec aliases, channel-layout suffixes, and the20
[ISO639-2 B/T language synonyms](https://www.loc.gov/standards/iso639-2/php/code_list.php).
It does not merge distinct languages or reassign playback/session track indexes.

Current-source file size/mtime/inode, current companion size, logical path,
duration and embedded track layouts must match. Missing/expired/mismatched
entries, offline transport and forced transcoding keep the prior HTTPS branch.
Live TV, provider VOD/STRM and ordinary non-P7 files are not converted to NFS.

The manifest establishes **current layout compatibility**, not cryptographic
proof that an old companion was derived from the current original's video.
The existing companion-provenance gap remains documented; this deployment does
not rewrite or certify those files. Canonical library path identity remains the
existing publisher's responsibility. Never describe all entries as fully
provenanced or all remux editions as byte-identical.

Accept with actual Kodi Python/VFS, not only a TCP test: read the manifest, stat
the original, exercise the real selector against current account metadata, read
a bounded original byte range, and verify forced-transcode/offline fallback.
Then test real LG/JBL display, P7/FEL decoding, audio/subtitles, seek/resume and
Bell-house sustained throughput with bitrate headroom. Headless reads do not
prove any of those physical/WAN properties. A connected but stalled NFS VFS call
or midstream network failure is not transparently recovered; the0.5s TCP check
bounds only an unreachable endpoint. No claim of seamless midstream fallback.

Immediate rollback: disable/remove only this device's `remote-originals.json`
opt-in (retain it privately), leaving HTTPS and normal account access intact.
For complete source rollback, stop Kodi and restore the transaction's changed
files and integrity manifest as a set. Revoke the device-specific export/grant
as well if removing private media authorization; account logout alone is not
NFS revocation.
