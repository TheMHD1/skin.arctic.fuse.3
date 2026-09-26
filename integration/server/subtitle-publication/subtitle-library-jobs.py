#!/usr/bin/env python3
"""ARR/Bazarr durable discovery and bounded worker for the four-track library.

No legacy done-list dependency. Discovery is cheap stat-based invalidation;
the engine still checks content hashes before publication. A periodic forced
verification window catches deleted/edited outputs and missed import events.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import sqlite3
import subprocess
import signal
import time
import uuid
import subtitle_timing as timing

EXTENSIONS = {'.mkv', '.mp4', '.m4v', '.avi', '.mov'}


def wait_unreaped(child, timeout=None):
    """Observe exit without freeing the PID/process-group identity."""
    deadline = None if timeout is None else time.monotonic() + timeout
    flags = os.WEXITED | os.WNOWAIT | (os.WNOHANG if timeout is not None else 0)
    while True:
        result = os.waitid(os.P_PID, child.pid, flags)
        if result is not None:
            return result.si_status if result.si_code == os.CLD_EXITED else -result.si_status
        if deadline is not None and time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired(child.args, timeout)
        time.sleep(.05)


def run_engine(command, env):
    """Bound child process group lifetime to the worker, including TERM.

    Caller must use timeout --foreground so its descendants stay in this group.
    Docker-client stop still needs a host-side signal path to this worker.
    """
    child = None
    previous = {}
    def interrupted(signum, frame):
        raise SystemExit(128 + signum)
    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, interrupted)
        child = subprocess.Popen(command, env=env, start_new_session=True)
        return wait_unreaped(child)
    finally:
        # Ignore repeated TERM while draining; service-level hard kill remains
        # the outer bound. Retain original handlers after cleanup.
        for signum in previous: signal.signal(signum, signal.SIG_IGN)
        try:
            if child is not None:
                try: os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                try: wait_unreaped(child, timeout=30)
                except subprocess.TimeoutExpired:
                    pass
                # The leader is still unreaped, so its PID/group cannot be
                # reassigned between exit observation and this final sweep.
                try: os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                child.wait(timeout=5)
        finally:
            for signum, handler in previous.items(): signal.signal(signum, handler)


def engine_detail(code, verified):
    """Attach the newest allow-listed child-stage failure to a durable job.

    Child stderr is deliberately not copied into SQLite: it may include a
    subtitle cue, model prompt, endpoint, or credential-bearing URL. Timing
    only exposes `safe_failure()`'s fixed vocabulary.
    """
    detail=f'engine rc={code}; verified={verified}'
    if code == 0 and verified:
        return detail
    failure=timing.latest_failure()
    if not isinstance(failure,dict):
        return detail
    stage=failure.get('stage')
    reason=failure.get('failure_reason_code')
    message=failure.get('failure_message')
    kind=failure.get('failure_type')
    if not all(isinstance(value,str) and value for value in (stage,reason,message,kind)):
        return detail
    # These fields originate from a fixed local allow-list, not exception text.
    return detail+f'; stage={stage}; reason={reason}; type={kind}; note={message}'


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA synchronous=FULL')
    con.execute('''CREATE TABLE IF NOT EXISTS jobs(
        video TEXT PRIMARY KEY, signature TEXT NOT NULL, status TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, available REAL NOT NULL DEFAULT 0,
        seen REAL NOT NULL, verified REAL NOT NULL DEFAULT 0,
        detail TEXT NOT NULL DEFAULT '')''')
    if 'changed' not in {r[1] for r in con.execute('PRAGMA table_info(jobs)')}:
        con.execute('ALTER TABLE jobs ADD COLUMN changed REAL NOT NULL DEFAULT 0')
    con.execute('CREATE TABLE IF NOT EXISTS policy(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS batch_assignments(video TEXT PRIMARY KEY,gpu TEXT NOT NULL CHECK(gpu IN (\'3060\',\'3090\')))')
    con.commit()
    return con


def signature(video):
    def stat(path):
        try:
            s = path.stat()
            return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]
        except FileNotFoundError:
            return None
    path = Path(video)
    # Provider downloads, file upgrades/renames and changes to named outputs all
    # invalidate completion. Archive/metadata writes do not trigger endless work.
    # Movie names often contain [imdbid] or [tmdbid]; treat these literally,
    # not as glob character classes or source changes would be missed.
    subs = sorted(p for p in path.parent.iterdir()
                  if p.name.startswith(path.stem + '.') and p.suffix.lower() == '.srt')
    payload = [stat(path), [(str(p), stat(p)) for p in subs]]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def enqueue(con, video, now=None):
    now = time.time() if now is None else now
    sig = signature(video)
    con.execute('''INSERT INTO jobs(video,signature,status,seen,changed) VALUES(?,?,'pending',?,?)
        ON CONFLICT(video) DO UPDATE SET seen=excluded.seen,
        status=CASE WHEN jobs.status='running' THEN jobs.status
                    WHEN jobs.signature<>excluded.signature THEN 'pending' ELSE jobs.status END,
        attempts=CASE WHEN jobs.signature<>excluded.signature AND jobs.status<>'running' THEN 0 ELSE jobs.attempts END,
        available=CASE WHEN jobs.signature<>excluded.signature AND jobs.status<>'running' THEN 0 ELSE jobs.available END,
        changed=CASE WHEN jobs.signature<>excluded.signature THEN excluded.changed ELSE jobs.changed END,
        signature=CASE WHEN jobs.status='running' THEN jobs.signature ELSE excluded.signature END''',
        (str(video),sig,now,now))
    con.commit()


def discover(con, roots, now=None):
    now = time.time() if now is None else now
    count = 0
    for root in roots:
        if not Path(root).is_dir():
            raise RuntimeError('canonical media root unavailable: ' + str(root))
    for root in roots:
        for directory, _, names in os.walk(root, followlinks=False):
            for name in names:
                path = Path(directory) / name
                if path.suffix.lower() not in EXTENSIONS or not path.is_file():
                    continue
                sig = signature(path)
                # Never reset an actively processing row; the worker compares
                # its initial signature before treating its result as complete.
                con.execute('''INSERT INTO jobs(video,signature,status,seen,changed) VALUES(?,?,'pending',?,?)
                    ON CONFLICT(video) DO UPDATE SET seen=excluded.seen,
                    status=CASE WHEN jobs.status='running' THEN jobs.status
                      WHEN jobs.signature<>excluded.signature THEN 'pending'
                      WHEN jobs.status='complete' AND jobs.verified<? THEN 'pending'
                      ELSE jobs.status END,
                    attempts=CASE WHEN jobs.signature<>excluded.signature AND jobs.status<>'running' THEN 0 ELSE jobs.attempts END,
                    available=CASE WHEN jobs.signature<>excluded.signature AND jobs.status<>'running' THEN 0 ELSE jobs.available END,
                    changed=CASE WHEN jobs.signature<>excluded.signature THEN excluded.changed ELSE jobs.changed END,
                    signature=CASE WHEN jobs.status='running' THEN jobs.signature ELSE excluded.signature END''',
                    (str(path), sig, now, now, now-7*86400))
                # Never hold a SQLite writer transaction while the next file's
                # potentially slow media-storage metadata is inspected. Hooks
                # and the worker must remain able to enqueue/commit mid-scan.
                con.commit()
                count += 1
    con.commit()
    return count


def result_state(con, video, code, verified, detail, now=None, post_signature=None):
    now = time.time() if now is None else now
    row = con.execute('SELECT * FROM jobs WHERE video=?', (video,)).fetchone()
    if not row:
        raise ValueError('unknown job')
    if code == 0 and verified:
        # Files are complete, but only the independent publisher can attest that
        # Jellyfin serves them. Never recycle this job through the GPU for that.
        con.execute("UPDATE jobs SET status='awaiting_jellyfin',verified=0,attempts=0,detail=?,signature=? WHERE video=?",
                    (detail + '; files ready; awaiting independent Jellyfin verification', post_signature or row['signature'], video))
    elif code == 65:
        # The API already applied bounded recovery. Repeating unchanged input
        # with the same model/seed wastes compute and cannot certify quality.
        con.execute("UPDATE jobs SET status='failed',attempts=attempts+1,detail=? WHERE video=?",
                    ('Translation rejected after bounded recovery; held for review; checkpoints preserved', video))
    elif code == 75:
        # Temporary service/GPU contention is not a failed subtitle attempt.
        con.execute("UPDATE jobs SET status='retry',available=?,detail=? WHERE video=?", (now+900, detail, video))
    else:
        attempts = row['attempts']+1
        con.execute('UPDATE jobs SET status=?,attempts=?,available=?,detail=? WHERE video=?',
                    ('failed' if attempts >= 8 else 'retry', attempts,
                     now+min(86400, 900*2**min(attempts,6)), detail, video))
    con.commit()


def load_engine(root):
    spec = importlib.util.spec_from_file_location('library_engine', root / 'sub-engine.py')
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def reconcile_policy(con, version):
    """Called under the worker flock; atomic, idempotent model/publication migration."""
    if not version:
        raise ValueError('missing publication version')
    with con:
        con.execute('BEGIN IMMEDIATE')
        previous = con.execute("SELECT value FROM policy WHERE key='publication_version'").fetchone()
        if previous and previous[0] == version:
            return False
        if con.execute("SELECT 1 FROM jobs WHERE status='running' LIMIT 1").fetchone():
            raise RuntimeError('cannot migrate policy during an active job')
        # Retain source signatures, import priorities, original files and caches.
        # Failed translations under an old model deserve a fresh bounded retry.
        con.execute("UPDATE jobs SET status='pending',attempts=0,available=0,verified=0,detail='publication policy changed' WHERE status NOT IN ('excluded','missing')")
        con.execute("INSERT INTO policy(key,value) VALUES('publication_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (version,))
    return True


def expected_version(root, engine):
    spec = importlib.util.spec_from_file_location('library_four', root/'sub-engine-four.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.publication_version(engine)


def manifest_verified(engine, manifest, video, version):
    """Do not let all([]), absent files, or an old policy certify completion."""
    try:
        if not isinstance(manifest, dict) or manifest.get('version') != version or manifest.get('status') != 'complete':
            return False
        roles = manifest['roles'];sources = manifest['sources']
        if not isinstance(roles, dict) or set(roles) not in (
                {'en_asr','ar_asr'}, {'en_asr','ar_asr','en_download','ar_download'}):
            return False
        source = os.path.splitext(video)[0] + '.en.srt'
        if not isinstance(sources, dict) or source not in sources:
            return False
        paths = [t['path'] for t in roles.values()]
        if len(set(paths)) != len(paths):
            return False
        if any(not isinstance(t['path'],str) or not t['path'] or
               not isinstance(t['hash'],str) or not t['hash'] for t in roles.values()):
            return False
        archives = manifest.get('input_retirements', {})
        if not isinstance(archives, dict):
            return False
        for path, digest in archives.items():
            if (not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{32}', digest)
                    or path != source + '.retired-subengine-' + digest + '.bak'
                    or os.path.islink(path)
                    or engine.file_hash(path) != digest):
                return False
        return (manifest['fingerprint'] == engine.fingerprint(video) and
                all(engine.file_hash(p)==h for p,h in sources.items()) and
                all(engine.file_hash(t['path'])==t['hash'] for t in roles.values()))
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        return False


def batch_active(con):
    row=con.execute("SELECT value FROM policy WHERE key='temporary_gpu_batch_active'").fetchone()
    return bool(row and row[0]=='1')


def lane_scope(con,lane):
    if lane not in (None,'3090'):raise ValueError('Unknown worker lane')
    if not batch_active(con):return '0' if lane else '1'
    member="video IN (SELECT video FROM batch_assignments WHERE gpu='3090')"
    return member if lane else 'NOT ('+member+')'


def finish_batch_if_terminal(con):
    if not batch_active(con):return False
    with con:
        con.execute('BEGIN IMMEDIATE')
        remaining=con.execute("SELECT 1 FROM jobs JOIN batch_assignments USING(video) WHERE status IN ('pending','retry','running') LIMIT 1").fetchone()
        if remaining:return False
        con.execute("UPDATE policy SET value='0' WHERE key='temporary_gpu_batch_active'")
    print('Temporary two-GPU backlog finished; normal routing restored',flush=True)
    return True


def work(con, root, lane=None):
    keys=('SUBTITLE_TIMING_RUN','SUBTITLE_TIMING_DIR','SUBTITLE_TIMING_GPU','SUBTITLE_VIDEO')
    previous={key:os.environ.get(key) for key in keys}
    os.environ.update(SUBTITLE_TIMING_RUN=uuid.uuid4().hex,
                      SUBTITLE_TIMING_DIR=str(root/'four-track-state'/'performance'),
                      SUBTITLE_TIMING_GPU=lane or '3060')
    os.environ.pop('SUBTITLE_VIDEO',None)
    started=time.monotonic()
    outcome='returned'
    try:
        return _work(con,root,lane)
    except BaseException as error:
        outcome=type(error).__name__
        raise
    finally:
        if os.environ.get('SUBTITLE_VIDEO'):
            row=con.execute('SELECT status,detail FROM jobs WHERE video=?',(os.environ['SUBTITLE_VIDEO'],)).fetchone()
            timing.emit('attempt_end',elapsed_seconds=round(time.monotonic()-started,6),
                        outcome=outcome,queue_status=row[0] if row else None,detail=row[1] if row else None)
        for key,value in previous.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


def _work(con, root, lane=None):
    # A worker can be restarted after a reboot. Single-worker flock plus the
    # engine's per-item/GPU locks are the authoritative live concurrency guards.
    with open(root / ('.library-worker-3090.lock' if lane else '.library-worker.lock'), 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        scope=lane_scope(con,lane)
        con.execute("UPDATE jobs SET status='pending' WHERE status='running' AND ("+scope+")")
        con.commit()
        engine = load_engine(root)
        version = expected_version(root, engine)
        if batch_active(con):
            stored=con.execute("SELECT value FROM policy WHERE key='publication_version'").fetchone()
            if not stored or stored[0]!=version:raise RuntimeError('Do not migrate policy during temporary GPU batch')
        elif not lane and reconcile_policy(con, version):
            print('library publication policy changed; eligible jobs requeued', version, flush=True)
        row = con.execute("SELECT * FROM jobs WHERE status IN ('pending','retry') AND ("+scope+") AND available<=? ORDER BY changed DESC,video LIMIT 1", (time.time(),)).fetchone()
        if not row:
            finish_batch_if_terminal(con)
            return
        preflight_spec=importlib.util.spec_from_file_location('subtitle_preflight',root/'subtitle-preflight.py')
        preflight=importlib.util.module_from_spec(preflight_spec);preflight_spec.loader.exec_module(preflight)
        import sys
        if preflight.inspect_job(con,root,sys.modules[__name__],engine,row)!='ready':
            finish_batch_if_terminal(con)
            return
        video = row['video']
        os.environ['SUBTITLE_VIDEO']=video
        timing.emit('attempt_start',previous_attempts=row['attempts'],pipeline=engine.PIPELINE_VERSION)
        if not Path(video).is_file():
            con.execute("UPDATE jobs SET status='missing',detail='media no longer present' WHERE video=?", (video,))
            con.commit()
            return
        if any(x in video for x in engine.EXCLUDE_PATHS):
            reason = 'explicit title exclusion'
        else:
            english, reason = timing.call('audio_language_probe',engine.is_english_audio,video)
            if english:
                reason = None
        if reason:
            con.execute("UPDATE jobs SET status='excluded',detail=?,verified=? WHERE video=?", (reason, time.time(),video))
            con.commit()
            return
        claimed=con.execute("UPDATE jobs SET status='running',detail='engine executing' WHERE video=? AND status IN ('pending','retry') AND signature=?", (video,row['signature']))
        con.commit()
        if not claimed.rowcount:return
        environment=dict(os.environ,SUBENGINE_FOUR_TRACKS='1',GPU_LOCK_WAIT='60',SUBTITLE_VIDEO=video)
        if lane:
            # Private lane endpoints are deployment inputs, never public source.
            environment.update(WHISPER_URL=os.environ['SUBTITLE_3090_WHISPER_URL'],NLLB_URL=os.environ['SUBTITLE_3090_NLLB_URL'],
                               SUBTITLE_GPU_LOCK_PATH='/tmp/subtitle-gpu3090.lock')
        seconds=max(30,min(600 if lane else 3300,int(os.environ.get('SUBTITLE_ENGINE_TIMEOUT','600' if lane else '3300'))))
        code = timing.call('engine_total',run_engine,['timeout','--foreground','-s','TERM','-k','30',str(seconds),'python3',str(root/'sub-engine.py'),
                               video,'--apply','--reason','library-worker'],
                              env=environment)
        if lane and code==124:code=75  # Yield GPU0 to queued API work; keep checkpoints/retry budget.
        key = hashlib.sha256(os.path.realpath(video).encode()).hexdigest()
        verified = False
        try:
            manifest = json.loads((root/'four-track-state'/(key+'.json')).read_text())
            verified = timing.call('final_manifest_verification',manifest_verified,engine,manifest,video,version)
        except (OSError, ValueError, KeyError):
            pass
        detail=engine_detail(code,verified)
        if code==0 and verified and manifest.get('translation_warnings'):
            detail=f"Completed with warnings: {len(manifest['translation_warnings'])} English fallback cues; details in title manifest and SUBTITLE_FALLBACK log"
        result_state(con,video,code,verified,detail,post_signature=signature(video))
        print('library job', video, code, verified, flush=True)
        finish_batch_if_terminal(con)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['discover','work','status','prepare'])
    ap.add_argument('--root', default='/config/scripts')
    ap.add_argument('--lane', choices=['3090'])
    args = ap.parse_args()
    root = Path(args.root)
    if args.action != 'status' and (not (root/'four-tracks.enabled').exists() or
            (root/'subengine.OFF').exists() or (root/'.subtitle-ai-maintenance').exists()):
        print('four-track library processing disabled/paused',flush=True)
        return
    with connect(root/'four-track-jobs.sqlite') as con:
        if args.action=='discover':
            print('discovered', discover(con, ['/data/media/movies','/data/media/shows']),flush=True)
        elif args.action=='work':
            work(con,root,args.lane)
        elif args.action=='prepare':
            import sys
            spec=importlib.util.spec_from_file_location('subtitle_preflight',root/'subtitle-preflight.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            video=module.prepare(con,root,sys.modules[__name__],args.lane)
            print('preflight ready',video,flush=True)
            raise SystemExit(0 if video else 3)
        else:
            print(json.dumps([dict(r) for r in con.execute('SELECT status,count(*) AS count FROM jobs GROUP BY status')]))


if __name__ == '__main__':
    main()
