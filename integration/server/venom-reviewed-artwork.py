"""Repair reviewed Venom artwork without claiming a manually supplied image.

The pending intent is written before an image POST. If the process dies after
Jellyfin accepts that POST but before its ledger is durable, a later run can
prove ownership by comparing unresized Primary bytes to the source digest.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import runpy
import struct
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path('/data/config/iptv-venom')
HERE = Path(__file__).resolve().parent
_clean_name = runpy.run_path(str(HERE / 'venom-channel-names.py'))['clean_name']
MAX_IMAGE_BYTES = 4 * 1024 * 1024


def key(name):
    name = _clean_name(name)
    name = re.sub(r'^(MBC|OSN)\s*[:.]\s*', r'\1 ', name, flags=re.I)
    name = re.sub(r'\s*· BACKUP.*$', '', name.upper())
    name = re.sub(r'\[NOT 24/7\]|\(\d{3,4}P\)', ' ', name)
    name = re.sub(r'(?<!\w)(?:[468]K|UHD|FHD|HDF|HD|SD|1080P|720P|50FPS)(?!\w)\.?\+?', ' ', name)
    return re.sub(r'\s+', ' ', name).strip(' /')


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path: Path, value: Any, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_bytes(path: Path, value: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def checked_image(data: bytes) -> tuple[bytes, str]:
    if not (100 < len(data) <= MAX_IMAGE_BYTES):
        raise ValueError('not a bounded PNG/JPEG')
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        if len(data) < 24:
            raise ValueError('truncated PNG')
        width, height = struct.unpack('>II', data[16:24])
        if not (16 <= width <= 8192 and 16 <= height <= 8192):
            raise ValueError('invalid PNG dimensions')
        return data, 'image/png'
    if data.startswith(b'\xff\xd8\xff'):
        return data, 'image/jpeg'
    raise ValueError('not a bounded PNG/JPEG')


def _cache_path(cache: Path, url: str) -> Path:
    return cache / (hashlib.sha256(url.encode('utf-8')).hexdigest() + '.image')


def pending_source(intent: dict[str, Any], cache: Path) -> tuple[bytes, str]:
    required = ('url', 'source_sha256', 'source_bytes', 'mime', 'gateway_id', 'station', 'name', 'kind')
    if not isinstance(intent, dict) or any(field not in intent for field in required):
        raise ValueError('incomplete pending intent')
    data, mime = checked_image(_cache_path(cache, intent['url']).read_bytes())
    if mime != intent['mime'] or len(data) != intent['source_bytes'] or hashlib.sha256(data).hexdigest() != intent['source_sha256']:
        raise ValueError('pending source digest mismatch')
    return data, mime


def ledger_entry(intent: dict[str, Any]) -> dict[str, Any]:
    return {field: intent[field] for field in ('gateway_id', 'station', 'url', 'name', 'kind', 'source_sha256', 'source_bytes')}


def bind_readiness_origin(base: str, readiness_url: str, readiness_loader=runpy.run_path) -> None:
    """Fail closed unless authenticated requests use the probed exact origin."""
    readiness = readiness_loader(str(HERE / 'venom-jellyfin-readiness.py'))
    readiness['require_matching_admin_origin'](readiness_url, base)


def reconcile_pending(iid: str, pending: dict[str, dict[str, Any]], ledger: dict[str, Any], *, cache: Path,
                      request: Callable[..., bytes], ledger_path: Path, pending_path: Path, persist: bool) -> str:
    """Promote only a byte-identical accepted upload; leave manual art intact."""
    intent = pending[iid]
    data, _mime = pending_source(intent, cache)
    try:
        native = request(f'/Items/{iid}/Images/Primary')
    except urllib.error.HTTPError as exc:
        try:
            if exc.code != 404:
                return 'pending-check-failed'
            return 'pending-no-primary'
        finally:
            exc.close()
    except Exception:
        return 'pending-check-failed'
    if len(native) != len(data) or hashlib.sha256(native).hexdigest() != hashlib.sha256(data).hexdigest():
        return 'pending-primary-mismatch'
    if not persist:
        return 'pending-would-promote'
    ledger[iid] = ledger_entry(intent)
    # A crash here leaves a pending intent. The next run repeats this idempotent
    # ledger write and removes the intent without another image POST.
    atomic_json(ledger_path, ledger)
    del pending[iid]
    atomic_json(pending_path, pending)
    return 'pending-promoted'


def fetch_source(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'PersonalChannelArtwork/1.0'}), timeout=12) as response:
        return response.read(MAX_IMAGE_BYTES + 1)


def build_intent(item: dict[str, Any], match: dict[str, Any], gateway_id: Any, data: bytes, mime: str) -> dict[str, Any]:
    return {'gateway_id': gateway_id, 'station': match['channel'], 'url': match['url'], 'name': item['Name'],
            'kind': match.get('kind', 'station-logo'), 'source_sha256': hashlib.sha256(data).hexdigest(),
            'source_bytes': len(data), 'mime': mime}


def primary_state(iid: str, request: Callable[..., bytes]) -> str:
    """Return present/missing; all non-404 failures remain hard errors."""
    try:
        request(f'/Items/{iid}/Images/Primary')
    except urllib.error.HTTPError as exc:
        try:
            if exc.code == 404:
                return 'missing'
            raise RuntimeError(f'primary-http-{exc.code}') from exc
        finally:
            exc.close()
    except Exception as exc:
        raise RuntimeError('primary-check-failed') from exc
    return 'present'


def process_items(items: list[dict[str, Any]], *, mapping: dict[str, Any], scopes: dict[str, str], ids: dict[str, Any],
                  cache: Path, ledger: dict[str, Any], pending: dict[str, dict[str, Any]], ledger_path: Path,
                  pending_path: Path, request: Callable[..., bytes], download: Callable[[str], bytes], apply: bool,
                  missing_only: bool, limit: int) -> dict[str, Any]:
    count = preserved = unmatched = 0
    errors: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    unavailable: set[str] = set()
    for item in items:
        iid = item['Id']
        match = mapping.get(scopes[iid] + ':' + key(item['Name'])) or mapping.get(key(item['Name']))
        # Pending reconciliation is deliberately before normal Primary preserve.
        if iid in pending:
            try:
                intent = pending[iid]
                if not match or any((intent.get('gateway_id') != ids[iid], intent.get('station') != match.get('channel'),
                                     intent.get('url') != match.get('url'), intent.get('name') != item['Name'],
                                     intent.get('kind') != match.get('kind', 'station-logo'))):
                    errors.append({'name': item['Name'], 'error': 'pending-intent-mismatch'})
                    continue
                state = reconcile_pending(iid, pending, ledger, cache=cache, request=request,
                                          ledger_path=ledger_path, pending_path=pending_path, persist=apply)
                if state == 'pending-no-primary' and apply:
                    # A durable intent can survive a crash before POST. A
                    # confirmed native 404 is the only state that safely
                    # permits resuming it; transport/5xx failures stay pending.
                    data, mime = pending_source(intent, cache)
                    request(f'/Items/{iid}/Images/Primary', base64.b64encode(data), mime)
                    state = reconcile_pending(iid, pending, ledger, cache=cache, request=request,
                                              ledger_path=ledger_path, pending_path=pending_path, persist=True)
                successful_states = {'pending-promoted'} if apply else {'pending-would-promote', 'pending-no-primary'}
                if state in successful_states:
                    count += 1
                else:
                    errors.append({'name': item['Name'], 'error': state})
                continue
            except Exception as exc:
                errors.append({'name': item['Name'], 'error': f'pending-{type(exc).__name__}'})
                continue
        if not match:
            unmatched += 1
            missing.append({'id': iid, 'name': item['Name'], 'scope': scopes[iid]})
            continue
        if count >= limit:
            break
        try:
            # ImageTags is advisory and may be stale. A native HTTP 200 always
            # preserves the current Primary; only an authoritative exact 404
            # authorizes a new upload. Transport and 5xx failures never do.
            if primary_state(iid, request) == 'present':
                preserved += 1
                continue
        except Exception as exc:
            errors.append({'name': item['Name'], 'error': type(exc).__name__})
            continue
        if not apply:
            count += 1
            continue
        try:
            url = match['url']
            if url in unavailable:
                raise RuntimeError('source_unavailable_this_pass')
            location = _cache_path(cache, url)
            if location.exists():
                data, mime = checked_image(location.read_bytes())
            else:
                try:
                    data, mime = checked_image(download(url))
                    atomic_bytes(location, data)
                except Exception:
                    unavailable.add(url)
                    raise
            intent = build_intent(item, match, ids[iid], data, mime)
            pending[iid] = intent
            # This durable intent always precedes the mutating Jellyfin POST.
            atomic_json(pending_path, pending)
            request(f'/Items/{iid}/Images/Primary', base64.b64encode(data), mime)
            state = reconcile_pending(iid, pending, ledger, cache=cache, request=request,
                                      ledger_path=ledger_path, pending_path=pending_path, persist=True)
            if state != 'pending-promoted':
                raise RuntimeError(state)
            count += 1
        except Exception as exc:
            errors.append({'name': item['Name'], 'error': type(exc).__name__})
    return {'repaired' if apply else 'planned': count, 'preserved': preserved, 'unmatched': unmatched,
            'errors': errors, 'missing': missing}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--limit', type=int, default=250)
    parser.add_argument('--missing-only', action='store_true')
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error('--limit must be non-negative')
    # Must happen before lock/cache/report/pending/ledger writes.
    helper = runpy.run_path('/root/iptv-jellyfin-admin.py')
    base = helper['BASE']
    bind_readiness_origin(base, os.environ.get('VENOM_JELLYFIN_READINESS_URL', ''))
    lock = (ROOT / 'reviewed-artwork.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    token = (ROOT / 'jellyfin-api-key').read_text().strip()
    headers = {'Authorization': 'MediaBrowser Token="' + token + '"'}

    def request(path: str, data: bytes | None = None, mime: str | None = None) -> bytes:
        request_headers = dict(headers)
        if mime:
            request_headers['Content-Type'] = mime
        with urllib.request.urlopen(urllib.request.Request(base + path, data=data, headers=request_headers), timeout=15) as response:
            return response.read(MAX_IMAGE_BYTES + 1)

    mapping = json.loads((ROOT / 'venom-reviewed-artwork.json').read_text())
    native = json.loads((ROOT / 'curated-native-channels.json').read_text())
    ids = {channel['id']: channel['gateway_id'] for group in native['groups'] for channel in group['channels']}
    scopes: dict[str, str] = {}
    for group in native['groups']:
        for channel in group['channels']:
            scopes.setdefault(channel['id'], 'AR' if group['id'].startswith('ar-') else 'CA' if group['id'] == 'en-canada' else 'EN')
    catalogue = json.loads((ROOT / 'live-catalogue-redacted.json').read_text())
    categories = {str(category['category_id']): category['category_name'] for category in catalogue['categories']}
    source = {str(channel['stream_id']): channel for channel in catalogue['channels']}
    language = runpy.run_path(str(ROOT / 'venom-sports-entertainment.py'))['language']
    for iid, gateway_id in ids.items():
        channel = source.get(str(gateway_id), {})
        detected = language(channel.get('name', ''), categories.get(str(channel.get('category_id')), ''))
        if detected and scopes[iid] != 'CA':
            scopes[iid] = 'AR' if detected == 'ar' else 'EN'
    uid = next(user['Id'] for user in helper['api']('/Users') if user['Name'].lower() == 'habibi')
    items: list[dict[str, Any]] = []
    keys = list(ids)
    for offset in range(0, len(keys), 80):
        items += helper['api']('/Users/' + uid + '/Items?' + urllib.parse.urlencode({'Ids': ','.join(keys[offset:offset + 80]), 'Limit': 80}))['Items']
    cache = ROOT / 'reviewed-logo-cache'
    ledger_path = ROOT / 'reviewed-artwork-applied.json'
    pending_path = ROOT / 'reviewed-artwork-pending.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    pending = json.loads(pending_path.read_text()) if pending_path.exists() else {}
    result = process_items(items, mapping=mapping, scopes=scopes, ids=ids, cache=cache, ledger=ledger, pending=pending,
                           ledger_path=ledger_path, pending_path=pending_path, request=request, download=fetch_source,
                           apply=args.apply, missing_only=args.missing_only, limit=args.limit)
    report = {'total': len(items), 'apply': args.apply, **result}
    atomic_json(ROOT / 'reviewed-artwork-report.json', report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    # 75 is reserved for a completed run with a durable report and per-item
    # errors. The service wrapper may publish successful ledger entries while
    # preserving this failure status for bounded systemd retry.
    code = 75 if result['errors'] else 0
    lock.close()
    return code


if __name__ == '__main__':
    raise SystemExit(main())
