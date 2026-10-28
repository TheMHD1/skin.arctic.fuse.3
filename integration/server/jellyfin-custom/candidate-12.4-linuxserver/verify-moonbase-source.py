#!/usr/bin/env python3
"""Verify an exact regular-file source manifest; optionally copy only that set."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import shutil
import stat

HERE = Path(__file__).resolve().parent


def verify(root, manifest):
    root, manifest = Path(root), Path(manifest)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('source root must be a real directory')
    expected = {}
    for line in manifest.read_text().splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  (.+)', line)
        if not match:
            raise ValueError('invalid source manifest entry')
        digest, name = match.groups()
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or str(path) != name
                or '\\' in name or any(ord(char) < 32 for char in name)):
            raise ValueError('unsafe source manifest path')
        if name in expected:
            raise ValueError('duplicate source manifest path')
        expected[name] = digest
    if not expected:
        raise ValueError('empty source manifest')
    actual = set()
    for path in root.rglob('*'):
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError('source symlink or special file is forbidden')
        actual.add(path.relative_to(root).as_posix())
    if actual != set(expected):
        raise ValueError('source file set does not exactly match manifest')
    for name, digest in expected.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError('source content does not match manifest')
    return expected


def copy_verified(root, manifest, destination):
    expected = verify(root, manifest)
    destination = Path(destination)
    if destination.is_symlink() or not destination.is_dir() or any(destination.iterdir()):
        raise ValueError('copy destination must be a new empty real directory')
    for name in expected:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(root) / name, target, follow_symlinks=False)
    # Reject changed source bytes or links introduced during the copy as well.
    verify(destination, manifest)
    return len(expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=HERE / 'moonbase-12.4-source')
    parser.add_argument('--manifest', type=Path, default=HERE / 'moonbase-12.4-source.sha256')
    parser.add_argument('--copy-to', type=Path)
    args = parser.parse_args()
    count = (copy_verified(args.source, args.manifest, args.copy_to) if args.copy_to
             else len(verify(args.source, args.manifest)))
    print(f'Verified exact Moonbase source set: {count} regular files')


if __name__ == '__main__':
    main()
