# Scoped subtitle publication

This is a two-lane publisher for `/data/config/bazarr/scripts`, not a library
scanner. `subtitle-raw-arrival.py arrival VIDEO SUBTITLE` is inserted in the
private Bazarr post-sub flow immediately after the provider has written its raw
SRT and before optional AI work. It commits a raw fingerprint/revision first;
therefore an AI failure never erases the provider-arrival publication intent.
The existing four-track generator subsequently enqueues the managed revision
through `subtitle-publication-queue.py` as before.

Both lanes keep durable `video`, subtitle path/fingerprint or managed revision,
status, attempts, first-seen time, next attempt and a short safe detail. Exact
duplicate raw fingerprints retain their existing budget. Changed bytes make a
new row/revision. A timer processes at most three due rows, one per video. The
common retry taper is 30 seconds, 2 minutes, 10 minutes, 30 minutes, 2 hours,
6 hours and 12 hours; after the initial attempt plus all seven delayed retries,
or 48 hours, the row is retained as `deadletter`. Lock/circuit cooldown skips
do not consume an attempt. A
transport failure opens a short shared circuit and stops the current batch.

Before acknowledging either lane, the worker resolves one exact physical video
path, refreshes only that Jellyfin item, and verifies the external subtitle
stream's served SRT bytes. Raw arrivals honour the compatibility-view video
entry and its verified managed manifest's hidden/retired policy. A raw provider
source hidden by a completed managed manifest is marked `superseded`, not
republished. Missing items/view entries simply defer: the dovi/new-title path
owns item creation.

The publisher never calls `Library/Media/Updated`, `ScheduledTasks`,
`RefreshLibrary`, or a whole-library API refresh. Before upgrading an older
scan-yield deployment, verify that no persisted pause/resume obligation remains.

## September 26 deployed acceptance

This publication repair was deployed successfully on September 26. Before the
old scan-yield calls were removed, the private deployment check asserted that
its persisted `paused` value was zero and that there was no outstanding resume
obligation. The deployed workers do not suspend, resume or start a Jellyfin
scan.

The live replay of an existing provider Arabic subtitle reached
`complete`: the source fingerprint stayed unchanged, exactly one resolved item
received the scoped refresh, and the served SRT proof matched. A newly managed
revision on another episode was also automatically verified. These are scoped
publication observations, not a claim about GPU generation, playback or client
UI acceptance. Private title paths, item IDs, logs, credentials, queue rows and
rollback locations remain outside this repository.

The separate isolated real-server acceptance is recorded in
[`../publication-e2e/ACCEPTANCE.md`](../publication-e2e/ACCEPTANCE.md). It uses
temporary fixture media/configuration and real native APIs; it does not use or
modify production data.

## Install and rollback

Deploy only `subtitle-raw-arrival.py`, `subtitle-publication-queue.py`,
`install-post-sub-arrival-hook.py`, `subtitle-arrival-hook.sh`, the existing
`subtitle-jellyfin-publication.service` and
`subtitle-jellyfin-publication.timer`, and this README; do not blanket-copy
this working directory or
`post-sub.sh`. The managed queue continues to use the already deployed,
private-reviewed engine helpers. In particular, `subtitle-library-jobs.py` is
not part of this publication change and must not be added from this directory:
its model-routing configuration is private runtime state.
If the separately maintained optional 3090 lane source is ever reviewed, its
endpoint values must come from private `SUBTITLE_3090_WHISPER_URL` and
`SUBTITLE_3090_NLLB_URL` environment inputs; this publication deployment does
not alter that lane or its model/GPU routing. Reference-only helper and
library-job snapshots in this directory are not deployed by this repair.

First record the private
file's SHA-256 and review its exact AI command. Then use
`install-post-sub-arrival-hook.py` with that hash. It refuses byte drift,
unexpected private-cohort structure, remaining scan routes and an existing
hook, and prints only the new hash. Retain the private
pre-change file as rollback; restoring it and disabling the timer returns to
the prior behavior without touching queues or subtitle media.

The existing unit preserves the Bazarr Docker execution context: both bounded
workers run sequentially through `docker exec bazarr`, so they retain the
container's Python dependencies, `/config/scripts` paths and private runtime
configuration. Do not add a second timer or substitute host Python. After
installing the updated existing service/timer, run `daemon-reload`, enable that
timer, and verify `status` for both CLIs. Keep the staged source and rollback
copy in the private operations record; never commit the private post-sub
script, its hash if sensitive in local practice, logs, queue databases,
credentials or private rollback artifacts.

Run `python3 subtitle-publication-tests.py` before staging (34 focused tests at
the September 26 deployment). Live acceptance is
separate: provider arrival, exact item/view appearance, served bytes, managed
replacement, AI failure retention, outage circuit and eventual deadletter.
