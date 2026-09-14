# High-quality channel rescan — 2026-09-14

## Superseding display-order correction

The user explicitly wants the channels labelled 8K at the top, even when decoded
video was lower resolution. Browse ordering and HD-and-above membership now
follow provider labels: HDR first, then 8K > 6K > 4K > 1080p > HD > SD.
Measurements are retained for diagnostics and fill in unlabelled channels only.
The separate >1080p verified companion still requires measured dimensions.
This supersedes the measurement-first display policy described in the original
rollout below. Tests cover labelled 8K measured at SD remaining first and in the
HD-and-above companion without falsely entering the verified-resolution list.

## Cause and correction

The old starter-list builder explicitly skipped 6K/8K-labelled channels. That
contradicted the subsequent request to include high-quality alternatives.
Sorting already-selected channels did not reveal this omission.

Removed that exclusion. Candidate builds now retain all matching 4K/UHD,
5K–9K, high-resolution pixel labels, HDR/HLG/Dolby Vision variants beyond the
starter count and three-variant cap. Existing language/category filters remain.
Arabic Al Mashhad news also qualifies when filed under Lebanon by the provider.

`venom-stage-high-quality.py` adds these candidates without replacing the old
queue or published selections. Running it again is idempotent. No stream IDs,
channel numbers, playback routes or user removals from favourites are changed.

## Scan and publication

Refreshed the gateway catalogue: 11,249 channels across 304 provider categories.
Compared the full catalogue with our custom category rules, staging 36 additional
group/channel entries: all 22 beIN 6K/8K feeds, four Arabic 8K news/general feeds,
Al Mashhad 4K and nine sports 4K/UHD alternatives. Foreign-language 8K channels
outside the existing category rules were not arbitrarily put in Arabic groups.
No explicit HDR/HLG/Dolby Vision channel-name labels were found in this snapshot.
Decoded HDR detection remains enabled.

Only fresh successful decoder checks permit publication. Six initial beIN probes
passed (gateway IDs 41, 42, 44, 45, 48, 50); measured video was 720p or 1080p,
not 6K/8K. The remaining candidates continue through the existing idle-only
checker and publisher. Occupied playback capacity defers testing, not a failure.

Normal categories and adjacent HD-and-above categories are regenerated together.
Order: HDR first, then descending resolution, including 8K > 6K > 4K > 1080p >
720p. Fresh decoded dimensions override marketing labels; unmeasured labels are
fallbacks, not verification. A working feed measured below HD remains in the
normal category but is not misrepresented as HD. Duplicates remain available.

## Operations and verification

- `venom-channel-checker.py --channel-ids 41,42,...` enables bounded targeted
  checks; the same shared lock, idle guards, retry cooldown and decoder checks apply.
- `venom-channel-checker.timer` continues normal unattended checking and promotion.
- `venom-promote-tested.py` publishes only fresh successful additions.
- `venom-verify-collection-order.py` checks the real Jellyfin category API against
  the published native manifest. Category snapshots can cache for five minutes.
- Existing files and candidate manifest saved under server
  `backups/high-quality-scan/` before deployment.
- Regression suites: 11 curation, 4 quality-category, 9 checker, 1 additive-staging
  tests passed. No custom client rebuild or Ugoos wake-up required.

The normal candidate builder contains the durable policy; the staging tool is
for additive rollout of that policy to an existing queue.
