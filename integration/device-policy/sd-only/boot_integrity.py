"""Read-only boot-pair acceptance; filesystem cleanliness is not firmware integrity."""
import hashlib
from pathlib import Path
import re
import stat


def check_pair(root, expected):
    """Accept only both reviewed payload hashes on a real, non-symlink directory.

    This never repairs media, invokes the updater or infers device acceptance.
    Physical identity, mount guards, backups and DTB/settings are separate checks.
    """
    root = Path(root)
    if root.is_symlink() or not root.is_dir() or root.resolve() == Path('/'):
        raise ValueError('Require a dedicated real boot directory')
    if set(expected) != {'kernel.img', 'SYSTEM'} or any(
        not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value)
        for value in expected.values()
    ):
        raise ValueError('Require both exact reviewed SHA256 payload hashes')
    result = {}
    for name, digest in expected.items():
        path = root / name
        if not path.exists() and not path.is_symlink():
            result[name] = {'matches': False, 'reason': 'missing'}
            continue
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError('Boot payload must be a regular file, not a link or device')
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        result[name] = {'matches': actual == digest, 'size': path.stat().st_size,
                        'sha256': actual}
    return {'accepted': all(row['matches'] for row in result.values()), 'files': result}
