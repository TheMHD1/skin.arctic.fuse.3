"""Keep a reviewed private rsync worker compatible with receiver inode pinning.

The source/destination identity remains private. Existing-file receiver targets
may be pinned to /proc/self/fd/N by rrsync; rsync cannot unlink that pathname
when replacing a file. Directory targets retain rsync's normal basename policy.
"""
import hashlib

BEFORE = 'bb2b0dea4bc1d3acacec305514417e52119b8566554744aaad928466d4cf48cd'
REPLACEMENTS = (
    ('"${backup_root}status/backup-running"', '"${backup_root}status/"'),
    ('"${backup_root}coreelec-state/hostname"', '"${backup_root}coreelec-state/"'),
    ('"${backup_root}coreelec-state/regdomain.conf"', '"${backup_root}coreelec-state/"'),
)

def transform(data):
    if hashlib.sha256(data).hexdigest() != BEFORE:
        raise ValueError('Unreviewed local receiver-compatibility worker')
    source = data.decode('utf-8')
    for before, after in REPLACEMENTS:
        if source.count(before) != 1:
            raise ValueError('Missing or duplicate single-file receiver anchor')
        source = source.replace(before, after)
    return source.encode('utf-8')
