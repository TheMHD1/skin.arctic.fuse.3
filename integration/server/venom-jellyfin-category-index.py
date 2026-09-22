#!/usr/bin/env python3
"""Register provider genre entities using Jellyfin's normal by-name API.

Fixes the gap before the full-library post-scan GenresValidator runs. No DB
writes, media moves, playback requests, library grants or item-ID changes.
Native /Genres remains responsible for library visibility and nonempty counts.
"""
import fcntl
import json
from pathlib import Path
import runpy
import urllib.parse
import urllib.request

ROOT=Path('/data/config/iptv-venom')

def category_names(rows):
    return sorted({'Venom: '+r['category_name'] for r in rows
                   if isinstance(r.get('category_name'),str) and r['category_name'].strip()})

def main():
    with (ROOT/'category-index.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        api=runpy.run_path('/root/iptv-jellyfin-admin.py')['api']
        secret=json.loads(Path('/data/config/dispatcharr/venom-credentials.json').read_text())
        rows=[]
        for action in ('get_vod_categories','get_series_categories'):
            query=urllib.parse.urlencode(dict(username=secret['stream_user'],password=secret['stream_password'],action=action))
            with urllib.request.urlopen('http://192.168.2.172:9191/player_api.php?'+query,timeout=30) as response:
                raw=response.read(1024*1024+1)
            if len(raw)>1024*1024:raise ValueError('Category response exceeds limit')
            data=json.loads(raw)
            if not isinstance(data,list):raise ValueError('Invalid category response')
            rows.extend(data)
        names=category_names(rows)
        if len(names)>1000:raise ValueError('Unexpected category count')
        # The legacy GET /Genres/{name} interprets every hyphen as a slug,
        # preventing creation of many real provider names. The admin-only
        # endpoint uses the same library manager directly, with bounded input.
        result=api('/VenomCategories/Maintenance/Register',names,'POST')
        if result.get('Registered',result.get('registered'))!=len(names):
            raise ValueError('Incomplete category registration')
        # New by-name entities need their normal metadata lifecycle once to
        # populate PresentationUniqueKey. Without it JF12 collapses all new
        # categories into one group. Queue ONLY those not previously requested,
        # no scraping/images/media refresh and no repeated 30-minute fanout.
        state_path=ROOT/'category-refresh-requested.json'
        try:requested=set(json.loads(state_path.read_text()))
        except FileNotFoundError:requested=set()
        genres=api('/Items?IncludeItemTypes=Genre&Recursive=true&SearchTerm=Venom&Limit=1000')['Items']
        queued=0
        for genre in genres:
            if genre.get('Name') not in names or genre['Id'] in requested:continue
            api('/Items/'+genre['Id']+'/Refresh?MetadataRefreshMode=None&ImageRefreshMode=None',method='POST')
            requested.add(genre['Id']);queued+=1
            temporary=state_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(sorted(requested)));temporary.replace(state_path)
        print(json.dumps({'event':'provider_category_index_ready','categories':len(names),'new_genre_refreshes':queued},ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Never put credential-bearing request URLs in journal output.
        print(json.dumps({'event':'provider_category_index_error','error':type(exc).__name__}))
        raise SystemExit(1)
