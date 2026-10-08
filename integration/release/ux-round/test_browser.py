"""Run BOTH transport contract sets with the same generic hidden-owner repair."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import overlay

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod

sys.modules['overlay']=load('ux_old_focus',HERE.parent/'remote-catchup/overlay.py')
remote=load('ux_remote_contracts',HERE.parent/'remote-catchup/test_remote.py')
sys.modules['overlay']=overlay
local=load('ux_local_contracts',HERE.parent/'shared-am9/test_local_browser.py')
remote_setup=remote.module.setUpModule
local_setup=local.setUpModule
def setup_remote():
    remote_setup()
    path=remote.module.STAGE/'browser.py';path.write_text(overlay.browser(path.read_text()))
def setup_local():
    local_setup()
    path=local.base.ROOT/'plugin.video.venom.tv/browser.py';path.write_text(overlay.browser(path.read_text()))
remote.module.setUpModule=setup_remote
local.setUpModule=setup_local

# Historical mocks predate visibility checks. Production Kodi exposes this API.
for cls in (remote.module.LocalOverlayRegression,local.Tests):
    original=cls.load
    def fixture(self,original=original):
        mod=original(self);mod['xbmc'].getCondVisibility=lambda value:False
        return mod
    cls.load=fixture
original_window=remote.module.RemoteTests.window
def remote_window(self,*args,**kwargs):
    result=original_window(self,*args,**kwargs);result[2].getCondVisibility=lambda value:False
    return result
remote.module.RemoteTests.window=remote_window
original_remote_load=remote.module.load
def remote_load(*args,**kwargs):
    result=original_remote_load(*args,**kwargs)
    result[2].getCondVisibility=lambda value:False
    return result
remote.module.load=remote_load

def remote_idle_live(self):
    b,mod,cat,kodi,gui,job=self.window('live');calls=[]
    def rpc(method,params):
        calls.append((method,params))
        if method.startswith('PVR.'):raise AssertionError('Remote PVR lookup')
        return [] if method=='Player.GetActivePlayers' else {}
    mod['Browser'].open_selected.__globals__['rpc']=rpc
    with patch.object(mod['shared_favorites'],'SharedFavorites',return_value=b.shared), \
            patch.object(b.shared,'request',return_value=[{'name':'Sport','id':'collection-sport'},{'name':'Arabic','id':'category-ar'}]):
        b.load_categories();job['apply'](job['work'](b.request_generation))
    self.assertEqual(b.categories,[('Sport','jf:collection-sport'),('Arabic','jf:category-ar')])
    b.visible_entries=[mod['entry']('Channel',{'mode':'shared','kind':'live','type':'TvChannel','id':'a'*32})]
    b.open_selected();b.open_selected()
    self.assertEqual(calls,[('Player.GetActivePlayers',{}),('Player.Open',{'item':{'file':'plugin://plugin.video.jellyfin/?mode=play&id='+'a'*32}})])
    self.assertIsNone(b.open_pending)

def remote_cancel_before_idle_live(self):
    import queue
    b,mod,cat,kodi,gui,job=self.window('live');applied=[];discarded=[];calls=[]
    class Network:
        def discard_pending(self):discarded.append(True)
        def close(self):pass
        def poll(self):return (7,'stale category',['stale'],None,.2)
        def poll_critical(self):return None
    b.network=Network();b.jobs=queue.Queue();b.busy=False;b.network_busy=True
    b.request_generation=7;b.request_apply=lambda value:applied.extend(value)
    b.retry_categories_if_ready=lambda:False;b.favorite_check=0
    b.visible_entries=[mod['entry']('Channel',{'mode':'shared','kind':'live','type':'TvChannel','id':'a'*32})]
    def rpc(method,params):
        calls.append((method,params));return [] if method=='Player.GetActivePlayers' else {}
    mod['Browser'].open_selected.__globals__['rpc']=rpc
    b.open_selected()
    self.assertEqual(b.request_generation,8+int(b.closed));self.assertEqual(discarded,[True])
    self.assertEqual(calls,[('Player.GetActivePlayers',{}),('Player.Open',{'item':{'file':'plugin://plugin.video.jellyfin/?mode=play&id='+'a'*32}})])
    b.shared=None;b.process();self.assertEqual(applied,[]);self.assertFalse(b.network_busy)

remote.FocusTests.test_remote_live_categories_and_play_never_query_pvr=remote_idle_live
remote.FocusTests.test_remote_live_play_cancels_stale_result_before_immediate_open=remote_cancel_before_idle_live

def preservation(self):
    import ast
    common=HERE.parents[1]/'plugin.video.venom.tv/browser.py'
    path=(remote.module.STAGE/'browser.py' if isinstance(self,remote.FocusTests)
          else local.base.ROOT/'plugin.video.venom.tv/browser.py')
    def classes(path):return {n.name:n for n in ast.parse(path.read_text()).body if isinstance(n,ast.ClassDef)}
    before,after=classes(common),classes(path)
    self.assertEqual(ast.dump(before['LatestWorker']),ast.dump(after['LatestWorker']))
    methods=lambda cls:{n.name:n for n in cls.body if isinstance(n,ast.FunctionDef)}
    left,right=methods(before['Browser']),methods(after['Browser'])
    self.assertIsInstance(right['process'].body[0],ast.If)
    right['process'].body.pop(0)
    # Only the two missing-onInit fields in close changed, not mutation/cancel policy.
    before_close=left['_final_close'];after_close=right['_final_close']
    self.assertEqual(len(before_close.body),len(after_close.body))
    after_close.body[0]=before_close.body[0]
    after_close.body[3]=before_close.body[3]
    for name in ('process','start_network','start_critical_network','cancel_network',
                 'request_cancelled','_final_close','apply_favorite_refresh',
                 'cancel_live_handoff','begin_channel_playback','poll_live_handoff','render'):
        self.assertEqual(ast.dump(left[name]),ast.dump(right[name]),name)
    if not isinstance(self,remote.FocusTests):
        self.assertEqual(ast.dump(left['open_selected']),ast.dump(right['open_selected']))
local.Tests.test_worker_cancellation_and_local_handoff_are_preserved=preservation
remote.FocusTests.test_remote_preserves_common_worker_cancellation_and_mutation_core=preservation

class DepartureTests(unittest.TestCase):
    def test_close_before_oninit_is_safe_and_idempotent(self):
        for suite in (local.Tests(),remote.module.LocalOverlayRegression()):
            mod=suite.load();browser=mod['Browser']()
            browser.close();browser.close()
            self.assertTrue(browser.closed);self.assertEqual(browser.request_generation,1)
    def test_home_retires_owner_without_consuming_jobs(self):
        for module in (remote.module,local):
            with self.subTest(cohort=module.__name__):
                suite=remote.module.LocalOverlayRegression() if module is remote.module else module.Tests()
                mod=suite.load();browser=mod['Browser']();closed=[]
                def close():closed.append(True);browser.closed=True
                browser.close=close
                with patch.object(mod['xbmc'],'getCondVisibility',create=True,
                                  side_effect=lambda value:value=='Window.IsActive(home)'):
                    browser.process()
                self.assertEqual(closed,[True])

    def test_media_and_modal_paths_do_not_retire_local_owner(self):
        module=local
        suite=module.Tests();mod=suite.load()
        for protected in ('Player.HasMedia','System.HasActiveModalDialog'):
            browser=mod['Browser']();closed=[]
            # This sentinel proves the normal process path remains reachable.
            browser.jobs=type('Jobs',(),{'get_nowait':lambda self:(_ for _ in ()).throw(RuntimeError('normal path'))})()
            browser.close=lambda:closed.append(True)
            with patch.object(mod['xbmc'],'getCondVisibility',create=True,
                              side_effect=lambda value:value in ('Window.IsActive(home)',protected)):
                with self.assertRaisesRegex(RuntimeError,'normal path'):browser.process()
            self.assertEqual(closed,[])

    def test_confirmed_favourite_can_complete_after_home_departure(self):
        import queue,types
        mod=local.Tests().load();browser=mod['Browser']();applied=[]
        browser.closed=False;browser.critical_busy=True;browser.close_requested=False
        browser.jobs=queue.Queue();browser.shared=None;browser.network_busy=False
        browser.request_generation=1;browser.request_apply=None
        browser.critical_apply=lambda value:applied.append(value)
        browser.network=types.SimpleNamespace(discard_pending=lambda:None,close=lambda:None,
            poll=lambda:None,poll_critical=lambda:(1,'favourite mutation','verified',None,.1))
        with patch.object(mod['xbmc'],'getCondVisibility',create=True,
                          side_effect=lambda value:value=='Window.IsActive(home)'):
            browser.process()
        self.assertEqual(applied,['verified']);self.assertTrue(browser.closed)

    def test_remote_handoff_stops_then_polls_before_exact_open(self):
        suite=remote.FocusTests();b,mod,*_=suite.window('live');calls=[];players=[{'type':'video','playerid':1}]
        def rpc(method,params):
            calls.append((method,params));return list(players) if method=='Player.GetActivePlayers' else {}
        mod['Browser'].open_selected.__globals__['rpc']=rpc
        b.network.close=lambda:None
        target={'file':'plugin://plugin.video.jellyfin/?mode=play&id='+'a'*32}
        self.assertTrue(b.begin_remote_channel_playback(target,'a',100))
        self.assertEqual(calls,[('Player.GetActivePlayers',{}),('Player.Stop',{'playerid':1})])
        self.assertFalse(b.poll_live_handoff(101));self.assertFalse(b.closed)
        players.clear();self.assertTrue(b.poll_live_handoff(102));self.assertTrue(b.closed)
        self.assertEqual(calls[-1],('Player.Open',{'item':target}))

    def test_remote_handoff_cancel_timeout_or_new_player_never_opens(self):
        for failure in ('cancel','timeout','replacement'):
            with self.subTest(failure=failure):
                b,mod,*_=remote.FocusTests().window('live');calls=[];players=[{'type':'video','playerid':1}]
                def rpc(method,params):
                    calls.append((method,params));return list(players) if method=='Player.GetActivePlayers' else {}
                mod['Browser'].open_selected.__globals__['rpc']=rpc;b.report_error=lambda e:None
                b.begin_remote_channel_playback({'file':'exact'},'a',100)
                if failure=='cancel':b.cancel_live_handoff('Back')
                if failure=='replacement':players[:]=[{'type':'video','playerid':2}]
                b.poll_live_handoff(200 if failure=='timeout' else 101)
                self.assertFalse(any(name=='Player.Open' for name,_ in calls));self.assertIsNone(b.live_handoff)

    def test_remote_handoff_rejects_ambiguous_players(self):
        b,mod,*_=remote.FocusTests().window('live');calls=[]
        def rpc(method,params):
            calls.append(method);return [{'type':'video','playerid':1},{'type':'video','playerid':2}]
        mod['Browser'].open_selected.__globals__['rpc']=rpc
        with self.assertRaisesRegex(RuntimeError,'Ambiguous'):b.begin_remote_channel_playback({'file':'exact'})
        self.assertEqual(calls,['Player.GetActivePlayers'])

if __name__=='__main__':
    setup_remote();setup_local()
    suite=unittest.TestSuite()
    for cls in (remote.module.LocalOverlayRegression,remote.FocusTests,local.Tests,DepartureTests):
        cls.__module__=__name__
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
    try:result=unittest.TextTestRunner().run(suite)
    finally:
        remote.module.tearDownModule();local.tearDownModule()
    raise SystemExit(not result.wasSuccessful())
