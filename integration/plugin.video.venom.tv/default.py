"""Small private XC catalogue client. Live TV remains Kodi's native PVR."""
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from urllib.parse import parse_qsl, urlencode, urlsplit, quote
from urllib.request import urlopen
import xbmc
import xbmcgui
import xbmcplugin
import xbmcvfs
sys.path.insert(0,os.path.dirname(__file__))
import venom_state

HANDLE=int(sys.argv[1]) if len(sys.argv)>1 and sys.argv[1].lstrip('-').isdigit() else -1
PARAMS=dict(parse_qsl(sys.argv[2].lstrip('?'))) if len(sys.argv)>2 and sys.argv[2].startswith('?') else {}
ROOT=xbmcvfs.translatePath('special://profile/addon_data/plugin.video.venom.tv')
os.makedirs(ROOT,exist_ok=True)

def auth():
    path=xbmcvfs.translatePath('special://profile/addon_data/pvr.iptvsimple/instance-settings-1.xml')
    url=ET.parse(path).getroot().find("setting[@id='m3uUrl']").text
    parts=urlsplit(url)
    params=dict(parse_qsl(parts.query))
    return parts.scheme+'://'+parts.netloc,{k:params[k] for k in ('username','password')}

BASE,AUTH=None,None
FAVORITES=None

def art_index_path(action):
    key=hashlib.sha256((BASE+'|'+AUTH['username']+'|'+action).encode()).hexdigest()
    return os.path.join(ROOT,'art-'+key+'.json')

def remember_category_art(action,data,stamp):
    if action not in ('get_vod_streams','get_series'):return
    path=art_index_path(action)
    try:
        with open(path) as source:
            existing=json.load(source)
            if existing.get('time')==stamp and 'featured' in existing:return
    except (OSError,ValueError,AttributeError):pass
    art={}
    for row in data:
        value=row.get('stream_icon') or row.get('cover')
        if isinstance(value,str) and value.startswith(('http://','https://')):
            for category in row.get('category_ids') or [row.get('category_id')]:
                art.setdefault(str(category),value)
    tmp=path+'.'+str(os.getpid())+'.tmp'
    with open(tmp,'w') as out:json.dump({'time':stamp,'art':art,'featured':ordered(data,order='recent')[:30]},out)
    os.replace(tmp,path)

def featured_rows(kind):
    try:
        with open(art_index_path('get_vod_streams' if kind=='movie' else 'get_series')) as source:
            data=json.load(source)
        if time.time()-data['time']<1800 and isinstance(data.get('featured'),list):return data['featured']
    except (OSError,ValueError,KeyError):pass
    return None

def category_art(kind):
    try:
        with open(art_index_path('get_vod_streams' if kind=='movie' else 'get_series')) as source:
            data=json.load(source)
        if time.time()-data['time']<86400:return data['art']
    except (OSError,ValueError,KeyError):pass
    return {}

def api(action,**params):
    query={'action':action,**params}
    key=hashlib.sha256(json.dumps([BASE,AUTH['username'],query],sort_keys=True).encode()).hexdigest()
    path=os.path.join(ROOT,key+'.json')
    cached=None
    try:
        with open(path) as f:cached=json.load(f)
        if time.time()-cached['time']<1800:
            if not params:remember_category_art(action,cached['data'],cached['time'])
            return cached['data']
    except (OSError,ValueError,KeyError):pass
    try:
        with urlopen(BASE+'/player_api.php?'+urlencode({**AUTH,**query}),timeout=20) as r:
            raw=r.read(32*1024*1024+1)
        if len(raw)>32*1024*1024:raise ValueError('Catalogue response too large')
        data=json.loads(raw)
        tmp=path+'.'+str(os.getpid())+'.tmp'
        stamp=time.time()
        with open(tmp,'w') as f:json.dump({'time':stamp,'data':data},f)
        os.replace(tmp,path)
        if not params:remember_category_art(action,data,stamp)
        return data
    except Exception:
        if cached and time.time()-cached.get('time',0)<86400:
            xbmc.log('Venom TV: using cached catalogue after network failure',xbmc.LOGWARNING)
            return cached['data']
        raise

def route(**params):return 'plugin://plugin.video.venom.tv/?'+urlencode(params)

def favorite_key(params):
    return hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()

def icon(name):return 'special://skin/extras/icons/'+name+'.png'

def add(label,params,folder=True,art=None,plot='',media=None,fanart=None,metadata=None,icon_name=None):
    # Native PVR playback is dispatched with Player.Open, not resolved as a
    # plugin stream; prevent Kodi waiting for a nonexistent resolved URL.
    if params.get('mode')=='channel':folder=True
    item=xbmcgui.ListItem(label=str(label))
    fallback='DefaultTVShows.png' if params.get('kind')=='series' else 'DefaultMovies.png'
    if params.get('mode')=='live':fallback='DefaultTVShows.png'
    if icon_name:fallback=icon(icon_name)
    item.setArt({'icon':fallback,'thumb':art or fallback,'poster':art or fallback,
                 'fanart':fanart or ''})
    info=item.getVideoInfoTag();info.setTitle(str(label));info.setPlot(plot)
    if media:info.setMediaType(media)
    metadata=metadata or {}
    year=str(metadata.get('year') or metadata.get('release_date') or metadata.get('releaseDate') or '')[:4]
    if year.isdigit() and 1800<=int(year)<=2200:info.setYear(int(year))
    genre=metadata.get('genre')
    if isinstance(genre,str) and genre:info.setGenres([x.strip() for x in re.split(r'[,/]',genre) if x.strip()])
    try:rating=float(metadata.get('rating') or 0)
    except (ValueError,TypeError):rating=0
    if 0<rating<=10:info.setRating(rating)
    for key,setter in [('season',info.setSeason),('episode_num',info.setEpisode)]:
        value=metadata.get(key)
        if str(value).isdigit():setter(int(value))
    if not folder:item.setProperty('IsPlayable','true')
    if params.get('mode') in ('play','seasons','items','channel') and 'start' not in params and not icon_name:
        entry={'label':str(label),'params':params,'folder':folder,'art':art,'plot':plot,'media':media,'fanart':fanart,'metadata':metadata}
        key=favorite_key(params)
        text=('Remove category bookmark' if key in (FAVORITES or {}) else 'Bookmark category on this Kodi') if params.get('mode')=='items' else 'Toggle Jellyfin favourite (all devices)'
        item.addContextMenuItems([(text,'RunPlugin('+route(mode='favorite',entry=json.dumps(entry,ensure_ascii=False,separators=(',',':')))+')')])
    xbmcplugin.addDirectoryItem(HANDLE,route(**params),item,folder)

def ident(value):
    value=str(value)
    if not value.isdigit():raise ValueError('Invalid item ID')
    return value

def search_text(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value)).casefold() if not unicodedata.combining(c) and c!='ـ')

def ordered(data,query='',order='name'):
    words=search_text(query).split()
    rows=[r for r in data if all(word in search_text(r.get('name','')) for word in words)]
    if order=='recent':
        def stamp(r):
            try:return int(r.get('added') or r.get('last_modified') or 0)
            except (ValueError,TypeError):return 0
        return sorted(rows,key=stamp,reverse=True)
    return sorted(rows,key=lambda r:str(r.get('name','')).casefold())

def main():
    global FAVORITES
    mode=PARAMS.get('mode','root')
    kind=PARAMS.get('kind','movie')
    if kind not in ('movie','series') and not (kind=='live' and mode=='channel'):raise ValueError('Invalid catalogue')
    FAVORITES=venom_state.read(ROOT).get('favorites',{})
    if mode=='root':
        add('Live TV — Categories & Channels',{'mode':'live'},plot='Category browser, channel grid and favourites. Your subscription allows one simultaneous stream.',icon_name='tv')
        add('Movies',{'mode':'categories','kind':'movie'},plot='All movies, search, recently added and provider categories.',icon_name='film')
        add('Series',{'mode':'categories','kind':'series'},plot='All series, search and provider categories, organized into seasons and episodes.',icon_name='layer-group')
        add('My favourites',{'mode':'favorites'},plot='Long-press a movie, show or category to add or remove it here.',icon_name='heart')
    elif mode=='favorites':
        xbmcplugin.endOfDirectory(HANDLE,succeeded=False)
        xbmc.executebuiltin('RunScript(special://home/addons/plugin.video.venom.tv/browser.py,favorites)');return
    elif mode=='favorite':
        entry=json.loads(PARAMS['entry'])
        if not isinstance(entry,dict) or not isinstance(entry.get('params'),dict):raise ValueError('Invalid favourite')
        allowed={'label','params','folder','art','plot','media','fanart','metadata'}
        if set(entry)-allowed:raise ValueError('Invalid favourite fields')
        args=entry['params']
        if args.get('mode') not in ('play','seasons','items','channel'):raise ValueError('Invalid favourite route')
        if args.get('kind') not in ('movie','series') and not (args.get('kind')=='live' and args.get('mode')=='channel'):raise ValueError('Invalid favourite kind')
        ident(args.get('id') if args.get('mode') in ('play','seasons','channel') else args.get('category'))
        if args.get('mode')=='items':
            added=venom_state.toggle_favorite(ROOT,favorite_key(args),entry)
        else:
            import shared_favorites
            shared=shared_favorites.from_kodi()
            if args.get('mode')=='channel' and not entry.get('metadata',{}).get('channelnumber'):
                result=json.loads(xbmc.executeJSONRPC(json.dumps({'jsonrpc':'2.0','id':1,'method':'PVR.GetChannelDetails','params':{'channelid':int(args['id']),'properties':['channelnumber']}})))
                entry['metadata']={**entry.get('metadata',{}),'channelnumber':result['result']['channeldetails']['channelnumber']}
            current=shared.resolve(entry)
            added=shared.set(entry,not bool(current.get('UserData',{}).get('IsFavorite')))
            xbmcgui.Window(10000).setProperty('Habibi.Home.Refresh',str(time.time_ns()))
        xbmcgui.Dialog().notification('Venom TV','Added to favourites' if added else 'Removed from favourites')
        xbmc.executebuiltin('Container.Refresh');return
    elif mode=='live':
        xbmcplugin.endOfDirectory(HANDLE,succeeded=False)
        xbmc.executebuiltin('RunScript(special://home/addons/plugin.video.venom.tv/browser.py,live)');return
    elif mode=='channel':
        result=json.loads(xbmc.executeJSONRPC(json.dumps({'jsonrpc':'2.0','id':1,'method':'Player.Open','params':{'item':{'channelid':int(ident(PARAMS['id']))}}})))
        if 'error' in result:raise RuntimeError('Native channel playback failed')
        xbmcplugin.endOfDirectory(HANDLE,succeeded=False);return
    elif mode=='categories':
        action='get_vod_categories' if kind=='movie' else 'get_series_categories'
        artwork=category_art(kind)
        add('Search all movies…' if kind=='movie' else 'Search all series…',{'mode':'search','kind':kind,'category':'all'},icon_name='magnifying-glass')
        add('Recently added to catalogue',{'mode':'items','kind':kind,'category':'all','order':'recent'},icon_name='clock')
        add('All movies — A–Z' if kind=='movie' else 'All series — A–Z',{'mode':'items','kind':kind,'category':'all'},icon_name='list-ul')
        for c in sorted(api(action),key=lambda r:r['category_name'].casefold()):
            add(c['category_name'],{'mode':'items','kind':kind,'category':ident(c['category_id'])},art=artwork.get(str(c['category_id'])),plot='Browse titles A–Z, search this category, or choose recently added. Artwork previews a title in this category.')
    elif mode in ('items','search','featured'):
        featured=mode=='featured'
        if featured:PARAMS.update({'category':'all','order':'recent'})
        action='get_vod_streams' if kind=='movie' else 'get_series'
        data=featured_rows(kind) if featured else None
        if data is None:data=api(action,**({} if PARAMS['category']=='all' else {'category_id':ident(PARAMS['category'])}))
        query=PARAMS.get('q','')
        if mode=='search':
            query=xbmcgui.Dialog().input('Search '+('all '+('movies' if kind=='movie' else 'series') if PARAMS['category']=='all' else 'this category'),defaultt=query).strip()
            if not query:
                xbmcplugin.endOfDirectory(HANDLE,succeeded=False);return
        order=PARAMS.get('order','name')
        data=ordered(data,query,order)
        start=max(0,int(PARAMS.get('start','0')))
        xbmcplugin.setContent(HANDLE,'movies' if kind=='movie' else 'tvshows')
        page_size=30 if featured else 100
        if start and not featured:
            add('Previous page',{'mode':'items','kind':kind,'category':PARAMS['category'],'start':max(0,start-100),'q':query,'order':order},icon_name='arrow-left')
        if start==0 and not featured:
            add('Search…',{'mode':'search','kind':kind,'category':PARAMS['category']},icon_name='magnifying-glass')
            add('Sort: Recently added' if order=='name' else 'Sort: A–Z',{'mode':'items','kind':kind,'category':PARAMS['category'],'order':'recent' if order=='name' else 'name','q':query},icon_name='sort3')
        for row in data[start:start+page_size]:
            if kind=='movie':
                args={'mode':'play','kind':kind,'id':ident(row['stream_id']),'ext':row.get('container_extension') or 'mp4','title':row['name']}
            else:args={'mode':'seasons','kind':kind,'id':ident(row['series_id'])}
            backdrop=row.get('backdrop_path') or []
            if isinstance(backdrop,list):backdrop=next((v for v in backdrop if isinstance(v,str) and v),None)
            add(row['name'],args,folder=kind=='series',art=row.get('stream_icon') or row.get('cover'),plot=row.get('plot') or '',media='movie' if kind=='movie' else 'tvshow',fanart=backdrop if isinstance(backdrop,str) else None,metadata=row)
        if not featured and start+100<len(data):add('Next page — '+str(start+101)+'–'+str(min(start+200,len(data)))+' of '+str(len(data)),{'mode':'items','kind':kind,'category':PARAMS['category'],'start':start+100,'q':query,'order':order},icon_name='arrow-right')
    elif mode in ('seasons','episodes'):
        data=api('get_series_info',series_id=ident(PARAMS['id']))
        episodes=data.get('episodes',{})
        if mode=='seasons':
            for season in sorted(episodes,key=lambda s:int(s) if str(s).isdigit() else 999):
                add('Season '+str(season),{'mode':'episodes','kind':'series','id':PARAMS['id'],'season':season},art=data.get('info',{}).get('cover'))
        else:
            xbmcplugin.setContent(HANDLE,'episodes')
            for row in episodes.get(PARAMS['season'],[]):
                info=row.get('info') or {}
                label=row.get('title') or ('Episode '+str(row.get('episode_num','')))
                add(label,{'mode':'play','kind':'series','id':ident(row['id']),'ext':row.get('container_extension') or 'mp4','title':label},False,info.get('movie_image') or data.get('info',{}).get('cover'),info.get('plot') or '',media='episode',metadata={**info,'season':PARAMS['season'],'episode_num':row.get('episode_num')})
    elif mode=='play':
        ext=PARAMS.get('ext','mp4')
        if not re.fullmatch(r'[a-zA-Z0-9]{1,8}',ext):raise ValueError('Invalid container')
        url=BASE+'/'+kind+'/'+quote(AUTH['username'],safe='')+'/'+quote(AUTH['password'],safe='')+'/'+ident(PARAMS['id'])+'.'+ext
        item=xbmcgui.ListItem(path=url);item.getVideoInfoTag().setTitle(PARAMS.get('title','Venom TV'))
        xbmcplugin.setResolvedUrl(HANDLE,True,item);return
    else:raise ValueError('Unknown route')
    xbmcplugin.endOfDirectory(HANDLE,cacheToDisc=True)

if __name__=='__main__':
    try:
        BASE,AUTH=auth()
        main()
        if PARAMS.get('mode') in ('categories','items','seasons','episodes','favorites') and xbmc.getSkinDir()=='skin.arctic.fuse.3' and xbmc.getCondVisibility('Window.IsActive(videos)'):
            xbmc.executebuiltin('Container.SetViewMode(512)')
    except Exception as exc:
        xbmc.log('Venom TV: '+type(exc).__name__+' during '+PARAMS.get('mode','root'),xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Venom TV','Could not load this item. Check the gateway or try again.',xbmcgui.NOTIFICATION_ERROR)
        if PARAMS.get('mode')=='play':xbmcplugin.setResolvedUrl(HANDLE,False,xbmcgui.ListItem())
        else:xbmcplugin.endOfDirectory(HANDLE,succeeded=False)
