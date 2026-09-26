"""Exclude only known Kodi caches, never identically named addon source trees."""
from pathlib import PurePosixPath

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
