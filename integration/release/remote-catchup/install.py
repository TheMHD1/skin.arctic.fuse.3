"""Remote r2 catch-up. Default is a no-write plan, never an OS updater."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import socket
import sys
import time
import overlay

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'kodi'))
import transaction

spec = importlib.util.spec_from_file_location('snapshot_overlay', HERE.parents[1]/'device-backup/worker_overlay.py')
snapshot_overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot_overlay)

MANIFEST = '.kodi/addons/plugin.video.habibi.resume/verified-build.json'
BROWSER = '.kodi/addons/plugin.video.venom.tv/browser.py'
BASE_MANIFEST = '9de6f6f448c507c052331a0effa509cdec073fe28a72b2a5c20b32c8795a8401'
AFTER_MANIFEST = 'c21a9c19d5e150828a2a710b38257f2eac36bcd7c1bca5ac0c3a24e4e184edb5'
OLD_POLICY = '776d089afd8602348cf51d0892ae74f62bcabb8812a834dbe09f83852ab39b1d'
NEW_POLICY = '689e0595a826b075f69a69065dbea431fdcdd43ec4cd565967effcda312d5995'
LAYER = 'remote-empty-focus-and-network-backup-20261002'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('Unsafe relative path')
    return path


def plan(root, worker_name, expected_worker_sha):
    worker = root/relative(worker_name)
    if worker.parent != root/'.config':
        raise ValueError('Snapshot worker must be directly under .config')
    manifest_path = root/MANIFEST
    original = manifest_path.read_bytes()
    manifest = json.loads(original)
    expected = {manifest_path:original}
    for name, digest in manifest['files'].items():
        path = root/'.kodi'/relative(name)
        data = path.read_bytes()
        if path.is_symlink() or sha(data) != digest:
            raise ValueError('Manifest drift: '+name)
        expected[path] = data
    policy = root/'.config/device_backup_policy.py'
    for path in (worker, policy):
        if path.is_symlink():
            raise ValueError('Symlink configuration source')
        expected[path] = path.read_bytes()
    policy_data = (HERE.parents[1]/'device-backup/policy.py').read_bytes()
    if sha(policy_data) != NEW_POLICY:
        raise ValueError('Unreviewed replacement snapshot policy')
    if manifest.get('remote_catchup') == LAYER:
        if sha(original) != AFTER_MANIFEST:
            raise ValueError('Unreviewed final manifest')
        if sha(expected[policy]) != sha(policy_data):
            raise ValueError('Snapshot policy drift')
        if sha(expected[worker]) != manifest['snapshot_worker_sha256']:
            raise ValueError('Snapshot worker drift')
        if manifest['snapshot_worker_before_sha256'] != expected_worker_sha:
            raise ValueError('Wrong snapshot starting cohort')
        return transaction.Plan({}, expected)
    if sha(original) != BASE_MANIFEST:
        raise ValueError('Unreviewed remote starting manifest')
    if sha(expected[policy]) != OLD_POLICY or sha(expected[worker]) != expected_worker_sha:
        raise ValueError('Unreviewed snapshot source')
    # Policy first: a timer firing between the atomic writes can still import
    # should_skip; the new worker cannot observe a policy without SNAPSHOT_ROOTS.
    worker_data = snapshot_overlay.transform(expected[worker].decode()).encode()
    browser_data = overlay.transform(expected[root/BROWSER])
    manifest['files'][BROWSER.removeprefix('.kodi/')] = sha(browser_data)
    manifest.update(remote_catchup=LAYER, snapshot_worker_sha256=sha(worker_data),
                    snapshot_worker_before_sha256=expected_worker_sha)
    changes = {policy:policy_data, worker:worker_data, root/BROWSER:browser_data,
               manifest_path:(json.dumps(manifest, indent=2, sort_keys=True)+'\n').encode()}
    if sha(changes[manifest_path]) != AFTER_MANIFEST:
        raise ValueError('Unexpected catch-up output')
    return transaction.Plan(changes, expected)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/storage'))
    parser.add_argument('--expected-hostname', required=True)
    parser.add_argument('--snapshot-worker', required=True)
    parser.add_argument('--expected-worker-sha256', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if socket.gethostname() != args.expected_hostname:
        raise SystemExit('Wrong appliance')
    changes = plan(args.root, args.snapshot_worker, args.expected_worker_sha256)
    print(json.dumps({'changes':[str(p.relative_to(args.root)) for p in changes]}))
    if args.apply and changes:
        backup = args.root/'backup'/(LAYER+'-'+time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
        transaction.deploy(args.root, changes, backup)
        print('Backup:', backup)
        if plan(args.root, args.snapshot_worker, args.expected_worker_sha256):
            raise RuntimeError('Non-idempotent final plan')
