# Maintained customizations and release boundary

This branch is a personal, non-commercial source integration for Arctic Fuse 3,
Jellyfin for Kodi and the optional Venom TV browser. It is not an official
release from Arctic, Jellyfin, Kodi or Dispatcharr. This file is the public
inventory of what is maintained, what has been accepted on a device, and what
still depends on private deployment state.

## Current supported source cohort

| Component | Reviewed version | Notes |
| --- | --- | --- |
| CoreELEC / Kodi | CoreELEC22 nightly20261028 accepted locally; remote October28 postboot pending / Kodi22RC1 | Both use their own standalone SD and private identities. The remote October28 stage and controlled reboot request completed, but network return and postboot acceptance are not yet proved. Future firmware updates still require separate review. |
| Arctic Fuse 3 | 3.3.1 on accepted devices | Reviewed upstream 3.3.1 source plus `patches/arctic-3.3.1-habibi.patch`; the repository root remains a legacy 3.2.19 baseline. |
| Jellyfin for Kodi | 2.2.0+py3 | Apply only the consolidated 2.2 patch stack. |
| Home companion | 1.1.0 | Server-backed Home, search, favourites and episode navigation. |
| Venom TV | 1.3.1 | Separate local-PVR and remote-Jellyfin source cohorts. |
| Up Next | 1.3.0 | Both clients reverified October28 against upstream tag `v1.3.0`; native prompt/cancel/Still Watching policy retained. |
| Jellyfin server source | 12.1 | Custom server changes require the matching build source and tests. |
| Dispatcharr source | 0.33.0 | Six version-rebased customizations are deployed; native UI and authenticated metadata-only HEAD passed. Provider/client playback remains separate. |

Implicit addon defaults belong to these versions. `settings-reference.json` is
a redacted inventory, not importable configuration.

## October 28 maintenance: source candidates and acceptance boundary

The [local backup receiver acceptance layer](release/local-backup-receiver/README.md)
preserves the immutable paired manifest while separately guarding the corrected
restricted-rsync worker. Its fake-only tests preserve every parent expectation;
the remote cohort checks receipt absence without touching the local worker.
The actual local backup repair and fourteen database checks passed. A fresh
backup invocation, completion marker and database verification subsequently
passed; the additive receipt was accepted against the complete local parent
without rewriting its historical manifest. The remote cohort remains
absence-only. Arctic's subsequent guarded deployment remains separate.

The [next-episode release guard](release/next-episode/README.md) adds the patched
Jellyfin player to the portable payload and exact installer hash checks. The
old builder patched its temporary checkout but omitted this file from the
emitted payload. Both live clients already contain the reviewed player, so
this is a future-update preservation fix, not a proven current autoplay cause.
Real ordinary EOF-to-adjacent playback passed on both local-native and
remote-HTTPS cohorts. Explicit cancel/stop and genuinely terminal episode
acceptance remain pending; do not infer them from an EOF check.

The [exact-item artwork queue](server/artwork-publication/README.md) and
[CT103 deployment gates](server/dovi/ARTWORK-CT103-DEPLOYMENT-2026-10-28.md)
add durable, bounded image publication after an exact native import acceptance.
They accept native compact Jellyfin UUIDs, verify canonical paths, retain
existing Primary images, serialize workers, and poll accepted refreshes without
reposting every thirty seconds. Repeated enqueue cannot resurrect a dead job.
The DOVI fast and notify-only entry points must both receive the explicit pair
of local worker/config paths. Timeout/launch failures keep bounded intent.
The Venom exporter image-refresh change removes recursive catalogue image
fetches from its frequent metadata refresh. These source changes are deployed.
The existing-Primary exact-item acceptance passed with zero refresh posts;
missing-Primary future-import acceptance remains pending. Effective systemd
drop-in ordering was corrected and both DOVI entry points were verified. The
original missing-artwork incident's exact cause is not proven merely by
repairing posters.

Version-scoped update candidates preserve existing deployed versions until
their complete runtime gates pass:

- [Arctic3.4.10](release/arctic-3.4.10/README.md): semantic rebase, generated
  selector checks and pinned source; exact official TMDb Helper6.19.2 artifact
  and 715-file payload now guarded in schema-3 private stages. Both installed
  dependency payloads pass read-only verification. A fresh actual local isolated
  generation passed with independently validated evidence; live3.4.10 skin
  installation and paired UI acceptance remain pending. The paired `.2`
  adapter now has independent source review and 84 focused tests, preserves
  the full latest parent without rewriting historical manifests, and has
  durable protected-state recovery. An actual isolated run generated valid
  managed selectors but exposed the evidence validator's default-user filename
  mismatch. A subsequent remote probe generated selectors but also rebuilt the
  native viewtypes include. Its exact-path, complete-expression-set validator
  is now covered separately; neither failed run produced acceptance evidence.
  A subsequent genuine local generation passed, then a private deployment
  preflight correctly rejected a byte-only live settings reordering after normal
  Kodi startup. Every setting value remained unchanged; repeating the private
  stage and generation reproduced the same order-only rejection. The deployment
  source now binds that one serialization exception to the immutable rollback
  subtree, preserving every setting ID/value/attribute and every other file.
  No evidence is rewritten. Fresh generation and live installation using the
  corrected source remain pending; the remote cohort also needs postboot acceptance.
  Two required image
  resources are present in private generation stages but absent from both live
  clients and their native add-on databases; installation/enabling and guarded recovery must
  pass before the skin is installed. Staged dependency hashes are not proof of
  live registration.
- [Jellyfin12.4](server/jellyfin-custom/candidate-12.4/README.md): patched server
  tests and exact12.4 Library Experience guard pass. The operational
  [LinuxServer candidate](server/jellyfin-custom/candidate-12.4-linuxserver/README.md)
  loads all14 installed feature plugins, including custom Live TV Categories.
  All13 isolated native publication checks pass against the full-feature image,
  including real artwork enqueue,
  one missing-Primary refresh, no verification repost, native image arrival and
  Arabic subtitle replacement/serving without another global scan. External
  provider downloads, production deployment and client acceptance remain
  separate; production12.1 is not replaced by a blank test. The custom Moonbase
  user-scoped Seerr port passes its isolated routes; the merged bundled Web
  preserves owned Home/search plus Live TV categories and native Guide/Channels
  tabs, passes18 targeted tests,
  and serves from the category plugin under its exact12.4 guard. An authenticated
  browser on the isolated blank configuration rendered Home, categories, Guide
  and Channels with working native tab navigation. Populated production rows,
  provider playback and physical client acceptance remain separate.
  A private, network-disabled copy of the stopped production configuration also
  starts on12.4 with all14 installed feature plugins. Item/user identities,
  credentials, permissions and API keys remain unchanged. The upstream watch-data
  harmonization migration was checked against the original snapshot: it reconciles
  only the expected conflicting rows to their most recent playback state. No
  library scan or production database modification was used for that check.
  **Production upgrade is now on hold:** the actual guarded rollout detected
  an additional inherited-parental-rating regression and restored the exact
  original12.1 image/configuration. All six database continuity groups matched
  after rollback and native health passed. The upstream
  [`MigrateRatingLevels` issue #18227](https://github.com/jellyfin/jellyfin/issues/18227)
  clears inherited episode/season rating caches for items with empty own ratings.
  Do not whitelist that difference or repeat the upgrade unchanged. Require an
  official fix or an isolated, fully validated native rehydration/restricted-user
  canary before another production exposure. Recovery archives remain retained;
  redundant failed-upgrade working copies were removed only after independent
  hash/decompression checks. No media or photos were removed.
- [Seerr3.5.1](server/seerr-request-privacy/candidate-3.5.1/README.md): clean
  compiled overlay builds, syntax and isolated native owner/ordinary-user
  route/privacy acceptance pass; production recreation, existing-request privacy
  and settings continuity, Arabic-fulfillment test webhook and independent
  request-ready polling now pass. No synthetic new download was created.
- [Dispatcharr0.33](server/dispatcharr-candidate-0.33/README.md): exact-source
  semantic patch rebase, all six mounted-module behaviors,63 focused and79
  broader isolated Django regressions pass. Native movie/episode HEAD retains
  authorization without entering stream allocation. The exact patched image is
  now deployed with stopped data/nginx rollback copied and verified externally;
  channel/provider/profile continuity, actual UI and authorized metadata-only
  HEAD pass. Client/provider playback acceptance remains separate.

This inventory distinguishes reviewed source, isolated tests and actual
deployment. A Git push is not delivery to either appliance or server.

## October 12 remote Wi-Fi recovery

The optional [persistent 5 GHz policy](device-policy/wifi-5ghz/README.md) is
installed on the remote AM9 after a cache-warning investigation. It fixes late
Canadian regulatory initialization and prefers the exact household 5 GHz AP,
with bounded scans/roaming and missing-AP recovery. Its configured 5 GHz AP is
currently not visible, so successful roaming, sustained playback and boot
acceptance are pending. Local-cohort deployment requires its own private profile
and remains pending; no account/transport/source parity is inferred from this
device-specific configuration.

## October 12 original Venom access recovery

The subsequent [native XC HEAD repair](server/vod-xc-head/README.md) adds
authenticated metadata-only movie/episode checks without reserving provider
slots. Ten real-function regressions and live authorized/denied HEAD checks
passed. Source/image pins, guarded deployment and rollback are preserved;
native GET/Kodi acceptance is distinct from the owner's currently playing
4K library episode. The [Arabic keyboard policy](device-policy/arabic-keyboard.json)
adds the built-in layout alongside English; saved/runtime and post-reboot values
passed on the local appliance. Remote keyboard rollout remains pending.

The [native IPTV access repair](server/AM9-IPTV-ACCESS.md) corrects an exact-client
Dispatcharr network allowlist mismatch without widening administrative access.
The device's existing Wi-Fi reservation was verified. Actual Home entry, category
grid/artwork, two 1080p hardware-decoded channels, switching, stop/Home and reopen
passed; all 58 shared source hashes still match. The remote HTTPS cohort was not
modified. The [bounded native-mount startup recovery](server/native-mount-recovery/README.md)
also restores skipped read-only server mounts/NFS startup; Kodi's previously
missing episode passed an actual VFS byte read. This server policy benefits both
native-original profiles; remote acceptance and a future host reboot remain
separate gates. Source receipts are unchanged.

## October 12 original-device storage conversion

After recovery, the owner authorized retiring the unreliable USB SSD path and
using the original card for both boot and storage. The guarded
[standalone SD migration](device-policy/sd-only/README.md) preserves the
complete local58 repair cohort and the appliance's own userdata; it is not a
fresh install or a remote-profile clone. Full-copy inventory, both unmounted
filesystem checks, cold206 operational entries, local58 and all14 databases
passed. The subsequent live boot runs October12 / Kodi22RC1, both boot hashes
match, `.update` is empty and boot/storage are on the card. Actual Kodi Home,
Venom playback and all58 shared-source hashes passed. Physical HDMI/DV/audio
and a new backup run remain separate acceptance checks.
This supersedes the hybrid-only hardware handoff below, not its recovery evidence.

The owner subsequently interrupted the first staged update. Readonly inspection
found a correct October12 kernel and truncated `SYSTEM`, despite clean filesystems.
The same [SD recovery runbook](device-policy/sd-only/README.md#interrupted-update-recovery)
now preserves the exact payload pins, failed-update marker handling, independent
backups and six readonly boot-integrity regressions. The original card's repair
passed cold boot-pair/MD5/tar verification, both final filesystem checks,
original206 operational entries, local58 and all14 databases. The subsequent live
October12 boot, completed staged update and bounded Kodi/Venom UI/playback checks
passed; full physical AV acceptance remains separate. The remote card was not modified.

## October 12 original-device recovery

The [local hybrid recovery record](LOCAL-AM9-RECOVERY-2026-10-12.md) distinguishes
SSD filesystem corruption and maintenance-adapter I/O failures from a firmware
mismatch. The new [offline installer](release/offline-recovery/README.md) uses the
same complete paired `am9-shared-20261008.7` source planner with additional exact
maintenance-host, physical-serial, UUID and mount guards. It does not replace a
device's account/network identity or clone remote-only playback transport.
Independent image/database acceptance, physical media deployment, staged
firmware and live appliance acceptance have separate records. New upstream
Arctic versions still require an exact rebase; a stock update is not repair parity.

## October 8 performance follow-up

The subsequent [Venom entry](release/venom-entry/README.md) and
[window lifecycle](release/venom-lifecycle/README.md) layers are followed by
the [collection removal repair](release/library-removal/README.md) and
[short sync transactions](release/library-transactions/README.md).
`am9-shared-20261008.7` composes the complete paired repair chain. It removes the
native-PVR dependency only for the explicit Venom Home route and preserves Home
navigation through Python-window teardown, including background video, prevents
the hub from automatically reopening a departing browser, and fixes collection
removal dispatch in Jellyfin for Kodi, releases completed sync writes before
queue/GUI waits, and fetches collection pages before SQL writes. Latest builds
must include these layers; a direct Browser launch is not Home-tab acceptance.
See the [October8 OS/UX record](REMOTE-AM9-UPDATE-2026-10-08.md) for remote
deployment/testing and the local prepared-not-deployed boundary.

The same round fixed [Venom episode-ID freshness](server/VENOM-SERIES-FRESHNESS.md)
on the server: the catalogue exporter detects identity rotation and rewrites
links instead of relying solely on its weekly successful-series cooldown.
This applies to the existing Kodi/Jellyfin/Moonfin server catalogue without
rebuilding apps or modifying the Jellyfin binary. General timer repair is
ongoing; actual sampled episode acceptance is recorded separately.

The [paired performance release](release/performance/README.md)
`am9-shared-20261008.3` adds a separate bounded optional favourite-read lane,
minimal key DTOs and a library-only authorized Views lookup. It composes the
preceding shared/UX repairs into one guarded idle update. Moustafa's remote61
output is installed and UI-tested; Habibi's local57 output is prepared from the
complete saved cohort but **not deployed**, because that appliance is unreachable.
Their identities, network, boot layout, account and transport remain separate.

The [server/Web/Proxmox runbook](server/performance/README.md) records native ARC,
Enhanced visible-card mode and database-scoped Jellystat query-budget changes,
plus the bounded/coalesced Enhanced search-watcher patch. No new server-core
fork, APK, firmware update, LXC RAM increase or Proxmox reboot was needed.
This supersedes only the affected performance/source pins; earlier AV/playback
and physical-acceptance boundaries remain applicable. Git publication is not
delivery to an offline box, and future fixes/updates must retain both cohorts.

## Deployment state at the September 22 acceptance point

The subsequent [remote private-access/original-P7 layer](release/remote-originals/README.md)
adds restricted Tailscale SSH and opt-in layout-gated original-file delivery to
the remote device, preserving global addon mode and HTTPS fallback. It supersedes
the historical remote-P7-not-implemented statements below. Headless selection
and transport acceptance is distinct from onsite Bell/HDMI/FEL acceptance; the
companion video-provenance limitation remains explicitly documented.

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

- `release/ux-round/`: October8 paired Home-departure lifecycle and one-shot
  Combined-search selection repair. Its installer composes the preceding shared
  repair in one transaction, with both complete output manifests pinned. The
  read-only inventory includes semantic menu routes and skin policy, not just
  versions. See its README for per-device deployment and acceptance status.

- `release/shared-am9/`: October2 paired release and read-only parity auditor.
  Common generic fixes are derived for both profiles, with separate account,
  hardware and transport guards. Original55/remote59 private fixture plans pass;
  Remote59 installed and idempotently verified October8; original55 remains
  pending. The [remote startup policy](device-policy/remote-startup/README.md)
  removes the unused native-PVR wait without changing the local PVR cohort.
  The awake/OLED policy was present in
  both live-original and saved-remote settings, not an omitted transfer. Server
  curated-group outage is historical: the October8 remote readback returns all37
  curated groups, independently of the box transaction. Full playback acceptance
  is not inferred from category availability.
- `release/remote-catchup/`: October2 empty-list focus and network
  snapshot-root repair after remote UI reliability revision2, installed through
  the paired release October8. The appliance was offline during preparation;
  [remaining acceptance/parity items](REMOTE-AM9-CATCHUP-2026-10-02.md)
  include extended switching, VOD playback and physical hardware verification.
  The catch-up is deployed; catalogue success
  does not certify every stream.
- `device-policy/wifi-canada/`: supported persistent Canadian regulatory hint
  that enabled the remote AM9's upper5GHz channels; October1 runtime playback
  recovered; October8 confirmed CA/5GHz after the intervening OS boot. Include its native cache file and the
  device's own ConnMan state using the reviewed backup-root migration.

- `release/ui-reliability/`: October 1 additive remote-only repairs for Venom's
  asynchronous grid focus and hidden-window playback lifecycle, valid Arctic
  rating predicates, and bounded owned-library Discover matching. Preserve this
  layer after the existing remote-originals/search-priority chain.

### Arctic, Kodi and client integrations

- `device-policy/private-tailnet/`: exact-peer appliance firewall, reviewed
  CoreELEC addon settings-format startup fix, manual-update policy, and the
  LAN-preserving server-side NFS bridge. No public SSH/NFS port is opened.
- `remote-native-originals/` and `release/remote-originals/`: bounded periodic
  P7/P8 layout manifest and opt-in remote Kodi selector with exact-cohort build,
  regression, install and rollback guidance. The shared converter and global
  Native setting remain unchanged.

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
