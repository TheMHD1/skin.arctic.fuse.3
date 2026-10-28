# Exact-item Jellyfin artwork publication

This is a durable guardrail for a newly imported movie or series with no
Primary image. It is not a scanner, never enumerates a library, never replaces
existing images, and never accepts an arbitrary path or remote URL.

The trusted discovery/import caller must enqueue only the ID returned by
`Habibi/LibraryExperience/DiscoverTitle` plus the canonical title directory:

```sh
python3 artwork-publication.py enqueue --config /data/config/_dovi/artwork-publication/config.json \
  --item-id "$DISCOVERED_JELLYFIN_ID" --title-root /data/media/shows/Exact-Title
```

The worker first reads only that ID and verifies that Jellyfin's path is the
specified `/data/media/movies/<title>` or `/data/media/shows/<title>` directory
(or a movie file directly under it). If a Primary already exists it records
completion and does nothing. Otherwise it posts a refresh for that exact item
with `MetadataRefreshMode=None`, `ImageRefreshMode=Default`, and both replace
flags false, then rechecks it. Busy/indexing 409s wait 30 seconds without
spending the eight-failure budget; all work has a finite 48-hour expiry.
Both native 32-character and hyphenated UUID item IDs are accepted and normalized.
An accepted refresh enters a verification-only phase for up to ten minutes;
the worker does not repeatedly submit new refreshes every thirty seconds. If
no Primary appears, it spends a failure attempt before bounded backoff/retry.
Repeated enqueue of the same ID/title cannot reset its age or resurrect a dead
job. The daily recovery helper remains available for later provider recovery.
The worker uses an exclusive, nonblocking process lock, while SQLite WAL lets
trusted import callers durably enqueue independently. Run it on ARR CT103 beside
the DOVI caller, not on CT102 with an unreachable cross-container script path.
Its private URL/token reference targets Jellyfin on CT102. Before deployment,
verify both containers agree on `/data/media/{movies,shows}/<title>` identities.

`config.json` is private and must be mode 0600. It contains only the private
base URL, a root-owned `token_file` path, `state_db`, and optional `media_root`.
Do not commit it or token material. Install the service/timer only after wiring
the enqueue call into the reviewed exact discovery return path. The daily
`repair-artwork.py` remains a recovery backstop; it is not evidence of an
established import root cause.
