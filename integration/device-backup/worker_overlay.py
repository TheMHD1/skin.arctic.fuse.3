"""Reviewed root-selection migration; retain private identity/retention/SQLite logic."""

OLD_IMPORT = 'from device_backup_policy import should_skip'
NEW_IMPORT = 'from device_backup_policy import should_skip, SNAPSHOT_ROOTS'
OLD_LOOP = "for base in ['.kodi/addons','.kodi/userdata','.config','.cache/hostname','.cache/tailscale/tailscaled.state']:"
NEW_LOOP = 'for base in SNAPSHOT_ROOTS:'


def transform(source):
    for old, new in ((OLD_IMPORT, NEW_IMPORT), (OLD_LOOP, NEW_LOOP)):
        if source.count(old) != 1:
            raise ValueError('Unreviewed snapshot source anchor')
        source = source.replace(old, new)
    compile(source, 'private-snapshot-worker', 'exec')
    return source
