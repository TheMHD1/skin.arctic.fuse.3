# September 18 fleet maintenance and Jellyfin 12.1

## Scope and final state

CT100 Core, CT101 Cloud, CT102 Media and CT103 Arr were updated and rebooted.
The Proxmox host, unrelated guests, Android firmware and AI GPU software were
not upgrade targets. User authorized service interruptions and redundant-data
cleanup. Media, application volumes, credentials and current rollback images
were preserved. Retired/stopped applications were not reactivated.

All four guests finish on Debian **13.7**, Docker **29.8.1**, with no pending
APT upgrades, empty `dpkg --audit`, and no failed systemd units. All **69**
expected containers run; every configured Docker health check is healthy.
Critical integrations were also checked through API and streaming paths;
running-container status alone is not full end-to-end certification of every app.

| Guest | Running containers | Final root free space |
|---|---:|---:|
| Core 100 | 18 | 9.5 GiB |
| Cloud 101 | 15 | 17.9 GiB |
| Media 102 | 12 | 24.5 GiB |
| Arr 103 | 24 | 22.9 GiB |

The sanitized complete image inventory is
[final-inventory.json](server/maintenance-20260918/final-inventory.json).
Runtime Compose image digests remain pinned; custom images require controlled
rebuilds. Database engines stay on compatible major versions, not blind upgrades
of existing PostgreSQL/MariaDB data directories.

## Application updates

- Jellyfin **12.0 -> 12.1.0**, custom One Pace build.
- Jellyfin Enhanced **12.5 -> 12.7.0.0**, retaining the active-tab/deep-link fixes.
- Seerr **3.4.1** was already the latest stable release and was verified.
- Intro Skipper **12.0.4** and Kodi Sync Queue **16** remain compatible/active;
  all 18 loaded Jellyfin plugins passed the isolated runtime check.
- Dispatcharr **0.30 -> 0.31.0**, with the ownership and XC/HLS compatibility
  patches described below.
- Immich server and OpenVINO machine learning **3.1.0 -> 3.2.2** together.
- Nextcloud custom image **34.0.3 -> 35.0.0**, preserving Intel VAAPI preview
  wrapper, ffmpeg, ImageMagick and Ghostscript. Database migration, enabled apps,
  core integrity, missing-index check, public status endpoint and reboot passed.
  Rebuild files are under `server/maintenance-20260918/`; place
  `nextcloud-ffmpeg-hw` in the Docker build context as `ffmpeg-hw`.
- Radarr **6.4.4.10685-ls317**, Sonarr **4.0.20.3014-ls325**, Prowlarr
  **2.6.5.5623-ls161**, Bazarr **1.6.1**, Maintainerr **3.29.0**, Cleanuparr
  **2.10.6**, FlareSolverr **3.5.2**.
- Core updates include Homarr **1.77.2**, Grafana **13.2.2**, Portainer
  **2.45.1**, Cloudflared **2026.9.1**, Alertmanager **0.34.1**, Dozzle and
  all guest agents **11.1.0**. Vaultwarden **1.37.3** on Cloud.
- Same-branch image refreshes were applied where newer publisher digests existed.
  The custom subtitle bridge/Arabic fulfillment code and GPU model assignments
  were not replaced. Gluetun/qBittorrent network ownership remains intact.

## Jellyfin rehearsal, rollout and acceptance

Source: upstream tag `v12.1`, commit
`ee91c75e777da41a9c4f4855e70adc604fbf2ef8`.

Apply [jellyfin-12.1-onepace.patch](patches/jellyfin-12.1-onepace.patch) to that
source and run the .NET 10 naming test project: **705 tests passed**. Upstream
12.1 already protects ambiguous chapter-style names; the explicit exact-directory
opt-out remains for intentional One Pace policy. Other directory/version grouping
retains upstream behavior. Do not copy an old 12.0 naming DLL into 12.1.

Build the patched `Emby.Naming.dll`, place it beside
[jellyfin-Dockerfile](server/maintenance-20260918/jellyfin-Dockerfile), and build
`jellyfin-custom:12.1-onepace-20260918`. The pinned LSIO base is
`12.1ubu2604-ls50`; OpenCL support and the exact-directory environment policy are
retained.

Enhanced source: upstream `12.7.0.0`, commit
`daf5b10c09d017941e29a79a0a45d0ab31c34abc`. Apply
[the tab patch](patches/jellyfin-enhanced-12.7-tabs.patch), build
`Jellyfin.Plugin.JellyfinEnhanced/JellyfinEnhanced.csproj` in Release with .NET 10
and its default `jf12` target. Both changed JS files passed syntax checks; the
build had zero warnings/errors. Keep `autoUpdate:false` for this local build.

A stopped database/config copy passed SQLite quick-check, isolated 12.1
`MigrateSystem`, and network-isolated runtime/plugin startup before production
promotion. Production retained its server ID, existing accounts/configuration
and actual media mounts. Final stopped databases were also copied immediately
before promotion. Do not run 12.0 against a migrated database when rolling back.

Acceptance passed before and after the final Media reboot:

- Public Jellyfin URL healthy, reporting **12.1.0**, same server identity.
- Authenticated library counts and both Kodi Sync Queue endpoints HTTP 200.
- External SRT response HTTP 200, 95,695 bytes in the test fixture.
- One Pace Loguetown episode IDs retained, one media source per episode.
- Direct media range request HTTP 206, correct 1,024-byte response.
- Actual HDR10 media: Intel QSV decode, tone mapping and H.264 encode succeeded
  for an 8-second sample, approximately 4.55x realtime in that bounded test.
- Library scan was idle after a successfully completed prior scan, not stuck in
  an upgrade-induced scan loop. IPTV background export resumed successfully.

Phone display/physical TV audio acceptance is not implied by server/API tests.

## IPTV regression caught and repaired

Dispatcharr 0.31 validates transformed credentials using a synthetic
`.../1234.ts` URL and reconstructs XC live URLs with a hard-coded TS extension.
Our existing profile changes `.ts` to `.m3u8` to select the provider's HLS
transport. The new strict filename check rejected it, causing live HTTP 503.

[dispatcharr-0.31-habibi.patch](patches/dispatcharr-0.31-habibi.patch) includes:

1. Retained Redis ownership fix: a failed SETNX does not grant ownership.
2. Credentials extraction accepts an unchanged synthetic ID with TS or HLS
   extension; altered IDs, unmatched transforms and regex timeouts fail closed.
3. XC live URLs are built from current account credentials and the actual stream
   ID, then transformed once, preserving transport rules instead of using stale
   stored credentials. Ordinary M3U URL handling remains unchanged.
4. Credential-transform logging no longer includes full URLs/passwords in the
   changed credentials helper.

Production Compose binds the three patched source files read-only. Preserve
those mounts and rebase/test against future releases; do not assume a whole
upstream source file remains compatible forever.

The isolated pure-function suite
[test-dispatcharr-xc-compat.py](server/maintenance-20260918/test-dispatcharr-xc-compat.py)
passed **11 tests** using the real changed functions, without network/provider or
production database access. The upstream Django test route was attempted but its
SQLite fallback cannot execute a PostgreSQL-specific migration; it is not
reported as passing. The patch also contains two upstream-style regression tests
for a future PostgreSQL-backed run.

Real favourite-channel test through the configured source returned HTTP 200 and
valid MPEG-TS packets: **2.89 seconds before final reboot; 3.11 seconds after**.
This is one bounded favourite-channel sample, not a claim about every provider
channel or client playback latency.

## Ugoos custom categories

Missing groups were caused by the server outage during maintenance. Kodi logged
`category service unavailable; keeping native PVR groups`. Its fallback was not
a loss of custom categories or favourites.

The authenticated request from Ugoos returned **341 category entries, including
37 custom collections**. Existing beIN subdivisions, sport groups, MBC, Syrian
and Lebanese groups remain intact. A native Kodi screenshot after recovery
visually confirmed the custom category sidebar.

`integration/plugin.video.venom.tv/browser.py` now retries a failed live-category
request after 15 seconds at the category chooser. It does not replace an open
channel grid or accumulate retry jobs. Both working-tree and fork browser suites
passed **13 tests**. The fork test reads the published Jellyfin 2.2.0 patch for
the exclusion helper instead of depending on a missing private fixture.

Kodi was restarted to load the change and left on the Venom category chooser.
The separate [hybrid boot record](UGOOS-HYBRID-RECOVERY-2026-09-18.md) and
[controlled updating instructions](UPDATING.md) remain prerequisites for another
AM9 build. Do not re-enable unattended hybrid CoreELEC updates.

## Maintenance repairs and cleanup

- NPM post-boot reload now waits for a live nginx master PID as well as valid
  configuration. Previously reload could run before its PID file existed.
- Media firewall validates inspected container IPv4 addresses before creating
  service-to-service rules. Stopped containers can report `invalid IP`; that no
  longer aborts restoration of the remaining firewall restrictions.
- Existing daily CoreELEC snapshot is now a successful no-op; invalid/symlink
  targets still fail. Snapshot retention behavior was not broadened.
- Nextcloud nightly backup enters maintenance before the SQL/config snapshot,
  does not suppress tar failures, and verifies the generated archives before
  retention. A full post-upgrade nightly-backup service run passed.
- AnimeTosho's official shutdown notice explains the failing unfiltered feed.
  Disabled it in Prowlarr/Radarr/Sonarr without deleting saved configuration.
  IPTorrents passed fresh Prowlarr and Sonarr tests. All three Arr health APIs
  subsequently returned empty warning lists.
- Removed explicitly reviewed obsolete images, protecting all container
  references (including stopped containers) and current rollback tags. Removed
  obsolete September 8 rehearsal containers/data after verifying the full Media
  backup. Removed the completed September 18 test copy after production passed;
  it can be regenerated from retained rollback state. No Docker volume prune or
  blind all-image prune was used, and no canonical media was deleted.
- Package caches were cleaned. Logs, current rollback copies and useful
  application caches were retained. No disk expansion was required.

## Backup and rollback

All four stopped LXC backups completed, and full `zstd -t` integrity checks
passed. They are under Proxmox `/tank/pve-backups/dump/`:

- `vzdump-lxc-100-2026_09_18-18_08_07.tar.zst`
- `vzdump-lxc-101-2026_09_18-18_10_34.tar.zst`
- `vzdump-lxc-102-2026_09_18-18_18_01.tar.zst`
- `vzdump-lxc-103-2026_09_18-18_31_45.tar.zst`

These are guest/root backups; excluded media bind mounts are **not** backed up by
these archives. Filenames use the Proxmox host's local clock.

Each guest retains private `/root/backups/update-20260918/` state: pre-upgrade
Compose, image references, rollback tags and relevant app backups. Nextcloud and
Immich have separate SQL backups. Jellyfin has its pre-12.1 config and final
stopped databases. Restore matching application image AND pre-migration state;
do not downgrade binaries over migrated databases. Credentials/SQL/private
Compose/`.env` files must never be committed to this repository.

## Monitoring boundary

34 monitoring scrape targets were up. 15 of 16 blackbox application probes passed.
The separate AI server translation endpoint on port 5500 reported HTTP 503 with
`status: poisoned`, `last_error: ValueError`; this lies outside the four-LXC
upgrade scope. GPU services/models were not restarted or changed. This remaining
AI alert must not be described as an all-green application estate.

## Primary release/incident references

- [Jellyfin 12.1](https://github.com/jellyfin/jellyfin/releases/tag/v12.1)
- [Enhanced 12.7](https://github.com/n00bcodr/Jellyfin-Enhanced/releases/tag/12.7.0.0)
- [Dispatcharr 0.31](https://github.com/Dispatcharr/Dispatcharr/releases/tag/v0.31.0)
- [Immich 3.2.2](https://github.com/immich-app/immich/releases/tag/v3.2.2)
- [Nextcloud 35.0.0](https://github.com/nextcloud/server/releases/tag/v35.0.0)
- [Seerr 3.4.1](https://github.com/seerr-team/seerr/releases/tag/v3.4.1)
- [AnimeTosho shutdown/feed notice](https://animetosho.org/)
