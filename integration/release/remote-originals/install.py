"""Guarded additive migration: remote HTTPS cohort to gated P7 preference.

This does NOT enable global Kodi Native mode or change authenticated routes.
The original remote installer must still reject drift; use this explicit layer
after the completed remote Home/ratings chain, not by weakening old guards.
"""
import argparse
import importlib.util
import hashlib
import json
from pathlib import Path
import socket
import sys
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'kodi'))
import transaction
builder_spec = importlib.util.spec_from_file_location('remote_originals_build', HERE/'build.py')
build = importlib.util.module_from_spec(builder_spec)
builder_spec.loader.exec_module(build)
REVIEWED_FIRST_PASS = {
    'playutils.py': '8afa4aadd2afa84940544d57c47dcb72b017696f470979e474568ca08795ce8f',
    'native_originals.py': '656df894c18d6d005c7d81a5ec04b3a9957a744f36ead16c6c05358309252171',
    'remote_native/__init__.py': 'c9baba397a4abd8677cec72d051b03b342f8ede9cfa7dfd7ed040c8a6090daec',
    'remote_native/kodi_adapter.py': '4829a7d2d6754980fe496991049e8b6fb906e913aad75b0543f8060e23236e53',
    'remote_native/gate.py': '8b1764db373f3432c178f9f6895e5996b2497abbb2649423b5785674e0cc28e2',
    'remote_native/manifest.py': '79349d7a6d0f77f79a0a7da75d124b27b83d05ef81555e576152d6d43e32bc88',
}
REVIEWED_SIDECAR_PASS = dict(REVIEWED_FIRST_PASS, **{
    'remote_native/gate.py': 'c38245145fc4928c4796eb53c3cafb5f7b622c8ea6d8d7ebcee64ede8ec75da1',
})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def plan(root, payload, profile, config):
    expected, changes = {}, {}
    def read(path):
        if path not in expected:
            expected[path] = path.read_bytes() if path.exists() else None
        return expected[path]
    def require(ok, why):
        transaction.require(ok, why)
    require(profile['variant'] == 'remote' and profile['native_paths'] == {}, 'Wrong base profile')
    require(socket.gethostname() in profile['hostnames'], 'Wrong hostname')
    require(Path('/sys/class/net/wlan0/address').read_text().strip() == profile['mac'], 'Wrong physical device')
    manifest_path = root/'addons/plugin.video.habibi.resume/verified-build.json'
    record = json.loads(read(manifest_path))
    for name, digest in record['files'].items():
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe manifest path')
        content = read(root/relative)
        require(content is not None and sha(content) == digest, 'Existing source integrity drift: '+name)
    addon = ET.fromstring(read(root/'addons/plugin.video.jellyfin/addon.xml'))
    require(addon.get('version') == '2.2.0+py3', 'Unreviewed Jellyfin addon version')
    data_dir = root/'userdata/addon_data/plugin.video.jellyfin'
    values = {item.get('id'): (item.text or '') for item in ET.fromstring(read(data_dir/'settings.xml'))}
    require(values.get('useDirectPaths') == '0' and values.get('playFromStream') == 'true', 'Preserve remote addon/HTTPS mode')
    servers = json.loads(read(data_dir/'data.json'))['Servers']
    require(len(servers) == 1 and servers[0]['UserId'] == profile['jellyfin_user_id'], 'Wrong Jellyfin account')
    require(not servers[0].get('paths'), 'Unexpected global native mappings')
    endpoint = urlsplit(servers[0]['address'])
    require(endpoint.scheme == 'https' and endpoint.hostname == profile['remote_public_host'], 'Wrong public Jellyfin route')
    remote_marker = root/'userdata/addon_data/plugin.video.venom.tv/remote-native.json'
    require(sha(read(remote_marker) or b'') == '4d3f886ca60726528b56a11e2271605a146d04d29c7fa63add90891011bc240b', 'Remote Venom route changed')
    payload_record = json.loads((payload/'payload.json').read_text())
    require(payload_record.get('schema') == 1 and payload_record.get('input_playutils') == build.BASE, 'Wrong payload base')
    files = payload_record.get('files', {})
    required = {'playutils.py', 'native_originals.py', 'remote_native/__init__.py',
                'remote_native/kodi_adapter.py', 'remote_native/gate.py', 'remote_native/manifest.py'}
    require(set(files) == required, 'Unexpected payload files')
    helper = root/'addons/plugin.video.jellyfin/jellyfin_kodi/helper'
    current = {name: sha(read(helper/name)) if read(helper/name) is not None else None for name in files}
    baseline = {name: (build.BASE if name == 'playutils.py' else None) for name in files}
    require(current in (baseline, REVIEWED_FIRST_PASS, REVIEWED_SIDECAR_PASS, files), 'Unreviewed or mixed remote playback cohort')
    for name, digest in files.items():
        content = (payload/name).read_bytes()
        require(sha(content) == digest, 'Payload hash mismatch: '+name)
        compile(content, name, 'exec')
        target = helper/name
        old = read(target)
        if old != content:
            changes[target] = content
        record['files'][str(target.relative_to(root))] = digest
    require(config.get('enabled') is True, 'Explicit private opt-in required')
    require(config.get('hostname') == socket.gethostname() and config.get('wifi_mac') == profile['mac'], 'Wrong native profile identity')
    # The adapter owns transport/mapping validation. Invoke its pure validator
    # during private deployment, before starting Kodi with the new source.
    adapter_spec = importlib.util.spec_from_file_location('native_adapter_validate', payload/'remote_native/kodi_adapter.py')
    adapter = importlib.util.module_from_spec(adapter_spec)
    adapter_spec.loader.exec_module(adapter)
    require(adapter.validate_config(config) is not None, 'Invalid private original-file route')
    config_path = data_dir/'remote-originals.json'
    old_config = read(config_path)
    serialized = (json.dumps(config, indent=2)+'\n').encode()
    require(old_config is None or old_config == serialized, 'Existing remote-native profile differs; review separately')
    if old_config != serialized:
        changes[config_path] = serialized
    record['remote_originals'] = {'schema': 1, 'mode': 'gated-p7-with-https-fallback', 'global_native_mode': False}
    updated = (json.dumps(record, indent=2)+'\n').encode()
    if updated != read(manifest_path):
        changes[manifest_path] = updated
    return transaction.Plan(changes, expected)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = Path('/storage/.kodi')
    proposal = plan(root, args.payload, json.loads(args.profile.read_text()), json.loads(args.config.read_text()))
    print('Reviewed remote-native migration:', len(proposal), 'files; global Native/HTTPS/Venom settings unchanged')
    if args.apply:
        for target in proposal:
            target.parent.mkdir(parents=True, exist_ok=True)
        backup = Path('/storage/upgrade-staging')/('remote-originals-before-'+time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
        transaction.deploy(root, proposal, backup)
        print('Applied; rollback:', backup)
