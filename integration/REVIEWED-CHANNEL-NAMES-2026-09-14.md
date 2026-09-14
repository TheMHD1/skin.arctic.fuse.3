# Reviewed custom-category channel names

## Correction: touch layout missed by v12

The earlier 16-page browser check used desktop input mode at a narrow viewport,
NOT Android/touch rendering. User correctly reported numbers still visible.
Reproduced using Android user agent, isMobile=true and hasTouch=true:
`9328 TSN 1 FHD` persisted because the touch overlay anchor has no
`cardImageContainer` class. Desktop has that class. This was not a user-cache
problem and the earlier browser result did not establish mobile correctness.

Helper v13 matches the same-card non-footer accessible anchor by matching href,
independent of its layout classes. It still requires item-name evidence before
removing a numeric prefix. Both footer and missing-artwork labels are covered.
Unit regressions cover desktop/touch anchors, wrong-item links and missing
evidence. No channel metadata, numbers or playback APIs changed for this fix.

Post-deployment Android-touch verification covered all 10 category landing
pages and all 6 later pages. Four pages initially had not loaded by a fixed
delay; these were explicitly rechecked after waiting for channel cards.
All pages then contained cards and passed the label checks (footer and
missing-artwork text). Example before/after: `9328 TSN 1 FHD` -> `TSN 1 FHD`.

Verified outcome: 381 Jellyfin metadata updates applied with protected-field
and favourite readbacks; final audit matched all 590/590 curated channels with
zero mismatches. Dispatcharr persistent override service succeeded. All 16
web category pages (10 first pages plus 6 subsequent pages) showed no leading
3–6 digit catalogue numbers on channel cards. Ten Python tests and the web
navigation policy suite pass, including all 540 map entries' idempotence.
The native curated manifest and all 10 published collections were refreshed
without re-seeding or changing users' favourites.

User reported `748 KD : KARAMEESH`, then confirmed leading numbers also
affected sports and other categories. These are two different layers:

- Jellyfin Name contained provider prefixes missed by the earlier conservative rule.
- Jellyfin web card labels prepend ChannelNumber independently of Name.

Reviewed all 10 curated categories (590 unique channels in this snapshot).
`server/venom-reviewed-channel-names.json` records 540 explicit source-name
replacements. It removes verified country/provider codes and separator clutter,
normalizes whitespace/quality-label formatting, preserves MBC/OSN brands and
meaningful channel numbers, and labels sports backup variants explicitly.
Unchanged clean names are intentionally not in the replacement map.

Deploy this JSON beside `venom-channel-names.py` in BOTH
`/data/config/iptv-venom` and `/data/config/dispatcharr` (container `/data`).
The existing Dispatcharr name-override timer consumes this policy; source
names, stream URLs, IDs, tuning numbers and unrelated user overrides remain
unchanged. Map entries are exact matches: a different future provider name is
not blindly rewritten using this manual review.

`venom-jellyfin-clean-names.py` updates full metadata DTOs with readback checks
and private recovery copies. It accepts the original or prior policy-owned
name, never arbitrary later manual edits. Run the read-only
`venom-reviewed-names-audit.py` after applying to check every curated channel.

Web navigation helper v12 cleans TvChannel cards on all authenticated routes,
including favourites, rather than only Live TV. The independent leading
catalogue number is removed only with evidence from the same card's
unnumbered item name. Real names such as `24 News` and `MBC 3` remain intact.
The missing-image text is cleaned too. The v12 query string forces a fresh
helper download when the web-based app reloads.

This does not modify or rebuild Android/Moonfin APKs. Native clients receive
the server Name, but may independently render ChannelNumber; that remains
a client presentation limitation if the app does not load Jellyfin web.
No claim of direct verification on the user's physical phone is made.
Ugoos was intentionally left powered off.

Regression coverage: all explicit map entries must be idempotent; conservative
fallbacks, manual override protection, channel identity resolution, favourites,
web policy scoping and card-name number handling remain tested.
