import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock,patch

HERE=Path(__file__).resolve().parent
def load():
    xbmc=MagicMock();gui=MagicMock()
    with patch.dict(sys.modules,{'xbmc':xbmc,'xbmcgui':gui}):
        spec=importlib.util.spec_from_file_location('ux_search',HERE/'search_selection.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod,xbmc,gui

class Tests(unittest.TestCase):
    def test_new_query_waits_for_owned_rows_and_selects_once(self):
        m,_,_=load();s=m.SearchSelection()
        self.assertFalse(s.observe(True,'office',10))
        self.assertFalse(s.observe(True,'office',12,updating=True))
        self.assertTrue(s.observe(True,'office',13))
        self.assertFalse(s.observe(True,'office',14))
        self.assertFalse(s.observe(True,'quiet place',15))
        self.assertTrue(s.observe(True,'quiet place',17))
    def test_manual_choice_timeout_empty_and_leaving_are_not_overridden(self):
        m,_,_=load()
        for kwargs in ({'manual':True},{'now':44},{'active':False}):
            s=m.SearchSelection();s.observe(True,'office',10)
            args={'active':True,'query':'office','now':12};args.update(kwargs)
            self.assertFalse(s.observe(**args));self.assertFalse(s.pending)
        s=m.SearchSelection();self.assertFalse(s.observe(True,' ',1))
    def test_same_query_return_preserves_section_and_new_typing_debounces(self):
        m,_,_=load();s=m.SearchSelection()
        s.observe(True,'a',1);s.observe(True,'ab',1.8)
        self.assertFalse(s.observe(True,'ab',2.1))
        self.assertTrue(s.observe(True,'ab',3))
        s.observe(False,'',4)
        self.assertFalse(s.observe(True,'ab',5))
    def test_runtime_queues_hidden_selection_without_focus_or_native_mutation(self):
        m,xbmc,gui=load();s=m.SearchSelection()
        xbmc.getSkinDir.return_value='skin.arctic.fuse.3'
        values={'Skin.String(HomeSwitcher.Search.Mode)':'Combined',
                'Container(3003).ListItem.Property(mode)':'search',
                'Control.GetLabel(3000).index(1)':'office','Container(601).NumItems':'3',
                'Container(502).NumItems':'1','Container(503).NumItems':'0',
                'Container(601).CurrentItem':'2'}
        xbmc.getInfoLabel.side_effect=lambda key:values[key]
        xbmc.getCondVisibility.side_effect=lambda key:key in ('Window.IsActive(1105)','Control.HasFocus(3000)')
        s.poll(10);s.poll(12);s.poll(13)
        gui.Window.assert_not_called()
        self.assertEqual([c.args[0] for c in xbmc.executebuiltin.call_args_list],
                         ['Control.Move(601,-1)'])
        xbmc.executeJSONRPC.assert_not_called()
    def test_nonsearch_modes_and_keyboard_are_untouched(self):
        m,xbmc,gui=load();s=m.SearchSelection()
        xbmc.getSkinDir.return_value='skin.arctic.fuse.3'
        xbmc.getInfoLabel.return_value='Wall';xbmc.getCondVisibility.return_value=True
        s.poll(1);gui.Window.assert_not_called()
    def test_result_browsing_is_not_interrupted(self):
        m,xbmc,gui=load();s=m.SearchSelection()
        xbmc.getSkinDir.return_value='skin.arctic.fuse.3'
        xbmc.getInfoLabel.side_effect=lambda key:{'Skin.String(HomeSwitcher.Search.Mode)':'Combined',
                'Container(3003).ListItem.Property(mode)':'search',
                'Control.GetLabel(3000).index(1)':'office','Container(601).NumItems':'2',
                'Container(502).NumItems':'1','Container(503).NumItems':'0'}[key]
        xbmc.getCondVisibility.side_effect=lambda key:key=='Window.IsActive(1105)'
        s.poll(1);s.poll(3);xbmc.executebuiltin.assert_not_called();gui.Window.assert_not_called()
    def test_late_owned_rows_do_not_spend_reset_on_provider_only_results(self):
        m,xbmc,_=load();s=m.SearchSelection()
        xbmc.getSkinDir.return_value='skin.arctic.fuse.3'
        values={'Skin.String(HomeSwitcher.Search.Mode)':'Combined',
                'Container(3003).ListItem.Property(mode)':'search',
                'Control.GetLabel(3000).index(1)':'quiet place','Container(601).NumItems':'1',
                'Container(502).NumItems':'0','Container(503).NumItems':'0',
                'Container(601).CurrentItem':'2'}
        xbmc.getInfoLabel.side_effect=lambda key:values[key]
        xbmc.getCondVisibility.side_effect=lambda key:key in ('Window.IsActive(1105)','Control.HasFocus(3000)')
        s.poll(1);s.poll(13);xbmc.executebuiltin.assert_not_called()
        values['Container(601).NumItems']='2';values['Container(502).NumItems']='1';s.poll(16)
        self.assertEqual(xbmc.executebuiltin.call_count,1)
        s.poll(17);self.assertEqual(xbmc.executebuiltin.call_count,1)
if __name__=='__main__':unittest.main()
