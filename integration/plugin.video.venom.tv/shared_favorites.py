"""Server-authoritative favourites using the active Jellyfin-for-Kodi user token.

Never uses an admin key. Native catalogue matches require exact managed paths;
channels require both channel number and name. Ambiguity fails closed.
"""
import json
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

def number(value):
    parts=str(value or '').split('.')
    return '.'.join(str(int(p)) if p.isdigit() else p for p in parts).removesuffix('.0')

def identity(e):
    p=e['params'];kind=p.get('kind');mode=p.get('mode')
    if mode=='shared':return 'jf:'+p['id']
    if mode=='channel':return 'channel:'+number(e.get('metadata',{}).get('channelnumber'))+':'+e['label'].strip()
    if mode=='seasons':return 'series:'+str(p['id'])
    if mode=='play' and kind=='movie':return 'movie:'+str(p['id'])
    if mode=='play' and kind=='series' and p.get('series_id'):
        return 'episode:%s:%s:%s'%(p['series_id'],int(p['season']),int(p['episode']))
    return None

def item_identity(item):
    path=(item.get('Path') or '').replace('\\','/').rstrip('/')
    match=re.search(r'/venom-catalogue/movies/Movie (\d+)/movie\.strm$',path)
    if match:return 'movie:'+match[1]
    match=re.search(r'/venom-catalogue/series/Series (\d+)$',path)
    if match:return 'series:'+match[1]
    match=re.search(r'/venom-catalogue/series/Series (\d+)/Season \d+/S(\d+)E(\d+)\.strm$',path)
    if match:return 'episode:%s:%s:%s'%(match[1],int(match[2]),int(match[3]))
    if item.get('Type')=='TvChannel':return 'channel:'+number(item.get('ChannelNumber') or item.get('Number'))+':'+item['Name'].strip()
    return 'jf:'+item['Id']

class SharedFavorites:
    def __init__(self,server):
        self.server=server;self.base=server['address'].rstrip('/');self.user=server['UserId']
        self.cached=[];self.stamp=0;self.matches={};self.retry_after=0

    def request(self,path,method='GET',cancelled=None,**query):
        cancelled=cancelled or (lambda:False)
        if time.monotonic()<self.retry_after:raise ConnectionError('Jellyfin temporarily unavailable; retry shortly')
        header='MediaBrowser Client="Venom TV", Device="Kodi", DeviceId="venom-favorites", Version="1.3", Token="'+self.server['AccessToken']+'"'
        req=Request(self.base+'/'+path+'?'+urlencode(query),headers={'Authorization':header},method=method)
        try:
            deadline=time.monotonic()+10
            with urlopen(req,timeout=8) as response:
                chunks=[];size=0;read=getattr(response,'read1',response.read)
                while True:
                    if cancelled():raise RuntimeError('Jellyfin request cancelled')
                    if time.monotonic()>deadline:raise TimeoutError('Jellyfin response deadline exceeded')
                    chunk=read(min(64*1024,8*1024*1024+1-size))
                    if not chunk:break
                    chunks.append(chunk);size+=len(chunk)
                    if size>8*1024*1024:raise ValueError('Favourite response too large')
                raw=b''.join(chunks)
        except OSError:
            self.retry_after=time.monotonic()+15
            raise
        if len(raw)>8*1024*1024:raise ValueError('Favourite response too large')
        return json.loads(raw) if raw else None

    def favorites(self,force=False,cancelled=None):
        cancelled=cancelled or (lambda:False)
        if not force and time.monotonic()-self.stamp<15:return self.cached
        items=[]
        for endpoint,params in [
            ('Users/'+self.user+'/Items',dict(Recursive='true',IncludeItemTypes='Movie,Series,Episode,TvChannel',Filters='IsFavorite',Fields='Path,ChannelInfo',SortBy='SortName'))]:
            offset=0
            while True:
                if cancelled():raise RuntimeError('Jellyfin request cancelled')
                page=self.request(endpoint,cancelled=cancelled,StartIndex=offset,Limit=500,**params).get('Items',[])
                items.extend(page);offset+=len(page)
                if len(page)<500:break
                if offset>=10000:raise RuntimeError('Favourite list exceeds safe browser limit')
        self.cached=items;self.stamp=time.monotonic()
        return items

    def keys(self,cancelled=None):
        items=self.favorites(cancelled=cancelled)
        return {key for item in items for key in (item_identity(item),'jf:'+item['Id'])}

    def resolve(self,e):
        p=e['params']
        if p.get('mode')=='shared':
            if not re.fullmatch('[0-9a-fA-F]{32}',p.get('id','')):raise ValueError('Invalid Jellyfin ID')
            return self.request('Users/'+self.user+'/Items/'+p['id'])
        key=identity(e)
        if not key:raise ValueError('This category/legacy episode is not a Jellyfin media item')
        if key in self.matches:
            item=self.request('Users/'+self.user+'/Items/'+self.matches[key])
            if item_identity(item)==key:return item
            del self.matches[key]
        if p['mode']=='channel':
            params=dict(Recursive='true',IncludeItemTypes='TvChannel',SearchTerm=e['label'],Fields='Path,ChannelInfo');endpoint='Users/'+self.user+'/Items'
        else:
            params=dict(Recursive='true',SearchTerm=e['label'],Fields='Path',IncludeItemTypes='Movie' if p['kind']=='movie' else ('Series' if p['mode']=='seasons' else 'Episode'))
            endpoint='Users/'+self.user+'/Items'
        matches=[];offset=0
        while True:
            rows=self.request(endpoint,StartIndex=offset,Limit=200,**params).get('Items',[])
            matches.extend(item for item in rows if item_identity(item)==key)
            offset+=len(rows)
            if len(rows)<200:break
            if offset>=2000:raise RuntimeError('Ambiguous search; no favourite changed')
        if len(matches)!=1:raise LookupError('Title not uniquely indexed in Jellyfin yet; no favourite changed')
        self.matches[key]=matches[0]['Id']
        return matches[0]

    def set(self,e,enabled):
        item=self.resolve(e)
        self.request('Users/'+self.user+'/FavoriteItems/'+item['Id'],method='POST' if enabled else 'DELETE')
        verified=self.request('Users/'+self.user+'/Items/'+item['Id'])
        if bool(verified.get('UserData',{}).get('IsFavorite'))!=enabled:
            raise RuntimeError('Jellyfin did not confirm the favourite change')
        self.stamp=0
        return enabled

    def entries(self,cancelled=None):
        result=[]
        for item in self.favorites(force=True,cancelled=cancelled):
            kind={'Movie':'movie','Episode':'series','Series':'series','TvChannel':'live'}.get(item.get('Type'))
            if not kind:continue
            art=self.base+'/Items/'+item['Id']+'/Images/Primary?maxWidth=320&quality=85' if item.get('ImageTags',{}).get('Primary') else ''
            metadata={'channelnumber':item.get('ChannelNumber') or item.get('Number')} if item.get('Type')=='TvChannel' else {}
            result.append({'label':item['Name'],'params':{'mode':'shared','kind':kind,'id':item['Id'],'type':item['Type']},'folder':item['Type']=='Series','art':art,'plot':item.get('Overview',''),'media':None,'metadata':metadata})
        return result

def from_kodi():
    import xbmcvfs
    with open(xbmcvfs.translatePath('special://profile/addon_data/plugin.video.jellyfin/data.json')) as f:
        servers=json.load(f)['Servers']
    if not servers or not servers[0].get('AccessToken') or not servers[0].get('UserId'):
        raise RuntimeError('Sign into Jellyfin for Kodi first')
    return SharedFavorites(servers[0])
