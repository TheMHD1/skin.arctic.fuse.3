# Repeatedly unavailable custom feeds

Inconclusive quality probes are not definitive dead-channel evidence. Short probes can fail for temporary availability, events off-air, or decoder reasons. Some inconclusive quality results have successful independent playback tests.

At the user's request, the publisher now suppresses repeatedly unavailable feeds from all custom groups, after all group extensions have run. Criterion: at least two capacity-available inconclusive observations within seven days, separated by at least 30 minutes, with no newer successful observation. A later successful checker or quality-audit observation permits automatic restoration. This is a reversible availability decision, not a claim of permanent provider failure.

Candidate manifests and provider channels/IDs are retained, and the existing quality audit continues without restart. Personal favourites are not forcibly deleted. Decisions are recorded in `/data/config/iptv-venom/unavailable-channel-exclusions.json`; original evidence stays in channel-health.sqlite3. Initial assessment found 92 repeatedly unavailable candidate feeds, 22 of which were still in published custom groups.

Implemented in venom-curate-channels.py. Tests cover single failures, insufficient time separation, unknown capacity, stale evidence and restoration following a successful test. Category API snapshot caching can delay visible removal by approximately five minutes.
