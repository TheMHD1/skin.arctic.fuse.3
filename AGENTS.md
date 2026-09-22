# Maintaining the custom media integration

The owner requires every Jellyfin, Kodi or Arctic fix to be preserved as code
or a documented configuration change so it can be recreated after an update
or on another device. A live edit or chat explanation alone is not completion.

For work in this repository:

1. Read `integration/CUSTOMIZATIONS.md`, `integration/UPDATING.md` and the
   affected component's instructions before changing its deployment.
2. Preserve the maintained source/patch, exact upstream version or commit,
   required configuration, regression test, build/install procedure and rollback
   instructions together. For a configuration-only fix, document the exact field,
   prerequisites, verification and private backup procedure instead of committing
   a live config dump.
3. Keep local-PVR and remote-Jellyfin cohorts separate. A source test or staged
   build is not live-device acceptance. Record deployed, tested, staged and
   pending status accurately, including known limitations.
4. Never copy real profiles, credentials, userdata/database files, raw logs,
   media inventories or backup archives into this public fork. Keep private
   recovery material with the deployment, referenced without exposing secrets.
5. Run the relevant regression suites and clean-source build checks. Stage only
   reviewed files, then regenerate `integration/release/source-manifest.json`
   using `verify-preservation.py --write`; verify it without `--write` afterward.
   The manifest covers listed bytes, not secret detection or runtime acceptance.
6. Within the user's authorized repository workflow, commit and push the reviewed
   changes before claiming they are preserved on GitHub. State explicitly if
   they remain local or publishing is blocked.

The root skin tree is the older 3.2.19 baseline. Current 3.3.1 integration uses
version-specific source patches and guarded overlays; do not simply bump the
root addon version or install the root ZIP as the current release.

Restoration/testing is not permission to interrupt playback, reboot, flash or
upgrade firmware. Respect current user holds. Exact-cohort guards must not be
bypassed to make a new or drifted device look supported.
