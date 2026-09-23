# Owned-library IMDb ratings

`update.py` reads IMDb's official, daily `title.ratings.tsv.gz` dataset and
publishes a small JSON subset matching the IMDb IDs of **owned Jellyfin Movie
and Series items only**. It never publishes or retains a full IMDb ratings DB.
This is for personal, non-commercial use; check IMDb dataset terms before any
other use and attribute IMDb as the ratings source in the UI. Do not scrape
IMDb pages or use an unofficial rating API.

Source: <https://datasets.imdbws.com/title.ratings.tsv.gz>. The reader expects
the exact `tconst<TAB>averageRating<TAB>numVotes` header, validates every row,
and caps download at 64 MiB compressed, 512 MiB uncompressed and 8 million
records. A live publish requires at least 100,000 records and at least one
owned match. There is no unbounded all-library fallback: only non-Venom media
views are queried, Movie/Series types are checked again after Jellyfin responds,
and nonmedia views are excluded. Missing IMDb IDs or absent ratings are omitted;
the UI should fall back to TMDb/Jellyfin `CommunityRating`.

The published `imdb-library-ratings.json` contract is:

```json
{"schema":1,"fetched_at":"2026-09-23T00:00:00Z","source_url":"https://datasets.imdbws.com/title.ratings.tsv.gz","ratings":{"tt1234567":{"rating":8.2,"votes":12345}}}
```

`ratings` is keyed only by matching owned IMDb IDs, with no titles, file paths,
user data or credentials. The server consumer must check schema, age and numeric
ranges, enforce ordinary per-user Jellyfin item access, and never serve the JSON
as an unauthenticated global endpoint. An absent/stale score must not be
misrepresented as IMDb. A Jellyfin ID is not an IMDb ID.

## Private installation sketch

Install `update.py` at `/opt/habibi/imdb-library-ratings/update.py` and the
systemd units at `/etc/systemd/system/`. Create the existing private output
directory `/data/config/jellyfin/data/plugins/configurations/library-experience/`
owned by the service user, mode `0700`. Create a private environment file at
`/etc/habibi/imdb-library-ratings.env` (mode `0600`) containing only paths and
the Jellyfin base URL, not the API token itself:

```ini
JELLYFIN_URL=http://127.0.0.1:8096
JELLYFIN_KEY_FILE=/path/to/private/jellyfin-api-key
OUTPUT_DIR=/data/config/jellyfin/data/plugins/configurations/library-experience
```

Use the actual reachable internal Jellyfin URL and existing key file. The
provided unit runs as root on the Docker host because the existing key and
configuration tree are root-only; it has no capabilities, no privilege escalation,
a read-only system, and only its output directory is writable. A native install
may use a dedicated user after explicitly granting the required private access;
do not assume a host `jellyfin` account exists for a containerized server. The
service's `ReadWritePaths` must match the private output path if changed. A
manual run of the same `ExecStart` is useful immediately after a new import;
otherwise the timer refreshes every six hours, with up to 30 minutes of jitter.
The official gzip is cached in that private directory and conditional HTTP
GET reuses it on 304. One cached gzip and one current JSON are retained, not a
history of complete downloads. Failed downloads, malformed data, missing owned
items or interrupted parsing leave the last published JSON untouched. Files
are written through same-directory temporary files, `fsync` and atomic rename
under a single-writer lock. The service prints counts only, not IDs or keys.

Run `python3 -m unittest discover -s integration/server/imdb-library-ratings -p 'test_*.py'`.
Fixture tests alone imply no deployment. On September 23 the media-host unit was
installed and its initial run and six-hour timer were verified; the public
Home/ratings release record carries acceptance counts. It does not run on the
development host.
For rollback, disable the timer/service, restore the private prior JSON if
desired, and revert the consumer to its TMDb fallback. Keep private backups and
API credentials outside this public repository.
