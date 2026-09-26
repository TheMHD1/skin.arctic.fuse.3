"""Guarded, exact-peer NFSv4 DNAT policy for one private appliance.

This is deliberately a transport policy, not an NFS server configurator.  It
never changes nfs.conf, exports, Docker, Tailscale, or a general firewall
policy.  The caller must install the matching exact read-only export before
enabling the NAT half of this policy.

The post-DNAT INPUT rule checks both the rewritten destination and conntrack's
original overlay destination.  That prevents a route to the LAN address from
accidentally becoming an equivalent tailnet NFS route.
"""
import argparse
import fcntl
import ipaddress
import json
import socket
import subprocess
from pathlib import Path

NAT_CHAIN = 'AM9NFS_DNAT'
FILTER_CHAIN = 'AM9NFS_INPUT'
PORT = '2049'


def _overlay(value):
    address = ipaddress.ip_address(value)
    if address.version != 4 or address not in ipaddress.ip_network('100.64.0.0/10') or str(address) != value:
        raise ValueError('Require canonical private-overlay IPv4 addresses')
    return address


def _private(value):
    address = ipaddress.ip_address(value)
    rfc1918 = (ipaddress.ip_network('10.0.0.0/8'), ipaddress.ip_network('172.16.0.0/12'),
               ipaddress.ip_network('192.168.0.0/16'))
    if address.version != 4 or not any(address in network for network in rfc1918) or str(address) != value:
        raise ValueError('Require canonical RFC1918 backend IPv4 address')
    return address


def validate(config):
    expected = {'bridge_hostname', 'client_ipv4', 'overlay_ipv4', 'backend_ipv4'}
    if set(config) != expected:
        raise ValueError('Unexpected media-forward profile fields')
    client, overlay = _overlay(config['client_ipv4']), _overlay(config['overlay_ipv4'])
    backend = _private(config['backend_ipv4'])
    if len({client, overlay, backend}) != 3:
        raise ValueError('Client, overlay and backend peers must be distinct')
    if not config['bridge_hostname'] or any(c.isspace() for c in config['bridge_hostname']):
        raise ValueError('Require a simple expected bridge hostname')


def _rules(existing, table, parent, tokens):
    """Delete each exact old hook, then put exactly one at priority one."""
    lines = []
    parsed = [line.split() for line in existing.splitlines() if line.startswith('-A ')]
    old = [parent] + tokens
    lines += ['-D ' + ' '.join(old)] * parsed.count(['-A'] + old)
    lines.append('-I ' + parent + ' 1 ' + ' '.join(tokens))
    return lines


def render_nat(config, existing):
    validate(config)
    # iptables-save canonicalizes source/destination before the interface.
    # Match its real output so periodic reconciliation removes exact old hooks.
    hook = nat_hooks(config)[0][1]
    lines = ['*nat', ':' + NAT_CHAIN + ' - [0:0]', '-F ' + NAT_CHAIN]
    lines += _rules(existing, 'nat', 'PREROUTING', hook)
    lines += ['-A ' + NAT_CHAIN + ' -p tcp -m tcp -j DNAT --to-destination ' + config['backend_ipv4'] + ':' + PORT,
              'COMMIT', '']
    return '\n'.join(lines)


def render_filter(config, existing, ipv6=False, block_all=False):
    validate(config)
    lines = ['*filter', ':' + FILTER_CHAIN + ' - [0:0]', '-F ' + FILTER_CHAIN]
    for protocol in ('tcp', 'udp'):
        lines += _rules(existing, 'filter', 'INPUT',
                        ['-i', 'tailscale0', '-p', protocol, '-m', protocol,
                         '--dport', PORT, '-j', FILTER_CHAIN])
    if not ipv6 and not block_all:
        lines.append('-A ' + FILTER_CHAIN + ' -s ' + config['client_ipv4'] + '/32 -d ' +
                     config['backend_ipv4'] + '/32 -p tcp -m tcp --dport ' + PORT +
                     ' -m conntrack --ctorigdst ' + config['overlay_ipv4'] +
                     ' --ctorigdstport ' + PORT +
                     ' -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT')
    # Both TCP and UDP are terminal here.  The NFS service is TCP-only, but
    # blocking UDP closes a future/accidental UDP listener too.
    lines += ['-A ' + FILTER_CHAIN + ' -j DROP', 'COMMIT', '']
    return '\n'.join(lines)


def render_remove(existing, table, chain, hooks):
    """Produce a noflush rollback that affects only our chain and exact jumps."""
    parsed = [line.split() for line in existing.splitlines() if line.startswith('-A ')]
    lines = ['*' + table]
    for parent, tokens in hooks:
        old = [parent] + tokens
        lines += ['-D ' + ' '.join(old)] * parsed.count(['-A'] + old)
    if ':' + chain + ' ' in existing:
        lines += ['-F ' + chain, '-X ' + chain]
    lines += ['COMMIT', '']
    return '\n'.join(lines)


def nat_hooks(config):
    return [('PREROUTING', ['-s', config['client_ipv4'] + '/32',
                             '-d', config['overlay_ipv4'] + '/32', '-i', 'tailscale0', '-p', 'tcp',
                             '-m', 'tcp', '--dport', PORT, '-j', NAT_CHAIN])]


def filter_hooks():
    return [('INPUT', ['-i', 'tailscale0', '-p', proto, '-m', proto,
                       '--dport', PORT, '-j', FILTER_CHAIN])
            for proto in ('tcp', 'udp')]


def filter_ready(config, existing, ipv6=False):
    """Require the exact active narrow chain before a DNAT can be installed."""
    hooks = ['-A ' + parent + ' ' + ' '.join(tokens) for parent, tokens in filter_hooks()]
    input_rules = [line for line in existing.splitlines() if line.startswith('-A INPUT ')]
    if any(input_rules.count(hook) != 1 for hook in hooks):
        return False
    ts = next((index for index, line in enumerate(input_rules) if line == '-A INPUT -j ts-input'), len(input_rules))
    if any(input_rules.index(hook) >= ts for hook in hooks):
        return False
    chain = [line for line in existing.splitlines() if line.startswith('-A ' + FILTER_CHAIN + ' ')]
    expected = ['-A ' + FILTER_CHAIN + ' -j DROP']
    if not ipv6:
        expected.insert(0, '-A ' + FILTER_CHAIN + ' -s ' + config['client_ipv4'] + '/32 -d ' +
                        config['backend_ipv4'] + '/32 -p tcp -m tcp --dport ' + PORT +
                        ' -m conntrack --ctorigdst ' + config['overlay_ipv4'] +
                        ' --ctorigdstport ' + PORT +
                        ' -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT')
    return chain == expected


def checked_profile(path):
    if path.stat().st_uid != 0 or path.stat().st_mode & 0o077:
        raise RuntimeError('Private profile must be root-owned and mode0600')
    config = json.loads(path.read_text())
    validate(config)
    if socket.gethostname() != config['bridge_hostname']:
        raise RuntimeError('Wrong NFS bridge host identity')
    addresses = subprocess.check_output(['ip', '-j', '-4', 'address', 'show'], text=True)
    current = {info['local'] for item in json.loads(addresses) for info in item.get('addr_info', [])
               if info.get('family') == 'inet'}
    if config['backend_ipv4'] not in current:
        raise RuntimeError('Configured NFS backend is not a local IPv4 address')
    # Boot before tailscaled is permitted: absent tailscale0 makes the rules
    # inert.  If the interface exists, its address must exactly agree.
    result = subprocess.run(['ip', '-j', '-4', 'address', 'show', 'dev', 'tailscale0'],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if result.returncode == 0:
        present = {info['local'] for item in json.loads(result.stdout) for info in item.get('addr_info', [])
                   if info.get('family') == 'inet'}
        if config['overlay_ipv4'] not in present:
            raise RuntimeError('tailscale0 identity drift; refusing policy change')
    return config


def _test(binary, plan):
    subprocess.run([binary + '-restore', '--noflush', '--test'], input=plan, text=True, check=True)


def _apply(binary, plan):
    subprocess.run([binary + '-restore', '--noflush'], input=plan, text=True, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply-filter', action='store_true')
    mode.add_argument('--block-all', action='store_true')
    mode.add_argument('--apply-nat', action='store_true')
    mode.add_argument('--reconcile', action='store_true')
    mode.add_argument('--remove-filter', action='store_true')
    mode.add_argument('--remove-nat', action='store_true')
    args = parser.parse_args()
    config = checked_profile(Path(args.config))
    ipv4_filter = subprocess.check_output(['iptables-save', '-t', 'filter'], text=True)
    ipv6_filter = subprocess.check_output(['ip6tables-save', '-t', 'filter'], text=True)
    ipv4_nat = subprocess.check_output(['iptables-save', '-t', 'nat'], text=True)
    if args.remove_filter:
        plans = [('iptables', render_remove(ipv4_filter, 'filter', FILTER_CHAIN, filter_hooks())),
                 ('ip6tables', render_remove(ipv6_filter, 'filter', FILTER_CHAIN, filter_hooks()))]
    elif args.remove_nat:
        plans = [('iptables', render_remove(ipv4_nat, 'nat', NAT_CHAIN, nat_hooks(config)))]
    elif args.apply_nat:
        if not filter_ready(config, ipv4_filter) or not filter_ready(config, ipv6_filter, ipv6=True):
            raise RuntimeError('Refuse DNAT until exact IPv4/IPv6 NFS filters are active before ts-input')
        plans = [('iptables', render_nat(config, ipv4_nat))]
    elif args.apply_filter or args.block_all:
        plans = [('iptables', render_filter(config, ipv4_filter)),
                 ('ip6tables', render_filter(config, ipv6_filter, ipv6=True))]
        if args.block_all:
            plans = [('iptables', render_filter(config, ipv4_filter, block_all=True)),
                     ('ip6tables', render_filter(config, ipv6_filter, ipv6=True, block_all=True))]
    else:
        # A dry run validates all three kernel-table operations without
        # suggesting that cross-table application is atomic.
        plans = [('iptables', render_filter(config, ipv4_filter)),
                 ('ip6tables', render_filter(config, ipv6_filter, ipv6=True)),
                 ('iptables', render_nat(config, ipv4_nat))]
    for binary, plan in plans:
        _test(binary, plan)
    if args.check:
        print('Validated exact-peer NFS bridge plans; no rules changed')
        return
    for binary, plan in plans:
        _apply(binary, plan)
    print('Applied ' + ('removal' if args.remove_filter or args.remove_nat else
                         'filter' if args.apply_filter else 'all-NFS block' if args.block_all else 'DNAT' if args.apply_nat else
                         'filter-then-DNAT reconciliation') + ' plan')


if __name__ == '__main__':
    with open('/run/am9-nfs-forward.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        main()
