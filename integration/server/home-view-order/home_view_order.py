#!/usr/bin/env python3
"""Safely order Jellyfin My Media views without changing any other user preference."""
import argparse
import json
import os
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request


def request(base, key, method, path, body=None):
    data = None if body is None else json.dumps(body, separators=(',', ':')).encode()
    req = urllib.request.Request(base.rstrip('/') + path, data=data, method=method,
        headers={'Authorization': 'MediaBrowser Token="' + key + '"', 'Accept': 'application/json', **({'Content-Type': 'application/json'} if data else {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return None if response.status == 204 else json.loads(response.read() or b'null')
    except urllib.error.HTTPError as error:
        raise RuntimeError('%s %s: %s' % (method, path, error.code, error.read().decode('utf-8', 'replace'))) from error


def rank(view):
    name = str(view.get('Name') or '').casefold()
    kind = str(view.get('CollectionType') or '').casefold()
    venom = name.startswith('venom')
    if venom and kind == 'movies': return 3
    if venom and kind in ('tvshows', 'series'): return 4
    if name.startswith('shoko'): return 5
    if kind == 'movies': return 0
    if kind in ('tvshows', 'series'): return 1
    if kind == 'livetv': return 2
    if kind in ('boxsets', 'collections'): return 6
    return 7


def desired_order(views, before):
    """Return every prior OrderedViews id exactly once; unknown/hidden ids remain tail-stable."""
    prior = [str(item) for item in before if item]
    prior_set = set(prior)
    known = []
    unknown_current = []
    for index, view in enumerate(views):
        view_id = str(view.get('Id') or '')
        if not view_id: continue
        (unknown_current if rank(view) == 7 else known).append((rank(view), index, view_id))
    known_ids = [item[2] for item in sorted(known)]
    known_set = set(known_ids)
    # Keep unknown current views in their server order, but retain old hidden/nonreturned ids too.
    tail = [item for item in prior if item not in known_set]
    tail.extend(item[2] for item in unknown_current if item[2] not in prior_set)
    return list(dict.fromkeys(known_ids + tail))


def private_key(path):
    mode = stat.S_IMODE(os.stat(path).st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise RuntimeError('API key file must not be group/world accessible (chmod 600)')
    with open(path, encoding='utf-8') as handle:
        value = handle.read().strip()
    if not value: raise RuntimeError('API key file is empty')
    return value


def append_journal(path, record):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    payload = (json.dumps(record, separators=(',', ':')) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.fchmod(fd, 0o600)
        if os.write(fd, payload) != len(payload): raise RuntimeError('incomplete journal write')
        os.fsync(fd)
    finally:
        os.close(fd)


def select_users(users, names, all_users):
    if all_users == bool(names): raise RuntimeError('choose exactly one of --all-users or one or more --user names')
    if all_users: return users
    wanted = {name.casefold() for name in names}
    selected = [user for user in users if str(user.get('Name') or '').casefold() in wanted]
    found = {str(user.get('Name') or '').casefold() for user in selected}
    missing = wanted - found
    if missing: raise RuntimeError('user not found: ' + ', '.join(sorted(missing)))
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--api-key-file', required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--all-users', action='store_true')
    scope.add_argument('--user', action='append', default=[])
    parser.add_argument('--apply', action='store_true', help='POST verified configuration changes (default is dry run)')
    parser.add_argument('--journal', help='required with --apply; private 0600 JSONL journal')
    parser.add_argument('--restore', action='store_true', help='restore OrderedViews from journal; requires --apply')
    args = parser.parse_args(argv)
    if args.apply and not args.journal: parser.error('--apply requires --journal')
    if args.restore and not args.apply: parser.error('--restore requires --apply')
    key = private_key(args.api_key_file)
    users = select_users(request(args.url, key, 'GET', '/Users'), args.user, args.all_users)
    if args.restore:
        records = [json.loads(line) for line in open(args.journal, encoding='utf-8') if line.strip()]
        latest = {record['userId']: record for record in records}
    for user in users:
        user_id = str(user['Id'])
        fresh = request(args.url, key, 'GET', '/Users/' + urllib.parse.quote(user_id))
        config = fresh.get('Configuration')
        if not isinstance(config, dict): raise RuntimeError('user configuration missing for ' + user_id)
        before = list(config.get('OrderedViews') or [])
        if args.restore:
            record = latest.get(user_id)
            if not record: raise RuntimeError('no journal record for ' + user_id)
            if before != record['after']: raise RuntimeError('OrderedViews drift for ' + user_id)
            after = record['before']
        else:
            views = request(args.url, key, 'GET', '/Users/' + urllib.parse.quote(user_id) + '/Views').get('Items', [])
            after = desired_order(views, before)
        print('%s: %s -> %s' % (fresh.get('Name', user_id), before, after))
        if not args.apply or before == after: continue
        # Fresh re-read closes the config overwrite race before posting the full configuration body.
        current = request(args.url, key, 'GET', '/Users/' + urllib.parse.quote(user_id)).get('Configuration')
        if current != config: raise RuntimeError('configuration drift for ' + user_id)
        updated = dict(config); updated['OrderedViews'] = after
        append_journal(args.journal, {'userId': user_id, 'before': before, 'after': after})
        request(args.url, key, 'POST', '/Users/' + urllib.parse.quote(user_id) + '/Configuration', updated)
        verified = request(args.url, key, 'GET', '/Users/' + urllib.parse.quote(user_id)).get('Configuration')
        if verified.get('OrderedViews') != after or {k:v for k,v in verified.items() if k != 'OrderedViews'} != {k:v for k,v in config.items() if k != 'OrderedViews'}:
            raise RuntimeError('post verification failed for ' + user_id)


if __name__ == '__main__':
    main()
