import hashlib
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

MODULE = runpy.run_path(str(Path(__file__).with_name('rsync_receiver_overlay.py')))
transform = MODULE['transform']

class ReceiverTests(unittest.TestCase):
    def source(self):
        return b'''#!/bin/sh
set -eu
rsync -a "${staging_root}/backup-running" "${backup_root}status/backup-running"
rsync -a /storage/.cache/hostname "${backup_root}coreelec-state/hostname"
if [ -f /storage/.cache/regdomain.conf ]; then
  rsync -a /storage/.cache/regdomain.conf "${backup_root}coreelec-state/regdomain.conf"
fi
rsync -a --exclude='/packages/' /storage/.kodi/addons/ "${backup_root}kodi-addons/"
'''

    def apply_fixture(self, source):
        with patch.dict(transform.__globals__, BEFORE=hashlib.sha256(source).hexdigest()):
            return transform(source)

    def test_only_three_destination_tokens_change(self):
        source = self.source()
        result = self.apply_fixture(source)
        expected = source
        for before, after in MODULE['REPLACEMENTS']:
            expected = expected.replace(before.encode(), after.encode())
            self.assertNotIn(before.encode(), result)
        self.assertEqual(result, expected)
        self.assertIn(b"--exclude='/packages/'", result)
        with tempfile.NamedTemporaryFile() as file:
            file.write(result)
            file.flush()
            subprocess.run(['sh', '-n', file.name], check=True)

    def test_unknown_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unreviewed'):
            transform(self.source())

    def test_missing_or_duplicate_anchor_is_rejected(self):
        anchor = MODULE['REPLACEMENTS'][0][0].encode()
        for source in (self.source().replace(anchor, b'other'), self.source() + anchor):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'anchor'):
                self.apply_fixture(source)

    def test_directory_destination_preserves_basename_and_overwrite(self):
        # Exercise actual rsync overwrite semantics, independently of the fake
        # fixture's strings. The production restricted receiver is a separate
        # deployment acceptance, not claimed by this local filesystem test.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            target = root / 'target'
            source.mkdir()
            target.mkdir()
            for name in ('backup-running', 'hostname', 'regdomain.conf'):
                (source / name).write_bytes(b'new-' + name.encode())
                (target / name).write_bytes(b'old')
                subprocess.run(['rsync', '-a', str(source / name), str(target) + '/'], check=True)
                self.assertEqual((target / name).read_bytes(), (source / name).read_bytes())
            self.assertEqual(sorted(p.name for p in target.iterdir()), ['backup-running', 'hostname', 'regdomain.conf'])

if __name__ == '__main__':
    unittest.main()
