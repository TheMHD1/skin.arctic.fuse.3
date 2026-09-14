"""Corroborate fresh provider-catalogue absences; never change visibility.

Run in Dispatcharr under the CT's channel-checker flock. At most two single-
source channels per daily run. No URLs, credentials or decoder logs persisted.
"""
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path('/data')

def fresh_absences(rows,now):
    latest={}
    for cid,stamp,present in rows:
        if cid not in latest or stamp>latest[cid][0]:latest[cid]=(stamp,present)
    return [cid for cid,(stamp,present) in latest.items()
            if present==0 and 0<=now-stamp<=36*3600]

def provider_idle(payload):
    info=payload.get('user_info',{})
    return (str(info.get('auth'))=='1' and str(info.get('status','')).lower()=='active'
            and str(info.get('active_cons'))=='0')

def missing_status(code,origin,expected):
    # Redirected CDN errors do not establish a missing resource at this origin.
    return code if code in (404,410) and origin==expected else None

def json_request(url,headers=None,data=None):
    req=urllib.request.Request(url,headers=headers or {},data=data)
    with urllib.request.urlopen(req,timeout=12) as response:
        body=response.read(2*1024*1024+1)
    if len(body)>2*1024*1024:raise ValueError('Response too large')
    return json.loads(body)

def control_decodes(url):
    command=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-threads','1',
             '-rw_timeout','55000000','-analyzeduration','3000000','-probesize','2097152',
             '-i',url,'-map','0:v:0','-frames:v','3','-an','-progress','pipe:1','-f','null','-']
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=58)
        frames=max([int(n) for n in re.findall(r'^frame=(\d+)',result.stdout,re.M)] or [0])
        return result.returncode==0 and frames>=3
    except subprocess.TimeoutExpired:return False

def main():
    from apps.channels.models import Channel
    from apps.m3u.models import M3UAccount
    now=time.time()
    with sqlite3.connect('file:/data/provider-presence.sqlite3?mode=ro',uri=True) as db:
        candidates=fresh_absences(db.execute('select channel_id,time,present from observations'),now)
        present={cid for cid,stamp,p in db.execute('select channel_id,time,present from observations where time=(select max(time) from runs)') if p==1}
    if not candidates:
        print(json.dumps({'event':'missing_check_finished','fresh_absences':0,'probed':0}));return
    if os.environ.get('VENOM_PROVIDER_CHECK_LOCKED')!='1':
        print(json.dumps({'event':'missing_check_deferred','reason':'use_serialized_service'}));return
    account=M3UAccount.objects.get(name='Venom TV')
    base=urllib.parse.urlsplit(account.server_url)
    origin=(base.scheme,base.hostname,base.port)
    provider_url=urllib.parse.urlunsplit((base.scheme,base.netloc,'/player_api.php',urllib.parse.urlencode({'username':account.username,'password':account.password}),''))
    secret=json.loads((ROOT/'venom-credentials.json').read_text())
    token=json_request('http://127.0.0.1:9191/api/accounts/token/',{'Content-Type':'application/json'},json.dumps({'username':secret['admin_user'],'password':secret['admin_password']}).encode())['access']
    def idle():
        stats=json_request('http://127.0.0.1:9191/proxy/stats/',{'Authorization':'Bearer '+token})
        for section,rows,count in [('live','channels','count'),('vod','vod_connections','total_connections'),('catchup','timeshift_sessions','total_connections')]:
            value=stats.get(section,{})
            if value.get(count)!=0 or value.get(rows)!=[]:return False
        return provider_idle(json_request(provider_url))
    def source(channel):
        sources=list(channel.streams.all())
        if len(sources)!=1 or sources[0].m3u_account_id!=account.pk:return None
        parts=urllib.parse.urlsplit(sources[0].url)
        return sources[0] if (parts.scheme,parts.hostname,parts.port)==origin else None
    controls=[]
    for channel in Channel.objects.filter(pk__in=present,streams__m3u_account=account).distinct().prefetch_related('streams').order_by('pk')[:30]:
        item=source(channel)
        if item:controls.append((channel.pk,item.url))
        if len(controls)>=3:break
    db=sqlite3.connect(ROOT/'provider-negative-evidence.sqlite3')
    (ROOT/'provider-negative-evidence.sqlite3').chmod(0o600)
    db.execute('create table if not exists observations (channel_id integer,time real,record text)')
    probed=0
    for channel in Channel.objects.filter(pk__in=candidates,streams__m3u_account=account).distinct().prefetch_related('streams').order_by('pk'):
        if probed>=2:break
        last=db.execute('select max(time) from observations where channel_id=?',(channel.pk,)).fetchone()[0]
        if last and now-last<24*3600:continue
        item=source(channel)
        # Event/temporary feeds need a separate schedule-aware decision.
        if not item or re.search(r'\b(event|live\s*\d+|ppv|cup|match|backup)\b|مباراة|بطولة',channel.name,re.I):continue
        if not idle():break
        control=None
        for cid,url in controls:
            if not idle():break
            if control_decodes(url):control=(cid,url);break
        if not control or not idle():break
        code=None
        try:
            # Disable redirects: only an origin 404/410 can qualify.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self,*args,**kwargs):return None
            opener=urllib.request.build_opener(NoRedirect)
            with opener.open(item.url,timeout=55) as response:response.read(1)
        except urllib.error.HTTPError as exc:
            parts=urllib.parse.urlsplit(exc.url)
            code=missing_status(exc.code,(parts.scheme,parts.hostname,parts.port),origin)
            exc.close()
        except (OSError,urllib.error.URLError):pass
        probed+=1
        after=bool(code and idle() and control_decodes(control[1]))
        record={'time':time.time(),'capacity_available':True,'control_ok':after,
                'control_channel_id':control[0],'http_status':code,'response_origin':'provider',
                'absent_from_provider_catalogue':True,'decoded_video_frames':0}
        with db:db.execute('insert into observations values (?,?,?)',(channel.pk,record['time'],json.dumps(record)))
        print(json.dumps({'event':'missing_check_observation','channel_id':channel.pk,'controlled_missing':after,'http_status':code}),flush=True)
    print(json.dumps({'event':'missing_check_finished','fresh_absences':len(candidates),'probed':probed,'visibility_changed':False}),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'event':'missing_check_error','type':type(exc).__name__}),flush=True)
        raise SystemExit(1)
