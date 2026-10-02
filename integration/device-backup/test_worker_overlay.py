import ast
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('worker_overlay', Path(__file__).with_name('worker_overlay.py'))
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)


class Tests(unittest.TestCase):
    def test_migration_only_changes_import_and_selection(self):
        source = (overlay.OLD_IMPORT + '\nidentity = "fixture-device"\n'
                  + overlay.OLD_LOOP + '\n    archive(base)\nretention = 3\n')
        result = overlay.transform(source)
        self.assertEqual(result, source.replace(overlay.OLD_IMPORT, overlay.NEW_IMPORT)
                         .replace(overlay.OLD_LOOP, overlay.NEW_LOOP))
        ast.parse(result)

    def test_drift_duplicate_and_repeated_migration_rejected(self):
        for source in ('unknown', overlay.OLD_IMPORT + '\n' + overlay.OLD_IMPORT,
                       overlay.NEW_IMPORT + '\n' + overlay.NEW_LOOP + '\n    pass\n'):
            with self.assertRaises(ValueError):
                overlay.transform(source)


if __name__ == '__main__':
    unittest.main()
