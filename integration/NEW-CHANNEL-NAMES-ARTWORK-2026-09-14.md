# New channel names and artwork

Expanded the persistent name policy for confirmed provider markers: USA/US/UK/CA,
AR/SP/DS/NW/KD/LB/SY/UAE with delimiters, numeric prefix before such markers,
and [SPO]. Collapses duplicate whitespace and normalizes MBC/OSN colon formatting.
Station numbers, quality labels, meaningful backup markers and regional FOX Movies
PT/SR distinctions are preserved. Explicit user overrides still take precedence.

Gateway name overrides are now scoped to the staged custom-channel IDs using
`venom-name-scope.json`, copied by `venom-channel-names.service`. They don't change
channel identities, stream URLs, numbers or other override fields. Jellyfin applies
full metadata DTO updates with protected-field and favourite readbacks, using the
existing backup/ownership rules. `--curated` restricts its updates to published IDs.

Artwork matching now uses channel source language/category rather than treating
the merged sports list as entirely Arabic. Canadian-specific existing scope is
retained. Artwork keys reuse the name cleaner. Added 58 reviewed aliases/matches
for new sports and entertainment stations, including AD/KSA/OnTime, MLB/NHL,
Fight Network, WWE, Sky NFL, SuperSport and movie networks. Generic beIN branding
is explicitly labelled network-logo-fallback, not a fabricated station-specific logo.
Source catalogue for reviewed logo URLs: https://iptv-org.github.io/api/logos.json .

`venom-new-channel-presentation.timer` runs every 30 minutes, invoking its matching
service: curated name cleanup, missing-only artwork repair, then supported gateway
logo override persistence. Existing Primary tags are preserved in this lightweight
pass. The separate daily `venom-reviewed-artwork.timer` still verifies broken images.
External image downloads remain bounded and signature-validated; no server token
is sent to external image sources. Unknown logos stay logged, not guessed.

Verified snapshot: 753/753 names matched policy, zero name mismatches. Latest
artwork pass: 753 channels, 703 existing images preserved, 33 repaired, 17 unmatched,
zero errors. A preceding pass repaired 32. These counts are snapshots while the
quality scan keeps publishing new channels, not a claim that all queued channels
already have images. Prior manual overrides and all favourites remain preserved.

Reports: `reviewed-artwork-report.json`; naming audit `venom-reviewed-names-audit.py`.
12 curation/name regression tests plus artwork-key/duplicate-JSON checks passed.
