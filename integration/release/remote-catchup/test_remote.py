"""Clean-source remote/local contracts plus strict empty-control focus checks."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import overlay


def load_module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


legacy=load_module('previous_ui_overlay',HERE.parent/'ui-reliability/overlay.py')
module=load_module('remote_catchup_contracts',HERE.parents[1]/'test-venom-remote.py')
original_setup=module.setUpModule


def setup():
    original_setup()
    path=module.STAGE/'browser.py'
    path.write_text(overlay.browser(legacy.browser(path.read_text())))


module.setUpModule=setup
original_window=module.RemoteTests.window


def window(self,*args,**kwargs):
    result=original_window(self,*args,**kwargs)
    result[0].network.close=lambda:None
    return result


module.RemoteTests.window=window


def bookmark_deferred(self):
    # Supersede only the historical assertion that deliberately focused an
    # empty grid. Bookmark identity and selected category still must agree.
    mod=self.load();b=mod['Browser']();loaded=[]
    b.closed=False;b.kind='movie';b.pending_bookmark=('7','Bookmarked')
    b.load_entries=lambda:loaded.append((b.category,b.category_name))
    b.apply_categories([('All','all'),('Drama','7')])
    self.assertEqual(loaded,[('7','Bookmarked')])
    self.assertEqual(b.getControl(910).position,1)
    self.assertEqual(b.getFocusId(),910)
    self.assertTrue(b.focus_grid_when_ready)


module.LocalOverlayRegression.test_bookmark_category_waits_for_category_apply_before_loading_entries=bookmark_deferred


class FocusTests(module.RemoteTests):
    def strict(self, kind='movie'):
        b,mod,cat,kodi,gui,job=self.window(kind)
        b.categories=[]
        def focus(control):
            if control in (910,920) and not b.getControl(control).items:
                raise AssertionError('Attempted focus on an empty container')
            b.focus=control
        b.setFocusId=focus
        return b,gui,job

    def test_empty_categories_leave_usable_button_and_retry_message(self):
        b,gui,job=self.strict('live')
        b.apply_categories([])
        self.assertEqual(b.getFocusId(),901)
        self.assertIn('retry',b.getControl(940).label)
        b.apply_categories([('Sports','jf:fixture')])
        self.assertEqual(b.getFocusId(),910)

    def test_top_section_does_not_focus_unpopulated_category_list(self):
        b,gui,job=self.strict()
        b.load_categories=MagicMock()
        b.onClick(903)
        self.assertEqual(b.getFocusId(),903)
        b.load_categories.assert_called_once_with()

    def test_reinitializing_empty_chooser_does_not_focus_missing_item(self):
        b,gui,job=self.strict()
        b.initialized=True;b.category=None
        b.onInit()
        self.assertEqual(b.getFocusId(),901)

    def test_reinitializing_empty_grid_does_not_focus_missing_item(self):
        b,gui,job=self.strict()
        b.initialized=True;b.entries=[]
        b.categories=[('All','all')];b.shared_keys=set()
        b.onInit()
        self.assertEqual(b.getFocusId(),910)

    def test_refresh_moves_focus_before_reset_then_restores_after_results(self):
        b,gui,job=self.strict()
        b.categories=[('All','all')];b.getControl(910).addItems(['All'])
        b.getControl(920).addItems(['old']);b.setFocusId(920)
        b.load_entries()
        self.assertEqual(b.getFocusId(),910)
        self.assertEqual(b.getControl(920).items,[])
        shared=b.load_entries.__globals__['shared_favorites']
        with patch.object(shared,'SharedFavorites',return_value=b.shared):
            job['apply'](job['work'](b.request_generation))
        self.assertEqual(b.getFocusId(),920)

    def test_search_with_zero_results_keeps_usable_category_focus(self):
        b,gui,job=self.strict()
        b.categories=[('All','all')];b.getControl(910).addItems(['All'])
        b.visible_entries=[]
        gui.Dialog.return_value.input.return_value='no matching titles'
        b.onClick(931)
        self.assertEqual(b.getFocusId(),910)
        job['apply']([])
        self.assertEqual(b.getFocusId(),910)
        self.assertEqual(b.getControl(920).items,[])


FocusTests.__module__=module.__name__
module.FocusTests=FocusTests


if __name__=='__main__':
    result=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(module))
    raise SystemExit(not result.wasSuccessful())
