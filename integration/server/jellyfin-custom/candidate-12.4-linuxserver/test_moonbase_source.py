import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('source_verifier', HERE / 'verify-moonbase-source.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class SourceManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name)
        self.root = self.parent / 'source'
        self.root.mkdir()
        (self.root / 'source.cs').write_text('maintained source')
        self.manifest = self.parent / 'source.sha256'
        self.line = hashlib.sha256(b'maintained source').hexdigest() + '  source.cs\n'
        self.manifest.write_text(self.line)

    def test_exact_copy_and_real_snapshot(self):
        destination = self.parent / 'stage'
        destination.mkdir()
        self.assertEqual(verifier.copy_verified(self.root, self.manifest, destination), 1)
        self.assertEqual((destination / 'source.cs').read_text(), 'maintained source')
        self.assertEqual(len(verifier.verify(HERE / 'moonbase-12.4-source',
                                             HERE / 'moonbase-12.4-source.sha256')), 201)

    def test_unlisted_build_inputs_are_rejected(self):
        (self.root / 'Directory.Build.props').write_text('<Project/>')
        with self.assertRaisesRegex(ValueError, 'file set'):
            verifier.verify(self.root, self.manifest)

    def test_missing_and_changed_inputs_are_rejected(self):
        (self.root / 'source.cs').write_text('different')
        with self.assertRaisesRegex(ValueError, 'content'):
            verifier.verify(self.root, self.manifest)
        (self.root / 'source.cs').unlink()
        with self.assertRaisesRegex(ValueError, 'file set'):
            verifier.verify(self.root, self.manifest)

    def test_symlinks_and_special_files_are_rejected(self):
        link = self.root / 'linked.props'
        link.symlink_to(self.root / 'source.cs')
        with self.assertRaisesRegex(ValueError, 'special file'):
            verifier.verify(self.root, self.manifest)
        link.unlink()
        os.mkfifo(self.root / 'blocked.props')
        with self.assertRaisesRegex(ValueError, 'special file'):
            verifier.verify(self.root, self.manifest)

    def test_duplicate_and_unsafe_manifest_paths_are_rejected(self):
        self.manifest.write_text(self.line * 2)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            verifier.verify(self.root, self.manifest)
        for name in ('../outside', '/absolute', './source.cs', 'a//b', 'a/../b', 'a\\b'):
            with self.subTest(name=name):
                self.manifest.write_text('0' * 64 + '  ' + name + '\n')
                with self.assertRaisesRegex(ValueError, 'unsafe'):
                    verifier.verify(self.root, self.manifest)

    def test_copy_refuses_nonempty_destination(self):
        destination = self.parent / 'out'
        destination.mkdir()
        (destination / 'stale.dll').write_text('stale')
        with self.assertRaisesRegex(ValueError, 'empty'):
            verifier.copy_verified(self.root, self.manifest, destination)


if __name__ == '__main__':
    unittest.main()
