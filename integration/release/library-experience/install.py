"""Guarded exact-cohort installer for Home freshness and separated search."""
import argparse
import hashlib
import ipaddress
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent/'kodi'))
import install as kodi_release
import transaction
from generated import transform as transform_generated, transform_nodes

VERSIONS = {'plugin.video.habibi.resume':'1.1.0',
            'plugin.video.jellyfin':'2.2.0+py3',
            'skin.arctic.fuse.3':'3.3.1',
            'plugin.video.venom.tv':'1.3.1'}
TARGETS = {
    'home/client.py':'addons/plugin.video.habibi.resume/client.py',
    'home/search.py':'addons/plugin.video.habibi.resume/search.py',
    'home/default.py':'addons/plugin.video.habibi.resume/default.py',
    'home/service.py':'addons/plugin.video.habibi.resume/service.py',
    'skin/search_path.xml':'addons/skin.arctic.fuse.3/shortcuts/generator/data/setup/search_path.xml',
    'skin/searchwidgets.json':'addons/skin.arctic.fuse.3/shortcuts/skinvariables-shortcut-searchwidgets.json',
}
PAYLOAD_HASHES = {
    'home/client.py':'ea2ebdec9f096df0ed9c1512ab9abb4d4661d90e72c3c5d8f80899330d2ceba4',
    'home/search.py':'0b04d08e0c38066b0b4cb4d5dc52b39d6626816b69991304c6d5f59128eac3f8',
    'home/default.py':'446dcf19357f7e095ca8729fa44e6ef8604b9fc4ec2bc4a7119f892d7aca2b99',
    'home/service.py':'4bd56224430ac38c9fe9a7d5aeb6123974070174403eaa6f34da1c95b21e6ffd',
    'skin/search_path.xml':'ad2c2018bb9e80b839343d975f4b939713771853b815a828845ae8e8a394007f',
    'skin/searchwidgets.json':'f718340a491415980f2344246ae49077e42493e663240bb5729257a325cf8e20',
}
BASE_HASHES = {
    'addons/plugin.video.habibi.resume/client.py':'1aaf8ec5a327f6f09c10a842de36c9eabfd2d4378b54d83fe1598b481aad31cd',
    'addons/plugin.video.habibi.resume/search.py':'74a5b1dcb21b36ca3004179b81cf3d2f4e7894025bba85fe8a941c68d8033ee8',
    'addons/plugin.video.habibi.resume/default.py':'4a281b6036b25e927d34e1d2f500fc6bfcd092d7eeb87a77dc6d1fc355d5c810',
    'addons/plugin.video.habibi.resume/service.py':'62664f772afabcd20e26e37b17d59ca41a2f4501a9be304a685066d2b606e1d9',
    'addons/skin.arctic.fuse.3/shortcuts/generator/data/setup/search_path.xml':'d819c566ae13c982f201f2d702fc9c755672c42778e220a227be750bd173ef48',
    'addons/skin.arctic.fuse.3/shortcuts/skinvariables-shortcut-searchwidgets.json':'0b6fc7f603096e8e29319bd47f1140d2210fea81f189490b8d8f12b5a0ee6edf',
    'addons/skin.arctic.fuse.3/1080i/script-skinvariables-generator-includes-.xml':'0e8eb078d931702f96fcc751d361539fcc57ffa1ac4a69050b29ef9cf327c745',
    'userdata/addon_data/script.skinvariables/nodes/skin.arctic.fuse.3/skinvariables-shortcut-searchwidgets.json':'3e42b1e1f3c6ff8ee816f9df8b9d43c1e29e7e81b4f1fbd16e9c739a02640ec7',
}
# The remote R6 starting point is intentionally separate from the local
# LAN/native R6 cohort. Its search helper is installed by the R6 bridge, while
# its generated include has not yet been rebuilt. These source guards are not a substitute
# for the private hostname/MAC/Jellyfin-account profile checked by live_plan.
REMOTE_BASE_HASHES = {
    'addons/plugin.video.habibi.resume/client.py':'1aaf8ec5a327f6f09c10a842de36c9eabfd2d4378b54d83fe1598b481aad31cd',
    'addons/plugin.video.habibi.resume/search.py':'74a5b1dcb21b36ca3004179b81cf3d2f4e7894025bba85fe8a941c68d8033ee8',
    'addons/plugin.video.habibi.resume/default.py':'4a281b6036b25e927d34e1d2f500fc6bfcd092d7eeb87a77dc6d1fc355d5c810',
    'addons/plugin.video.habibi.resume/service.py':'62664f772afabcd20e26e37b17d59ca41a2f4501a9be304a685066d2b606e1d9',
    'addons/skin.arctic.fuse.3/shortcuts/generator/data/setup/search_path.xml':'d819c566ae13c982f201f2d702fc9c755672c42778e220a227be750bd173ef48',
    'addons/skin.arctic.fuse.3/shortcuts/skinvariables-shortcut-searchwidgets.json':'0b6fc7f603096e8e29319bd47f1140d2210fea81f189490b8d8f12b5a0ee6edf',
    'addons/skin.arctic.fuse.3/1080i/script-skinvariables-generator-includes-.xml':'5935f5696f19c09f9cba1511c0db61f506d1bba3108773be531719de3895dcf8',
    'userdata/addon_data/script.skinvariables/nodes/skin.arctic.fuse.3/skinvariables-shortcut-searchwidgets.json':'3e42b1e1f3c6ff8ee816f9df8b9d43c1e29e7e81b4f1fbd16e9c739a02640ec7',
}
REMOTE_MARKER = '4d3f886ca60726528b56a11e2271605a146d04d29c7fa63add90891011bc240b'
GENERATED = 'addons/skin.arctic.fuse.3/1080i/script-skinvariables-generator-includes-.xml'
GENERATED_HASH = '573e388dead0fcfc2dceae9c184bd60e8802fa94f8059a5d18e4a0076688b692'
# The real generator rewrites indentation after startup. Verified identical
# element/attribute/order/nonblank-text content, not an arbitrary drift bypass.
REBUILT_GENERATED_HASH = '002abbb3fd60212c7b81bdd8228a58855c9305a0e0b7498f0edd83eabced1e6a'
NODES = 'userdata/addon_data/script.skinvariables/nodes/skin.arctic.fuse.3/skinvariables-shortcut-searchwidgets.json'
NODES_HASH = 'e139923bbbbc7af44a609662544298327c8c93efda30d6035e09ac9f459c6f62'
BASE_MANIFEST_HASH = 'ebd17d7779c4c50d46fa1009de0d92b38213af14093a1aef2a2ef221788f974a'
REMOTE_BASE_MANIFEST_HASH = 'aef34b0db83b4a5c5f1c30b4fab1a59bbd4b017aef17d9cf09338287cc3ed266'
PREVIOUS_SEARCH_HASH = 'df5da027592a8c8aa9ab3be5c564e9b7ecb15c0c01d2b938c18890e4f95b168a'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(value, message):
    transaction.require(value, message)


def payloads(stage):
    result = {}
    for name, digest in PAYLOAD_HASHES.items():
        data = (stage/name).read_bytes()
        require(sha(data) == digest, 'Unreviewed payload: '+name)
        if name.endswith('.py'):
            compile(data, name, 'exec')
        elif name.endswith('.xml'):
            ET.fromstring(data)
        else:
            require(isinstance(json.loads(data), list), 'Invalid search widget payload')
        result[name] = data
    return result


def require_remote_transport(root, read, expected_host):
    """Reject local-path or non-public transport drift before remote updates."""
    settings = {entry.get('id'):(entry.text or '').strip()
                for entry in ET.fromstring(read(root/'userdata/addon_data/plugin.video.jellyfin/settings.xml')).findall('setting')
                if entry.get('id')}
    require(settings.get('playFromStream') == 'true'
            and settings.get('playFromTranscode') == 'false'
            and settings.get('useDirectPaths') == '0'
            and settings.get('sslverify') == 'true',
            'Remote profile must remain HTTPS add-on playback')
    servers = json.loads(read(root/'userdata/addon_data/plugin.video.jellyfin/data.json')).get('Servers') or []
    require(len(servers) == 1 and isinstance(servers[0], dict), 'Remote Jellyfin server identity is invalid')
    server = servers[0]
    require(server.get('paths') in (None, {}), 'Remote profile cannot carry native paths')
    parsed = urlparse(server.get('address') or '')
    require(parsed.scheme == 'https' and parsed.hostname == expected_host
            and not parsed.username and not parsed.password
            and not parsed.query and not parsed.fragment and parsed.path in ('', '/'),
            'Remote profile requires its approved HTTPS Jellyfin address')
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return
    require(not (address.is_private or address.is_loopback or address.is_link_local),
            'Remote profile cannot use a private Jellyfin address')


def build_changes(root, stage, profile):
    remote = profile['variant'] == 'remote'
    require(profile['variant'] in ('local', 'remote'), 'Unknown source cohort')
    expected = {}
    def read(path):
        if path not in expected:
            expected[path] = path.read_bytes() if path.exists() else None
        return expected[path]

    manifest = root/'addons/plugin.video.habibi.resume/verified-build.json'
    manifest_source = read(manifest)
    require(manifest_source is not None, 'Required live integrity manifest is absent')
    record = json.loads(manifest_source)
    require(isinstance(record.get('files'), dict) and isinstance(record.get('versions'), dict),
            'Bad integrity manifest')
    for name, version in VERSIONS.items():
        addon_path = root/'addons'/name/'addon.xml'
        addon = ET.fromstring(read(addon_path))
        require(addon.get('id') == name and addon.get('version') == version,
                'Unreviewed addon version: '+name)
        require(record['versions'].get(name) == version,
                'Manifest version mismatch: '+name)

    marker = root/'userdata/addon_data/plugin.video.venom.tv/remote-native.json'
    if remote:
        require(read(marker) is not None and sha(read(marker)) == REMOTE_MARKER,
                'Remote marker differs from the reviewed HTTPS cohort')
        require_remote_transport(root, read, profile.get('remote_public_host'))
    else:
        require(read(marker) is None, 'Local profile unexpectedly has the remote marker')
    base_hashes = REMOTE_BASE_HASHES if remote else BASE_HASHES
    base_manifest_hash = REMOTE_BASE_MANIFEST_HASH if remote else BASE_MANIFEST_HASH
    bundle = payloads(stage)
    current = {relative:(sha(read(root/relative)) if read(root/relative) is not None else None)
               for relative in base_hashes}
    output_hashes = {TARGETS[name]:digest for name,digest in PAYLOAD_HASHES.items()}
    output_hashes[GENERATED] = GENERATED_HASH
    if current[GENERATED] == REBUILT_GENERATED_HASH:
        output_hashes[GENERATED] = REBUILT_GENERATED_HASH
    output_hashes[NODES] = NODES_HASH
    baseline = current == base_hashes
    installed = current == output_hashes
    previous_hashes = dict(output_hashes)
    previous_hashes[TARGETS['home/search.py']] = PREVIOUS_SEARCH_HASH
    previous = not remote and current == previous_hashes
    require(baseline or installed or previous, 'Unreviewed or partial Home/search source cohort')
    if baseline:
        require(sha(manifest_source) == base_manifest_hash,
                'Baseline integrity manifest is not the reviewed snapshot')
        for relative in TARGETS.values():
            if base_hashes[relative] is None:
                require(relative not in record['files'],
                        'Absent baseline source has an active manifest hash: '+relative)
            elif relative in record['files']:
                require(record['files'][relative] == base_hashes[relative],
                        'Baseline source/manifest drift: '+relative)
        generated = transform_generated(read(root/GENERATED))
        require(sha(generated) == GENERATED_HASH, 'Unexpected generated search output')
        nodes = transform_nodes(read(root/NODES))
        require(sha(nodes) == NODES_HASH, 'Unexpected search widget node output')
    else:
        for relative, digest in current.items():
            accepted = {digest}
            if relative == GENERATED and digest == REBUILT_GENERATED_HASH:
                accepted.add(GENERATED_HASH)
            require(record['files'].get(relative) in accepted,
                    'Installed source/manifest drift: '+relative)
        generated = read(root/GENERATED)
        nodes = read(root/NODES)

    changes = {root/TARGETS[name]:data for name,data in bundle.items()}
    changes[root/GENERATED] = generated
    changes[root/NODES] = nodes
    for path, data in changes.items():
        record['files'][str(path.relative_to(root))] = sha(data)
    updated_manifest = (json.dumps(record, indent=2)+'\n').encode()
    changes[manifest] = updated_manifest
    return transaction.Plan({path:data for path,data in changes.items() if read(path) != data}, expected)


def live_plan(root, stage, profile, hostname_path, mac_path):
    account = root/'userdata/addon_data/plugin.video.jellyfin/data.json'
    identity = {path:path.read_bytes() for path in (hostname_path, mac_path, account)}
    hostname = identity[hostname_path].decode().strip()
    mac = identity[mac_path].decode().strip().lower()
    servers = json.loads(identity[account])['Servers']
    require(hostname in profile['hostnames'], 'Hostname not allowed by private profile')
    require(mac == profile['mac'].lower(), 'Hardware identity mismatch')
    require(servers and servers[0].get('UserId') == profile['jellyfin_user_id'],
            'Jellyfin identity mismatch')
    plan = build_changes(root, stage, profile)
    for path, data in identity.items():
        require(path not in plan.expected or plan.expected[path] == data,
                'Identity changed during planning')
        plan.expected[path] = data
    return plan


def selected_idle_check(allow_active_playback, notify=print):
    if allow_active_playback:
        notify('WARNING: explicit override will stop active or paused Kodi playback.')
        return lambda: None
    return transaction.idle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', required=True)
    parser.add_argument('--payload', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--allow-active-playback', action='store_true',
                        help='explicitly authorize stopping active/paused Kodi playback')
    args = parser.parse_args()
    profile = kodi_release.load_profile(args.profile)
    root = Path('/storage/.kodi')
    plan = live_plan(root, Path(args.payload), profile,
                     Path('/storage/.cache/hostname'), Path('/sys/class/net/wlan0/address'))
    if not args.apply:
        print('PLAN_ONLY', len(plan), 'replacement(s)')
        for path in sorted(plan, key=lambda value:str(value)):
            print(path.relative_to(root))
        print('No files changed; rerun with --apply after review.')
        return
    idle_check = selected_idle_check(args.allow_active_playback)
    backup = Path('/storage/upgrade-staging')/(
        'library-experience-before-'+time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    if transaction.deploy(root, plan, backup, idle_check=idle_check):
        print('Applied reviewed Home/search cohort; rollback:', backup)
    else:
        print('Reviewed Home/search cohort already installed; Kodi not restarted')


if __name__ == '__main__':
    main()
