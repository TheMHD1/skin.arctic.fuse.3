import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('launch', Path(__file__).with_name('launch.py'))
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


class LaunchTests(unittest.TestCase):
    def settings(self, version):
        values = dict(ts_connect='true', ts_auto_hostname='false', ts_hostname='test-am9',
                      ts_accept_routes='false', ts_exit_node='false', ts_subnet_routes='false',
                      ts_use_exit_node='false', ts_subnets='', ts_exit_node_host='')
        elements = ['<setting id="'+k+'"'+(' value="'+v+'" />' if version == '1' else '>'+v+'</setting>') for k, v in values.items()]
        return '<settings version="'+version+'">'+''.join(elements)+'</settings>'

    @patch('socket.gethostname', return_value='test-am9')
    def test_current_and_legacy_xml(self, _):
        for version in ('1', '2', '3', '4'):
            self.assertIn('ts_connect=true', launch.settings_values([self.settings(version)]))

    @patch('socket.gethostname', return_value='test-am9')
    def test_routing_policy_changes_rejected(self, _):
        xml = self.settings('4').replace('id="ts_exit_node">false', 'id="ts_exit_node">true')
        with self.assertRaises(ValueError):
            launch.settings_values([xml])

    def test_source_drift_rejected(self):
        with self.assertRaises(RuntimeError):
            launch.reviewed_start(b'unknown upstream', '')

    def test_stopped_and_unsafe_prefs_rejected(self):
        prefs = dict(WantRunning=True, RouteAll=False, CorpDNS=False, RunSSH=False,
                     ShieldsUp=False, AdvertiseRoutes=[], ExitNodeID='', ExitNodeIP='',
                     NetfilterMode=0, AutoUpdate={'Apply': False})
        self.assertTrue(launch.safe_prefs(prefs))
        for key in ('WantRunning', 'RouteAll', 'CorpDNS', 'RunSSH', 'ShieldsUp'):
            self.assertFalse(launch.safe_prefs(dict(prefs, **{key: not prefs[key]})))
        self.assertFalse(launch.safe_prefs(dict(prefs, AutoUpdate={'Apply': True})))


if __name__ == '__main__':
    unittest.main()
