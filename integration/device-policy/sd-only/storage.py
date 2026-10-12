"""Offline SD-only conversion helpers; no repartitioning, formatting or flashing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import uuid


def sd_config(text, old_uuid, new_uuid):
    """Replace only the exact storage selector and the retired SSD's UAS quirk."""
    if str(uuid.UUID(old_uuid)) != old_uuid or str(uuid.UUID(new_uuid)) != new_uuid:
        raise ValueError('Canonical storage UUIDs required')
    if old_uuid == new_uuid:
        raise ValueError('Source and destination must differ')
    matches = list(re.finditer(r"^coreelec='([^'\r\n]*)'[ \t]*$", text, re.MULTILINE))
    if len(matches) != 1:
        raise ValueError('Exactly one reviewed active coreelec assignment required')
    match = matches[0]
    tokens = shlex.split(match.group(1))
    if [t for t in tokens if t.startswith('disk=')] != ['disk=UUID=' + old_uuid]:
        raise ValueError('Unexpected storage selector')
    tokens = ['disk=UUID=' + new_uuid if t == 'disk=UUID=' + old_uuid else t
              for t in tokens if t != 'usb-storage.quirks=174c:55aa:u']
    result = text[:match.start()] + "coreelec='" + ' '.join(tokens) + "'" + text[match.end():]
    result = result.replace(
        '# Ugoos AM9 Pro hybrid boot: load the OS to RAM, keep /storage on the Samsung\n'
        '# USB SSD by its unique ext4 UUID, and disable broken UAS on the ASMedia bridge.\n',
        '# Ugoos AM9 Pro standalone SD: boot and persistent storage use this card.\n')
    return result


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root):
    """Private recursive byte/metadata inventory; never follows appliance symlinks."""
    root = Path(root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir() or root == Path('/'):
        raise ValueError('Exact non-symlink mounted/snapshot directory required')
    result = {}

    def visit(path):
        info = path.lstat()
        entry = {'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}
        relative = path.relative_to(root).as_posix()
        if stat.S_ISLNK(info.st_mode):
            entry.update(type='link', target=os.readlink(path))
        elif stat.S_ISREG(info.st_mode):
            entry.update(type='file', size=info.st_size, sha256=sha(path))
        elif stat.S_ISDIR(info.st_mode):
            entry.update(type='dir')
        else:
            raise ValueError('Unexpected special file in offline appliance snapshot')
        entry['xattrs'] = {name: hashlib.sha256(os.getxattr(path, name, follow_symlinks=False)).hexdigest()
                           for name in sorted(os.listxattr(path, follow_symlinks=False))}
        result[relative] = entry
        if entry['type'] == 'dir':
            for child in sorted(path.iterdir()):
                visit(child)

    visit(root)
    return result


def verify_inventory(root, expected):
    actual = inventory(root)
    if actual != expected:
        # Paths may contain private inventory. Keep error output aggregate-only.
        changed = sum(actual.get(name) != expected.get(name) for name in actual.keys() | expected.keys())
        raise ValueError(f'Offline snapshot differs in {changed} entries')
    return len(actual)


def require_mount(row, source, fs, writable):
    """Validate exact findmnt JSON mountpoint data, not an inherited parent mount."""
    if row.get('source') != source or row.get('fstype') != fs:
        raise ValueError('Unexpected mounted partition/filesystem')
    options = row.get('options', '').split(',')
    if ('rw' if writable else 'ro') not in options:
        raise ValueError('Unexpected mount write policy')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('inventory', 'verify'):
        command = sub.add_parser(action)
        command.add_argument('--root', required=True)
        command.add_argument('--manifest', required=True)
    command = sub.add_parser('config')
    command.add_argument('--path', required=True)
    command.add_argument('--old-uuid', required=True)
    command.add_argument('--new-uuid', required=True)
    command.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    if args.action == 'inventory':
        target = Path(args.manifest)
        if target.exists() or target.is_symlink():
            raise ValueError('Never overwrite an existing private inventory')
        payload = inventory(args.root)
        with target.open('x') as output:
            os.chmod(target, 0o600)
            json.dump(payload, output, sort_keys=True)
        print('Private inventory entries:', len(payload))
    elif args.action == 'verify':
        expected = json.loads(Path(args.manifest).read_bytes())
        print('Verified private inventory entries:', verify_inventory(args.root, expected))
    else:
        path = Path(args.path)
        if path.is_symlink() or not path.is_file() or sha(path) != args.expected_sha256:
            raise ValueError('Boot config identity/hash changed')
        content = sd_config(path.read_text(), args.old_uuid, args.new_uuid)
        temporary = path.with_name(path.name + '.sd-only-pending')
        if temporary.exists() or temporary.is_symlink():
            raise ValueError('Existing pending boot config requires review')
        previous = path.stat()
        mode = stat.S_IMODE(previous.st_mode)
        try:
            with temporary.open('x') as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.chown(temporary, previous.st_uid, previous.st_gid)
            temporary.chmod(mode)
            temporary.replace(path)
            os.sync()
            if path.read_text() != content:
                raise ValueError('Boot config readback failed')
        finally:
            if temporary.exists():
                temporary.unlink()
        print('SD storage selector changed; firmware and other boot settings untouched')


if __name__ == '__main__':
    main()
