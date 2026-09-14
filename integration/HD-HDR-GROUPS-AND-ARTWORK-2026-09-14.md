# HD/HDR companion groups and reviewed artwork

## Channel caption typography — web helper v14

User requested smaller channel names in category grids/mobile. Captions now
use max(12px, .8rem), normal wrapping instead of single-line ellipsis, and
automatic height with a two-line minimum. Longer names may wrap further; there
is no line clamp. Missing-artwork text is reduced to 1rem. Selectors target
TvChannel cards only; movie/series typography and touch menu buttons are unchanged.
Root-relative scaling remains supported for larger-text preferences.

Android touch emulation at 412x915 verified long Sky Sports captions at 12px
over two lines, no horizontal overflow and retained menu buttons. Desktop
rendering also verified. Jellyfin's web-based Android app receives the server
helper on reload; stock native clients that do not use this web UI do not inherit
its CSS. Deployed v14 cache-busted index; v13 helper saved in server backups.

## Final requested behavior

The initial request for 4K/8K was clarified to HD and above, including HDR,
retaining separate quality variants. All normal and companion lists sort HDR
first, then resolution descending within that tier: 8K, 4K, Full HD, HD.
Fresh decoded geometry wins over marketing names. Fresh measured SDR wins over
an incorrect HDR label. Unknown geometry/HDR falls back to the provider label;
these fallback labels are not verification of actual quality.

Added MBC & related (the provider's MBC family, including its related feeds)
and Syrian channel groups. Each of the 12 base categories has an adjacent
HD & above companion when nonempty. No duplicate quality variant is discarded.
An additional verified-above-1080p companion appears only with positive decoded
evidence. At the initial audit no selected measured channel exceeded 1080p,
despite many provider 4K labels. Do not claim real 4K/8K from these labels.

`venom-special-groups.py` is integrated into the existing curation/promotion
pipeline. `venom-stage-special-groups.py` added 94 MBC-family and 32 Syrian
candidates without replacing the previous candidate set. New channels still
need the existing fresh successful decoder check before admission. Existing
selections and each account's explicit favourite removals remain respected.
Future measurements update group membership and ordering automatically.

`venom-channel-checker.py` now records PQ (`smpte2084`) and HLG
(`arib-std-b67`) from decoded showinfo frames, before the diagnostic scale.
It does not change stream playback or transcode viewing sessions. It does not
claim to detect all Dolby Vision profiles; unknown transfer stays unknown.

Published collections are loaded by the existing category plugin, with a
five-minute server snapshot cache. A just-published new category can briefly
return 404 until that snapshot expires; this was observed and then verified
working without restarting Jellyfin. Existing Kodi integration reads the same
collection endpoint; physical Ugoos verification was not performed because it
was intentionally off. Native clients without category support remain limited
by their stock UI; no apps/APKs rebuilt.

## Artwork

Reviewed names across the entire curated selection, grouping quality duplicates.
Saved explicit country/scoped station matches in `venom-reviewed-artwork.json`.
Research started from https://iptv-org.github.io/api/channels.json and
https://iptv-org.github.io/api/logos.json and the actual file inventory at
https://github.com/tv-logo/tv-logos. Corrections include official Syria One
https://syriaone.tv/logo.png and Shahid-hosted MBC Mood/Thaqafiya assets.
Names alone were not enough for ambiguous cases (e.g. Lebanese MTV versus
music MTV, Egyptian CBC versus Canadian CBC). Those have scoped mappings.

The image repair script preserves existing images that successfully load,
downloads only reviewed public sources without Jellyfin credentials, bounds
image size, validates PNG/JPEG signatures, uploads through the normal Jellyfin
image endpoint and verifies image retrieval. Original filenames/streams and
IDs are not changed. Some numbered Sky Sport and provider-specific beIN feeds
use explicitly recorded `network-logo-fallback` assets, not invented exact logos.

Last full audit at deployment: 652 selected items; 643 had working artwork,
9 unresolved and no download errors. The applied ledger recorded 261 distinct
items with uploaded artwork, including 14 network-logo fallbacks. Raw per-pass
upload counts must not be summed as distinct channels: images can be repaired
again during a provider guide refresh. Counts grow as tested candidates publish.

Unresolved at that audit: Ana Syria (two variants), LBC 3, MBC Toon, Marah TV,
the Abdulrahman Al-Majed and Majed Al-Zamil feeds, Syrian Prime TV and Damascus
Radio 2. Research was attempted, but no unambiguous usable image was installed.
Do not replace them with a similarly named foreign station or arbitrary photo.

Successful uploads also create supported Dispatcharr logo overrides through
`venom-artwork-overrides.py`; existing explicit overrides are preserved.
Daily `venom-reviewed-artwork.timer` reruns only this reviewed mapping to repair
missing/broken artwork on newly admitted channels; it does not guess new matches.
Schedule: 05:40 UTC plus up to ten minutes randomized delay. Existing working
images remain untouched. Per-title unresolved/error details are stored on CT102.

## Deployment and recovery

- CT102 `/data/config/iptv-venom`: curation, special groups, checker, artwork
  policy/JSON/scripts, report, private applied ledger, downloaded logo cache.
- CT102 `/data/config/dispatcharr`: Django artwork override script and copied
  successful-upload ledger (container `/data`).
- `/etc/systemd/system/venom-reviewed-artwork.{service,timer}` maintains images.
- `backups/curated-before-special.json` and `candidates-before-special.json`
  preserve pre-change manifests. Remove only derived/new groups to revert the
  menu; no media deletion, tuning renumbering or channel rebuild is needed.
- To stop artwork maintenance, disable its timer. Uploaded images are standard
  Jellyfin images and can be managed using its image editor. Gateway overrides
  are normal ChannelOverride.logo fields; do not clear unrelated user overrides.

Verification: 3 special-group policy tests, 9 checker tests and 10 curation
tests pass. Tests cover HDR-first ranking, duplicate retention, false 8K/HDR
labels, measured SD exclusion, idempotent companions and untested-candidate
exclusion. Public Jellyfin MBC HD companion page loaded with the first six
channel logos verified as decoded browser images. Full physical-phone/Kodi
acceptance is not claimed.
