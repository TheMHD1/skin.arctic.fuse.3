#!/usr/bin/env python3
"""Durable, single-consumer Jellyfin publication; never owns a GPU lock.

Generation commits a revision before dropping its retry marker. A revision is
acknowledged only after exact-path, subtitle-content and default-track checks.
SQLite compare-and-swap prevents an old verifier acknowledging newer output.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


class LookupPending(RuntimeError):
    """Jellyfin has not exposed an unambiguous physical item yet."""


class ViewPending(LookupPending):
    """Canonical video is intentionally not published in the compatibility view."""


# Bump this only when the on-disk series index's completeness semantics change.
# A prior implementation treated a Jellyfin response that omitted
# TotalRecordCount as an empty catalogue after page one, then recorded that
# partial scan as fresh.  Persisting the revision makes a corrected resolver
# rebuild that stale cache once while preserving the normal shared rate limit.
SERIES_INVENTORY_REVISION = 'exact-path-pagination-v2'
RETRY_DELAYS = (30, 120, 600, 1800, 7200, 21600, 43200)
MAX_AGE = 48 * 3600
MAX_ATTEMPTS = 8  # initial try plus all seven taper delays


def publication_delay(error, attempts):
    """Return a bounded retry delay without turning absent library items into a hot loop.

    A normal new import gets rapid initial visibility checks.  If Jellyfin has
    still not exposed its exact physical path, further polling cannot repair it
    and used to hammer the metadata API once a minute indefinitely.  Keep a
    finite, recoverable retry cadence; a changed subtitle revision still resets
    the row to immediate verification.
    """
    # One common finite policy applies to missing items, compatibility-view
    # timing and HTTP errors.  A changed revision is the only reset.
    return RETRY_DELAYS[min(attempts, len(RETRY_DELAYS) - 1)]


def load(root, name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(root)/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def connect(root):
    db = sqlite3.connect(Path(root)/'four-track-jobs.sqlite', timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=FULL')
    db.execute('''CREATE TABLE IF NOT EXISTS jellyfin_publications(
      video TEXT PRIMARY KEY, revision TEXT NOT NULL, signature TEXT NOT NULL,
      status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
      available REAL NOT NULL DEFAULT 0, updated REAL NOT NULL,
      first_seen REAL NOT NULL DEFAULT 0,
      next_attempt REAL NOT NULL DEFAULT 0,
      detail TEXT NOT NULL DEFAULT '')''')
    columns = {row[1] for row in db.execute('PRAGMA table_info(jellyfin_publications)')}
    if 'first_seen' not in columns:
        db.execute('ALTER TABLE jellyfin_publications ADD COLUMN first_seen REAL NOT NULL DEFAULT 0')
        db.execute('UPDATE jellyfin_publications SET first_seen=updated WHERE first_seen=0')
    if 'next_attempt' not in columns:
        db.execute('ALTER TABLE jellyfin_publications ADD COLUMN next_attempt REAL NOT NULL DEFAULT 0')
        db.execute('UPDATE jellyfin_publications SET next_attempt=available WHERE next_attempt=0')
    db.execute('''CREATE TABLE IF NOT EXISTS jellyfin_path_cache(
      video TEXT PRIMARY KEY, item_id TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS jellyfin_series_path_cache(
      path TEXT PRIMARY KEY, item_id TEXT NOT NULL, scanned REAL NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS jellyfin_series_inventory_state(
      id INTEGER PRIMARY KEY CHECK(id=1), scanned REAL NOT NULL,
      revision TEXT NOT NULL DEFAULT '')''')
    # Existing installations have the two-column form.  SQLite has no
    # portable ADD COLUMN IF NOT EXISTS, so inspect rather than masking a
    # migration error.  This is an additive, reversible schema change.
    columns = {row[1] for row in db.execute('PRAGMA table_info(jellyfin_series_inventory_state)')}
    if 'revision' not in columns:
        db.execute("ALTER TABLE jellyfin_series_inventory_state ADD COLUMN revision TEXT NOT NULL DEFAULT ''")
    db.execute('''CREATE TABLE IF NOT EXISTS jellyfin_refresh_hints(
      target TEXT PRIMARY KEY, sent REAL NOT NULL)''')
    # This state is deliberately local to the publication workers.  It prevents
    # one Jellyfin outage from fanning out into every due row; it never pauses,
    # resumes or starts Jellyfin scheduled tasks.
    db.execute('''CREATE TABLE IF NOT EXISTS jellyfin_publication_circuit(
      id INTEGER PRIMARY KEY CHECK(id=1), open_until REAL NOT NULL,
      detail TEXT NOT NULL DEFAULT '')''')
    db.commit()
    return db


def snapshot(video, root):
    key = hashlib.sha256(os.path.realpath(video).encode()).hexdigest()
    raw = (Path(root)/'four-track-state'/(key+'.json')).read_bytes()
    manifest = json.loads(raw)
    if manifest.get('status') != 'complete':
        raise RuntimeError('Cannot queue unfinished subtitle files')
    sig = load(root, 'subtitle-library-jobs').signature(video)
    revision = hashlib.sha256(raw + sig.encode()).hexdigest()
    return revision, sig, manifest


def enqueue(video, root):
    video = os.path.abspath(video)
    revision, sig, _ = snapshot(video, root)
    with connect(root) as db:
        db.execute('''INSERT INTO jellyfin_publications
          (video,revision,signature,status,updated,first_seen,next_attempt) VALUES(?,?,?,'pending',?,?,0)
          ON CONFLICT(video) DO UPDATE SET revision=excluded.revision,
          signature=excluded.signature,
          status=CASE WHEN jellyfin_publications.revision=excluded.revision
            THEN jellyfin_publications.status ELSE 'pending' END,
          attempts=CASE WHEN jellyfin_publications.revision=excluded.revision
            THEN jellyfin_publications.attempts ELSE 0 END,
          available=CASE WHEN jellyfin_publications.revision=excluded.revision
            THEN jellyfin_publications.available ELSE 0 END,
          first_seen=CASE WHEN jellyfin_publications.revision=excluded.revision
            THEN jellyfin_publications.first_seen ELSE excluded.first_seen END,
          next_attempt=CASE WHEN jellyfin_publications.revision=excluded.revision
            THEN jellyfin_publications.next_attempt ELSE 0 END,
          updated=excluded.updated, detail=CASE WHEN jellyfin_publications.revision=excluded.revision
            THEN jellyfin_publications.detail ELSE '' END''',
          (video, revision, sig, time.time(), time.time()))
    return revision


def search_terms(video):
    path = Path(video)
    terms = []
    try:
        tree = ET.parse(path.with_suffix('.nfo'))
        terms.extend(tree.findtext(tag) for tag in ('title', 'originaltitle'))
    except (OSError, ET.ParseError):
        pass
    # Sonarr: Series - S01E02 - Episode title WEBDL-2160p.
    episode = re.search(r'\bS\d+E\d+(?:-E?\d+)?\s*-\s*(.*)', path.stem, re.I)
    if episode:
        terms.append(re.split(r'\s+(?:WEBDL|WEBRip|Bluray|BluRay|HDTV|Remux|DVD|\d{3,4}p)\b', episode[1], flags=re.I)[0])
        terms.append(re.split(r'\s*-\s*S\d+E\d+', path.stem, flags=re.I)[0])
    else:
        terms.append(re.split(r'\s*[([](?:19|20)\d{2}[)\]]', path.stem)[0])
        terms.append(re.split(r'\s*[([](?:19|20)\d{2}[)\]]', path.parent.name)[0])
    return list(dict.fromkeys(t.strip() for t in terms if t and t.strip()))[:3]


def episode_parent(video):
    path = Path(video)
    return path.parent.parent if re.fullmatch(r'Season\s+\d+', path.parent.name, re.I) else path.parent


def resolve_series_child(db, video, request, parent_id):
    """Resolve an episode only inside an already exact-path matched Series."""
    matches = []
    exhausted = False
    for page in range(5):
        query = urllib.parse.urlencode(dict(ParentId=parent_id, Recursive='true',
            IncludeItemTypes='Episode', Fields='Path', Limit=200, StartIndex=page * 200,
            EnableTotalRecordCount='false'))
        items = json.loads(request('/Items?' + query))['Items']
        matches.extend(item for item in items if item.get('Path') == video)
        if len(items) < 200:
            exhausted = True
            break
    if len(matches) > 1:
        raise RuntimeError('Ambiguous exact series-child path; no refresh sent')
    if exhausted and len(matches) == 1:
        item_id = matches[0]['Id']
        with db:
            db.execute('INSERT OR REPLACE INTO jellyfin_path_cache VALUES(?,?)', (video, item_id))
        return item_id
    return None


def inventory_due(db, now=None):
    now = time.time() if now is None else now
    row = db.execute('SELECT scanned,revision FROM jellyfin_series_inventory_state WHERE id=1').fetchone()
    return row is None or row['revision'] != SERIES_INVENTORY_REVISION or now - row['scanned'] >= 900


def index_pending_series_paths(db, video, request):
    """Rate-limited exact path index for badly labelled local series.

    Jellyfin search is metadata-title based. A title can be wrong while its
    physical local path is perfectly valid, so the bounded name lookup above
    must not decide publication eligibility. This one shared scan looks only
    for exact parent paths of pending jobs, stores no title-derived identity,
    and deliberately cannot select a Venom/STRM series.
    """
    if not inventory_due(db):
        return
    wanted = {str(episode_parent(video))}
    for row in db.execute("SELECT video FROM jellyfin_publications WHERE status='pending'"):
        candidate = row['video']
        if re.search(r'\bS\d+E\d+', Path(candidate).stem, re.I):
            wanted.add(str(episode_parent(candidate)))
    start = 0
    pages = 0
    found = {}
    while pages < 100:
        query = urllib.parse.urlencode(dict(Recursive='true', IncludeItemTypes='Series',
            Fields='Path', Limit=500, StartIndex=start,
            EnableTotalRecordCount='true'))
        payload = json.loads(request('/Items?' + query))
        items = payload['Items']
        for item in items:
            path = item.get('Path')
            if path in wanted:
                found[path] = item['Id']
        pages += 1
        start += len(items)
        # Jellyfin 12 may omit TotalRecordCount unless explicitly requested.
        # A missing count must not look like zero and stop the exact-path
        # inventory after its first page.  A short page is still a safe EOF;
        # an endlessly full response remains capped by the hard 100-page limit.
        total = payload.get('TotalRecordCount')
        if not items or len(items) < 500 or (isinstance(total, int) and start >= total):
            break
    else:
        raise RuntimeError('Jellyfin series inventory exceeded bounded page limit')
    now = time.time()
    with db:
        for path, item_id in found.items():
            db.execute('INSERT OR REPLACE INTO jellyfin_series_path_cache VALUES(?,?,?)',
                       (path, item_id, now))
        db.execute('''INSERT INTO jellyfin_series_inventory_state(id,scanned,revision)
                      VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET
                      scanned=excluded.scanned, revision=excluded.revision''',
                   (now, SERIES_INVENTORY_REVISION))


def resolve(db, video, request):
    cached = db.execute('SELECT item_id FROM jellyfin_path_cache WHERE video=?', (video,)).fetchone()
    if cached:
        result = json.loads(request('/Items?Ids='+urllib.parse.quote(cached[0], safe='')+'&Fields=Path'))['Items']
        if len(result) == 1 and result[0].get('Path') == video:
            return cached[0]
        db.execute('DELETE FROM jellyfin_path_cache WHERE video=?', (video,))
        db.commit()
    for term in search_terms(video):
        matches = []
        exhausted = False
        for page in range(3):
            query = urllib.parse.urlencode(dict(Recursive='true', IncludeItemTypes='Episode,Movie',
                Fields='Path', SearchTerm=term, Limit=200, StartIndex=page*200, EnableTotalRecordCount='false'))
            items = json.loads(request('/Items?'+query))['Items']
            matches.extend(i for i in items if i.get('Path') == video)
            if len(items) < 200:
                exhausted = True
                break
        if len(matches) > 1:
            raise RuntimeError('Ambiguous exact Jellyfin path; no refresh sent')
        if len(matches) == 1 and exhausted:
            item_id = matches[0]['Id']
            db.execute('INSERT OR REPLACE INTO jellyfin_path_cache VALUES(?,?)', (video, item_id))
            db.commit()
            return item_id
    # Localized/renamed episode titles do not necessarily match filenames
    # (e.g. "Will Power" versus "Willpower"). Resolve the exact series path,
    # then search its bounded children by exact video path, never title alone.
    path=Path(video)
    if re.search(r'\bS\d+E\d+',path.stem,re.I):
        parent=episode_parent(video)
        parent_terms=[parent.name]
        try:
            tree=ET.parse(parent/'tvshow.nfo')
            parent_terms.extend(tree.findtext(tag) for tag in ('title','originaltitle'))
        except (OSError,ET.ParseError):pass
        parent_terms.append(re.split(r'\s+-\s+',parent.name)[0])
        # Jellyfin token search commonly indexes a series as its display title
        # without the filesystem disambiguation year.  Keep both forms, then
        # still require the returned parent *and* child physical paths to be
        # exact before using an ID.
        parent_terms.append(re.split(r'\s*[([](?:19|20)\d{2}[)\]]', parent.name)[0])
        series=[];parents=[]
        for term in list(dict.fromkeys(t.strip() for t in parent_terms if t and t.strip()))[:4]:
            query=urllib.parse.urlencode(dict(Recursive='true',IncludeItemTypes='Series',
                Fields='Path',SearchTerm=term,Limit=100,EnableTotalRecordCount='false'))
            series=json.loads(request('/Items?'+query))['Items']
            parents=[s for s in series if s.get('Path')==str(parent)]
            if len(series)<100 and len(parents)==1:break
        if len(series)<100 and len(parents)==1:
            item_id = resolve_series_child(db, video, request, parents[0]['Id'])
            if item_id:
                return item_id
        # Metadata can be wrong even where the exact local path is indexed.
        # Build one shared, rate-limited exact Series path index before deferring.
        index_pending_series_paths(db, video, request)
        cached_parent = db.execute('SELECT item_id FROM jellyfin_series_path_cache WHERE path=?',
                                   (str(parent),)).fetchone()
        if cached_parent:
            item_id = resolve_series_child(db, video, request, cached_parent['item_id'])
            if item_id:
                return item_id
    raise LookupPending('Exact Jellyfin path not found in bounded title lookup; deferred')


def hint_due(db, target, now=None):
    now = time.time() if now is None else now
    row = db.execute('SELECT sent FROM jellyfin_refresh_hints WHERE target=?',(target,)).fetchone()
    return row is None or now-row[0] >= 300


def record_hint(db, target):
    with db:
        db.execute('INSERT OR REPLACE INTO jellyfin_refresh_hints VALUES(?,?)',(target,time.time()))


def recover_transport_backoff(db, request, now=None):
    """A recovered server need not leave valid files waiting six more hours."""
    now=time.time() if now is None else now
    predicate="status='pending' AND available>? AND (detail LIKE 'URLError:%' OR detail LIKE 'TimeoutError:%' OR detail LIKE 'ConnectionResetError:%' OR detail LIKE 'ConnectionRefusedError:%')"
    if not db.execute('SELECT 1 FROM jellyfin_publications WHERE '+predicate+' LIMIT 1',(now+120,)).fetchone():return 0
    target='health:transport-backoff'
    if not hint_due(db,target,now):return 0
    # Bound probing even if the endpoint is still unavailable. No open SQLite
    # write transaction while making network requests.
    with db:db.execute('INSERT OR REPLACE INTO jellyfin_refresh_hints VALUES(?,?)',(target,now))
    try:
        info=json.loads(request('/System/Info/Public'))
        if not isinstance(info,dict) or not info.get('Version'):return 0
    except Exception:return 0
    with db:
        count=db.execute('UPDATE jellyfin_publications SET available=? WHERE '+predicate,(now,now+120)).rowcount
    if count:print('publication transport recovered; bounded worker rechecking',count,flush=True)
    return count


def refresh_parent(db, video, request):
    """Discover a missing episode via its exact local series, never IPTV/title alone."""
    path = Path(video)
    if not re.search(r'\bS\d+E\d+',path.stem,re.I):return False
    parent = path.parent.parent if re.fullmatch(r'Season\s+\d+',path.parent.name,re.I) else path.parent
    target = 'parent:'+str(parent)
    if not hint_due(db,target):return False
    query = urllib.parse.urlencode(dict(Recursive='true',IncludeItemTypes='Series',
        Fields='Path',SearchTerm=parent.name,Limit=100,EnableTotalRecordCount='false'))
    items = json.loads(request('/Items?'+query))['Items']
    matches = [i for i in items if i.get('Path')==str(parent)]
    if len(items)>=100 or len(matches)!=1:return False
    request('/Items/'+urllib.parse.quote(matches[0]['Id'],safe='')+
        '/Refresh?MetadataRefreshMode=Default&ImageRefreshMode=None&ReplaceAllMetadata=false'
        '&ReplaceAllImages=false&RegenerateTrickplay=false','POST')
    record_hint(db,target)
    return True


def check_view(video, canonical='/data/media', view='/data/media/compatibility/jellyfin-view'):
    try:relative=Path(video).relative_to(canonical)
    except ValueError:return
    if Path(view).is_dir() and not (Path(view)/relative).is_file():
        raise ViewPending('Video is not yet exposed in the managed compatibility view; awaiting video publication, not subtitle generation')


def circuit_open(db, now=None):
    now = time.time() if now is None else now
    row = db.execute('SELECT open_until FROM jellyfin_publication_circuit WHERE id=1').fetchone()
    return bool(row and row[0] > now)


def transport_error(error):
    return isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError, ConnectionResetError))


def defer(db, table, key_column, key, attempts, first_seen, error, detail_prefix='', revision=None):
    """Record one real try; lock/circuit cooldowns deliberately call none of this."""
    now = time.time()
    next_attempt = attempts + 1
    expired = now - first_seen >= MAX_AGE or next_attempt >= MAX_ATTEMPTS
    status = 'deadletter' if expired else 'pending'
    available = 0 if expired else now + publication_delay(error, attempts)
    with db:
        where = key_column + '=?' + (' AND revision=?' if revision is not None else '')
        columns = {row[1] for row in db.execute('PRAGMA table_info(' + table + ')')}
        due = ',next_attempt=?' if 'next_attempt' in columns else ''
        db.execute('UPDATE ' + table + ' SET status=?,attempts=?,available=?,updated=?,detail=?' + due + ' WHERE ' + where,
                   (status, next_attempt, available, now, detail_prefix + type(error).__name__) +
                   ((available,) if due else ()) + (key,) +
                   ((revision,) if revision is not None else ()))
        if transport_error(error):
            db.execute("INSERT INTO jellyfin_publication_circuit(id,open_until,detail) VALUES(1,?,?) "
                       "ON CONFLICT(id) DO UPDATE SET open_until=excluded.open_until,detail=excluded.detail",
                       (now + 120, type(error).__name__))
    return status, available


def expire_if_aged(db, table, key_column, key, first_seen, revision=None):
    if time.time() - first_seen < MAX_AGE:
        return False
    where = key_column + '=?' + (' AND revision=?' if revision is not None else '')
    with db:
        db.execute('UPDATE ' + table + " SET status='deadletter',available=0,next_attempt=0,updated=?,detail=? WHERE " + where,
                   (time.time(), 'retry window expired before attempt', key) + ((revision,) if revision is not None else ()))
    return True


def acknowledge(db, row, root, jobs, engine):
    """Reconcile both normal completion and the publisher/producer finish race."""
    video = row['video']
    if not Path(video).is_file():
        with db:
            db.execute("UPDATE jellyfin_publications SET status='missing',detail='media removed' WHERE video=? AND revision=?", (video,row['revision']))
            db.execute("UPDATE jobs SET status='missing',detail='media removed' WHERE video=? AND status='awaiting_jellyfin'", (video,))
        return False
    try:
        revision, sig, manifest = snapshot(video, root)
        valid = revision == row['revision'] and jobs.manifest_verified(engine, manifest, video, jobs.expected_version(Path(root), engine))
    except (OSError, ValueError, KeyError, RuntimeError):
        valid = False
    with db:
        if valid:
            db.execute("""UPDATE jobs SET status='complete',verified=?,attempts=0,
              detail=replace(detail,'awaiting independent Jellyfin verification','Jellyfin tracks verified')
              WHERE video=? AND status='awaiting_jellyfin' AND signature=?
              AND EXISTS(SELECT 1 FROM jellyfin_publications WHERE video=? AND revision=? AND status='complete')""",
              (time.time(),video,sig,video,revision))
        else:
            db.execute("UPDATE jobs SET status='pending',available=0,detail='Subtitle inputs changed before publication acknowledgement' WHERE video=? AND status='awaiting_jellyfin'", (video,))
            db.execute("UPDATE jellyfin_publications SET status='superseded' WHERE video=? AND revision=?", (video,row['revision']))
    return valid


def work(root, limit=3):
    root = Path(root)
    with (root/'.jellyfin-publication.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        db = connect(root)
        jobs = load(root, 'subtitle-library-jobs')
        engine = jobs.load_engine(root)
        sync = load(root, 'subtitle-jellyfin-sync')
        config = (root/'post-sub.sh').read_text()
        url = re.search(r'JELLYFIN_URL="([^"]+)"', config)[1]
        token = re.search(r'JELLYFIN_KEY="([^"]+)"', config)[1]
        def request(path, method='GET', body=None):
            req = urllib.request.Request(url.rstrip('/')+path, method=method,
                data=body if body is not None else b'' if method == 'POST' else None,
                headers={'Authorization':'MediaBrowser Token="'+token+'"','Content-Type':'application/json'})
            with urllib.request.urlopen(req, timeout=8) as response: return response.read()
        def expired(*_): raise TimeoutError('Publication attempt exceeded 90 seconds')
        signal.signal(signal.SIGALRM, expired)
        # A short shared circuit avoids turning one Jellyfin outage into a
        # fan-out across the bounded batch.  No scheduled task is inspected or
        # controlled by subtitle publication.
        if circuit_open(db):
            return
        # A child may have committed its ACK just before generation marked waiting.
        for row in db.execute("SELECT p.* FROM jellyfin_publications p JOIN jobs j USING(video) WHERE p.status='complete' AND j.status='awaiting_jellyfin' LIMIT 30").fetchall():
            try:
                signal.alarm(90)
                acknowledge(db,row,root,jobs,engine)
            finally: signal.alarm(0)
        rows = db.execute("SELECT * FROM jellyfin_publications WHERE status='pending' AND available<=? ORDER BY available,updated LIMIT ?", (time.time(),limit)).fetchall()
        for row in rows:
            video = row['video']
            started = time.monotonic()
            try:
                if expire_if_aged(db, 'jellyfin_publications', 'video', video, row['first_seen'], row['revision']):
                    print('publication deadletter', video, 'retry-age-expired', flush=True)
                    continue
                signal.alarm(90)
                if not Path(video).is_file():
                    acknowledge(db,row,root,jobs,engine)
                    continue
                revision, sig, manifest = snapshot(video,root)
                if revision != row['revision']:
                    acknowledge(db,row,root,jobs,engine)
                    continue
                if not jobs.manifest_verified(engine,manifest,video,jobs.expected_version(root,engine)):
                    acknowledge(db,row,root,jobs,engine)
                    continue
                try:
                    check_view(video)
                    item_id = resolve(db,video,request)
                except ViewPending:
                    raise
                except LookupPending:
                    # Import/index/view publication is owned elsewhere.  Do
                    # not submit a new-title notification, library refresh or
                    # scan; defer until this exact item exists.
                    raise
                due = hint_due(db,'item:'+item_id)
                def refresh_request(path, method='GET'):
                    result = request(path,method)
                    if method == 'POST':record_hint(db,'item:'+item_id)
                    return result
                sync.synchronize(video,root,url,token,request=refresh_request,item_id=item_id,
                                 poll_attempts=0,refresh=due)
                if snapshot(video,root)[0] != revision:
                    raise RuntimeError('Subtitle revision changed during verification')
                with db:
                    db.execute("UPDATE jellyfin_publications SET status='complete',updated=?,detail='Exact paths, defaults, titles and served SRT content verified' WHERE video=? AND revision=?", (time.time(),video,revision))
                acknowledge(db,row,root,jobs,engine)
                print('publication verified',video,round(time.monotonic()-started,2),flush=True)
            except Exception as exc:
                # No translation retries, no GPU claim and no unbounded retry.
                status, available = defer(db, 'jellyfin_publications', 'video', video,
                    row['attempts'], row['first_seen'], exc, 'managed: ', row['revision'])
                print('publication '+status,video,type(exc).__name__,round(time.monotonic()-started,2),
                      'retry_seconds',max(0,round(available-time.time())),flush=True)
                if transport_error(exc):
                    break
            finally: signal.alarm(0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['work','enqueue','status'])
    parser.add_argument('video', nargs='?')
    parser.add_argument('--root', default='/config/scripts')
    parser.add_argument('--limit', type=int, default=3)
    args = parser.parse_args()
    if args.action == 'work': work(args.root, max(1, min(args.limit, 3)))
    elif args.action == 'enqueue': enqueue(args.video,args.root)
    else:
        with connect(args.root) as db:
            print(json.dumps([dict(r) for r in db.execute('SELECT status,count(*) AS count FROM jellyfin_publications GROUP BY status')]))
