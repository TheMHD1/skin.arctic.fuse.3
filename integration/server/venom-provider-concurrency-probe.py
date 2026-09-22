"""Bounded direct-provider decoder test, run via Dispatcharr's Django shell.

No gateway limit changes. Never log URLs, credentials, or raw decoder output.
Tests two already-successful gateway channel identities against their sources.
"""
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import signal
import threading
import time
import urllib.request
from types import SimpleNamespace
from apps.channels.models import Channel

def request(path,data=None,token=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    req=urllib.request.Request('http://127.0.0.1:9191'+path,
        data=json.dumps(data).encode() if data is not None else None,headers=headers)
    with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)

def decode(source,seconds,realtime=False):
    started=time.monotonic()
    cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-threads','1','-filter_threads','1',
         '-rw_timeout','12000000','-analyzeduration','3000000','-probesize','2097152',
         *(['-re'] if realtime else []),'-i',source.url,'-t',str(seconds),'-map','0:v:0','-an','-vf','scale=16:16',
         '-progress','pipe:1','-f','null','-']
    try:
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=seconds+25)
        frames=max([int(n) for n in re.findall(r'^frame=(\d+)',result.stdout,re.M)] or [0])
        decoded=max([int(n)/1000000 for n in re.findall(r'^out_time_us=(\d+)',result.stdout,re.M)] or [0])
        return dict(source_id=source.stream_id,exit_code=result.returncode,frames=frames,
                    http_errors=sorted(set(re.findall(r'HTTP error (\d{3})',result.stderr))),
                    decoded_seconds=round(decoded,2),wall_seconds=round(time.monotonic()-started,2),
                    started=started,ended=time.monotonic())
    except subprocess.TimeoutExpired:
        return dict(source_id=source.stream_id,result='timeout',started=started,ended=time.monotonic())

def wall_decode(source,seconds):
    """No media-time cutoff: verify a live decoder until our wall deadline."""
    started=time.monotonic();samples=[];frames=0
    cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-threads','1','-filter_threads','1',
         '-rw_timeout','12000000','-analyzeduration','3000000','-probesize','2097152',
         *(['-re'] if isinstance(source.stream_id,str) and ':' in source.stream_id else []),
         '-i',source.url,'-map','0:v:0','-an','-vf','scale=16:16','-stats_period','1',
         '-progress','pipe:1','-f','null','-']
    process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    def collect():
        nonlocal frames
        for line in process.stdout:
            if line.startswith('frame='):frames=int(line.split('=',1)[1])
            if line.startswith('progress='):samples.append((time.monotonic()-started,frames))
    reader=threading.Thread(target=collect,daemon=True);reader.start()
    alive=False
    try:
        try:process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:alive=True
        elapsed=time.monotonic()-started
        observed=list(samples)
    finally:
        if process.poll() is None:process.send_signal(signal.SIGINT)
        try:process.wait(timeout=4)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        reader.join(timeout=2);process.stdout.close()
    recent=[frame for stamp,frame in observed if stamp>=seconds-10]
    advancing=len(recent)>=2 and recent[-1]>recent[0]
    return dict(source_id=source.stream_id,alive_at_deadline=alive,frames=frames,
                advancing_final_10s=advancing,last_progress_seconds=round(observed[-1][0],2) if observed else None,
                wall_seconds=round(elapsed,2),passed=alive and advancing and bool(observed) and elapsed-observed[-1][0]<5)

def main():
    secret=json.loads(Path('/data/venom-credentials.json').read_text())
    token=request('/api/accounts/token/',{'username':secret['admin_user'],'password':secret['admin_password']})['access']
    stats=request('/proxy/stats/',token=token)
    for key,rows,count in [('live','channels','count'),('vod','vod_connections','total_connections'),('catchup','timeshift_sessions','total_connections')]:
        section=stats.get(key,{})
        if section.get(count)!=0 or section.get(rows)!=[]:
            print(json.dumps({'event':'deferred','reason':'gateway_busy_or_unknown'}),flush=True);return
    sources=[]
    mode=os.environ.get('VENOM_PROBE_MODE','live')
    mixed=mode in ('mixed','mixedpair','wallmixed')
    if mode in ('wall','wallmixed','wallsolo','wallshare'):
        sources=[]
        for cid in ([96] if mixed or mode in ('wallsolo','wallshare') else [96,55,40,46,47,53,58,61]):
            sources.append(Channel.objects.get(pk=cid).streams.order_by('channelstream__order').first())
        if mode=='wallshare':
            import urllib.parse
            url='http://127.0.0.1:9191/live/'+urllib.parse.quote(secret['stream_user'],safe='')+'/'+urllib.parse.quote(secret['stream_password'],safe='')+'/96.ts'
            sources=[SimpleNamespace(stream_id='shared'+str(i),url=url) for i in range(2)]
        if mixed:
            from apps.vod.models import M3UMovieRelation, M3UEpisodeRelation
            for kind,model in [('movie',M3UMovieRelation),('episode',M3UEpisodeRelation)]:
                relation=model.objects.filter(m3u_account__name='Venom TV').order_by('-last_seen').first()
                sources.append(SimpleNamespace(stream_id=kind+':'+str(relation.stream_id),url=relation.get_stream_url()))
        for count in ([1] if mode=='wallsolo' else [2] if mode=='wallshare' else [2,3] if mixed else [2,4,6,8]):
            stats=request('/proxy/stats/',token=token)
            if stats.get('live',{}).get('count')!=0 or stats.get('vod',{}).get('total_connections')!=0:
                print(json.dumps({'event':'deferred','reason':'viewer_started'}),flush=True);return
            print(json.dumps({'event':'wall_stage_started','concurrency':count}),flush=True)
            with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
                futures=[pool.submit(wall_decode,source,90 if mode in ('wallsolo','wallshare') else 60) for source in sources[:count]]
                if mode=='wallshare':
                    time.sleep(10)
                    live=request('/proxy/stats/',token=token).get('live',{})
                    print(json.dumps({'event':'sharing_stats','channels':live.get('count'),'client_counts':[len(c.get('clients',[])) for c in live.get('channels',[])]}),flush=True)
                results=[future.result() for future in futures]
            passed=all(r['passed'] for r in results)
            print(json.dumps({'event':'wall_stage','mixed':mixed,'concurrency':count,'passed':passed,'results':results}),flush=True)
            if not passed:return
            time.sleep(8)
        return
    duration=90 if mode=='sustained' else 60 if mode in ('confirm','boundary','mixed','mixedpair','pair') else 20
    for cid in ([96] if mixed else [96,55] if mode=='pair' else [96,55,40,46] if mode=='boundary' else [96,55,166,40,43,46,47,53]):
        source=Channel.objects.get(pk=cid).streams.order_by('channelstream__order').first()
        if source is None or not source.url:raise ValueError('Missing source')
        sources.append(source)
    if mixed:
        from apps.vod.models import M3UMovieRelation, M3UEpisodeRelation
        for kind,model in [('movie',M3UMovieRelation),('episode',M3UEpisodeRelation)]:
            if mode=='mixedpair' and kind=='episode':continue
            relation=model.objects.filter(m3u_account__name='Venom TV').order_by('-last_seen').first()
            if relation is None:raise ValueError('Missing VOD source')
            sources.append(SimpleNamespace(stream_id=kind+':'+str(relation.stream_id),url=relation.get_stream_url()))
    if len({source.stream_id for source in sources})!=len(sources):raise ValueError('Need distinct provider channels')
    for source in sources:
        result=decode(source,3)
        print(json.dumps({'event':'baseline',**result}),flush=True)
        if result.get('exit_code')!=0 or result.get('decoded_seconds',0)<2:
            print(json.dumps({'event':'aborted','reason':'baseline_not_working'}),flush=True);return
        time.sleep(4)
    for count in ([2] if mode in ('pair','mixedpair') else [3] if mixed else [3,4] if mode=='boundary' else [5,6] if mode=='confirm' else [8] if mode=='sustained' else [2,3,4,6,8]):
        stats=request('/proxy/stats/',token=token)
        if stats.get('live',{}).get('count')!=0 or stats.get('vod',{}).get('total_connections')!=0 or stats.get('catchup',{}).get('total_connections')!=0:
            print(json.dumps({'event':'deferred','reason':'viewer_started'}),flush=True);return
        print(json.dumps({'event':'stage_started','concurrency':count,'realtime_seconds':duration}),flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
            results=list(pool.map(lambda source:decode(source,duration,True),sources[:count]))
        overlap=max(0,min(r['ended'] for r in results)-max(r['started'] for r in results))
        passed=all(r.get('exit_code')==0 and r.get('decoded_seconds',0)>=duration-1 and r.get('frames',0)>=100 for r in results) and overlap>=duration-1
        print(json.dumps({'event':'mixed_stage' if mixed else 'distinct_live_stage','concurrency':count,'passed':passed,'process_overlap_seconds':round(overlap,2),'results':results}),flush=True)
        if not passed:
            print(json.dumps({'event':'stopped','reason':'first_unstable_stage_not_proof_of_account_limit'}),flush=True);return
        time.sleep(8)

try:main()
except Exception as exc:print(json.dumps({'event':'test_error','type':type(exc).__name__}),flush=True)
