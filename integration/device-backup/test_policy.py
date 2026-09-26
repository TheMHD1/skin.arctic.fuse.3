import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('backup_policy', Path(__file__).with_name('policy.py'))
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class BackupPolicyTests(unittest.TestCase):
    def test_real_addon_packages_are_source(self):
        for name in ('__init__.py', 'six.py', 'backports/__init__.py', 'backports/makefile.py'):
            self.assertFalse(policy.should_skip('.kodi/addons/slyguy.dependencies/resources/modules/urllib3/packages/'+name))
        self.assertFalse(policy.should_skip('.kodi/addons/example/resources/Database/schema.sql'))
        self.assertFalse(policy.should_skip('.kodi/addons/example/backups/restore.py'))

    def test_only_known_caches_and_live_databases_are_excluded(self):
        for name in ('.kodi/addons/packages/addon.zip', '.kodi/userdata/Thumbnails/a/image.jpg',
                     '.kodi/userdata/Database/MyVideos.db', '.kodi/userdata/Database/MyVideos.db-wal',
                     '.kodi/addons/example/__pycache__/code.pyc'):
            self.assertTrue(policy.should_skip(name))
        self.assertFalse(policy.should_skip('.kodi/userdata/addon_data/example/settings.xml'))
        self.assertFalse(policy.should_skip('.config/snapshot.py'))

    def test_unsafe_inputs_fail(self):
        for name in ('', '/', '/storage/.kodi/file', '../outside', '.kodi/../outside'):
            with self.assertRaises(ValueError):
                policy.should_skip(name)


if __name__ == '__main__':
    unittest.main()
