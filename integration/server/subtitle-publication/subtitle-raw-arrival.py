#!/usr/bin/env python3
"""Durably publish a Bazarr/provider subtitle before optional AI processing.

The arrival command is intentionally tiny and local: it records the bytes that
arrived, then returns.  A timer runs ``work`` later, in small per-video groups.
Neither path starts a Jellyfin library scan nor sends a new-title notification.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import time
import urllib.parse
import urllib.request


def load(root, name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(root) / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT_DIR = Path(__file__).parent


def fingerprint(path):
    data = Path(path).read_bytes()
    if not data.strip():
        raise ValueError('empty provider subtitle')
    return hashlib.sha256(data).hexdigest()


def connect(root):
    queue = load(SCRIPT_DIR, 'subtitle-publication-queue')
    db = queue.connect(root)
    db.execute('''CREATE TABLE IF NOT EXISTS raw_subtitle_arrivals(
      id INTEGER PRIMARY KEY AUTOINCREMENT, video TEXT NOT NULL, subtitle TEXT NOT NULL,
      fingerprint TEXT NOT NULL, revision TEXT NOT NULL, status TEXT NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0, first_seen REAL NOT NULL,
      available REAL NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0, updated REAL NOT NULL,
      detail TEXT NOT NULL DEFAULT '', UNIQUE(video, subtitle, fingerprint))''')
    columns = {row[1] for row in db.execute('PRAGMA table_info(raw_subtitle_arrivals)')}
    if 'next_attempt' not in columns:
        db.execute('ALTER TABLE raw_subtitle_arrivals ADD COLUMN next_attempt REAL NOT NULL DEFAULT 0')
        db.execute('UPDATE raw_subtitle_arrivals SET next_attempt=available WHERE next_attempt=0')
    db.execute('CREATE INDEX IF NOT EXISTS raw_subtitle_arrivals_due ON raw_subtitle_arrivals(status,available,video,id)')
    db.execute('CREATE TABLE IF NOT EXISTS raw_subtitle_current(video TEXT NOT NULL, subtitle TEXT NOT NULL, fingerprint TEXT NOT NULL, PRIMARY KEY(video,subtitle))')
    db.commit()
    return db, queue


def enqueue(root, video, subtitle, now=None, canonical='/data/media'):
    now = time.time() if now is None else now
    root, video, subtitle = Path(root), os.path.abspath(video), os.path.abspath(subtitle)
    if not Path(video).is_file() or not Path(subtitle).is_file():
        raise ValueError('arrival video and subtitle must both exist')
    if not allowed_sidecar(video, subtitle, canonical):
        raise ValueError('arrival is not an allowed canonical provider sidecar')
    digest = fingerprint(subtitle)
    # Revision includes the path and content.  Repeated identical provider
    # events retain their retry budget; changed bytes create a new revision.
    revision = hashlib.sha256((video + '\0' + subtitle + '\0' + digest).encode()).hexdigest()
    db, _ = connect(root)
    try:
        with db:
            previous = db.execute('SELECT fingerprint FROM raw_subtitle_current WHERE video=? AND subtitle=?', (video, subtitle)).fetchone()
            db.execute('''INSERT INTO raw_subtitle_arrivals(video,subtitle,fingerprint,revision,status,first_seen,available,next_attempt,updated)
              VALUES(?,?,?,?, 'pending',?,?,?,?)
              ON CONFLICT(video,subtitle,fingerprint) DO UPDATE SET updated=excluded.updated''',
              (video, subtitle, digest, revision, now, 0, 0, now))
            if previous and previous[0] != digest:
                db.execute("UPDATE raw_subtitle_arrivals SET status='pending',attempts=0,available=0,next_attempt=0,first_seen=?,updated=?,detail='provider bytes changed; reactivated' WHERE video=? AND subtitle=? AND fingerprint=?",
                           (now, now, video, subtitle, digest))
            db.execute('INSERT INTO raw_subtitle_current VALUES(?,?,?) ON CONFLICT(video,subtitle) DO UPDATE SET fingerprint=excluded.fingerprint', (video, subtitle, digest))
    finally:
        db.close()
    return revision


def allowed_sidecar(video, subtitle, canonical):
    video, subtitle, canonical = Path(video), Path(subtitle), Path(canonical)
    try:
        relative_video = video.relative_to(canonical)
        subtitle.relative_to(canonical)
    except ValueError:
        return False
    return (relative_video.parts and relative_video.parts[0] in ('shows', 'movies') and
            subtitle.parent == video.parent and subtitle.suffix.lower() == '.srt' and
            subtitle.name.startswith(video.stem + '.') and subtitle.is_file() and not subtitle.is_symlink() and
            canonical.resolve() in subtitle.resolve().parents and canonical.resolve() in video.resolve().parents)


def link_allowed_sidecar(video, subtitle, canonical, view):
    """Atomically expose only an allow-listed provider sidecar in the view."""
    video, subtitle, canonical, view = map(Path, (video, subtitle, canonical, view))
    if not allowed_sidecar(video, subtitle, canonical):
        raise ValueError('provider subtitle is not an allowed canonical sidecar')
    target_video = view / video.relative_to(canonical)
    target = view / subtitle.relative_to(canonical)
    if target_video.is_symlink() or target.is_symlink():
        raise ValueError('compatibility target may not be a symlink')
    if not target_video.is_file():
        raise load(SCRIPT_DIR, 'subtitle-publication-queue').ViewPending('compatibility video pending')
    before = fingerprint(subtitle)
    if target.exists() and fingerprint(target) == before:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / ('.subtitle-arrival-' + hashlib.sha256(str(target).encode()).hexdigest())
    try:
        try:
            os.link(subtitle, temporary)
        except OSError:
            shutil.copyfile(subtitle, temporary)
        if fingerprint(subtitle) != before or fingerprint(temporary) != before:
            raise RuntimeError('provider subtitle changed while linking view')
        # This deterministic view path is derived from the verified canonical
        # sidecar; replacing its old inode is the normal Bazarr atomic update.
        if target.is_symlink(): raise ValueError('compatibility target became a symlink')
        os.replace(temporary, target)
        return target
    finally:
        if temporary.exists():
            temporary.unlink()


def view_paths(video, subtitle, canonical='/data/media', view='/data/media/compatibility/jellyfin-view'):
    """Prepare host view files but return Jellyfin's canonical bind paths."""
    video, subtitle = Path(video), Path(subtitle)
    try:
        relative_video = video.relative_to(canonical)
        relative_subtitle = subtitle.relative_to(canonical)
    except ValueError:
        raise ValueError('provider subtitle is outside the canonical media roots')
    view = Path(view)
    if not view.is_dir():
        raise load(SCRIPT_DIR, 'subtitle-publication-queue').ViewPending('compatibility view root pending')
    policy = load(SCRIPT_DIR, 'subtitle-view-filter')
    hidden = policy.hidden_sources(video.with_suffix('.subengine.json'))
    retired = policy.retired_sources(video.with_suffix('.subengine.json'))
    if str(subtitle) in hidden or str(subtitle) in retired:
        raise RuntimeError('provider subtitle superseded by verified managed manifest')
    link_allowed_sidecar(video, subtitle, canonical, view)
    # CT102 bind-mounts the host view at its canonical /data/media path.
    return str(video), str(subtitle)


def config_request(root):
    config = (Path(root) / 'post-sub.sh').read_text()
    url = re.search(r'JELLYFIN_URL="([^"]+)"', config)[1]
    token = re.search(r'JELLYFIN_KEY="([^"]+)"', config)[1]
    def request(path, method='GET'):
        req = urllib.request.Request(url.rstrip('/') + path, method=method,
            data=b'' if method == 'POST' else None,
            headers={'Authorization': 'MediaBrowser Token="' + token + '"'})
        with urllib.request.urlopen(req, timeout=8) as response:
            return response.read()
    return url, token, request


def served_exact(request, item_id, video, subtitle, expected):
    if fingerprint(subtitle) != expected:
        return False
    payload = json.loads(request('/Items?Ids=' + urllib.parse.quote(item_id, safe='') +
                                 '&Fields=Path,MediaStreams,MediaSources'))
    items = payload.get('Items', [])
    if len(items) != 1 or items[0].get('Path') != video or not items[0].get('MediaSources'):
        return False
    streams = [stream for stream in items[0].get('MediaStreams', [])
               if stream.get('Type') == 'Subtitle' and stream.get('IsExternal') and stream.get('Path') == subtitle]
    if len(streams) != 1:
        return False
    source = urllib.parse.quote(items[0]['MediaSources'][0]['Id'], safe='')
    served = request('/Videos/' + urllib.parse.quote(item_id, safe='') + '/' + source +
                     '/Subtitles/' + str(streams[0]['Index']) + '/Stream.srt')
    # Jellyfin may normalize BOM/line endings when serving an SRT.  Use the
    # same canonical cue comparison as the managed verifier, not raw bytes.
    sync = load(SCRIPT_DIR, 'subtitle-jellyfin-sync')
    return fingerprint(subtitle) == expected and sync.normalized(served) == sync.normalized(Path(subtitle).read_bytes())


def work(root, limit=3, canonical='/data/media', view='/data/media/compatibility/jellyfin-view'):
    root = Path(root)
    # Serialize raw and managed publication: both refresh the same exact item.
    with (root / '.jellyfin-publication.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        db, queue = connect(root)
        try:
            if queue.circuit_open(db): return
            _, _, request = config_request(root)
            rows = db.execute("SELECT * FROM raw_subtitle_arrivals WHERE status='pending' AND available<=? "
                              "ORDER BY video,id LIMIT ?", (time.time(), limit)).fetchall()
            seen = set()
            for row in rows:
                if row['video'] in seen: continue
                seen.add(row['video'])
                try:
                    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('raw publication attempt timed out')))
                    signal.alarm(90)
                    if queue.expire_if_aged(db, 'raw_subtitle_arrivals', 'id', row['id'], row['first_seen'], row['revision']):
                        continue
                    if not Path(row['video']).is_file() or not Path(row['subtitle']).is_file():
                        raise FileNotFoundError('arrival input removed')
                    if fingerprint(row['subtitle']) != row['fingerprint']:
                        raise RuntimeError('provider subtitle bytes changed')
                    item_video, item_subtitle = view_paths(row['video'], row['subtitle'], canonical, view)
                    item_id = queue.resolve(db, item_video, request)
                    # Share the per-item cooldown with managed publication.
                    if queue.hint_due(db, 'item:' + item_id):
                        request('/Items/' + urllib.parse.quote(item_id, safe='') +
                                '/Refresh?MetadataRefreshMode=Default&ImageRefreshMode=None&ReplaceAllMetadata=false'
                                '&ReplaceAllImages=false&RegenerateTrickplay=false', 'POST')
                        queue.record_hint(db, 'item:' + item_id)
                    if not served_exact(request, item_id, item_video, item_subtitle, row['fingerprint']):
                        if fingerprint(row['subtitle']) != row['fingerprint']:
                            raise RuntimeError('provider subtitle bytes changed')
                        raise queue.LookupPending('exact raw subtitle not served yet')
                    with db:
                        db.execute("UPDATE raw_subtitle_arrivals SET status='complete',updated=?,detail=? WHERE id=? AND revision=?",
                                   (time.time(), 'exact item refresh and served SRT content verified', row['id'], row['revision']))
                except RuntimeError as error:
                    if str(error) == 'provider subtitle bytes changed':
                        with db: db.execute("UPDATE raw_subtitle_arrivals SET status='superseded',updated=?,detail='provider bytes changed; newer arrival required' WHERE id=?", (time.time(), row['id']))
                        continue
                    if str(error) == 'provider subtitle superseded by verified managed manifest':
                        with db: db.execute("UPDATE raw_subtitle_arrivals SET status='superseded',updated=?,detail=? WHERE id=?",
                                            (time.time(), 'managed manifest hides provider source', row['id']))
                        continue
                    status, _ = queue.defer(db, 'raw_subtitle_arrivals', 'id', row['id'], row['attempts'], row['first_seen'], error, 'raw: ', row['revision'])
                    print('raw publication ' + status, row['subtitle'], type(error).__name__, flush=True)
                except Exception as error:
                    status, _ = queue.defer(db, 'raw_subtitle_arrivals', 'id', row['id'], row['attempts'], row['first_seen'], error, 'raw: ', row['revision'])
                    print('raw publication ' + status, row['subtitle'], type(error).__name__, flush=True)
                    if queue.transport_error(error): break
                finally:
                    signal.alarm(0)
        finally:
            db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('arrival', 'work', 'status'))
    parser.add_argument('video', nargs='?')
    parser.add_argument('subtitle', nargs='?')
    parser.add_argument('--root', default='/config/scripts')
    parser.add_argument('--canonical', default='/data/media')
    parser.add_argument('--view', default='/data/media/compatibility/jellyfin-view')
    parser.add_argument('--limit', type=int, default=3)
    args = parser.parse_args()
    if args.action == 'arrival':
        if not args.video or not args.subtitle:
            parser.error('arrival requires VIDEO SUBTITLE')
        print(enqueue(args.root, args.video, args.subtitle, canonical=args.canonical))
    elif args.action == 'work':
        work(args.root, max(1, min(args.limit, 3)), args.canonical, args.view)
    else:
        db, _ = connect(args.root)
        try:
            print(json.dumps([dict(row) for row in db.execute('SELECT status,count(*) AS count FROM raw_subtitle_arrivals GROUP BY status')]))
        finally: db.close()


if __name__ == '__main__':
    main()
