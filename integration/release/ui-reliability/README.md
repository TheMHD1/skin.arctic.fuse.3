# October 1 remote UI repair

This is an **additive, remote-only, exact-source overlay** after the September 26
remote originals layer and search-priority overlay. It does not replace the
historical builders, install the repository's legacy skin, or modify credentials,
transport policy, firmware, libraries or user databases.

## Repairs

- Venom category OK no longer requests focus on an empty asynchronous grid.
  The accepted result moves focus after populating it. Empty results stay in the
  category chooser; moving to a top button or cancelling a pending load does not
  have its focus stolen by the eventual result. Network generation cancellation
  and all remote/local playback identity rules remain unchanged.
- Arctic rating visibility tests real info labels instead of passing `$VAR`
  into a boolean expression. This also avoids the invalid doubled-negation
  expansion in the existing poster-indicator parameter. The label's IMDb → TMDb
  → generic/community provenance priority is unchanged.
- Remote playback explicitly closes the browser before handing off to Jellyfin.
  Previously fullscreen could hide the custom window without its close handler,
  leaving the singleton set and later launches silently ignored. Local PVR
  switching is unchanged. The guarded installer also accepts the one recorded
  interim October 1 manifest, upgrading only browser and manifest to revision 2.
- Discover's ownership bridge indexes only authorized owned movie/show roots,
  never the enormous Venom libraries. It uses at most eight 500-item requests,
  a two-second per-page timeout and an eight-second page-loop deadline after
  view authorization. The native Client's view discovery has its own timeout.
  Incomplete indices are not cached. The 60-second complete-index cache is bound
  to server, user, credential digest, scopes, freshly authorized roots and Home
  refresh revision. It retains only fields needed for exact TMDb matching and
  favourites. Discover's existing exception handler remains fail-open.

The bridge still uses exact provider IDs: this is not fuzzy-title playback.
The library search still handles punctuation/spacing, not arbitrary spelling
mistakes: `quite` is not `quiet`. No single-film alias is added.

## Rebuild and installation

Reproduce the documented remote R6 → R7 → search-priority → remote-originals
chain first. `overlay.py` supplies the deterministic transformations and four
reviewed input SHA-256 hashes. The full starting integrity manifest is pinned
by `install.py`; an unknown cohort must be reviewed/rebased, not force-installed.
The clean-source remote browser regression reconstructs the common addon and
remote patch before applying this repair.

Copy this directory and `../kodi/transaction.py` with their relative layout to a
private staging directory on the intended remote appliance. Run:

```sh
python3 install.py --expected-hostname ACTUAL-APPLIANCE-HOSTNAME
python3 install.py --expected-hostname ACTUAL-APPLIANCE-HOSTNAME --apply
```

The first invocation only plans. Apply requires Kodi idle (paused is active),
checks every current manifest file, saves the four files and manifest privately,
stops Kodi once, writes the patch, restarts and checks an idempotent final plan.
Existing transaction rollback applies to caught failures; power loss/SIGKILL
still needs manual recovery. No whole-userdata restore is required for rollback:
while idle stop Kodi, restore the five saved files together, start Kodi, verify
manifest integrity and repeat UI acceptance. Keep the private backup path from
the installer output; never commit it or a real profile to this fork.

Run:

```sh
python3 -m unittest integration/release/ui-reliability/test_overlay.py
python3 integration/release/ui-reliability/test_remote.py
python3 -m unittest integration/release/search-priority/test_installer.py integration/test-library-search.py
python3 integration/check.py
```

After any rebase, physically exercise category OK on a cold grid, Back during
loading, Movies/Series listing, search keyboard entry, visible rating badges,
Discover and real playback. An API list or successful Player.Open is not proof
of video playback. The owner-authorized October 1 remote device deployment and
acceptance are recorded in `../../REMOTE-AM9-UPDATE-2026-10-01.md`; this layer has
not been deployed to the original local-PVR appliance.

The later [shared AM9 release](../shared-am9/README.md) derives a guarded local
port using this same bridge/rating code and `browser(..., remote=False)` for
generic focus repairs only. It preserves the original local playback handoff;
the remote default output hashes are unchanged. That paired port is staged,
not installed. The installer in this directory remains remote-only.
