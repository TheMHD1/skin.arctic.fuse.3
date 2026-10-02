"""One AM9 release, two guarded device profiles. Default: read-only plan.

This is an additive update of reviewed installed cohorts, not a firmware or
blank-device installer. Private profiles stay out of Git and out of receipts.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import socket
import sys
import time
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'kodi'))
import transaction


def module(name, path, search=None):
    # Legacy installer imports its sibling overlay by name. Bind it only while
    # loading that module; never let it replace this release's local functions.
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    previous = sys.modules.get('overlay')
    if search:
        sys.modules['overlay'] = local_overlay.module(name+'_overlay', search/'overlay.py')
    try:
        spec.loader.exec_module(result)
    finally:
        if search:
            if previous is None:
                sys.modules.pop('overlay', None)
            else:
                sys.modules['overlay'] = previous
    return result


local_overlay = module('paired_local_overlay', HERE/'local_overlay.py')
remote = module('shared_remote_install', HERE.parent/'remote-catchup/install.py', HERE.parent/'remote-catchup')
backup = module('shared_local_backup', HERE.parents[1]/'device-backup/local_overlay.py')
RELEASE = 'am9-shared-20261002.1'
MANIFEST = '.kodi/addons/plugin.video.habibi.resume/verified-build.json'
RECEIPT = '.config/am9-shared-release.json'
LOCAL_BASE = '45e71b792fad7f11c20f260d415eeaf810a40aacfb3d7f432d632e5b081ed160'
LOCAL_FINAL = '009d48883b8b7d84655204f0b65084e1eabd054d201ea6ab6dd7bcb2aa777abf'
LOCAL_BACKUP = '.config/scripts/coreelec-backup.sh'
LOCAL_AFTER = {
    'addons/plugin.video.venom.tv/browser.py': '2f8aedfb7c71e8f5baa85af649b60cfad9d5cbcbd86dd8f915ed157221f17979',
    'addons/plugin.video.kodiseerr/jellyfin_bridge.py': '2956a6eb3f02348aca2b8d5e63704c706d55804ff8ad4cbb1405e39858c83211',
    'addons/skin.arctic.fuse.3/1080i/Includes_Objects.xml': 'dd0384a36046c77ab97cc9f66c76eae9a4903c1e5818c664ec22936eae2d8608',
    'addons/skin.arctic.fuse.3/1080i/Includes_Layouts.xml': 'de209d18f7adfeaef899a91259f185f3f9fb1866954711ea0a6d415dbdabfc9b'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def regular(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('Unsafe relative path')
    current = root
    for component in path.parts:
        current = current/component
        if current.is_symlink():
            raise ValueError('Symlink in guarded path: '+relative)
    return current


def local_plan(root):
    manifest_path = regular(root, MANIFEST)
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    expected = {manifest_path: raw}
    for name, digest in manifest['files'].items():
        path = regular(root, '.kodi/'+name)
        data = path.read_bytes()
        if sha(data) != digest:
            raise ValueError('Manifest drift: '+name)
        expected[path] = data
    worker = regular(root, LOCAL_BACKUP)
    expected[worker] = worker.read_bytes()
    if manifest.get('shared_am9') == RELEASE:
        if sha(raw) != LOCAL_FINAL:
            raise ValueError('Unreviewed final local manifest')
        for name, digest in LOCAL_AFTER.items():
            if manifest['files'].get(name) != digest:
                raise ValueError('Shared local source drift')
        if sha(expected[worker]) != manifest['local_backup_sha256']:
            raise ValueError('Shared local snapshot drift')
        return transaction.Plan({}, expected)
    if sha(raw) != LOCAL_BASE:
        raise ValueError('Unreviewed local starting cohort')
    changes = {}
    for name in local_overlay.BEFORE:
        path = regular(root, '.kodi/'+name)
        payload = local_overlay.transform(name, expected[path])
        if sha(payload) != LOCAL_AFTER[name]:
            raise ValueError('Unexpected shared repair output')
        changes[path] = payload
        manifest['files'][name] = sha(payload)
    changes[worker] = backup.transform(expected[worker])
    manifest.update(shared_am9=RELEASE, local_backup_sha256=sha(changes[worker]))
    changes[manifest_path] = (json.dumps(manifest, indent=2, sort_keys=True)+'\n').encode()
    if sha(changes[manifest_path]) != LOCAL_FINAL:
        raise ValueError('Unexpected local manifest output')
    return transaction.Plan(changes, expected)


def identity(root, profile):
    if profile.get('cohort') not in ('local', 'remote'):
        raise ValueError('Unsupported cohort')
    for key in ('hostname', 'wlan_mac', 'jellyfin_user_id', 'jellyfin_address'):
        if not isinstance(profile.get(key), str) or not profile[key].strip():
            raise ValueError('Missing private identity field: '+key)
    paths = {regular(root, '.cache/hostname'): None,
             regular(root, '.kodi/userdata/addon_data/plugin.video.jellyfin/data.json'): None,
             regular(root, '.kodi/userdata/addon_data/plugin.video.jellyfin/settings.xml'): None}
    expected = {path: path.read_bytes() for path in paths}
    if expected[root/'.cache/hostname'].decode().strip() != profile['hostname']:
        raise ValueError('Wrong appliance hostname')
    auth = json.loads(expected[root/'.kodi/userdata/addon_data/plugin.video.jellyfin/data.json'])['Servers'][0]
    if (auth.get('UserId') != profile['jellyfin_user_id'] or
            (auth.get('address') or auth.get('Address')) != profile['jellyfin_address']):
        raise ValueError('Wrong Jellyfin account/server profile')
    settings = {node.get('id'): node.text or node.get('value') or '' for node in
                ET.fromstring(expected[root/'.kodi/userdata/addon_data/plugin.video.jellyfin/settings.xml']).iter('setting')}
    if settings.get('useDirectPaths') != ('1' if profile['cohort'] == 'local' else '0'):
        raise ValueError('Wrong Native/remote transport profile')
    if profile['cohort'] == 'remote':
        address = urlsplit(profile['jellyfin_address'])
        if address.scheme != 'https' or not address.hostname or address.username or address.password:
            raise ValueError('Remote profile requires authenticated HTTPS without URL credentials')
        if settings.get('sslverify', '').lower() not in ('', 'true', '1'):
            raise ValueError('Remote TLS verification must not be disabled')
    marker = regular(root, '.kodi/userdata/addon_data/plugin.video.venom.tv/remote-native.json')
    marker_data = marker.read_bytes() if marker.exists() else None
    if (sha(marker_data) if marker_data is not None else None) != profile.get('remote_marker_sha256'):
        raise ValueError('Wrong remote routing marker')
    if (profile['cohort'] == 'remote') != (marker_data is not None):
        raise ValueError('Cohort/marker mismatch')
    expected[marker] = marker_data
    return expected


def plan(root, profile):
    if root.is_symlink() or root.resolve() != root:
        raise ValueError('Root must be an absolute, non-symlink storage path')
    expected_identity = identity(root, profile)
    if profile['cohort'] == 'local':
        result = local_plan(root)
    else:
        # Prevalidate every path, including the private worker and policy,
        # before delegating to the existing exact-r2 transaction plan.
        worker_name = profile['snapshot_worker']
        for name in (MANIFEST, worker_name, '.config/device_backup_policy.py'):
            regular(root, name)
        for name in json.loads((root/MANIFEST).read_bytes())['files']:
            regular(root, '.kodi/'+name)
        result = remote.plan(root, worker_name, profile['snapshot_worker_before_sha256'])
    result.expected.update(expected_identity)
    # Protect existing display, seeking, audio and network configuration against
    # changes during planning. No files from these areas are copied or written.
    for pattern in ('.kodi/userdata/keymaps/*.xml', '.kodi/userdata/peripheral_data/*.xml',
                    '.cache/connman/*/settings', '.cache/connman/*.config', '.cache/regdomain.conf'):
        for path in root.glob(pattern):
            regular(root, str(path.relative_to(root)))
            if path.is_file():
                result.expected[path] = path.read_bytes()
    manifest_raw = result.get(root/MANIFEST, (root/MANIFEST).read_bytes())
    receipt = {'schema': 1, 'release': RELEASE, 'cohort': profile['cohort'],
               'manifest_sha256': sha(manifest_raw),
               'acceptance': 'source-installed-live-behaviour-pending'}
    receipt_raw = (json.dumps(receipt, indent=2, sort_keys=True)+'\n').encode()
    path = regular(root, RECEIPT)
    previous = path.read_bytes() if path.exists() else None
    result.expected[path] = previous
    if previous is not None and previous != receipt_raw:
        raise ValueError('Unreviewed release receipt')
    if previous != receipt_raw:
        result[path] = receipt_raw
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/storage'))
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text())
    if socket.gethostname() != profile['hostname']:
        raise SystemExit('Wrong appliance')
    mac_path = Path('/sys/class/net/wlan0/address')
    mac_raw = mac_path.read_bytes()
    if mac_raw.decode().strip().lower() != profile['wlan_mac'].lower():
        raise SystemExit('Wrong hardware identity')
    result = plan(args.root, profile)
    result.expected[mac_path] = mac_raw
    print(json.dumps({'release': RELEASE, 'cohort': profile['cohort'],
                      'mode': 'apply' if args.apply else 'plan-only',
                      'changes': [str(p.relative_to(args.root)) for p in result]}, indent=2))
    if args.apply and result:
        rollback = args.root/'backup'/(RELEASE+'-'+time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
        transaction.deploy(args.root, result, rollback)
        if plan(args.root, profile):
            raise RuntimeError('Final release plan is not idempotent')
        print('Installed source; physical acceptance pending. Rollback:', rollback)
