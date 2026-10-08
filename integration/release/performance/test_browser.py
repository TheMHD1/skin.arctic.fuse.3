"""Run both full browser contract sets against the performance output."""
import ast
import importlib.util
from pathlib import Path
import shutil
import sys
import threading
import time
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import install
sys.modules['overlay']=install.previous_overlay
spec=importlib.util.spec_from_file_location('performance_ux_tests',HERE.parent/'ux-round/test_browser.py')
ux=importlib.util.module_from_spec(spec);spec.loader.exec_module(ux)

def extend(path,cohort):
    path.write_bytes(install.overlay.transform(install.overlay.BROWSER,path.read_bytes(),cohort))
    shutil.copy2(HERE/'favorite_refresh.py',path.parent/'favorite_refresh.py')
    fav=path.parent/'shared_favorites.py'
    fav.write_bytes(install.overlay.transform(install.overlay.FAVORITES,fav.read_bytes(),cohort))

def preservation(self):
    common=HERE.parents[1]/'plugin.video.venom.tv/browser.py'
    path=(ux.remote.module.STAGE/'browser.py' if isinstance(self,ux.remote.FocusTests)
          else ux.local.base.ROOT/'plugin.video.venom.tv/browser.py')
    classes=lambda p:{n.name:n for n in ast.parse(p.read_text()).body if isinstance(n,ast.ClassDef)}
    left,right=classes(common),classes(path)
    self.assertEqual(ast.dump(left['LatestWorker']),ast.dump(right['LatestWorker']))
    methods=lambda c:{n.name:n for n in c.body if isinstance(n,ast.FunctionDef)}
    before,after=methods(left['Browser']),methods(right['Browser'])
    for name in ('start_network','cancel_network','request_cancelled','apply_favorite_refresh',
                 'cancel_live_handoff','begin_channel_playback','poll_live_handoff','render'):
        self.assertEqual(ast.dump(before[name]),ast.dump(after[name]),name)
    if not isinstance(self,ux.remote.FocusTests):
        self.assertEqual(ast.dump(before['open_selected']),ast.dump(after['open_selected']))
    # These three changes are intentional, narrow and covered by runtime tests.
    self.assertIn('refresh.poll(blocked=',path.read_text())
    self.assertIn('favorite_refresh.invalidate()',path.read_text())
    self.assertIn('favorite_refresh.close()',path.read_text())
ux.local.Tests.test_worker_cancellation_and_local_handoff_are_preserved=preservation
ux.remote.FocusTests.test_remote_preserves_common_worker_cancellation_and_mutation_core=preservation

class OptionalLane(unittest.TestCase):
    def test_slow_optional_read_does_not_occupy_foreground_worker(self):
        for loader in (ux.local.Tests().load,ux.remote.module.LocalOverlayRegression().load):
            with self.subTest(loader=loader.__self__.__class__.__name__):
                mod=loader();Worker=mod['LatestWorker']
                foreground,optional=Worker(),Worker();started=threading.Event();release=threading.Event();navigated=threading.Event()
                def slow():started.set();release.wait(2);return set()
                refresh=mod['FavoriteRefresh'](optional,{},lambda value:None,now=0)
                try:
                    with patch.object(mod['shared_favorites'],'SharedFavorites') as client:
                        client.return_value.keys.side_effect=lambda **kw:slow()
                        refresh.poll(now=2);self.assertTrue(started.wait(1))
                        foreground.submit(1,'categories',lambda:navigated.set())
                        self.assertTrue(navigated.wait(.5),'Navigation queued behind optional read')
                        self.assertFalse(release.is_set())
                finally:refresh.close();foreground.close();release.set()

    def test_foreground_process_polls_optional_without_network_busy_or_generation_change(self):
        import queue,types
        mod=ux.local.Tests().load();browser=mod['Browser']();calls=[]
        browser.jobs=queue.Queue();browser.network_busy=False;browser.critical_busy=False
        browser.closed=False;browser.busy=False;browser.request_apply=None
        browser.network=types.SimpleNamespace(poll=lambda:None,poll_critical=lambda:None)
        browser.request_generation=9;browser.retry_categories_if_ready=lambda:False
        browser.favorite_refresh=types.SimpleNamespace(poll=lambda **kw:calls.append(kw))
        browser.process();self.assertEqual(calls,[{'blocked':False}])
        self.assertFalse(browser.network_busy);self.assertEqual(browser.request_generation,9)

if __name__=='__main__':
    ux.setup_remote();ux.setup_local()
    extend(ux.remote.module.STAGE/'browser.py','remote')
    extend(ux.local.base.ROOT/'plugin.video.venom.tv/browser.py','local')
    suite=unittest.TestSuite()
    for cls in (ux.remote.module.LocalOverlayRegression,ux.remote.FocusTests,ux.local.Tests,ux.DepartureTests,OptionalLane):
        cls.__module__=__name__;suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
    try:result=unittest.TextTestRunner().run(suite)
    finally:ux.remote.module.tearDownModule();ux.local.tearDownModule()
    raise SystemExit(not result.wasSuccessful())
