#!/usr/bin/env python3
"""Repair Seerr 3.4.1 webhook payload encoding through its settings API only."""
import argparse
import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import urllib.request


ROUTE = '/api/v1/settings/notifications/webhook'
SOURCE = '/app/dist/lib/notifications/agents/webhook.js'


def private_backup(path, document):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(document, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def parser_guard(container='jellyseerr'):
    result = subprocess.run(['docker', 'exec', container, 'cat', SOURCE],
                            check=True, capture_output=True, text=True, timeout=15)
    if 'JSON.parse(JSON.parse(payloadString))' not in result.stdout:
        raise RuntimeError('Installed webhook parser is not the known 3.4.1 double-parse implementation')


def request(base, key, route, document=None):
    headers = {'X-Api-Key': key}
    data = None
    if document is not None:
        data = json.dumps(document).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(base.rstrip('/') + route, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def repair(api, settings_path, backup_path, container='jellyseerr', apply=False):
    parser_guard(container)
    settings = json.loads(Path(settings_path).read_text())
    key = settings['main']['apiKey']
    raw = settings['notifications']['agents']['webhook']
    status = api(key, '/api/v1/status')
    if status.get('version') != '3.4.1':
        raise RuntimeError('Unexpected Seerr version')
    before = api(key, ROUTE)
    payload = before['options']['jsonPayload']
    decoded = base64.b64decode(raw['options']['jsonPayload'], validate=True).decode()
    if isinstance(payload, str):
        if not isinstance(json.loads(payload), dict):
            raise RuntimeError('Existing webhook payload is not a JSON object')
        if json.loads(decoded) != payload:
            raise RuntimeError('API and private stored payload disagree')
        return 'already-correct'
    if not isinstance(payload, dict):
        raise RuntimeError('Unexpected webhook payload type')
    if json.loads(decoded) != payload:
        raise RuntimeError('API and private stored payload disagree')
    desired = copy.deepcopy(before)
    desired['options']['jsonPayload'] = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    if not apply:
        return 'repair-needed'
    private_backup(backup_path, {'version': status['version'], 'raw_webhook': raw,
                                  'api_webhook': before})
    # Fail closed if an administrator changed settings between the backup and POST.
    if api(key, ROUTE) != before or json.loads(Path(settings_path).read_text())['notifications']['agents']['webhook'] != raw:
        raise RuntimeError('Webhook settings changed since backup; no update sent')
    api(key, ROUTE, desired)
    after = api(key, ROUTE)
    if after != desired:
        raise RuntimeError('Webhook settings API readback differs from intended value')
    expected_raw = base64.b64encode(json.dumps(desired['options']['jsonPayload']).encode()).decode()
    saved = json.loads(Path(settings_path).read_text())['notifications']['agents']['webhook']
    if saved['options']['jsonPayload'] != expected_raw:
        raise RuntimeError('Persisted webhook payload encoding did not match API readback')
    return 'repaired'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', required=True, help='Private URL of the installed Seerr service')
    p.add_argument('--settings-file', type=Path, default=Path('/data/config/jellyseerr/settings.json'))
    p.add_argument('--container', default='jellyseerr')
    p.add_argument('--backup', type=Path)
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    if args.apply and not args.backup:
        p.error('--apply requires a new private --backup path')
    result = repair(lambda key, route, document=None: request(args.url, key, route, document),
                    args.settings_file, args.backup, args.container, args.apply)
    print(result)


if __name__ == '__main__':
    main()
