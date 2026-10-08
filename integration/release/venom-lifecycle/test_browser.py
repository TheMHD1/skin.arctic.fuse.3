"""Full paired browser contracts plus Home teardown/background-video coverage."""
import ast,importlib.util,sys,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module
overlay=load('lifecycle_test_overlay',HERE/'overlay.py')
sys.path.insert(0,str(HERE.parent/'performance'))
perf=load('lifecycle_performance_tests',HERE.parent/'performance/test_browser.py')

def extend(path,cohort):
    perf.extend(path,cohort)
    path.write_bytes(overlay.transform(path.read_bytes(),cohort))

class HomeTests(unittest.TestCase):
    def test_native_close_is_not_called_after_home_already_deactivated_window(self):
        for loader in (perf.ux.local.Tests().load,perf.ux.remote.module.LocalOverlayRegression().load):
            for active_home in (False,True):
                mod=loader();browser=mod['Browser']();browser.closed=False
                browser.cancel_live_handoff=lambda reason:None
                with patch.object(mod['xbmc'],'getCondVisibility',create=True,return_value=active_home), \
                     patch.object(mod['xbmcgui'].WindowXML,'close',create=True) as native:
                    browser._final_close();browser._final_close()
                    self.assertEqual(native.call_count,0 if active_home else 1)
                self.assertTrue(browser.closed)

    def test_home_with_background_video_closes_browser_without_stopping_player(self):
        for loader in (perf.ux.local.Tests().load,perf.ux.remote.module.LocalOverlayRegression().load):
            mod=loader();browser=mod['Browser']();calls=[]
            def close():calls.append('close');browser.closed=True
            browser.close=close
            with patch.object(mod['xbmc'],'getCondVisibility',create=True,
                    side_effect=lambda value:value in ('Window.IsActive(home)','Player.HasMedia')):
                browser.process()
            self.assertEqual(calls,['close'])

    def test_fullscreen_and_modal_keep_the_normal_process_path(self):
        for loader in (perf.ux.local.Tests().load,perf.ux.remote.module.LocalOverlayRegression().load):
            for flags in (set(),{'Player.HasMedia'}, {'Window.IsActive(home)','System.HasActiveModalDialog'}):
                mod=loader();browser=mod['Browser']();calls=[]
                browser.close=lambda:calls.append('close')
                browser.jobs=type('Jobs',(),{'get_nowait':lambda self:(_ for _ in ()).throw(RuntimeError('normal path'))})()
                with patch.object(mod['xbmc'],'getCondVisibility',create=True,side_effect=lambda value:value in flags):
                    with self.assertRaisesRegex(RuntimeError,'normal path'):browser.process()
                self.assertFalse(calls)

    def test_main_only_leaves_the_native_venom_hub_and_never_overrides_later_navigation(self):
        paths=(perf.ux.local.base.ROOT/'plugin.video.venom.tv/browser.py',perf.ux.remote.module.STAGE/'browser.py')
        for path in paths:
            main=ast.parse(path.read_text()).body[-1]
            self.assertIsInstance(main,ast.If)
            for active in ('home','1107','fullscreenvideo','1105','1101'):
                events=[]
                class Home:
                    def getProperty(self,name):return ''
                    def setProperty(self,*args):pass
                    def clearProperty(self,*args):events.append('release-owner')
                class Window:
                    def __init__(self,*args):self.initialized=True;self.closed=False
                    def show(self):pass
                    def process(self):self.closed=True
                    def close(self):events.append('close')
                class Kodi:
                    LOGINFO=1;LOGWARNING=2
                    def log(self,*args):pass
                    def getCondVisibility(self,value):return value=='Window.IsActive('+active+')'
                    def executebuiltin(self,action):events.append(action)
                    class Monitor:
                        def waitForAbort(self,*args):return False
                import types,time,os
                namespace={'__name__':'__main__','__file__':str(path),'Browser':Window,'xbmc':Kodi(),'REMOTE_NATIVE':True,
                    'xbmcgui':types.SimpleNamespace(Window=lambda ident:Home()),
                    'catalogue':types.SimpleNamespace(auth=lambda:('private','private')),'time':time,'os':os}
                exec(compile(ast.Module(body=[main],type_ignores=[]),str(path),'exec'),namespace)
                self.assertEqual(events,['close','release-owner']+(['ActivateWindow(home)'] if active=='1107' else []))
    def test_hub_guard_is_evaluated_before_queueing_and_preserves_native_pvr(self):
        import hashlib,xml.etree.ElementTree as ET
        fixture=('<window><onload condition="'+overlay.HUB_CONDITION+'">'+overlay.HUB_ACTION+
            '</onload><include condition="!Skin.String(HomeSwitcher.1107.Name,Venom TV)" /></window>').encode()
        with patch.object(overlay,'HUB_BEFORE',hashlib.sha256(fixture).hexdigest()):
            result=ET.fromstring(overlay.hub(fixture))
        self.assertEqual(result.find('onload').text,overlay.HUB_ACTION)
        self.assertEqual(result.find('onload').get('condition'),overlay.HUB_CONDITION+
            ' + String.IsEmpty(Window(Home).Property(Venom.Browser.Open))')
        self.assertEqual(result.find('include').attrib,ET.fromstring(fixture).find('include').attrib)
        with self.assertRaisesRegex(ValueError,'hub source'):overlay.hub(b'unknown')

# This intentionally supersedes only the old Home+background-media expectation;
# fullscreen and modal protection are explicitly tested above for BOTH cohorts.
def updated_media_contract(self):
    HomeTests().test_fullscreen_and_modal_keep_the_normal_process_path()
perf.ux.DepartureTests.test_media_and_modal_paths_do_not_retire_local_owner=updated_media_contract

if __name__=='__main__':
    perf.ux.setup_remote();perf.ux.setup_local()
    extend(perf.ux.remote.module.STAGE/'browser.py','remote')
    extend(perf.ux.local.base.ROOT/'plugin.video.venom.tv/browser.py','local')
    suite=unittest.TestSuite()
    for cls in (perf.ux.remote.module.LocalOverlayRegression,perf.ux.remote.FocusTests,
                perf.ux.local.Tests,perf.ux.DepartureTests,perf.OptionalLane,HomeTests):
        cls.__module__=__name__;suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
    try:result=unittest.TextTestRunner().run(suite)
    finally:perf.ux.remote.module.tearDownModule();perf.ux.local.tearDownModule()
    raise SystemExit(not result.wasSuccessful())
