#!/usr/bin/env python3
"""Guarded native Seerr library selection; dry-run unless explicitly applied."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request

SUPPORTED_VERSION = "3.4.1"


def request(url, key, path, body=None):
    req = urllib.request.Request(url.rstrip('/') + '/api/v1/' + path,
        headers={'X-Api-Key': key, 'Content-Type': 'application/json'},
        data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def plan(settings, selections, native):
    result = copy.deepcopy(settings)
    libraries = result.get('libraries')
    if not isinstance(libraries, list) or not libraries:
        raise ValueError('No existing native Seerr library selections')
    if len({row['id'] for row in libraries}) != len(libraries):
        raise ValueError('Duplicate Seerr library identity')
    for identity, kind in selections.items():
        if not re.fullmatch(r'[a-fA-F0-9]{32}', identity) or kind not in {'movie', 'show'}:
            raise ValueError('An exact native library ID and movie/show type are required')
        matched = [row for row in libraries if row['id'] == identity]
        actual = [row for row in native if row.get('ItemId') == identity]
        if len(matched) != 1 or matched[0].get('type') != kind or len(actual) != 1:
            raise ValueError('Selected library is absent or ambiguous')
        if actual[0].get('CollectionType') != {'movie': 'movies', 'show': 'tvshows'}[kind] or not actual[0].get('Locations'):
            raise ValueError('Native library does not match an owned physical movie/show library')
        matched[0]['enabled'] = True
    return result


def private_backup(path, payload):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        json.dump(payload, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())


def repair(api, native, selections, backup=None, apply=False, config=None):
    version = api('status')['version']
    if version != SUPPORTED_VERSION:
        raise ValueError('Review the native route/schema before a Seerr version change')
    before = api('settings/jellyfin')  # Safe read: /jellyfin/library is NOT a read-only endpoint.
    after = plan(before, selections, native)
    changed = after != before
    if apply and changed:
        if backup is None:
            raise ValueError('Applying a selection requires a new private backup path')
        private_backup(backup, {'version': version, 'jellyfin': before, 'configuration': config})
        if api('settings/jellyfin') != before:
            raise ValueError('Concurrent Jellyfin settings change; no mutation performed')
        enabled = [row['id'] for row in after['libraries'] if row.get('enabled')]
        # This supported route changes ONLY library enabled flags. No sync flag:
        # refreshing the library inventory can change selection/name semantics.
        result = api('settings/jellyfin/library?' + urllib.parse.urlencode({'enable': ','.join(enabled)}))
        if result != after['libraries'] or api('settings/jellyfin') != after:
            raise ValueError('Native selection readback mismatch; inspect private backup before retrying')
    return {'version': version, 'apply': apply, 'changed': changed,
            'selectedCount': len(selections), 'enabledCount': sum(bool(row.get('enabled')) for row in after['libraries'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--settings', required=True, type=Path, help='Private Seerr settings.json; never printed')
    parser.add_argument('--jellyfin-url', required=True)
    parser.add_argument('--library', required=True, action='append', help='Exact native library ID=movie|show')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    config = json.loads(args.settings.read_text())
    key = config['main']['apiKey']
    selections = dict(value.split('=', 1) for value in args.library)
    if len(selections) != len(args.library):
        parser.error('Duplicate selected library')
    jf = urllib.request.Request(args.jellyfin_url.rstrip('/') + '/Library/VirtualFolders',
        headers={'Authorization': 'MediaBrowser Token="' + config['jellyfin']['apiKey'] + '"'})
    with urllib.request.urlopen(jf, timeout=30) as response:
        native = json.load(response)
    print(json.dumps(repair(lambda path: request(args.url, key, path), native, selections,
                            args.backup, args.apply, config)))


if __name__ == '__main__':
    main()
