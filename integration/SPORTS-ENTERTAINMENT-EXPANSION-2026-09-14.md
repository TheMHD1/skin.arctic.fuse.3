# Sports/entertainment expansion and quality-category removal

User requested no duplicate HD-and-above categories, sports by discipline with
Arabic and English together except separate soccer, full English movies/show
channels, and quality measurements for every new candidate.

## Persistent classification

`venom-special-groups.py` no longer generates quality companion categories.
The normal categories retain HDR-first, provider-label quality ordering pending
review of the full measured audit. Measurements and channel identities are intact.
`en-sport` folds into `ar-sport`, relabelled All sports · عربي / English, preserving
both sets of channel IDs. Specific sports appear adjacent to All sports.

`venom-sports-entertainment.py` scans the entire redacted live catalogue, not the
previous capped starter lists. It stages UFC/MMA, boxing/kickboxing, wrestling,
rugby, American/Canadian football, cricket, baseball, basketball, hockey, golf,
tennis, motorsport/F1, horse racing, Arabic soccer and English soccer.

General networks stay in All sports. Football categories include regular carriers
as well as dedicated feeds; beIN/Kass are not claimed to show only football.
TSN is included as a CFL carrier (https://cfl.prod.s.cfl.ca/2026-cfl-broadcast-schedule).
SuperSport Rugby was found under Africa/Canal+, not UK: its identity matches
https://campaigns.supersport.com/rugby/match/9829a196-a62e-4448-8b9e-89bfa5fc70ff .

Language assignment is category/network/label inference, not speech recognition.
Explicit foreign-language tags are excluded from new Arabic/English sports entries.
SP is ambiguous (sports vs Spain), so it is never sufficient by itself. Mixed
international/Africa bins admit identified English networks but not every feed.
No empty sports group is published before a working feed is available.

English entertainment includes HBO, Cinemax, Showtime, Starz, MGM/Epix, Hallmark,
Sky Cinema, FX/FXX/FXM, AMC, Sony, Paramount and other matching channel families,
plus provider English cinema/entertainment bins without arbitrary variant caps.
OSN/beIN English-programming movie feeds are candidates. The two explicit FOX
Movies feeds exist in Portugal/Serbia bins: retained as requested with regional
labels, English audio unconfirmed until inspection. This does not fabricate feeds
missing from the provider or promise all broadcasts are in one language.

## Rollout and continuing checks

Catalogue refresh: 11,249 channels / 304 provider groups. Additive staging via
`venom-stage-sports-entertainment.py` yielded 1,680 unique candidates. First publish
retained all 697 existing channel IDs and replaced 24 old lists with 20 nonempty
lists; additional sport groups appear automatically after decoder success.
The final configured classification has 26 potential nonempty category groups.
Event-only feeds can be inconclusive off-air and remain unpublished until working.

The quality worker now refreshes candidate + published scope each iteration,
deduplicates channel IDs, preserves completed schema-3 records, and prioritizes
missing sports groups. Every successful full-quality decode writes a small
successful observation to the existing channel-health database, allowing the
ordinary publisher to admit it without a redundant playback-only test. Failed
quality samples do not write failure observations or hide existing channels.

Current worker: `venom-quality-audit-sports.service`, transient, 24-hour cap.
Report: `/data/config/iptv-venom/channel-quality-audit.json`.
Publisher/checker: existing `venom-channel-checker.timer`; idle guards retained.
No app rebuild, no stream URL change, no channel deletion. Removing the twelve
HD companion navigation groups is recoverable from the config/code backups under
`/data/config/iptv-venom/backups/sports-expansion/`.

Regression tests: 4 sports classification, 5 special groups, 11 curation,
5 quality probe tests passed. New feeds are queued, not falsely marked tested.
Client category snapshots cache for five minutes. Ugoos was not woken for this work.
