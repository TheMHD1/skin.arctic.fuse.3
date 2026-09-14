"""One-pass, resumable custom-channel HDR audit; no selection/playback mutations."""
import argparse
import collections
import fcntl
import json
from pathlib import Path
import runpy
import sqlite3
import time
import urllib.parse

ROOT=Path('/data/config/iptv-venom')

def load_scope():
    groups=[]
    for filename in ('curated-candidates.json','curated-channels.json'):
        path=ROOT/filename
        if path.exists():groups.extend(json.loads(path.read_text())['groups'])
    channels={str(c['stream_id']):c for g in groups for c in g['channels']}
    return {'groups':groups},channels

def classification(record):
    if record.get('result')!='working':return 'inconclusive_playback'
    if record.get('decoded_hdr') is True:return 'hdr'
    if record.get('decoded_hdr') is False:return 'sdr'
    return 'unknown_transfer'

def save(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2));temp.chmod(0o600);temp.replace(path)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--max-probes',type=int,default=10000);args=parser.parse_args()
    own=(ROOT/'hdr-audit.lock').open('a')
    try:fcntl.flock(own,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return
    checker=runpy.run_path(str(ROOT/'venom-channel-checker.py'))
    quality=runpy.run_path(str(ROOT/'venom-quality-probe.py'))
    priority=runpy.run_path(str(ROOT/'venom-special-groups.py'))['priority']
    manifest,channels=load_scope()
    path=ROOT/'channel-quality-audit.json'
    previous=json.loads(path.read_text()).get('channels',{}) if path.exists() else {}
    now=time.time()
    records={i:r for i,r in previous.items() if i in channels and r.get('quality_schema')==3 and 0<=now-r.get('time',0)<7*86400}
    def report(state):
        membership={}
        for g in manifest['groups']:
            for c in g['channels']:membership.setdefault(str(c['stream_id']),set()).add(g['id'])
        for cid,row in records.items():row['custom_groups']=sorted(membership.get(cid,set()))
        counts=dict(collections.Counter(r['classification'] for r in records.values()))
        counts['pending']=len(channels)-len(records)
        save(path,{'updated':time.time(),'state':state,'total_channels':len(channels),'counts':counts,'channels':records})
    report('running')
    secret=json.loads(Path('/data/config/dispatcharr/venom-credentials.json').read_text())
    token=checker['request']('/api/accounts/token/',{'username':secret['admin_user'],'password':secret['admin_password']})['access']
    token_time=time.monotonic()
    attempted=0
    while True:
        manifest,channels=load_scope()
        published_groups={g['id'] for g in json.loads((ROOT/'curated-channels.json').read_text())['groups']}
        missing_sport_ids={str(c['stream_id']) for g in manifest['groups'] if g['id'].startswith('sport-') and g['id'] not in published_groups for c in g['channels']}
        pending=sorted(((i,c) for i,c in channels.items() if i not in records),key=lambda pair:(pair[0] not in missing_sport_ids,priority(pair[1])))
        if not pending:break
        cid,c=pending[0]
        if attempted>=args.max_probes:break
        if not cid.isdigit():raise ValueError('Invalid gateway ID')
        while True:
            lock=(ROOT/'channel-checker.lock').open('a')
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                lock.close();report('waiting_checker');time.sleep(15);continue
            try:
                if time.monotonic()-token_time>120:
                    token=checker['request']('/api/accounts/token/',{'username':secret['admin_user'],'password':secret['admin_password']})['access']
                    token_time=time.monotonic()
                if not checker['idle'](token,12):
                    lock.close();report('waiting_playback');time.sleep(30);continue
                url=checker['BASE']+'/live/'+urllib.parse.quote(secret['stream_user'],safe='')+'/'+urllib.parse.quote(secret['stream_password'],safe='')+'/'+cid+'.ts'
                result=quality['probe'](url,35)
                groups=list(dict.fromkeys(g['id'] for g in manifest['groups'] if any(str(x['stream_id'])==cid for x in g['channels'])))
                records[cid]={'name':c['name'],'provider_category_id':c.get('category_id'),'custom_groups':groups,'time':time.time(),'source':'quality_audit','quality_schema':3,**result}
                # A successful full-quality decode also satisfies the ordinary
                # playback gate, avoiding a second probe just for publication.
                if result['result']=='working':
                    frame=result['decoded_frame_variants'][0]
                    health={'result':'working','channel_id':cid,'time':records[cid]['time'],'source':'quality_audit',
                            'decoded_video_frames':result['decoded_video_frames'],'decoded_width':frame.get('width'),'decoded_height':frame.get('height')}
                    if result['classification'] in ('hdr','sdr'):
                        health.update(decoded_hdr=result['classification']=='hdr',decoded_transfer=frame.get('color_transfer'))
                    with sqlite3.connect(ROOT/'channel-health.sqlite3') as db:
                        db.execute('insert into observations(channel_id,time,result,record) values(?,?,?,?)',(cid,health['time'],'working',json.dumps(health)))
                attempted+=1;report('running')
                print(json.dumps({'channel_id':cid,'name':c['name'],'classification':result['classification'],'completed':len(records),'total':len(channels)},ensure_ascii=False),flush=True)
                break
            finally:lock.close()
        time.sleep(3)
    report('complete' if len(records)==len(channels) else 'partial')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        path=ROOT/'channel-quality-audit.json'
        if path.exists():
            report=json.loads(path.read_text());report.update(state='error',error_type=type(exc).__name__,updated=time.time());save(path,report)
        print(json.dumps({'event':'audit_error','type':type(exc).__name__}),flush=True)
        raise SystemExit(1)
