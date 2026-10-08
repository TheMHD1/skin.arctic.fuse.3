"""Read-only AM9 inventory. Output is private evidence, not a public profile.

Run with Python over SSH stdin. No remote files, playback or settings are changed.
Never serialize tokens, passwords, full addon settings or raw logs.
"""
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit,parse_qs

ROOT = Path('/storage/.kodi')
SHARED = ('plugin.video.habibi.resume', 'plugin.video.venom.tv',
          'plugin.video.jellyfin', 'skin.arctic.fuse.3', 'plugin.video.kodiseerr',
          'service.upnext')
GLOBAL_SETTINGS = (
    'lookandfeel.skin', 'lookandfeel.font', 'audiooutput.audiodevice',
    'audiooutput.passthroughdevice', 'audiooutput.passthrough',
    'audiooutput.ac3passthrough', 'audiooutput.eac3passthrough',
    'audiooutput.dtspassthrough', 'audiooutput.truehdpassthrough',
    'audiooutput.dtshdpassthrough', 'audiooutput.ac3transcode', 'audiooutput.channels',
    'videoplayer.adjustrefreshrate', 'videoplayer.usedisplayasclock',
    'videoscreen.delayrefreshchange', 'videoscreen.whitelist', 'videoscreen.screenmode',
    'filecache.memorysize', 'filecache.chunksize', 'filecache.buffermode',
    'powermanagement.displaysoff', 'powermanagement.shutdowntime', 'screensaver.mode',
    'screensaver.time', 'screensaver.disableforaudio', 'screensaver.usedimonpause',
    'addons.updatemode')
CEC_IDS = ('standby_pc_on_tv_standby', 'standby_devices', 'activate_source',
           'wake_devices', 'cec_wake_screensaver', 'cec_standby_screensaver_mode',
           'enabled', 'standby_tv_on_pc_standby')
SKIN_POLICY_IDS=('homeswitcher.search.mode','startup.disablewaitforload',
                 'homeswitcher.disablesearch','homeswitcher.vertical',
                 'homeswitcher.disablefirstwidgetfocus','search.disablediscover',
                 'home.firstrun')

def menu_contract(rows):
    """Semantic routes only: no query text, tokens, account IDs or full URLs."""
    if not isinstance(rows,list):return {'error':'Unknown menu structure'}
    result=[]
    for row in rows:
        if not isinstance(row,dict):return {'error':'Unknown menu entry'}
        route=urlsplit(str(row.get('path','')))
        query=parse_qs(route.query)
        result.append({'label':row.get('label',''),
                       'addon':route.hostname if route.scheme=='plugin' else 'non-plugin',
                       'mode':query.get('mode',[''])[0],
                       'info':query.get('info',[''])[0],
                       'target':row.get('target','') if row.get('target','') in ('','videos','music','pictures') else 'custom-target'})
    return result


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rpc(method, params=None):
    try:
        with socket.create_connection(('127.0.0.1', 9090), 3) as conn:
            conn.settimeout(5)
            conn.sendall(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method,
                                    'params': params or {}}).encode())
            data = b''
            while len(data) < 4000000:
                part = conn.recv(65536)
                if not part:
                    break
                data += part
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    pass
        return {'error': {'message': 'Incomplete/oversized RPC'}}
    except (OSError, ValueError):
        return {'error': {'message': 'RPC unavailable'}}


def command(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=6)
        return {'returncode': result.returncode, 'output': result.stdout.strip()}
    except (OSError, subprocess.TimeoutExpired):
        return {'error': 'Unavailable/timed out'}


def settings(path):
    if not path.is_file():
        return {}
    return {node.get('id'): node.text or node.get('value') or ''
            for node in ET.parse(path).getroot().iter('setting')}


def addon_database(directory):
    candidates = [(int(match.group(1)), path)
                  for path in directory.glob('Addons*.db')
                  if (match := re.fullmatch(r'Addons(\d+)\.db', path.name))]
    return max(candidates, default=(None, None))[1]


def inventory():
    out = {'schema': 1, 'captured_at': datetime.now(timezone.utc).isoformat(),
           'hostname': socket.gethostname(),
           'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
           'os_release': Path('/etc/os-release').read_text(),
           'kernel': command(['uname', '-r']),
           'players': rpc('Player.GetActivePlayers'),
           'gui': rpc('GUI.GetProperties', {'properties': ['currentwindow', 'currentcontrol']}),
           'application': rpc('Application.GetProperties', {'properties': ['version', 'name']}),
           'addons': rpc('Addons.GetAddons', {'properties': ['name', 'version', 'enabled']}),
           'settings': {key: rpc('Settings.GetSettingValue', {'setting': key})
                        for key in GLOBAL_SETTINGS},
           'failed_services': command(['systemctl', '--failed', '--no-legend', '--no-pager']),
           'timers': command(['systemctl', 'list-timers', '--all', '--no-pager']),
           'storage': command(['df', '-h', '/storage', '/flash']),
           'mounts': command(['findmnt', '-n', '-o', 'TARGET,SOURCE,FSTYPE', '/storage', '/flash'])}
    for addon, keys in {
        'plugin.video.jellyfin': ('username', 'serverName', 'server', 'sslverify',
            'useDirectPaths', 'playFromStream', 'playFromTranscode', 'syncDuringPlay',
            'mediaSegmentsEnabled', 'skipIntroductionMode', 'markPlayed'),
        'service.upnext': ('autoPlayMode', 'stopAfterClose', 'includeWatched',
            'playedInARow', 'customAutoPlayTime', 'autoPlaySeasonTime'),
    }.items():
        values = settings(ROOT/'userdata/addon_data'/addon/'settings.xml')
        out[addon] = {key: values[key] for key in keys if key in values}
    auth = ROOT/'userdata/addon_data/plugin.video.jellyfin/data.json'
    servers = json.loads(auth.read_text()).get('Servers', []) if auth.is_file() else []
    out['servers'] = [{key: server.get(key) for key in
                      ('Name', 'address', 'Address', 'UserId', 'UserName', 'ServerId')}
                     for server in servers]
    out['cec'] = {path.name: {key: value for key, value in settings(path).items()
                             if key in CEC_IDS}
                  for path in sorted((ROOT/'userdata/peripheral_data').glob('cec_*.xml'))}
    out['source_hashes'] = {}
    for addon in SHARED:
        for path in (ROOT/'addons'/addon).rglob('*'):
            if (path.is_file() and not any(part in {'__pycache__', '.git'} for part in path.parts)
                    and path.suffix not in {'.pyc', '.pyo'}):
                out['source_hashes'][str(path.relative_to(ROOT))] = sha(path)
    out['shortcut_hashes'] = {str(p.relative_to(ROOT)): sha(p) for p in
                             (ROOT/'userdata/addon_data/script.skinvariables/nodes').rglob('*.json')}
    skin=settings(ROOT/'userdata/addon_data/skin.arctic.fuse.3/settings.xml')
    out['skin_policy']={key:skin.get(key) for key in SKIN_POLICY_IDS}
    out['menu_contracts']={}
    for p in (ROOT/'userdata/addon_data/script.skinvariables/nodes').rglob('*.json'):
        try:out['menu_contracts'][p.name]=menu_contract(json.loads(p.read_bytes()))
        except (ValueError,OSError):out['menu_contracts'][p.name]={'error':'Unreadable menu'}
    manifest = ROOT/'addons/plugin.video.habibi.resume/verified-build.json'
    out['manifest_sha256'] = sha(manifest) if manifest.is_file() else None
    receipt = Path('/storage/.config/am9-shared-release.json')
    out['shared_release'] = None
    if receipt.is_file():
        try:
            value = json.loads(receipt.read_bytes())
            out['shared_release'] = {key: value.get(key) for key in
                                     ('schema', 'release', 'cohort', 'manifest_sha256', 'acceptance')}
        except (ValueError, OSError):
            out['shared_release'] = {'error': 'Unreadable release receipt'}
    ux_receipt=Path('/storage/.config/am9-ux-release.json')
    out['ux_release']=None
    if ux_receipt.is_file():
        try:
            value=json.loads(ux_receipt.read_bytes())
            out['ux_release']={key:value.get(key) for key in
                              ('schema','release','cohort','manifest_sha256','acceptance')}
        except (ValueError,OSError):out['ux_release']={'error':'Unreadable UX receipt'}
    record = json.loads(manifest.read_text()) if manifest.is_file() else {}
    out['manifest_count'] = len(record.get('files', {}))
    out['manifest_drift'] = []
    for name, expected in record.get('files', {}).items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            out['manifest_drift'].append({'path': name, 'reason': 'Unsafe manifest path'})
            continue
        path = ROOT/relative
        actual = sha(path) if path.is_file() else None
        if actual != expected:
            out['manifest_drift'].append({'path': name, 'expected': expected, 'actual': actual})
    # Dependency declarations are version evidence, not an automatic upgrade order.
    out['dependencies'] = {}
    for parent in (ROOT/'addons', Path('/usr/share/kodi/addons')):
        for path in parent.glob('*/addon.xml'):
            try:
                node = ET.parse(path).getroot()
                out['dependencies'][node.get('id')] = {
                    'version': node.get('version'), 'requires': [dict(x.attrib) for x in node.findall('requires/import')]}
            except (ET.ParseError, OSError):
                continue
    out['protected_hashes'] = {}
    for pattern in ('userdata/keymaps/*.xml', 'userdata/advancedsettings.xml',
                    'userdata/peripheral_data/*.xml',
                    'userdata/addon_data/plugin.video.venom.tv/remote-native.json',
                    'userdata/addon_data/script.audiooffsetmanager/settings.xml'):
        for path in ROOT.glob(pattern):
            if path.is_file():
                out['protected_hashes'][str(path.relative_to(ROOT))] = sha(path)
    out['backup_roots'] = {}
    for path in Path('/storage/.config').glob('*backup*.py'):
        out['protected_hashes'][str(path.relative_to(Path('/storage')))] = sha(path)
        try:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.List, ast.Tuple)) and all(
                        isinstance(x, ast.Constant) and isinstance(x.value, str) for x in node.elts):
                    values = [x.value for x in node.elts]
                    if '.kodi/addons' in values:
                        out['backup_roots'][path.name] = values
            if any(isinstance(node, ast.ImportFrom) and node.module == 'device_backup_policy'
                   and any(alias.name == 'SNAPSHOT_ROOTS' for alias in node.names) for node in ast.walk(tree)):
                policy = path.parent/'device_backup_policy.py'
                if policy.is_file():
                    for node in ast.parse(policy.read_text()).body:
                        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SNAPSHOT_ROOTS' for t in node.targets):
                            roots = ast.literal_eval(node.value)
                            if isinstance(roots, (tuple, list)) and all(isinstance(x, str) for x in roots):
                                out['backup_roots'][path.name] = list(roots)
        except (SyntaxError, OSError):
            pass
    for name in ('.config/ugoos-osd-seek.py', '.cache/regdomain.conf'):
        path = Path('/storage')/name
        if path.is_file():
            out['protected_hashes'][name] = sha(path)
    # Read only supported tables, never database dumps or userdata.
    out['update_rules'] = None
    database = addon_database(ROOT/'userdata/Database')
    for path in [database] if database else []:
        out['update_rules_database'] = path.name
        try:
            with sqlite3.connect('file:'+str(path)+'?mode=ro', uri=True, timeout=2) as db:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'update_rules' in tables:
                    out['update_rules'] = [list(r) for r in db.execute('SELECT * FROM update_rules')]
        except sqlite3.Error:
            out['update_rules_error'] = 'Read-only database query failed'
    backup = Path('/storage/.config/scripts/coreelec-backup.sh')
    if backup.is_file():
        text = backup.read_text()
        out['protected_hashes'][str(backup.relative_to(Path('/storage')))] = sha(backup)
        out['local_backup_checks'] = {
            'broad_packages_exclusion': "--exclude='packages/'" in text,
            'rooted_packages_exclusion': "--exclude='/packages/'" in text,
            'connman_selected': '/storage/.cache/connman/' in text,
            'regdomain_selected': '/storage/.cache/regdomain.conf' in text,
            'sqlite_consistent_copies': '.backup ' in text,
        }
    log = ROOT/'temp/kodi.log'
    if log.is_file():
        lines = log.read_text(errors='replace').splitlines()[-12000:]
        counts = Counter()
        for line in lines:
            for label, needle in (
                ('python_exception', 'EXCEPTION Thrown'), ('python_traceback', 'Traceback (most recent call last)'),
                ('missing_dependency', 'ModuleNotFoundError'), ('jellyfin_unreachable', 'Unable to connect to Jellyfin'),
                ('http_503', '503 Service'), ('http_403', '403 Client'), ('cperipherals_crash', 'CPeripherals::GetDirectory')):
                if needle.lower() in line.lower():
                    counts[label] += 1
        out['recent_log_counts'] = dict(counts)
        out['recent_log_lines_examined'] = len(lines)
    return out


if __name__ == '__main__':
    print(json.dumps(inventory(), indent=2, sort_keys=True))
