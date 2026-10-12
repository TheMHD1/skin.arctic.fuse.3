import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('sd_storage', Path(__file__).with_name('storage.py'))
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)
OLD = '11111111-1111-4111-8111-111111111111'
NEW = '22222222-2222-4222-8222-222222222222'


class StorageTests(unittest.TestCase):
    def config(self, tail=''):
        return "# coreelec='quiet'\nvout='1080p60hz'\ncoreelec='quiet toram disk=UUID=" + OLD + " usb-storage.quirks=174c:55aa:u'\n" + tail

    def test_storage_only_and_other_settings_preserved(self):
        result = storage.sd_config(self.config("cec_func_config='7f'\n"), OLD, NEW)
        self.assertIn('disk=UUID=' + NEW, result)
        self.assertNotIn(OLD, result)
        self.assertNotIn('usb-storage.quirks=174c:55aa:u', result)
        self.assertIn("vout='1080p60hz'", result)
        self.assertIn("cec_func_config='7f'", result)
        self.assertIn('quiet toram', result)

    def test_wrong_or_duplicate_selector_rejected(self):
        for text in (self.config().replace(OLD, NEW), self.config() + "coreelec='quiet'\n",
                     self.config().replace(' toram', ' disk=LABEL=STORAGE toram')):
            with self.assertRaises(ValueError):
                storage.sd_config(text, OLD, NEW)

    def test_invalid_or_identical_uuid_rejected(self):
        for old, new in ((OLD, OLD), (OLD, '../../sda'), ('bad', NEW)):
            with self.assertRaises(ValueError):
                storage.sd_config(self.config(), old, new)

    def test_comment_not_active_assignment(self):
        with self.assertRaises(ValueError):
            storage.sd_config(self.config().replace('\ncoreelec=', '\n# coreelec='), OLD, NEW)

    def test_other_usb_quirk_retained(self):
        result = storage.sd_config(self.config().replace('174c:55aa:u', '9999:8888:u'), OLD, NEW)
        self.assertIn('usb-storage.quirks=9999:8888:u', result)

    def test_inventory_preserves_links_without_following(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'settings').write_text('fake-only')
            (root/'runtime-link').symlink_to('/run/does-not-exist')
            (root/'loop').symlink_to(root)
            expected = storage.inventory(root)
            self.assertEqual(expected['runtime-link']['type'], 'link')
            self.assertEqual(len(expected), 4)
            self.assertEqual(storage.verify_inventory(root, expected), 4)

    def test_byte_mode_link_and_extra_file_drift_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root/'settings'
            file.write_text('fake')
            expected = storage.inventory(root)
            file.write_text('changed')
            with self.assertRaises(ValueError):
                storage.verify_inventory(root, expected)
            file.write_text('fake')
            file.chmod(0o600)
            with self.assertRaises(ValueError):
                storage.verify_inventory(root, expected)

    def test_root_symlink_and_special_files_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'root-link').symlink_to(root)
            with self.assertRaises(ValueError):
                storage.inventory(root/'root-link')
            os.mkfifo(root/'fifo')
            with self.assertRaises(ValueError):
                storage.inventory(root)

    def test_missing_extra_and_changed_link_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'link').symlink_to('/run/fake-a')
            expected = storage.inventory(root)
            (root/'link').unlink()
            with self.assertRaises(ValueError):
                storage.verify_inventory(root, expected)
            (root/'link').symlink_to('/run/fake-b')
            with self.assertRaises(ValueError):
                storage.verify_inventory(root, expected)
            (root/'link').unlink()
            (root/'link').symlink_to('/run/fake-a')
            (root/'extra').write_text('fake')
            with self.assertRaises(ValueError):
                storage.verify_inventory(root, expected)

    def test_xattr_drift_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root/'settings'
            file.write_text('fake')
            try:
                os.setxattr(file, 'user.fixture', b'fake-one')
            except OSError:
                self.skipTest('Filesystem does not support user xattrs')
            expected = storage.inventory(root)
            os.setxattr(file, 'user.fixture', b'fake-two')
            with self.assertRaises(ValueError):
                storage.verify_inventory(root, expected)

    def test_exact_mount_and_write_mode(self):
        row = {'source': '/dev/fake2', 'fstype': 'ext4', 'options': 'ro,norecovery'}
        self.assertTrue(storage.require_mount(row, '/dev/fake2', 'ext4', False))
        for source, fs, writable in (('/dev/wrong', 'ext4', False), ('/dev/fake2', 'vfat', False),
                                     ('/dev/fake2', 'ext4', True)):
            with self.assertRaises(ValueError):
                storage.require_mount(row, source, fs, writable)

    def test_config_cli_hash_guard_and_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'config.ini'
            path.write_text(self.config())
            path.chmod(0o640)
            args = ['storage.py', 'config', '--path', str(path), '--old-uuid', OLD,
                    '--new-uuid', NEW, '--expected-sha256', 'wrong']
            before = path.read_bytes()
            with patch('sys.argv', args), self.assertRaises(ValueError):
                storage.main()
            self.assertEqual(path.read_bytes(), before)
            args[-1] = storage.sha(path)
            with patch('sys.argv', args), patch.object(storage.os, 'sync'):
                storage.main()
            self.assertIn('disk=UUID='+NEW, path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertFalse(path.with_name('config.ini.sd-only-pending').exists())

    def test_config_cli_pending_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'config.ini'
            path.write_text(self.config())
            args = ['storage.py', 'config', '--path', str(path), '--old-uuid', OLD,
                    '--new-uuid', NEW, '--expected-sha256', storage.sha(path)]
            pending = path.with_name('config.ini.sd-only-pending')
            pending.write_text('retain pending evidence')
            with patch('sys.argv', args), self.assertRaises(ValueError):
                storage.main()
            self.assertEqual(pending.read_text(), 'retain pending evidence')
            link = Path(tmp)/'link'
            link.symlink_to(path)
            args[3] = str(link)
            with patch('sys.argv', args), self.assertRaises(ValueError):
                storage.main()


if __name__ == '__main__':
    unittest.main()
