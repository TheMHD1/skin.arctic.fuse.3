# Preserve dependency source in private Kodi snapshots

The remote commissioning snapshot excluded every directory component named
`packages`. That also removed legitimate bundled `urllib3/packages` source from
SlyGuy dependencies0.0.30, so its service and trailers failed with
`ModuleNotFoundError: urllib3.packages`. This was a cloning/backup exclusion bug,
not evidence that CoreELEC20260926 changed the addon ABI.

`policy.py` excludes only the known Kodi addon-download cache, thumbnail cache,
live database tree and Python bytecode caches. Add SQLite-consistent database
copies separately using the private snapshot's existing online backup procedure.
Never exclude arbitrary addon subtrees merely because their names resemble a
cache. In particular, retain all four Python sources under bundled
`urllib3/packages`, including its `backports` subdirectory.

For an existing private snapshot worker:

1. Save its source privately and confirm the expected old exclusion expression.
2. Install this module beside the private worker as `device_backup_policy.py`.
3. Import `should_skip` and replace the broad component-name exclusion with
   `if should_skip(relative): continue`. Preserve device identity, destination,
   SQLite online copies, idle check, restrictive permissions and retention.
4. Run `python3 integration/device-backup/test_policy.py`.
5. Run the normal idle snapshot, inspect its archive member list, and verify
   the SlyGuy dependency sources and consistent database copies are present.
   Retain a verified off-device copy before declaring the replacement ready.

To repair a previously incomplete clone, restore the four missing sources from
the exact installed version's official SlyGuy dependency archive after checking
addon ID/version and zip paths. Do not replace the independent global urllib3
addon, mix arbitrary PyPI versions, disable TLS or copy private userdata.
The accepted0.0.30 source was the [official addon archive](https://slyguy.uk/.repo/repository.slyguy/slyguy.dependencies/slyguy.dependencies-0.0.30.zip),
SHA256 `ff651f4ca1a6afb963868dc0a962064236b5c9c726a04b9425e43916fb3cb7f2`.
Confirm the actual Kodi SlyGuy/trailer import succeeds afterward. Revert using
the private changed-file backup, not another device's profile.

This module preserves the exclusion policy only. The private worker, destination,
host identity, archives and credentials never belong in this repository.
