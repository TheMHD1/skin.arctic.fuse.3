"""Regression tests for crash-safe reviewed Venom artwork publication."""
from __future__ import annotations

import base64
import contextlib
import importlib.util
import io
import json
import pathlib
import subprocess
import tempfile
import urllib.error
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('venom_reviewed_artwork', HERE / 'venom-reviewed-artwork.py')
artwork = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(artwork)
RUNNER_SPEC = importlib.util.spec_from_file_location('venom_reviewed_artwork_run', HERE / 'venom-reviewed-artwork-run.py')
artwork_run = importlib.util.module_from_spec(RUNNER_SPEC)
assert RUNNER_SPEC.loader is not None
RUNNER_SPEC.loader.exec_module(artwork_run)


def png() -> bytes:
    # Header + IHDR width/height is enough for the worker's conservative check.
    return b'\x89PNG\r\n\x1a\n' + b'\0\0\0\rIHDR' + (64).to_bytes(4, 'big') + (64).to_bytes(4, 'big') + b'\0' * 100


class FakeApi:
    def __init__(self, images=None, crash_after_post=False, read_error=None):
        self.images = dict(images or {})
        self.posts = []
        self.crash_after_post = crash_after_post
        self.read_error = read_error

    def request(self, path, data=None, mime=None):
        item_id = path.split('/')[2]
        if data is not None:
            self.posts.append((item_id, mime))
            self.images[item_id] = base64.b64decode(data)
            if self.crash_after_post:
                raise RuntimeError('accepted POST then process died')
            return b''
        if self.read_error is not None:
            raise urllib.error.HTTPError(path, self.read_error, 'read failed', None, None)
        if item_id not in self.images:
            raise urllib.error.HTTPError(path, 404, 'not found', None, None)
        return self.images[item_id]


class ArtworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.cache = self.root / 'cache'
        self.ledger_path = self.root / 'ledger.json'
        self.pending_path = self.root / 'pending.json'
        self.item = {'Id': 'item-a', 'Name': 'Example TV', 'ImageTags': {}}
        self.mapping = {'EN:EXAMPLE TV': {'channel': 'Example.example', 'url': 'https://logos.example/one.png'}}
        self.kwargs = dict(items=[self.item], mapping=self.mapping, scopes={'item-a': 'EN'}, ids={'item-a': 'gateway-a'},
                           cache=self.cache, ledger_path=self.ledger_path, pending_path=self.pending_path,
                           download=lambda _url: png(), apply=True, missing_only=False, limit=1)

    def tearDown(self):
        self.temp.cleanup()

    def test_accepted_post_interruption_reconciles_without_repeat_post(self):
        first = FakeApi(crash_after_post=True)
        pending, ledger = {}, {}
        result = artwork.process_items(ledger=ledger, pending=pending, request=first.request, **self.kwargs)
        self.assertEqual(len(first.posts), 1)
        self.assertTrue(result['errors'])
        self.assertIn('item-a', json.loads(self.pending_path.read_text()))
        # This is the next process: it finds the pending intent before ordinary
        # Primary preservation and proves the unresized native bytes match.
        second = FakeApi(images=first.images)
        saved_pending = json.loads(self.pending_path.read_text())
        result = artwork.process_items(ledger={}, pending=saved_pending, request=second.request, **self.kwargs)
        self.assertEqual(second.posts, [])
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['repaired'], 1)
        self.assertIn('item-a', json.loads(self.ledger_path.read_text()))
        self.assertEqual(json.loads(self.pending_path.read_text()), {})

    def test_mismatched_pending_primary_is_never_claimed_or_replaced(self):
        data = png()
        intent = artwork.build_intent(self.item, self.mapping['EN:EXAMPLE TV'], 'gateway-a', data, 'image/png')
        artwork.atomic_bytes(artwork._cache_path(self.cache, intent['url']), data)
        artwork.atomic_json(self.pending_path, {'item-a': intent})
        manual = b'manual-primary-not-owned'
        api = FakeApi(images={'item-a': manual})
        result = artwork.process_items(ledger={}, pending={'item-a': intent}, request=api.request, **self.kwargs)
        self.assertEqual(api.posts, [])
        self.assertEqual(api.images['item-a'], manual)
        self.assertEqual(result['errors'][0]['error'], 'pending-primary-mismatch')
        self.assertIn('item-a', json.loads(self.pending_path.read_text()))

    def test_intent_before_post_is_resumed_only_after_authoritative_404(self):
        data = png()
        intent = artwork.build_intent(self.item, self.mapping['EN:EXAMPLE TV'], 'gateway-a', data, 'image/png')
        artwork.atomic_bytes(artwork._cache_path(self.cache, intent['url']), data)
        artwork.atomic_json(self.pending_path, {'item-a': intent})
        api = FakeApi()
        result = artwork.process_items(ledger={}, pending={'item-a': intent}, request=api.request, **self.kwargs)
        self.assertEqual(api.posts, [('item-a', 'image/png')])
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['repaired'], 1)
        self.assertEqual(json.loads(self.pending_path.read_text()), {})

    def test_post_accepted_but_native_readback_still_404_is_not_false_success(self):
        class DelayedPrimary(FakeApi):
            def request(self, path, data=None, mime=None):
                if data is not None:
                    self.posts.append((path.split('/')[2], mime))
                    return b''
                raise urllib.error.HTTPError(path, 404, 'not visible', None, None)

        api = DelayedPrimary()
        result = artwork.process_items(ledger={}, pending={}, request=api.request, **self.kwargs)
        self.assertEqual(api.posts, [('item-a', 'image/png')])
        self.assertEqual(result['repaired'], 0)
        self.assertEqual(result['errors'][0]['error'], 'RuntimeError')
        self.assertIn('item-a', json.loads(self.pending_path.read_text()))

    def test_dry_run_pending_is_diagnostic_only_and_does_not_mutate_state(self):
        data = png()
        intent = artwork.build_intent(self.item, self.mapping['EN:EXAMPLE TV'], 'gateway-a', data, 'image/png')
        artwork.atomic_bytes(artwork._cache_path(self.cache, intent['url']), data)
        artwork.atomic_json(self.pending_path, {'item-a': intent})
        self.ledger_path.write_text(json.dumps({'old': {'station': 'Old'}}))
        before_pending = self.pending_path.read_bytes()
        before_ledger = self.ledger_path.read_bytes()
        api = FakeApi(images={'item-a': data})
        result = artwork.process_items(ledger=json.loads(before_ledger), pending={'item-a': intent}, request=api.request,
                                       apply=False, **{key: value for key, value in self.kwargs.items() if key != 'apply'})
        self.assertEqual(api.posts, [])
        self.assertEqual(result['planned'], 1)
        self.assertEqual(result['errors'], [])
        self.assertEqual(self.pending_path.read_bytes(), before_pending)
        self.assertEqual(self.ledger_path.read_bytes(), before_ledger)

    def test_stale_pending_identity_fails_closed_without_upload(self):
        data = png()
        intent = artwork.build_intent(self.item, self.mapping['EN:EXAMPLE TV'], 'old-gateway', data, 'image/png')
        artwork.atomic_bytes(artwork._cache_path(self.cache, intent['url']), data)
        artwork.atomic_json(self.pending_path, {'item-a': intent})
        api = FakeApi()
        result = artwork.process_items(ledger={}, pending={'item-a': intent}, request=api.request, **self.kwargs)
        self.assertEqual(api.posts, [])
        self.assertEqual(result['errors'][0]['error'], 'pending-intent-mismatch')

    def test_pending_transport_or_server_error_never_reposts(self):
        data = png()
        intent = artwork.build_intent(self.item, self.mapping['EN:EXAMPLE TV'], 'gateway-a', data, 'image/png')
        artwork.atomic_bytes(artwork._cache_path(self.cache, intent['url']), data)
        artwork.atomic_json(self.pending_path, {'item-a': intent})
        api = FakeApi(read_error=503)
        result = artwork.process_items(ledger={}, pending={'item-a': intent}, request=api.request, **self.kwargs)
        self.assertEqual(api.posts, [])
        self.assertEqual(result['errors'][0]['error'], 'pending-check-failed')
        self.assertIn('item-a', json.loads(self.pending_path.read_text()))

    def test_native_primary_200_is_preserved_even_when_image_tags_are_stale(self):
        manual = b'manual-primary' * 20
        api = FakeApi(images={'item-a': manual})
        result = artwork.process_items(ledger={}, pending={}, request=api.request, **self.kwargs)
        self.assertEqual(api.posts, [])
        self.assertEqual(api.images['item-a'], manual)
        self.assertEqual(result['preserved'], 1)
        self.assertEqual(result['errors'], [])

    def test_native_primary_transport_or_5xx_never_authorizes_post(self):
        class TransportApi(FakeApi):
            def request(self, path, data=None, mime=None):
                if data is not None:
                    return super().request(path, data, mime)
                raise urllib.error.URLError('temporary transport failure')

        for label, api in (
            ('transport', TransportApi()),
            ('http-500', FakeApi(read_error=500)),
            ('http-503', FakeApi(read_error=503)),
        ):
            with self.subTest(case=label):
                tagged = {**self.item, 'ImageTags': {'Primary': 'manual-tag'}}
                result = artwork.process_items(
                    ledger={}, pending={}, request=api.request,
                    **{**self.kwargs, 'items': [tagged]},
                )
                self.assertEqual(api.posts, [])
                self.assertEqual(result['repaired'], 0)
                self.assertTrue(result['errors'])

    def test_partial_run_durably_records_success_and_reports_other_item_error(self):
        second = {'Id': 'item-b', 'Name': 'Broken TV', 'ImageTags': {}}
        mapping = {
            **self.mapping,
            'EN:BROKEN TV': {'channel': 'Broken.example', 'url': 'https://logos.example/broken.png'},
        }
        api = FakeApi()

        def download(url):
            if url.endswith('broken.png'):
                raise OSError('reviewed source unavailable')
            return png()

        result = artwork.process_items(
            items=[self.item, second], mapping=mapping,
            scopes={'item-a': 'EN', 'item-b': 'EN'}, ids={'item-a': 'gateway-a', 'item-b': 'gateway-b'},
            cache=self.cache, ledger={}, pending={}, ledger_path=self.ledger_path,
            pending_path=self.pending_path, request=api.request, download=download,
            apply=True, missing_only=False, limit=2,
        )
        self.assertEqual(result['repaired'], 1)
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('item-a', json.loads(self.ledger_path.read_text()))
        self.assertNotIn('item-b', json.loads(self.ledger_path.read_text()))

    def test_unmatched_is_normal_but_error_is_failure_after_report_write(self):
        api = FakeApi()
        result = artwork.process_items(items=[self.item], mapping={}, scopes={'item-a': 'EN'}, ids={'item-a': 'gateway-a'},
                                       cache=self.cache, ledger={}, pending={}, ledger_path=self.ledger_path,
                                       pending_path=self.pending_path, request=api.request, download=lambda _: png(),
                                       apply=True, missing_only=False, limit=1)
        self.assertEqual(result['unmatched'], 1)
        self.assertEqual(result['errors'], [])
        report = {'total': 1, 'apply': True, **result}
        artwork.atomic_json(self.root / 'report.json', report)
        self.assertEqual(json.loads((self.root / 'report.json').read_text())['unmatched'], 1)
        errored = {**report, 'errors': [{'name': 'Example TV', 'error': 'RuntimeError'}]}
        artwork.atomic_json(self.root / 'report.json', errored)
        self.assertTrue(json.loads((self.root / 'report.json').read_text())['errors'])

    def test_origin_mismatch_rejects_before_any_worker_state_write(self):
        state = self.root / 'state'
        state.mkdir()
        marker = state / 'unchanged'
        marker.write_text('sentinel')
        with self.assertRaisesRegex(ValueError, 'origins differ'):
            artwork.bind_readiness_origin('http://jellyfin.example:8096', 'http://jellyfin.example:8097/health')
        self.assertEqual(sorted(path.name for path in state.iterdir()), ['unchanged'])
        self.assertEqual(marker.read_text(), 'sentinel')

    def test_default_and_explicit_ports_bind_only_when_effective_origin_matches(self):
        artwork.bind_readiness_origin('https://JELLYFIN.example/', 'https://jellyfin.example/System/Info/Public')
        with self.assertRaises(ValueError):
            artwork.bind_readiness_origin('https://jellyfin.example:444/', 'https://jellyfin.example/System/Info/Public')

    def test_both_artwork_entry_points_have_the_same_private_readiness_boundary(self):
        for name in ('venom-reviewed-artwork.service', 'venom-new-channel-presentation.service'):
            text = (HERE / name).read_text()
            self.assertIn('EnvironmentFile=/etc/venom-reviewed-artwork.env', text)
            preflight = text.index('ExecStartPre=/usr/bin/python3 /data/config/iptv-venom/venom-jellyfin-readiness.py')
            self.assertIn('--check-admin-origin', text[preflight:text.index('\n', preflight)])
            first_mutation = text.index('ExecStart=')
            wrapper = text.index('venom-reviewed-artwork-run.py')
            self.assertLess(preflight, first_mutation)
            self.assertLess(preflight, wrapper)
            self.assertNotIn('ExecStartPost=', text)

    def test_main_persists_error_report_before_returning_nonzero(self):
        original_root, original_run_path = artwork.ROOT, artwork.runpy.run_path
        original_bind, original_process = artwork.bind_readiness_origin, artwork.process_items
        try:
            artwork.ROOT = self.root
            (self.root / 'venom-reviewed-artwork.json').write_text('{}')
            (self.root / 'curated-native-channels.json').write_text(json.dumps({'groups': []}))
            (self.root / 'live-catalogue-redacted.json').write_text(json.dumps({'categories': [], 'channels': []}))
            (self.root / 'jellyfin-api-key').write_text('private-test-key')
            def helper(path):
                if path == '/root/iptv-jellyfin-admin.py':
                    return {'BASE': 'http://jellyfin.example:8096', 'api': lambda _path: [{'Id': 'user', 'Name': 'habibi'}]}
                return {'language': lambda *_args: None}
            artwork.runpy.run_path = helper
            artwork.bind_readiness_origin = lambda *_args: None
            artwork.process_items = lambda *_args, **_kwargs: {
                'repaired': 0, 'preserved': 0, 'unmatched': 0,
                'missing': [], 'errors': [{'name': 'Example TV', 'error': 'RuntimeError'}],
            }
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(artwork.main(['--apply']), 75)
            report = json.loads((self.root / 'reviewed-artwork-report.json').read_text())
            self.assertEqual(report['errors'][0]['error'], 'RuntimeError')
        finally:
            artwork.ROOT, artwork.runpy.run_path = original_root, original_run_path
            artwork.bind_readiness_origin, artwork.process_items = original_bind, original_process


class ArtworkRunWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.source = self.root / 'source.json'
        self.destination = self.root / 'destination.json'
        self.source.write_text(json.dumps({'item-a': {'station': 'Example'}}))

    def tearDown(self):
        self.temp.cleanup()

    def test_partial_exit_finalizes_ledger_and_preserves_failure_status(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 75 if len(calls) == 1 else 0)

        code = artwork_run.run_artwork(
            limit=1000, missing_only=False, runner=runner,
            source_ledger=self.source, destination_ledger=self.destination,
        )
        self.assertEqual(code, 75)
        self.assertEqual(json.loads(self.destination.read_text()), json.loads(self.source.read_text()))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][0], list(artwork_run.OVERRIDE_COMMAND))
        self.assertEqual(calls[1][1]['timeout'], artwork_run.FINALIZER_TIMEOUT_SECONDS)

    def test_fatal_worker_exit_never_copies_or_runs_finalizer(self):
        self.destination.write_text('sentinel')
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 1)

        code = artwork_run.run_artwork(
            limit=1000, missing_only=False, runner=runner,
            source_ledger=self.source, destination_ledger=self.destination,
        )
        self.assertEqual(code, 1)
        self.assertEqual(self.destination.read_text(), 'sentinel')
        self.assertEqual(len(calls), 1)

    def test_success_finalizes_with_fixed_bounded_commands(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0)

        self.assertEqual(
            artwork_run.run_artwork(
                limit=2000, missing_only=True, runner=runner,
                source_ledger=self.source, destination_ledger=self.destination,
            ),
            0,
        )
        worker = calls[0]
        self.assertEqual(worker[0][:3], ['/usr/bin/python3', str(artwork_run.WORKER), '--apply'])
        self.assertEqual(worker[0][-1], '--missing-only')
        self.assertEqual(worker[1]['timeout'], artwork_run.WORKER_TIMEOUT_SECONDS)
        self.assertEqual(calls[1][0], list(artwork_run.OVERRIDE_COMMAND))


if __name__ == '__main__':
    unittest.main()
