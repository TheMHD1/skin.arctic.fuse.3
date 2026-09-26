"""Guarded local Kodi overlay for search priority and poster ratings."""
import argparse
import hashlib
import ipaddress
import importlib.util
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

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
# Remote HTTPS R7 is an independently pinned continuation of the remote R6
# Home cohort.  It intentionally keeps the remote marker and add-on playback
# policy; these source hashes do not authorize a local/NFS profile.
REMOTE_BASE_HASHES={
 **BASE_HASHES,
 GENERATED:'573e388dead0fcfc2dceae9c184bd60e8802fa94f8059a5d18e4a0076688b692',
}
REMOTE_BASE_MANIFEST_HASH='fdc083bd7c3dcfe87195fff9cbde4354cdca6c2379f774c1fa7fd89274afb61b'
REMOTE_MARKER='4d3f886ca60726528b56a11e2271605a146d04d29c7fa63add90891011bc240b'
# Skin Variables rewrites indentation after Kodi startup. This one exact byte
# variant was compared recursively with the reviewed generated output: tags,
# attributes, nonblank text, child order, IDs, routes and GUIDs are identical.
REBUILT_GENERATED_HASH='619174a0e7dd6aebce7c1e13059a04950266b43ca46b22169bc57680af79f745'
OUTPUT_TRANSFORMS={
 SEARCH:('4a2d97a40009ed74fb49852723bb1ca13242cb222b006887ff103dd838aa49d5',generated.transform_search),
 GENERATED:('01e96f52d53ffd7b57088b0a52136fbeca50bdbba367bb1698b2ba4f8697fa0f',generated.transform_generated),
 LABELS:('3709fe666115bfbb47baa75deafe202b7e92eeb725cfb5ce28772dc331f48206',generated.transform_labels),
 OBJECTS:('8c214f38a01d2c0dfcba797b543c0437f1ea292385b42706002fcb2155071846',generated.transform_objects),
 LAYOUTS:('80e41db0843dd82c75c8e5faf186ae79cd4453a243685d0f695c7be5966e6cb9',generated.transform_layouts),
}
OLD_OBJECTS_OUTPUT='15d224e74f8fbcba188f25051ef5922581b09e79ff263cd8ebbbc2b727e44fd2'
# Both cohorts have the R6 search-first static selector before this step.
# Keep the remote transform map explicit for future independently reviewed ports.
REMOTE_OUTPUT_TRANSFORMS={
 **OUTPUT_TRANSFORMS,
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


def require_remote_transport(root, read, expected_host):
    settings={entry.get('id'):(entry.text or '').strip()
              for entry in ET.fromstring(read(root/'userdata/addon_data/plugin.video.jellyfin/settings.xml')).findall('setting')
              if entry.get('id')}
    transaction.require(settings.get('playFromStream')=='true'
                        and settings.get('playFromTranscode')=='false'
                        and settings.get('useDirectPaths')=='0'
                        and settings.get('sslverify')=='true',
                        'Remote profile must remain HTTPS add-on playback')
    servers=json.loads(read(root/'userdata/addon_data/plugin.video.jellyfin/data.json')).get('Servers') or []
    transaction.require(len(servers)==1 and isinstance(servers[0],dict),
                        'Remote Jellyfin server identity is invalid')
    server=servers[0]
    transaction.require(server.get('paths') in (None,{}),'Remote profile cannot carry native paths')
    parsed=urlparse(server.get('address') or '')
    transaction.require(parsed.scheme=='https' and parsed.hostname==expected_host
                        and not parsed.username and not parsed.password
                        and not parsed.query and not parsed.fragment and parsed.path in ('','/'),
                        'Remote profile requires its approved HTTPS Jellyfin address')
    try:address=ipaddress.ip_address(parsed.hostname)
    except ValueError:return
    transaction.require(not (address.is_private or address.is_loopback or address.is_link_local),
                        'Remote profile cannot use a private Jellyfin address')


def build_changes(root,stage,profile):
    remote=profile['variant']=='remote'
    transaction.require(profile['variant'] in ('local','remote'),'Unknown source cohort')
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
    marker=root/'userdata/addon_data/plugin.video.venom.tv/remote-native.json'
    if remote:
        transaction.require(read(marker) is not None and sha(read(marker))==REMOTE_MARKER,
                            'Remote marker differs from the reviewed HTTPS cohort')
        require_remote_transport(root,read,profile.get('remote_public_host'))
    else:
        transaction.require(read(marker) is None,'Local profile unexpectedly has the remote marker')
    base_hashes=REMOTE_BASE_HASHES if remote else BASE_HASHES
    base_manifest_hash=REMOTE_BASE_MANIFEST_HASH if remote else BASE_MANIFEST_HASH
    output_transforms=REMOTE_OUTPUT_TRANSFORMS if remote else OUTPUT_TRANSFORMS
    bundle=payloads(stage)
    paths=set(base_hashes)|{TARGETS['skin/search_selector_venom.xml'],
                            TARGETS['skin/search_selector_wall_venom.xml']}
    current={relative:(sha(read(root/relative)) if read(root/relative) is not None else None)
             for relative in paths}
    output={TARGETS[name]:digest for name,digest in build.OUTPUTS.items()}
    output.update({name:value[0] for name,value in output_transforms.items()})
    baseline=all(current.get(name)==digest for name,digest in base_hashes.items()) and all(
        current.get(name) is None for name in paths-set(base_hashes))
    installed=all(current.get(name)==digest or
                  (name==OBJECTS and current.get(name)==OLD_OBJECTS_OUTPUT) or
                  (name==GENERATED and current.get(name)==REBUILT_GENERATED_HASH)
                  for name,digest in output.items())
    transaction.require(baseline or installed,'Unreviewed or partial search/rating cohort')
    if baseline:
        transaction.require(sha(manifest_source)==base_manifest_hash,
                            'Baseline integrity manifest is not the reviewed R7 snapshot')
        for relative in (TARGETS['home/client.py'],TARGETS['home/default.py'],SEARCH,GENERATED):
            # The historical remote R6 manifest did not own its static search
            # include.  Its exact current bytes remain a required guard here;
            # the R7 transaction adds only the files it actually replaces.
            expected_record={base_hashes[relative]}
            if remote and relative==SEARCH:
                expected_record.add(None)
            transaction.require(record['files'].get(relative) in expected_record,
                                'Baseline source/manifest drift: '+relative)
    else:
        for relative,digest in output.items():
            accepted={digest}
            if relative==OBJECTS and current.get(relative)==OLD_OBJECTS_OUTPUT:
                accepted.add(OLD_OBJECTS_OUTPUT)
            if relative==GENERATED and current.get(relative)==REBUILT_GENERATED_HASH:
                accepted.add(REBUILT_GENERATED_HASH)
            transaction.require(record['files'].get(relative) in accepted,
                                'Installed source/manifest drift: '+relative)
    changes={root/TARGETS[name]:data for name,data in bundle.items()}
    if baseline:
        for relative,(digest,fn) in output_transforms.items():
            data=fn(read(root/relative))
            transaction.require(sha(data)==digest,'Unexpected transformed output: '+relative)
            changes[root/relative]=data
    else:
        for relative in output_transforms:
            if relative==OBJECTS and current.get(relative)==OLD_OBJECTS_OUTPUT:
                repaired=generated.upgrade_objects(read(root/relative))
                transaction.require(sha(repaired)==output[OBJECTS],
                                    'Unexpected repaired poster indicator output')
                changes[root/relative]=repaired
            else:
                changes[root/relative]=read(root/relative)
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
