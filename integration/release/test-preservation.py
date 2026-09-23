"""Exercise inventory completeness and archive verification without touching GitHub."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('preservation', HERE / 'verify-preservation.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PreservationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'integration/release').mkdir(parents=True)
        self.source = self.root / 'integration/example.py'
        self.source.write_text('example = 1\n')
        for name, value in (('ROOT', self.root), ('MANIFEST', self.root / 'integration/release/source-manifest.json')):
            mock = patch.object(module, name, value)
            mock.start()
            self.addCleanup(mock.stop)

    def stage(self):
        subprocess.run(['git', 'add', 'integration'], cwd=self.root, check=True)

    def test_refuses_untracked_and_unstaged_sources(self):
        with self.assertRaisesRegex(SystemExit, 'stage sources'):
            module.write()
        self.stage()
        self.source.write_text('example = 2\n')
        with self.assertRaisesRegex(SystemExit, 'stage sources'):
            module.write()

    def test_staged_manifest_and_new_source_completeness(self):
        self.stage()
        module.write()
        self.stage()
        module.verify()
        (self.root / 'integration/new.py').write_text('new = True\n')
        self.stage()
        with self.assertRaisesRegex(SystemExit, 'Unlisted tracked source'):
            module.verify()

    def test_git_free_archive_still_checks_bytes(self):
        self.stage()
        module.write()
        (self.root / '.git').rename(self.root / 'git-metadata-away')
        module.verify()
        self.source.write_text('changed = True\n')
        with self.assertRaisesRegex(SystemExit, 'Changed source'):
            module.verify()


if __name__ == '__main__':
    unittest.main()
