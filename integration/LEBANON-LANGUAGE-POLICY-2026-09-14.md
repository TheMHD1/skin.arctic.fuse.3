# Lebanese category and Arabic/English-only custom lists

Added `ar-lebanon` (لبنان · Lebanese channels) to the persistent provider-family builder. It stages all 47 feeds in provider category 9 plus the reviewed JADEED 4K feed from category 2. Distinct quality variants remain distinct IDs. The provider Lebanon bin contains some regional networks; this is not a claim that every station is Lebanese-owned.

The existing quality audit dynamically reloads candidate/published manifests. No audit restart was needed: Lebanese feeds join automatically, completed IDs are reused, and group membership is recorded. New feeds still need successful playback evidence before publication. At the first verification, 17 Lebanese feeds were published and nine had full technical audit records. Remaining candidates are not represented as tested.

Added 24 reviewed Lebanese artwork aliases, preserving existing artwork. Extended logo lookup to ignore parenthesized pixel resolution and the provider's [Not 24/7] annotation. Display cleanup now also removes the observed `LB ,` prefix. The existing 30-minute presentation timer applies cleaned names and missing artwork to newly published feeds. Unknown logos remain logged, not guessed.

User subsequently required Arabic or English channels only. Removed the former regional FOX Movies exception. The final custom-group builder now filters all groups using original provider names and category language evidence, so previously published foreign variants do not bypass the policy. Provider catalogue and channel identities are not deleted; personal favourites are not forcibly removed. Classification is metadata-based, not speech-language identification; ambiguous variants are excluded where the classifier cannot establish Arabic/English. Exact JADEED 4K is a reviewed Arabic exception from the mixed BLUE 4K bin.

Verified local special-group and sports classification tests, including candidate publication gating and removal of a Spanish channel from an existing group. Keep labelled quality ordering until the separate measured-quality review. Do not recreate HD-only duplicate groups or rebuild client applications.

Deployment: updated scripts under `/data/config/iptv-venom`, name helper also under `/data/config/dispatcharr`; ran stage-special-groups, existing promotion, and new-channel-presentation. The Live TV Categories API caches snapshots for up to five minutes. Artwork aliases are sourced from the iptv-org station/logo catalogue; station-specific unresolved matches remain in reviewed-artwork-report.json.
