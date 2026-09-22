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
NETWORK_CACHE_SECONDS=300
PVR_PLAYBACK_CACHE_SECONDS=30
PVR_PLAYBACK_CACHE_LIMIT=15000
CHANNEL_COSMETIC_PREFIXES='VIP|CA|UK|US|AR|NW|IRQ|LB'
LIVE_HANDOFF_TIMEOUT_SECONDS=25
LIVE_HANDOFF_POLL_SECONDS=.1

class LatestWorker:
    """One daemon worker with one replaceable pending request/result slot."""
    def __init__(self):
        self.lock=threading.Lock();self.wake=threading.Event()
        self.pending=None;self.critical=None;self.active_critical=False
        self.result=None;self.critical_result=None;self.stopped=False;self.closing=False
        self.thread=threading.Thread(target=self._run,name='VenomNetwork',daemon=True)
        self.thread.start()

    def submit(self,generation,name,work,critical=False):
        with self.lock:
            if self.stopped or self.closing:return False
            if critical:
                if self.critical is not None or self.active_critical:return False
                self.critical=(generation,name,work)
            else:self.pending=(generation,name,work)
            self.wake.set()
        return True

    def discard_pending(self):
        with self.lock:self.pending=None

    def poll(self):
        with self.lock:
            result=self.result;self.result=None
        return result

    def poll_critical(self):
        with self.lock:
            result=self.critical_result;self.critical_result=None
        return result

    def can_submit_critical(self):
        with self.lock:
            return not self.stopped and not self.closing and self.critical is None and not self.active_critical

    def close(self):
        with self.lock:
            # A user-confirmed mutation is non-replaceable and may finish after
            # its window closes. Its result is discarded, never applied late.
            self.closing=True;self.pending=None;self.result=None;self.critical_result=None;self.wake.set()

    def _run(self):
        while True:
            self.wake.wait()
            with self.lock:
                if self.stopped:return
                is_critical=self.critical is not None
                if is_critical:
                    job=self.critical;self.critical=None;self.active_critical=True
                elif self.closing:
                    self.stopped=True;return
                else:job=self.pending;self.pending=None
                if self.pending is None and self.critical is None:self.wake.clear()
                else:self.wake.set()
            if job is None:continue
            generation,name,work=job;started=time.monotonic()
            try:value=work();error=None
            except Exception as exc:value=None;error=exc
            result=(generation,name,value,error,time.monotonic()-started)
            with self.lock:
                if is_critical:self.active_critical=False
                if self.closing:
                    if self.critical is None:self.stopped=True
                    else:self.wake.set()
                    if self.stopped:return
                    continue
                if is_critical:self.critical_result=result
                # Never allow a late older completion to replace a newer one.
                elif self.result is None or generation>=self.result[0]:self.result=result

def clean_label(value):
    # Preserve Arabic text; omit decorative emoji unsupported by the skin font.
    return ' '.join(''.join(c for c in str(value) if unicodedata.category(c) not in ('So','Cs') and c not in ('\ufe0f','\ufe0e')).split())

def channel_display_name(value):
    """Remove only reviewed cosmetic prefixes; preserve the full channel title."""
    label=clean_label(value)
    label=re.sub(r'^\d{3,6}\s+(?=(?:'+CHANNEL_COSMETIC_PREFIXES+r')\b)','',label,flags=re.I)
    label=re.sub(r'^(?:(?:'+CHANNEL_COSMETIC_PREFIXES+r')\b[\s:|.-]*)+','',label,flags=re.I).strip()
    return label or clean_label(value)

def channel_number_name(value):
    """Normalize reviewed prefixes only when an exact number also identifies it."""
    return channel_display_name(value).casefold()

def channel_full_name(value):
    """Preserve every word, digit and quality/country marker for name identity."""
    return clean_label(value).casefold()

def rpc(method,params):
    response=json.loads(xbmc.executeJSONRPC(json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params})))
    if 'error' in response:raise RuntimeError('Kodi API '+method+' failed')
    return response['result']

def entry(label,params,art='',folder=False,plot='',media=None,metadata=None):
    return dict(label=label,params=params,art=art,folder=folder,plot=plot,media=media,metadata=metadata or {})

def active_video_channel(rpc_call):
    """Return one known Kodi TV channel; ambiguity/other media stays unknown."""
    try:players=rpc_call('Player.GetActivePlayers',{})
    except Exception:return None
    videos=[p for p in players if p.get('type')=='video' and isinstance(p.get('playerid'),int) and not isinstance(p.get('playerid'),bool)]
    if len(videos)!=1:return None
    playerid=videos[0]['playerid']
    try:item=rpc_call('Player.GetItem',{'playerid':playerid}).get('item',{})
    except Exception:return None
    channelid=item.get('id')
    if item.get('type')!='channel' or not isinstance(channelid,int) or isinstance(channelid,bool):return None
    return playerid,channelid

def channel_pvr_match(target,channels):
    """Return one fail-closed PVR match and the identity rule that selected it."""
    target_number=shared_favorites.number(target.get('ChannelNumber') or target.get('Number'))
    numbered_name=channel_number_name(target.get('Name',''))
    matches=[r for r in channels if target_number and shared_favorites.number(r['channelnumber'])==target_number and channel_number_name(r['label'])==numbered_name]
    if len(matches)==1:return matches[0],'number'
    # PVR group edits can renumber channels independently of Jellyfin.  Only a
    # unique complete label may recover from that drift: country/source tags,
    # quality suffixes and digits all remain significant.
    full_name=channel_full_name(target.get('Name',''))
    matches=[r for r in channels if full_name and channel_full_name(r['label'])==full_name]
    if len(matches)==1:return matches[0],'label'
    return None,None

def channel_playback_item(target,channels):
    """Use one verified PVR identity, otherwise play the exact Jellyfin ID."""
    match,_identity=channel_pvr_match(target,channels)
    if match:return {'channelid':match['channelid']}
    ident=target.get('Id','')
    if not re.fullmatch('[0-9a-fA-F]{32}',ident):raise RuntimeError('Invalid Jellyfin channel identity')
    return {'file':'plugin://plugin.video.jellyfin/?mode=play&id='+ident}

def playback_from_pvr_cache(target,cache,rpc_call,now=None):
    """Use a brief PVR snapshot, but freshly verify a cached native id."""
    now=time.monotonic() if now is None else now
    fallback=channel_playback_item(target,[])
    rows=cache.get('rows')
    if rows is None or now-cache.get('stamp',0)>=PVR_PLAYBACK_CACHE_SECONDS:
        try:
            rows=rpc_call('PVR.GetChannels',{'channelgroupid':'alltv','properties':['channelnumber']}).get('channels',[])
            if len(rows)<=PVR_PLAYBACK_CACHE_LIMIT:cache.update(stamp=now,rows=rows)
            else:cache.clear()
        except Exception:return fallback
    candidate,identity=channel_pvr_match(target,rows)
    if not candidate:return fallback
    try:
        detail=rpc_call('PVR.GetChannelDetails',{'channelid':candidate['channelid'],'properties':['channelnumber']})['channeldetails']
        if detail.get('channelid')!=candidate['channelid']:return fallback
        if identity=='number':
            verified=(shared_favorites.number(detail.get('channelnumber'))==shared_favorites.number(target.get('ChannelNumber') or target.get('Number'))
                      and channel_number_name(detail.get('label',''))==channel_number_name(target.get('Name','')))
        else:
            verified=(bool(channel_full_name(target.get('Name','')))
                      and channel_full_name(detail.get('label',''))==channel_full_name(target.get('Name','')))
        return {'channelid':candidate['channelid']} if verified else fallback
    except Exception:
        return fallback

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
        self.network=LatestWorker();self.request_generation=0;self.request_apply=None;self.network_busy=False
        self.critical_apply=None;self.critical_busy=False
        self.close_requested=False;self.pending_bookmark=None
        self.kind=sys.argv[1] if len(sys.argv)>1 and sys.argv[1] in ('live','movie','series','favorites') else 'live'
        self.page=0;self.query='';self.recent=False;self.stack=[];self.entries=[];self.categories=[]
        self.source_cache=OrderedDict();self.pvr_playback_cache={};self.scope=None
        self.open_selection=None;self.open_pending=None;self.live_handoff=None
        self.category_retry_at=0
        try:self.shared=shared_favorites.from_kodi()
        except Exception:self.shared=None
        self.shared_keys=set();self.shared_error=False
        self.favorite_check=0
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
        self.poll_live_handoff()
        if self.closed:return
        result=self.network.poll()
        if result:
            generation,name,value,error,elapsed=result
            cancelled=generation!=self.request_generation
            xbmc.log('Venom network: %s %.3fs%s'%(name,elapsed,' cancelled' if cancelled else ''),xbmc.LOGINFO)
            if not cancelled:
                self.network_busy=False
                apply=self.request_apply;self.request_apply=None
                if error:
                    self.clear_open_pending(generation);self.report_error(error)
                elif apply:
                    try:apply(value)
                    except Exception as exc:self.report_error(exc)
        critical=self.network.poll_critical()
        if critical:
            _generation,name,value,error,elapsed=critical
            xbmc.log('Venom network: %s %.3fs'%(name,elapsed),xbmc.LOGINFO)
            apply=self.critical_apply;self.critical_apply=None;self.critical_busy=False
            if error:self.report_error(error)
            elif apply:
                try:apply(value)
                except Exception as exc:self.report_error(exc)
            if self.close_requested:self._final_close();return
        self.retry_categories_if_ready()
        if (self.shared and time.monotonic()-self.favorite_check>30
                and not self.network_busy and not self.critical_busy):
            self.favorite_check=time.monotonic()
            server=self.shared.server
            def refresh(generation):
                try:
                    client=shared_favorites.SharedFavorites(server)
                    return client.keys(cancelled=lambda:self.request_cancelled(generation)),False
                except Exception:return None,True
            self.start_network('favourite refresh',refresh,self.apply_favorite_refresh)

    def apply_favorite_refresh(self,value):
        keys,error=value;changed=keys is not None and keys!=self.shared_keys
        if keys is not None:self.shared_keys=keys
        self.shared_error=error
        if changed and self.category is not None and not self.network_busy:
            pos=self.getControl(920).getSelectedPosition()
            self.render();self.getControl(920).selectItem(max(0,pos))

    def retry_categories_if_ready(self):
        # A temporary server outage must not leave this window stuck on PVR
        # groups. Retry only at the category chooser, never over an open grid.
        deadline=getattr(self,'category_retry_at',0)
        if (deadline and time.monotonic()>=deadline and self.kind=='live'
                and self.category is None and not self.closed
                and not self.busy and not getattr(self,'network_busy',False) and self.jobs.empty()):
            self.category_retry_at=0
            self.enqueue(self.load_categories)
            return True
        return False

    def close(self):
        if getattr(self,'critical_busy',False):
            self.close_requested=True
            self.cancel_network('close waiting for favourite')
            self.getControl(940).setLabel('Saving favourite…')
            return
        self._final_close()

    def _final_close(self):
        if self.closed:return
        self.cancel_live_handoff('window close')
        self.closed=True
        self.request_generation+=1;self.request_apply=None;self.network_busy=False
        self.critical_apply=None;self.critical_busy=False
        if hasattr(self,'network'):self.network.close()
        super().close()

    def cancel_network(self,reason):
        if not hasattr(self,'network'):return
        self.request_generation+=1;self.request_apply=None;self.network_busy=False
        self.open_pending=None
        self.network.discard_pending()
        xbmc.log('Venom network: cancelled '+reason,xbmc.LOGINFO)

    def clear_open_pending(self,generation):
        pending=getattr(self,'open_pending',None)
        if pending and len(pending)>1 and pending[1]==generation:self.open_pending=None

    def start_network(self,name,work,apply):
        self.cancel_network('superseded')
        generation=self.request_generation
        self.request_apply=apply;self.network_busy=True
        self.network.submit(generation,name,lambda:work(generation))
        return generation

    def start_critical_network(self,name,work,apply):
        if not self.network.can_submit_critical():
            raise RuntimeError('Another favourite change is still pending')
        self.cancel_network('user mutation')
        generation=self.request_generation
        if not self.network.submit(generation,name,lambda:work(generation),critical=True):
            raise RuntimeError('Another favourite change is still pending')
        self.critical_apply=apply;self.critical_busy=True
        return generation

    def request_cancelled(self,generation):
        return self.closed or generation!=self.request_generation

    def cancel_live_handoff(self,reason):
        if not getattr(self,'live_handoff',None):return
        self.live_handoff=None
        self.open_pending=None
        xbmc.log('Venom playback: cancelled channel handoff '+reason,xbmc.LOGINFO)

    def open_channel_now(self,playback):
        rpc('Player.Open',{'item':playback})
        xbmc.executebuiltin('ActivateWindow(fullscreenvideo)')

    def begin_channel_playback(self,playback,selection=None,now=None):
        """Break before a proven different native channel; never guess state."""
        self.cancel_live_handoff('replaced')
        if 'channelid' not in playback:
            self.open_channel_now(playback);return False
        current=active_video_channel(rpc)
        target=playback['channelid']
        if not current or current[1]==target:
            self.open_channel_now(playback);return False
        playerid,_channelid=current
        # Player.Stop is asynchronous in Kodi.  Its success only starts a
        # bounded UI-loop wait; no new stream opens until this player vanishes.
        rpc('Player.Stop',{'playerid':playerid})
        now=time.monotonic() if now is None else now
        self.live_handoff={'playerid':playerid,'playback':dict(playback),'selection':selection,
                           'deadline':now+LIVE_HANDOFF_TIMEOUT_SECONDS,'next_poll':now}
        self.getControl(940).setLabel('Stopping current channel before switching…')
        return True

    def poll_live_handoff(self,now=None):
        handoff=getattr(self,'live_handoff',None)
        if not handoff or self.closed:return False
        now=time.monotonic() if now is None else now
        if now<handoff['next_poll']:return False
        if now>=handoff['deadline']:
            self.cancel_live_handoff('timeout')
            self.report_error(TimeoutError('Kodi did not stop the previous channel in time'))
            return False
        handoff['next_poll']=now+LIVE_HANDOFF_POLL_SECONDS
        try:players=rpc('Player.GetActivePlayers',{})
        except Exception:return False
        videos=[p for p in players if p.get('type')=='video']
        if any(p.get('playerid')==handoff['playerid'] for p in videos):return False
        if videos:
            self.cancel_live_handoff('player changed')
            self.report_error(RuntimeError('Another video started during channel switch'))
            return False
        playback=handoff['playback'];self.live_handoff=None;self.open_pending=None
        try:self.open_channel_now(playback)
        except Exception as exc:
            self.report_error(exc)
            return False
        return True

    def report_error(self,exc):
        xbmc.log('Venom browser: '+type(exc).__name__,xbmc.LOGERROR)
        if self.closed:return
        self.getControl(940).setLabel('Unable to load. Press OK to retry, or choose another category.')
        message='Could not match this item for the requested action. Nothing was changed.' if isinstance(exc,LookupError) else 'Could not load or play this item. Try again.'
        xbmcgui.Dialog().notification('Venom TV',message,xbmcgui.NOTIFICATION_ERROR)

    def safe(self,call):
        started=time.monotonic()
        try:call()
        except Exception as exc:
            self.report_error(exc)
        finally:xbmc.log('Venom browser: '+call.__name__+' %.3fs'%(time.monotonic()-started),xbmc.LOGINFO)

    def load_categories(self):
        self.cancel_live_handoff('navigation')
        self.cancel_network('category menu')
        self.open_pending=None
        self.page=0;self.query='';self.stack=[];self.scope=None;self.category=None;self.selected_category_index=0
        self.categories=[];self.getControl(910).reset()
        self.getControl(940).setLabel('Choose a category on the left, then press OK. Menu / hold OK: favourites.')
        self.getControl(920).reset();self.entries=[]
        self.getControl(941).setLabel({'live':'Live TV','movie':'Movies','series':'Series','favorites':'Favourites'}[self.kind])
        if self.kind=='live':
            groups=rpc('PVR.GetChannelGroups',{'channeltype':'tv'}).get('channelgroups',[])
            if self.shared:
                def fetch(generation):
                    client=shared_favorites.SharedFavorites(self.shared.server)
                    try:return client.request('LiveTvCategories',cancelled=lambda:self.request_cancelled(generation)),False
                    except Exception:return [],True
                self.start_network('live categories',fetch,
                    lambda value:self.apply_live_categories(groups,*value))
                return
            self.apply_categories(live_group_choices(groups,[]));return
        elif self.kind=='favorites':
            self.apply_categories([('All shared favourites','all'),('Live channels','live'),('Movies','movie'),('Series','series'),('Local bookmarks / pending sync','local')]);return
        else:
            action='get_vod_categories' if self.kind=='movie' else 'get_series_categories'
            kind=self.kind
            def fetch(generation):
                rows=catalogue.api(action,cancelled=lambda:self.request_cancelled(generation))
                return [('All titles','all')]+[(r['category_name'],str(r['category_id'])) for r in sorted(rows,key=lambda r:catalogue.search_text(r['category_name']))]
            self.start_network(kind+' categories',fetch,self.apply_categories)
            return

    def apply_live_categories(self,groups,summaries,error):
        if self.closed:return
        if error:
            self.category_retry_at=time.monotonic()+15
            xbmc.log('Venom category service unavailable; keeping native PVR groups and retrying at chooser',xbmc.LOGINFO)
        else:self.category_retry_at=0
        self.apply_categories(live_group_choices(groups,summaries))

    def apply_categories(self,categories):
        if self.closed:return
        self.categories=categories
        self.setProperty('Venom.Posters','true' if self.kind in ('movie','series') else 'false')
        items=[xbmcgui.ListItem(label=clean_label(name)) for name,_ in self.categories]
        self.getControl(910).reset();self.getControl(910).addItems(items)
        self.getControl(910).selectItem(0);self.setFocusId(910)
        if self.pending_bookmark:
            category,label=self.pending_bookmark;self.pending_bookmark=None
            index=next((i for i,row in enumerate(categories) if str(row[1])==str(category)),0)
            self.selected_category_index=index;self.getControl(910).selectItem(index)
            self.category=category;self.category_name=label;self.scope=None;self.stack=[];self.page=0;self.query=''
            self.load_entries();self.setFocusId(920)
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

    def entry_snapshot(self):
        scope=getattr(self,'scope',None)
        return {'kind':self.kind,'category':getattr(self,'category',None),'scope':dict(scope) if scope else None,
                'recent':self.recent,'query':getattr(self,'query',''),'page':getattr(self,'page',0),
                'category_name':getattr(self,'category_name','')}

    def source_key(self,snapshot):
        return (snapshot['kind'],str(snapshot['category']),json.dumps(snapshot['scope'],sort_keys=True),snapshot['recent'])

    def cached_source(self,snapshot):
        if snapshot['kind']=='favorites':return None
        if not hasattr(self,'source_cache'):self.source_cache=OrderedDict()
        key=self.source_key(snapshot)
        cached=self.source_cache.get(key)
        if cached and time.monotonic()-cached[0]<NETWORK_CACHE_SECONDS:
            self.source_cache.move_to_end(key);return cached[1]
        return None

    def remember_source(self,snapshot,rows):
        if snapshot['kind']=='favorites':return
        if not hasattr(self,'source_cache'):self.source_cache=OrderedDict()
        key=self.source_key(snapshot)
        self.source_cache[key]=(time.monotonic(),rows)
        # Bound both category count and retained title count (large All titles).
        while len(self.source_cache)>4 or (len(self.source_cache)>1 and sum(len(v[1]) for v in self.source_cache.values())>35000):
            self.source_cache.popitem(last=False)

    def source_entries(self,snapshot=None):
        supplied=snapshot is not None
        snapshot=snapshot or self.entry_snapshot()
        cached=self.cached_source(snapshot)
        if cached is not None:return cached
        rows=self.fetch_entries(snapshot) if supplied else self.fetch_entries()
        self.remember_source(snapshot,rows)
        return rows

    def fetch_entries(self,snapshot=None,shared_client=None,cancelled=lambda:False):
        snapshot=snapshot or self.entry_snapshot()
        kind=snapshot['kind'];category=snapshot['category'];scope=snapshot['scope'];recent=snapshot['recent']
        shared=shared_client or self.shared
        if kind=='favorites':
            if category=='local':return list(catalogue.venom_state.read(catalogue.ROOT).get('favorites',{}).values())
            if not shared:raise RuntimeError('Jellyfin sign-in required for shared favourites')
            favorites=shared.entries(cancelled=cancelled)
            return [v for v in favorites if category=='all' or v['params'].get('kind')==category]
        if kind=='live':
            if str(category).startswith('jf:'):
                if not shared:raise RuntimeError('Jellyfin sign-in required')
                result=[]
                for offset in range(0,15001,250):
                    if cancelled():return []
                    page=shared.request('LiveTvCategories/'+category[3:]+'/Channels',cancelled=cancelled,startIndex=offset,limit=250,addCurrentProgram='false')
                    items=page.get('Items') or []
                    if offset>=15000:
                        if items:raise RuntimeError('Channel category exceeds safe size')
                        return result
                    for row in items:
                        art=shared.base+'/Items/'+row['Id']+'/Images/Primary?maxWidth=320&quality=85' if row.get('ImageTags',{}).get('Primary') else ''
                        result.append(entry(row['Name'],{'mode':'shared','kind':'live','id':row['Id'],'type':'TvChannel'},art=art,metadata={'channelnumber':row.get('ChannelNumber') or row.get('Number')}))
                    if not items or len(items)<250:return result
                raise RuntimeError('Channel category exceeds safe size')
            rows=rpc('PVR.GetChannels',{'channelgroupid':category,'properties':['thumbnail','channelnumber']}).get('channels',[])
            return [entry(r['label'],{'mode':'channel','kind':'live','id':str(r['channelid'])},r.get('thumbnail',''),metadata={'channelnumber':r['channelnumber']}) for r in rows]
        if scope:
            if scope.get('jf_series'):
                items=[]
                for offset in range(0,10001,500):
                    if cancelled():return []
                    page=shared.request('Shows/'+scope['jf_series']+'/Episodes',cancelled=cancelled,UserId=shared.user,IsMissing='false',StartIndex=offset,Limit=500).get('Items',[])
                    if offset>=10000:
                        if page:raise RuntimeError('Series exceeds safe episode browser limit')
                        break
                    items.extend(page)
                    if len(page)<500:break
                else:raise RuntimeError('Series exceeds safe episode browser limit')
                return [entry(r['Name'],{'mode':'shared','kind':'series','id':r['Id'],'type':'Episode'}) for r in items]
            data=catalogue.api('get_series_info',series_id=catalogue.ident(scope['id']),cancelled=cancelled)
            episodes=data.get('episodes') or {};cover=data.get('info',{}).get('cover','')
            if 'season' not in scope:
                return [entry('Season '+str(s),{'mode':'episodes','kind':'series','id':scope['id'],'season':s},cover,True) for s in sorted(episodes,key=lambda s:int(s) if str(s).isdigit() else 999)]
            return [entry(r.get('title') or 'Episode '+str(r.get('episode_num','')),{'mode':'play','kind':'series','id':catalogue.ident(r['id']),'ext':r.get('container_extension') or 'mp4','title':r.get('title',''),'series_id':scope['id'],'season':scope['season'],'episode':r.get('episode_num',0)},(r.get('info') or {}).get('movie_image') or cover,False,(r.get('info') or {}).get('plot',''),'episode') for r in episodes.get(scope['season'],[])]
        action='get_vod_streams' if kind=='movie' else 'get_series'
        args={} if category=='all' else {'category_id':category}
        rows=catalogue.api(action,cancelled=cancelled,**args)
        rows=catalogue.ordered(rows,order='recent' if recent else 'name')
        return [entry(r['name'],{'mode':'play','kind':'movie','id':catalogue.ident(r['stream_id']),'ext':r.get('container_extension') or 'mp4','title':r['name']} if kind=='movie' else {'mode':'seasons','kind':'series','id':catalogue.ident(r['series_id'])},r.get('stream_icon') or r.get('cover') or '',kind=='series',r.get('plot') or '','movie' if kind=='movie' else 'tvshow') for r in rows]

    def load_entries(self):
        # A cache hit has no replacement worker submission to invalidate a
        # pending shared-channel lookup, so cancel it explicitly on navigation.
        if getattr(self,'open_pending',None):self.cancel_network('entry navigation')
        self.getControl(940).setLabel('Loading…')
        self.entries=[];self.visible_entries=[];self.getControl(920).reset()
        snapshot=self.entry_snapshot()
        cached=self.cached_source(snapshot)
        if cached is not None:
            xbmc.log('Venom network: entries 0.000s cachehit',xbmc.LOGINFO)
            self.apply_entries(snapshot,cached);return
        # Raw unit-test windows have no lifecycle worker; production windows do.
        if not hasattr(self,'network'):
            self.apply_entries(snapshot,self.source_entries());return
        server=getattr(self.shared,'server',None)
        def fetch(generation):
            shared=shared_favorites.SharedFavorites(server) if server else self.shared
            return self.fetch_entries(snapshot,shared,lambda:self.request_cancelled(generation))
        self.start_network(snapshot['kind']+' entries',fetch,
            lambda rows:self.finish_entries(snapshot,rows))

    def finish_entries(self,snapshot,rows):
        if self.closed:return
        self.remember_source(snapshot,rows)
        self.apply_entries(snapshot,rows)

    def apply_entries(self,snapshot,rows):
        if getattr(self,'closed',False):return
        if hasattr(self,'setProperty'):self.setProperty('Venom.Posters','true' if self.kind in ('movie','series') else 'false')
        words=catalogue.search_text(snapshot['query']).split()
        self.entries=[r for r in rows if all(w in catalogue.search_text(r['label']) for w in words)]
        self.page=min(snapshot['page'],max(0,(len(self.entries)-1)//PAGE))
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
        selection=(p.get('mode'),p.get('id'),p.get('season'))
        now=time.monotonic()
        if self.open_selection and self.open_selection[0]==selection and now-self.open_selection[1]<1:return
        if self.open_pending and self.open_pending[0]!=selection:
            self.cancel_network('new playback selection')
        handoff=getattr(self,'live_handoff',None)
        if handoff:
            if handoff.get('selection')==selection:return
            self.cancel_live_handoff('new selection')
        self.open_selection=(selection,now)
        if p['mode']=='shared':
            if p.get('type')=='TvChannel':
                if self.open_pending and self.open_pending[0]==selection:return
                target={'Id':p['id'],'Name':e['label'],'ChannelNumber':e.get('metadata',{}).get('channelnumber')}
                pvr_cache=dict(self.pvr_playback_cache)
                def lookup(_generation):return playback_from_pvr_cache(target,pvr_cache,rpc),pvr_cache
                def play(result):
                    playback,updated_cache=result;self.pvr_playback_cache=updated_cache;self.open_pending=None
                    if 'file' in playback:xbmc.log('Venom playback: native PVR identity unavailable; delegating exact Jellyfin channel ID',xbmc.LOGINFO)
                    self.begin_channel_playback(playback,selection)
                generation=self.start_network('shared channel lookup',lookup,play)
                self.open_pending=(selection,generation)
            elif p.get('type')=='Series':
                self.stack.append((self.kind,self.scope,self.page,self.query,self.category_name,pos))
                self.kind='series';self.scope={'jf_series':p['id']};self.page=0;self.query='';self.category_name=e['label'];self.load_entries()
            else:
                xbmc.Player().play('plugin://plugin.video.jellyfin/?mode=play&id='+p['id']);xbmc.executebuiltin('ActivateWindow(fullscreenvideo)')
        elif p['mode']=='channel':
            self.begin_channel_playback({'channelid':int(catalogue.ident(p['id']))},selection)
        elif p['mode'] in ('seasons','episodes'):
            self.stack.append((self.kind,self.scope,self.page,self.query,self.category_name,pos))
            self.kind='series';self.scope=p;self.page=0;self.query='';self.category_name=e['label'];self.load_entries()
        elif p['mode']=='items':
            self.kind=p['kind'];self.pending_bookmark=(p['category'],e['label']);self.load_categories()
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
            server=self.shared.server;enabled=not exists;key=shared_favorites.identity(e)
            origin=(self.kind,self.category)
            def mutate(generation):
                return shared_favorites.SharedFavorites(server).set(e,enabled)
            def applied(_result):
                if exists:self.shared_keys.discard(key)
                else:self.shared_keys.add(key)
                # Discard any pre-mutation snapshot still in flight.
                self.favorite_check=0
                xbmcgui.Window(10000).setProperty('Habibi.Home.Refresh',str(time.time_ns()))
                if self.network_busy or (self.kind,self.category)!=origin:return
                if self.close_requested:return
                if self.kind=='favorites':self.load_entries()
                else:self.render();self.getControl(920).selectItem(pos)
            self.start_critical_network('favourite mutation',mutate,applied)
        elif choice==1:self.open_selected()

    def onClick(self,control):
        def handle():
            if control in (901,902,903,904):
                self.pending_bookmark=None
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
            elif self.getFocusId()==920:
                self.cancel_network('navigation back');self.cancel_live_handoff('navigation back');self.open_pending=None;self.setFocusId(910)
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
