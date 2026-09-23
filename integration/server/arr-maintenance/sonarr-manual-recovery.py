#!/usr/bin/env python3
"""Bounded, fail-closed Sonarr manual-import recovery for completed SAB downloads."""
import argparse
import configparser
import datetime as dt
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


ROOT = Path('/data/downloads/usenet/complete/tv')
WARNING = 'matched to series by ID. Automatic import is not possible'


def private_json(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def replace_json(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + '.new')
    private_json(temporary, data)
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def api(base, key, route, body=None, timeout=15):
    headers = {'X-Api-Key': key}
    data = None
    if body is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(body).encode()
    req = urllib.request.Request(base.rstrip('/') + '/api/v3/' + route, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def sab_history(base, key):
    query = urllib.parse.urlencode({'mode': 'history', 'output': 'json', 'limit': 500, 'apikey': key})
    with urllib.request.urlopen(base.rstrip('/') + '/api?' + query, timeout=20) as response:
        data = json.load(response)
    rows = data['history']['slots']
    if not isinstance(rows, list) or len(rows) > 500:
        raise ValueError('SAB history exceeds bound')
    return {row['nzo_id']: row for row in rows}


def read_keys(sonarr_config, sab_config):
    sonarr_key = ET.parse(sonarr_config).findtext('ApiKey')
    # SAB begins with a few unsectioned metadata lines.
    sab = configparser.ConfigParser()
    sab.read_string('[DEFAULT]\n' + Path(sab_config).read_text())
    sab_key = sab['misc']['api_key']
    if not sonarr_key or not sab_key:
        raise ValueError('Missing private API key')
    return sonarr_key, sab_key


def warning_rows(sonarr):
    data = sonarr('queue?page=1&pageSize=200')
    if not isinstance(data.get('totalRecords'), int) or data['totalRecords'] > 200:
        raise ValueError('Sonarr queue exceeds bound')
    rows = data.get('records') or []
    if len(rows) != data['totalRecords']:
        raise ValueError('Incomplete Sonarr queue snapshot')
    groups = {}
    for row in rows:
        messages = [str(message) for group in row.get('statusMessages') or []
                    for message in group.get('messages') or []]
        if not any(WARNING.lower() in message.lower() for message in messages):
            continue
        download_id = row.get('downloadId')
        if not isinstance(download_id, str) or not download_id:
            continue
        groups.setdefault(download_id, []).append(row)
    return groups


def inside_root(path, root=ROOT):
    candidate = Path(path)
    if not candidate.is_absolute() or candidate.is_symlink():
        return False
    try:
        candidate.resolve(strict=True).relative_to(root.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def preview_package(sonarr, download_id, rows, slot, root=ROOT):
    if any(row.get('downloadClient') != 'SABnzbd' or row.get('status') != 'completed'
           or row.get('trackedDownloadStatus') != 'warning' for row in rows):
        return 'not-completed-sab-warning', []
    series_ids = {row.get('seriesId') for row in rows}
    if len(series_ids) != 1 or not isinstance(next(iter(series_ids)), int):
        return 'ambiguous-tracked-series', []
    if not slot or slot.get('status') != 'Completed' or slot.get('category') != 'tv':
        return 'missing-completed-tv-download', []
    storage = Path(slot.get('storage') or '')
    if not inside_root(storage, root):
        return 'unsafe-download-path', []
    folder = storage if storage.is_dir() else storage.parent
    if not inside_root(folder, root) or folder.resolve() == root.resolve():
        return 'unsafe-download-folder', []
    query = urllib.parse.urlencode({'folder': str(folder), 'downloadId': download_id,
                                    'filterExistingFiles': 'true'})
    candidates = sonarr('manualimport?' + query)
    if not isinstance(candidates, list) or not candidates or len(candidates) > 50:
        return 'empty-or-unbounded-preview', []
    if len(candidates) != len(rows):
        return 'preview-row-count-mismatch', []
    files, used_episodes, used_paths = [], set(), set()
    for candidate in candidates:
        path = candidate.get('path')
        series = candidate.get('series') or {}
        episodes = candidate.get('episodes') or []
        ids = [episode.get('id') for episode in episodes]
        if not isinstance(path, str) or not inside_root(path, root) or not Path(path).is_file() \
                or Path(path).resolve() == folder.resolve() or not Path(path).resolve().is_relative_to(folder.resolve()):
            return 'unsafe-preview-path', []
        if candidate.get('rejections'):
            return 'preview-rejection', []
        if series.get('id') not in series_ids or not ids or not all(isinstance(value, int) and value > 0 for value in ids):
            return 'missing-or-mismatched-episode', []
        if len(ids) != len(set(ids)) or used_episodes.intersection(ids) or path in used_paths:
            return 'duplicate-episode-or-path', []
        if any(episode.get('hasFile') or episode.get('episodeFileId') for episode in episodes):
            return 'target-already-has-file', []
        if not isinstance(candidate.get('quality'), dict) or not candidate.get('languages'):
            return 'missing-preview-quality-or-language', []
        used_episodes.update(ids)
        used_paths.add(path)
        files.append({'path': path, 'seriesId': series['id'], 'episodeIds': ids,
                      'quality': candidate['quality'], 'languages': candidate['languages'],
                      # Deliberately omit DownloadId from the mutation: Sonarr
                      # otherwise deletes the completed source and SAB history
                      # even in copy mode after a tracked manual import.
                      'releaseGroup': candidate.get('releaseGroup'),
                      'indexerFlags': candidate.get('indexerFlags') or 0,
                      'releaseType': candidate.get('releaseType')})
    return 'eligible', files


def verify_import(sonarr, files, command_id, started_at):
    command = sonarr('command/' + str(command_id))
    if command.get('status') != 'completed' or command.get('result') != 'successful':
        return False
    for file in files:
        if not Path(file['path']).is_file():
            return False
        for episode_id in file['episodeIds']:
            episode = sonarr('episode/' + str(episode_id))
            if episode.get('seriesId') != file['seriesId'] or not episode.get('episodeFileId'):
                return False
            episode_file = sonarr('episodefile/' + str(episode['episodeFileId']))
            if not Path(episode_file.get('path') or '').is_file():
                return False
    history = sonarr('history?page=1&pageSize=500&sortKey=date&sortDirection=descending')
    earliest = dt.datetime.fromisoformat(started_at.replace('Z', '+00:00')) - dt.timedelta(seconds=1)
    def after_start(row):
        try:
            return dt.datetime.fromisoformat(row['date'].replace('Z', '+00:00')) >= earliest
        except (KeyError, ValueError, AttributeError):
            return False
    for file in files:
        for episode_id in file['episodeIds']:
            if not any(row.get('episodeId') == episode_id and row.get('eventType') == 'downloadFolderImported'
                       and (row.get('data') or {}).get('droppedPath') == file['path']
                       and after_start(row)
                       for row in history.get('records') or []):
                return False
    return True


def run(sonarr, sab, audit_path, selected=(), apply=False, max_packages=10):
    if not 1 <= max_packages <= 10:
        raise ValueError('Maximum is 10 packages per run')
    groups = warning_rows(sonarr)
    choices = list(selected) if selected else sorted(groups)[:max_packages]
    if len(choices) > max_packages:
        raise ValueError('Selection exceeds per-run package limit')
    if len(choices) != len(set(choices)):
        raise ValueError('Duplicate package selection')
    if any(choice not in groups for choice in choices):
        raise ValueError('Selected download is no longer in the warning queue')
    history = sab()
    audit = {'schema': 1, 'mode': 'apply' if apply else 'dry-run', 'packages': []}
    private_json(audit_path, audit)
    for download_id in choices:
        state, files = preview_package(sonarr, download_id, groups[download_id], history.get(download_id))
        record = {'download_id': download_id, 'state': state,
                  'series_id': groups[download_id][0].get('seriesId'),
                  'file_count': len(files), 'episode_count': sum(len(f['episodeIds']) for f in files)}
        audit['packages'].append(record)
        replace_json(audit_path, audit)
        if not apply or state != 'eligible':
            continue
        # Journal before mutation. A lost response must never trigger an automatic retry.
        record['state'] = 'attempting'
        record['started_at'] = dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')
        replace_json(audit_path, audit)
        command = sonarr('command', {'name': 'ManualImport', 'importMode': 'copy', 'files': files})
        record['command_id'] = command.get('id')
        replace_json(audit_path, audit)
        for _ in range(12):
            if verify_import(sonarr, files, record['command_id'], record['started_at']):
                record['state'] = 'verified'
                break
            time.sleep(5)
        else:
            record['state'] = 'needs-manual-verification'
        replace_json(audit_path, audit)
        if record['state'] != 'verified':
            break
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sonarr-url', default='http://127.0.0.1:8989')
    parser.add_argument('--sab-url', default='http://127.0.0.1:8081')
    parser.add_argument('--sonarr-config', type=Path, default=Path('/data/config/sonarr/config.xml'))
    parser.add_argument('--sab-config', type=Path, default=Path('/data/config/sabnzbd/sabnzbd.ini'))
    parser.add_argument('--audit', required=True, type=Path)
    parser.add_argument('--download-id', action='append', default=[])
    parser.add_argument('--max-packages', type=int, default=10)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    sonarr_key, sab_key = read_keys(args.sonarr_config, args.sab_config)
    def call(route, body=None):
        return api(args.sonarr_url, sonarr_key, route, body)
    result = run(call, lambda: sab_history(args.sab_url, sab_key), args.audit,
                 args.download_id, args.apply, args.max_packages)
    counts = {}
    for row in result['packages']:
        counts[row['state']] = counts.get(row['state'], 0) + 1
    print(json.dumps({'packages': len(result['packages']), 'states': counts,
                      'audit': str(args.audit)}, sort_keys=True))


if __name__ == '__main__':
    main()
