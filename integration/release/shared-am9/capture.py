"""Capture read-only SSH inventory into a new private local evidence file."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def capture(target, destination, expected_hostname, host_key_alias=None):
    source = Path(__file__).with_name('inventory.py').read_bytes()
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=6']
    if host_key_alias:
        command += ['-o', 'HostKeyAlias='+host_key_alias]
    command += [target, 'python3 -']
    result = subprocess.run(command, input=source, capture_output=True, timeout=240, check=True)
    record = json.loads(result.stdout)
    if record['hostname'] != expected_hostname:
        raise ValueError('Wrong appliance; inventory was not saved')
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if destination.parent.stat().st_mode & 0o077:
        raise ValueError('Evidence directory must be private (0700)')
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write('\n')
    return {key: record.get(key) for key in ('captured_at', 'hostname', 'manifest_count',
                                           'manifest_drift', 'recent_log_counts')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--expected-hostname', required=True)
    parser.add_argument('--host-key-alias')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(capture(args.target, args.output, args.expected_hostname, args.host_key_alias), indent=2))
