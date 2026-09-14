"""Read-only provider catalogue observations; run in Dispatcharr Django shell.

No streams opened, no URLs logged, no visibility mutation. Absence is only
corroborating evidence, never sufficient by itself to hide a channel.
"""
import json
from pathlib import Path
import sqlite3
import time
import urllib.parse
import urllib.request
from apps.channels.models import Channel
from apps.m3u.models import M3UAccount

def main():
    account=M3UAccount.objects.get(name='Venom TV')
    parts=urllib.parse.urlsplit(account.server_url)
    query=urllib.parse.urlencode(dict(username=account.username,password=account.password,action='get_live_streams'))
    url=urllib.parse.urlunsplit((parts.scheme,parts.netloc,'/player_api.php',query,''))
    with urllib.request.urlopen(url,timeout=30) as response:
        body=response.read(32*1024*1024+1)
    if len(body)>32*1024*1024:raise ValueError('Catalogue exceeds bound')
    rows=json.loads(body)
    if not isinstance(rows,list):raise ValueError('Not a catalogue')
    ids={str(row['stream_id']) for row in rows if isinstance(row,dict) and str(row.get('stream_id','')).isdigit()}
    # A login/error body, empty feed, or unexpectedly truncated listing must not
    # create thousands of false absence observations.
    if len(ids)<1000 or len(ids)<len(rows)*0.95:raise ValueError('Untrusted catalogue shape/count')
    path=Path('/data/provider-presence.sqlite3')
    db=sqlite3.connect(path)
    db.execute('create table if not exists runs (time real primary key, provider_count integer)')
    db.execute('create table if not exists observations (channel_id integer,time real,present integer,source_ids text,primary key(channel_id,time))')
    previous=db.execute('select provider_count from runs order by time desc limit 1').fetchone()
    if previous and len(ids)<previous[0]*0.75:raise ValueError('Large catalogue shrink needs review')
    stamp=time.time();counts={'present':0,'absent':0,'unmapped':0};records=[]
    channels=Channel.objects.filter(streams__m3u_account=account).distinct().prefetch_related('streams')
    for channel in channels:
        source_ids={str(source.stream_id) for source in channel.streams.all()
                    if source.m3u_account_id==account.pk and source.stream_id is not None}
        present=int(bool(source_ids & ids)) if source_ids else None
        counts['unmapped' if present is None else 'present' if present else 'absent']+=1
        records.append((channel.pk,stamp,present,json.dumps(sorted(source_ids))))
    with db:
        db.execute('insert into runs values (?,?)',(stamp,len(ids)))
        db.executemany('insert into observations values (?,?,?,?)',records)
        # Thirty daily observations are ample for multi-day corroboration.
        db.execute('delete from observations where time<?',(stamp-30*86400,))
        db.execute('delete from runs where time<?',(stamp-30*86400,))
    path.chmod(0o600)
    print(json.dumps({'event':'provider_presence_audit','provider_channels':len(ids),**counts,'hiding_enabled':False}),flush=True)

try:main()
except Exception as exc:
    print(json.dumps({'event':'presence_audit_error','type':type(exc).__name__}),flush=True)
    raise SystemExit(1)
