#!/usr/bin/env python3
"""Use native ARR naming to carry provider identity into future library folders.

No existing media is renamed, searched, imported or deleted. Dry-run default.
"""
import argparse
import json
import os
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

POLICY = {
    'sonarr': ('seriesFolderFormat', '{Series TitleYear} [tvdbid-{TvdbId}]', 8989),
    'radarr': ('movieFolderFormat', '{Movie Title} ({Release Year}) [tmdbid-{TmdbId}]', 7878),
}

def desired(app, current):
    result = dict(current)
    field, value, _ = POLICY[app]
    result[field] = value
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', choices=POLICY, required=True)
    parser.add_argument('--config', type=Path, required=True, help='Private ARR config.xml')
    parser.add_argument('--url', help='Local ARR URL; defaults to loopback native port')
    parser.add_argument('--backup', type=Path, help='New private JSON backup path; required for apply')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    field, value, port = POLICY[args.app]
    key = ET.parse(args.config).findtext('ApiKey')
    if not key:
        parser.error('Private config has no API key')
    url = (args.url or f'http://127.0.0.1:{port}').rstrip('/') + '/api/v3/config/naming'
    def call(payload=None):
        request = urllib.request.Request(url,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'X-Api-Key': key, 'Content-Type': 'application/json'},
            method='PUT' if payload is not None else 'GET')
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    before = call()
    if not isinstance(before.get(field), str) or not before.get('id'):
        raise SystemExit('Unrecognized native naming schema; review after upgrade')
    print(json.dumps({'app': args.app, 'field': field, 'before': before[field], 'after': value,
                     'renames_existing_media': False, 'applied': False}))
    if not args.apply or before[field] == value:
        return
    if not args.backup:
        parser.error('--backup is required with --apply')
    fd = os.open(args.backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(before, out, indent=2)
        out.flush()
        os.fsync(out.fileno())
    # Refuse a concurrent settings edit; leave backup for explicit recovery.
    if call() != before:
        raise SystemExit('Naming settings changed during preflight; no write')
    after = desired(args.app, before)
    call(after)
    actual = call()
    if actual != after:
        raise SystemExit('Readback differed; inspect private backup before retry')
    print(json.dumps({'app': args.app, 'applied': True, 'verified': True}))

if __name__ == '__main__':
    main()
