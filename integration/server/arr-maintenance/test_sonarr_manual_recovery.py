import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('sonarr_recovery', Path(__file__).with_name('sonarr-manual-recovery.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def queue_row(download='download-1', series=7):
    return {'downloadId': download, 'seriesId': series, 'downloadClient': 'SABnzbd',
            'status': 'completed', 'trackedDownloadStatus': 'warning',
            'statusMessages': [{'messages': ['Found matching series via grab history, but release was matched to series by ID. Automatic import is not possible. See the FAQ for details.']}]}


def candidate(path, episode_id=11, series=7, rejection=()):
    return {'path': str(path), 'series': {'id': series},
            'episodes': [{'id': episode_id, 'hasFile': False, 'episodeFileId': 0}],
            'rejections': list(rejection), 'quality': {'quality': {'id': 4}},
            'languages': [{'id': 1}], 'releaseGroup': 'group'}


class RecoveryTests(unittest.TestCase):
    def test_preview_eligible_and_preserves_quality(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'release'
            folder.mkdir()
            path = folder / 'episode.mkv'
            path.write_bytes(b'video')
            def get(route):
                self.assertTrue(route.startswith('manualimport?'))
                return [candidate(path)]
            status, files = mod.preview_package(get, 'download-1', [queue_row()],
                                                {'status': 'Completed', 'category': 'tv', 'storage': str(path)}, root)
            self.assertEqual('eligible', status)
            self.assertEqual([11], files[0]['episodeIds'])
            self.assertEqual({'quality': {'id': 4}}, files[0]['quality'])
            self.assertNotIn('downloadId', files[0])

    def test_rejections_duplicates_and_wrong_series_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'release'
            folder.mkdir()
            path = folder / 'episode.mkv'
            path.write_bytes(b'video')
            slot = {'status': 'Completed', 'category': 'tv', 'storage': str(path)}
            scenarios = [([candidate(path, rejection=[{'reason': 'Sample'}])], 'preview-rejection'),
                         ([candidate(path, series=8)], 'missing-or-mismatched-episode'),
                         ([candidate(path), candidate(path)], 'duplicate-episode-or-path')]
            for rows, expected in scenarios:
                with self.subTest(expected=expected):
                    queue = [queue_row()] * len(rows) if expected == 'duplicate-episode-or-path' else [queue_row()]
                    state, files = mod.preview_package(lambda _: rows, 'download-1', queue, slot, root)
                    self.assertEqual(expected, state)
                    self.assertEqual([], files)

    def test_missing_target_and_outside_root_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'tv'
            root.mkdir()
            folder = root / 'release'
            folder.mkdir()
            path = folder / 'episode.mkv'
            path.write_bytes(b'video')
            slot = {'status': 'Completed', 'category': 'tv', 'storage': str(path)}
            row = candidate(path)
            row['episodes'][0]['episodeFileId'] = 77
            self.assertEqual('target-already-has-file', mod.preview_package(lambda _: [row],
                'download-1', [queue_row()], slot, root)[0])
            self.assertEqual('unsafe-download-path', mod.preview_package(lambda _: [candidate(path)],
                'download-1', [queue_row()], {'status': 'Completed', 'category': 'tv', 'storage': temp}, root)[0])

    def test_dry_run_never_posts_and_limits_packages(self):
        rows = [queue_row(str(i)) for i in range(12)]
        def sonarr(route, body=None):
            self.assertIsNone(body)
            return {'totalRecords': len(rows), 'records': rows}
        with tempfile.TemporaryDirectory() as temp, patch.object(mod, 'preview_package', return_value=('eligible', [{'episodeIds':[1]}])):
            audit = mod.run(sonarr, lambda: {}, Path(temp) / 'audit.json', max_packages=10)
            self.assertEqual(10, len(audit['packages']))
            self.assertTrue(all(row['state'] == 'eligible' for row in audit['packages']))

    def test_verify_requires_source_target_command_and_import_history(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.mkv'
            target = Path(temp) / 'target.mkv'
            source.write_bytes(b'source')
            target.write_bytes(b'target')
            files = [{'path': str(source), 'seriesId': 7, 'episodeIds': [11]}]
            history = {'records': [{'episodeId': 11, 'eventType': 'downloadFolderImported',
                                    'data': {'droppedPath': str(source)},
                                    'date': '2026-09-23T10:00:01Z'}]}
            def api(route):
                if route == 'command/4': return {'status': 'completed', 'result': 'successful'}
                if route == 'episode/11': return {'seriesId': 7, 'episodeFileId': 22}
                if route == 'episodefile/22': return {'path': str(target)}
                if route.startswith('history?'): return history
                raise AssertionError(route)
            self.assertTrue(mod.verify_import(api, files, 4, '2026-09-23T10:00:00Z'))
            source.unlink()
            self.assertFalse(mod.verify_import(api, files, 4, '2026-09-23T10:00:00Z'))


if __name__ == '__main__':
    unittest.main()
