"""Run one reviewed official Tailscale startup with explicit appliance prefs.

The upstream script uses --reset on every start. Preserve its lifecycle while
making DNS, SSH interception and inbound-mode choices explicit. Do not install
this wrapper over an unknown addon revision or enable automatic addon updates.
"""
import hashlib
import json
import shlex
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

START = Path('/storage/.kodi/addons/service.tailscale/bin/tailscale.start')
REVIEWED_SHA = 'f24f06e0ea50d8ab2bdbc93f8b9b8c43f8799318f1c079b47e8de8145353bfd0'
OLD = 'TS_ARGS="--reset --netfilter-mode=off"'
NEW = 'TS_ARGS="--reset --netfilter-mode=off --accept-dns=false --accept-routes=false --ssh=false --shields-up=false --timeout=30s"'
ADDON = START.parent.parent
SETTINGS = Path('/storage/.kodi/userdata/addon_data/service.tailscale/settings.xml')
LAUNCHER = '/storage/.config/am9-tailnet-launch.py'


def settings_values(sources):
    values = {}
    for source in sources:
        root = ET.fromstring(source)
        if root.tag != 'settings' or root.get('version', '1') not in ('1', '2', '3', '4'):
            raise ValueError('Unreviewed Kodi settings format')
        for item in root.findall('setting'):
            value = item.get('value', '') if root.get('version', '1') == '1' else (item.text or '')
            values[item.get('id')] = value.strip()
    required = {'ts_connect': 'true', 'ts_auto_hostname': 'false',
                'ts_accept_routes': 'false', 'ts_exit_node': 'false',
                'ts_subnet_routes': 'false', 'ts_use_exit_node': 'false',
                'ts_subnets': '', 'ts_exit_node_host': ''}
    if any(values.get(key) != value for key, value in required.items()):
        raise ValueError('Private appliance settings changed; review routing/connect policy')
    import socket
    if values.get('ts_hostname') != socket.gethostname():
        raise ValueError('Tailscale hostname must match this appliance')
    # Whitelist assignments: never evaluate arbitrary XML IDs as shell code.
    return '\n'.join(key+'='+shlex.quote(values[key]) for key in (*required, 'ts_hostname'))


def reviewed_start(source, assignments):
    if hashlib.sha256(source).hexdigest() != REVIEWED_SHA:
        raise RuntimeError('Unreviewed Tailscale addon startup; review before upgrade')
    text = source.decode()
    if text.count(OLD) != 1:
        raise RuntimeError('Unexpected official startup shape')
    text = text.replace(OLD, NEW, 1)
    # Amlogic's oe_setup_addon treats v3/v4 text values as legacy @value,
    # silently erasing ts_connect. Override only this addon's parsed values;
    # never patch the global loader or rewrite Kodi's settings version.
    text = text.replace('oe_setup_addon service.tailscale',
                        'oe_setup_addon service.tailscale\n'+assignments, 1)
    text = text.replace('[ -S "$SOCKET" ] && break',
                        '[ -S "$SOCKET" ] && $TAILSCALE --socket="$SOCKET" status --json >/dev/null 2>&1 && break', 1)
    text = text.replace('if [ ! -S "$SOCKET" ]; then',
                        'if ! $TAILSCALE --socket="$SOCKET" status --json >/dev/null 2>&1; then', 1)
    text = text.replace('  $TAILSCALE --socket="$SOCKET" up $TS_ARGS', '''  $TAILSCALE --socket="$SOCKET" set --auto-update=false --update-check=true || exit 1
  $TAILSCALE --socket="$SOCKET" up $TS_ARGS
  $TAILSCALE --socket="$SOCKET" set --auto-update=false --update-check=true || exit 1
  # Offline up can time out with WantRunning=true; leave its daemon alive to
  # reconnect. Unsafe/stopped preferences fail instead of false readiness.
  /usr/bin/python3 '''+LAUNCHER+''' --verify-prefs || exit 1''', 1)
    return text


def safe_prefs(prefs):
    return (prefs.get('WantRunning') is True
            and all(prefs.get(key) is False for key in ('RouteAll', 'CorpDNS', 'RunSSH', 'ShieldsUp'))
            and not any(prefs.get(key) for key in ('AdvertiseRoutes', 'ExitNodeID', 'ExitNodeIP'))
            and prefs.get('NetfilterMode') == 0
            and prefs.get('AutoUpdate', {}).get('Apply') is False)


if __name__ == '__main__':
    if sys.argv[1:] == ['--verify-prefs']:
        for attempt in range(10):
            prefs = json.loads(subprocess.check_output(
                [str(ADDON/'bin/tailscale'), '--socket=/run/tailscale/tailscaled.sock', 'debug', 'prefs'], timeout=10))
            if safe_prefs(prefs):
                break
            time.sleep(0.5)
        if not safe_prefs(prefs):
            raise SystemExit('Private Tailscale preference verification failed')
        print('Private Tailscale preferences verified; network readiness is checked separately')
    elif not sys.argv[1:]:
        assignments = settings_values([(ADDON/'settings-default.xml').read_bytes(), SETTINGS.read_bytes()])
        raise SystemExit(subprocess.call(['/bin/sh', '-c', reviewed_start(START.read_bytes(), assignments)]))
    else:
        raise SystemExit('Unexpected launcher arguments')
