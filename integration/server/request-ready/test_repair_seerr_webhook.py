import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import importlib.util


SPEC = importlib.util.spec_from_file_location('repair_seerr_webhook', Path(__file__).with_name('repair-seerr-webhook.py'))
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class FakeApi:
    def __init__(self, agent):
        self.agent = agent
        self.posts = 0

    def __call__(self, key, route, document=None):
        assert key == 'private-key'
        if route == '/api/v1/status':
            return {'version': '3.4.1'}
        assert route == mod.ROUTE
        if document is not None:
            self.posts += 1
            self.agent = json.loads(json.dumps(document))
        return json.loads(json.dumps(self.agent))


class RepairTests(unittest.TestCase):
    def test_repair_preserves_every_other_setting_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Path(temp) / 'settings.json'
            backup = Path(temp) / 'backup.json'
            payload = {'notification_type': '{{notification_type}}', '{{request}}': {'id': '{{request_id}}'}}
            raw = {'enabled': True, 'types': 134, 'embedPoster': True,
                   'options': {'webhookUrl': 'http://private/hook', 'customHeaders': [{'key': 'X-Test', 'value': 'secret'}],
                               'jsonPayload': base64.b64encode(json.dumps(payload).encode()).decode()}}
            settings.write_text(json.dumps({'main': {'apiKey': 'private-key'}, 'notifications': {'agents': {'webhook': raw}}}))
            api = FakeApi({**raw, 'options': {**raw['options'], 'jsonPayload': payload}})
            def call(key, route, document=None):
                result = api(key, route, document)
                if document is not None:
                    raw['options']['jsonPayload'] = base64.b64encode(json.dumps(document['options']['jsonPayload']).encode()).decode()
                    settings.write_text(json.dumps({'main': {'apiKey': 'private-key'}, 'notifications': {'agents': {'webhook': raw}}}))
                return result
            with patch.object(mod, 'parser_guard'):
                self.assertEqual('repair-needed', mod.repair(call, settings, backup))
                self.assertEqual('repaired', mod.repair(call, settings, backup, apply=True))
                self.assertEqual('already-correct', mod.repair(call, settings, Path(temp) / 'other.json', apply=True))
            self.assertEqual(1, api.posts)
            self.assertTrue(backup.exists())
            self.assertEqual(0o600, backup.stat().st_mode & 0o777)
            self.assertEqual('http://private/hook', api.agent['options']['webhookUrl'])
            self.assertEqual(134, api.agent['types'])
            self.assertEqual(payload, json.loads(api.agent['options']['jsonPayload']))

    def test_rejects_unknown_parser_or_payload(self):
        with patch.object(mod.subprocess, 'run') as run:
            run.return_value.stdout = 'JSON.parse(payloadString)'
            with self.assertRaises(RuntimeError):
                mod.parser_guard()

    def test_already_correct_fails_closed_if_disk_and_api_disagree(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Path(temp) / 'settings.json'
            payload = json.dumps({'event': '{{event}}'})
            raw = {'options': {'jsonPayload': base64.b64encode(json.dumps('different').encode()).decode()}}
            settings.write_text(json.dumps({'main': {'apiKey': 'private-key'},
                                            'notifications': {'agents': {'webhook': raw}}}))
            api = FakeApi({'options': {'jsonPayload': payload}})
            with patch.object(mod, 'parser_guard'), self.assertRaises(RuntimeError):
                mod.repair(api, settings, Path(temp) / 'backup.json')
            self.assertEqual(0, api.posts)


if __name__ == '__main__':
    unittest.main()
