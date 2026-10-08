"""Configuration regression: remote HTTPS must not wait for unused native PVR."""
import json
from pathlib import Path
import unittest


class StartupPolicyTests(unittest.TestCase):
    def test_remote_only_native_skin_setting(self):
        policy = json.loads(Path(__file__).with_name('skin-settings.json').read_text())
        self.assertEqual(policy['schema'], 1)
        self.assertEqual(policy['release'], 'am9-ui-policy-20261008.1')
        self.assertEqual(policy['skin'], 'skin.arctic.fuse.3')
        self.assertEqual(policy['reviewed_skin_version'], '3.3.1')
        self.assertEqual(policy['profiles'], {
            'local': {}, 'remote': {'Startup.DisableWaitForLoad': True}})

    def test_no_firmware_network_account_or_pvr_disable(self):
        policy = json.loads(Path(__file__).with_name('skin-settings.json').read_text())
        self.assertEqual(set(policy), {
            'schema', 'release', 'skin', 'reviewed_skin_version', 'profiles'})
        self.assertIs(policy['profiles']['remote']['Startup.DisableWaitForLoad'], True)


if __name__ == '__main__':
    unittest.main()
