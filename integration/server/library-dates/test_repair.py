import unittest
import json
import tempfile
from pathlib import Path
from repair import (index_imports, journaled_repair, plan_digest, refresh_pending_series,
                    repair_entry, validate_plan)


GUID = 'a' * 32
SERIES = 'b' * 32
OTHER_SERIES = 'c' * 32


class FakeApi:
    def __init__(self, current='2020-01-01T00:00:00Z', path='/media/movie.mkv',
                 item_type='Movie', series_id=None):
        self.current = current
        self.path = path
        self.item_type = item_type
        self.series_id = series_id
        self.posts = 0
        self.fail_after_post = False
        self.fail_refresh_after_commit = False
        self.refreshes = []

    def call(self, route, query=None, data=None):
        if route == '/Items':
            return {'Items': [{'Id': GUID, 'Type': self.item_type, 'Path': self.path,
                               'DateCreated': self.current, 'SeriesId': self.series_id}]}
        if route == '/Habibi/LibraryImportDate/RefreshLatestDates':
            document = data['SeriesIds']
            self.refreshes.append(list(document))
            if self.fail_refresh_after_commit:
                raise OSError('connection lost after series refresh commit')
            return {'updatedSeries': len(document)}
        if route == '/Habibi/LibraryImportDate/' + GUID:
            self.posts += 1
            self.current = data['DateCreated']
            if self.fail_after_post:
                raise OSError('connection lost after commit')
            return None
        raise AssertionError(route)


def repair_plan():
    return {'schema': 1, 'counts': {}, 'repairs': [{
        'id': GUID, 'type': 'Movie', 'source': 'radarr',
        'ExpectedPath': '/media/movie.mkv',
        'ExpectedDateCreated': '2020-01-01T00:00:00Z',
        'DateCreated': '2025-01-01T00:00:00Z'}]}


def episode_plan():
    result = repair_plan()
    result['repairs'][0].update(type='Episode', ExpectedPath='/media/show/s01e01.mkv')
    return result


class ImportDateTests(unittest.TestCase):
    def source(self, **changes):
        return dict({'path': '/media/movie.mkv', 'realpath': '/media/movie.mkv',
                     'date': '2025-01-01T00:00:00Z', 'source': 'radarr'}, **changes)

    def item(self, **changes):
        return dict({'Id': 'one', 'Type': 'Movie', 'Path': '/media/movie.mkv',
                     'DateCreated': '2010-01-01T00:00:00Z'}, **changes)

    def test_exact_match_only(self):
        index = index_imports({'files': [self.source()]})
        self.assertIsNotNone(repair_entry(self.item(), index))
        self.assertIsNone(repair_entry(self.item(Path='/elsewhere/movie.mkv'), index))

    def test_idempotent_and_no_streams(self):
        index = index_imports({'files': [self.source()]})
        self.assertIsNone(repair_entry(self.item(DateCreated='2025-01-01T00:00:00Z'), index))
        self.assertIsNone(repair_entry(self.item(Path='https://example.invalid/movie'), index))
        self.assertIsNone(repair_entry(self.item(Path='/media/movie.strm'), index))

    def test_conflicting_evidence_fails_closed(self):
        index = index_imports({'files': [self.source(), self.source(date='2025-01-02T00:00:00Z')]})
        self.assertNotIn('/media/movie.mkv', index)

    def test_journal_resume_after_post_committed_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / 'private-journal.json'
            api = FakeApi()
            api.fail_after_post = True
            with self.assertRaises(OSError):
                journaled_repair(api, repair_plan(), journal)
            self.assertEqual('attempting', json.loads(journal.read_text())['rows'][0]['state'])
            self.assertEqual(1, api.posts)
            api.fail_after_post = False
            self.assertEqual(0, journaled_repair(api, repair_plan(), journal, resume=True))
            self.assertEqual('applied', json.loads(journal.read_text())['rows'][0]['state'])
            self.assertEqual(1, api.posts)
            self.assertEqual(1, journaled_repair(api, repair_plan(), journal, rollback=True))
            self.assertEqual('2020-01-01T00:00:00Z', api.current)
            self.assertEqual(2, api.posts)

    def test_already_desired_skips_and_is_not_rolled_back(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / 'journal.json'
            api = FakeApi(current='2025-01-01T00:00:00Z')
            self.assertEqual(0, journaled_repair(api, repair_plan(), journal))
            self.assertEqual('already_desired', json.loads(journal.read_text())['rows'][0]['state'])
            self.assertEqual(0, journaled_repair(api, repair_plan(), journal, rollback=True))
            self.assertEqual(0, api.posts)

    def test_unknown_date_or_path_fails_without_post(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / 'journal.json'
            api = FakeApi(current='2024-01-01T00:00:00Z')
            with self.assertRaises(RuntimeError):
                journaled_repair(api, repair_plan(), journal)
            self.assertEqual(0, api.posts)
            api.current = '2020-01-01T00:00:00Z'
            api.path = '/media/replaced.mkv'
            with self.assertRaises(RuntimeError):
                journaled_repair(api, repair_plan(), journal, resume=True)
            self.assertEqual(0, api.posts)

    def test_rollback_unfinished_attempt_checks_live_date(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / 'journal.json'
            api = FakeApi()
            api.fail_after_post = True
            with self.assertRaises(OSError):
                journaled_repair(api, repair_plan(), journal)
            api.fail_after_post = False
            self.assertEqual(1, journaled_repair(api, repair_plan(), journal, rollback=True))
            self.assertEqual('rolled_back', json.loads(journal.read_text())['rows'][0]['state'])

    def test_duplicate_ids_are_case_insensitive(self):
        candidate = repair_plan()
        candidate['repairs'].append(dict(candidate['repairs'][0], id=GUID.upper()))
        with self.assertRaises(ValueError):
            validate_plan(candidate)

    def test_episode_apply_and_rollback_refresh_exact_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / 'journal.json'
            api = FakeApi(path='/media/show/s01e01.mkv', item_type='Episode', series_id=SERIES)
            self.assertEqual(1, journaled_repair(api, episode_plan(), journal))
            saved = json.loads(journal.read_text())
            self.assertEqual(SERIES, saved['rows'][0]['series_id'])
            self.assertEqual([], saved['pending_series_refresh'])
            self.assertEqual([[SERIES]], api.refreshes)
            self.assertEqual(1, journaled_repair(api, episode_plan(), journal, rollback=True))
            self.assertEqual([[SERIES], [SERIES]], api.refreshes)
            self.assertEqual('2020-01-01T00:00:00Z', api.current)

    def test_refresh_response_loss_is_retried_without_reposting_item(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / 'journal.json'
            api = FakeApi(path='/media/show/s01e01.mkv', item_type='Episode', series_id=SERIES)
            api.fail_refresh_after_commit = True
            with self.assertRaises(OSError):
                journaled_repair(api, episode_plan(), journal)
            self.assertEqual(1, api.posts)
            self.assertEqual([SERIES], json.loads(journal.read_text())['pending_series_refresh'])
            api.fail_refresh_after_commit = False
            self.assertEqual(0, journaled_repair(api, episode_plan(), journal, resume=True))
            self.assertEqual(1, api.posts)
            self.assertEqual([[SERIES], [SERIES]], api.refreshes)

    def test_item_response_loss_leaves_parent_pending_for_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / 'journal.json'
            api = FakeApi(path='/media/show/s01e01.mkv', item_type='Episode', series_id=SERIES)
            api.fail_after_post = True
            with self.assertRaises(OSError):
                journaled_repair(api, episode_plan(), journal)
            self.assertEqual([], api.refreshes)
            self.assertEqual([SERIES], json.loads(journal.read_text())['pending_series_refresh'])
            api.fail_after_post = False
            self.assertEqual(0, journaled_repair(api, episode_plan(), journal, resume=True))
            self.assertEqual(1, api.posts)
            self.assertEqual([[SERIES]], api.refreshes)

    def test_interrupted_rollback_refreshes_parent_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / 'journal.json'
            api = FakeApi(path='/media/show/s01e01.mkv', item_type='Episode', series_id=SERIES)
            journaled_repair(api, episode_plan(), journal)
            api.fail_after_post = True
            with self.assertRaises(OSError):
                journaled_repair(api, episode_plan(), journal, rollback=True)
            self.assertEqual([SERIES], json.loads(journal.read_text())['pending_series_refresh'])
            api.fail_after_post = False
            self.assertEqual(1, journaled_repair(api, episode_plan(), journal, rollback=True))
            self.assertEqual('rolled_back', json.loads(journal.read_text())['rows'][0]['state'])
            self.assertEqual([[SERIES], [SERIES]], api.refreshes)

    def test_legacy_applied_episode_journal_derives_parent_and_refreshes(self):
        with tempfile.TemporaryDirectory() as directory:
            journal_path = Path(directory) / 'journal.json'
            plan = episode_plan()
            legacy = {'schema': 1, 'plan_sha256': plan_digest(plan), 'plan': plan,
                      'rows': [{'entry': plan['repairs'][0], 'state': 'applied'}]}
            journal_path.write_text(json.dumps(legacy))
            api = FakeApi(current='2025-01-01T00:00:00Z', path='/media/show/s01e01.mkv',
                          item_type='Episode', series_id=SERIES)
            self.assertEqual(0, journaled_repair(api, plan, journal_path, resume=True))
            saved = json.loads(journal_path.read_text())
            self.assertEqual(1, saved['series_refresh_schema'])
            self.assertEqual(SERIES, saved['rows'][0]['series_id'])
            self.assertEqual([[SERIES]], api.refreshes)

    def test_unrelated_pending_parent_is_rejected_without_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            journal_path = Path(directory) / 'journal.json'
            plan = episode_plan()
            document = {'schema': 1, 'plan_sha256': plan_digest(plan), 'plan': plan,
                        'series_refresh_schema': 1, 'pending_series_refresh': [OTHER_SERIES],
                        'rows': [{'entry': plan['repairs'][0], 'state': 'applied',
                                  'series_id': SERIES}]}
            journal_path.write_text(json.dumps(document))
            api = FakeApi(current='2025-01-01T00:00:00Z', path='/media/show/s01e01.mkv',
                          item_type='Episode', series_id=SERIES)
            with self.assertRaises(ValueError):
                journaled_repair(api, plan, journal_path, resume=True)
            self.assertEqual([], api.refreshes)

    def test_series_refresh_batches_are_capped_at_five_hundred(self):
        with tempfile.TemporaryDirectory() as directory:
            journal_path = Path(directory) / 'journal.json'
            series = [format(value, '032x') for value in range(1, 502)]
            document = {'rows': [], 'pending_series_refresh': series}
            journal_path.write_text(json.dumps(document))
            api = FakeApi()
            refresh_pending_series(api, document, journal_path, validated_series=set(series))
            self.assertEqual([500, 1], [len(batch) for batch in api.refreshes])
            self.assertEqual([], json.loads(journal_path.read_text())['pending_series_refresh'])


if __name__ == '__main__':
    unittest.main()
