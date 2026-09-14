#!/usr/bin/env python3
"""Resolve exact native channel IDs and seed each account once, resumably.

Existing favourites are retained. Completed records are never re-added, so a
later user removal is respected. All requests use the local admin helper;
credentials and playback URLs are never emitted.
"""
import argparse
import fcntl
import json
from pathlib import Path
import runpy
import sqlite3
import time
from urllib.parse import urlencode

ROOT=Path('/data/config/iptv-venom')
clean_name=runpy.run_path(str(Path(__file__).with_name('venom-channel-names.py')))['clean_name']

def number(value):
    try:return str(int(float(value))) if float(value).is_integer() else str(value)
    except (ValueError,TypeError):return str(value)

def resolve(groups,channels):
    index={};clean_index={}
    for channel in channels:
        num=number(channel.get('ChannelNumber') or channel.get('Number'))
        index.setdefault((channel['Name'].strip(),num),[]).append(channel)
        clean_index.setdefault((clean_name(channel['Name']),num),[]).append(channel)
    result=[]
    for group in groups:
        rows=[]
        for source in group['channels']:
            matches=index.get((source['name'].strip(),number(source['num'])),[])
            if not matches:
                matches=clean_index.get((clean_name(source['name']),number(source['num'])),[])
            if len(matches)!=1:raise ValueError('Channel identity missing or ambiguous: '+source['name'])
            rows.append({'id':matches[0]['Id'],'name':matches[0]['Name'],'gateway_id':source['stream_id']})
        result.append({'id':group['id'],'name':group['name'],'channels':rows})
    return result

def user_items(api,uid,ids):
    rows=[]
    for offset in range(0,len(ids),80):
        query=urlencode(dict(Ids=','.join(ids[offset:offset+80]),Limit=80,EnableImages=False,EnableUserData=True))
        rows.extend(api('/Users/'+uid+'/Items?'+query)['Items'])
    return rows

def verify_favourites(expected,items):
    actual={item['Id']:bool(item.get('UserData',{}).get('IsFavorite')) for item in items}
    if set(actual)!=set(expected) or not all(actual.values()):
        raise RuntimeError('Favourite verification failed')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    lock=(ROOT/'seed-favourites.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:print('Seed already running',flush=True);return
    api=runpy.run_path('/root/iptv-jellyfin-admin.py')['api']
    catalogue=json.loads((ROOT/'curated-channels.json').read_text());channels=[]
    for offset in range(0,20000,500):
        page=api('/LiveTv/Channels?'+urlencode(dict(StartIndex=offset,Limit=500,AddCurrentProgram=False,EnableImages=False)))
        channels.extend(page['Items'])
        if offset+len(page['Items'])>=page['TotalRecordCount']:break
    else:raise ValueError('Unexpected channel count')
    groups=resolve(catalogue['groups'],channels)
    ids=list(dict.fromkeys(c['id'] for g in groups for c in g['channels']))
    output={'version':1,'groups':groups,'unique_channels':len(ids)}
    target=ROOT/'curated-native-channels.json';tmp=target.with_suffix('.tmp')
    tmp.write_text(json.dumps(output,ensure_ascii=False,indent=2));tmp.chmod(0o600);tmp.replace(target)
    print(json.dumps({'event':'resolved','channels':len(ids),'groups':len(groups),'apply':args.apply}),flush=True)
    if not args.apply:return
    db=sqlite3.connect(ROOT/'seed-favourites.sqlite3')
    db.execute('create table if not exists seeds (user_id text, item_id text, was_favourite integer, status text, updated real, primary key(user_id,item_id))')
    for user in api('/Users'):
        uid=user['Id'];added=retained=skipped=0;processed=[]
        if not user['Policy'].get('EnableLiveTvAccess'):continue
        visible=user_items(api,uid,ids)
        for item in visible:
            old=db.execute('select status from seeds where user_id=? and item_id=?',(uid,item['Id'])).fetchone()
            if old and old[0]=='done':skipped+=1;continue
            favourite=bool(item.get('UserData',{}).get('IsFavorite'))
            if not old:
                db.execute('insert into seeds values (?,?,?,?,?)',(uid,item['Id'],int(favourite),'pending',time.time()));db.commit()
            if not favourite:
                api('/Users/'+uid+'/FavoriteItems/'+item['Id'],method='POST');added+=1
            else:retained+=1
            processed.append(item['Id'])
        # Verify additions from this run, without treating previous user removals
        # as failures or undoing those choices on a resumed run.
        if processed:
            verify_favourites(processed,user_items(api,uid,processed))
            db.executemany('update seeds set status=?,updated=? where user_id=? and item_id=?',
                [('done',time.time(),uid,iid) for iid in processed]);db.commit()
        print(json.dumps({'event':'user_seeded','user_id':uid,'visible':len(visible),'added':added,'existing':retained,'previously_seeded':skipped}),flush=True)
    print(json.dumps({'event':'seed_finished','channels':len(ids)}),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'event':'seed_error','error':type(exc).__name__}),flush=True)
        raise SystemExit(1)
