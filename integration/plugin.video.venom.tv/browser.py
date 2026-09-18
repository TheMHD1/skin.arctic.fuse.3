"""Bounded, category-first IPTV browser; native PVR playback, no EPG dependency."""
import json
import re
import os
import sys
import time
import unicodedata
import queue
import threading
from collections import OrderedDict
import xbmc
import xbmcgui
sys.path.insert(0,os.path.dirname(__file__))
import default as catalogue
import shared_favorites

PAGE=80

def clean_label(value):
    # Preserve Arabic text; omit decorative emoji unsupported by the skin font.
    return ' '.join(''.join(c for c in str(value) if unicodedata.category(c) not in ('So','Cs') and c not in ('\ufe0f','\ufe0e')).split())

def channel_display_name(value):
    """Cosmetic only: raw entry labels remain available for exact PVR matching."""
    label=clean_label(value)
    label=re.sub(r'^\d{3,6}\s+(?=(?:VIP\b|CA\b|UK\b|US\b|AR\b|NW\b))','',label,flags=re.I)
    label=re.sub(r'^(?:(?:VIP|CA|UK|US|AR|NW)\b[\s:|.-]*)+','',label,flags=re.I).strip()
    return label or clean_label(value)

def rpc(method,params):
    response=json.loads(xbmc.executeJSONRPC(json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params})))
    if 'error' in response:raise RuntimeError('Kodi API '+method+' failed')
    return response['result']

def entry(label,params,art='',folder=False,plot='',media=None,metadata=None):
    return dict(label=label,params=params,art=art,folder=folder,plot=plot,media=media,metadata=metadata or {})

def channel_playback_item(target,channels):
    """Use exact PVR identity when present; otherwise play the actual server ID.

    PVR numbering/names can lag server guide refreshes. Never guess a similar
    channel or change a favourite just because its native PVR match is absent.
    """
    matches=[r for r in channels if shared_favorites.number(r['channelnumber'])==shared_favorites.number(target.get('ChannelNumber') or target.get('Number')) and r['label'].strip()==target['Name'].strip()]
    if len(matches)==1:return {'channelid':matches[0]['channelid']}
    ident=target.get('Id','')
    if not re.fullmatch('[0-9a-fA-F]{32}',ident):raise RuntimeError('Invalid Jellyfin channel identity')
    return {'file':'plugin://plugin.video.jellyfin/?mode=play&id='+ident}

def live_group_choices(groups,summaries):
    ranks={clean_label(row['name']):i for i,row in enumerate(summaries)}
    pinned=[(row['name'],'jf:'+row['id']) for row in summaries if row['id'].startswith('collection-')]
    provider=[(row['name'],'jf:'+row['id']) for row in summaries if not row['id'].startswith('collection-')]
    if provider:return pinned+[('All channels','alltv')]+provider
    ordered=sorted(groups,key=lambda group:ranks.get(clean_label(group['label']),10**9))
    return pinned+[('All channels','alltv')]+[(g['label'],g['channelgroupid']) for g in ordered if g['label']!='All channels']

class Browser(xbmcgui.WindowXML):
    def onInit(self):
        if getattr(self,'initialized',False):
            categories=self.getControl(910);categories.reset()
            categories.addItems([xbmcgui.ListItem(label=clean_label(name)) for name,_ in self.categories])
            categories.selectItem(getattr(self,'selected_category_index',0))
            self.getControl(941).setLabel({'live':'Live TV','movie':'Movies','series':'Series','favorites':'Favourites'}[self.kind])
            if self.category is None:
                self.setFocusId(910)
                return
            self.render();self.setFocusId(920)
            self.getControl(920).selectItem(getattr(self,'last_grid_position',0))
            return
        self.initialized=True
        self.jobs=queue.Queue();self.closed=False;self.busy=False
        self.kind=sys.argv[1] if len(sys.argv)>1 and sys.argv[1] in ('live','movie','series','favorites') else 'live'
        self.page=0;self.query='';self.recent=False;self.stack=[];self.entries=[];self.categories=[]
        self.cache={};self.source_cache=OrderedDict();self.scope=None
        self.category_retry_at=0
        try:self.shared=shared_favorites.from_kodi()
        except Exception:self.shared=None
        self.shared_keys=set();self.shared_error=False
        self.favorite_refresh=None;self.favorite_result=None;self.favorite_check=0;self.favorite_generation=0
        self.jobs.put(self.load_categories)
        self.setFocusId(910)

    def enqueue(self,call):
        # Execute slow work outside Kodi's input callbacks; never accumulate a
        # backlog of repeated remote presses while a request is outstanding.
        if not self.closed and not self.busy and self.jobs.empty():self.jobs.put(call)

    def process(self):
        try:call=self.jobs.get_nowait()
        except queue.Empty:call=None
        if call:
            self.busy=True
            try:self.safe(call)
            finally:self.busy=False;self.jobs.task_done()
        if self.closed:return
        self.retry_categories_if_ready()
        if self.favorite_result is not None:
            keys,error=self.favorite_result;self.favorite_result=None
            changed=keys is not None and keys!=self.shared_keys
            if keys is not None:self.shared_keys=keys
            self.shared_error=error
            if changed and self.category is not None:
                pos=self.getControl(920).getSelectedPosition()
                self.render();self.getControl(920).selectItem(max(0,pos))
        if self.shared and time.monotonic()-self.favorite_check>30 and not (self.favorite_refresh and self.favorite_refresh.is_alive()):
            self.favorite_check=time.monotonic()
            generation=self.favorite_generation
            def refresh():
                # Separate client: no races with foreground favourite mutations.
                try:result=(shared_favorites.SharedFavorites(self.shared.server).keys(),False)
                except Exception:result=(None,True)
                if generation==self.favorite_generation:self.favorite_result=result
            self.favorite_refresh=threading.Thread(target=refresh,daemon=True);self.favorite_refresh.start()

    def retry_categories_if_ready(self):
        # A temporary server outage must not leave this window stuck on PVR
        # groups. Retry only at the category chooser, never over an open grid.
        deadline=getattr(self,'category_retry_at',0)
        if (deadline and time.monotonic()>=deadline and self.kind=='live'
                and self.category is None and not self.closed
                and not self.busy and self.jobs.empty()):
            self.category_retry_at=0
            self.enqueue(self.load_categories)
            return True
        return False

    def close(self):
        self.closed=True
        super().close()

    def safe(self,call):
        started=time.monotonic()
        try:call()
        except Exception as exc:
            xbmc.log('Venom browser: '+type(exc).__name__,xbmc.LOGERROR)
            if self.closed:return
            self.getControl(940).setLabel('Unable to load. Press OK to retry, or choose another category.')
            message='Could not match this item for the requested action. Nothing was changed.' if isinstance(exc,LookupError) else 'Could not load or play this item. Try again.'
            xbmcgui.Dialog().notification('Venom TV',message,xbmcgui.NOTIFICATION_ERROR)
        finally:xbmc.log('Venom browser: '+call.__name__+' %.3fs'%(time.monotonic()-started),xbmc.LOGINFO)

    def load_categories(self):
        self.page=0;self.query='';self.stack=[];self.scope=None;self.category=None;self.selected_category_index=0
        self.getControl(940).setLabel('Choose a category on the left, then press OK. Menu / hold OK: favourites.')
        self.getControl(920).reset();self.entries=[]
        self.getControl(941).setLabel({'live':'Live TV','movie':'Movies','series':'Series','favorites':'Favourites'}[self.kind])
        if self.kind=='live':
            groups=rpc('PVR.GetChannelGroups',{'channeltype':'tv'}).get('channelgroups',[])
            summaries=[]
            if self.shared:
                try:
                    summaries=self.shared.request('LiveTvCategories')
                    self.category_retry_at=0
                except Exception:
                    self.category_retry_at=time.monotonic()+15
                    xbmc.log('Venom category service unavailable; keeping native PVR groups and retrying at chooser',xbmc.LOGINFO)
            self.categories=live_group_choices(groups,summaries)
        elif self.kind=='favorites':
            self.categories=[('All shared favourites','all'),('Live channels','live'),('Movies','movie'),('Series','series'),('Local bookmarks / pending sync','local')]
        else:
            action='get_vod_categories' if self.kind=='movie' else 'get_series_categories'
            self.categories=[('All titles','all')]+[(r['category_name'],str(r['category_id'])) for r in sorted(catalogue.api(action),key=lambda r:catalogue.search_text(r['category_name']))]
        if self.closed:return
        self.setProperty('Venom.Posters','true' if self.kind in ('movie','series') else 'false')
        items=[xbmcgui.ListItem(label=clean_label(name)) for name,_ in self.categories]
        self.getControl(910).reset();self.getControl(910).addItems(items)
        self.getControl(910).selectItem(0);self.setFocusId(910)
        # No automatic category fetch on focus: scrolling hundreds of groups
        # never launches hundreds of requests or lands in the first cartoon group.

    def prepare_shared_entry(self,e):
        if e['params'].get('mode')=='channel' and not e.get('metadata',{}).get('channelnumber'):
            detail=rpc('PVR.GetChannelDetails',{'channelid':int(e['params']['id']),'properties':['channelnumber']})['channeldetails']
            e={**e,'metadata':{**e.get('metadata',{}),'channelnumber':detail['channelnumber']}}
        return e

    def migrate_local(self):
        if not self.shared:return
        state=catalogue.venom_state.read(catalogue.ROOT)
        processed=0
        for key,e in list(state.get('favorites',{}).items()):
            if e['params'].get('mode')=='items':continue # Category bookmarks are not server media.
            retry=state.get('shared_retry',{}).get(key,0)
            if time.time()-retry<3600:continue
            if processed>=3:break
            processed+=1
            try:
                self.shared.set(self.prepare_shared_entry(e),True)
                def migrated(value):
                    if value.get('favorites',{}).get(key)==e:value['favorites'].pop(key)
                    value.setdefault('shared_retry',{}).pop(key,None)
                catalogue.venom_state.update(catalogue.ROOT,migrated)
            except Exception:
                catalogue.venom_state.update(catalogue.ROOT,lambda value:value.setdefault('shared_retry',{}).update({key:time.time()}))
                xbmc.log('Venom favourites: legacy entry retained pending exact server match',xbmc.LOGWARNING)
                break

    def select_category(self):
        index=self.getControl(910).getSelectedPosition()
        if not 0<=index<len(self.categories):return
        self.selected_category_index=index
        self.category_name,self.category=self.categories[index]
        self.scope=None;self.stack=[];self.page=0;self.query=''
        self.load_entries();self.setFocusId(920)

    def source_entries(self):
        if self.kind=='favorites':return self.fetch_entries()
        key=(self.kind,str(self.category),json.dumps(self.scope,sort_keys=True),self.recent)
        cached=self.source_cache.get(key)
        if cached and time.monotonic()-cached[0]<300:
            self.source_cache.move_to_end(key);return cached[1]
        rows=self.fetch_entries()
        self.source_cache[key]=(time.monotonic(),rows)
        # Bound both category count and retained title count (large All titles).
        while len(self.source_cache)>4 or (len(self.source_cache)>1 and sum(len(v[1]) for v in self.source_cache.values())>35000):
            self.source_cache.popitem(last=False)
        return rows

    def fetch_entries(self):
        if self.kind=='favorites':
            if self.category=='local':return list(catalogue.venom_state.read(catalogue.ROOT).get('favorites',{}).values())
            if not self.shared:raise RuntimeError('Jellyfin sign-in required for shared favourites')
            favorites=self.shared.entries()
            return [v for v in favorites if self.category=='all' or v['params'].get('kind')==self.category]
        if self.kind=='live':
            if str(self.category).startswith('jf:'):
                if not self.shared:raise RuntimeError('Jellyfin sign-in required')
                result=[]
                for offset in range(0,15000,250):
                    page=self.shared.request('LiveTvCategories/'+self.category[3:]+'/Channels',startIndex=offset,limit=250,addCurrentProgram='false')
                    for row in page['Items']:
                        art=self.shared.base+'/Items/'+row['Id']+'/Images/Primary?maxWidth=320&quality=85' if row.get('ImageTags',{}).get('Primary') else ''
                        result.append(entry(row['Name'],{'mode':'shared','kind':'live','id':row['Id'],'type':'TvChannel'},art=art,metadata={'channelnumber':row.get('ChannelNumber') or row.get('Number')}))
                    if len(result)>=page['TotalRecordCount']:return result
                raise RuntimeError('Channel category exceeds safe size')
            key=('live',str(self.category))
            cached=self.cache.get(key)
            if not cached or time.monotonic()-cached[0]>300:
                rows=rpc('PVR.GetChannels',{'channelgroupid':self.category,'properties':['thumbnail','channelnumber']}).get('channels',[])
                result=[entry(r['label'],{'mode':'channel','kind':'live','id':str(r['channelid'])},r.get('thumbnail',''),metadata={'channelnumber':r['channelnumber']}) for r in rows]
                # Bound RAM: retain only the last live group, not all 11k channels per group.
                self.cache={key:(time.monotonic(),result)}
            return self.cache[key][1]
        if self.scope:
            if self.scope.get('jf_series'):
                items=[]
                for offset in range(0,10000,500):
                    if self.closed:return []
                    page=self.shared.request('Shows/'+self.scope['jf_series']+'/Episodes',UserId=self.shared.user,IsMissing='false',StartIndex=offset,Limit=500).get('Items',[])
                    items.extend(page)
                    if len(page)<500:break
                else:raise RuntimeError('Series exceeds safe episode browser limit')
                return [entry(r['Name'],{'mode':'shared','kind':'series','id':r['Id'],'type':'Episode'}) for r in items]
            data=catalogue.api('get_series_info',series_id=catalogue.ident(self.scope['id']))
            episodes=data.get('episodes') or {};cover=data.get('info',{}).get('cover','')
            if 'season' not in self.scope:
                return [entry('Season '+str(s),{'mode':'episodes','kind':'series','id':self.scope['id'],'season':s},cover,True) for s in sorted(episodes,key=lambda s:int(s) if str(s).isdigit() else 999)]
            return [entry(r.get('title') or 'Episode '+str(r.get('episode_num','')),{'mode':'play','kind':'series','id':catalogue.ident(r['id']),'ext':r.get('container_extension') or 'mp4','title':r.get('title',''),'series_id':self.scope['id'],'season':self.scope['season'],'episode':r.get('episode_num',0)},(r.get('info') or {}).get('movie_image') or cover,False,(r.get('info') or {}).get('plot',''),'episode') for r in episodes.get(self.scope['season'],[])]
        action='get_vod_streams' if self.kind=='movie' else 'get_series'
        rows=catalogue.api(action,**({} if self.category=='all' else {'category_id':self.category}))
        rows=catalogue.ordered(rows,order='recent' if self.recent else 'name')
        return [entry(r['name'],{'mode':'play','kind':'movie','id':catalogue.ident(r['stream_id']),'ext':r.get('container_extension') or 'mp4','title':r['name']} if self.kind=='movie' else {'mode':'seasons','kind':'series','id':catalogue.ident(r['series_id'])},r.get('stream_icon') or r.get('cover') or '',self.kind=='series',r.get('plot') or '','movie' if self.kind=='movie' else 'tvshow') for r in rows]

    def load_entries(self):
        self.getControl(940).setLabel('Loading…')
        self.entries=[];self.visible_entries=[];self.getControl(920).reset()
        rows=self.source_entries()
        if getattr(self,'closed',False):return
        if hasattr(self,'setProperty'):self.setProperty('Venom.Posters','true' if self.kind in ('movie','series') else 'false')
        words=catalogue.search_text(self.query).split()
        self.entries=[r for r in rows if all(w in catalogue.search_text(r['label']) for w in words)]
        self.page=min(self.page,max(0,(len(self.entries)-1)//PAGE))
        self.render()

    def render(self):
        # Rendering/page changes must NEVER contact Jellyfin or the provider.
        # Stars are refreshed by a separate, bounded background request.
        self.visible_entries=self.entries[self.page*PAGE:(self.page+1)*PAGE]
        items=[]
        for e in self.visible_entries:
            item=xbmcgui.ListItem(label=clean_label(e['label']))
            fallback='DefaultTVShows.png' if e['params'].get('kind') in ('live','series') else 'DefaultMovies.png'
            item.setArt({'thumb':e.get('art') or 'special://skin/media/'+fallback,'icon':'special://skin/media/'+fallback})
            item.setProperty('venom.favorite','true' if shared_favorites.identity(e) in self.shared_keys else 'false')
            items.append(item)
        self.getControl(920).reset();self.getControl(920).addItems(items)
        pages=max(1,(len(self.entries)+PAGE-1)//PAGE)
        self.getControl(940).setLabel('%s • %s %s • Page %s / %s%s'%(clean_label(self.category_name),len(self.entries),'channels' if self.kind=='live' else 'titles',self.page+1,pages,(' • Search: '+self.query) if self.query else ''))
        self.getControl(934).setLabel('Refresh favourites' if self.kind=='favorites' else ('Sort: Recent' if self.recent else 'Sort: A–Z'))
        if getattr(self,'shared_error',False):self.getControl(940).setLabel(self.getControl(940).getLabel()+' • Favourites temporarily offline')

    def open_selected(self):
        pos=self.getControl(920).getSelectedPosition()
        if not 0<=pos<len(self.visible_entries):return
        self.last_grid_position=pos
        e=self.visible_entries[pos];p=e['params']
        if p['mode']=='shared':
            if p.get('type')=='TvChannel':
                target=self.shared.resolve(e)
                channels=rpc('PVR.GetChannels',{'channelgroupid':'alltv','properties':['channelnumber']}).get('channels',[])
                playback=channel_playback_item(target,channels)
                if 'file' in playback:xbmc.log('Venom playback: native PVR identity unavailable; delegating exact Jellyfin channel ID',xbmc.LOGINFO)
                rpc('Player.Open',{'item':playback});xbmc.executebuiltin('ActivateWindow(fullscreenvideo)')
            elif p.get('type')=='Series':
                self.stack.append((self.kind,self.scope,self.page,self.query,self.category_name,pos))
                self.kind='series';self.scope={'jf_series':p['id']};self.page=0;self.query='';self.category_name=e['label'];self.load_entries()
            else:
                xbmc.Player().play('plugin://plugin.video.jellyfin/?mode=play&id='+p['id']);xbmc.executebuiltin('ActivateWindow(fullscreenvideo)')
        elif p['mode']=='channel':
            rpc('Player.Open',{'item':{'channelid':int(catalogue.ident(p['id']))}})
            xbmc.executebuiltin('ActivateWindow(fullscreenvideo)')
        elif p['mode'] in ('seasons','episodes'):
            self.stack.append((self.kind,self.scope,self.page,self.query,self.category_name,pos))
            self.kind='series';self.scope=p;self.page=0;self.query='';self.category_name=e['label'];self.load_entries()
        elif p['mode']=='items':
            self.kind=p['kind'];self.load_categories();self.category=p['category'];self.category_name=e['label'];self.load_entries()
        else:
            xbmc.Player().play(catalogue.route(**p));xbmc.executebuiltin('ActivateWindow(fullscreenvideo)')

    def favorite_menu(self):
        if self.getFocusId()!=920:return
        pos=self.getControl(920).getSelectedPosition()
        if not 0<=pos<len(self.visible_entries):return
        e=self.visible_entries[pos]
        if e['params'].get('mode')=='episodes':return
        if self.kind=='favorites' and self.category=='local':
            choice=xbmcgui.Dialog().select(e['label'],['Remove this local bookmark / pending entry','Play / Open'])
            if choice==0:
                key=catalogue.favorite_key(e['params'])
                catalogue.venom_state.update(catalogue.ROOT,lambda value:value.get('favorites',{}).pop(key,None))
                self.load_entries()
            elif choice==1:self.open_selected()
            return
        if not self.shared:raise RuntimeError('Sign into Jellyfin for shared favourites')
        e=self.prepare_shared_entry(e)
        exists=shared_favorites.identity(e) in self.shared_keys
        choice=xbmcgui.Dialog().select(e['label'],['Remove from Jellyfin favourites (all devices)' if exists else 'Add to Jellyfin favourites (all devices)','Play / Open'])
        if choice==0:
            self.shared.set(e,not exists)
            key=shared_favorites.identity(e)
            if exists:self.shared_keys.discard(key)
            else:self.shared_keys.add(key)
            # Discard any pre-mutation snapshot still in flight.
            self.favorite_generation+=1
            self.favorite_result=None;self.favorite_check=0
            xbmcgui.Window(10000).setProperty('Habibi.Home.Refresh',str(time.time_ns()))
            if self.kind=='favorites':self.load_entries()
            else:self.render();self.getControl(920).selectItem(pos)
        elif choice==1:self.open_selected()

    def onClick(self,control):
        def handle():
            if control in (901,902,903,904):
                self.kind={901:'live',902:'movie',903:'series',904:'favorites'}[control];self.load_categories();self.setFocusId(910)
            elif control==910:self.select_category()
            elif control==920:self.open_selected()
            elif control==931 and self.category is not None:
                query=xbmcgui.Dialog().input('Search '+self.category_name,defaultt=self.query)
                self.query=query.strip();self.page=0;self.load_entries();self.setFocusId(920)
            elif control in (932,933) and self.entries:
                self.page=max(0,min(self.page+(-1 if control==932 else 1),(len(self.entries)-1)//PAGE));self.render();self.setFocusId(920)
            elif control==934 and self.kind in ('movie','series') and self.category is not None:
                self.recent=not self.recent;self.page=0;self.load_entries()
            elif control==934 and self.kind=='favorites' and self.category is not None:
                self.load_entries()
        self.enqueue(handle)

    def onAction(self,action):
        if action.getId() in (92,10):
            if self.busy:self.close();return
            if self.stack:
                def back():
                    self.kind,self.scope,self.page,self.query,self.category_name,pos=self.stack.pop()
                    self.load_entries();self.getControl(920).selectItem(pos)
                self.enqueue(back)
            elif self.getFocusId()==920:self.setFocusId(910)
            else:self.close()
        elif action.getId() in (117,101):self.enqueue(self.favorite_menu)

if __name__=='__main__':
    xbmc.log('Venom browser: launch requested',xbmc.LOGINFO)
    home=xbmcgui.Window(10000)
    if not home.getProperty('Venom.Browser.Open'):
        home.setProperty('Venom.Browser.Open','true')
        try:
            catalogue.BASE,catalogue.AUTH=catalogue.auth()
            xbmc.log('Venom browser: credentials loaded',xbmc.LOGINFO)
            window=Browser('VenomBrowser.xml',os.path.dirname(__file__),'Default','1080i')
            window.show()
            xbmc.log('Venom browser: window shown',xbmc.LOGINFO)
            monitor=xbmc.Monitor()
            launch_deadline=time.monotonic()+5
            while not getattr(window,'closed',False) and not monitor.waitForAbort(0.05):
                if getattr(window,'initialized',False):window.process()
                elif time.monotonic()>launch_deadline:
                    # Kodi can refuse a window while a modal dialog is open.
                    # Release the singleton so the next menu click can retry.
                    xbmc.log('Venom browser: window activation blocked; allowing retry',xbmc.LOGWARNING)
                    break
            window.close();del window
        finally:
            home.clearProperty('Venom.Browser.Open')
            if xbmc.getCondVisibility('Window.IsActive(1107)'):
                xbmc.executebuiltin('ActivateWindow(home)')
