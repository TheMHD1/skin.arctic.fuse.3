"""Reviewed local rsync snapshot repair, preserving the private worker."""
import hashlib

BEFORE = '3e17643d150ef02893fa28263bd732ddfdc5c3395cea3b6d07e0c0f6fb05a383'


def transform(data):
    if hashlib.sha256(data).hexdigest() != BEFORE:
        raise ValueError('Unreviewed local backup worker')
    source = data.decode()
    old = "--exclude='packages/'"
    if source.count(old) != 1:
        raise ValueError('Unexpected package exclusion')
    source = source.replace(old, "--exclude='/packages/'")
    anchor = 'rsync -a /storage/.cache/hostname "${backup_root}coreelec-state/hostname"\n'
    if source.count(anchor) != 1:
        raise ValueError('Unexpected network snapshot anchor')
    # Optional on the LAN device; never transplant another device's state.
    source = source.replace(anchor, anchor + '''if [ -f /storage/.cache/regdomain.conf ]; then
  rsync -a /storage/.cache/regdomain.conf "${backup_root}coreelec-state/regdomain.conf"
fi
''')
    return source.encode()
