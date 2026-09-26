# Bounded Sonarr manual-import recovery

`sonarr-manual-recovery.py` handles one specific warning: a completed SABnzbd
TV download that Sonarr matched to a series by grab ID but cannot automatically
import. It does not clear queues, remove downloads, invent episode numbers, or
override a rejection. qBittorrent items are excluded until an equally strict
path/history adapter is implemented.

Run on ARR CT103 with private Sonarr/SAB config files. Dry-run is the default:

```sh
python3 sonarr-manual-recovery.py --audit /data/config/sonarr/manual-recovery-dryrun-UNIQUE.json --max-packages 10
```

Use repeatable `--download-id` to select only packages already reviewed. Each
run handles at most ten unique packages and needs a **new** private audit path.
The audit is created exclusively with mode 0600. For each package the tool
re-fetches the current Sonarr queue, SAB completed history and Sonarr manual
import preview. It rejects wrong category/status, paths outside the TV
completed-download root, missing/mismatched series or episode IDs, duplicate
episode assignments, existing target files, absent preview quality/language,
any Sonarr rejection (including `Sample`), and preview/queue row-count drift.
All inferred IDs, quality and languages are copied from Sonarr's own preview.

Only a reviewed `--apply` invokes Sonarr's supported `ManualImport` command in
`copy` mode. The mutation deliberately omits `downloadId` while retaining it
for read-only preview: Sonarr otherwise cleans up the tracked SAB source even
in `copy` mode. The revised untracked path has local tests but has **not**
been live-canary-tested. The private audit is durably marked `attempting`
before the command POST. The tool checks source retention, target EpisodeFileIds
and files, successful command status and matching episode/path import-history
events before
claiming `verified`. If verification times out or a response is lost, do not
automatically retry: a known Sonarr bug can move files and then report a
failed command. Check target episodes and history first. Each eligible package
is re-previewed on a fresh run; already imported targets fail closed.

On 2026-09-23 the first bounded CT103 dry-run of ten unique packages found ten
eligible and made no imports. Two separately reviewed packages, `X-Men`
S01E05 and `The Traitors India` S01, were imported and independently verified
(one and ten episodes). **The initial deployed CLI had included `downloadId`
in the `ManualImport` file payload; Sonarr removed their completed SAB source
folders and history as tracked-import cleanup despite `copy` mode.** The
library targets and Sonarr import history remain present. The preserved CLI
now omits `downloadId` on the mutation path and checks source retention; this
revised mutation path was not used on those two packages. `Ma.Fiyi` S01E33 had
a permanent `Sample` rejection and was not forced. See the sanitized
`ops/library-experience-20260922/hooks-seerr-audit.md` for wider queue triage.
Do not use this tool for unrelated warnings, corruption, or bulk content guessing.

Afterward, an authenticated Jellyfin API check found all 11 exact episode paths
in the owned Shows library; one non-admin user could see all 11 and each item
had playable MediaSources. No playback was started. The two separately affected
Radarr collection movies were refreshed one at a time through supported
`RefreshMovie` commands; both completed successfully with no recurring unique
collection error in the subsequent logs. No Radarr database edit was made.

Reference: [Sonarr ManualImport API discussion](https://github.com/Sonarr/Sonarr/issues/5416),
[upstream partial-success caveat](https://github.com/Sonarr/Sonarr/issues/8649).

## Preserve identity in future title folders

`identity-naming.py` changes only native future folder naming through the
supported ARR API. It does not rename existing folders or files, change episode
names, re-identify a whole library, search for releases, or start a Jellyfin scan.
The September 26 deployment verified these fields on Sonarr 4.0.20.3014 and the
installed Radarr naming API:

| Application | Field | Value |
| --- | --- | --- |
| Sonarr | `seriesFolderFormat` | `{Series TitleYear} [tvdbid-{TvdbId}]` |
| Radarr | `movieFolderFormat` | `{Movie Title} ({Release Year}) [tmdbid-{TmdbId}]` |

This prevents an ambiguous translated title from being Jellyfin's only identity
hint. It cannot repair an existing wrong identification by itself. For an
existing mismatch, first compare ARR and Jellyfin provider IDs, original title
and year; then use Jellyfin's native Identify with those verified IDs for that
single title. A title alias alone is not evidence that two records are the same.

Run the tool without `--apply` first, supplying the private ARR `config.xml`:

```sh
python3 identity-naming.py --app sonarr --config /private/sonarr/config.xml
python3 -m unittest discover -s integration/server/arr-maintenance -p 'test_identity_naming.py'
```

For an applying run, additionally supply `--apply --backup` with a new private
JSON path. The tool requires a recognized naming schema, creates the backup
exclusively with mode 0600, rechecks settings before PUT, preserves every other
field, and verifies the complete response afterward. Do not edit ARR naming
settings concurrently: the native API has no conditional-write transaction.

These are native settings and survive ordinary updates. Recheck the two fields
after upgrades and validate the tokens against the new ARR version. Roll back
only the affected field to the private backup's value, preserving unrelated
current settings, through the ARR UI or a fresh GET/merged PUT/readback. Never
restore an old whole config over newer settings. Rollback does not rename
already-created folders. The private deployment record retains exact backups;
no credentials, media inventory or live settings dump belongs in this fork.

References: [Jellyfin TV naming](https://jellyfin.org/docs/general/server/media/shows/)
and [Sonarr media management](https://wiki.servarr.com/sonarr/settings#media-management).

## Native Seerr library availability selection

`seerr-library-selection.py` repairs only existing, verified physical
Movie/Show library enabled flags through the native Seerr 3.4.1 API. It does
not update Seerr media/request statuses manually, change permissions or server
credentials, enable Venom, install another scanner/timer, or start a Jellyfin
media-library scan. Dry-run is the default. Native Jellyfin library IDs and
collection types must match the existing Seerr selections before applying.

**Native API trap:** in this reviewed version,
`GET /api/v1/settings/jellyfin/library` is a mutating selection endpoint.
Omitting its `enable` query makes every selection disabled. Never use a bare
GET there as a read-only audit. Use `GET /api/v1/settings/jellyfin` to inspect
the current settings safely. The helper uses the supported
`/settings/jellyfin/library?enable=<IDs>` route only after explicit `--apply`,
including the union of existing enabled scopes and requested verified scopes.
It never supplies `sync`, rewrites names, or disables unrelated selections.

```sh
python3 seerr-library-selection.py --url http://seerr-private:5055 \
  --settings /private/seerr/settings.json --jellyfin-url http://jellyfin-private:8096 \
  --library EXACT_MOVIE_LIBRARY_ID=movie --library EXACT_SHOW_LIBRARY_ID=show
python3 -m unittest discover -s integration/server/arr-maintenance -p 'test_seerr_library_selection.py'
```

For an applying run also supply `--apply --backup /private/NEW-backup.json`.
The helper checks Seerr's exact version, creates an exclusive mode-0600 private
backup containing native settings and the original private configuration,
rechecks settings before mutation, and verifies exact library and full native
Jellyfin settings readback. This API has no conditional-write transaction;
do not edit Jellyfin selections concurrently. It prints only version/counts,
never credentials or the private configuration.

September 26 acceptance: restored the two existing owned-library selections,
verified persisted flags and exact native settings readback, then completed
native recent and initial full metadata-catalog reconciliation. The reviewed
TV requests became completed with their requested seasons available and
correct Jellyfin mappings; deliberately cancelled seasons remained unknown
and requestable. The existing request-ready worker then created durable
readiness events. Those events remained pending because their requesters had
no matching active message-capable sessions: this proves event creation,
not delivery or that anyone saw a notice. No new timer or Jellyfin filesystem
scan was introduced. Five isolated helper tests passed. Private request IDs,
media names, mappings, configuration and backup remain outside this fork.

After restoring selections, use Seerr's native
`POST /api/v1/settings/jobs/jellyfin-recently-added-scan/run` for new imports.
For initial/historical reconciliation, the native `jellyfin-full-scan` job
reads Jellyfin's metadata catalog for enabled libraries; it is **not** a
Jellyfin filesystem/library scan. Verify requested season statuses and exact
media mappings afterward. Native cron already runs recently-added checks
every five minutes. The separate request-ready notifier only reads Seerr's
availability and verifies playability; it does not create availability.

Rollback changes only the affected selection flags to their saved values
through a fresh safe GET and native enabled-ID query, preserving unrelated
current selections. Do not restore the whole old settings file over newer
permissions/configuration. Keep the backup private. These native persisted
settings survive ordinary recreation/update; after an update, review the
route's semantics/version guard and repeat native availability acceptance.
