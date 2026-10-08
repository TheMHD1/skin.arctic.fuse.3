"""One guarded paired update; composes the preceding shared repair when needed."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import overlay

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

shared=load('ux_shared_release',HERE.parent/'shared-am9/install.py')
transaction=shared.transaction
RELEASE='am9-shared-20261008.2'
MANIFEST=shared.MANIFEST
RECEIPT='.config/am9-ux-release.json'
AFTER={
    'local':{overlay.BROWSER:'ad999c6bc1e920093c6dd5187a2ee089adac4fcab3f3a610bf613a868d798107',
             overlay.SERVICE:'eb775a8f8c2926aaa7bd8b0a4a20dfd49aba53bb410b007e37a3b4c026566535',
             overlay.SELECTOR:'02efa4cc7e932a0e8f73e8ce7b2f75758dcc4744adacbd4adebef2908ca7cf7c'},
    'remote':{overlay.BROWSER:'f81b91f1ec47a21ef88a78517850878c014329bf04cb849f383a23e2789e6aa7',
              overlay.SERVICE:'eb775a8f8c2926aaa7bd8b0a4a20dfd49aba53bb410b007e37a3b4c026566535',
              overlay.SELECTOR:'02efa4cc7e932a0e8f73e8ce7b2f75758dcc4744adacbd4adebef2908ca7cf7c'},
}
FINAL={'local':'d3067fceabc4976cced6d350beb17a24d853a7a8a2138800433e6fb959e76abe',
       'remote':'02382819780f6ddf9e11d6e3539e38dfc9815c73c6c02cb279b16f156f2f9a26'}
INTERIM={'remote':{
    '5ebfa0ad49c2ee659791620d7aeccba37240d595b40bc0ba6e450a21df3f662d':{
        overlay.BROWSER:'cf31553e263f0fc93147d049c9149ced7c1ae204fe5d86aaa9c3d39933097c59',
        overlay.SERVICE:'40eafb981bd4fa64e0dc0f406fe46d284933e5073a72d8782c77516e995c452c',
        overlay.SELECTOR:'6dd23ea80a48de5956ecc931bb28e30ed57a40a120e3b2afc7e2d2b80042a5dc'},
    'e548425a3d8f1d27cf8de74db45c4d17914531274e3dc30bd5a12d48ff7d761f':{
        overlay.BROWSER:'9a272997d31cf7dbd11f322d195a04782427a3f942e3ec5c4e72dee4286df45a',
        overlay.SERVICE:'40eafb981bd4fa64e0dc0f406fe46d284933e5073a72d8782c77516e995c452c',
        overlay.SELECTOR:'4931e8cab72b42130480a5293094b0b9bd343d7a60a04e3a469bdaafbc6d41b9'},
    '02fbda64ae570eba422a47e90b6992a78913c71d38fc9b8656ef6e32e38a1e64':{
        overlay.BROWSER:'9d6cc039c21ef8fc89a824608151399f29e658b50354f905d0e0e3b1fdfc6f49',
        overlay.SERVICE:'eb775a8f8c2926aaa7bd8b0a4a20dfd49aba53bb410b007e37a3b4c026566535',
        overlay.SELECTOR:'fc169953f15b89062d72b4ffdd40526f04ff744612297bf73e2a6bc6703f7eaa'},
    'aa8fdeaef90453f951f165ff5c4829a51995e56d2822a41db73c92d9fbbd8ed3':{
        overlay.BROWSER:'9d6cc039c21ef8fc89a824608151399f29e658b50354f905d0e0e3b1fdfc6f49',
        overlay.SERVICE:'eb775a8f8c2926aaa7bd8b0a4a20dfd49aba53bb410b007e37a3b4c026566535',
        overlay.SELECTOR:'02efa4cc7e932a0e8f73e8ce7b2f75758dcc4744adacbd4adebef2908ca7cf7c'}}}

def sha(data):return hashlib.sha256(data).hexdigest()

def plan(root,profile):
    if root.is_symlink() or root.resolve()!=root:raise ValueError('Unsafe storage root')
    identity=shared.identity(root,profile)
    cohort=profile['cohort']
    path=shared.regular(root,MANIFEST)
    raw=path.read_bytes();manifest=json.loads(raw)
    interim=sha(raw) in INTERIM.get(cohort,{})
    if interim:
        expected={path:raw,**identity}
        for name,digest in manifest['files'].items():
            source=shared.regular(root,'.kodi/'+name);data=source.read_bytes()
            if sha(data)!=digest:raise ValueError('Interim source drift')
            expected[source]=data
        interim_pins=INTERIM[cohort][sha(raw)]
        if any(manifest['files'].get(n)!=d for n,d in interim_pins.items()):
            raise ValueError('Unreviewed interim outputs')
        result=transaction.Plan({},expected)
        source=shared.regular(root,'.kodi/'+overlay.BROWSER)
        text=expected[source].decode()
        if sha(raw)=='5ebfa0ad49c2ee659791620d7aeccba37240d595b40bc0ba6e450a21df3f662d':
            text=overlay.harden_close(text)
        result[source]=overlay.remote_handoff(text.replace('System.HasModalDialog','System.HasActiveModalDialog')).encode()
        helper=shared.regular(root,'.kodi/'+overlay.SELECTOR)
        result[helper]=(HERE/'search_selection.py').read_bytes()
        service=shared.regular(root,'.kodi/'+overlay.SERVICE)
        result[service]=expected[service].replace(b'System.HasModalDialog',b'System.HasActiveModalDialog')
        for name in (overlay.BROWSER,overlay.SELECTOR,overlay.SERVICE):
            source=shared.regular(root,'.kodi/'+name)
            if sha(result[source])!=AFTER[cohort][name]:raise ValueError('Interim repair output drift')
            manifest['files'][name]=sha(result[source])
            if result[source]==expected[source]:del result[source]
        result[path]=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
        if sha(result[path])!=FINAL[cohort]:raise ValueError('Interim final manifest drift')
    elif manifest.get('am9_ux_release')==RELEASE:
        if sha(raw)!=FINAL[cohort]:raise ValueError('Unreviewed final UX manifest')
        expected={path:raw,**identity}
        for name,digest in manifest['files'].items():
            source=shared.regular(root,'.kodi/'+name);data=source.read_bytes()
            if sha(data)!=digest:raise ValueError('UX manifest source drift')
            expected[source]=data
        for name,digest in AFTER[cohort].items():
            if manifest['files'].get(name)!=digest:raise ValueError('UX output pin drift')
        result=transaction.Plan({},expected)
    else:
        # This protects the entire earlier cohort and composes its pending writes
        # into ONE idle transaction instead of requiring another historical step.
        result=shared.plan(root,profile)
        raw=result.get(path,raw);manifest=json.loads(raw)
        for name in overlay.BEFORE[cohort]:
            source=shared.regular(root,'.kodi/'+name)
            data=result.get(source,source.read_bytes())
            output=overlay.transform(name,data,cohort)
            if sha(output)!=AFTER[cohort][name]:raise ValueError('Unexpected UX output')
            result[source]=output;manifest['files'][name]=sha(output)
        selector_path=shared.regular(root,'.kodi/'+overlay.SELECTOR)
        if selector_path.exists():raise ValueError('Unreviewed existing search selector helper')
        helper=(HERE/'search_selection.py').read_bytes()
        if sha(helper)!=AFTER[cohort][overlay.SELECTOR]:raise ValueError('Search helper source drift')
        result.expected[selector_path]=None;result[selector_path]=helper
        manifest['files'][overlay.SELECTOR]=sha(helper)
        manifest['am9_ux_release']=RELEASE
        result[path]=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
        if sha(result[path])!=FINAL[cohort]:raise ValueError('Unexpected UX manifest output')
    receipt_path=shared.regular(root,RECEIPT)
    receipt={'schema':1,'release':RELEASE,'cohort':cohort,
             'manifest_sha256':sha(result.get(path,raw)),
             'acceptance':'installed-source-live-checks-separate'}
    payload=(json.dumps(receipt,indent=2,sort_keys=True)+'\n').encode()
    before=receipt_path.read_bytes() if receipt_path.exists() else None
    result.expected[receipt_path]=before
    old_receipt={**receipt,'manifest_sha256':sha(raw)}
    old_payload=(json.dumps(old_receipt,indent=2,sort_keys=True)+'\n').encode()
    if before is not None and before!=payload and not (interim and before==old_payload):
        raise ValueError('Unreviewed UX receipt')
    if before!=payload:result[receipt_path]=payload
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/storage'))
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    profile=json.loads(args.profile.read_text())
    if socket.gethostname()!=profile['hostname']:raise SystemExit('Wrong appliance')
    mac=Path('/sys/class/net/wlan0/address');mac_raw=mac.read_bytes()
    if mac_raw.decode().strip().lower()!=profile['wlan_mac'].lower():raise SystemExit('Wrong hardware')
    result=plan(args.root,profile);result.expected[mac]=mac_raw
    print(json.dumps({'release':RELEASE,'cohort':profile['cohort'],
                      'mode':'apply' if args.apply else 'plan-only',
                      'changes':[str(p.relative_to(args.root)) for p in result]},indent=2))
    if args.apply and result:
        backup=args.root/'backup'/(RELEASE+'-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
        transaction.deploy(args.root,result,backup)
        if plan(args.root,profile):raise RuntimeError('UX final plan not idempotent')
        print('Applied; rollback:',backup)
