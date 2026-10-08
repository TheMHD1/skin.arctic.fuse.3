"""Paired short-sync-transaction repair after collection removal dispatch."""
import argparse,hashlib,importlib.util,json,socket,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
overlay=load('transaction_overlay',HERE/'overlay.py')
previous=load('transaction_parent',HERE.parent/'library-removal/install.py')
shared=previous.shared;transaction=previous.transaction;MANIFEST=previous.MANIFEST
RELEASE='am9-shared-20261008.7';RECEIPT='.config/am9-library-transactions-release.json'
AFTER={overlay.LIBRARY:'c8990746c887f3889b0b8bc4288079446143ecef85455fa5bb5cf4ccaef258ab',
       overlay.MOVIES:'586ce652ee08b334a176f7e1f9fdfe2f575c2329f5c9d40b2dd8cff999612a92'}
FINAL={'local':'017158ff49a9ebeb8ca0079a1fa50d68ee30225c30ad9759bb84fafd793cf60c',
       'remote':'32465a8959dc4bd3e2e97c4f19a57ee21f88dee164cfd595a56585622701230f'}
def sha(data):return hashlib.sha256(data).hexdigest()
def receipt(cohort,digest):
    return (json.dumps({'schema':1,'release':RELEASE,'cohort':cohort,'manifest_sha256':digest,
        'acceptance':'source-installed-live-acceptance-separate'},indent=2,sort_keys=True)+'\n').encode()
def plan(root,profile):
    if root.is_symlink() or root.resolve()!=root:raise ValueError('Unsafe storage root')
    identity=shared.identity(root,profile);cohort=profile['cohort']
    path=shared.regular(root,MANIFEST);raw=path.read_bytes();manifest=json.loads(raw)
    target=shared.regular(root,RECEIPT);old=target.read_bytes() if target.exists() else None
    if manifest.get('am9_library_transactions_release')==RELEASE:
        if sha(raw)!=FINAL[cohort] or old!=receipt(cohort,sha(raw)):raise ValueError('Transaction manifest or receipt drift')
        expected={path:raw,target:old,**identity}
        for name,digest in manifest['files'].items():
            item=shared.regular(root,'.kodi/'+name);data=item.read_bytes()
            if sha(data)!=digest:raise ValueError('Transaction source drift')
            expected[item]=data
        if any(manifest['files'].get(name)!=digest for name,digest in AFTER.items()):raise ValueError('Transaction output pin drift')
        result=transaction.Plan({},expected)
    else:
        if old is not None:raise ValueError('Foreign transaction receipt')
        result=previous.plan(root,profile);manifest=json.loads(result.get(path,raw))
        for name in overlay.BEFORE:
            source=shared.regular(root,'.kodi/'+name);original=source.read_bytes()
            output=overlay.transform(name,result.get(source,original))
            if sha(output)!=AFTER[name]:raise ValueError('Transaction output drift')
            result.expected.setdefault(source,original);result[source]=output;manifest['files'][name]=sha(output)
        manifest['am9_library_transactions_release']=RELEASE
        final=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
        if sha(final)!=FINAL[cohort]:raise ValueError('Unexpected transaction manifest output')
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
        if plan(args.root,profile):raise RuntimeError('Transaction final plan not idempotent')
        print('Applied; rollback:',backup)
