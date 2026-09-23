#!/usr/bin/env python3
"""Plan/apply exact-file import dates; never edit a Jellyfin database directly."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
import urllib.parse
import urllib.request


def timestamp(value):
    result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result.astimezone(dt.timezone.utc)


def private_json(path, value):
    # Refuse overwriting audit/rollback evidence.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def replace_private_json(path, value):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Refusing symlinked journal')
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def same_date(first, second):
    return abs((timestamp(first) - timestamp(second)).total_seconds()) < .001


def plan_digest(plan):
    data = json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(data).hexdigest()


def validate_plan(plan):
    if plan.get('schema') != 1 or not isinstance(plan.get('repairs'), list):
        raise ValueError('Unsupported repair plan')
    seen = set()
    for entry in plan['repairs']:
        item_id = entry.get('id')
        path = entry.get('ExpectedPath')
        if not isinstance(item_id, str) or not re.fullmatch(r'[0-9a-f]{32}', item_id, re.I) or item_id.lower() in seen:
            raise ValueError('Missing or duplicate item ID')
        seen.add(item_id.lower())
        if entry.get('type') not in ('Movie', 'Episode') or not isinstance(path, str) or not os.path.isabs(path) or Path(path).suffix.lower() == '.strm':
            raise ValueError('Unsafe item type or path in plan')
        previous = timestamp(entry['ExpectedDateCreated'])
        desired = timestamp(entry['DateCreated'])
        if previous.year < 2000 or desired.year < 2000 or desired > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
            raise ValueError('Plan date cannot be safely applied and reversed')
        if same_date(entry['ExpectedDateCreated'], entry['DateCreated']):
            raise ValueError('Plan contains an unchanged date')


def item_state(api, entry, expected_series_id=None):
    # SeriesId is a core Episode DTO property in Jellyfin 12.1, not an ItemFields
    # enum value; requesting it in Fields would make the query invalid.
    response = api.call('/Items', {'Ids': entry['id'], 'Fields': 'Path,DateCreated',
                                   'Limit': 1, 'EnableTotalRecordCount': 'false'})
    rows = response.get('Items', [])
    item = next((row for row in rows if isinstance(row.get('Id'), str)
                 and row['Id'].lower() == entry['id'].lower()), None)
    if item is None or item.get('Type') != entry['type'] or item.get('Path') != entry['ExpectedPath'] or not item.get('DateCreated'):
        raise RuntimeError('Item identity or path changed; stop and create a fresh plan')
    series_id = None
    if entry['type'] == 'Episode':
        series_id = item.get('SeriesId')
        if not isinstance(series_id, str) or not re.fullmatch(r'[0-9a-f]{32}', series_id, re.I):
            raise RuntimeError('Episode has no exact parent series; stop and investigate')
        series_id = series_id.lower()
        if expected_series_id is not None and series_id != expected_series_id.lower():
            raise RuntimeError('Episode parent series changed; stop and create a fresh plan')
    current = item['DateCreated']
    if same_date(current, entry['ExpectedDateCreated']):
        return 'old', series_id
    if same_date(current, entry['DateCreated']):
        return 'desired', series_id
    raise RuntimeError('Item date changed to an unknown value; stop and investigate')


def set_date(api, entry, reverse=False):
    old = entry['DateCreated'] if reverse else entry['ExpectedDateCreated']
    new = entry['ExpectedDateCreated'] if reverse else entry['DateCreated']
    api.call('/Habibi/LibraryImportDate/' + entry['id'], data={
        'ExpectedPath': entry['ExpectedPath'], 'ExpectedDateCreated': old, 'DateCreated': new})


def row_state(api, row, journal, journal_path):
    entry = row['entry']
    recorded = row.get('series_id')
    if recorded is not None and (entry['type'] != 'Episode'
                                 or not isinstance(recorded, str)
                                 or not re.fullmatch(r'[0-9a-f]{32}', recorded, re.I)):
        raise ValueError('Journal contains an invalid parent series identity')
    state, series_id = item_state(api, entry, recorded)
    if series_id is not None and recorded is None:
        # Persist the authenticated current relationship before any item mutation.
        row['series_id'] = series_id
        replace_private_json(journal_path, journal)
    return state, series_id


def add_pending_series(journal, series_id):
    if series_id is None:
        return False
    pending = journal.setdefault('pending_series_refresh', [])
    if series_id in pending:
        return False
    pending.append(series_id)
    pending.sort()
    return True


def refresh_pending_series(api, journal, journal_path, validated_series=None):
    pending = journal.get('pending_series_refresh', [])
    if not isinstance(pending, list) or any(
            not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value, re.I)
            for value in pending):
        raise ValueError('Journal contains invalid pending series refresh identities')
    pending = [value.lower() for value in pending]
    if len(set(pending)) != len(pending):
        raise ValueError('Journal contains duplicate pending series refresh identities')
    journal['pending_series_refresh'] = pending
    validated = set(validated_series or ())

    # A journal field alone is not authority to change a parent. Revalidate that
    # every pending ID is the current parent of an exact Episode in this plan.
    for series_id in pending:
        if series_id in validated:
            continue
        candidate = next((row for row in journal['rows']
                          if isinstance(row.get('series_id'), str)
                          and row['series_id'].lower() == series_id
                          and row['entry']['type'] == 'Episode'), None)
        if candidate is None:
            raise ValueError('Pending refresh is unrelated to an Episode in the repair plan')
        _, actual = item_state(api, candidate['entry'], series_id)
        if actual != series_id:
            raise RuntimeError('Episode parent series changed; stop and investigate')
        validated.add(series_id)

    while journal['pending_series_refresh']:
        batch = journal['pending_series_refresh'][:500]
        result = api.call('/Habibi/LibraryImportDate/RefreshLatestDates',
                          data={'SeriesIds': batch})
        if not isinstance(result, dict):
            raise RuntimeError('Series latest-date refresh returned no verified result')
        updated = result.get('updatedSeries', result.get('UpdatedSeries'))
        if updated != len(batch):
            raise RuntimeError('Series latest-date refresh count mismatch')
        journal['pending_series_refresh'] = journal['pending_series_refresh'][len(batch):]
        replace_private_json(journal_path, journal)


def migrate_series_refresh_journal(api, journal, journal_path):
    if journal.get('series_refresh_schema') == 1:
        return
    if journal.get('series_refresh_schema') is not None:
        raise ValueError('Unsupported series refresh journal schema')
    # Old journals predate derived-parent tracking. Any row that may have been
    # changed is conservatively recomputed from its current exact Episode parent.
    for row in journal['rows']:
        if row.get('state') not in ('attempting', 'applied', 'rolling_back', 'rolled_back'):
            continue
        _, series_id = row_state(api, row, journal, journal_path)
        add_pending_series(journal, series_id)
    journal['series_refresh_schema'] = 1
    journal.setdefault('pending_series_refresh', [])
    replace_private_json(journal_path, journal)


def journaled_repair(api, plan, journal_path, resume=False, rollback=False):
    journal_path = Path(journal_path)
    if journal_path.is_symlink():
        raise ValueError('Refusing symlinked journal')
    validate_plan(plan)
    if rollback or resume:
        journal = json.loads(journal_path.read_text())
        if journal.get('schema') != 1 or journal.get('plan_sha256') != plan_digest(plan):
            raise ValueError('Journal does not match the requested plan')
    else:
        journal = {'schema': 1, 'plan_sha256': plan_digest(plan),
                   'plan': plan, 'series_refresh_schema': 1,
                   'pending_series_refresh': [],
                   'rows': [{'entry': entry, 'state': 'planned'} for entry in plan['repairs']]}
        private_json(journal_path, journal)
    rows = journal['rows']
    if len(rows) != len(plan['repairs']) or any(row.get('entry') != entry for row, entry in zip(rows, plan['repairs'])):
        raise ValueError('Journal rows do not match the requested plan')
    migrate_series_refresh_journal(api, journal, journal_path)
    # Finish any batch whose item writes were interrupted before doing more work.
    refresh_pending_series(api, journal, journal_path)
    count = 0
    sequence = reversed(rows) if rollback else rows
    for row in sequence:
        entry = row['entry']
        state = row.get('state')
        if rollback:
            if state not in ('applied', 'attempting', 'rolling_back'):
                continue
            current, series_id = row_state(api, row, journal, journal_path)
            if current == 'desired':
                row['state'] = 'rolling_back'
                add_pending_series(journal, series_id)
                replace_private_json(journal_path, journal)
                set_date(api, entry, reverse=True)
                if item_state(api, entry, series_id)[0] != 'old':
                    raise RuntimeError('Rollback readback mismatch; stop and investigate')
            row['state'] = 'rolled_back'
            replace_private_json(journal_path, journal)
            count += 1
            continue
        if state == 'already_desired':
            if row_state(api, row, journal, journal_path)[0] != 'desired':
                raise RuntimeError('Previously desired date is no longer present')
            continue
        if state not in ('planned', 'attempting', 'applied'):
            raise ValueError('Journal contains a state that cannot be applied')
        current, series_id = row_state(api, row, journal, journal_path)
        if current == 'desired':
            row['state'] = 'applied' if state in ('attempting', 'applied') else 'already_desired'
            replace_private_json(journal_path, journal)
            continue
        if state == 'applied':
            raise RuntimeError('Previously applied date is no longer present')
        row['state'] = 'attempting'
        add_pending_series(journal, series_id)
        replace_private_json(journal_path, journal)
        set_date(api, entry)
        if item_state(api, entry, series_id)[0] != 'desired':
            raise RuntimeError('Apply readback mismatch; stop and investigate')
        row['state'] = 'applied'
        replace_private_json(journal_path, journal)
        count += 1
    refresh_pending_series(api, journal, journal_path)
    return count


class Api:
    def __init__(self, base, key_file):
        self.base = base.rstrip('/')
        self.key = Path(key_file).read_text().strip()

    def call(self, route, query=None, data=None):
        url = self.base + route
        if query:
            url += '?' + urllib.parse.urlencode(query)
        request = urllib.request.Request(url, headers={'Authorization': 'MediaBrowser Token="' + self.key + '"'})
        if data is not None:
            request.data = json.dumps(data).encode()
            request.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
        return json.loads(raw) if raw else None


def index_imports(document):
    index = {}
    conflicts = set()
    now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
    for row in document['files']:
        date = timestamp(row['date'])
        if date.year < 2000 or date > now:
            continue
        for key in (row['path'], row.get('realpath')):
            if not key or not os.path.isabs(key):
                continue
            if key in index and timestamp(index[key]['date']) != date:
                conflicts.add(key)
            index[key] = row
    return {key: row for key, row in index.items() if key not in conflicts}


def repair_entry(item, index):
    path = item.get('Path') or ''
    if not os.path.isabs(path) or Path(path).suffix.lower() == '.strm':
        return None
    # Only resolve existing paths on the media host; do not infer by title/basename.
    source = index.get(path)
    if source is None and Path(path).is_file():
        source = index.get(str(Path(path).resolve()))
    if not source or not item.get('DateCreated'):
        return None
    if abs((timestamp(item['DateCreated']) - timestamp(source['date'])).total_seconds()) < 1:
        return None
    return {'id': item['Id'], 'type': item['Type'], 'source': source['source'],
            'ExpectedPath': path, 'ExpectedDateCreated': item['DateCreated'],
            'DateCreated': timestamp(source['date']).isoformat().replace('+00:00', 'Z')}


def plan(api, imports):
    index = index_imports(imports)
    repairs, seen = [], set()
    counts = {'items': 0, 'exact_path_matches': 0}
    for library in api.call('/Library/VirtualFolders'):
        if 'venom' in library.get('Name', '').casefold():
            continue
        if library.get('CollectionType') not in (None, '', 'movies', 'tvshows'):
            continue
        parent = library.get('ItemId')
        if not parent:
            continue
        offset = 0
        while True:
            response = api.call('/Items', {'ParentId': parent, 'Recursive': 'true',
                'IncludeItemTypes': 'Movie,Episode', 'Fields': 'Path,DateCreated',
                'SortBy': 'SortName', 'SortOrder': 'Ascending', 'StartIndex': offset,
                'Limit': 500, 'EnableTotalRecordCount': 'true'})
            items = response.get('Items', [])
            for item in items:
                if item['Id'] in seen:
                    continue
                seen.add(item['Id'])
                counts['items'] += 1
                path = item.get('Path', '')
                if path in index or (path and Path(path).is_file() and str(Path(path).resolve()) in index):
                    counts['exact_path_matches'] += 1
                entry = repair_entry(item, index)
                if entry:
                    repairs.append(entry)
            offset += len(items)
            if not items or offset >= response.get('TotalRecordCount', offset):
                break
            if offset > 100000:
                raise RuntimeError('Refusing unbounded library scan')
    return {'schema': 1, 'counts': counts, 'repairs': repairs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--key-file', required=True, type=Path)
    parser.add_argument('--imports', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume', action='store_true', help='Continue an interrupted apply using --backup journal')
    parser.add_argument('--rollback', action='store_true', help='Reverse journaled changes with fresh item checks')
    parser.add_argument('--set-import-policy', action='store_true')
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    api = Api(args.url, args.key_file)
    if args.rollback:
        if args.apply or args.resume or not args.backup:
            parser.error('--rollback requires --backup and cannot combine with --apply/--resume')
        journal = json.loads(args.backup.read_text())
        plan_data = journal.get('plan')
        if not isinstance(plan_data, dict):
            raise ValueError('Rollback journal has no saved plan')
        lock_path = Path(str(args.backup) + '.lock')
        fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            reversed_count = journaled_repair(api, plan_data, args.backup, rollback=True)
        print(json.dumps({'rolled_back': reversed_count, 'journal': str(args.backup)}))
        return
    if args.set_import_policy:
        current = api.call('/System/Configuration/metadata')
        if current.get('UseFileCreationTimeForDateAdded') is False:
            print('Import-date policy already active')
            return
        if not args.apply:
            print('Plan: UseFileCreationTimeForDateAdded=false (only this configuration field)')
            return
        if not args.backup:
            parser.error('--backup is required')
        private_json(args.backup, current)
        if api.call('/System/Configuration/metadata') != current:
            raise RuntimeError('Metadata configuration changed after backup; no update sent')
        changed = dict(current, UseFileCreationTimeForDateAdded=False)
        api.call('/System/Configuration/metadata', data=changed)
        if api.call('/System/Configuration/metadata') != changed:
            raise RuntimeError('Metadata configuration readback mismatch; inspect before retry')
        print('Import-date policy applied and verified')
        return
    if not args.plan:
        parser.error('--plan is required')
    if args.resume and not args.apply:
        parser.error('--resume requires --apply')
    if not args.apply:
        if not args.imports:
            parser.error('--imports is required to create a plan')
        result = plan(api, json.loads(args.imports.read_text()))
        private_json(args.plan, result)
        print(json.dumps(dict(result['counts'], repairs=len(result['repairs']))))
        return
    if not args.backup:
        parser.error('--backup is required for the private apply journal')
    result = json.loads(args.plan.read_text())
    lock_path = Path(str(args.backup) + '.lock')
    fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        applied = journaled_repair(api, result, args.backup, resume=args.resume)
    print(json.dumps({'applied': applied, 'journal': str(args.backup)}))


if __name__ == '__main__':
    main()
