"""Remote-house overlay contracts and the unchanged local browser regressions."""
import importlib.util
import json
from pathlib import Path
import queue
import runpy
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('base_browser_tests', ROOT/'test-venom-browser.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def setUpModule():
    global WORK, STAGE, remote
    WORK = tempfile.TemporaryDirectory(prefix='venom-remote-overlay-tests-')
    STAGE = Path(WORK.name)/'plugin.video.venom.tv'
    shutil.copytree(ROOT/'plugin.video.venom.tv', STAGE)
    subprocess.run(['git','apply','--check',str(ROOT/'patches/venom-remote-performance.patch')],cwd=STAGE,check=True)
    subprocess.run(['git','apply',str(ROOT/'patches/venom-remote-performance.patch')],cwd=STAGE,check=True)
    shutil.copy2(ROOT/'remote-venom/remote_catalogue.py',STAGE/'remote_catalogue.py')
    spec=importlib.util.spec_from_file_location('remote_catalogue',STAGE/'remote_catalogue.py')
    remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)


def tearDownModule():
    WORK.cleanup()


def load(remote_mode=True):
    cat=types.SimpleNamespace(ROOT='unused',search_text=lambda value:str(value).casefold(),
                             favorite_key=lambda value:str(value),
                             venom_state=types.SimpleNamespace(read=lambda path:{'favorites':{}}),
                             auth=MagicMock(side_effect=AssertionError('private gateway auth')),
                             api=MagicMock(side_effect=AssertionError('private gateway API')),
                             route=MagicMock(side_effect=AssertionError('provider playback')))
    kodi=types.SimpleNamespace(log=lambda *args:None,executebuiltin=MagicMock(),
                               Player=MagicMock(),LOGINFO=1,LOGERROR=3)
    gui=types.SimpleNamespace(WindowXML=base.Window,ListItem=base.Item,Dialog=MagicMock())
    modules={'default':cat,'xbmc':kodi,'xbmcgui':gui,'remote_catalogue':remote}
    with patch.dict(sys.modules,modules):
        result=runpy.run_path(str(STAGE/'browser.py'))
    result['Browser'].onInit.__globals__['REMOTE_NATIVE']=remote_mode
    return result,cat,kodi,gui


class LocalOverlayRegression(base.Tests):
    def load(self):
        return load(False)[0]


class FakeServer:
    user='signed-in-user';base='https://jellyfin.example.test'
    server={'address':base,'UserId':user,'AccessToken':'fixture-only'}
    def __init__(self):self.calls=[];self.views=[{'Name':'Venom Movies','Id':'1'*32},{'Name':'Venom Series','Id':'2'*32}]
    def request(self,path,cancelled=None,**params):
        self.calls.append((path,params,cancelled))
        if path.endswith('/Views'):return {'Items':self.views}
        if path=='Genres':return {'Items':[{'Name':'Venom: Arabic'},{'Name':'Drama'},{'Name':'Venom: '}]}
        kind=params.get('IncludeItemTypes','Movie')
        return {'Items':[{'Id':'a'*32,'Name':'Server matched title','Type':kind,'ImageTags':{'Primary':'x'}}], 'TotalRecordCount':1000}


class RemoteTests(unittest.TestCase):
    def window(self,kind='movie'):
        mod,cat,kodi,gui=load();b=mod['Browser']()
        b.kind=kind;b.category='all';b.category_name='All';b.scope=None;b.recent=False;b.query=''
        b.native_offset=0;b.page=0;b.closed=False;b.stack=[];b.open_selection=None;b.open_pending=None
        b.request_generation=1;b.shared=FakeServer();b.pvr_playback_cache={};b.pending_bookmark=None
        b.enqueue=lambda call:call()
        b.network=types.SimpleNamespace(discard_pending=lambda:None)
        scheduled={}
        def start(name,work,apply):
            scheduled.update(name=name,work=work,apply=apply);return 1
        b.start_network=start
        return b,mod,cat,kodi,gui,scheduled

    def test_scoped_remote_categories_and_pages_propagate_cancellation(self):
        server=FakeServer();catalogue=remote.RemoteCatalogue(server);cancel=lambda:False
        self.assertEqual(catalogue.categories('movie',cancel),[('All titles','all'),('Arabic','Venom: Arabic')])
        rows=catalogue.page('series','Venom: Arabic',160,'arabic',True,cancel)
        self.assertEqual([row['params']['mode'] for row in rows],['nativepage','shared','nativepage'])
        self.assertEqual(rows[-1]['params']['offset'],320)
        self.assertTrue(all(callback is cancel for _,_,callback in server.calls))
        path,params,_=server.calls[-1]
        self.assertEqual(path,'Users/signed-in-user/Items')
        self.assertEqual((params['ParentId'],params['IncludeItemTypes'],params['Limit']),('2'*32,'Series',160))
        self.assertEqual((params['Genres'],params['SearchTerm']),('Venom: Arabic','arabic'))
        self.assertTrue(rows[1]['art'].startswith(server.base+'/Items/'))
        self.assertNotIn('AccessToken',rows[1]['art'])

    def test_missing_duplicate_views_and_bad_inputs_fail_closed(self):
        for views in ([],[{'Name':'Venom Movies','Id':'1'*32}]*2):
            server=FakeServer();server.views=views
            with self.assertRaises(RuntimeError):remote.RemoteCatalogue(server).parent('movie')
        for args in [('live','all',0),('movie','bad',0),('movie','all',-1),('movie','all',1)]:
            server=FakeServer()
            with self.assertRaises(ValueError):remote.RemoteCatalogue(server).page(*args)
            self.assertFalse(server.calls)

    def test_cancel_between_calls_stops_next_request(self):
        server=FakeServer()
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            remote.RemoteCatalogue(server).page('movie','all',cancelled=lambda:bool(server.calls))
        self.assertEqual(len(server.calls),1)

    def test_oversized_or_wrong_type_page_and_empty_stale_total(self):
        server=FakeServer();catalogue=remote.RemoteCatalogue(server);catalogue.parents['movie']='1'*32
        bad=[{'Items':[{'Id':'a'*32,'Type':'Movie','Name':'X'}]*161,'TotalRecordCount':161},
             {'Items':[{'Id':'a'*32,'Type':'Episode','Name':'X'}],'TotalRecordCount':1},
             {'Items':[{'Id':'../bad','Type':'Movie','Name':'X'}],'TotalRecordCount':1}]
        for value in bad:
            with patch.object(server,'request',return_value=value),self.assertRaises(ValueError):catalogue.page('movie','all')
        with patch.object(server,'request',return_value={'Items':[],'TotalRecordCount':999}):
            self.assertEqual(catalogue.page('movie','all'),[])

    def test_remote_movie_categories_and_entries_have_no_provider_calls(self):
        b,mod,cat,kodi,gui,job=self.window()
        globals_=mod['Browser'].load_categories.__globals__
        with patch.object(globals_['shared_favorites'],'SharedFavorites',return_value=b.shared):
            b.load_categories();self.assertEqual(job['name'],'movie remote categories')
            self.assertEqual(b.categories,[])
            job['apply'](job['work'](b.request_generation));self.assertEqual(b.categories[-1],('Arabic','Venom: Arabic'))
            b.category='Venom: Arabic';b.native_offset=160;b.query='arabic'
            rows=b.fetch_entries(b.entry_snapshot(),b.shared,lambda:False)
        self.assertEqual(rows[1]['params']['id'],'a'*32)
        cat.api.assert_not_called();cat.auth.assert_not_called()

    def test_remote_live_categories_and_play_never_query_pvr(self):
        b,mod,cat,kodi,gui,job=self.window('live');calls=[]
        globals_=mod['Browser'].open_selected.__globals__
        def rpc(method,params):
            calls.append((method,params))
            if method.startswith('PVR.'):raise AssertionError('Remote PVR lookup')
            return {}
        globals_['rpc']=rpc
        with patch.object(globals_['shared_favorites'],'SharedFavorites',return_value=b.shared), \
                patch.object(b.shared,'request',return_value=[{'name':'Sport','id':'collection-sport'},{'name':'Arabic','id':'category-ar'}]):
            b.load_categories();job['apply'](job['work'](b.request_generation))
        self.assertEqual(b.categories,[('Sport','jf:collection-sport'),('Arabic','jf:category-ar')])
        b.visible_entries=[mod['entry']('Channel',{'mode':'shared','kind':'live','type':'TvChannel','id':'a'*32})]
        b.open_selected();b.open_selected()
        self.assertEqual(calls,[('Player.Open',{'item':{'file':'plugin://plugin.video.jellyfin/?mode=play&id='+'a'*32}})])
        self.assertIsNone(b.open_pending)

    def test_remote_live_play_cancels_stale_result_before_immediate_open(self):
        b,mod,cat,kodi,gui,job=self.window('live');applied=[];discarded=[];calls=[]
        class Network:
            def discard_pending(self):discarded.append(True)
            def poll(self):return (7,'stale category',['stale'],None,.2)
            def poll_critical(self):return None
        b.network=Network();b.jobs=queue.Queue();b.busy=False;b.network_busy=True
        b.request_generation=7;b.request_apply=lambda value:applied.extend(value)
        b.retry_categories_if_ready=lambda:False;b.favorite_check=0
        b.visible_entries=[mod['entry']('Channel',{'mode':'shared','kind':'live','type':'TvChannel','id':'a'*32})]
        def rpc(method,params):
            calls.append((method,params));return {}
        mod['Browser'].open_selected.__globals__['rpc']=rpc
        b.open_selected()
        self.assertEqual(b.request_generation,8);self.assertEqual(discarded,[True])
        self.assertEqual(calls,[('Player.Open',{'item':{'file':'plugin://plugin.video.jellyfin/?mode=play&id='+'a'*32}})])
        b.shared=None;b.process()
        self.assertEqual(applied,[]);self.assertFalse(b.network_busy)

    def test_remote_cache_query_offset_and_navigation_controls(self):
        b,mod,cat,kodi,gui,job=self.window();snapshot=b.entry_snapshot()
        for changed in ({'query':'different'},{'native_offset':160},{'recent':True},{'category':'Venom: Arabic'},{'kind':'series'}):
            self.assertNotEqual(b.source_key(snapshot),b.source_key({**snapshot,**changed}))
        b.query='server synonym';snapshot=b.entry_snapshot()
        rows=remote.RemoteCatalogue(b.shared).page('movie','all',160)
        b.apply_entries(snapshot,rows)
        self.assertEqual(len(b.entries),3)  # Do not refilter server search matches or hide paging.
        b.getControl(920).selectItem(0);b.load_entries=MagicMock();b.open_selected()
        self.assertEqual(b.native_offset,0)
        b.setFocusId(920);b.favorite_menu();gui.Dialog.assert_not_called()
        b.getControl(920).selectItem(2);b.open_selected()
        self.assertEqual(b.native_offset,320)  # Distinct paging offsets are not double-click duplicates.

    def test_remote_search_sort_and_category_reset_offset(self):
        b,mod,cat,kodi,gui,job=self.window();b.load_entries=MagicMock()
        for control in (931,934,910):
            b.native_offset=320;b.categories=[('All','all')]
            gui.Dialog.return_value.input.return_value='test'
            b.onClick(control);self.assertEqual(b.native_offset,0)

    def test_remote_series_back_restores_offset_query_page_and_selection(self):
        b,mod,cat,kodi,gui,job=self.window('series');b.native_offset=320;b.query='search';b.page=1
        b.visible_entries=[mod['entry']('Series',{'mode':'shared','kind':'series','type':'Series','id':'a'*32})]
        b.load_entries=MagicMock();b.open_selected()
        self.assertEqual(b.scope,{'jf_series':'a'*32});self.assertEqual(b.native_offset,0)
        b.busy=False;b.onAction(types.SimpleNamespace(getId=lambda:92))
        self.assertEqual((b.native_offset,b.query,b.page,b.restore_grid_position),(320,'search',1,0))
        episode=mod['entry']('Episode',{'mode':'shared','kind':'series','type':'Episode','id':'b'*32})
        b.visible_entries=[episode];b.open_selected()
        kodi.Player.return_value.play.assert_called_once_with('plugin://plugin.video.jellyfin/?mode=play&id='+'b'*32)
        cat.route.assert_not_called()

    def test_remote_back_restores_grid_selection_from_cache_and_async_result(self):
        b,mod,cat,kodi,gui,job=self.window('series')
        rows=[mod['entry']('Series '+str(index),{'mode':'shared','kind':'series','type':'Series','id':('%032x'%index)})
              for index in range(1,12)]
        b.restore_grid_position=4
        b.remember_source(b.entry_snapshot(),rows)
        b.load_entries()
        self.assertEqual(b.getControl(920).position,4)
        self.assertIsNone(b.restore_grid_position)

        b.source_cache.clear();b.query='async';b.restore_grid_position=7
        b.load_entries()
        self.assertEqual(job['name'],'series entries')
        self.assertEqual(b.getControl(920).position,0)
        job['apply'](rows)
        self.assertEqual(b.getControl(920).position,7)
        self.assertIsNone(b.restore_grid_position)

    def test_remote_shared_favourite_is_critical_survives_close_and_never_uses_pvr(self):
        b,mod,cat,kodi,gui,job=self.window('favorites');submitted={};rpc_calls=[]
        class Network:
            result=None
            def can_submit_critical(self):return True
            def discard_pending(self):pass
            def submit(self,generation,name,work,critical=False):
                self.generation=generation;self.name=name;self.work=work
                submitted.update(generation=generation,name=name,critical=critical)
                return True
            def poll(self):return None
            def poll_critical(self):
                value=self.result;self.result=None;return value
            def close(self):pass
        network=Network();b.network=network;b.jobs=queue.Queue();b.busy=False
        b.network_busy=False;b.critical_busy=False;b.critical_apply=None;b.close_requested=False
        b.favorite_check=0;b.shared_keys=set();b.setFocusId(920)
        entry=mod['entry']('Remote channel',{'mode':'shared','kind':'live','type':'TvChannel','id':'a'*32})
        b.visible_entries=[entry];gui.Dialog.return_value.select.return_value=0;gui.Window=MagicMock()
        globals_=mod['Browser'].favorite_menu.__globals__
        globals_['rpc']=lambda method,params:(rpc_calls.append(method) or (_ for _ in ()).throw(AssertionError('PVR lookup')))
        client=MagicMock();client.set.return_value=True
        with patch.object(globals_['shared_favorites'],'SharedFavorites',return_value=client):
            b.favorite_menu()
            self.assertEqual(submitted,{'generation':2,'name':'favourite mutation','critical':True})
            self.assertTrue(b.critical_busy)
            b.close();self.assertFalse(b.closed);self.assertTrue(b.close_requested)
            result=network.work()
            network.result=(network.generation,network.name,result,None,.1)
            b.retry_categories_if_ready=lambda:False
            b.process()
        client.set.assert_called_once_with(entry,True)
        self.assertEqual(rpc_calls,[]);self.assertIn('jf:'+'a'*32,b.shared_keys)
        self.assertTrue(b.closed);self.assertTrue(getattr(b,'window_closed',False))

    def test_remote_legacy_pvr_and_provider_entries_fail_closed(self):
        b,mod,cat,kodi,gui,job=self.window('live')
        for params in ({'mode':'channel','kind':'live','id':'1'},{'mode':'seasons','kind':'series','id':'1'},{'mode':'play','kind':'movie','id':'1'}):
            b.open_selection=None;b.visible_entries=[mod['entry']('Legacy',params)]
            with self.assertRaises(RuntimeError):b.open_selected()
            with self.assertRaises(RuntimeError):b.prepare_shared_entry(b.visible_entries[0])
        cat.api.assert_not_called();cat.auth.assert_not_called();cat.route.assert_not_called()

    def test_default_remote_categories_redirect_without_private_auth(self):
        with tempfile.TemporaryDirectory(prefix='venom-remote-default-') as tmp:
            (Path(tmp)/'remote-native.json').write_text('{}')
            modules={name:MagicMock() for name in ('xbmc','xbmcgui','xbmcplugin','xbmcvfs','venom_state')}
            modules['xbmcvfs'].translatePath.return_value=tmp
            modules['xbmc'].getCondVisibility.return_value=False
            modules['venom_state'].read.return_value={'favorites':{}}
            for kind in ('movie','series'):
                modules['xbmc'].executebuiltin.reset_mock()
                with patch.dict(sys.modules,modules),patch.object(sys,'argv',['plugin://venom','1','?mode=categories&kind='+kind]):
                    result=runpy.run_path(str(STAGE/'default.py'),run_name='__main__')
                    with self.assertRaisesRegex(RuntimeError,'account authentication'):result['auth']()
                modules['xbmc'].executebuiltin.assert_called_once_with('RunScript(special://home/addons/plugin.video.venom.tv/browser.py,'+kind+')')
                modules['xbmcplugin'].setResolvedUrl.assert_not_called()

    def test_remote_browser_startup_and_allowed_default_routes_never_read_gateway(self):
        class LaunchWindow(base.Window):
            def __init__(self,*args):super().__init__();self.closed=True
            def show(self):pass
        home=MagicMock();home.getProperty.return_value=''
        cat=types.SimpleNamespace(ROOT='remote-profile',BASE=None,AUTH=None,
                                  search_text=lambda value:str(value).casefold(),
                                  favorite_key=lambda value:str(value),
                                  venom_state=types.SimpleNamespace(read=lambda path:{'favorites':{}}),
                                  auth=MagicMock(side_effect=AssertionError('private gateway auth')),
                                  api=MagicMock(side_effect=AssertionError('private gateway API')),
                                  route=MagicMock(side_effect=AssertionError('provider playback')))
        kodi=types.SimpleNamespace(log=lambda *args:None,executebuiltin=MagicMock(),
                                   getCondVisibility=lambda *args:False,Monitor=MagicMock(),
                                   LOGINFO=1,LOGWARNING=2,LOGERROR=3)
        gui=types.SimpleNamespace(WindowXML=LaunchWindow,ListItem=base.Item,
                                  Window=MagicMock(return_value=home),Dialog=MagicMock())
        modules={'default':cat,'xbmc':kodi,'xbmcgui':gui,'remote_catalogue':remote}
        real_exists=Path.exists
        def remote_exists(path):
            return str(path).endswith('remote-native.json') or real_exists(Path(path))
        with patch.dict(sys.modules,modules),patch('os.path.exists',side_effect=remote_exists):
            runpy.run_path(str(STAGE/'browser.py'),run_name='__main__')
        cat.auth.assert_not_called();cat.api.assert_not_called()

        with tempfile.TemporaryDirectory(prefix='venom-remote-default-routes-') as tmp:
            (Path(tmp)/'remote-native.json').write_text('{}')
            defaults={name:MagicMock() for name in ('xbmc','xbmcgui','xbmcplugin','xbmcvfs','venom_state')}
            defaults['xbmcvfs'].translatePath.return_value=tmp
            defaults['xbmc'].getCondVisibility.return_value=False
            defaults['venom_state'].read.return_value={'favorites':{}}
            for mode in ('root','live','favorites'):
                defaults['xbmcvfs'].translatePath.reset_mock()
                defaults['xbmc'].executebuiltin.reset_mock()
                with patch.dict(sys.modules,defaults),patch.object(sys,'argv',['plugin://venom','1','?mode='+mode]):
                    result=runpy.run_path(str(STAGE/'default.py'),run_name='__main__')
                    with self.assertRaisesRegex(RuntimeError,'must use Jellyfin'):result['api']('get_vod_streams')
                translated=[call.args[0] for call in defaults['xbmcvfs'].translatePath.call_args_list]
                self.assertFalse(any('pvr.iptvsimple' in path for path in translated))


if __name__=='__main__':
    unittest.main()
