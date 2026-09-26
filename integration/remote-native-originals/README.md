# Conservative remote P7-original gate

This optional component permits a remote AM9 to open the original Dolby Vision
profile 7 file over its private NFS route only when its currently indexed
Jellyfin P8.1 compatibility file has the same embedded audio/subtitle layout.
It is not a general Dolby Vision switch.  Missing, expired, malformed, stale,
or mismatched entries use the existing HTTPS/P8.1 path without changing the
Jellyfin account, the original P7 master, or the compatibility-view publisher.

`manifest.py` is run on the media side with an **explicit scoped source list**.
It requires all of the following before atomically publishing an entry:

- canonical `/data/media/movies|shows/...mkv` is current, regular and DOVI P7;
  P7 MEL and FEL are both eligible—no enhancement-layer inference is made;
- the precise `dovi-p8` companion is current, regular and DOVI P8;
- `jellyfin-view` is the companion's exact inode;
- both ffprobe calls succeed without a source/companion change during probing;
- duration differs by at most one second; and
- the ordered embedded audio/subtitle signatures match exactly: stream index,
  type, codec, language, title, default/forced flag, audio channels and audio
  channel layout.  External subtitle sidecars are intentionally outside this
  container test because Jellyfin maps them separately.

The generator has no server address or credentials.  Keep actual input paths,
generated manifests and deployment logs private.  Fake fixtures are used in
the test suite.

The intended shared output is
`/data/media/compatibility/_remote-native/verified-p7-v1.json`; it is outside
the Jellyfin view and is exposed to the restricted NFS client as
`/.native/verified-p7-v1.json`.  The generator writes a 0644 file atomically;
the shared parent must be root-managed and 0755.  The manifest contains no
secrets, but its paths remain private because its NFS export is device-scoped.

The Kodi integration first performs the existing 0.5-second private
NFS TCP preflight, then reads at most 3 MiB from its read-only NFS manifest and
call `gate.allows_native`.  It must compare the original VFS size/mtime (and
inode when VFS reliably supplies it), current Jellyfin P8 source `Size`, and
the current Jellyfin embedded `MediaStreams` semantic signature.  Jellyfin 12
may prepend external sidecars and renumber every stream; their indexes are
validated for uniqueness but are not compared to raw ffprobe indexes.  Any read/VFS failure falls
back to HTTPS.  Kodi Python cannot safely time-limit an individual VFS call,
so this gate never treats a failed/hung manifest read as approval.

`kodi_adapter.py` defines the concrete opt-in boundary used by the separate
remote-device builder: `remote_original_path(item, source, force_transcode,
...)`.  Its private `remote-originals.json` configuration is deliberately
device-bound and only admits these exact roots:

```json
{
  "schema": "remote-native-originals/config-v1",
  "enabled": true,
  "hostname": "example-am9",
  "wifi_mac": "00:11:22:33:44:55",
  "mappings": {
    "/data/media/movies/": "nfs://100.64.0.1/movies/",
    "/data/media/shows/": "nfs://100.64.0.1/shows/"
  },
  "manifest_uri": "nfs://100.64.0.1/.native/verified-p7-v1.json"
}
```

The host/address above is documentation-only.  The two NFS mappings and the
manifest must resolve to one literal private/CGNAT host; the config does not
offer a directory-prefix escape hatch.  The adapter keeps global
`useDirectPaths=0` and `data.json.paths=null` so every non-approved item stays
on HTTPS.  Its private configuration and manifest are never committed.

Example shape only—do not use real library paths as a broad scan:

```sh
python3 manifest.py --output /private/staging/remote-native.json \
  --source /data/media/movies/example.mkv
```

For the server's bounded periodic publication, use `--scan-companions` with a
private rejection report.  It enumerates only the exact
`movies|shows/**/* - P8.1 Compatibility.mkv` names, derives their canonical
counterparts, and refuses to overwrite the previous manifest if enumeration is
incomplete or exceeds 8,192 entries.  Individual invalid/mismatched pairs are
omitted and recorded in the mode-0600 report; that is a safe HTTPS fallback,
not a claim that those originals are playable natively.

The manifest expires after 24 hours. The supplied service/timer rescans current
companions every30 minutes on the ARR/media host (not the administration server),
and publishes atomically. Failed/incomplete scans retain the previous snapshot;
expiry eventually disables native selection safely. Do not make native P7 the
fallback while the manifest is absent.  Source provenance remains a separate
constraint: equality of current layout and duration cannot prove that two
different encodes originated from the same release.  The existing converter's
source-to-companion provenance work must remain authoritative.

The runtime identification accommodates Jellyfin12's external-subtitle prefix
and index renumbering. It validates unique Jellyfin indexes, then compares ordered
embedded track semantics with ISO639-2 B/T aliases and equivalent channel-layout
spelling normalized. The producer still requires exact original/companion
container-index equality. No playback index, subtitle map or server history is
rewritten.

Run locally without media access:

```sh
python3 integration/remote-native-originals/test_remote_native_originals.py
```
