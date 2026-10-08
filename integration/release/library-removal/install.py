"""Shared Jellyfin removal repair after the accepted Venom lifecycle layer."""
import argparse,hashlib,importlib.util,json,socket,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
overlay=load('removal_overlay',HERE/'overlay.py')
previous=load('removal_parent',HERE.parent/'venom-lifecycle/install.py')
shared=previous.shared;transaction=previous.transaction;MANIFEST=previous.MANIFEST
RELEASE='am9-shared-20261008.6';RECEIPT='.config/am9-library-removal-release.json'
AFTER='e58c7cb29e358feecf8a0c41838e08047c08860af9e9d7b62d3a1ff6257009eb'
FINAL={'local':'f7e917da286f8b2c781a137a3ac2bffbbececbe756d2f72b0333576a26ae4a99',
       'remote':'b085afd82f4e2a6f48a89036022044beb090900015e425c557b69ae7d560801f'}
def sha(data):return hashlib.sha256(data).hexdigest()
def receipt(cohort,digest):
    return (json.dumps({'schema':1,'release':RELEASE,'cohort':cohort,'manifest_sha256':digest,
        'acceptance':'source-installed-live-acceptance-separate'},indent=2,sort_keys=True)+'\n').encode()
def plan(root,profile):
    if root.is_symlink() or root.resolve()!=root:raise ValueError('Unsafe storage root')
    identity=shared.identity(root,profile);cohort=profile['cohort']
    path=shared.regular(root,MANIFEST);raw=path.read_bytes();manifest=json.loads(raw)
    target=shared.regular(root,RECEIPT);old=target.read_bytes() if target.exists() else None
    if manifest.get('am9_library_removal_release')==RELEASE:
        if sha(raw)!=FINAL[cohort] or old!=receipt(cohort,sha(raw)):raise ValueError('Removal manifest or receipt drift')
        expected={path:raw,target:old,**identity}
        for name,digest in manifest['files'].items():
            item=shared.regular(root,'.kodi/'+name);data=item.read_bytes()
            if sha(data)!=digest:raise ValueError('Removal source drift')
            expected[item]=data
        if manifest['files'].get(overlay.SOURCE)!=AFTER:raise ValueError('Removal output pin drift')
        result=transaction.Plan({},expected)
    else:
        if old is not None:raise ValueError('Foreign removal receipt')
        result=previous.plan(root,profile)
        manifest=json.loads(result.get(path,raw))
        source=shared.regular(root,'.kodi/'+overlay.SOURCE)
        output=overlay.transform(result.get(source,source.read_bytes()))
        if sha(output)!=AFTER:raise ValueError('Removal output drift')
        result[source]=output;manifest['files'][overlay.SOURCE]=sha(output)
        manifest['am9_library_removal_release']=RELEASE
        final=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
        if sha(final)!=FINAL[cohort]:raise ValueError('Unexpected removal manifest output')
        result[path]=final;result.expected[target]=None;result[target]=receipt(cohort,sha(final))
    parent=shared.regular(root,previous.RECEIPT)
    if parent.exists():
        data=parent.read_bytes()
        if result.get(parent,data)!=previous.receipt(cohort,previous.FINAL[cohort]):raise ValueError('Parent receipt drift')
        result.expected[parent]=data
    for pattern in ('.kodi/userdata/keymaps/*.xml','.kodi/userdata/peripheral_data/*.xml',
                    '.cache/connman/*/settings','.cache/connman/*.config','.cache/regdomain.conf'):
        for item in root.glob(pattern):
            shared.regular(root,str(item.relative_to(root)))
            if item.is_file():result.expected[item]=item.read_bytes()
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/storage'));parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--apply',action='store_true');args=parser.parse_args();profile=json.loads(args.profile.read_bytes())
    if socket.gethostname()!=profile['hostname']:raise SystemExit('Wrong appliance')
    mac=Path('/sys/class/net/wlan0/address');mac_raw=mac.read_bytes()
    if mac_raw.decode().strip().lower()!=profile['wlan_mac'].lower():raise SystemExit('Wrong hardware')
    changes=plan(args.root,profile);changes.expected[mac]=mac_raw
    print(json.dumps({'release':RELEASE,'cohort':profile['cohort'],'mode':'apply' if args.apply else 'plan-only',
        'changes':[str(p.relative_to(args.root)) for p in changes]},indent=2))
    if args.apply and changes:
        backup=args.root/'backup'/(RELEASE+'-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
        transaction.deploy(args.root,changes,backup)
        if plan(args.root,profile):raise RuntimeError('Removal final plan not idempotent')
        print('Applied; rollback:',backup)
