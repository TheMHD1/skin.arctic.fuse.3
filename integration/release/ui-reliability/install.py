"""Reviewed remote UI source overlay; defaults to a no-write plan."""
import argparse
import hashlib
import json
import socket
import sys
import time
from pathlib import Path, PurePosixPath
import overlay

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'kodi'))
import transaction

MANIFEST='addons/plugin.video.habibi.resume/verified-build.json'
BASE_MANIFEST='df2ff757baaac9405e47fb9c29d9b96d7b67d2fff2648a11486adca7bb430c1e'
LAYER='remote-ui-reliability-20261001-r2'
PREVIOUS_MANIFEST='f2ca10b66b40102793f97423c60389578c08e336a004a68902be3a9541e049f4'
PREVIOUS_BROWSER='d3267ee07ce3919cb74ba4f3b144b8d2b652f317199ad59e66fba2d53e4b1d34'


def plan(root):
    manifest_path=root/MANIFEST
    original=manifest_path.read_bytes()
    manifest=json.loads(original)
    expected={manifest_path:original}
    for name,digest in manifest['files'].items():
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe manifest path')
        path=root/name
        data=path.read_bytes()
        if path.is_symlink() or hashlib.sha256(data).hexdigest()!=digest:
            raise ValueError('Manifest drift: '+name)
        expected[path]=data
    if manifest.get('ui_reliability')==LAYER:
        return transaction.Plan({},expected)
    manifest_hash=hashlib.sha256(original).hexdigest()
    if manifest_hash not in (BASE_MANIFEST,PREVIOUS_MANIFEST):
        raise ValueError('Unreviewed starting cohort')
    changes={}
    for name in overlay.BEFORE:
        path=root/name
        if manifest_hash==PREVIOUS_MANIFEST:
            if not name.endswith('/browser.py'):continue
            if hashlib.sha256(expected[path]).hexdigest()!=PREVIOUS_BROWSER:
                raise ValueError('Unreviewed interim browser')
            data=overlay.playback_lifecycle(expected[path].decode()).encode()
        else:
            data=overlay.transform(name,expected[path])
        changes[path]=data
        manifest['files'][name]=hashlib.sha256(data).hexdigest()
    manifest['ui_reliability']=LAYER
    changes[manifest_path]=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    return transaction.Plan(changes,expected)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/storage/.kodi'))
    parser.add_argument('--expected-hostname',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if socket.gethostname()!=args.expected_hostname:
        raise SystemExit('Wrong appliance')
    changes=plan(args.root)
    print(json.dumps({'changes':[str(p.relative_to(args.root)) for p in changes]}))
    if args.apply and changes:
        backup=Path('/storage/backup')/(LAYER+'-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
        transaction.deploy(args.root,changes,backup)
        print('Backup:',backup)
        if plan(args.root):raise RuntimeError('Non-idempotent final plan')
