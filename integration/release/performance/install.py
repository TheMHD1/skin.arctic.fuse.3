"""Paired AM9 performance update; exact source and private identity guards."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import time

HERE=Path(__file__).resolve().parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

overlay=load('performance_overlay',HERE/'overlay.py')
previous_overlay=load('performance_parent_overlay',HERE.parent/'ux-round/overlay.py')
binding=sys.modules.get('overlay')
sys.modules['overlay']=previous_overlay
try:previous=load('performance_parent_install',HERE.parent/'ux-round/install.py')
finally:
    if binding is None:sys.modules.pop('overlay',None)
    else:sys.modules['overlay']=binding
shared=previous.shared
transaction=previous.transaction
RELEASE='am9-shared-20261008.3'
MANIFEST=previous.MANIFEST
RECEIPT='.config/am9-performance-release.json'
# Exact paired outputs, reproduced from public inputs and complete saved cohorts.
AFTER={
    'local':{overlay.BROWSER:'832606869ece94df80c01bcd1b0b3d4d66147d74c92b5e9ae36c91501caf162c'},
    'remote':{overlay.BROWSER:'b56bd320e64dfc1866db3995059ad8385259a6b6db8606e6bc968e168d28cd88'},
}
for row in AFTER.values():
    row.update({overlay.FAVORITES:'7cdddfa38e1c0c5d62f14ba1e4f1a3deeef5ab73cef0bb7f5e74d5bba9352f0d',
                overlay.CLIENT:'75bb81b9f4c0e027fa3cdd6d7b220e41a90549b3585a4bf15abe8acbbf6afeca',
                overlay.HELPER:'48bc2dbde49c78b85e3f6e8b0c22ed58dc5a4bb2ef0d78dd074205fcac80c92c'})
FINAL={'local':'857e91d76f7cd41782fa7b73e56e0fcf8ecfb2d185afee09e4174015ec78d867',
       'remote':'f89430cd3d0620cbe8186d60fb88b7b684d24eaaaf07218823a71239aff62678'}

def sha(data):return hashlib.sha256(data).hexdigest()

def receipt(cohort,manifest_sha):
    return (json.dumps({'schema':1,'release':RELEASE,'cohort':cohort,
        'manifest_sha256':manifest_sha,'acceptance':'source-installed-behaviour-checked-separately'},
        indent=2,sort_keys=True)+'\n').encode()

def plan(root,profile):
    if root.is_symlink() or root.resolve()!=root:raise ValueError('Unsafe storage root')
    identity=shared.identity(root,profile);cohort=profile['cohort']
    path=shared.regular(root,MANIFEST);raw=path.read_bytes();manifest=json.loads(raw)
    target=shared.regular(root,RECEIPT)
    old_receipt=target.read_bytes() if target.exists() else None
    if manifest.get('am9_performance_release')==RELEASE:
        if sha(raw)!=FINAL[cohort]:raise ValueError('Unreviewed performance manifest')
        expected={path:raw,**identity,target:old_receipt}
        for name,digest in manifest['files'].items():
            source=shared.regular(root,'.kodi/'+name);data=source.read_bytes()
            if sha(data)!=digest:raise ValueError('Performance source drift')
            expected[source]=data
        if any(manifest['files'].get(n)!=v for n,v in AFTER[cohort].items()):
            raise ValueError('Performance output pin drift')
        if old_receipt!=receipt(cohort,sha(raw)):raise ValueError('Performance receipt drift')
        result=transaction.Plan({},expected)
    else:
        if old_receipt is not None:raise ValueError('Foreign performance receipt')
        # Compose the entire preceding release into the same transaction when
        # the original appliance has not yet received it. Never omit its guards.
        result=previous.plan(root,profile)
        manifest=json.loads(result.get(path,raw))
        for name in overlay.BEFORE[cohort]:
            source=shared.regular(root,'.kodi/'+name)
            data=result.get(source,source.read_bytes())
            output=overlay.transform(name,data,cohort)
            if sha(output)!=AFTER[cohort][name]:raise ValueError('Performance output drift')
            result[source]=output;manifest['files'][name]=sha(output)
        helper=shared.regular(root,'.kodi/'+overlay.HELPER)
        if helper.exists():raise ValueError('Foreign favourite refresh helper')
        output=(HERE/'favorite_refresh.py').read_bytes()
        if sha(output)!=AFTER[cohort][overlay.HELPER]:raise ValueError('Favourite helper source drift')
        result.expected[helper]=None;result[helper]=output
        manifest['files'][overlay.HELPER]=sha(output)
        manifest['am9_performance_release']=RELEASE
        result[path]=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
        if sha(result[path])!=FINAL[cohort]:raise ValueError('Unexpected performance manifest output')
        result.expected[target]=None;result[target]=receipt(cohort,sha(result[path]))
    # Retain the preceding receipt as historical evidence of the parent build;
    # do not rewrite it to pretend that it describes the new source manifest.
    parent=shared.regular(root,previous.RECEIPT)
    if parent.exists():
        data=parent.read_bytes()
        if result.get(parent,data)!=previous_receipt(cohort):raise ValueError('Parent UX receipt drift')
        result.expected[parent]=data
    for pattern in ('.kodi/userdata/keymaps/*.xml','.kodi/userdata/peripheral_data/*.xml',
                    '.cache/connman/*/settings','.cache/connman/*.config','.cache/regdomain.conf'):
        for protected in root.glob(pattern):
            shared.regular(root,str(protected.relative_to(root)))
            if protected.is_file():result.expected[protected]=protected.read_bytes()
    return result

def previous_receipt(cohort):
    return (json.dumps({'schema':1,'release':previous.RELEASE,'cohort':cohort,
        'manifest_sha256':previous.FINAL[cohort],
        'acceptance':'installed-source-live-checks-separate'},indent=2,sort_keys=True)+'\n').encode()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('/storage'))
    p.add_argument('--profile',type=Path,required=True);p.add_argument('--apply',action='store_true')
    args=p.parse_args();profile=json.loads(args.profile.read_bytes())
    if socket.gethostname()!=profile['hostname']:raise SystemExit('Wrong appliance')
    mac=Path('/sys/class/net/wlan0/address');mac_raw=mac.read_bytes()
    if mac_raw.decode().strip().lower()!=profile['wlan_mac'].lower():raise SystemExit('Wrong hardware')
    changes=plan(args.root,profile);changes.expected[mac]=mac_raw
    print(json.dumps({'release':RELEASE,'cohort':profile['cohort'],
        'mode':'apply' if args.apply else 'plan-only',
        'changes':[str(path.relative_to(args.root)) for path in changes]},indent=2))
    if args.apply and changes:
        backup=args.root/'backup'/(RELEASE+'-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
        transaction.deploy(args.root,changes,backup)
        if plan(args.root,profile):raise RuntimeError('Performance final plan not idempotent')
        print('Applied; rollback:',backup)
