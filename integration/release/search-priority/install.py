"""Guarded local Kodi overlay for search priority and poster ratings."""
import argparse
import hashlib
import importlib.util
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE=Path(__file__).resolve().parent


def _load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


# Use unique module names: both this directory and ../kodi contain build.py or
# install.py, and sys.path ordering must never select the wrong release cohort.
sys.path.insert(0,str(HERE.parent/'kodi'))
transaction=_load('search_priority_transaction',HERE.parent/'kodi/transaction.py')
sys.modules['transaction']=transaction  # dependency of kodi install
kodi_release=_load('search_priority_kodi_release',HERE.parent/'kodi/install.py')
build=_load('search_priority_build',HERE/'build.py')
generated=_load('search_priority_generated',HERE/'generated.py')

VERSIONS={'plugin.video.habibi.resume':'1.1.0','plugin.video.jellyfin':'2.2.0+py3',
          'skin.arctic.fuse.3':'3.3.1','plugin.video.venom.tv':'1.3.1'}
TARGETS={
 'home/client.py':'addons/plugin.video.habibi.resume/client.py',
 'home/default.py':'addons/plugin.video.habibi.resume/default.py',
 'skin/search_selector.xml':'addons/skin.arctic.fuse.3/shortcuts/generator/data/base/search_selector.xml',
 'skin/search_selector_venom.xml':'addons/skin.arctic.fuse.3/shortcuts/generator/data/base/search_selector_venom.xml',
 'skin/search_selector_wall.xml':'addons/skin.arctic.fuse.3/shortcuts/generator/data/base/search_selector_wall.xml',
 'skin/search_selector_wall_venom.xml':'addons/skin.arctic.fuse.3/shortcuts/generator/data/base/search_selector_wall_venom.xml',
 'skin/skinvariables-generator.json':'addons/skin.arctic.fuse.3/shortcuts/skinvariables-generator.json',
}
SEARCH='addons/skin.arctic.fuse.3/1080i/Includes_Search.xml'
GENERATED='addons/skin.arctic.fuse.3/1080i/script-skinvariables-generator-includes-.xml'
LABELS='addons/skin.arctic.fuse.3/1080i/Includes_Labels.xml'
OBJECTS='addons/skin.arctic.fuse.3/1080i/Includes_Objects.xml'
LAYOUTS='addons/skin.arctic.fuse.3/1080i/Includes_Layouts.xml'
BASE_HASHES={
 TARGETS['home/client.py']:'ea2ebdec9f096df0ed9c1512ab9abb4d4661d90e72c3c5d8f80899330d2ceba4',
 TARGETS['home/default.py']:'446dcf19357f7e095ca8729fa44e6ef8604b9fc4ec2bc4a7119f892d7aca2b99',
 TARGETS['skin/search_selector.xml']:'5df193895fcc311c2698ebff7eedbe6c62ce52b716e66448545ae76c397bd6b5',
 TARGETS['skin/search_selector_wall.xml']:'bb31aeacf46aa6803785e2793ca48eaad2f52ad45a0ec9587230452486965796',
 TARGETS['skin/skinvariables-generator.json']:'127847d0afa37f6f0624d94c9369c722a2ea0cc84ffdde4e48e6e2db7cf4ab08',
 SEARCH:'77fb1c5e96945b4f9ac25a968f9a8db76928c249eb62776d8c6e3f2e934c5bfe',
 GENERATED:'002abbb3fd60212c7b81bdd8228a58855c9305a0e0b7498f0edd83eabced1e6a',
 LABELS:'400839c81f8c176783e7dfbc7d0ce0412eaf0486caa15ab1c4c21822cf433dbb',
 OBJECTS:'5d32984c498336eb238da12c410c4fef6122967eb6058e2a2daa425d60c317ab',
 LAYOUTS:'b09595f1c7a76f7e2bc9800ec81adc7181b3145c9eac620790a9008135c3ff8e',
}
BASE_MANIFEST_HASH='a121f12b16028fb79e44258f7395ea88c937a3e5fcfc3183e6fffab8db180300'
OUTPUT_TRANSFORMS={
 SEARCH:('4a2d97a40009ed74fb49852723bb1ca13242cb222b006887ff103dd838aa49d5',generated.transform_search),
 GENERATED:('01e96f52d53ffd7b57088b0a52136fbeca50bdbba367bb1698b2ba4f8697fa0f',generated.transform_generated),
 LABELS:('3709fe666115bfbb47baa75deafe202b7e92eeb725cfb5ce28772dc331f48206',generated.transform_labels),
 OBJECTS:('15d224e74f8fbcba188f25051ef5922581b09e79ff263cd8ebbbc2b727e44fd2',generated.transform_objects),
 LAYOUTS:('80e41db0843dd82c75c8e5faf186ae79cd4453a243685d0f695c7be5966e6cb9',generated.transform_layouts),
}


def sha(data):return hashlib.sha256(data).hexdigest()


def payloads(stage):
    result={}
    for name,digest in build.OUTPUTS.items():
        data=(stage/name).read_bytes()
        transaction.require(sha(data)==digest,'Unreviewed payload: '+name)
        if name.endswith('.py'):compile(data,name,'exec')
        elif name.endswith('.xml'):ET.fromstring(data)
        else:json.loads(data)
        result[name]=data
    return result


def build_changes(root,stage,profile):
    transaction.require(profile['variant']=='local','This exact source cohort is local only')
    expected={}
    def read(path):
        if path not in expected:expected[path]=path.read_bytes() if path.exists() else None
        return expected[path]
    manifest=root/'addons/plugin.video.habibi.resume/verified-build.json'
    manifest_source=read(manifest)
    transaction.require(manifest_source is not None,'Required live integrity manifest is absent')
    record=json.loads(manifest_source)
    for name,version in VERSIONS.items():
        addon=ET.fromstring(read(root/'addons'/name/'addon.xml'))
        transaction.require(addon.get('id')==name and addon.get('version')==version,
                            'Unreviewed addon version: '+name)
        transaction.require(record.get('versions',{}).get(name)==version,
                            'Manifest version mismatch: '+name)
    bundle=payloads(stage)
    paths=set(BASE_HASHES)|{TARGETS['skin/search_selector_venom.xml'],
                            TARGETS['skin/search_selector_wall_venom.xml']}
    current={relative:(sha(read(root/relative)) if read(root/relative) is not None else None)
             for relative in paths}
    output={TARGETS[name]:digest for name,digest in build.OUTPUTS.items()}
    output.update({name:value[0] for name,value in OUTPUT_TRANSFORMS.items()})
    baseline=all(current.get(name)==digest for name,digest in BASE_HASHES.items()) and all(
        current.get(name) is None for name in paths-set(BASE_HASHES))
    installed=all(current.get(name)==digest for name,digest in output.items())
    transaction.require(baseline or installed,'Unreviewed or partial search/rating cohort')
    if baseline:
        transaction.require(sha(manifest_source)==BASE_MANIFEST_HASH,
                            'Baseline integrity manifest is not the reviewed R7 snapshot')
        for relative in (TARGETS['home/client.py'],TARGETS['home/default.py'],SEARCH,GENERATED):
            transaction.require(record['files'].get(relative)==BASE_HASHES[relative],
                                'Baseline source/manifest drift: '+relative)
    else:
        for relative,digest in output.items():
            transaction.require(record['files'].get(relative)==digest,
                                'Installed source/manifest drift: '+relative)
    changes={root/TARGETS[name]:data for name,data in bundle.items()}
    if baseline:
        for relative,(digest,fn) in OUTPUT_TRANSFORMS.items():
            data=fn(read(root/relative))
            transaction.require(sha(data)==digest,'Unexpected transformed output: '+relative)
            changes[root/relative]=data
    else:
        for relative in OUTPUT_TRANSFORMS:changes[root/relative]=read(root/relative)
    for path,data in changes.items():record['files'][str(path.relative_to(root))]=sha(data)
    changes[manifest]=(json.dumps(record,indent=2)+'\n').encode()
    return transaction.Plan({path:data for path,data in changes.items() if read(path)!=data},expected)


def live_plan(root,stage,profile,hostname_path,mac_path):
    account=root/'userdata/addon_data/plugin.video.jellyfin/data.json'
    identity={path:path.read_bytes() for path in (hostname_path,mac_path,account)}
    servers=json.loads(identity[account])['Servers']
    transaction.require(identity[hostname_path].decode().strip() in profile['hostnames'],
                        'Hostname not allowed by private profile')
    transaction.require(identity[mac_path].decode().strip().lower()==profile['mac'].lower(),
                        'Hardware identity mismatch')
    transaction.require(servers and servers[0].get('UserId')==profile['jellyfin_user_id'],
                        'Jellyfin identity mismatch')
    plan=build_changes(root,stage,profile)
    for path,data in identity.items():plan.expected[path]=data
    return plan


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--profile',required=True);parser.add_argument('--payload',required=True)
    parser.add_argument('--apply',action='store_true');parser.add_argument('--allow-active-playback',action='store_true')
    args=parser.parse_args();profile=kodi_release.load_profile(args.profile);root=Path('/storage/.kodi')
    plan=live_plan(root,Path(args.payload),profile,Path('/storage/.cache/hostname'),Path('/sys/class/net/wlan0/address'))
    if not args.apply:
        print('PLAN_ONLY',len(plan),'replacement(s)')
        for path in sorted(plan,key=str):print(path.relative_to(root))
        print('No files changed; rerun with --apply after review.');return
    idle=(lambda:None) if args.allow_active_playback else transaction.idle
    if args.allow_active_playback:print('WARNING: explicit override will stop active or paused Kodi playback.')
    backup=Path('/storage/upgrade-staging')/('search-priority-before-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
    if transaction.deploy(root,plan,backup,idle_check=idle):print('Applied reviewed search/rating overlay; rollback:',backup)
    else:print('Reviewed search/rating overlay already installed; Kodi not restarted')


if __name__=='__main__':main()
