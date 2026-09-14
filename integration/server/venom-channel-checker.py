#!/usr/bin/env python3
"""Resumable idle-only decoder probes via the existing capacity-limited gateway.

One stream at a time with this account. Never mistakes a gateway error for a
provider-origin permanent failure; this worker does not change visibility.
"""
import argparse
import fcntl
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import urllib.parse
import urllib.request

ROOT=Path('/data/config/iptv-venom');BASE='http://192.168.2.172:9191'

def request(path,data=None,token=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    req=urllib.request.Request(BASE+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
    with urllib.request.urlopen(req,timeout=12) as response:return json.load(response)

def occupied(stats):
    # Missing or changed API shape fails closed, never interpreted as idle.
    for section in ('live','vod','catchup'):
        value=stats.get(section)
        if not isinstance(value,dict):return True
        row_key,count_key={'live':('channels','count'),'vod':('vod_connections','total_connections'),'catchup':('timeshift_sessions','total_connections')}[section]
        rows=value.get(row_key)
        count=value.get(count_key)
        if not isinstance(count,int) or not isinstance(rows,list):return True
        if count or rows:return True
    return False

def decoded_geometry(stderr):
    # Only accept the pre-scale decoded-frame filter, not a URL, container
    # claim, or the 16x16 diagnostic output. Never retain raw stderr.
    sizes=re.findall(r'\[Parsed_showinfo_0[^\]]*\][^\n]*\bn:\s*\d+[^\n]*\bs:(\d+)x(\d+)\b',stderr)
    if not sizes:return {}
    width,height=map(int,sizes[0])
    if not (16<=width<=16384 and 16<=height<=16384):return {}
    geometry={'decoded_width':width,'decoded_height':height}
    transfer=re.search(r'\[Parsed_showinfo_0[^\]]*\][^\n]*\bcolor_trc:(\S+)',stderr)
    if transfer and transfer[1] in ('smpte2084','arib-std-b67','bt709','iec61966-2-1','gamma22','gamma28'):
        geometry.update(decoded_transfer=transfer[1],decoded_hdr=transfer[1] in ('smpte2084','arib-std-b67'))
    return geometry

def probe(url,seconds):
    started=time.monotonic()
    cmd=['docker','exec','jellyfin','timeout','--signal=TERM','--kill-after=3',str(seconds),
         '/usr/lib/jellyfin-ffmpeg/ffmpeg','-hide_banner','-loglevel','info','-nostdin',
         # The longer retry must really allow a slow source to start. The outer
         # timeout still bounds the entire probe, including decoding/cleanup.
         '-rw_timeout',str(seconds*1000000),'-analyzeduration','3000000','-probesize','2097152',
         '-i',url,'-map','0:v:0','-frames:v','3','-an','-vf','showinfo=checksum=0,scale=16:16','-progress','pipe:1','-f','null','-']
    try:
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=seconds+8)
        frames=max([int(n) for n in re.findall(r'^frame=(\d+)',result.stdout,re.M)] or [0])
        status='working' if result.returncode==0 and frames>=3 else 'inconclusive_playback'
        return {'result':status,'decoded_video_frames':frames,'exit_code':result.returncode,'seconds':round(time.monotonic()-started,2),**decoded_geometry(result.stderr)}
    except subprocess.TimeoutExpired:
        return {'result':'inconclusive_timeout','decoded_video_frames':0,'seconds':round(time.monotonic()-started,2)}

def idle(token,grace=0):
    deadline=time.monotonic()+grace
    while True:
        if not occupied(request('/proxy/stats/',token=token)):return True
        if time.monotonic()>=deadline:return False
        time.sleep(2)

def coverage(ids, latest, now):
    counts=dict(working_fresh=0,working_stale=0,inconclusive=0,untested=0)
    ids={str(cid) for cid in ids}
    for cid in ids:
        row=latest.get(cid)
        if row is None:counts['untested']+=1
        elif row[1]=='working':
            counts['working_fresh' if 0<=now-row[0]<=7*86400 else 'working_stale']+=1
        else:counts['inconclusive']+=1
    return {'channels':len(ids),**counts}

def probe_order(channels, published, latest):
    # Give every existing favourite an initial test before more expansion or
    # repeated long retries. Stable sort preserves provider order within ties.
    def key(channel):
        cid=str(channel['stream_id']);last=latest.get(cid)
        return (last is not None,cid not in published,last[0] if last else 0)
    return sorted(channels,key=key)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=20);parser.add_argument('--probe',action='store_true');parser.add_argument('--summary',action='store_true');parser.add_argument('--scope',choices=('curated','catalogue'),default='curated');parser.add_argument('--channel-ids',help='Optional comma-separated gateway IDs; existing safety and cooldown rules still apply');args=parser.parse_args()
    if args.channel_ids and not re.fullmatch(r'\d+(?:,\d+)*',args.channel_ids):parser.error('Invalid channel IDs')
    if args.summary:
        db=sqlite3.connect('file:'+str(ROOT/'channel-health.sqlite3')+'?mode=ro',uri=True)
        rows=db.execute('select result,count(*) from observations where id in (select max(id) from observations group by channel_id) group by result').fetchall()
        count=sum(n for _,n in rows)
        total=len(json.loads((ROOT/'live-catalogue-redacted.json').read_text())['channels'])
        latest={str(cid):(stamp,result) for cid,stamp,result in db.execute('select channel_id,time,result from observations where id in (select max(id) from observations group by channel_id)')}
        now=time.time();scopes={}
        for name,filename in (('published','curated-channels.json'),('candidates','curated-candidates.json')):
            path=ROOT/filename
            if not path.exists():continue
            manifest=json.loads(path.read_text())
            scopes[name]=coverage((c['stream_id'] for g in manifest['groups'] for c in g['channels']),latest,now)
            scopes[name]['groups']={g['id']:coverage((c['stream_id'] for c in g['channels']),latest,now) for g in manifest['groups']}
        print(json.dumps({'tested_channels':count,'catalogue_channels':total,'not_yet_tested':max(0,total-count),'latest_results':dict(rows),'coverage':scopes,'visibility_changes_by_this_worker':False,'visibility_worker':'venom-hide-confirmed.py'}));return
    lock=(ROOT/'channel-checker.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return
    secret=json.loads(Path('/data/config/dispatcharr/venom-credentials.json').read_text())
    token=request('/api/accounts/token/',{'username':secret['admin_user'],'password':secret['admin_password']})['access']
    stats=request('/proxy/stats/',token=token)
    print(json.dumps({'event':'occupancy','busy':occupied(stats),'counts':{k:v.get('count',v.get('total_connections')) for k,v in stats.items() if isinstance(v,dict)}}),flush=True)
    if occupied(stats):return
    catalogue=json.loads((ROOT/'live-catalogue-redacted.json').read_text())
    curated=json.loads((ROOT/'curated-channels.json').read_text())
    priority={str(c['stream_id']) for g in curated['groups'] for c in g['channels']}
    published=set(priority)
    candidate_path=ROOT/'curated-candidates.json'
    if candidate_path.exists():
        candidates=json.loads(candidate_path.read_text())
        priority.update(str(c['stream_id']) for g in candidates['groups'] for c in g['channels'])
    channels=sorted(catalogue['channels'],key=lambda c:str(c['stream_id']) not in priority)
    if args.scope=='curated':channels=[c for c in channels if str(c['stream_id']) in priority]
    if args.channel_ids:channels=[c for c in channels if str(c['stream_id']) in set(args.channel_ids.split(','))]
    db=sqlite3.connect(ROOT/'channel-health.sqlite3')
    db.execute('create table if not exists observations (id integer primary key,channel_id text,time real,result text,record text)')
    db.execute('create index if not exists observations_channel_time on observations(channel_id,time)')
    latest={str(cid):(stamp,result) for cid,stamp,result in db.execute('select channel_id,time,result from observations where id in (select max(id) from observations group by channel_id)')}
    channels=probe_order(channels,published,latest)
    attempted=0
    for channel in channels:
        cid=str(channel['stream_id'])
        last=db.execute('select time,result from observations where channel_id=? order by time desc limit 1',(cid,)).fetchone()
        if last and time.time()-last[0]<(7*86400 if last[1]=='working' else 6*3600):continue
        if attempted>=args.limit:break
        if not args.probe:
            print(json.dumps({'event':'planned_probe','channel_id':cid,'name':channel['name']}),flush=True);attempted+=1;continue
        if not idle(token,12 if attempted else 0):
            print(json.dumps({'event':'deferred_occupied','attempted':attempted}),flush=True);break
        if not cid.isdigit():raise ValueError('Invalid channel ID')
        url=BASE+'/live/'+urllib.parse.quote(secret['stream_user'],safe='')+'/'+urllib.parse.quote(secret['stream_password'],safe='')+'/'+cid+'.ts'
        # First attempt is quick; inconclusive sources get a longer retry on a
        # later idle run after cooldown, rather than filling the provider slot.
        seconds=55 if last and last[1]!='working' else 22
        record=probe(url,seconds)
        record.update(channel_id=cid,time=time.time(),capacity_available=True,response_origin='gateway',probe_budget_seconds=seconds)
        db.execute('insert into observations(channel_id,time,result,record) values (?,?,?,?)',(cid,record['time'],record['result'],json.dumps(record)));db.commit()
        print(json.dumps({'event':'probe_finished',**record}),flush=True);attempted+=1
    print(json.dumps({'event':'run_finished','attempted':attempted,'mode':'probe' if args.probe else 'plan'}),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'event':'checker_error','error':type(exc).__name__}),flush=True);raise SystemExit(1)
