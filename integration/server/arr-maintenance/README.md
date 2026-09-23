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
