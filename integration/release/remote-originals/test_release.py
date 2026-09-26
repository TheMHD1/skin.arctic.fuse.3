import ast
import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('builder', HERE/'build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
PAYLOAD = Path(sys.argv.pop(1)) if len(sys.argv) > 1 else None


class BuilderTests(unittest.TestCase):
    def test_unknown_cohort_refused(self):
        with self.assertRaises(ValueError):
            builder.patch_playutils(b'unknown or locally changed upstream')


@unittest.skipIf(PAYLOAD is None, 'Build a payload for actual playback-method regressions')
class PlaybackTests(unittest.TestCase):
    def setUp(self):
        module = ast.parse((PAYLOAD/'playutils.py').read_text())
        cls = next(item for item in module.body if isinstance(item, ast.ClassDef) and item.name == 'PlayUtils')
        self.native = Mock(return_value=None)
        self.settings = {'playFromStream.bool': True}
        env = {'remote_original_path': self.native, 'LOG': Mock(),
               'settings': lambda key: self.settings[key], 'window': Mock(),
               'api': types.SimpleNamespace(API=lambda *args: types.SimpleNamespace(get_file_path=lambda path: path))}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), 'actual-remote-playutils', 'exec'), env)
        self.player = env['PlayUtils'].__new__(env['PlayUtils'])
        self.player.item = {'Type': 'Movie', 'MediaType': 'Video', 'Path': '/data/media/movies/Film.mkv', 'PlaybackInfo': {}}
        self.player.info = {'ForceTranscode': False, 'ServerAddress': 'https://example.invalid', 'PlaySessionId': 'session',
                            'Subtitles': {4: 'existing-sidecar-map'}}
        self.source = {'Id': 'source', 'Protocol': 'File', 'SupportsDirectPlay': True, 'SupportsDirectStream': True,
                       'Path': self.player.item['Path'], 'Container': 'mkv',
                       'MediaStreams': [{'Type': 'Video', 'Index': 0}, {'Type': 'Audio', 'Index': 1}],
                       'DefaultAudioStreamIndex': 1, 'DefaultSubtitleStreamIndex': 4}
        def route(name):
            return lambda *args: self.player.info.update(Method=name, Path=name)
        self.player.direct_play = route('LegacyDirectPlay')
        self.player.direct_url = route('HTTPS')
        self.player.transcode = route('Transcode')
        self.player.is_file_exists = Mock(return_value=False)

    def test_native_preserves_reporting_and_stream_indexes(self):
        self.native.return_value = 'nfs://100.64.0.1/movies/Film.mkv'
        self.player.get(copy.deepcopy(self.source))
        state = self.player.item['PlaybackInfo']
        self.assertEqual(state['Method'], 'DirectPlay')
        self.assertEqual(state['PlaySessionId'], 'session')
        self.assertEqual(state['MediaSourceId'], 'source')
        self.assertEqual(state['KodiAudioStreamIndexes'], [1])
        self.assertEqual(state['AudioStreamIndex'], 1)
        self.assertEqual(state['SubtitleStreamIndex'], 4)
        self.assertEqual(state['Subtitles'], {4: 'existing-sidecar-map'})

    def test_missing_proof_keeps_http_and_remote_http_variant(self):
        for protocol in ('File', 'Http'):
            self.player.get(dict(self.source, Protocol=protocol))
            self.assertEqual(self.player.info['Method'], 'HTTPS')

    def test_force_transcode_retains_transcode(self):
        self.player.info['ForceTranscode'] = True
        self.player.get(copy.deepcopy(self.source))
        self.native.assert_called_once()
        self.assertTrue(self.native.call_args.args[2])
        self.assertEqual(self.player.info['Method'], 'Transcode')

    def test_http_legacy_optout_preserved(self):
        self.settings['playFromStream.bool'] = False
        self.player.get(dict(self.source, Protocol='Http'))
        self.assertEqual(self.player.info['Method'], 'LegacyDirectPlay')


if __name__ == '__main__':
    unittest.main()
