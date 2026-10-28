# Local restricted-receiver backup acceptance

`am9-local-backup-receiver-20261028.1` is an additive, local-only acceptance
boundary above the complete `am9-shared-20261008.7` paired plan. It does not
rewrite that release's immutable manifest or its historical
`local_backup_sha256`. The older value records what the shared release installed;
it is not silently repurposed as the current worker identity. The new receipt
records both the replaced and accepted worker digests.

The restricted receiver package began inode-pinning an existing destination
file as `/proc/self/fd/N`. Receiver rsync cannot replace that procfs pathname.
The separately reviewed worker repair changes only the status marker, hostname
and optional regulatory-hint destinations to their existing parent directories,
retaining each source basename. Its exact accepted worker SHA-256 is
`d063c27e77590ffd45d900ad968b33bbf4b7cc723ce0d25b555e0301adae8842`.

## Public/private boundary

The public layer does not contain the appliance's backup destination, SSH key,
database names or private acceptance files. A root-owned private profile must
preauthorize three exact hashes: the installer receipt, the immutable private
acceptance evidence and the final public receipt. The private evidence is small,
non-symlinked and owner-private. It must bind the local hostname/MAC/cohort,
reviewed worker on both source and destination, successful recent service run,
destination success marker inside that run, installer receipt, and exactly
fourteen successful SQLite quick checks.

`acceptance_plan()` consumes that exact evidence and proposes only the public
receipt. It never installs a worker, writes a file, starts Kodi, starts the
backup service or reboots. A separate reviewed recorder may consume the plan,
but must revalidate its complete expected snapshot immediately before writing
the sole receipt change.
Default `plan()` validates the final receipt and worker. It preserves every
parent expected key/value and adds exactly the local worker and receipt. The
remote branch never reads or owns the local worker and requires the local-only
receipt to remain absent. Parent expected cardinality is derived from the
complete parent plan; it is never hard-coded to the currently observed 73 local
or 77 remote entries.

The standalone command also requires its private profile and acceptance
evidence to be absolute, owner-private, single-link regular files reached
without symlinks. Their contents are read through no-follow file descriptors;
the public repository contains neither file.

Run the fake-only source tests with:

```sh
python3 integration/release/local-backup-receiver/test_install.py
```

After an independently reviewed recorder writes the receipt, run the complete
local plan again and require zero changes. A future full paired guard should use
a new versioned guard directory and source-tree hash importing this layer. Keep
the previous guard and recovery archives immutable. Never copy the local worker,
receipt, private evidence, network state, account profile or backup credentials
to the remote AM9.
