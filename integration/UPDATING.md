# Controlled update workflow

## Current release authority

For the remote-house AM9, follow the
[September 26 parity record](REMOTE-AM9-PARITY-2026-09-26.md), not the historical
remote-not-deployed notes below. The guarded source chain is remote R6 bridge →
remote R7 Home/search → search/ratings; use the fake-only
`release/kodi/profile.remote.example.json` to construct a private device profile.
Its expected HTTPS hostname is explicit. Preserve the remote marker, verified
TLS and disabled Native mode. The standalone SD CoreELEC20260926 update is a
separate operation from the local AM9's hybrid20260922 procedure; never exchange
their UUIDs, boot-layout scripts or account configuration.

The [September 26 import/request repairs](IMPORT-REQUEST-REPAIRS-2026-09-26.md)
record native naming/indexer/permission changes, bounded request-search recovery
and the Seerr request-privacy overlay. Seerr's compiled overlay is exact-version
pinned and startup guarded: review/rebuild it before changing the image. Do not
remove its guard or readonly mounts merely to make a new version start.

The same record covers the deployed exact-import and subtitle publishers. Keep
their queues/databases, private keys, timers and volume mappings persistent;
do not replace them with the sanitized converter reference or copy private
runtime configuration into Git. A bind-mounted individual ARR hook file requires
container remount/recreation after atomic replacement: check the in-container
hash, not only the host file. The subtitle timer retains its existing Bazarr
Docker execution context and must not be duplicated under a new unit name.

Library Experience 1.2 uses an exact Jellyfin 12.1 assembly guard. Before upgrading
Jellyfin, build against the candidate's reviewed source, run all plugin and worker
regressions, then run the [isolated publication fixture](server/publication-e2e/README.md)
against the actual candidate image/plugin. Confirm new Movie/Episode discovery,
duplicate identity, provider conflicts, replaced served subtitles and unchanged
global scan state. Rebase the guard only after acceptance; do not silently fall
back to a whole-library scan. Keep the prior image/plugin and private worker
backups for rollback. Existing native library items remain usable if discovery
is temporarily unavailable; bounded pending jobs retain their error evidence.

For the library-only Home rows, IMDb bridge/updater and revised search priority,
apply the paired, version-pinned components in
[HOME-RATINGS-2026-09-23.md](HOME-RATINGS-2026-09-23.md). Web alone is insufficient
to position Enhanced Discover ahead of Venom. Use the normal authenticated
plugin bridge; never copy an administrator key into a client or published fork.

[CUSTOMIZATIONS.md](CUSTOMIZATIONS.md) is the public feature/status inventory.
`release/README.md` is the portable build/update entry point. Its Kodi builder
uses exact clean inputs and writes generated payloads only to a caller-selected
staging directory. `install.py` and `transaction.py` require a private profile
and perform the reviewed version/source/manifest/idle/backup/rollback workflow;
`rebuild.py` is the separate post-install template step. The release tests cover
both the local-PVR and remote-Jellyfin cohorts.

The local/LAN r6 cohort is installed and physically accepted. The remote-house
r6 overlay is built and tested but not deployed. The separately authorized
[September 23 CoreELEC hybrid update](COREELEC-HYBRID-UPDATE-2026-09-23.md)
is complete on the local AM9; this does not authorize future firmware updates.
The portable release is an **exact-cohort addon update**, not a blank-device
bootstrap, firmware updater or general Dispatcharr installer. Generated payloads,
real profiles, credentials and rollback archives never belong in Git.

The repository-root Arctic tree is a legacy 3.2.19 integration baseline, not
the installable current skin. Current 3.3.1 devices use reviewed upstream 3.3.1
source with `patches/arctic-3.3.1-habibi.patch`, followed by the r6
search/template overlay. Do not relabel or package the root tree as 3.3.1. The
release installer expects the exact reviewed 3.3.1 cohort and must reject the
legacy tree; it is not a 3.2.19-to-3.3.1 migration tool.

## September 22 live XC transport and admission

The canonical `patches/dispatcharr-live-admission.patch` targets the exact
reviewed 0.31.0 live-proxy view. It adds bounded monotonic capacity waiting and
authenticated metadata-only HEAD support to `stream_xc`; it does not increase
provider capacity or evict another viewer. Pair with the `/live/` non-buffered
uWSGI location in `server/dispatcharr-nginx.conf`. Authentication stays in the
application, never a blanket nginx HEAD success response.

The first admission-only revision did not pass live switching. HEAD/probe GET
and buffered disconnect handling were separate causes, so preserve the paired
fix. Rebase the patch against a future actual upstream source, run admission,
HEAD authorization/format and exact GET regression tests, then check cold play,
A→B→C switching and same-channel reopen on Kodi. A HEAD 200 proves entitlement
and metadata only, not upstream availability. Keep profile limits and normal
same-channel grace unchanged.

On a bind-mounted Python file, atomic replacement needs an explicit container
recreate to replace the old mounted inode. Verify the in-container hash after
deployment and rollback. Preserve the existing ownership, credentials and URL
compatibility mounts. The private execution record keeps device results,
version-pinned build/deployment scripts and exact rollback paths.

The paired `patches/dispatcharr-disconnected-keepalive.patch` targets the exact
0.31 TS generator. Its final revision lets all workers use the existing bounded
keepalive path after five empty reads at the buffer head, independently of
shared upstream health. It uses a valid payload-only null TS packet; real
buffered data wins. It does not preempt viewers or release slots. Test packet
bytes/PID/AFC, both worker roles, the empty-read gate, broken-write cleanup,
another-viewer preservation and unchanged cap/grace/capacity semantics. The
first owner-only revision missed followers and is superseded. One early live
handoff decoded successfully while its return was rejected with upstream HTTP
403. A later bounded r6 client handoff and exact-403 profile mitigation passed
the final local device switch/reopen acceptance. This does not prove that every
provider 403 or arbitrarily long outage will recover.

## September 22 search / TLS update

The Movies/TV search template now uses Jellyfin Home `searchmovies/searchshows`
instead of the local Kodi database. Deploy the companion `search.py`, updated
client/default files and the search template together, retaining per-user Home
library scopes. Test `spider man`, `Spider-Man` and `spiderman` against owned
titles before declaring device acceptance. Discover remains an independent row.
These routes and their generated templates were accepted on the local/LAN r6
device; the remote-house cohort still needs on-screen acceptance.

After the consolidated 2.2 patch, apply `patches/jellyfin-tls-secure-default.patch`:
unset request-client certificate policy now verifies TLS by default; explicit
configured policy is preserved. `check-catchup.py` verifies clean application.
The secure default is part of the accepted local cohort. Preserve explicit
certificate policy and retest the remote HTTPS cohort when it is deployed.

## September 22 Native-original selection

After the consolidated 2.2 and TLS patches, apply
`patches/jellyfin-native-originals.patch` and install `jellyfin_native_originals.py`
as `jellyfin_kodi/helper/native_originals.py`. `check-catchup.py` covers the full
patch stack and twelve focused policy/real-method tests. Do not deploy just
the patch without its helper, and do not stack this on a separate remote HTTP
variant without an explicit rebase/review.

This is an existing-Native-mode opt-in, not a username or reported DV-profile
override. It uses exact configured NFS mappings for direct-play-capable library
Movie/Episode files while preserving `playFromStream=true` for other sources.
The existing server P7-to-P8.1 converter and compatibility view are unchanged.
Keep Kodi NFS filenames literal; percent-encoding spaces/Unicode breaks actual
NFS filename lookup. The 0.5-second TCP probe only bounds a dead host/port check,
not Kodi VFS or midstream faults. Physical P7/audio/subtitle/resume acceptance
passed on the local/LAN cohort. Remote original-file delivery is not implemented
by this patch and must remain disabled until its separate private route and
throughput/fallback gates pass.

See [the September 18 Venom recovery](VENOM-RECOVERY-2026-09-18.md) for the
general channel-ID playback fallback, paired KodiSyncQueue/client catch-up fix,
12.1 web build, category batching/order, verification and rollback locations.
Run `python3 integration/check-catchup.py` for the maintained 2.2 catch-up patch;
the older checker is not a complete 2.2 compatibility test.

The [September 18 fleet record](FLEET-MAINTENANCE-2026-09-18.md) records the
Jellyfin 12.1 / Enhanced 12.7 source patches, Dispatcharr 0.31 HLS compatibility
fix, verified rollback state and Kodi category-outage recovery. Rebase those
version-specific patches when updating their upstream components.

## AM9 hybrid boot prerequisite (September 18 repair)

Use the [September 23 verified update runbook](COREELEC-HYBRID-UPDATE-2026-09-23.md)
for the current target, preflight/backup/read-back guards, final synchronization
and recovery procedure. Review a future release rather than substituting its
filename into the old exact-device script. Keep manual updates enabled.

The AM9 boots its kernel from SD while `/flash` and `/storage` may resolve to
SSD. **Do not use unattended CoreELEC updates on this arrangement.** Before
rebooting into an update, stage its matching kernel/SYSTEM/AM9 Pro DTB on SD
and let the normal updater update SSD. Afterward synchronize updater-generated
DTB/dtb.xml, device trees and boot support files, verify both kernel/SYSTEM
hashes, and confirm the live kernel build matches `/etc/os-release`. Preserve
hybrid config.ini and storage UUIDs. Verify Wi-Fi, Jellyfin and Kodi after boot.

Arctic 3.3.1 / Jellyfin for Kodi 2.2.0 ports are recorded in
[the repair record](UGOOS-HYBRID-RECOVERY-2026-09-18.md) and version-specific
patches. Do not stack the 2.2.0 consolidated patch with older 2.1.0 patches.
Custom add-ons use manual updates so stock packages cannot silently erase the
ports. Ordinary unmodified add-ons retain their normal update policy.

Preserve the [always-awake/OLED configuration](device-policy/always-awake/README.md)
when commissioning or upgrading the local AM9. It uses Kodi settings and a
version-reviewed peripheral XML merge, not a replacement system image. Recheck
CEC enum/file identity after updates; do not clone a whole peripheral profile.

1. Confirm the last private backup succeeded. Keep the currently working addon
   sources, settings and a SQLite-consistent DB backup. Verify rollback artifacts.
2. Fetch `upstream` (jurialmunkey/skin.arctic.fuse.3). Create a candidate from
   the exact reviewed upstream tag/commit, not the repository-root 3.2.19 files.
   Apply/rebase `patches/arctic-3.3.1-habibi.patch`, then the r6 search/template
   changes. Do not edit `addon.xml` alone, reset production or rewrite history.
3. Review `shortcuts/generator/data/setup/widgets_row.xml` and its generated
   onclick behavior. Resolve conflicts consciously. Request/detail actions must
   not become PlayMedia; real media must not become a request.
4. If Jellyfin/KodiSeerr changed, create fresh pinned checkouts. Run
   `git apply --check integration/patches/<component>.patch` from the appropriate
   checkout (use an absolute patch path). Set `git config core.autocrlf input`
   in these disposable checkouts first: KodiSeerr contains CRLF source files,
   and patches were generated using Git's input normalization. Do not change
   global Git settings. A failure means **stop and port/review**,
   not use fuzzy patching or copy the old entire player file over a new version.
5. Update source pins and patches together. Run `python3 integration/check.py`
   and `python3 integration/release/verify-preservation.py`, then review CI.
   Inspect upstream release notes and permissions/dependency changes. A fix is
   not complete until code/patch, regression, source manifest and public docs
   agree, the reviewed commit is pushed, and private rollback/acceptance records
   exist.
6. Deploy only while no video/audio is active. Stage files and preserve old ones.
   Build Arctic templates without a live skin reload, then restart Kodi while idle.
   Wait for Jellyfin's background service to authenticate before testing playback.
7. Live acceptance checklist:
   - Phone resume position appears in Home and resumes correctly.
   - Discover owned movie plays through Jellyfin; a show opens its episodes.
   - Unavailable card confirms a request, cancelling causes no playback error.
   - Already requested movie is not submitted again. Test failures do not report
     success. An approved request follows existing server quality profiles.
   - Favorites add/remove reaches Jellyfin; other clients agree.
   - Seek near episode end: prompt, automatic next episode, explicit cancel/stop.
   - Intro/outro buttons, subtitles, audio sync/passthrough and HDR remain correct.
   - Home/Discover ordering, paging, Requests status and trailer action load.
   - Check logs and cold/warm load timings; do not publish raw credential-bearing logs.
8. Only after passing, regenerate `verified-build.json` from the intended deployed
   addon versions/source hashes. Exclude caches/settings/credentials from Git.
   Record evidence, rollback location and differences from the previous release.
9. Tag the reviewed integration commit if desired. This fork does not dispatch to
   upstream's addon repository or auto-publish Kodi packages. Any future release
   workflow must explicitly select source files and exclude private userdata.

## Remote Venom variant

The remote-house marker selects a Jellyfin-account/HTTPS
catalogue and playback route, not the private provider/PVR route. Preserve it
when updating the common browser: rebase and test
`patches/venom-remote-performance.patch`, and include
`remote-venom/remote_catalogue.py` in the reviewed payload/integrity manifest.
Run `test-venom-remote.py` and the full checker. Never replace remote files with
unmodified local-provider files or copy another device's credentials/profile.
The supported bundle distinguishes exact local/remote cohorts and snapshots
settings/marker as read-only inputs; unknown/partial cohorts require review.
Remote native P7 transport is a separate setup and is not enabled by this overlay.

## Rollback

September 22 r6 Venom handoff note: keep the common Browser's explicit
Stop/poll/Open lifecycle for a confirmed different native TV channel, and its
generation-based cancellation of stale playback lookups. Do not apply that
local PVR branch to the exact-Jellyfin remote route. Rebase the remote
overlay and run both Browser and remote tests before producing a device bundle.
The public r6 build/installer pins live under `release/`; exact device profiles,
deployment evidence and rollback locations stay with the private operations
record.

Server profile 6 separately uses bounded exact-403 input retry: maximum four
retries, seven-second individual backoff cap and eleven-second scheduled total
backoff. Preserve the original-quality copy mapping/output. It is a supported
profile setting, not an extra whole-file Dispatcharr override. Recheck FFmpeg
option availability on update and never broaden it to every 4xx or raise account
limits. It does not cover all nested HLS requests. Full operational evidence and
rollback paths stay private. Portable profile-update and local HTTP fixture
tooling live under `release/handoff/`.

Stop Kodi while idle. Restore the saved compatible addon source and configuration
as a set; restore databases only if migration requires it. Never combine an older
DB with newer WAL/SHM files. Preserve ownership and permissions. Start Kodi, wait
for service login, and rerun the playback/resume acceptance checks. Do not flash
firmware or replace boot media for a skin/addon rollback.
