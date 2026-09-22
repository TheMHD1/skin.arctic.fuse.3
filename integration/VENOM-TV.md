# Optional Venom IPTV integration

This is a private-gateway client, not a provider subscription or bundled playlist.
Do not commit IPTV Simple settings, gateway credentials, STRM files, user IDs,
Kodi databases or personal favourites. A second device needs its own authorized
network route and private settings; it does not create another provider slot.

## Kodi / Arctic

**Current layout/favourites supersede the initial deployment below:** Venom 1.3.0
uses a left category sidebar, four-column grids and Jellyfin-account media
favourites. No programme guide is required. See [VENOM-LAYOUT.md](VENOM-LAYOUT.md)
for deployment, tests, exact matching, migration and remaining mobile limitations.

The initial `plugin.video.venom.tv` 1.1.0 read the IPTV Simple instance-1 M3U URL
to find the authenticated gateway. Live playback remains native Kodi PVR.
The custom Arctic Live TV window is labelled Venom TV and provides movie/series
poster widgets, all provider groups, recent channels, guide and favourites.
Movie/series clicks open the full category browser, not only the 30 featured cards.

- Global and category search normalizes Arabic diacritics and tatweel.
- A–Z and recently-added sorting retain search across 100-item pages.
- Recently added means gateway/provider catalogue timestamps, not download date.
- Category posters are derived from an already-fetched catalogue; there is no
  per-category metadata fetch. Missing artwork uses native skin icons.
- API cache: 30 minutes fresh; up to 24 hours stale on network failure; 32 MiB
  response cap. Artwork HTTP failures are separately cached by the gateway.
- Featured widgets read a small derived 30-title cache with the same freshness
  boundary, avoiding a full catalogue parse/sort on every Home visit.
- Initial 1.1 local media favourites are superseded by 1.3 shared Jellyfin media
  favourites. Local-only category bookmarks remain distinct from server media.
- Use Kodi's **Default (Unicode)** interface font for Arabic labels.
- Existing live-TV pause/timeshift remains disabled; do not advertise DVR support.

## Jellyfin / Moonfin

The media server exports the gateway catalogue as private `.strm`/NFO libraries:
Venom Movies and Venom Series. No video is downloaded. Provider category is
retained as a tag and `Venom: ...` genre. Seasons/episodes, posters and descriptions
come from the catalogue. Export is incremental and resumable; Jellyfin indexing
is a separate asynchronous stage, so exported counts are not visible-item counts.
The refresh scheduler skips Active/Queued libraries and prioritizes series on new
requests, avoiding duplicate work in Jellyfin's serial refresh queue.

Habibi-only access is enforced server-side. Other users keep their original
library allowlists and no live-TV permission. On this Jellyfin build the returned
`BlockedMediaFolders` field did not persist through the policy updater; explicit
`EnabledFolders` with `EnableAllFolders=false` is used instead. **Future ordinary
libraries must also be granted explicitly to those users.**

Use Moonfin's Libraries screen or Jellyfin's home library cards. Moonfin 2.5.0
fixed a remote STRM direct-play problem; production logs showed 2.5.1 previously,
but the current handset build must be checked on the handset. Do not force every
remote source to transcode: direct play preserves quality, and the existing Intel
QSV path supplies lower-bitrate HLS when required. No NVIDIA/AI filter is needed
for lossless remux delivery. Client navigation differs; this is not a custom
Moonfin APK or a claim that its live-TV UI equals Kodi's PVR guide.

Native Venom playback bypasses Jellyfin and does not report its resume position.
Playback through Jellyfin/Jellyfin for Kodi does use Jellyfin's watched-state path.

## Keep the normal Home fast

The Home companion supports optional private userdata `home-library-scopes.json`:

```json
{"movies":["ORIGINAL_32_HEX_LIBRARY_ID"],"shows":["ORIGINAL_32_HEX_LIBRARY_ID"],"episodes":["ORIGINAL_32_HEX_LIBRARY_ID"],"toprated":["ORIGINAL_32_HEX_LIBRARY_ID"]}
```

Use real original-library IDs, including anime if desired. Resume, next-up and
favourites stay server-wide. Omit the file to retain unscoped behaviour.

The Jellyfin Kodi patch additionally accepts private `sync.json` configuration:

```json
{"ExcludedLibraryPaths":{"/config/venom-catalogue/movies/":"REAL_LIBRARY_ID","/config/venom-catalogue/series/":"REAL_LIBRARY_ID"}}
```

Merge this field into the existing sync file while Kodi is stopped; never replace
the whole file with this example. Explicitly whitelisting an excluded library
overrides the optimization. This prevents a large unsynced IPTV import from
issuing one ancestors API lookup per changed item. No library content is deleted.

## Validation and updates

`python integration/check.py` validates clean patch application and regressions,
including scoped Home ordering and excluded-library ancestry behaviour. Venom's
separate tests exercise search, pagination, featured cards, ID validation, local
favourites and isolation from live-TV seek handling. The deployment also tested
real movie/Arabic episode playback, seek, real favourite add/remove and mobile HLS.

Provider allowance remains one independent stream. A bounded test shared one
live channel across two downstream clients; a different second channel got 503.
Dispatcharr 0.30.0's ownership fix must remain paired with its pinned version:
Redis SET NX returning None means lock contention, not successful ownership.
The bounded diff is `patches/dispatcharr-live-ownership.patch`; it is a server-side
patch and is not applied by the Kodi integration check. Check it against exactly
Dispatcharr v0.30.0, test ownership contention/unavailable Redis, then mount the
patched file read-only. Never transplant the full old module onto a new release.
Re-test release-to-zero after upgrades; do not mask capacity bugs by raising
the advertised subscription limit or blindly clearing counters during playback.

Keep server backups private. They include gateway PostgreSQL, configuration,
SQLite-consistent import progress and the generated STRM/NFO catalogue. Kodi's
private backup includes settings and local favourites. No restore rehearsal or
all-provider-title playback test is implied by the bounded acceptance checks.

## Storage protection (required for a large first import)

A bulk import exposed a large retained SQLite WAL, filling the media system disk
and breaking new logins. Do not remove live database/WAL files or indiscriminately
purge poster caches. Use SQLite checkpointing and retain useful metadata.

`server/venom-storage-guard.*` contains the deployed bounded safeguard. Install
the Python script under `/data/config/iptv-venom/`, create an isolated environment
at `storage-guard-venv` (using uv, or python3-venv/venv), and install the pinned
`venom-storage-guard-requirements.txt` into that environment. Install the service
and timer under `/etc/systemd/system`, daemon-reload, then enable/start the timer.
Run `test-venom-storage-guard.py` with that same environment before enabling it.

It checks every two minutes, requests a checkpoint above 256 MiB, and retries
later if readers/writers are busy. It uses patched SQLite via APSW rather than
the older system Python SQLite; it does not replace Jellyfin's bundled engine.
Threshold is not a hard WAL size cap. The server exporter and refresh scheduler
also defer new work below 8 GiB free. Keep genuine storage headroom: checkpoints
cannot force an active transaction to finish, and unrelated workloads still write.
The private incident document holds the host-specific capacity/health evidence.

Sources: [Moonfin releases](https://github.com/Moonfin-Client/Moonfin-Core/releases),
[STRM issue](https://github.com/Moonfin-Client/Moonfin-Core/issues/860),
[Jellyfin libraries](https://jellyfin.org/docs/general/server/libraries/),
[Intel acceleration](https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/intel/).
