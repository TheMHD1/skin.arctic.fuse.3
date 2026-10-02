"""Exclude only known Kodi caches, never identically named addon source trees."""
from pathlib import PurePosixPath

# Selected /storage roots, including this appliance's own network recovery
# state. Archives stay private; these names are not a profile to clone.
SNAPSHOT_ROOTS = (
    '.kodi/addons', '.kodi/userdata', '.config', '.cache/hostname',
    '.cache/tailscale/tailscaled.state', '.cache/regdomain.conf', '.cache/connman',
)

EXCLUDED_TREES = (
    ('.kodi', 'addons', 'packages'),
    ('.kodi', 'userdata', 'Thumbnails'),
    ('.kodi', 'userdata', 'Database'),  # SQLite-consistent copies are added separately.
)


def should_skip(relative):
    parts = PurePosixPath(str(relative)).parts
    if not parts or '..' in parts or PurePosixPath(str(relative)).is_absolute():
        raise ValueError('Expected a relative path within the snapshot root')
    if '__pycache__' in parts:
        return True
    return any(parts[:len(prefix)] == prefix for prefix in EXCLUDED_TREES)
