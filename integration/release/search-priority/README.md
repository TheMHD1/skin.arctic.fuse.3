# Kodi search priority and poster ratings overlay

This exact-cohort overlay updates the local Arctic Fuse 3.3.1 installation
after the R7 library-experience release. It preserves the four existing search
routes, container IDs and Skin Variables GUIDs while presenting them as:

1. Movies
2. Shows
3. Discover / Seerr
4. Venom Movies — Not HD
5. Venom Shows — Not HD

Both the Combined/Standard selector and Wall selector use that order. The
maintained generator sources split owned and Venom selector includes, so a
later Skin Variables rebuild retains the order instead of undoing it.

Poster cards also gain a bottom-right rating badge. Its provenance order is
explicit IMDb, explicit TMDb (including TMDb Helper Discover results), then a
provider-neutral star for generic/community ratings. The Home companion makes
one authenticated request for at most 100 visible Movie/Series IDs to
`/Habibi/LibraryExperience/Ratings`; it times out after two seconds and fails
open. It never labels Jellyfin `CommunityRating` as IMDb and never fabricates a
zero score.

Build from a clean committed fork:

```sh
python3 integration/release/search-priority/build.py --output /tmp/search-priority-payload
```

On a reviewed local device, first run the no-write plan and then opt in:

```sh
python3 install.py --profile /private/profile.json --payload /tmp/search-priority-payload
python3 install.py --profile /private/profile.json --payload /tmp/search-priority-payload --apply
```

The installer validates the local cohort, addon versions, hostname, MAC and
Jellyfin user; checks all touched pre-install hashes; updates the integrity
manifest; and uses the shared transactional backup/rollback/restart helper.
Playback must be idle unless the operator explicitly supplies
`--allow-active-playback`. A power loss or SIGTERM still requires restoring the
reported backup manually.

After Kodi starts, Skin Variables may rewrite only the generated XML's
indentation. The installer accepts the single reviewed regenerated hash
`619174a0…` after structural comparison confirmed identical elements,
attributes, text, ordering, routes, IDs and GUIDs. In that state a later plan
updates only the integrity-manifest hash; any other generated-file hash remains
an error.

Focused checks:

```sh
python3 -m unittest integration/release/search-priority/test_installer.py
python3 -m unittest integration/test-library-search.py
python3 integration/test-ugoos-home.py
```

The September 23 local deployment passed the exact-cohort plan, restart and
final zero-change plan, including the precisely reviewed regenerated XML variant.
Live Home client returned 30/30 movie IMDb ratings in 55 ms. Kodi's pending
CoreELEC download prompt was cancelled per the firmware hold. This is live source/
API acceptance, not a claim of physical viewing-distance badge inspection or
remote-house deployment. See `../../HOME-RATINGS-2026-09-23.md` for the paired
server/Web release and native-client boundaries.
