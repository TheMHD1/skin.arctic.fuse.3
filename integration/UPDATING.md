# Controlled update workflow

See [the September 18 Venom recovery](VENOM-RECOVERY-2026-09-18.md) for the
general channel-ID playback fallback, paired KodiSyncQueue/client catch-up fix,
12.1 web build, category batching/order, verification and rollback locations.
Run `python3 integration/check-catchup.py` for the maintained 2.2 catch-up patch;
the older checker is not a complete 2.2 compatibility test.

The [September 18 fleet record](FLEET-MAINTENANCE-2026-09-18.md) records the
Jellyfin 12.1 / Enhanced 12.7 source patches, Dispatcharr 0.31 HLS compatibility
fix, verified rollback state and Kodi category-outage recovery. Rebase those
version-specific patches when updating their upstream components.

## AM9 hybrid boot prerequisite (September 18 repair)

The AM9 boots its kernel from SD while `/flash` and `/storage` may resolve to
SSD. **Do not use unattended CoreELEC updates on this arrangement.** Before
rebooting into an update, stage its matching kernel/SYSTEM/AM9 Pro DTB on SD
and let the normal updater update SSD. Afterward synchronize updater-generated
DTB/dtb.xml, device trees and boot support files, verify both kernel/SYSTEM
hashes, and confirm the live kernel build matches `/etc/os-release`. Preserve
hybrid config.ini and storage UUIDs. Verify Wi-Fi, Jellyfin and Kodi after boot.

Arctic 3.3.1 / Jellyfin for Kodi 2.2.0 ports are recorded in
[the repair record](UGOOS-HYBRID-RECOVERY-2026-09-18.md) and version-specific
patches. Do not stack the 2.2.0 consolidated patch with older 2.1.0 patches.
Custom add-ons use manual updates so stock packages cannot silently erase the
ports. Ordinary unmodified add-ons retain their normal update policy.

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
   checkout (use an absolute patch path). Set `git config core.autocrlf input`
   in these disposable checkouts first: KodiSeerr contains CRLF source files,
   and patches were generated using Git's input normalization. Do not change
   global Git settings. A failure means **stop and port/review**,
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
