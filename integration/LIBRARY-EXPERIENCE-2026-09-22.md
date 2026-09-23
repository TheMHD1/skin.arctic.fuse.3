# Library experience: September 22–23, 2026

This is the rebuild and acceptance index for the server, Web and Kodi work.
It contains no credentials, user IDs, media inventory or private deployment
profiles. The operations record holds before/after API captures and backups.

## The three different clocks

| Row | Intended order | Not ordered by |
| --- | --- | --- |
| Continue Watching | Most recent actual playback activity first, one resumable episode per series | Download date, release date or episode number |
| Next Up | Most recently watched **series** first, with its appropriate next episode or intentional rewind | Furthest episode's old play date or download date |
| Recently Added | Current file's verified import date, newest first; new episodes bring their show forward | Release date or an old filesystem creation timestamp |

Playback state stays per-user on Jellyfin. Kodi reads the server rows instead
of independently re-sorting them by `DateCreated`. Nothing in this release
marks titles watched or fabricates watch activity.

The server's Resume de-duplication is retained. Next Up previously ranked series
by recent activity, then re-sorted the resulting candidates using an older
completed episode's timestamp. The preserved patch removes that second sort,
keeps access filtering and deterministic ties, and considers alternate-version
activity without producing duplicate series. Twelve scoped executable server
tests passed. A read-only post-deployment audit of 26 accounts found zero
duplicate series, Resume order violations or API errors.

## Owned library first, provider catalogue separate

Web and maintained Kodi search now present Movies and Shows first, followed by
**Venom Movies — Not HD** and **Venom Shows — Not HD**. Discover remains a
separate search/request path. The requested “Not HD” wording distinguishes the
secondary provider catalogue; it is not a per-file resolution measurement.

Scope is resolved from the signed-in user's accessible libraries before
querying. There is no unrestricted fallback if views fail. Exact item IDs are
retained for playback; unknown provider-named libraries are not treated as
owned content. Punctuation variants supplement literal Kodi searches.

A live joined-spelling check found that local normalization alone was not
sufficient: the server returned no candidates for `spiderman`. Kodi now has a
permission-scoped bounded prefix/suffix fallback before full-query matching.
It does not download the full provider catalogue; overly broad joined searches
ask for spaces rather than silently claiming a complete result.

The deployed Web bundle was checked in an authenticated mobile-size browser
with a user having both catalogues and a restricted user. Owned rows appeared
first, provider rows were separate, Discover remained available, and the
restricted account did not receive provider rows. The local Kodi R7 transaction
passed a zero-change re-plan and live Resume/Next Up/latest API checks. Physical
remote-control acceptance of every new row is separate from those API checks.

Stock Moonfin/native clients benefit from the shared server order and library
permissions, but may render their own search groups and caches. This release
does not rebuild APKs or claim to force new section headings into a native UI.

## Import dates and refresh behavior

Future imports use Jellyfin's library-added time instead of filesystem creation
time (`UseFileCreationTimeForDateAdded=false`). Historical repairs match the
current Radarr/Sonarr physical file by exact path, never title guesses. The
administrator-only maintenance plugin changes only the guarded date column,
then recomputes affected Series latest-media dates. The journaled CLI includes
resume and compensating rollback; both must preserve derived parent dates.

The completed live batch corrected 4,050 Movie/Episode dates and recomputed
165 parent Series dates. Independent read-only database checks found zero
missing items, path/date mismatches or derived-date mismatches, and no pending
refreshes. Kodi's new imports rose to the top while Continue Watching retained
the latest real playback first. No watch history was changed by the repair.

Kodi's Home refresh recognizes both Home and Videos windows, refreshes while
idle, and schedules a bounded refresh after playback or library-change events.
An earlier periodic refresh no longer consumes a pending event refresh. Latest
Shows groups newly imported episodes into show cards rather than sorting shows
only by their original folder creation date.

Existing Radarr/Sonarr download/upgrade hooks were retained. They trigger the
Dolby Vision compatibility reconciler, which publishes canonical view changes
to Jellyfin using `/Library/Media/Updated`. This intentionally waits for safe
media publication; a large reconciliation can take several minutes. It is not
an unconditional instant full-library scan.

A live recovery supplied an end-to-end check: all 11 imported episodes appeared
in the compatibility view and then as exact-path Jellyfin items with playable
media sources for a non-admin account. No playback was started for this test.

Bazarr post-processing and the AI subtitle discovery/work/publisher timers
were checked. Two long-waiting subtitle items were blocked by unpublished
compatibility-view video, not by a missing subtitle refresh hook. Do not bypass
the video-publication safety gate merely to clear their retry count.

## Ready notifications and queue maintenance

The new request-ready timer polls Seerr without replacing its existing Arabic
fulfillment webhook. It verifies requester-visible owned media is playable and
all requested TV seasons are available, then durably queues one notification
per request. Existing available requests are seeded without historical spam.
Delivery waits for an idle, active, message-capable Jellyfin session belonging
to that requester; accepted commands are not proof the person saw the message.
Offline phone push requires a separately opted-in native/Seerr notification
channel. No real new-request completion has yet been observed end-to-end.

Seerr's existing webhook had six recent pre-delivery JSON decoding failures.
Its payload encoding was repaired through the supported settings API, preserving
the receiver, authentication, event mask and enabled state. API and durable
settings readback passed, and a safe test returned HTTP 204. Failed historical
events were not blindly replayed.

The Arr audit distinguishes safe import recovery from valid rejections and
external failures. See `server/arr-maintenance/README.md` for bounded fresh
preview checks, verified recovery results and cleanup behavior. Old approved
requests are not deleted merely because they are old. Unknown releases,
sample rejections and non-upgrades are not forced into the library.

Two affected Radarr movies also passed sequential supported metadata refreshes
after a collection-key uniqueness error during concurrent adds. Both commands
completed without that error recurring; no collection database rows were edited.

## Source / rebuild / rollback map

| Component | Maintained entry point | Rollback boundary |
| --- | --- | --- |
| Resume / Next Up / One Pace | `server/jellyfin-custom/README.md` | Matching prior image, not a blind database restore |
| Date maintenance plugin | `server/library-experience-plugin/README.md` | Dedicated plugin directory; date rollback is separate |
| Import-date plan and journal | `server/library-dates/README.md` | Guarded compensating dates plus derived Series refresh |
| Web search | `web-navigation/search-README.md` | Retained matching Web bundle/index |
| Kodi Home/search R7 | `release/library-experience/README.md` | Transaction backup and original live integrity manifest |
| Ready timer / existing webhook | `server/request-ready/README.md` | Stop timer, retain outbox; restore saved webhook only if necessary |
| Arr warning recovery | `server/arr-maintenance/README.md` | No blind repeated command or database edits |

The source manifest checks hashes and, in a Git clone, completeness of the
tracked source set. Stage reviewed additions before regenerating it. CI runs
Python release/behavior tests and executable .NET 10 tests from freshly
reconstructed pinned Jellyfin source. Binary payloads, journals and private
profiles remain outside Git.

The narrow Next Up query fix still needs a matching server build because the
stock endpoint does not expose a plugin ordering override. Import-date repair
and notifications deliberately live outside core server patches. Rebase and
test the source stack for upgrades; never copy 12.1 DLLs onto a newer server.

The remote-house Kodi R7 cohort is not deployed. CoreELEC firmware remains held;
service/Kodi restarts authorized for this work did not authorize an OS update.
