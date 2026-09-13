# Controlled update workflow

1. Confirm the last private backup succeeded. Keep the currently working addon
   sources, settings and a SQLite-consistent DB backup. Verify rollback artifacts.
2. Fetch `upstream` (jurialmunkey/skin.arctic.fuse.3). Create a new candidate branch
   from your integration branch. Merge the desired upstream tag/commit there.
   Do not reset the production branch or rewrite its history.
3. Review `shortcuts/generator/data/setup/widgets_row.xml` and its generated
   onclick behavior. Resolve conflicts consciously. Request/detail actions must
   not become PlayMedia; real media must not become a request.
4. If Jellyfin/KodiSeerr changed, create fresh pinned checkouts. Run
   `git apply --check integration/patches/<component>.patch` from the appropriate
   checkout (use an absolute patch path). A failure means **stop and port/review**,
   not use fuzzy patching or copy the old entire player file over a new version.
5. Update source pins and patches together. Run `python integration/check.py` and
   review CI. Inspect upstream release notes and permissions/dependency changes.
6. Deploy only while no video/audio is active. Stage files and preserve old ones.
   Build Arctic templates without a live skin reload, then restart Kodi while idle.
   Wait for Jellyfin's background service to authenticate before testing playback.
7. Live acceptance checklist:
   - Phone resume position appears in Home and resumes correctly.
   - Discover owned movie plays through Jellyfin; a show opens its episodes.
   - Unavailable card confirms a request, cancelling causes no playback error.
   - Already requested movie is not submitted again. Test failures do not report
     success. An approved request follows existing server quality profiles.
   - Favorites add/remove reaches Jellyfin; other clients agree.
   - Seek near episode end: prompt, automatic next episode, explicit cancel/stop.
   - Intro/outro buttons, subtitles, audio sync/passthrough and HDR remain correct.
   - Home/Discover ordering, paging, Requests status and trailer action load.
   - Check logs and cold/warm load timings; do not publish raw credential-bearing logs.
8. Only after passing, regenerate `verified-build.json` from the intended deployed
   addon versions/source hashes. Exclude caches/settings/credentials from Git.
   Record evidence, rollback location and differences from the previous release.
9. Tag the reviewed integration commit if desired. This fork does not dispatch to
   upstream's addon repository or auto-publish Kodi packages. Any future release
   workflow must explicitly select source files and exclude private userdata.

## Rollback

Stop Kodi while idle. Restore the saved compatible addon source and configuration
as a set; restore databases only if migration requires it. Never combine an older
DB with newer WAL/SHM files. Preserve ownership and permissions. Start Kodi, wait
for service login, and rerun the playback/resume acceptance checks. Do not flash
firmware or replace boot media for a skin/addon rollback.
