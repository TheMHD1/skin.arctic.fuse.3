"""Bounded, identity-scoped 5 GHz selection through the existing Wi-Fi manager."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

BUS = 'fi.w1.wpa_supplicant1'
ROOT = '/fi/w1/wpa_supplicant1'
INTERFACE = BUS + '.Interface'
NETWORK = BUS + '.Network'


def run(*args):
    return subprocess.check_output(args, text=True, timeout=10)


def prop(path, interface, name):
    return json.loads(run('busctl', '--json=short', 'get-property', BUS,
                          path, interface, name))['data']


def is_5ghz(frequency):
    return 5000 <= frequency < 5925


def scan_candidates(scan, ssid):
    """Exact SSID and frequency, never a neighbouring household's stronger AP."""
    candidates = []
    for block in re.split(r'^BSS ', scan, flags=re.M)[1:]:
        lines = block.splitlines()
        name = next((x.strip()[6:] for x in lines if x.strip().startswith('SSID: ')), None)
        freq = re.search(r'^\s*freq: (\d+)', block, re.M)
        signal = re.search(r'^\s*signal: (-?[\d.]+)', block, re.M)
        age = re.search(r'^\s*last seen: (\d+) ms ago', block, re.M)
        mac = re.match(r'([0-9a-fA-F:]{17})\(', block)
        if name == ssid and freq and signal and mac and is_5ghz(int(freq[1])) and not (age and int(age[1]) > 20000):
            candidates.append((float(signal[1]), mac[1]))
    return sorted(candidates, reverse=True)


def allowed_frequencies(phy):
    return [int(match[1]) for line in phy.splitlines()
            if (match := re.search(r'\* (\d+)\.0 MHz', line))
            and is_5ghz(int(match[1])) and 'disabled' not in line]


def set_frequencies(network, value):
    run('busctl', 'set-property', BUS, network, NETWORK, 'Properties',
        'a{sv}', '1', 'freq_list', 's', value)


def network_ssid(properties):
    encoded = properties.get('ssid', {}).get('data', '')
    try:
        return json.loads(encoded)
    except (ValueError, TypeError):
        return None


def apply(config, state):
    device = config['interface']
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,16}', device):
        raise ValueError('invalid interface')
    if Path('/etc/hostname').read_text().strip() != config['hostname']:
        raise ValueError('hostname mismatch')
    if Path('/sys/class/net', device, 'address').read_text().strip().lower() != config['mac'].lower():
        raise ValueError('radio identity mismatch')
    country = config['country']
    if not re.fullmatch(r'[A-Z]{2}', country):
        raise ValueError('invalid physical country')
    interface = next((p for p in prop(ROOT, BUS, 'Interfaces')
                      if prop(p, INTERFACE, 'Ifname') == device), None)
    if not interface:
        return 'wifi-manager-not-ready'
    phy_name = Path('/sys/class/net', device, 'phy80211').resolve().name
    phy = run('iw', 'phy', phy_name, 'info')
    # On the reviewed Canadian AM9 driver, the early udev hint can be lost
    # during firmware initialization. Apply it again only if that defect exists.
    upper_disabled = country == 'CA' and bool(re.search(r'5745\.0 MHz[^\n]*disabled', phy))
    if upper_disabled and time.monotonic() >= state.get('country_retry_after', 0):
        state['country_retry_after'] = time.monotonic() + 1800
        run('iw', 'reg', 'set', country)
        time.sleep(2)
        phy = run('iw', 'phy', phy_name, 'info')
    if prop(interface, INTERFACE, 'Country') != country:
        run('busctl', 'set-property', BUS, interface, INTERFACE, 'Country', 's', country)
    frequencies = allowed_frequencies(phy)
    if not frequencies:
        return 'no-legal-5ghz-channels'
    networks = [p for p in prop(interface, INTERFACE, 'Networks')
                if network_ssid(prop(p, NETWORK, 'Properties')) == config['ssid']]
    if len(networks) != 1:
        return 'configured-network-not-ready-or-ambiguous'
    network = networks[0]
    link = run('iw', 'dev', device, 'link')
    current_name = re.search(r'^\s*SSID: (.*)$', link, re.M)
    if current_name and current_name[1] != config['ssid']:
        return 'other-network-preserved'
    current_freq = re.search(r'^\s*freq: (\d+)', link, re.M)
    value = ' '.join(map(str, frequencies))
    old = prop(network, NETWORK, 'Properties').get('freq_list', {}).get('data', '')
    original = state.get('previous_frequencies', '') if old == value and state.get('owns_restriction') else old
    if current_freq and is_5ghz(int(current_freq[1])):
        if old != value:
            state['previous_frequencies'] = original
            set_frequencies(network, value)
            state['owns_restriction'] = True
        return '5ghz-active-selection-restricted'
    if time.monotonic() < state.get('next_attempt', 0):
        return 'retry-cooldown'
    state['next_attempt'] = time.monotonic() + 300
    # A targeted active scan also discovers a hidden configured SSID. No PSK
    # is read, replaced, passed to a command, or printed.
    ssid = config['ssid'].encode('utf-8')
    if not 1 <= len(ssid) <= 32:
        raise ValueError('invalid SSID length')
    run('busctl', 'call', BUS, interface, INTERFACE, 'Scan', 'a{sv}', '3',
        'Type', 's', 'active', 'AllowRoam', 'b', 'false',
        'SSIDs', 'aay', '1', str(len(ssid)), *map(str, ssid))
    for _ in range(12):
        time.sleep(1)
        if not prop(interface, INTERFACE, 'Scanning'):
            break
    candidates = scan_candidates(run('iw', 'dev', device, 'scan', 'dump'), config['ssid'])
    if not candidates:
        if old == value and state.get('owns_restriction'):
            set_frequencies(network, state.get('previous_frequencies', ''))
            state['owns_restriction'] = False
            run('busctl', 'call', BUS, interface, INTERFACE, 'Reconnect')
        return 'configured-5ghz-ap-not-visible-2ghz-access-preserved'
    accepted = False
    try:
        set_frequencies(network, value)
        run('busctl', 'call', BUS, interface, INTERFACE, 'Roam', 's', candidates[0][1])
        for _ in range(10):
            time.sleep(2)
            link = run('iw', 'dev', device, 'link')
            freq = re.search(r'^\s*freq: (\d+)', link, re.M)
            name = re.search(r'^\s*SSID: (.*)$', link, re.M)
            if freq and name and name[1] == config['ssid'] and is_5ghz(int(freq[1])):
                accepted = True
                state['previous_frequencies'] = original
                state['owns_restriction'] = True
                return '5ghz-roam-accepted'
        return '5ghz-roam-failed-selection-restored'
    finally:
        if not accepted:
            # ConnMan may recreate the object during a failed handoff.
            for path in prop(interface, INTERFACE, 'Networks'):
                if network_ssid(prop(path, NETWORK, 'Properties')) == config['ssid']:
                    set_frequencies(path, original)
            state['owns_restriction'] = False
            run('busctl', 'call', BUS, interface, INTERFACE, 'Reconnect')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--state', default='/run/am9-wifi-5ghz.json')
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise InterruptedError('service stop')
    signal.signal(signal.SIGTERM, interrupted)
    config = json.loads(Path(args.config).read_bytes())
    state_path = Path(args.state)
    try:
        state = json.loads(state_path.read_bytes())
    except FileNotFoundError:
        state = {}
    try:
        result = apply(config, state)
    except Exception as error:
        result = 'check-failed-' + type(error).__name__
    # Do not duplicate a missing-AP warning every minute or expose private names.
    if state.get('result') != result and result != 'retry-cooldown':
        print('AM9 Wi-Fi: ' + result, flush=True)
        state['result'] = result
    temp = state_path.with_suffix('.pending')
    fd = os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(state, stream)
    os.replace(temp, state_path)


if __name__ == '__main__':
    main()
