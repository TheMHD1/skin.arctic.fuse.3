"""Apply the exact shared addon plan to an offline, identified ext4 appliance disk.

This does not repair a filesystem, update firmware, migrate a blank installation,
or certify a live device. Use only after verified off-device recovery backups.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('offline_shared_release', HERE.parent/'library-transactions/install.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def command(*args):
    return subprocess.check_output(args, text=True, timeout=15).strip()


def guard(root, profile, probe=command, hostname=socket.gethostname):
    if root == Path('/') or root.is_symlink() or root.resolve() != root:
        raise ValueError('Unsafe offline storage root')
    policy = profile.get('offline_recovery', {})
    for key in ('maintenance_host', 'storage_uuid', 'disk_serial'):
        if not isinstance(policy.get(key), str) or not policy[key].strip():
            raise ValueError('Missing offline media identity: '+key)
    if hostname() != policy['maintenance_host'] or hostname() == profile['hostname']:
        raise ValueError('Wrong maintenance host or live appliance')
    mounts = json.loads(probe('findmnt', '--json', '--target', str(root), '-o', 'TARGET,SOURCE,FSTYPE,OPTIONS'))['filesystems']
    if len(mounts) != 1:
        raise ValueError('Ambiguous offline mount')
    mount = mounts[0]
    if mount['target'] != str(root) or mount['fstype'] != 'ext4' or 'rw' not in mount['options'].split(','):
        raise ValueError('Requires the exact offline ext4 mount, writable')
    source = mount['source']
    if not source.startswith('/dev/') or '[' in source:
        raise ValueError('Unsupported filesystem source')
    if probe('blkid', '-s', 'UUID', '-o', 'value', source) != policy['storage_uuid']:
        raise ValueError('Wrong storage UUID')
    parent = probe('lsblk', '-dn', '-o', 'PKNAME', source)
    if not parent or '/' in parent or '\n' in parent:
        raise ValueError('Requires one physical partition parent')
    if probe('lsblk', '-dn', '-o', 'SERIAL', '/dev/'+parent) != policy['disk_serial']:
        raise ValueError('Wrong physical disk serial')
    return source


def validate(root, plan):
    for path in set(plan) | set(plan.expected):
        release.shared.regular(root, str(path.relative_to(root)))
    for path, expected in plan.expected.items():
        if (path.read_bytes() if path.exists() else None) != expected:
            raise ValueError('Source changed since planning: '+str(path))
    for path in plan:
        if path.is_symlink() or path.with_name(path.name+'.audit-tmp').exists():
            raise ValueError('Foreign destination or staging file')


def deploy(root, profile, plan, backup, check_guard=guard, write=release.transaction.atomic_write):
    if not isinstance(plan, release.transaction.Plan):
        raise ValueError('Requires a guarded shared-release plan')
    if not plan:
        return False
    check_guard(root, profile)
    validate(root, plan)
    free = os.statvfs(root)
    if free.f_bavail * free.f_frsize < 4 * sum(len(data) for data in plan.values()) + 10*1024*1024:
        raise ValueError('Insufficient rollback space')
    originals = {p: (p.read_bytes(), p.stat().st_mode & 0o777, p.stat().st_uid, p.stat().st_gid)
                 if p.exists() else (None, 0o644, 0, 0) for p in plan}
    release.shared.regular(root, str(backup.relative_to(root)))
    backup.mkdir(parents=True, mode=0o700, exist_ok=False)
    records = []
    for path, (data, mode, uid, gid) in originals.items():
        name = str(path.relative_to(root))
        if data is not None:
            target = backup/name
            target.parent.mkdir(parents=True, exist_ok=True)
            release.transaction.atomic_write(target, data, mode)
        records.append({'path': name, 'existed': data is not None, 'mode': mode, 'uid': uid, 'gid': gid})
    release.transaction.atomic_write(backup/'change-paths.json', (json.dumps(records, indent=2)+'\n').encode(), 0o600)
    check_guard(root, profile)
    validate(root, plan)
    written = []
    try:
        for path, data in plan.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            written.append(path)
            _, mode, uid, gid = originals[path]
            write(path, data, mode)
            os.chown(path, uid, gid)
        os.sync()
        if release.plan(root, profile):
            raise ValueError('Shared release did not converge')
    except (Exception, KeyboardInterrupt):
        for path in reversed(written):
            data, mode, uid, gid = originals[path]
            if data is None:
                path.unlink(missing_ok=True)
            else:
                release.transaction.atomic_write(path, data, mode)
                os.chown(path, uid, gid)
        os.sync()
        raise
    return True


def verified_image(path, digest):
    if path.is_symlink() or not path.is_file() or len(digest) != 64:
        raise ValueError('Requires an off-device regular recovery image and SHA256')
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4*1024*1024), b''):
            result.update(chunk)
    if result.hexdigest() != digest:
        raise ValueError('Recovery image checksum mismatch')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--recovery-image', type=Path)
    parser.add_argument('--recovery-sha256')
    args = parser.parse_args()
    profile = json.loads(args.profile.read_bytes())
    guard(args.root, profile)
    plan = release.plan(args.root, profile)
    print(json.dumps({'release': release.RELEASE, 'cohort': profile['cohort'],
                     'mode': 'offline-apply' if args.apply else 'offline-plan',
                     'changes': [str(p.relative_to(args.root)) for p in plan]}, indent=2))
    if args.apply and plan:
        if args.recovery_image is None or args.recovery_sha256 is None:
            parser.error('--apply requires --recovery-image and --recovery-sha256')
        if args.recovery_image.resolve().is_relative_to(args.root):
            raise ValueError('Recovery image must be independently off-device')
        verified_image(args.recovery_image, args.recovery_sha256)
        backup = args.root/'backup'/('offline-'+release.RELEASE+'-'+time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
        deploy(args.root, profile, plan, backup)
        print('Offline source installed; live device acceptance still required. Rollback:', backup)
