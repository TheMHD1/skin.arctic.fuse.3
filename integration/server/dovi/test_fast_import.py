import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('fast', Path(__file__).with_name('dovi-import-fast.py'))
fast = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fast)


class FastTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.title = self.root / 'shows' / 'Localized title'
        self.title.mkdir(parents=True)
        self.video = self.title / 'episode.mkv'
        self.video.write_bytes(b'fixture')
        self.config = {'media_root': str(self.root), 'spool': str(self.root / 'queue'), 'claims': str(self.root / 'claims')}
        for key in ('spool', 'claims'):
            Path(self.config[key]).mkdir()
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.worker = fast.FastImports(self.config, self.db, {}, clock=lambda: 1000)
        self.event = {'app': 'sonarr', 'item_id': 7, 'title': str(self.title), 'file': str(self.video), 'created': 1000}

    def put(self, name):
        fast.write_event(Path(self.config['spool']), name, self.event)
        self.worker.claim()

    def test_claim_crash_recovery_and_duplicate_budget(self):
        fast.write_event(Path(self.config['claims']), 'crash.event', self.event)
        self.worker.claim()
        self.worker.defer(['crash.event'], 'failed')
        self.put('duplicate.event')
        self.assertEqual(self.db.execute("SELECT attempts FROM jobs WHERE name='crash.event'").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT state FROM jobs WHERE name='duplicate.event'").fetchone()[0], 'duplicate')
        self.worker.claim()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 2)

    def test_changed_file_creates_new_revision(self):
        self.put('first.event')
        self.video.write_bytes(b'new longer fixture')
        self.put('changed.event')
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM jobs WHERE state='pending'").fetchone()[0], 2)

    def test_wait_does_not_spend_attempts_but_unknown_caps(self):
        self.put('first.event')
        self.worker.defer(['first.event'], 'p7-companion-wait', waiting=True)
        self.assertEqual(self.db.execute('SELECT attempts FROM jobs').fetchone()[0], 0)
        for _ in range(8):
            self.worker.defer(['first.event'], 'unknown-probe')
        self.assertEqual(self.db.execute('SELECT state FROM jobs').fetchone()[0], 'dead')

    def test_owner_root_mismatch_rejected(self):
        self.event['app'] = 'radarr'
        with self.assertRaises(ValueError):
            fast.validate_event(self.event, self.root)

    def test_checkpoint_after_durable_enqueue_and_replay(self):
        from datetime import datetime, timezone
        date = datetime.fromtimestamp(1000, timezone.utc).isoformat()
        class Api:
            def get(_, route, params):
                return {'totalRecords': 1, 'records': [{'id': 42, 'date': date, 'seriesId': 7, 'eventType': 'downloadFolderImported', 'data': {'importedPath': str(self.video)}}]}
        self.worker.apis = {'sonarr': Api()}
        self.assertEqual(self.worker.backfill(), 1)
        self.assertTrue((Path(self.config['spool']) / 'history-sonarr-42.event').exists())
        self.assertEqual(self.worker.backfill(), 0)
        self.worker.claim()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)

    def test_native_history_outage_eventually_stops_http(self):
        class Api:
            calls = 0
            def get(self, *_):
                self.calls += 1
                raise OSError('private error must not be logged')
        api = Api()
        self.worker.apis = {'sonarr': api}
        for _ in range(8):
            self.db.execute('UPDATE history_retry SET next_due=0')
            self.db.commit()
            self.worker.run()
        self.assertEqual(api.calls, 8)
        self.worker.run()
        self.assertEqual(api.calls, 8)
        self.assertEqual(self.db.execute('SELECT dead FROM history_retry').fetchone()[0], 1)

    def test_migration_is_idempotent_and_source_read_only(self):
        source, destination = self.root / 'old.sqlite', self.root / 'new.sqlite'
        with sqlite3.connect(source) as db:
            db.execute('CREATE TABLE notification_outbox(folder TEXT PRIMARY KEY)')
            db.execute('INSERT INTO notification_outbox VALUES(?)', ('/data/media/shows/Office',))
        original = source.read_bytes()
        command = [sys.executable, str(Path(__file__).with_name('migrate-publication.py')), '--source', str(source), '--destination', str(destination)]
        subprocess.run(command, check=True, capture_output=True)
        subprocess.run(command, check=True, capture_output=True)
        self.assertEqual(source.read_bytes(), original)
        with sqlite3.connect(destination) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM notification_outbox').fetchone()[0], 1)

    def test_companion_ready_releases_wait_and_deduplicates_same_companion(self):
        self.put('first.event')
        self.worker.defer(['first.event'], 'p7-companion-wait', waiting=True)
        companion = self.root / 'compatibility' / 'dovi-p8' / 'shows' / self.title.name / 'episode - P8.1 Compatibility.mkv'
        companion.parent.mkdir(parents=True)
        companion.write_bytes(b'validated P8 fixture; no actual probe')
        class Api:
            def get(_, route):
                return {'id': 7, 'path': str(self.title), 'tvdbId': 78107}
        self.worker.apis = {'sonarr': Api()}
        self.worker.companion_ready(self.video)
        self.assertEqual(self.db.execute("SELECT next_due FROM jobs WHERE name='first.event'").fetchone()[0], 0)
        self.worker.claim()
        name = self.db.execute("SELECT name FROM jobs WHERE name LIKE 'companion-%'").fetchone()[0]
        for _ in range(8):
            self.worker.defer([name], 'failed')
        self.worker.companion_ready(self.video)
        self.worker.claim()
        self.assertEqual(self.db.execute('SELECT attempts,state FROM jobs WHERE name=?', (name,)).fetchone(), (8, 'dead'))
        companion.write_bytes(b'genuinely replaced longer companion')
        self.worker.companion_ready(self.video)
        self.worker.claim()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM jobs WHERE name LIKE 'companion-%'").fetchone()[0], 2)

    def test_companion_mapping_current_path_change_is_rejected(self):
        self.put('first.event')
        class Api:
            def get(_, route):
                return {'id': 7, 'path': '/wrong', 'tvdbId': 78107}
        self.worker.apis = {'sonarr': Api()}
        with self.assertRaises(ValueError):
            self.worker.companion_ready(self.video)

    def test_guarded_worker_transform_retains_private_lines(self):
        spec = importlib.util.spec_from_file_location('worker_patch', Path(__file__).with_name('patch-worker-publication.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        text = 'JK="private fixture"\njf_refresh(){\n /Library/Media/Updated\n}\n\n# Persistent cooldown\n         touch /data/media/compatibility/.dovi-reconcile.trigger\n'
        changed = module.transform(text)
        self.assertIn('JK="private fixture"\n', changed)
        self.assertNotIn('/Library/Media/Updated', changed)
        self.assertNotIn('.dovi-reconcile.trigger', changed)
        self.assertIn('companion_publish "$FILE"', changed)
        with self.assertRaises(ValueError):
            module.transform(changed)


if __name__ == '__main__':
    unittest.main()
