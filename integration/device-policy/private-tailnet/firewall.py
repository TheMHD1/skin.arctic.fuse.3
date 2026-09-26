"""A narrow appliance firewall for ordinary SSH and a private media peer.

Only tailscale0 traffic is touched. Tailnet control-plane grants are still
required: local root could remove this defense-in-depth device policy.
"""
import argparse
import fcntl
import ipaddress
import json
import shlex
import socket
import subprocess
from pathlib import Path

CHAINS = ('AM9TS_IN', 'AM9TS_OUT', 'AM9TS_FWD')
HOOKS = (
    ('INPUT', '-i', 'AM9TS_IN'), ('OUTPUT', '-o', 'AM9TS_OUT'),
    ('FORWARD', '-i', 'AM9TS_FWD'), ('FORWARD', '-o', 'AM9TS_FWD'),
)


def validate(config):
    if set(config) != {'hostname', 'wifi_mac', 'admin_ipv4', 'media_ipv4'}:
        raise ValueError('Unexpected private firewall profile fields')
    addresses = []
    for key in ('admin_ipv4', 'media_ipv4'):
        value = config[key]
        address = ipaddress.ip_address(value)
        if address.version != 4 or address not in ipaddress.ip_network('100.64.0.0/10') or str(address) != value:
            raise ValueError('Require canonical private-overlay IPv4 peers')
        addresses.append(address)
    if addresses[0] == addresses[1]:
        raise ValueError('Administrative and media peers must be distinct')


def render(config, existing, ipv6=False):
    validate(config)
    lines = ['*filter'] + [':'+name+' - [0:0]' for name in CHAINS]
    lines += ['-F '+name for name in CHAINS]
    # Atomically normalize only our exact interface-qualified jumps. Preserve
    # unrelated tables, chains, rules and every built-in default policy.
    tokens = [shlex.split(line) for line in existing.splitlines() if line.startswith('-A ')]
    for root, direction, chain in HOOKS:
        rule = [root, direction, 'tailscale0', '-j', chain]
        lines += ['-D '+' '.join(rule)] * tokens.count(['-A']+rule)
        lines.append('-I '+root+' 1 '+' '.join(rule[1:]))
    for name in ('AM9TS_IN', 'AM9TS_OUT'):
        lines.append('-A '+name+' -m conntrack --ctstate INVALID -j DROP')
    if not ipv6:
        admin = config['admin_ipv4']
        media = config['media_ipv4']
        lines += [
            '-A AM9TS_IN -s '+admin+'/32 -p tcp --dport 22 -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT',
            '-A AM9TS_OUT -d '+admin+'/32 -p tcp --sport 22 -m conntrack --ctstate ESTABLISHED -j ACCEPT',
            '-A AM9TS_IN -s '+media+'/32 -p tcp --sport 2049 -m conntrack --ctstate ESTABLISHED -j ACCEPT',
            '-A AM9TS_IN -s '+admin+'/32 -p icmp --icmp-type echo-request -j ACCEPT',
            '-A AM9TS_OUT -d '+admin+'/32 -p icmp --icmp-type echo-reply -j ACCEPT',
            '-A AM9TS_OUT -d '+media+'/32 -p tcp --dport 2049 -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT',
            '-A AM9TS_OUT -d '+media+'/32 -p icmp --icmp-type echo-request -j ACCEPT',
            '-A AM9TS_IN -s '+media+'/32 -p icmp --icmp-type echo-reply -j ACCEPT',
        ]
    lines += ['-A '+name+' -j DROP' for name in CHAINS]
    return '\n'.join(lines+['COMMIT', ''])


def daemon_running():
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if (entry/'comm').read_text().strip() == 'tailscaled':
                return True
        except FileNotFoundError:
            pass
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    path = Path(args.config)
    if path.stat().st_uid != 0 or path.stat().st_mode & 0o077:
        raise RuntimeError('Private profile must be root-owned and mode0600')
    config = json.loads(path.read_text())
    validate(config)
    if socket.gethostname() != config['hostname'] or Path('/sys/class/net/wlan0/address').read_text().strip() != config['wifi_mac']:
        raise RuntimeError('Wrong appliance identity')
    plans = []
    for binary, ipv6 in [('iptables', False), ('ip6tables', True)]:
        existing = subprocess.check_output([binary+'-save', '-t', 'filter'], text=True)
        plan = render(config, existing, ipv6)
        subprocess.run([binary+'-restore', '--noflush', '--test'], input=plan, text=True, check=True)
        plans.append((binary, plan))
    if args.apply:
        # IPv4 and IPv6 are separate kernel transactions. Never change them
        # around an active overlay daemon; ExecStartPre runs before it starts.
        if daemon_running():
            raise RuntimeError('Stop Tailscale before applying both address-family policies')
        for binary, plan in plans:
            subprocess.run([binary+'-restore', '--noflush'], input=plan, text=True, check=True)
        print('Applied private-overlay-only IPv4/IPv6 policy; LAN rules preserved')
    else:
        print('Validated private-overlay-only IPv4/IPv6 policy; no rules changed')


if __name__ == '__main__':
    with open('/run/am9-tailnet-firewall.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        main()
