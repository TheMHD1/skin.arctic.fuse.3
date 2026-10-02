"""Exercise the shared navigation repair with the LOCAL transport contracts."""
import ast
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import local_overlay


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


base = load('shared_local_contracts', HERE.parents[1]/'test-venom-browser.py')
ORIGINAL = base.ROOT


def setUpModule():
    global WORK
    WORK = tempfile.TemporaryDirectory()
    root = Path(WORK.name)
    shutil.copytree(ORIGINAL/'plugin.video.venom.tv', root/'plugin.video.venom.tv')
    (root/'patches').mkdir()
    shutil.copy2(ORIGINAL/'patches/jellyfin-2.2.0-habibi.patch', root/'patches')
    path = root/'plugin.video.venom.tv/browser.py'
    path.write_bytes(local_overlay.transform('addons/plugin.video.venom.tv/browser.py', path.read_bytes()))
    base.ROOT = root


def tearDownModule():
    base.ROOT = ORIGINAL
    WORK.cleanup()


class Tests(base.Tests):
    def test_bookmark_category_waits_for_category_apply_before_loading_entries(self):
        mod = self.load(); browser = mod['Browser'](); loaded = []
        browser.closed = False; browser.kind = 'movie'; browser.pending_bookmark = ('7', 'Bookmarked')
        browser.load_entries = lambda: loaded.append((browser.category, browser.category_name))
        browser.apply_categories([('All', 'all'), ('Drama', '7')])
        self.assertEqual(loaded, [('7', 'Bookmarked')])
        self.assertEqual(browser.getControl(910).position, 1)
        self.assertEqual(browser.getFocusId(), 910)
        self.assertTrue(browser.focus_grid_when_ready)

    def strict(self):
        browser = self.load()['Browser']()
        browser.closed = False; browser.category = None; browser.categories = []
        browser.pending_bookmark = None; browser.entries = []; browser.visible_entries = []
        browser.open_pending = None; browser.page = 0; browser.query = ''; browser.category_name = 'All'
        browser.enqueue = lambda call: call()
        def focus(control):
            if control in (910, 920) and not browser.getControl(control).items:
                raise AssertionError('Focus on an empty container')
            browser.focus = control
        browser.setFocusId = focus
        return browser

    def test_empty_categories_have_retry_message(self):
        browser = self.strict(); browser.apply_categories([])
        self.assertEqual(browser.getFocusId(), 901)
        self.assertIn('retry', browser.getControl(940).label)

    def test_empty_reinitialization_uses_button(self):
        browser = self.strict(); browser.initialized = True
        browser.onInit()
        self.assertEqual(browser.getFocusId(), 901)

    def test_empty_grid_reinitialization_uses_categories(self):
        browser = self.strict(); browser.initialized = True; browser.category = 'all'
        browser.categories = [('All', 'all')]
        browser.onInit()
        self.assertEqual(browser.getFocusId(), 910)

    def test_top_button_does_not_focus_empty_categories(self):
        browser = self.strict(); browser.load_categories = lambda: None
        browser.onClick(903)
        self.assertEqual(browser.getFocusId(), 903)

    def test_refresh_moves_focus_before_grid_reset(self):
        browser = self.strict(); browser.category = 'all'; browser.categories = [('All', 'all')]
        browser.getControl(910).addItems(['All']); browser.getControl(920).addItems(['old'])
        browser.setFocusId(920); browser.source_entries = lambda: []
        browser.load_entries()
        self.assertEqual(browser.getFocusId(), 910)
        self.assertEqual(browser.getControl(920).items, [])

    def test_worker_cancellation_and_local_handoff_are_preserved(self):
        def classes(path):
            return {node.name: node for node in ast.parse(path.read_text()).body if isinstance(node, ast.ClassDef)}
        before = classes(ORIGINAL/'plugin.video.venom.tv/browser.py')
        after = classes(base.ROOT/'plugin.video.venom.tv/browser.py')
        self.assertEqual(ast.dump(before['LatestWorker']), ast.dump(after['LatestWorker']))
        methods = lambda node: {n.name: n for n in node.body if isinstance(n, ast.FunctionDef)}
        left, right = methods(before['Browser']), methods(after['Browser'])
        for name in ('process', 'start_network', 'start_critical_network', 'cancel_network',
                     'request_cancelled', '_final_close', 'apply_favorite_refresh',
                     'cancel_live_handoff', 'begin_channel_playback', 'poll_live_handoff', 'render', 'open_selected'):
            with self.subTest(method=name):
                self.assertEqual(ast.dump(left[name]), ast.dump(right[name]))


if __name__ == '__main__':
    unittest.main()
