"""Append-only, best-effort subtitle performance events on ARR (no model changes)."""
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid


def safe_failure(error, stage=None):
    """Return an allow-listed diagnostic, never exception text.

    Exception messages can contain paths, HTTP headers, model input, or a cue.
    Performance telemetry and the durable queue therefore receive only a stable
    reason code plus a short maintained explanation.  Extend this table when a
    new *general* failure class is proven; do not copy raw exception strings.
    """
    kind=type(error).__name__
    raw=str(error).lower()
    known=(
        ('unsafe retirement target','publisher-unsafe-retirement-target','publisher rejected unsafe retirement target'),
        ('cannot retire an active source input','publisher-active-source-retirement','publisher refused to retire an active source'),
        ('unsafe retired input provenance','publisher-unsafe-retired-input','publisher rejected retired-input provenance'),
        ('manifest video identity mismatch','publisher-manifest-identity','publisher manifest identity mismatch'),
        ('incomplete or unknown track roles','publisher-track-role-set','publisher rejected track role set'),
        ('invalid role filename','publisher-role-filename','publisher rejected role filename'),
        ('source changed','publisher-source-changed','source changed during publication'),
        ('unmanaged or externally edited target','publisher-target-preserved','publisher preserved unmanaged target'),
        ('target changed during publication','publisher-target-changed','target changed during publication'),
        ('published file verification failed','publisher-output-verification','publisher output verification failed'),
        ('archive conflict','publisher-archive-conflict','publisher archive conflict'),
        ('retirement archive already exists','publisher-retirement-archive','publisher retirement archive conflict'),
        ('publisher arabic pair validation failed','publisher-arabic-pair-validation','publisher rejected Arabic/English track pair'),
    )
    for needle,code,message in known:
        if needle in raw:
            return {'failure_type':kind,'failure_reason_code':code,'failure_message':message}
    stage=stage or ''
    prefix='publisher' if stage == 'publish_tracks' else 'stage'
    # No raw fallback: unclassified strings can be user/model supplied.
    return {'failure_type':kind,'failure_reason_code':prefix+'-unclassified-'+re.sub(r'[^a-z0-9]+','-',kind.lower()).strip('-'),
            'failure_message':'unclassified '+prefix+' failure; inspect bounded local diagnostics'}


def emit(event, **fields):
    if not os.environ.get('SUBTITLE_TIMING_RUN'):
        return
    try:
        video = os.environ.get('SUBTITLE_VIDEO', '')
        row = dict(schema=1, event=event, utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   run_id=os.environ['SUBTITLE_TIMING_RUN'], video=video,
                   title=Path(video).stem, title_id=hashlib.sha256(video.encode()).hexdigest(),
                   media_type='movie' if '/movies/' in video else 'show' if '/shows/' in video else 'unknown',
                   gpu=os.environ.get('SUBTITLE_TIMING_GPU', 'unknown'), **fields)
        root = Path(os.environ['SUBTITLE_TIMING_DIR'])
        root.mkdir(parents=True, exist_ok=True)
        # Monthly append-only files survive translation-cache cleanup. Lock both lanes.
        path = root / (row['utc'][:7] + '.jsonl')
        with path.open('a', encoding='utf-8') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
            stream.flush()
    except Exception as error:
        print('SUBTITLE_TIMING logging error: ' + type(error).__name__, flush=True)


def latest_failure(run_id=None):
    """Read the newest sanitized failed stage for one run, if still available."""
    run_id=run_id or os.environ.get('SUBTITLE_TIMING_RUN')
    directory=os.environ.get('SUBTITLE_TIMING_DIR')
    if not run_id or not directory:
        return None
    path=Path(directory)/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m')+'.jsonl')
    try:
        # The newest worker events are at EOF; bound memory even for a busy month.
        from collections import deque
        with path.open(encoding='utf-8') as stream:
            lines=deque(stream,maxlen=512)
        for line in reversed(lines):
            row=json.loads(line)
            if row.get('run_id') == run_id and row.get('event') == 'stage_end' and row.get('failure_reason_code'):
                return {key:row.get(key) for key in ('stage','failure_type','failure_reason_code','failure_message')}
    except (OSError,ValueError,TypeError,json.JSONDecodeError):
        return None
    return None


@contextlib.contextmanager
def stage(name, **details):
    started = time.monotonic()
    stage_id = uuid.uuid4().hex
    parent=os.environ.get('SUBTITLE_TIMING_STAGE')
    emit('stage_start', stage=name, stage_id=stage_id, parent_stage_id=parent, **details)
    os.environ['SUBTITLE_TIMING_STAGE']=stage_id
    outcome = 'ok'
    failure = {}
    try:
        yield details
    except BaseException as error:
        outcome = type(error).__name__
        failure = safe_failure(error, name)
        raise
    finally:
        emit('stage_end', stage=name, stage_id=stage_id,
             parent_stage_id=parent, elapsed_seconds=round(time.monotonic()-started, 6), outcome=outcome,
             **failure, **details)
        if parent is None:os.environ.pop('SUBTITLE_TIMING_STAGE',None)
        else:os.environ['SUBTITLE_TIMING_STAGE']=parent


def call(name, function, *args, **kwargs):
    with stage(name):
        return function(*args, **kwargs)
