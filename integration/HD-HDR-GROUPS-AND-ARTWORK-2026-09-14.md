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

The maintained unit now runs `venom-jellyfin-readiness.py` before the artwork
script. The helper makes only an unauthenticated GET to an exact Jellyfin
`/System/Info/Public` or `/health` endpoint, accepts only strict HTTP 200 plus a
valid ready body, and gives up after at most 60 seconds. Redirects, setup mode,
malformed/oversized bodies, non-200 responses and transport timeouts fail
closed before the artwork script can open its lock, cache, report or ledger.
The Linux command also uses an absolute process timer, so slow-trickling HTTP
bodies or DNS cannot extend its socket timeouts beyond that budget.
The private endpoint is supplied only through the root-owned mode-0600
`/etc/venom-reviewed-artwork.env` file as
`VENOM_JELLYFIN_READINESS_URL=http://jellyfin.example.invalid:8096/System/Info/Public`;
do not put the real address or an API token in this repository or unit. The
service retries a failed preflight/job after ten minutes, with systemd capped at
six starts per two hours. Its existing commands, 20-minute timeout, nice level,
idempotent image preservation and credential boundary are unchanged.

Both artwork entry points use that same environment file and readiness preflight:
the daily reviewed-artwork unit and the legacy new-channel presentation unit.
The preflight also loads only the private helper definition and compares the
normalized scheme, hostname and effective port of its authenticated base URL.
A different host, scheme or port fails before the presentation unit can rename
a channel and before either unit can open artwork state. The artwork worker
repeats the same origin binding as defense in depth. This prevents a healthy
public check for one origin from authorizing credentialed writes to another.

Each upload is now crash-safe. After the reviewed source image is bounded and
cached, the worker fsyncs an owned pending intent containing its digest before
posting it. On the next run it reconciles pending work before ordinary
existing-Primary preservation. It promotes an intent only when the unresized
native Primary bytes have exactly the same digest and size; a manual or other
non-matching image is retained and reported, never replaced or claimed. Ledger
promotion and pending removal are separately fsynced and idempotent, so an
interruption between them does not repeat a POST. Per-item errors are durably
reported and make the unit fail for systemd retry; unmatched reviewed candidates
remain normal review work rather than a job failure.

For new work, Jellyfin's `ImageTags` value is only advisory. The worker reads the
exact unresized native Primary endpoint before every possible upload. HTTP 200
always preserves that image, including a manually supplied image; only an exact
HTTP 404 permits a new pending intent and POST. Transport errors, timeouts and
all other HTTP failures are item errors and never authorize replacement. If a
POST is accepted but exact readback still returns 404, the pending intent is
retained and the item remains failed rather than being counted as repaired.

The service invokes `venom-reviewed-artwork-run.py`, a fixed-command bounded
wrapper. A fully completed worker run returns 0. A run with a durable report and
one or more item errors returns 75. For only those two statuses the wrapper
atomically copies the successful ledger and runs the existing bounded Dispatcharr
override command, then returns the original 75 failure so systemd still retries.
Readiness, origin, setup, signal and other fatal failures cannot run that
finalizer; no stale report is used as authorization. This preserves successful
partial uploads without turning a partial run green.

## Deployment and recovery

- CT102 `/data/config/iptv-venom`: curation, special groups, checker, artwork
  policy/JSON/scripts, report, private applied ledger, downloaded logo cache.
- CT102 `/data/config/dispatcharr`: Django artwork override script and copied
  successful-upload ledger (container `/data`).
- `/etc/systemd/system/venom-reviewed-artwork.{service,timer}` maintains images.
- `/data/config/iptv-venom/venom-jellyfin-readiness.py` is the source-matched
  preflight; `/etc/venom-reviewed-artwork.env` is private deployment state.
- `/data/config/iptv-venom/venom-reviewed-artwork-run.py` is the bounded service
  wrapper that preserves partial-error status while finalizing durable successes.
- `backups/curated-before-special.json` and `candidates-before-special.json`
  preserve pre-change manifests. Remove only derived/new groups to revert the
  menu; no media deletion, tuning renumbering or channel rebuild is needed.
- To stop artwork maintenance, disable its timer. Uploaded images are standard
  Jellyfin images and can be managed using its image editor. Gateway overrides
  are normal ChannelOverride.logo fields; do not clear unrelated user overrides.

For deployment, first save the live unit and any existing helper/environment
file to the private rollback directory and verify the live unit still matches
the reviewed pre-change hash. Install the readiness helper, artwork worker and
service wrapper as root-owned `0755`, create
the environment file as root-owned `0600`, install the unit as `0644`, run
`systemd-analyze verify` and `systemctl daemon-reload`, then execute the helper
alone. Do not start the artwork job until that read-only preflight passes and a
maintenance run is authorized. Verify the unit's next timer, capped retry
properties, final result and unchanged existing artwork behavior.

To restore, stop only an in-progress artwork unit, restore the saved original
unit, restore or remove the helpers/environment file according to their saved
pre-deployment existence, run `systemctl daemon-reload`, and verify the timer.
Do not delete artwork, ledgers or caches and do not manually rerun the job as
part of rollback. This source revision is prepared and tested but not deployed.

Verification includes `python3 -m unittest -v
integration/server/test_venom_jellyfin_readiness.py
integration/server/test_venom_reviewed_artwork.py`: its isolated real HTTP
fixtures cover unavailable-to-ready recovery without authorization, non-200,
redirect, invalid-body, degraded-health, slow-trickling-body and bounded-timeout failures, plus unit
ordering and retry caps. The 18 artwork transaction tests cover the native
Primary safety matrix, crash windows, stale identity, durable partial
finalization and fatal no-finalizer boundary. The current 2 artwork-config, 6 special-group, 9
checker and 15 curation tests also pass. Tests cover HDR-first ranking,
duplicate retention, false 8K/HDR
labels, measured SD exclusion, idempotent companions and untested-candidate
exclusion. Public Jellyfin MBC HD companion page loaded with the first six
channel logos verified as decoded browser images. Full physical-phone/Kodi
acceptance is not claimed.
