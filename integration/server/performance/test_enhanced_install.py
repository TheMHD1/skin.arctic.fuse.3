import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import enhanced_install as e

class Tests(unittest.TestCase):
    def fixture(self,d):
        root=Path(d);target=root/'live.dll';candidate=root/'candidate.dll'
        target.write_bytes(b'before');candidate.write_bytes(b'after')
        configuration={'TagCacheServerMode':False,'PrivateToken':'never-public'}
        def request(path):
            if path=='System/Info/Public':return {'Version':'12.1.0'}
            if path=='Plugins':return [{'Name':'Jellyfin Enhanced','Status':'Active','Version':'12.7.0.0','Id':'own'}]
            return dict(configuration)
        return root,target,candidate,request
    def test_plan_and_apply_preserve_configuration_with_readback(self):
        with tempfile.TemporaryDirectory() as d:
            root,target,candidate,request=self.fixture(d);events=[]
            with patch.object(e,'BEFORE',e.sha(b'before')),patch.object(e,'AFTER',e.sha(b'after')):
                plan=e.deploy(target,candidate,root/'backup',request,Mock(),Mock(),Mock())
                self.assertTrue(plan['restart']);self.assertFalse((root/'backup').exists())
                e.deploy(target,candidate,root/'backup',request,lambda:events.append('stop'),lambda:events.append('start'),lambda:events.append('ready'),True)
                self.assertEqual(events,['stop','start','ready']);self.assertEqual(target.read_bytes(),b'after')
                self.assertFalse(e.deploy(target,candidate,root/'other',request,Mock(),Mock(),Mock(),True)['restart'])
    def test_activation_failure_restores_binary(self):
        with tempfile.TemporaryDirectory() as d:
            root,target,candidate,request=self.fixture(d)
            ready=Mock(side_effect=[RuntimeError('failed activation'),None])
            with patch.object(e,'BEFORE',e.sha(b'before')),patch.object(e,'AFTER',e.sha(b'after')):
                with self.assertRaisesRegex(RuntimeError,'failed activation'):
                    e.deploy(target,candidate,root/'backup',request,Mock(),Mock(),ready,True)
            self.assertEqual(target.read_bytes(),b'before')
    def test_unknown_binary_refused_before_restart(self):
        with tempfile.TemporaryDirectory() as d:
            root,target,candidate,request=self.fixture(d);stop=Mock()
            with self.assertRaises(ValueError):e.deploy(target,candidate,root/'backup',request,stop,Mock(),Mock(),True)
            stop.assert_not_called()

if __name__=='__main__':unittest.main()
