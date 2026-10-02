import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import local_overlay


class Tests(unittest.TestCase):
    def test_preserves_worker_and_only_changes_reviewed_selection(self):
        source = b'''#!/bin/sh
identity=fixture
rsync --exclude='packages/' /storage/.kodi/addons/ "${backup_root}kodi-addons/"
rsync -a /storage/.cache/hostname "${backup_root}coreelec-state/hostname"
# Existing consistent database backup and private destination are unchanged.
'''
        with patch.object(local_overlay, 'BEFORE', hashlib.sha256(source).hexdigest()):
            updated = local_overlay.transform(source)
        self.assertIn(b"--exclude='/packages/'", updated)
        self.assertNotIn(b"--exclude='packages/'", updated)
        self.assertIn(b'if [ -f /storage/.cache/regdomain.conf ]; then', updated)
        self.assertIn(b'identity=fixture', updated)
        subprocess.run(['sh', '-n'], input=updated, check=True)
        with self.assertRaises(ValueError):local_overlay.transform(b'unknown-worker')

    @unittest.skipUnless(shutil.which('rsync'), 'rsync required for real filter semantics')
    def test_rooted_rsync_filter_keeps_bundled_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';target=root/'target'
            for name in ('packages/cache.zip','slyguy.dependencies/urllib3/packages/__init__.py',
                         'slyguy.dependencies/urllib3/packages/backports/__init__.py'):
                path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
            subprocess.run(['rsync','-a',"--exclude=/packages/",str(source)+'/',str(target)+'/'],check=True)
            self.assertFalse((target/'packages/cache.zip').exists())
            self.assertTrue((target/'slyguy.dependencies/urllib3/packages/__init__.py').exists())
            self.assertTrue((target/'slyguy.dependencies/urllib3/packages/backports/__init__.py').exists())


if __name__ == '__main__':unittest.main()
