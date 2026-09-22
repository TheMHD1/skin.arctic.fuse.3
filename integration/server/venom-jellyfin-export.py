#!/usr/bin/env python3
"""Mirror provider metadata into private STRM/NFO libraries; never download video.

Run on media CT102. Series discovery is resumable and time-bounded. Existing
files are only replaced when changed; removed provider items are not deleted.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

CONFIG=Path('/data/config/iptv-venom')
ROOT=Path('/data/config/jellyfin/venom-catalogue')
BASE='http://192.168.2.172:9191'
MIN_FREE_BYTES=8*1024*1024*1024
DIRTY_MARKED=set()

def enough_space():
    free=shutil.disk_usage(CONFIG).free
    if free<MIN_FREE_BYTES:
        log('low_space_deferred',free_bytes=free,minimum_bytes=MIN_FREE_BYTES)
        return False
    return True


def log(event,**fields):
    print(json.dumps({'time':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'event':event,**fields},ensure_ascii=False),flush=True)


def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
    try:
        if path.read_bytes()==data:return False
    except FileNotFoundError:pass
    # Durable dirty generation, once per changed library per process. Write
    # before content so a crash cannot leave unannounced catalogue changes.
    try:kind=path.relative_to(ROOT).parts[0]
    except ValueError:kind=None
    if kind in ('movies','series') and kind not in DIRTY_MARKED:
        atomic(CONFIG/('refresh-dirty-'+kind),str(time.time_ns()).encode())
        DIRTY_MARKED.add(kind)
    fd,tmp=tempfile.mkstemp(prefix='.venom-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:out.write(data)
        os.chmod(tmp,0o640)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return True


def text(value):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str('' if value is None else value))


def category_names(row,categories):
    ids=row.get('category_ids') or []
    if not isinstance(ids,list):ids=[ids]
    ids=[row.get('category_id'),*ids]
    return list(dict.fromkeys(categories[str(x)] for x in ids if str(x) in categories))


def nfo(tag,row,category='',season=None,episode=None):
    root=ET.Element(tag)
    def add(key,value):
        if value not in (None,''):ET.SubElement(root,key).text=text(value)
    add('title',row.get('name') or row.get('title'))
    add('plot',row.get('plot') or '')
    year=str(row.get('year') or row.get('release_date') or row.get('releaseDate') or '')[:4]
    if year.isdigit():add('year',year)
    try:
        rating=float(row.get('rating') or 0)
        if 0<rating<=10:add('rating',rating)
    except (ValueError,TypeError):pass
    for genre in re.split(r'[,/]',str(row.get('genre') or '')):
        if genre.strip():add('genre',genre.strip())
    for name in ([category] if isinstance(category,str) else category):
        if name:add('genre','Venom: '+name);add('tag',name)
    add('tag','Venom TV')
    poster=row.get('stream_icon') or row.get('cover') or row.get('movie_image')
    if isinstance(poster,str) and poster.startswith(('http://','https://')):
        ET.SubElement(root,'thumb',{'aspect':'poster'}).text=poster
    if season is not None:add('season',season)
    if episode is not None:add('episode',episode)
    # No external IDs: prevent accidental cross-library merging or scraper fanout.
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def ident(value):
    value=str(value)
    if not value.isdigit():raise ValueError('Invalid catalogue ID')
    return value


def stream_url(auth,kind,item_id,ext):
    ext=ext or 'mp4'
    if not re.fullmatch(r'[a-zA-Z0-9]{1,8}',ext):raise ValueError('Invalid container')
    item_id=ident(item_id)
    # Jellyfin probes a STRM before playback. Keep both HTTP clients in the same
    # gateway session instead of consuming a second provider slot at handoff.
    session='jf_'+hashlib.sha256((auth['username']+'|'+kind+'|'+item_id).encode()).hexdigest()[:24]
    return BASE+'/'+kind+'/'+urllib.parse.quote(auth['username'],safe='')+'/'+urllib.parse.quote(auth['password'],safe='')+'/'+item_id+'.'+ext+'?session_id='+session+'\n'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--canary',action='store_true')
    parser.add_argument('--max-seconds',type=int,default=2400)
    parser.add_argument('--series-limit',type=int,default=10000)
    parser.add_argument('--rewrite-sessions',action='store_true')
    args=parser.parse_args()
    CONFIG.mkdir(parents=True,exist_ok=True)
    if not enough_space():return
    lock=open(CONFIG/'catalogue-export.lock','a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:log('already_running');return
    secret=json.loads(Path('/data/config/dispatcharr/venom-credentials.json').read_text())
    auth={'username':secret['stream_user'],'password':secret['stream_password']}
    if args.rewrite_sessions:
        changed=0
        for path in ROOT.rglob('*.strm'):
            old=urllib.parse.urlsplit(path.read_text().strip())
            parts=old.path.split('/')
            if old.netloc!=urllib.parse.urlsplit(BASE).netloc or len(parts)!=5 or parts[1] not in ('movie','series'):continue
            if parts[2:4]!=[urllib.parse.quote(auth['username'],safe=''),urllib.parse.quote(auth['password'],safe='')]:continue
            item_id,ext=parts[4].rsplit('.',1)
            changed+=atomic(path,stream_url(auth,parts[1],item_id,ext).encode())
        log('session_urls_updated',files=changed);return
    def api(action,**kwargs):
        url=BASE+'/player_api.php?'+urllib.parse.urlencode({**auth,'action':action,**kwargs})
        with urllib.request.urlopen(url,timeout=35) as response:
            raw=response.read(48*1024*1024+1)
        if len(raw)>48*1024*1024:raise ValueError('Catalogue too large')
        return json.loads(raw)
    started=time.monotonic()
    db=sqlite3.connect(CONFIG/'catalogue-progress.sqlite3')
    db.execute('create table if not exists series (id text primary key, refreshed real, status text, episodes integer, error text)')
    movies=api('get_vod_streams')
    cats={str(x['category_id']):x['category_name'] for x in api('get_vod_categories')}
    changed=count=errors=0
    for index,row in enumerate(movies):
        if index%200==0 and not enough_space():return
        if args.canary and str(row['stream_id'])!='15350':continue
        try:
            item_id=ident(row['stream_id']);directory=ROOT/'movies'/('Movie '+item_id)
            changed+=atomic(directory/'movie.nfo',nfo('movie',row,category_names(row,cats)))
            changed+=atomic(directory/'movie.strm',stream_url(auth,'movie',item_id,row.get('container_extension')).encode())
            count+=1
        except Exception as exc:
            errors+=1;log('movie_error',id=row.get('stream_id'),error=type(exc).__name__)
    log('movies_exported',movies=count,changed_files=changed,errors=errors,seconds=round(time.monotonic()-started,2))
    all_series=api('get_series')
    cats={str(x['category_id']):x['category_name'] for x in api('get_series_categories')}
    processed=episodes=0
    for row in all_series:
        if processed%20==0 and not enough_space():break
        item_id=ident(row['series_id'])
        if args.canary and item_id!='5739':continue
        if time.monotonic()-started>args.max_seconds or processed>=args.series_limit:break
        # Category/title metadata does not need an episode-detail fetch. Keep it
        # current even when successful series are within their weekly cooldown.
        directory=ROOT/'series'/('Series '+item_id)
        if directory.exists():atomic(directory/'tvshow.nfo',nfo('tvshow',row,category_names(row,cats)))
        old=db.execute('select refreshed,status from series where id=?',(item_id,)).fetchone()
        # Refresh successful series weekly, retry failures after six hours.
        if old and not args.canary and time.time()-old[0]<(604800 if old[1]=='ok' else 21600):continue
        try:
            detail=api('get_series_info',series_id=item_id)
            directory=ROOT/'series'/('Series '+item_id)
            atomic(directory/'tvshow.nfo',nfo('tvshow',row,category_names(row,cats)))
            total=0
            for season,items in (detail.get('episodes') or {}).items():
                season_no=int(ident(season))
                for ep in items:
                    number=int(ident(ep.get('episode_num')))
                    ep_id=ident(ep['id']);stem='S%02dE%03d'%(season_no,number)
                    folder=directory/('Season %02d'%season_no)
                    meta={**(ep.get('info') or {}),'title':ep.get('title') or stem}
                    atomic(folder/(stem+'.nfo'),nfo('episodedetails',meta,season=season_no,episode=number))
                    atomic(folder/(stem+'.strm'),stream_url(auth,'series',ep_id,ep.get('container_extension')).encode())
                    total+=1
            # Empty catalogues are retried; they may be transient provider failures.
            status='ok' if total else 'empty'
            db.execute('insert or replace into series values (?,?,?,?,?)',(item_id,time.time(),status,total,None));db.commit()
            processed+=1;episodes+=total
            if processed%20==0 or args.canary:log('series_progress',processed=processed,episodes=episodes,total_catalogue=len(all_series))
        except Exception as exc:
            db.execute('insert or replace into series values (?,?,?,?,?)',(item_id,time.time(),'error',0,type(exc).__name__));db.commit()
            processed+=1;log('series_error',id=item_id,error=type(exc).__name__)
        if not args.canary:time.sleep(0.35)
    state={'movies':count,'series_total':len(all_series),'series_processed_this_run':processed,'episodes_this_run':episodes,
           'series_status':dict(db.execute('select status,count(*) from series group by status').fetchall()),
           'updated':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'seconds':round(time.monotonic()-started,2)}
    atomic(CONFIG/'catalogue-status.json',json.dumps(state,indent=2).encode());log('run_finished',**state)


if __name__=='__main__':main()
