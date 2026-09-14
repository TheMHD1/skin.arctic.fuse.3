"""CT controller: evaluate current evidence under the shared checker lock."""
import argparse
import fcntl
import json
from pathlib import Path
import runpy
import sqlite3
import subprocess
import time

ROOT=Path('/data/config/iptv-venom')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    lock=(ROOT/'channel-checker.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        if args.apply:
            print(json.dumps({'event':'visibility_deferred','reason':'checker_busy'}));return
        print(json.dumps({'event':'visibility_read_only_snapshot','checker_busy':True}))
    if args.apply:
        checker=runpy.run_path(str(ROOT/'venom-channel-checker.py'))
        secret=json.loads(Path('/data/config/dispatcharr/venom-credentials.json').read_text())
        token=checker['request']('/api/accounts/token/',{'username':secret['admin_user'],'password':secret['admin_password']})['access']
        if not checker['idle'](token):
            print(json.dumps({'event':'visibility_deferred','reason':'playback_active'}));return
    classify=runpy.run_path(str(ROOT/'venom-channel-health-policy.py'))['classify']
    success={}
    with sqlite3.connect('file:'+str(ROOT/'channel-health.sqlite3')+'?mode=ro',uri=True) as db:
        for cid,raw in db.execute('select channel_id,record from observations'):
            r=json.loads(raw)
            if classify(r)=='working':success[str(cid)]=max(success.get(str(cid),0),r['time'])
    result=subprocess.run(['docker','exec','-i','dispatcharr','timeout','--signal=TERM','--kill-after=3','100','python','manage.py','shell','-c',
                           "import runpy; runpy.run_path('/data/venom-hide-confirmed-worker.py',run_name='__main__')"],
                          input=json.dumps({'generated':time.time(),'success':success,'apply':args.apply}),
                          capture_output=True,text=True,timeout=120)
    # Worker emits only redacted event records; omit Django startup chatter.
    for line in result.stdout.splitlines():
        if line.startswith('{'):print(line,flush=True)
    if result.returncode:raise RuntimeError('Visibility worker failed')

if __name__=='__main__':main()
