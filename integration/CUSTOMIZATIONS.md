# Maintained customizations and release boundary

This branch is a personal, non-commercial source integration for Arctic Fuse 3,
Jellyfin for Kodi and the optional Venom TV browser. It is not an official
release from Arctic, Jellyfin, Kodi or Dispatcharr. This file is the public
inventory of what is maintained, what has been accepted on a device, and what
still depends on private deployment state.

## Current supported source cohort

| Component | Reviewed version | Notes |
| --- | --- | --- |
| CoreELEC / Kodi | CoreELEC 22 nightly 20260922 local / 20260926 remote; Kodi 22 BETA2 | Local AM9 uses the [verified hybrid procedure](COREELEC-HYBRID-UPDATE-2026-09-23.md); the [remote standalone-SD update](REMOTE-AM9-PARITY-2026-09-26.md) was separately authorized. Future firmware updates still require review. |
| Arctic Fuse 3 | 3.3.1 on accepted devices | Reviewed upstream 3.3.1 source plus `patches/arctic-3.3.1-habibi.patch`; the repository root remains a legacy 3.2.19 baseline. |
| Jellyfin for Kodi | 2.2.0+py3 | Apply only the consolidated 2.2 patch stack. |
| Home companion | 1.1.0 | Server-backed Home, search, favourites and episode navigation. |
| Venom TV | 1.3.1 | Separate local-PVR and remote-Jellyfin source cohorts. |
| Up Next | 1.1.9+matrix.1 | Unmodified addon, configured privately. |
| Jellyfin server source | 12.1 | Custom server changes require the matching build source and tests. |
| Dispatcharr source | 0.31.0 | Live-proxy patches are version-specific and must be rebased for an update. |

Implicit addon defaults belong to these versions. `settings-reference.json` is
a redacted inventory, not importable configuration.

## Deployment state at the September 22 acceptance point

The later [September 26 remote-house catch-up](REMOTE-AM9-PARITY-2026-09-26.md)
supersedes the historical remote-not-deployed statements below. It preserves
the remote HTTPS cohort and records its separate headless/physical acceptance
limits. It does not turn the original local hybrid device into the newer
standalone-SD cohort or implement remote original-P7 transport.

The subsequent [September 23 Home/ratings release](HOME-RATINGS-2026-09-23.md)
adds library-only Favorites/Top Rated Web rows, genuine optional IMDb scores,
and paired Web/Enhanced search priority (owned → Discover → Venom). Its new
features use a small plugin and client overlays, not additional server core
changes or custom native APKs.

The subsequent September 22–23 library-experience rollout is documented in
[LIBRARY-EXPERIENCE-2026-09-22.md](LIBRARY-EXPERIENCE-2026-09-22.md). Local Kodi
is now R7 for Home/search, with the R6 playback/transport cohort retained.
Server Next Up, Web search separation and the request-ready timer are deployed.
The following R6 physical playback acceptance remains historical evidence, not
a claim that every R7 UI interaction was physically repeated.

- The local/LAN AM9 cohort is at revision r6. General Jellyfin Movies/TV search,
  Search-first Arctic navigation, the secure TLS default, native-original
  selection and local Venom channel handoff were installed and exercised on the
  real device. Original Dolby Vision P7 FEL, TrueHD Atmos, external subtitles,
  seeking and Jellyfin DirectPlay reporting were observed for the accepted
  sentinel. Actual MBC/Al Jadeed switching, same-channel selection and explicit
  stop/reopen passed sustained hardware-decoder checks.
- The remote-house r6 Venom overlay is built and regression-tested but has not
  been installed or physically accepted there. It deliberately retains
  Jellyfin HTTPS playback, no local PVR dependency and Native mode disabled.
- At that R6 acceptance point, a CoreELEC update was verified separately but
  held. The owner subsequently authorized and completed the
  [September 23 hybrid update](COREELEC-HYBRID-UPDATE-2026-09-23.md).
  Addon acceptance alone still does not authorize future firmware changes.
- Server-side exact-403 input retry is a bounded mitigation with local fixture
  proof. It is not proof that a provider will recover from every rejection.
- Remote original-P7 delivery is not part of r6. It still requires a distinct
  managed-device identity, least-privilege private route, server enforcement,
  offline fallback and measured remote throughput.

Private device names, network addresses, account identifiers, credentials and
backup paths are intentionally omitted. Keep the corresponding acceptance and
rollback record with the private deployment.

## Source map

### Arctic, Kodi and client integrations

- `device-policy/always-awake/`: local AM9 persistent settings for ignoring TV
  standby while leaving CEC remote control enabled; independent TV power and
  three-minute black screensaver for idle/paused/static audio screens. See its
  README for verified enum meanings, merge/rollback rules and physical TV-cycle
  acceptance limits. No boot-media or systemd sleep-mask changes.

- `patches/arctic-3.3.1-habibi.patch`: the maintained skin port for reviewed
  upstream 3.3.1 source. The repository-root skin and `addon.xml` are still the
  legacy 3.2.19 integration baseline: never relabel, ZIP or install that root
  tree as 3.3.1. Apply the r6 search/template overlay after the 3.3.1 port.
- `../1080i/Includes_Search.xml` and
  `../shortcuts/generator/data/setup/search_path.xml`: default Search/Discover
  presentation and generated search paths.
- `plugin.video.habibi.resume/`: server-backed Home and general Movie/Series
  search using the already signed-in Jellyfin account. `test-library-search.py`
  and `test-search-default.py` cover the default routes and generic queries.
- `patches/jellyfin-2.2.0-habibi.patch`: consolidated Jellyfin-for-Kodi 2.2
  integration base. Apply the TLS and native patches below after it.
- `patches/jellyfin-tls-secure-default.patch`: verify TLS when certificate policy
  is unset while preserving an explicit configured policy.
- `patches/jellyfin-native-originals.patch` plus
  `jellyfin_native_originals.py`: opt-in direct-path selection for trusted,
  mapped native library files. HTTP, IPTV, STRM and forced-transcode paths keep
  their existing behavior. `test-native-originals.py` covers the policy.
- `plugin.video.venom.tv/`: common bounded worker, shared favourites, exact PVR
  identity and local channel handoff. `test-venom-browser.py`,
  `test-venom-shared-favorites.py` and `test-venom-tv.py` are its focused suites.
- `patches/venom-remote-performance.patch` and `remote-venom/`: the separately
  reviewed remote-Jellyfin overlay. `test-venom-remote.py` must pass whenever
  common Venom code changes.

### Server integrations carried with this branch

- `patches/dispatcharr-live-admission.patch`,
  `patches/dispatcharr-disconnected-keepalive.patch` and
  `server/dispatcharr-nginx.conf`: the reviewed Dispatcharr 0.31 live transport
  changes. They do not raise provider capacity or bypass authentication.
- `server/jellyfin-custom/`: portable Jellyfin 12.1 source patches and tests for
  custom server behavior, including Continue Watching and retained One Pace
  integration. A production image, database, Compose file and credentials are
  private deployment artifacts, not reconstructed by this directory.
- `server/library-experience-plugin/` and `server/library-dates/`: narrowly
  guarded import-date maintenance, derived Series dates and resumable journal.
  Plugin 1.2 also provides administrator-only single-title discovery without
  a whole-library scan. Deployed September 26 with exact Jellyfin 12.1 ABI guard.
- `server/request-ready/`: durable requester-specific readiness notifications
  and the version-checked repair of the existing Seerr webhook encoding.
- `server/arr-maintenance/`: bounded generic manual-import recovery and audit.
  Its native identity-naming helper carries provider IDs into future title
  folders without renaming existing media.
  Its Seerr selection helper restores only verified existing Movies/Shows
  availability scopes and guards the 3.4.1 mutating-GET API trap. Native library
  settings persist; the ordinary Seerr metadata scan owns availability updates.
- `server/arr-request-search/`: external, journalled recovery of approved TV
  season searches dropped during burst requests. Uses supported APIs, exact
  identity/monitoring checks, active-work exclusions and one uncertain-safe
  attempt per request/season. Deployed September 26; no live recovery was
  needed by its first run because the eligible episodes were already imported.
- `server/seerr-request-privacy/`: exact Seerr 3.4.1 response/count overlay,
  paired with native per-user permissions, to restrict request records to their
  requester except privileged accounts. Deployed and API-verified September 26.
  Its startup pins intentionally require review/rebuild before Seerr upgrades;
  ordinary image recreation retains the read-only mounts. This is not a
  Jellyfin server-core patch or a custom client application.
- `web-navigation/search-jellyfin-web-12.1.patch`: permission-scoped owned and
  secondary provider search rows; see its README and bundle installer.
- `server/dovi/`: portable source and tests for the P7-to-P8.1 reconciliation
  policy. Media, probe/retry databases, queues, exports and validated companions
  remain private runtime state. Its source/runtime map verifies the maintained
  Python hashes. The sanitized worker is evidence/reference source and is not
  runnable as-is; use its documented dry-run/review process and never treat it
  as a production queue worker.
  September 26 adds a deployed exact-file import queue, companion-completion
  handoff, separate durable publication database, bounded history recovery and
  finite tapered retries. ACK requires native indexed playable paths, not 2xx.
- `server/subtitle-publication/`: provider-arrival and managed AI publication
  with exact-item refresh, atomic compatibility sidecar replacement, served-SRT
  verification and finite durable retries. Deployed September 26; retired
  legacy whole-library-scan and global scan pause/resume calls. Reference helper
  snapshots are not a replacement for private model/GPU configuration.
- `server/publication-e2e/`: isolated real Jellyfin Movie/Episode/subtitle
  acceptance fixture, including duplicate/conflict/auth and no-global-scan
  assertions. Eleven checks plus four harness safety tests passed September 26;
  it is not a client/GPU/new-downloader acceptance test.

The server directories preserve reviewable code; they do not claim that a new
server can be reproduced without its private configuration and data. The colour
repair is primarily a supported Jellyfin encoding preference, not a public
server patch. Continue Watching additionally requires a matching custom server
build. Existing P8 companions must not be treated as current-source-proven solely
because their Dolby Vision profile is valid; source-fingerprint provenance is a
separate open correction.

## Portable release tooling

`release/README.md` is the entry point for the portable release source. The Kodi
builder in `release/kodi/` fetches or accepts the exact pinned clean Jellyfin
source, builds a hash-checked payload from this fork, and writes a caller-selected
staging envelope. Generated payloads and real deployment profiles are not
committed.

`install.py` and `transaction.py` implement the reviewed exact-cohort update:
version/manifest/source checks, active-or-paused playback refusal, private
profile validation, backup, one Kodi stop/start, readiness checking and rollback
for caught errors/interactive interruption. Power loss or forced process death
requires manual recovery from the retained backup; it is not guaranteed atomic
multi-file recovery. `rebuild.py` performs the separate post-install template rebuild.
The pinned builder verifies all emitted hashes; `kodi/test_release.py` covers
both installed cohorts, drift rejection and an interrupted transaction. The
handoff subdirectory carries the bounded profile-6 retry
tooling and local HTTP fixtures.

This is a **guarded update envelope**, not a blank-device bootstrap or a generic
Dispatcharr installer. A real profile is private and should be patterned on the
redacted example only.

## New device versus exact-cohort update

For a new device:

1. Install the correct official CoreELEC image and device tree for its hardware.
   Give it unique network, SSH, Kodi and Jellyfin client identities.
2. Install the reviewed base addon versions above and their platform-matched
   binary dependencies. For Arctic, use reviewed upstream 3.3.1 source plus
   `patches/arctic-3.3.1-habibi.patch`; do not install the legacy repository-root
   tree or edit only its version. Do not copy databases, host keys or the whole
   userdata tree from another box.
3. Authenticate Jellyfin and optional request services locally. Configure the
   device's own libraries, paths, audio/display capabilities, PVR route and
   private backup destination.
4. Build the portable release, create a private host profile from the example,
   and review the resulting plan. A blank or unreviewed source cohort should be
   rejected rather than forced through the upgrade installer.
5. Merge user-facing shortcuts/settings selectively, rebuild templates, and run
   the complete display/playback/search/IPTV/resume/subtitle acceptance list.

For an existing reviewed device:

1. Verify its private backup and leave Kodi idle; paused playback counts as
   active.
2. Build from the pinned public release source. Supply the matching private
   profile and require an exact version/source/manifest plan.
3. Apply one transaction, retain its printed backup, complete the template
   rebuild, then test actual routes rather than treating readiness as acceptance.
4. If source or settings drift is detected, rebase and retest. Never bypass a
   guard or overwrite the entire addon/userdata tree.

See [SECOND-UGOOS.md](SECOND-UGOOS.md) for commissioning and
[UPDATING.md](UPDATING.md) for the controlled update/rebase process.

## Public/private boundary

Git may contain source, patches, tests, redacted examples and deterministic
builders. It must not contain real profiles, tokens, passwords, API keys,
account/device identifiers, host keys, private URLs, userdata databases,
manifests containing private paths, logs, media inventories or rollback
archives. Device/server backups remain encrypted or access-controlled outside
Git. A source release is not a backup.

## Future-fix process

1. Reproduce and identify the owning layer: upstream source, maintained patch,
   deployment policy or private runtime state.
2. Change the smallest maintained source or setting; preserve exact identities,
   permissions and fallback behavior.
3. Add a regression at that layer and run the full integration and release
   suites, including both local and remote cohorts where common code changed.
4. Build from clean pinned inputs. Review a no-write plan against a sanitized or
   private saved cohort before contacting a device.
5. Deploy only while idle, retain rollback, collect bounded acceptance evidence,
   and update this inventory when status changes.

A future fix is not complete until its maintained code or patch, regression,
source manifest and public documentation agree; the reviewed commit is pushed;
and the private deployment record contains the rollback location and acceptance
result. Run `python3 integration/release/verify-preservation.py` before release
handoff to catch omitted source, tests or manifest entries.

Do not record an offline stage as deployed, a successful RPC as playback, or a
server transcode as proof of direct-play display behavior.
