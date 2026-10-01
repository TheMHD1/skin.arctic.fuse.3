"""Run the existing local+remote contracts against the repaired remote build."""
import importlib.util
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import overlay
spec=importlib.util.spec_from_file_location('remote_ui_contracts',HERE.parents[1]/'test-venom-remote.py')
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
original_setup=module.setUpModule


def setup():
    original_setup()
    path=module.STAGE/'browser.py'
    path.write_text(overlay.browser(path.read_text()))


module.setUpModule=setup

# The new explicit remote close exercises the production worker's close API.
# Extend the old fixture (which previously only needed discard_pending).
original_window=module.RemoteTests.window
def window(self,*args,**kwargs):
    result=original_window(self,*args,**kwargs)
    result[0].network.close=lambda:None
    return result
module.RemoteTests.window=window


class LifecycleTests(module.RemoteTests):
    def test_remote_live_retires_browser_before_player_open(self):
        b,mod,cat,kodi,gui,job=self.window('live')
        b.visible_entries=[mod['entry']('Channel',{'mode':'shared','kind':'live','type':'TvChannel','id':'a'*32})]
        observed=[]
        mod['Browser'].open_selected.__globals__['rpc']=lambda *args:observed.append(b.closed)
        b.open_selected()
        self.assertEqual(observed,[True])
        self.assertTrue(b.window_closed)


module.LifecycleTests=LifecycleTests
# Ensure unittest invokes the shared temporary clean-build fixture for this
# class as well, rather than attributing it to the runner's __main__ module.
LifecycleTests.__module__=module.__name__


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(module))
    raise SystemExit(not result.wasSuccessful())
