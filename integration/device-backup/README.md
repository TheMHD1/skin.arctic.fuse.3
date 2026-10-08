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

## October 2 network-recovery catch-up

`SNAPSHOT_ROOTS` also selects `.cache/regdomain.conf` and `.cache/connman`.
The previous private worker selected only hostname and Tailscale state from
`.cache`: its daily archive therefore did not preserve the successful Canadian
radio hint or the appliance's ConnMan Wi-Fi credentials/provisioning. The earlier
claim that storing provisioning in ConnMan automatically put it in snapshots
was incorrect for that worker's selected roots.

`worker_overlay.py` replaces only the reviewed import and literal root list.
Before applying, bind the private worker to its reviewed full-file SHA-256 and
retain a private copy. Install the new policy first, then the worker. Identity,
idle check, SQLite online copies, permissions, destination and retention remain
unchanged. Unknown/duplicate anchors fail closed. The additive remote installer
in `../release/remote-catchup/` includes this migration with source guards and
rollback. It was prepared against a saved cohort on October2 and installed
through the shared release on October8. The new private snapshot was copied
off-device: network/regulatory recovery files, Tailscale state, four bundled
dependency sources, all59 repair hashes and nine SQLite quick checks passed.

Run both `test_policy.py` and `test_worker_overlay.py`. After deployment run one
normal idle snapshot; verify its member list includes the regulatory file and
the intended device's ConnMan provisioning/settings, alongside dependency source,
Tailscale state and consistent databases. Copy it off-device and verify its
checksum. An existing timer alone does not establish successful new backup coverage.
Archives contain secrets and remain private. Restore network credentials only
to their original appliance; never copy Tailscale state/host keys between devices.

The private worker, destination, host identity, archives and credentials never
belong in this repository.

## Original rsync worker audit

The October2 live-original audit found the same broad directory-name hazard in
its separate shell worker: `--exclude='packages/'` applies at arbitrary depths.
`local_overlay.py` roots the cache exclusion to `--exclude='/packages/'`, keeping
bundled `urllib3/packages` source. It also adds an optional copy of this device's
regulatory hint, while retaining the already-selected ConnMan state, private
destination, SQLite consistency, status and boot-critical backup logic.

The worker is whole-file SHA-256 guarded and remains private. The correction is
included in the [shared AM9 plan](../release/shared-am9/README.md), prepared but
not installed. `test_local_overlay.py` uses actual rsync filter semantics to
verify that the download cache is omitted and bundled dependency packages remain.
Do not transplant the remote Python worker onto the local mirror or point both
devices at the same backup destination. Verify a new snapshot after deployment.
