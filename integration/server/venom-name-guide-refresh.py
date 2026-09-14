"""Request one coalesced guide refresh after persistent name overrides change.

Never interrupts/restarts a running guide. Existing daily task remains intact.
No channel/video requests, client patches or playback changes.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import runpy
import time

ROOT=Path('/data/config/iptv-venom')

def should_refresh(state,fingerprint,previous,now):
    return (state=='Idle' and fingerprint!=previous.get('fingerprint')
            and now-previous.get('requested_at',0)>=6*3600)

def main():
    lock=(ROOT/'name-guide-refresh.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return
    ledger=Path('/data/config/dispatcharr/venom-name-overrides.json')
    if not ledger.exists():return
    payload=json.loads(ledger.read_text())
    if not payload:return
    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    marker=ROOT/'name-guide-refresh.json'
    previous=json.loads(marker.read_text()) if marker.exists() else {}
    api=runpy.run_path('/root/iptv-jellyfin-admin.py')['api']
    task=next(t for t in api('/ScheduledTasks') if t.get('Key')=='RefreshGuide')
    now=time.time()
    if not should_refresh(task['State'],fingerprint,previous,now):
        print(json.dumps({'event':'name_refresh_deferred','guide_state':task['State'],'already_requested':fingerprint==previous.get('fingerprint')}));return
    api('/ScheduledTasks/Running/'+task['Id'],method='POST')
    tmp=marker.with_suffix('.tmp')
    tmp.write_text(json.dumps({'fingerprint':fingerprint,'requested_at':now}))
    tmp.chmod(0o600);tmp.replace(marker)
    print(json.dumps({'event':'name_refresh_requested'}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'event':'name_refresh_error','type':type(exc).__name__}));raise SystemExit(1)
