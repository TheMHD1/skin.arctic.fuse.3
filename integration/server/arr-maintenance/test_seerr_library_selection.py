import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('selection', Path(__file__).with_name('seerr-library-selection.py'))
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)
A, B, C = 'a' * 32, 'b' * 32, 'c' * 32


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.before = {'apiKey': 'private-fixture', 'hostname': 'unchanged', 'other': {'preserve': True},
                       'libraries': [{'id': A, 'name': 'Movies', 'type': 'movie', 'enabled': False},
                                     {'id': B, 'name': 'Shows', 'type': 'show', 'enabled': False},
                                     {'id': C, 'name': 'Other', 'type': 'show', 'enabled': True}]}
        self.native = [{'ItemId': A, 'CollectionType': 'movies', 'Locations': ['/fixture/movies']},
                       {'ItemId': B, 'CollectionType': 'tvshows', 'Locations': ['/fixture/shows']}]

    def test_changes_only_selected_flags_preserves_other_scopes_and_input(self):
        after = selection.plan(self.before, {A: 'movie', B: 'show'}, self.native)
        self.assertTrue(all(row['enabled'] for row in after['libraries']))
        after['libraries'][0]['enabled'] = after['libraries'][1]['enabled'] = False
        self.assertEqual(after, self.before)
        self.assertFalse(self.before['libraries'][0]['enabled'])

    def test_rejects_unknown_wrong_type_and_nonphysical_library(self):
        for ids, native in (({C: 'show'}, self.native), ({A: 'show'}, self.native),
                            ({A: 'movie'}, [{'ItemId': A, 'CollectionType': 'movies', 'Locations': []}])):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                selection.plan(self.before, ids, native)

    def test_dry_run_calls_only_safe_reads_and_version_drift_blocks(self):
        calls = []
        def api(path):
            calls.append(path)
            return {'version': '3.4.1'} if path == 'status' else self.before
        result = selection.repair(api, self.native, {A: 'movie'})
        self.assertTrue(result['changed'])
        self.assertEqual(calls, ['status', 'settings/jellyfin'])
        with self.assertRaises(ValueError):
            selection.repair(lambda _: {'version': 'future'}, self.native, {A: 'movie'})

    def test_apply_preserves_enabled_union_and_requires_exact_readback(self):
        after = selection.plan(self.before, {A: 'movie'}, self.native)
        calls = []
        def api(path):
            calls.append(path)
            if path == 'status': return {'version': '3.4.1'}
            if path.startswith('settings/jellyfin/library?'): return after['libraries']
            return after if len(calls) > 4 else self.before
        with tempfile.TemporaryDirectory() as root:
            backup = Path(root) / 'backup.json'
            selection.repair(api, self.native, {A: 'movie'}, backup, True, {'private': 'fixture'})
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
            self.assertIn(A, calls[3]); self.assertIn(C, calls[3]); self.assertNotIn(B, calls[3])
            self.assertNotIn('sync=', calls[3])

    def test_concurrent_change_aborts_before_mutating_route(self):
        calls = []
        def api(path):
            calls.append(path)
            if path == 'status': return {'version': '3.4.1'}
            return self.before if len(calls) == 2 else {'libraries': []}
        with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError):
            selection.repair(api, self.native, {A: 'movie'}, Path(root) / 'backup.json', True)
        self.assertTrue(all('library?' not in path for path in calls))


if __name__ == '__main__':
    unittest.main()
