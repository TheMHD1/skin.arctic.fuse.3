"""Paired exact-cohort Home teardown repair after the Venom-entry release."""
import argparse,hashlib,importlib.util,json,socket,time
from pathlib import Path

HERE=Path(__file__).resolve().parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
overlay=load('venom_lifecycle_overlay',HERE/'overlay.py')
previous=load('venom_lifecycle_parent',HERE.parent/'venom-entry/install.py')
shared=previous.shared
transaction=previous.transaction
MANIFEST=previous.MANIFEST
RELEASE='am9-shared-20261008.5'
RECEIPT='.config/am9-venom-lifecycle-release.json'
AFTER={'local':'3e3b416391019b422eefaf170ee185af6c794ce6222da4d309fe57370dcb3f3e',
       'remote':'b471cc51cb9e45a0e19ba1b6b440b42990f7b5ee4ccc0ab5797099792f0d60ed'}
FINAL={'local':'0e575a1c026a288ec5c3002748b507116f462a5481a52339d55fc6b9b9bfece1',
       'remote':'5e401cebbaea1d63e8971762f1ddc0010c16d6ccf5065c4fbe687401a8a7e0a1'}
HUB_AFTER='89633f38b93bb68d91800f950f0cce3a1b705f079e30c9471aef8f151cee76e2'
INTERIMS={'4e27085acab258dd85f746742c144030480d755351b2be68bad4f7fbd932caf3':
              'c739a86b41ce3912a156c37d8e18952e968740b89e031418c897aacf93d79d2d',
          '9781b9d1fe0097f25d7c5f744b901d496d71a39692fcb39c1fecd2ba7a32c15a':
              'c9601e4530202db453bb3a741b328812084bd678e01afcd9be2919da0e263549'}
def sha(data):return hashlib.sha256(data).hexdigest()
def receipt(cohort,digest):
    return (json.dumps({'schema':1,'release':RELEASE,'cohort':cohort,'manifest_sha256':digest,
        'acceptance':'source-installed-live-acceptance-separate'},indent=2,sort_keys=True)+'\n').encode()

def plan(root,profile):
    if root.is_symlink() or root.resolve()!=root:raise ValueError('Unsafe storage root')
    identity=shared.identity(root,profile);cohort=profile['cohort']
    path=shared.regular(root,MANIFEST);raw=path.read_bytes();manifest=json.loads(raw)
    target=shared.regular(root,RECEIPT);old=target.read_bytes() if target.exists() else None
    if cohort=='remote' and sha(raw) in INTERIMS and sha(raw)!=FINAL[cohort]:
        # The first device candidate passed source tests but failed repeated
        # actual Home entry. Migrate only its complete reviewed manifest,
        # receipt and exact browser; no drift/identity guard is bypassed.
        if old!=receipt(cohort,sha(raw)):raise ValueError('Interim receipt drift')
        expected={path:raw,target:old,**identity}
        for name,digest in manifest['files'].items():
            item=shared.regular(root,'.kodi/'+name);data=item.read_bytes()
            if sha(data)!=digest:raise ValueError('Interim source drift')
            expected[item]=data
        source=shared.regular(root,'.kodi/'+overlay.BROWSER);data=source.read_bytes()
        if sha(data)!=INTERIMS[sha(raw)]:raise ValueError('Interim browser drift')
        text=data.decode()
        if sha(data)!=AFTER[cohort]:
            if '        super().close()\n' in text:
                text=overlay.replace(text,'        super().close()\n',
                    "        # Native close navigates to the previous window. After Home has\n        # already deactivated us, calling it would resurrect old history.\n        if not xbmc.getCondVisibility('Window.IsActive(home)'):super().close()\n")
            text=overlay.replace(text,'            self.home_departure_requested=True\n','')
            text=overlay.replace(text,'    return_home=False\n','')
            text=overlay.replace(text,"            return_home=getattr(window,'home_departure_requested',False)\n",'')
            text=overlay.replace(text,"            if return_home or xbmc.getCondVisibility('Window.IsActive(1107)'):",
                "            if xbmc.getCondVisibility('Window.IsActive(1107)'):")
            text=overlay.replace(text,'        # stopping that player; remember intent after native WindowXML teardown.',
                '        # stopping that player. Cleanup must not override later navigation.')
        output=text.encode();compile(text,'interim-lifecycle','exec')
        if sha(output)!=AFTER[cohort]:raise ValueError('Interim output drift')
        manifest['files'][overlay.BROWSER]=sha(output)
        hub=shared.regular(root,'.kodi/'+overlay.HUB);hub_data=overlay.hub(hub.read_bytes())
        if sha(hub_data)!=HUB_AFTER:raise ValueError('Interim hub output drift')
        manifest['files'][overlay.HUB]=sha(hub_data)
        final=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
        if sha(final)!=FINAL[cohort]:raise ValueError('Interim final manifest drift')
        writes={hub:hub_data,path:final,target:receipt(cohort,sha(final))}
        if output!=data:writes[source]=output
        result=transaction.Plan(writes,expected)
    elif manifest.get('am9_venom_lifecycle_release')==RELEASE:
        if sha(raw)!=FINAL[cohort]:raise ValueError('Unreviewed entry manifest')
        if old!=receipt(cohort,sha(raw)):raise ValueError('Entry receipt drift')
        expected={path:raw,target:old,**identity}
        for name,digest in manifest['files'].items():
            source=shared.regular(root,'.kodi/'+name);data=source.read_bytes()
            if sha(data)!=digest:raise ValueError('Entry source drift')
            expected[source]=data
        if manifest['files'].get(overlay.BROWSER)!=AFTER[cohort]:raise ValueError('Lifecycle output pin drift')
        if manifest['files'].get(overlay.HUB)!=HUB_AFTER:raise ValueError('Hub output pin drift')
        result=transaction.Plan({},expected)
    else:
        if old is not None:raise ValueError('Foreign entry receipt')
        result=previous.plan(root,profile)
        manifest=json.loads(result.get(path,raw))
        source=shared.regular(root,'.kodi/'+overlay.BROWSER)
        data=result.get(source,source.read_bytes());output=overlay.transform(data,cohort)
        if sha(output)!=AFTER[cohort]:raise ValueError('Lifecycle output drift')
        result[source]=output;manifest['files'][overlay.BROWSER]=sha(output)
        hub=shared.regular(root,'.kodi/'+overlay.HUB)
        hub_data=overlay.hub(result.get(hub,hub.read_bytes()))
        if sha(hub_data)!=HUB_AFTER:raise ValueError('Hub output drift')
        result[hub]=hub_data;manifest['files'][overlay.HUB]=sha(hub_data)
        manifest['am9_venom_lifecycle_release']=RELEASE
        final=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
        if sha(final)!=FINAL[cohort]:raise ValueError('Unexpected entry manifest output')
        result[path]=final;result.expected[target]=None;result[target]=receipt(cohort,sha(final))
    # Historical parent receipts are retained, not relabelled as this build.
    for parent in (previous,previous.previous):
        expected_receipt=parent.receipt(cohort,parent.FINAL[cohort])
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
