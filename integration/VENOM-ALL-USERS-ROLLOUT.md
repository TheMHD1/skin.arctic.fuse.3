# Venom all-user rollout — historical operations record

This file preserves time-stamped rollout evidence and incomplete-state notes.
For the current supported device-update scope and source-of-truth paths, see
[CUSTOMIZATIONS.md](CUSTOMIZATIONS.md).

## Requirements and phases

1. Audit actual provider order, catalogue, concurrency and existing access. Enable Live TV for every existing Jellyfin account while preserving unrelated permissions and parental controls. Extend UI policy beyond Habibi for libraries users can access.
2. Preserve provider category order, with curated groups pinned first. Do not label provider order as popularity without evidence. Preserve quality variants and native channel IDs.
3. Curate a few hundred Arabic/English/Canadian channels, separated into news, general, drama/movies, kids and sports. Publish named groups on all supported clients and seed native favourites for every account without removing existing favourites. Record exactly which additions were made; avoid repeatedly re-adding user removals.
4. Implement a resumable health checker. Parallelize metadata checks, but cap actual streaming probes to verified provider capacity and defer while viewers occupy that capacity. Give slow starts a second longer attempt. Distinguish busy/unauthorized/network/off-air from persistent failure; require multiple independent windows and healthy control channels before automatic reversible hiding.
5. Carry grouping, visibility, favourites and performance improvements through Kodi, Jellyfin and native Moonfin. Native Moonfin currently needs client development for provider groups; not complete merely because server endpoints exist.
6. Verify real user/API/UI behaviour, testing worker runtime and reversibility. Document/publish reproducible integration artifacts after checking for credentials. Keep goal active until all requirements are proven.

## Current evidence

Previous turn produced verified VOD category repair, not completion of this objective.
At this continuation's audit, 26 Jellyfin accounts existed; only Habibi had Live TV access. All others retained their existing library restrictions. Library scan was running.
CategorySnapshotBuilder explicitly sorted category names alphabetically. Kodi's Venom browser independently sorted PVR groups and VOD categories by name, so both require changes.

No channels have been declared dead or hidden by this rollout. No automated checker has yet been deployed. Completion remains unproven.

## Continuation progress

- Applied `venom-live-access.py --apply`: all 26 current accounts now have Live TV. Read-back comparison verified every other policy field unchanged. Original policies backed up privately with a timestamp. No VOD library permissions broadened.
- Redacted gateway catalogue captured: 11,249 channels / 304 groups, no stream URLs or credentials in the catalogue artifact.
- Direct provider metadata audit disproved equivalence of gateway order and provider order: provider begins with its Blue banner, Arabic News, Jazeera, MBC and Arabic country groups; gateway starts at Tunisian channels. Therefore merely removing alphabetical sorting is insufficient. Source patch and regression test preserve input order, but deployment must also supply real provider rank. **Ordering patch not deployed yet.**
- Provider account profile reports max_connections=1, and gateway max_streams=1. Parallel metadata work is safe; parallel distinct streaming probes would manufacture failures. Live occupancy must be rechecked by the future worker, not inferred from this cached account field.
- Added pure health-decision policy/tests: capacity/control failures, auth/rate limiting, gateway errors and event off-air states never count as dead. Repeated retries in one day do not count as independent evidence. Three days/48h of provider-origin missing responses are only review candidates unless provider catalogue removal also persists. Later valid decoding resets prior failure evidence. This is a tested policy component, **not an operational checker**.
- Plugin tests: 31 passed after adding input-order and user-visibility regression test. No additional Jellyfin restart performed in this continuation.

Research: [FFprobe documentation](https://ffmpeg.org/ffprobe.html) supports bounded packet/frame inspection; use an external wall-time limit as well as protocol read timeouts. Decoder-confirmed frames are stronger than HTTP 200 or receiving a few bytes. Full runtime worker and multi-day hiding verification remain open.

## Collections phase — deployed server/web, Kodi pending connectivity

Built and reviewed 312 channels across ten bilingual collections: Arabic news (30), Arabic general (36), Arabic movies/drama (36), Arabic kids (24), Arabic sports (42), Canada (30), English news (24), English kids (24), English movies/entertainment (30), English sports (36). Channels are matched by provider group and recognized brand patterns, not a claimed numerical popularity ranking. Conventional quality variants are retained; 6K/8K labels are excluded from starter selection, not deleted from the catalogue. Source labels do not prove actual resolution.

Curator corrections were made before seeding: excluded misleading title substrings, non-news Al Sharq channels, documentary/English feeds from Arabic News, French Disney from English kids, and provider-made MBC thematic variants from the mainstream general selection. Exact channel name + channel number resolves each selection to one existing Jellyfin ID; ambiguity aborts without changing favourites.

At 01:14:35 UTC, `venom-seed-favourites.service` completed successfully: 26 users × 312 selected channels = 8,112 completed seed records, of which one was already favourited. Added 8,111 flags, retaining all other favourites. Per-user API read-back verified the selections. SQLite ledger `/data/config/iptv-venom/seed-favourites.sqlite3` records original state and completion. Reruns skip completed entries, respecting subsequent personal removals. Separate `venom-seed-idempotence.service` completed successfully at 01:16:37 UTC, skipping prior seed records and adding no new flags.

Deployed category plugin extension reads redacted `channel-collections.json` beside its DLL. It prepends collections and uses actual provider category-name rank for original groups, preserving fallback order for new/unmatched groups. User visibility is applied to each collection; unindexed/unknown channel IDs are removed. `/LiveTvCategories` verified 314 groups (10 curated + 304 source) for another account, not only Habibi.

One restart loaded the extension; no active playback at precheck; full scan resumed. DLL backup: `/data/config/iptv-venom/backups/LiveTvCategories-before-collections.dll`. Plugin remains upstream 0.3.0.0 plus local extensions, not an official newer release.

Web navigation v7 now applies to authenticated users, without granting VOD library access. Clears category caches on account switch. The bundled modern web client independently alphabetizes category cards, so the compatibility script reorders existing keyed cards to server rank while preserving handlers and keyboard order. It also displays distinct channel count (11,249), not the sum including collection memberships (11,561). Browser verified pinned collection order, Arabic News opens exactly its selected channels, and zero navigation console errors after reload. This is a DOM compatibility layer; a future full web rebuild should remove the upstream normalizer's alphabetic sort instead. Legacy-web layout parity remains unverified.

Kodi browser changes are prepared locally: fetch category summaries with the active user's token, pin curated groups, order PVR groups by source rank, and use existing native PVR playback/favourites for selected shared channels. 10 browser tests pass. **Not deployed to Ugoos:** 192.168.50.169 SSH timed out. No verified-build manifest changed. Do not claim Kodi screen verification.

Tests: .NET 33 passed (including curated access filtering and explicit provider rank), curation/resolution 2 passed, Kodi browser 10 passed, navigation assertions passed. Actual worker has not streamed/probed any channel; no dead channels hidden. Native Moonfin still lacks provider-group UI; its ordinary native favourites should consume the seeded server flags, but handset rendering remains unverified.

Scripts: `venom-curate-channels.py`, `venom-seed-favourites.py`, `venom-publish-collections.py`, `venom-provider-order-audit.py`. Server artifacts: redacted source catalogue, provider-order.json, curated-channels.json, curated-native-channels.json. No credentials embedded in these artifacts. Provider-order refresh is currently a manual audited step, not yet an unattended maintenance timer.

Editorial references: [MBC's own channel descriptions in its exchange filing](https://www.saudiexchange.sa/Resources/fsPdf/5326_0_2026-03-31_19-49-42_En.pdf), [Corus children's channel description](https://www.corusent.com/advertising/brands/treehouse/), [TSN multi-feed lineup](https://www.shawdirect.ca/english/tsn/). Actual selection is constrained to provider catalogue entries; these references do not establish that each provider stream works or is authentic.

## Operational decoder worker — 2026-09-14 01:24 UTC

Deployed `venom-channel-checker.py`, `.service`, `.timer` to media CT102. Timer enabled; starts 30 seconds after an idle batch completes. One worker uses a file lock, at most 20 channel probes per batch. It prioritizes curated channels, then the existing full 11,249-channel snapshot. No video is stored.

Runtime occupancy uses authenticated Dispatcharr `/proxy/stats/`, checking live (`channels/count`), VOD (`vod_connections/total_connections`) and catch-up (`timeshift_sessions/total_connections`). Missing/unknown shapes or request errors fail closed. First canary correctly deferred while occupied. A later idle canary decoded three frames in 2.58 seconds. Provider account capacity remains 1; no concurrent distinct stream probing is attempted. The gateway's capacity limiter remains authoritative if another viewer arrives after the precheck.

Decoder is existing Jellyfin FFmpeg 8.1.2 inside its container. Both in-container `timeout` and outer subprocess deadline bound probes. FFmpeg reads up to three decoded video frames, scales only the diagnostic output to 16×16 and discards it. Normal successful exit AND at least three reported frames are required. HTTP 200, data arrival or zero frames alone do not pass. Raw FFmpeg stderr and credential-bearing URLs are never written into checker logs/results.

First budget 22 seconds. Inconclusive results retry after at least six hours with a 55-second budget; successful channels skip seven days. Twelve-second bounded occupancy wait between probes accommodates normal connection cleanup. Never kills another viewer/session to free a slot. Later batches retry after occupied runs. Current coverage is a snapshot, not proof of a completed scan.

Authoritative first batch: service PID 584095, systemd oneshot `activating/start` while it runs (normal, not a startup hang). SQLite summary at 01:23:43 showed 9 tested / 11,249 total, all 9 working, 11,240 not yet tested. Subsequent logs showed additional successful progress, commonly 1.76–4.19 seconds per probe plus cleanup. Timer and Jellyfin health verified. Do not restart a running batch just because a polling call times out.

Persistent observations: `/data/config/iptv-venom/channel-health.sqlite3`, indexed channel/time, with channel ID, timestamp, decoded frame count, exit status, duration and attempt budget. Logs: `journalctl -u venom-channel-checker.service`. Read-only progress command: `python3 /data/config/iptv-venom/venom-channel-checker.py --summary`. Pause scanning: `systemctl stop venom-channel-checker.timer` (lets current service finish); stop service as well only when necessary.

Tests: 4 checker tests passed for all occupancy types, unknown API shape, zero-frame rejection, real decoded success and redacted return values. Health policy tests now 7 passed; valid decoded frames are positive evidence even without a separate control-channel result.

Important remaining work: **automatic hiding is disabled**. Gateway failures are recorded only as inconclusive, never provider-origin 404/410. Need actual provider-removal/control evidence and reversible hide/unhide integration before enabling that policy. Radio/audio-only channels currently remain inconclusive rather than dead. Catalogue refresh and robust retry fairness remain further integration tasks; all-client goal is still active. No native Moonfin or live Kodi deployment was completed by this worker phase.
# Quality-first expansion — 2026-09-14 follow-up

## Automatic verified promotion — 02:00 UTC follow-up

- `venom-promote-tested.py` now runs after each successful checker batch. It
  merges fresh successful candidates, resolves native IDs, seeds all eligible
  accounts, publishes collections, and records a fingerprint only after success.
  Unchanged manifests skip repeated account/API work. Failed runs remain retryable.
- Fixed seeder verification: newly processed IDs are verified even when older
  already-seeded IDs are skipped. Missing results fail verification. Pending rows
  become done only after read-back succeeds; user removals of older done entries
  remain respected. Five curation/verification tests pass.
- Initial promotion completed successfully at 02:00:12 UTC, retaining the existing
  312 channels. The checker timer and sequential curated-candidate scans resumed.
  Occupied gateway checks defer work; a viewer arriving during an active probe
  can still compete briefly. No claim of perfect viewer preemption is made.
- Provider concurrency investigation is documented separately in
  `VENOM-CONCURRENCY-2026-09-14.md`. No reliable higher distinct-stream capacity
  was established, so parallel probes and automatic hiding remain disabled.
- Web channel display cleanup v8 was deployed and browser-verified: for example
  `8482 NW : ALJAZEERA 4K` displays as `ALJAZEERA 4K`. Backend names/IDs are
  unchanged. Native Moonfin and offline Kodi still need their display changes.

The user requested higher-quality channels first, backups below primary choices,
and up to 100+ useful channels per custom category, but **no untested new additions**.

- Curator now orders primary channel families by provider quality label (4K/UHD,
  FHD, HD, unspecified/SD), then places alternative versions in subsequent tiers.
  These labels are not a measurement of actual decoded resolution.
- `venom-curate-channels.py --candidates` stages a separate 120-per-category
  candidate manifest. Current matching produces 660 candidates across ten groups;
  smaller categories are not padded with unrelated channels.
- `--approve-tested` retains existing channel identities and accepts new candidates
  only when their latest decoder observation is working and at most seven days old.
  Unknown, timed-out, and failed candidates are not added. Existing channels are
  not deleted based on an inconclusive check.
- Existing 312-channel collection ordering was republished. No new additions were
  eligible yet. Native ID resolution remains exact and favourites are unchanged.
- Checker defaults to the curated/candidate union; full catalogue scanning now
  requires explicit `--scope catalogue`. The background timer remains stopped
  while playback startup delay is diagnosed: the provider has a single stream slot.
- Last observed coverage: 24 channels successfully decoded, no automatic hiding.
  A stopped service's signal/TERM status was caused by our deliberate stop, not a
  channel failure. No guarantee of a full 11,249-channel scan within 24 hours.
- Four curation tests and four checker tests pass. Quality ordering is published
  server-side; Kodi deployment/native Moonfin changes and real-resolution checking
  remain separate outstanding work. Display-name cleanup/startup-delay diagnosis
  are also still outstanding. No GitHub push was performed for this follow-up.
