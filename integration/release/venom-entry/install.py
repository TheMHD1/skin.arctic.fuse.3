"""Paired exact-cohort Venom-entry repair after the performance release."""
import argparse,hashlib,importlib.util,json,socket,time
from pathlib import Path

HERE=Path(__file__).resolve().parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
overlay=load('venom_entry_overlay',HERE/'overlay.py')
previous=load('venom_entry_parent',HERE.parent/'performance/install.py')
shared=previous.shared
transaction=previous.transaction
MANIFEST=previous.MANIFEST
RELEASE='am9-shared-20261008.4'
RECEIPT='.config/am9-venom-entry-release.json'
AFTER='48fd68a7cc1f626bda5e9488940ed3c362f11b3fe3acc5c005ec7044431a418b'
FINAL={'local':'c7a0e103d03c5b8a739c8bdb88f14e6530e6be3b52f977aa236420e18932e977',
       'remote':'69e97deb4258457c3ad25c31fa676bd566d01212ded269d40ef6a3f845236fec'}
def sha(data):return hashlib.sha256(data).hexdigest()
def receipt(cohort,digest):
    return (json.dumps({'schema':1,'release':RELEASE,'cohort':cohort,'manifest_sha256':digest,
        'acceptance':'source-installed-live-acceptance-separate'},indent=2,sort_keys=True)+'\n').encode()

def plan(root,profile):
    if root.is_symlink() or root.resolve()!=root:raise ValueError('Unsafe storage root')
    identity=shared.identity(root,profile);cohort=profile['cohort']
    path=shared.regular(root,MANIFEST);raw=path.read_bytes();manifest=json.loads(raw)
    target=shared.regular(root,RECEIPT);old=target.read_bytes() if target.exists() else None
    if manifest.get('am9_venom_entry_release')==RELEASE:
        if sha(raw)!=FINAL[cohort]:raise ValueError('Unreviewed entry manifest')
        if old!=receipt(cohort,sha(raw)):raise ValueError('Entry receipt drift')
        expected={path:raw,target:old,**identity}
        for name,digest in manifest['files'].items():
            source=shared.regular(root,'.kodi/'+name);data=source.read_bytes()
            if sha(data)!=digest:raise ValueError('Entry source drift')
            expected[source]=data
        if manifest['files'].get(overlay.SKIN)!=AFTER:raise ValueError('Entry output pin drift')
        result=transaction.Plan({},expected)
    else:
        if old is not None:raise ValueError('Foreign entry receipt')
        result=previous.plan(root,profile)
        manifest=json.loads(result.get(path,raw))
        source=shared.regular(root,'.kodi/'+overlay.SKIN)
        data=result.get(source,source.read_bytes());output=overlay.transform(data)
        if sha(output)!=AFTER:raise ValueError('Entry output drift')
        result[source]=output;manifest['files'][overlay.SKIN]=sha(output)
        manifest['am9_venom_entry_release']=RELEASE
        final=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
        if sha(final)!=FINAL[cohort]:raise ValueError('Unexpected entry manifest output')
        result[path]=final;result.expected[target]=None;result[target]=receipt(cohort,sha(final))
    # Historical parent receipts are retained, not relabelled as this build.
    for parent,expected_receipt in ((previous,previous.receipt(cohort,previous.FINAL[cohort])),
                                    (previous.previous,previous.previous_receipt(cohort))):
        item=shared.regular(root,parent.RECEIPT)
        if item.exists():
            data=item.read_bytes()
            if result.get(item,data)!=expected_receipt:
                raise ValueError('Parent receipt drift')
            result.expected[item]=data
    for pattern in ('.kodi/userdata/keymaps/*.xml','.kodi/userdata/peripheral_data/*.xml',
                    '.cache/connman/*/settings','.cache/connman/*.config','.cache/regdomain.conf'):
        for protected in root.glob(pattern):
            shared.regular(root,str(protected.relative_to(root)))
            if protected.is_file():result.expected[protected]=protected.read_bytes()
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/storage'))
    parser.add_argument('--profile',type=Path,required=True);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();profile=json.loads(args.profile.read_bytes())
    if socket.gethostname()!=profile['hostname']:raise SystemExit('Wrong appliance')
    mac=Path('/sys/class/net/wlan0/address');mac_raw=mac.read_bytes()
    if mac_raw.decode().strip().lower()!=profile['wlan_mac'].lower():raise SystemExit('Wrong hardware')
    changes=plan(args.root,profile);changes.expected[mac]=mac_raw
    print(json.dumps({'release':RELEASE,'cohort':profile['cohort'],'mode':'apply' if args.apply else 'plan-only',
        'changes':[str(path.relative_to(args.root)) for path in changes]},indent=2))
    if args.apply and changes:
        backup=args.root/'backup'/(RELEASE+'-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
        transaction.deploy(args.root,changes,backup)
        if plan(args.root,profile):raise RuntimeError('Entry final plan not idempotent')
        print('Applied; rollback:',backup)
