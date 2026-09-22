"""Offline regression checks for grid paging, remote actions and sync filtering."""
import ast
import importlib.util
from pathlib import Path
import runpy
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).parent

class Control:
    def __init__(self):self.items=[];self.position=0;self.label=''
    def reset(self):self.items=[];self.position=0
    def addItems(self,items):self.items.extend(items)
    def getSelectedPosition(self):return self.position
    def selectItem(self,index):self.position=index
    def setLabel(self,label):self.label=label

class Item:
    def __init__(self,label=''):self.label=label;self.properties={}
    def setArt(self,art):self.art=art
    def setProperty(self,key,value):self.properties[key]=value

class Window:
    def __init__(self):self.controls={};self.focus=910;self.kind='live';self.recent=False;self.shared=None;self.shared_keys=set()
    def getControl(self,id):return self.controls.setdefault(id,Control())
    def setFocusId(self,id):self.focus=id
    def getFocusId(self):return self.focus
    def setProperty(self,key,value):setattr(self,key,value)
    def close(self):self.window_closed=True

class Tests(unittest.TestCase):
    def test_network_worker_replaces_pending_selection_with_latest(self):
        Worker=self.load()['LatestWorker'];worker=Worker();started=threading.Event();release=threading.Event();latest=threading.Event();calls=[]
        def first():
            calls.append(1);started.set();release.wait(1);return 1
        worker.submit(1,'first',first);self.assertTrue(started.wait(1))
        worker.submit(2,'stale',lambda:calls.append(2))
        worker.submit(3,'latest',lambda:(calls.append(3),latest.set(),3)[2])
        release.set();self.assertTrue(latest.wait(1))
        result=None
        for _ in range(100):
            result=worker.poll()
            if result and result[0]==3:break
            time.sleep(.005)
        worker.close()
        self.assertEqual(calls,[1,3]);self.assertEqual(result[0],3);self.assertEqual(result[2],3)

    def test_network_worker_close_discards_blocked_late_result(self):
        Worker=self.load()['LatestWorker'];worker=Worker();started=threading.Event();release=threading.Event()
        def blocked():started.set();release.wait(1);return 'late'
        worker.submit(1,'blocked',blocked);self.assertTrue(started.wait(1))
        worker.close();release.set();time.sleep(.02)
        self.assertIsNone(worker.poll())

    def test_confirmed_favourite_mutation_survives_close_but_has_no_late_ui_result(self):
        Worker=self.load()['LatestWorker'];worker=Worker();started=threading.Event();release=threading.Event();mutated=threading.Event()
        def blocked():started.set();release.wait(1)
        worker.submit(1,'blocked read',blocked);self.assertTrue(started.wait(1))
        self.assertTrue(worker.submit(2,'favourite mutation',lambda:mutated.set(),critical=True))
        worker.close();release.set();self.assertTrue(mutated.wait(1));time.sleep(.02)
        self.assertIsNone(worker.poll());self.assertIsNone(worker.poll_critical())

    def test_favourite_completion_is_separate_from_replaceable_navigation_result(self):
        Worker=self.load()['LatestWorker'];worker=Worker();started=threading.Event();release=threading.Event();mutated=threading.Event();navigated=threading.Event()
        def blocked():started.set();release.wait(1)
        worker.submit(1,'blocked read',blocked);self.assertTrue(started.wait(1))
        self.assertTrue(worker.submit(2,'favourite mutation',lambda:(mutated.set() or 'verified'),critical=True))
        self.assertFalse(worker.can_submit_critical())
        worker.submit(3,'new navigation',lambda:(navigated.set() or 'new'))
        release.set();self.assertTrue(mutated.wait(1));self.assertTrue(navigated.wait(1))
        critical=None
        for _ in range(100):
            critical=worker.poll_critical()
            if critical:break
            time.sleep(.005)
        worker.close()
        self.assertEqual(critical[2],'verified')

    def test_late_generation_result_cannot_apply_over_current_request(self):
        import queue
        mod=self.load();b=mod['Browser']();applied=[]
        results=iter([(1,'old entries',['old'],None,.2),(2,'new entries',['new'],None,.1)])
        b.closed=False;b.jobs=queue.Queue();b.busy=False;b.network=types.SimpleNamespace(poll=lambda:next(results),poll_critical=lambda:None)
        b.request_generation=2;b.request_apply=lambda value:applied.extend(value);b.network_busy=True
        b.retry_categories_if_ready=lambda:False;b.favorite_result=None;b.shared=None
        b.process();self.assertEqual(applied,[]);self.assertTrue(b.network_busy)
        b.process();self.assertEqual(applied,['new']);self.assertFalse(b.network_busy)

    def test_confirmed_mutation_defers_window_close_until_completion(self):
        import queue
        mod=self.load();b=mod['Browser']();applied=[]
        critical=iter([None,(1,'favourite mutation','verified',None,.1)])
        b.closed=False;b.close_requested=False;b.critical_busy=True;b.favorite_generation=0
        b.jobs=queue.Queue();b.busy=False;b.network_busy=False;b.request_generation=1;b.request_apply=None
        b.network=types.SimpleNamespace(poll=lambda:None,poll_critical=lambda:next(critical),discard_pending=lambda:None,close=lambda:None)
        b.critical_apply=lambda value:applied.append(value);b.retry_categories_if_ready=lambda:False
        b.favorite_result=None;b.shared=None
        b.close();self.assertFalse(b.closed);self.assertTrue(b.close_requested)
        b.process();self.assertFalse(b.closed)
        b.process();self.assertTrue(b.closed);self.assertEqual(applied,['verified'])

    def test_bookmark_category_waits_for_category_apply_before_loading_entries(self):
        mod=self.load();b=mod['Browser']();loaded=[]
        b.closed=False;b.kind='movie';b.pending_bookmark=('7','Bookmarked');b.load_entries=lambda:loaded.append((b.category,b.category_name))
        b.apply_categories([('All','all'),('Drama','7')])
        self.assertEqual(loaded,[('7','Bookmarked')]);self.assertEqual(b.getControl(910).position,1);self.assertEqual(b.getFocusId(),920)

    def test_exact_pvr_match_uses_native_player(self):
        choose=self.load()['channel_playback_item']
        self.assertEqual({'channelid':7},choose({'Id':'a'*32,'Name':'MBC 3','ChannelNumber':'100'},[{'channelid':7,'label':'MBC 3','channelnumber':100}]))
    def test_missing_renamed_or_ambiguous_pvr_uses_exact_server_id(self):
        choose=self.load()['channel_playback_item'];target={'Id':'a'*32,'Name':'MBC 3','ChannelNumber':'100'}
        row={'channelid':7,'label':'MBC 3','channelnumber':100}
        for channels in [[],[{**row,'label':'MBC 3 FHD'}],[row,{**row,'channelid':8}]]:
            self.assertEqual({'file':'plugin://plugin.video.jellyfin/?mode=play&id='+'a'*32},choose(target,channels))
    def test_unique_full_label_survives_pvr_renumbering(self):
        choose=self.load()['channel_playback_item']
        target={'Id':'a'*32,'Name':'beIN MOVIES 1 HD','ChannelNumber':'166'}
        rows=[{'channelid':7,'label':'beIN MOVIES 1 HD','channelnumber':160},
              {'channelid':8,'label':'beIN MOVIES 2 HD','channelnumber':162},
              {'channelid':9,'label':'beIN MOVIES 1 FHD','channelnumber':161}]
        self.assertEqual({'channelid':7},choose(target,rows))
    def test_known_prefix_and_number_disambiguate_duplicate_full_labels(self):
        choose=self.load()['channel_playback_item']
        target={'Id':'a'*32,'Name':'IRQ : MBC IRAQ 4K','ChannelNumber':'9527'}
        rows=[{'channelid':7,'label':'MBC IRAQ 4K','channelnumber':9255},
              {'channelid':8,'label':'MBC IRAQ 4K','channelnumber':9527}]
        self.assertEqual({'channelid':8},choose(target,rows))
    def test_known_prefix_and_space_normalization_match_same_number(self):
        choose=self.load()['channel_playback_item']
        target={'Id':'a'*32,'Name':'LB : AL JADEED  HD','ChannelNumber':'9352'}
        rows=[{'channelid':9666,'label':'AL JADEED HD','channelnumber':9352}]
        self.assertEqual({'channelid':9666},choose(target,rows))
    def test_unique_label_fallback_keeps_digits_and_quality_suffix_significant(self):
        choose=self.load()['channel_playback_item']
        target={'Id':'a'*32,'Name':'beIN MOVIES 1 HD','ChannelNumber':'166'}
        fallback={'file':'plugin://plugin.video.jellyfin/?mode=play&id='+'a'*32}
        self.assertEqual(fallback,choose(target,[{'channelid':8,'label':'beIN MOVIES 2 HD','channelnumber':166}]))
        self.assertEqual(fallback,choose(target,[{'channelid':9,'label':'beIN MOVIES 1 FHD','channelnumber':166}]))
    def test_renumbered_label_fallback_does_not_strip_country_prefix(self):
        choose=self.load()['channel_playback_item']
        target={'Id':'a'*32,'Name':'UK : NEWS HD','ChannelNumber':'100'}
        fallback={'file':'plugin://plugin.video.jellyfin/?mode=play&id='+'a'*32}
        self.assertEqual(fallback,choose(target,[{'channelid':7,'label':'NEWS HD','channelnumber':101}]))
        self.assertEqual({'channelid':7},choose(target,[{'channelid':7,'label':'NEWS HD','channelnumber':100}]))
    def test_channel_fallback_rejects_invalid_server_id(self):
        with self.assertRaises(RuntimeError):self.load()['channel_playback_item']({'Id':'../bad','Name':'MBC 3'},[])
    def test_shared_playback_cache_reuses_enumeration_but_freshly_verifies(self):
        mod=self.load();calls=[];target={'Id':'a'*32,'Name':'MBC 3','ChannelNumber':'100'}
        row={'channelid':7,'label':'MBC 3','channelnumber':100}
        def rpc(method,params):
            calls.append(method)
            return {'channels':[row]} if method=='PVR.GetChannels' else {'channeldetails':row}
        cache={}
        self.assertEqual(mod['playback_from_pvr_cache'](target,cache,rpc,now=10),{'channelid':7})
        self.assertEqual(mod['playback_from_pvr_cache'](target,cache,rpc,now=20),{'channelid':7})
        self.assertEqual(calls,['PVR.GetChannels','PVR.GetChannelDetails','PVR.GetChannelDetails'])
        self.assertEqual(mod['playback_from_pvr_cache'](target,cache,rpc,now=41),{'channelid':7})
        self.assertEqual(calls.count('PVR.GetChannels'),2)

    def test_shared_playback_cache_fails_closed_on_reassigned_id_or_pvr_error(self):
        mod=self.load();target={'Id':'a'*32,'Name':'MBC 3','ChannelNumber':'100'}
        cache={'stamp':10,'rows':[{'channelid':7,'label':'MBC 3','channelnumber':100}]}
        fallback={'file':'plugin://plugin.video.jellyfin/?mode=play&id='+'a'*32}
        mismatch=lambda method,params:{'channeldetails':{'channelid':7,'label':'Other','channelnumber':100}}
        self.assertEqual(mod['playback_from_pvr_cache'](target,cache,mismatch,now=20),fallback)
        reassigned=lambda method,params:{'channeldetails':{'channelid':8,'label':'MBC 3','channelnumber':100}}
        self.assertEqual(mod['playback_from_pvr_cache'](target,cache,reassigned,now=20),fallback)
        def broken(method,params):raise RuntimeError('PVR unavailable')
        self.assertEqual(mod['playback_from_pvr_cache'](target,{},broken,now=20),fallback)
    def test_renumbered_unique_label_is_freshly_reverified(self):
        mod=self.load();target={'Id':'a'*32,'Name':'beIN MOVIES 1 HD','ChannelNumber':'166'};calls=[]
        row={'channelid':7,'label':'beIN MOVIES 1 HD','channelnumber':160}
        def rpc(method,params):
            calls.append(method)
            return {'channels':[row]} if method=='PVR.GetChannels' else {'channeldetails':row}
        self.assertEqual(mod['playback_from_pvr_cache'](target,{},rpc,now=10),{'channelid':7})
        self.assertEqual(calls,['PVR.GetChannels','PVR.GetChannelDetails'])
        renamed=lambda method,params:{'channels':[row]} if method=='PVR.GetChannels' else {'channeldetails':{**row,'label':'beIN MOVIES 2 HD'}}
        self.assertEqual(mod['playback_from_pvr_cache'](target,{},renamed,now=10),{'file':'plugin://plugin.video.jellyfin/?mode=play&id='+'a'*32})
    def test_shared_channel_data_lookup_precedes_ui_player_open_without_resolve(self):
        mod=self.load();b=mod['Browser']();calls=[];scheduled={};schedules=[]
        b.visible_entries=[mod['entry']('MBC 3',{'mode':'shared','kind':'live','id':'a'*32,'type':'TvChannel'},metadata={'channelnumber':'100'})]
        b.pvr_playback_cache={};b.open_selection=None;b.open_pending=None
        b.shared=types.SimpleNamespace(resolve=lambda e:(_ for _ in ()).throw(AssertionError('redundant resolve')))
        def start(name,work,apply):
            schedules.append(name);scheduled.update(name=name,work=work,apply=apply);return len(schedules)
        b.start_network=start
        def rpc(method,params):
            calls.append(method)
            if method=='PVR.GetChannels':return {'channels':[{'channelid':7,'label':'MBC 3','channelnumber':100}]}
            if method=='PVR.GetChannelDetails':return {'channeldetails':{'channelid':7,'label':'MBC 3','channelnumber':100}}
            return {}
        mod['Browser'].open_selected.__globals__['rpc']=rpc
        b.open_selected();self.assertEqual(calls,[]);self.assertEqual(scheduled['name'],'shared channel lookup')
        b.open_selected();self.assertEqual(len(schedules),1)
        result=scheduled['work'](1);self.assertNotIn('Player.Open',calls)
        scheduled['apply'](result);self.assertEqual(calls[-1],'Player.Open')

    def test_different_native_channel_stops_then_waits_for_old_player_absence(self):
        mod=self.load();b=mod['Browser']();b.closed=False;b.live_handoff=None;b.open_pending=None;calls=[]
        players=[{'playerid':1,'type':'video'}]
        def rpc(method,params):
            calls.append((method,params))
            if method=='Player.GetActivePlayers':return list(players)
            if method=='Player.GetItem':return {'item':{'id':7,'type':'channel'}}
            return 'OK'
        mod['Browser'].begin_channel_playback.__globals__['rpc']=rpc
        self.assertTrue(b.begin_channel_playback({'channelid':8},('channel','8',None),now=10))
        self.assertEqual([c[0] for c in calls],['Player.GetActivePlayers','Player.GetItem','Player.Stop'])
        b.poll_live_handoff(now=10);self.assertNotIn('Player.Open',[c[0] for c in calls])
        players.clear();self.assertTrue(b.poll_live_handoff(now=10.2))
        self.assertEqual(calls[-1],('Player.Open',{'item':{'channelid':8}}));self.assertIsNone(b.live_handoff)

    def test_channel_break_before_make_never_stops_same_unknown_or_fallback(self):
        mod=self.load();Browser=mod['Browser']
        cases=[
            ([{'playerid':1,'type':'video'}],{'item':{'id':8,'type':'channel'}},{'channelid':8}),
            ([{'playerid':1,'type':'video'}],{'item':{'id':3,'type':'movie'}},{'channelid':8}),
            ([],{}, {'channelid':8}),
            ([{'playerid':1,'type':'video'}],{'item':{'id':7,'type':'channel'}},{'file':'plugin://jellyfin/channel'}),
        ]
        for players,item,playback in cases:
            b=Browser();b.closed=False;b.live_handoff=None;b.open_pending=None;calls=[]
            def rpc(method,params,players=players,item=item):
                calls.append((method,params))
                if method=='Player.GetActivePlayers':return players
                if method=='Player.GetItem':return item
                return 'OK'
            Browser.begin_channel_playback.__globals__['rpc']=rpc
            self.assertFalse(b.begin_channel_playback(playback,now=1))
            self.assertNotIn('Player.Stop',[c[0] for c in calls])
            self.assertEqual(calls[-1][0],'Player.Open')

    def test_stop_error_and_handoff_timeout_fail_closed_without_open(self):
        mod=self.load();Browser=mod['Browser'];b=Browser();b.closed=False;b.live_handoff=None;b.open_pending=None;calls=[];errors=[]
        def stop_fails(method,params):
            calls.append(method)
            if method=='Player.GetActivePlayers':return [{'playerid':1,'type':'video'}]
            if method=='Player.GetItem':return {'item':{'id':7,'type':'channel'}}
            if method=='Player.Stop':raise RuntimeError('stop failed')
        Browser.begin_channel_playback.__globals__['rpc']=stop_fails
        with self.assertRaisesRegex(RuntimeError,'stop failed'):b.begin_channel_playback({'channelid':8},now=1)
        self.assertIsNone(b.live_handoff);self.assertNotIn('Player.Open',calls)
        def waiting(method,params):
            if method=='Player.GetActivePlayers':return [{'playerid':1,'type':'video'}]
            if method=='Player.GetItem':return {'item':{'id':7,'type':'channel'}}
            return 'OK'
        Browser.begin_channel_playback.__globals__['rpc']=waiting
        b.report_error=lambda error:errors.append(type(error).__name__)
        b.begin_channel_playback({'channelid':8},now=1)
        b.poll_live_handoff(now=1+mod['LIVE_HANDOFF_TIMEOUT_SECONDS'])
        self.assertIsNone(b.live_handoff);self.assertEqual(errors,['TimeoutError'])

    def test_delayed_open_error_is_reported_without_retry_or_loop_escape(self):
        mod=self.load();Browser=mod['Browser'];b=Browser();b.closed=False;b.open_pending=('channel',1);errors=[];opens=[]
        b.live_handoff={'playerid':1,'playback':{'channelid':8},'selection':('channel','8',None),'deadline':30,'next_poll':0}
        def rpc(method,params):
            if method=='Player.GetActivePlayers':return []
            if method=='Player.Open':opens.append(params);raise RuntimeError('open failed')
        Browser.poll_live_handoff.__globals__['rpc']=rpc;b.report_error=lambda error:errors.append(str(error))
        self.assertFalse(b.poll_live_handoff(now=2));self.assertIsNone(b.live_handoff);self.assertIsNone(b.open_pending)
        self.assertEqual(len(opens),1);self.assertEqual(errors,['open failed'])

    def test_new_selection_cancels_stale_handoff_and_unexpected_player_blocks_open(self):
        mod=self.load();Browser=mod['Browser'];b=Browser();b.closed=False;b.live_handoff=None;b.open_pending=('old',1);calls=[];errors=[]
        b.live_handoff={'playerid':1,'playback':{'channelid':8},'selection':('channel','8',None),'deadline':30,'next_poll':0}
        b.cancel_live_handoff('new selection');self.assertIsNone(b.live_handoff);self.assertIsNone(b.open_pending)
        b.live_handoff={'playerid':1,'playback':{'channelid':9},'selection':('channel','9',None),'deadline':30,'next_poll':0}
        Browser.poll_live_handoff.__globals__['rpc']=lambda method,params:[{'playerid':2,'type':'video'}]
        b.report_error=lambda error:errors.append(str(error))
        self.assertFalse(b.poll_live_handoff(now=2));self.assertIsNone(b.live_handoff)
        self.assertEqual(errors,['Another video started during channel switch'])

    def test_navigation_back_cancels_channel_handoff(self):
        mod=self.load();b=mod['Browser']();cancelled=[]
        b.busy=False;b.stack=[];b.focus=920;b.open_pending=('channel',1)
        b.live_handoff={'playerid':1,'playback':{'channelid':8},'selection':('channel','8',None),'deadline':30,'next_poll':0}
        b.cancel_network=lambda reason:cancelled.append(('network',reason))
        original=b.cancel_live_handoff
        b.cancel_live_handoff=lambda reason:(cancelled.append(('handoff',reason)),original(reason))[1]
        b.onAction(types.SimpleNamespace(getId=lambda:92))
        self.assertIsNone(b.live_handoff);self.assertIsNone(b.open_pending);self.assertEqual(b.getFocusId(),910)
        self.assertEqual(cancelled,[('network','navigation back'),('handoff','navigation back')])

    def test_distinct_native_selection_invalidates_stale_shared_lookup(self):
        import queue
        mod=self.load();Browser=mod['Browser'];b=Browser();opened=[];applied=[]
        old_selection=('shared','a'*32,None);b.closed=False;b.jobs=queue.Queue();b.busy=False
        b.open_selection=None;b.open_pending=(old_selection,1);b.request_generation=1;b.request_apply=lambda value:applied.append(value);b.network_busy=True
        b.network=types.SimpleNamespace(discard_pending=lambda:None,poll=lambda:(1,'shared channel lookup','old',None,.1),poll_critical=lambda:None)
        b.retry_categories_if_ready=lambda:False;b.shared=None;b.live_handoff=None
        b.visible_entries=[mod['entry']('New',{'mode':'channel','kind':'live','id':'8'})]
        Browser.open_selected.__globals__['catalogue'].ident=lambda value:value
        b.begin_channel_playback=lambda playback,selection:opened.append((playback,selection))
        b.open_selected();self.assertEqual(len(opened),1);self.assertEqual(opened[0][0],{'channelid':8})
        self.assertEqual(opened[0][1][:3],('channel','8',None))
        self.assertEqual(b.request_generation,2);self.assertIsNone(b.open_pending);self.assertIsNone(b.request_apply)
        b.process();self.assertEqual(applied,[]);self.assertEqual(len(opened),1)

    def test_cache_hit_navigation_invalidates_stale_shared_lookup(self):
        from collections import OrderedDict
        mod=self.load();b=mod['Browser']();discarded=[]
        b.kind='live';b.category='all';b.scope=None;b.page=0;b.query='';b.category_name='All';b.closed=False
        b.request_generation=4;b.request_apply=lambda value:None;b.network_busy=True;b.open_pending=(('shared','a'*32,None),4)
        b.network=types.SimpleNamespace(discard_pending=lambda:discarded.append(True))
        snapshot=b.entry_snapshot();b.source_cache=OrderedDict([(b.source_key(snapshot),(time.monotonic(),[mod['entry']('Cached',{})]))])
        b.load_entries()
        self.assertEqual(discarded,[True]);self.assertEqual(b.request_generation,5);self.assertIsNone(b.open_pending)
        self.assertEqual([row['label'] for row in b.entries],['Cached'])

    def test_cancelled_shared_channel_lookup_can_be_retried(self):
        mod=self.load();b=mod['Browser']();schedules=[]
        b.visible_entries=[mod['entry']('MBC 3',{'mode':'shared','kind':'live','id':'a'*32,'type':'TvChannel'},metadata={'channelnumber':'100'})]
        b.pvr_playback_cache={};b.open_selection=None;b.open_pending=None;b.request_generation=0;b.request_apply=None;b.network_busy=False
        b.network=types.SimpleNamespace(discard_pending=lambda:None)
        b.start_network=lambda name,work,apply:(schedules.append((work,apply)) or len(schedules))
        b.open_selected();self.assertEqual(len(schedules),1);self.assertIsNotNone(b.open_pending)
        b.cancel_network('test cancel');self.assertIsNone(b.open_pending)
        b.open_selection=None;b.open_selected();self.assertEqual(len(schedules),2)

    def test_failed_shared_channel_lookup_clears_pending_for_retry(self):
        import queue
        mod=self.load();b=mod['Browser']();selection=('shared','a'*32,None);errors=[]
        b.closed=False;b.jobs=queue.Queue();b.busy=False;b.network_busy=True;b.request_generation=4
        b.request_apply=lambda value:None;b.open_pending=(selection,4)
        b.network=types.SimpleNamespace(poll=lambda:(4,'shared channel lookup',None,RuntimeError('failed'),.1),poll_critical=lambda:None)
        b.report_error=lambda error:errors.append(str(error));b.retry_categories_if_ready=lambda:False;b.shared=None
        b.process();self.assertIsNone(b.open_pending);self.assertEqual(errors,['failed'])
    def test_category_retry_is_bounded_and_never_replaces_open_grid(self):
        import queue
        mod=self.load();b=mod['Browser']();b.category=None;b.closed=False;b.busy=False;b.jobs=queue.Queue()
        b.category_retry_at=20
        with patch('time.monotonic',return_value=19):
            self.assertFalse(b.retry_categories_if_ready())
        with patch('time.monotonic',return_value=21):
            b.category='alltv';self.assertFalse(b.retry_categories_if_ready())
            b.category=None;b.busy=True;self.assertFalse(b.retry_categories_if_ready())
            b.busy=False;self.assertTrue(b.retry_categories_if_ready())
            self.assertEqual(b.jobs.qsize(),1)
            self.assertFalse(b.retry_categories_if_ready())
            self.assertEqual(b.jobs.qsize(),1)
    def test_channel_display_cleanup_preserves_identity_and_other_titles(self):
        mod=self.load();clean=mod['channel_display_name']
        self.assertEqual(clean('9328 CA TSN1 FHD'),'TSN1 FHD')
        self.assertEqual(clean('5849 VIP UK: SKY SPORTS 1 4K'),'SKY SPORTS 1 4K')
        for name in ['24 NEWS HD','MBC 1 HD','360 العربية','BBC UK NEWS']:
            self.assertEqual(clean(name),name)
        b=mod['Browser']();b.page=0;b.query='';b.category_name='Favourites'
        live=mod['entry']('9328 CA TSN1 FHD',{'kind':'live','mode':'channel','id':'7'})
        movie=mod['entry']('VIP UK Story',{'kind':'movie','id':'8'})
        b.entries=[live,movie];b.render()
        # User confirmed Kodi names already work; don't add a second cosmetic
        # rename layer while deploying the missing category navigation.
        self.assertEqual([i.label for i in b.getControl(920).items],['9328 CA TSN1 FHD','VIP UK Story'])
        self.assertEqual(live['label'],'9328 CA TSN1 FHD')
        self.assertEqual(live['params']['id'],'7')
    def test_curated_groups_pinned_provider_rank_preserved(self):
        choices=self.load()['live_group_choices'](
            [{'label':'Tunisia','channelgroupid':1},{'label':'Arabic News','channelgroupid':2}],
            [{'id':'collection-news','name':'أخبار'},{'id':'category-a','name':'Arabic News'},{'id':'category-t','name':'Tunisia'}])
        self.assertEqual(choices,[('أخبار','jf:collection-news'),('All channels','alltv'),('Arabic News','jf:category-a'),('Tunisia','jf:category-t')])
    def test_provider_groups_do_not_require_pvr_import(self):
        mod=self.load()
        self.assertEqual(mod['live_group_choices']([],[{'id':'category-a','name':'Arabic News'}]),[('All channels','alltv'),('Arabic News','jf:category-a')])
    def test_curated_entries_use_existing_shared_channel_playback(self):
        mod=self.load();b=mod['Browser']();b.kind='live';b.category='jf:collection-news'
        b.shared=types.SimpleNamespace(request=lambda *a,**k:{'Items':[{'Name':'News','Id':'native','ChannelNumber':'10'}],'TotalRecordCount':1})
        row=b.fetch_entries()[0]
        self.assertEqual(row['params'],{'mode':'shared','kind':'live','id':'native','type':'TvChannel'})
    def test_curated_paging_stops_on_short_page_when_total_is_missing_or_stale(self):
        mod=self.load();b=mod['Browser']();b.kind='live';b.category='jf:category';b.scope=None;b.recent=False;b.query='';b.page=0;b.category_name='Category'
        calls=[]
        def request(path,**params):
            calls.append(params['startIndex']);count=250 if params['startIndex']==0 else 2
            return {'Items':[{'Name':'Channel','Id':'a'*32,'ChannelNumber':str(i)} for i in range(count)],'TotalRecordCount':1}
        b.shared=types.SimpleNamespace(base='http://jf',request=request)
        self.assertEqual(len(b.fetch_entries()),252);self.assertEqual(calls,[0,250])
    def load(self):
        cat=types.SimpleNamespace(ROOT='unused',search_text=lambda x:str(x).casefold(),favorite_key=lambda x:str(x),venom_state=types.SimpleNamespace(read=lambda p:{'favorites':{}}))
        modules={'default':cat,'xbmc':types.SimpleNamespace(log=lambda *a:None,executebuiltin=lambda *a:None,LOGINFO=1,LOGERROR=3),'xbmcgui':types.SimpleNamespace(WindowXML=Window,ListItem=Item)}
        with patch.dict(sys.modules,modules):
            result=runpy.run_path(str(ROOT/'plugin.video.venom.tv/browser.py'))
        return result
    def test_page_bounded_and_clamped(self):
        mod=self.load();b=mod['Browser']();b.kind='live';b.page=999;b.query='';b.category_name='All'
        b.source_entries=lambda:[mod['entry']('Channel '+str(i),{'kind':'live','id':str(i)}) for i in range(165)]
        b.load_entries();self.assertEqual(b.page,2);self.assertEqual(len(b.getControl(920).items),5)
        b.page=0;b.render();self.assertEqual(len(b.getControl(920).items),80)
    def test_search_and_empty_results(self):
        mod=self.load();b=mod['Browser']();b.page=0;b.query='arabic';b.category_name='All'
        b.source_entries=lambda:[mod['entry']('Arabic News',{}),mod['entry']('Sport',{})]
        b.load_entries();self.assertEqual(len(b.entries),1)
        b.query='missing';b.load_entries();self.assertEqual(b.entries,[])
    def test_arabic_preserved_emoji_removed(self):
        clean=self.load()['clean_label']
        self.assertEqual(clean('⚽  العربية \ufe0f'),'العربية')
    def test_grid_star_uses_server_favourite_identity(self):
        mod=self.load();b=mod['Browser']();b.page=0;b.query='';b.category_name='Movies'
        b.entries=[mod['entry']('Movie',{'mode':'play','kind':'movie','id':'7'})]
        b.shared=types.SimpleNamespace(keys=lambda:(_ for _ in ()).throw(AssertionError('render contacted server')))
        b.shared_keys={'movie:7'}
        b.render();self.assertEqual(b.getControl(920).items[0].properties['venom.favorite'],'true')
        b.shared_keys=set()
        b.render();self.assertEqual(b.getControl(920).items[0].properties['venom.favorite'],'false')
    def test_category_cache_reuses_search_source(self):
        from collections import OrderedDict
        mod=self.load();b=mod['Browser']();b.kind='movie';b.category='all';b.scope=None;b.source_cache=OrderedDict()
        calls=[]
        b.fetch_entries=lambda:(calls.append(True) or [mod['entry']('A',{})])
        self.assertEqual(b.source_entries(),b.source_entries());self.assertEqual(len(calls),1)
        b.category='new';b.source_entries();self.assertEqual(len(calls),2)
    def test_shared_series_not_truncated_at_500(self):
        mod=self.load();b=mod['Browser']();b.kind='series';b.scope={'jf_series':'s'};b.closed=False
        offsets=[]
        def request(path,**params):
            offsets.append(params['StartIndex'])
            return {'Items':[{'Name':'Episode','Id':str(i)} for i in range(500 if params['StartIndex']==0 else 1)]}
        b.shared=types.SimpleNamespace(user='u',request=request)
        self.assertEqual(len(b.fetch_entries()),501);self.assertEqual(offsets,[0,500])
    def test_exclusion_boundaries_and_whitelist(self):
        # Test the shipped patch itself; no private working-tree fixture needed.
        lines=(ROOT/'patches/jellyfin-2.2.0-habibi.patch').read_text().splitlines()
        start=next(i for i,line in enumerate(lines) if line.startswith('+def excluded_stream_item('))
        added=[]
        for line in lines[start:]:
            if not line.startswith('+'):break
            added.append(line[1:])
        source=ast.parse('\n'.join(added))
        function=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='excluded_stream_item')
        namespace={};exec(compile(ast.Module(body=[function],type_ignores=[]),'test','exec'),namespace)
        excluded=namespace['excluded_stream_item'];policy={'Whitelist':[],'ExcludedLibraryPaths':{'/config/venom/series':'iptv'}}
        self.assertTrue(excluded({'Type':'Season','Path':'/config/venom/series/show/season'},policy))
        self.assertFalse(excluded({'Path':'/config/venom/series-other/show'},policy))
        self.assertFalse(excluded({'Path':'/media/shows/a'},policy))
        self.assertFalse(excluded({},policy))
        policy['Whitelist']=['Mixed:iptv'];self.assertFalse(excluded({'Path':'/config/venom/series/show'},policy))
    def test_xml_navigation_ids_exist(self):
        import xml.etree.ElementTree as ET
        root=ET.parse(ROOT/'plugin.video.venom.tv/resources/skins/Default/1080i/VenomBrowser.xml').getroot()
        ids=[e.get('id') for e in root.iter('control') if e.get('id')]
        self.assertEqual(len(ids),len(set(ids)))
        for control in root.iter('control'):
            for tag in ('onleft','onright','onup','ondown'):
                action=control.findtext(tag)
                if action and action.isdigit():self.assertIn(action,ids)

if __name__=='__main__':unittest.main()
