"""Native-original policy tests; optionally inspect real patched Kodi methods."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, mock_open, patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_originals", HERE / "jellyfin_native_originals.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
ITEM = dict(Type="Movie", MediaType="Video", Path="/data/media/movies/Film.mkv")
SOURCE = dict(Id="source-id", Protocol="File", SupportsDirectPlay=True,
              SupportsDirectStream=True, Path=ITEM["Path"], Container="mkv",
              MediaStreams=[dict(Type="Video", Index=0), dict(Type="Audio", Index=1)],
              DefaultAudioStreamIndex=1, DefaultSubtitleStreamIndex=3)
MAPPINGS = {"/data/media/movies/": "nfs://192.168.2.167/movies/"}


class Policy(unittest.TestCase):
    def test_native_library_movie_and_episode(self):
        for kind in ("Movie", "Episode"):
            self.assertTrue(native.eligible(dict(ITEM, Type=kind), SOURCE, "1", False))

    def test_ineligible_sources(self):
        for change in (dict(Protocol="Http"), dict(Type="Placeholder"), dict(SupportsDirectPlay=False),
                       dict(RequiresOpening=True), dict(RequiresClosing=True), dict(RequiresLooping=True),
                       dict(IsInfiniteStream=True), dict(Container="mkv, STRM"), dict(Path="/x/Foo.STRM")):
            self.assertFalse(native.eligible(ITEM, dict(SOURCE, **change), "1", False), change)
        for change in (dict(Type="TvChannel"), dict(MediaType="Audio"), dict(SourceType="Channel"),
                       dict(Path="/x/Foo.StRm")):
            self.assertFalse(native.eligible(dict(ITEM, **change), SOURCE, "1", False), change)
        self.assertFalse(native.eligible(ITEM, SOURCE, "0", False))
        self.assertFalse(native.eligible(ITEM, SOURCE, "1", True))

    def test_mapping_boundary_longest_and_unicode(self):
        mappings = dict(MAPPINGS, **{"/data/media/movies/special": "nfs://100.69.149.93/special"})
        self.assertEqual(native.map_native_path("/data/media/movies/special/A # فيلم.mkv", mappings),
                         ("nfs://100.69.149.93/special/A # فيلم.mkv", "100.69.149.93"))
        self.assertEqual(native.map_native_path("/data/media/movies/100% Movie%20Name.mkv", MAPPINGS),
                         ("nfs://192.168.2.167/movies/100% Movie%20Name.mkv", "192.168.2.167"))
        self.assertIsNone(native.map_native_path("/data/media/movies-old/Film.mkv", mappings))
        mappings["/data/media/movies/special"] = "smb://server/special"
        self.assertIsNone(native.map_native_path("/data/media/movies/special/Film.mkv", mappings))

    def test_mapping_rejects_untrusted_or_malformed_inputs(self):
        for path in (None, "relative.mkv", "/data/media/movies/../secret", "/data/media/movies/%2e%2e/x",
                     "/data/media/movies/a|x", "/data/media/movies/Film?question.mkv"):
            self.assertIsNone(native.map_native_path(path, MAPPINGS), path)
        for target in ("smb://server/movies", "nfs://user:pass@192.168.2.167/movies",
                       "nfs://192.168.2.167/movies?x=y", "nfs://192.168.2.167/movies#x",
                       "nfs://192.168.2.167/movies/../secret", "nfs://media.example/movies",
                       "nfs://8.8.8.8/movies", "nfs://127.0.0.1/movies", "nfs://192.168.2.167:22/movies",
                       "nfs://[invalid/movies", None):
            self.assertIsNone(native.map_native_path(ITEM["Path"], {"/data/media/movies": target}), target)
        self.assertIsNone(native.map_native_path(ITEM["Path"], None))

    def test_preflight_fallback_and_state_free_success(self):
        candidate = native.map_native_path(ITEM["Path"], MAPPINGS)
        exists = Mock(return_value=True)
        connection = Mock()
        connection.return_value.__enter__ = Mock()
        connection.return_value.__exit__ = Mock()
        self.assertEqual(native.available_native_path(candidate, exists, connection), candidate[0])
        connection.assert_called_once_with(("192.168.2.167", 2049), timeout=0.5)
        for error in (TimeoutError(), ConnectionRefusedError()):
            exists.reset_mock()
            self.assertIsNone(native.available_native_path(candidate, exists, Mock(side_effect=error)))
            exists.assert_not_called()
        for probe in (Mock(return_value=False), Mock(side_effect=RuntimeError("private path"))):
            self.assertIsNone(native.available_native_path(candidate, probe, connection))


if len(sys.argv) > 1:
    PATCHED = Path(sys.argv.pop(1))

    class Playback(unittest.TestCase):
        def setUp(self):
            source = ast.parse((PATCHED / "jellyfin_kodi/helper/playutils.py").read_text())
            methods = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == "PlayUtils")
            self.settings = {"useDirectPaths": "1", "playFromStream.bool": True}
            self.exists = Mock(return_value=True)
            self.connect = Mock()
            self.connect.return_value.__enter__ = Mock()
            self.connect.return_value.__exit__ = Mock()
            self.mapping = Mock(return_value=native.map_native_path(ITEM["Path"], MAPPINGS))
            api_instance = types.SimpleNamespace(get_native_file_path=self.mapping, get_file_path=lambda p: p)
            env = dict(eligible=native.eligible,
                       available_native_path=lambda c, e: native.available_native_path(c, e, self.connect),
                       api=types.SimpleNamespace(API=lambda *a: api_instance), settings=lambda k: self.settings[k],
                       xbmcvfs=types.SimpleNamespace(exists=self.exists), LOG=Mock(), window=Mock())
            exec(compile(ast.Module(body=[methods], type_ignores=[]), "real-patched-playutils", "exec"), env)
            self.player = env["PlayUtils"].__new__(env["PlayUtils"])
            self.player.item = dict(copy.deepcopy(ITEM), PlaybackInfo={})
            self.player.info = dict(ServerAddress="https://jellyfin.invalid", ForceTranscode=False,
                                    PlaySessionId="session-id", Subtitles={3: "existing-mapping"})
            def route(name):
                def run(*args):
                    self.player.info.update(Method=name, Path=name)
                return run
            self.player.direct_url = route("DirectStream")
            self.player.direct_play = route("OriginalDirectPlay")
            self.player.transcode = route("Transcode")
            self.player.is_file_exists = Mock(return_value=False)

        def test_get_native_preserves_reporting_and_streams(self):
            self.player.get(copy.deepcopy(SOURCE))
            self.assertEqual(self.player.info["Method"], "DirectPlay")
            for key, expected in dict(MediaSourceId="source-id", PlaySessionId="session-id",
                                      KodiAudioStreamIndexes=[1], AudioStreamIndex=1, SubtitleStreamIndex=3,
                                      Subtitles={3: "existing-mapping"}).items():
                self.assertEqual(self.player.item["PlaybackInfo"][key], expected)

        def test_get_ineligible_never_probes_native(self):
            for change in (dict(Protocol="Http"), dict(Container="strm"), dict(RequiresOpening=True),
                           dict(Type="Placeholder"), dict(SupportsDirectPlay=False),
                           dict(RequiresClosing=True, LiveStreamId="live-id"),
                           dict(RequiresLooping=True), dict(IsInfiniteStream=True)):
                self.player.get(dict(copy.deepcopy(SOURCE), **change))
                self.mapping.assert_not_called()
                self.exists.assert_not_called()
                self.connect.assert_not_called()
                expected = "OriginalDirectPlay" if change.get("Protocol") == "Http" else "DirectStream"
                self.assertEqual(self.player.info["Method"], expected)

        def test_get_tcp_failure_never_calls_vfs_and_missing_mapping_never_connects(self):
            self.connect.side_effect = TimeoutError()
            self.player.get(copy.deepcopy(SOURCE))
            self.exists.assert_not_called()
            self.assertEqual(self.player.info["Method"], "DirectStream")
            self.connect.reset_mock()
            self.mapping.return_value = None
            self.player.get(copy.deepcopy(SOURCE))
            self.connect.assert_not_called()
            self.assertEqual(self.player.info["Method"], "DirectStream")

        def test_get_channel_audio_and_strm_item_paths_unchanged(self):
            for change in (dict(Type="TvChannel"), dict(MediaType="Audio"),
                           dict(SourceType="Channel"), dict(Path="/x/source.STRM")):
                self.player.item = dict(copy.deepcopy(ITEM), PlaybackInfo={}, **change)
                self.player.get(copy.deepcopy(SOURCE))
                self.mapping.assert_not_called()
                self.connect.assert_not_called()
                self.assertEqual(self.player.info["Method"], "DirectStream")

        def test_get_missing_native_stays_http_and_forced_stays_transcode(self):
            self.exists.return_value = False
            self.player.get(copy.deepcopy(SOURCE))
            self.assertEqual(self.player.info["Method"], "DirectStream")
            self.player.info["ForceTranscode"] = True
            self.mapping.reset_mock()
            self.player.get(copy.deepcopy(SOURCE))
            self.mapping.assert_not_called()
            self.assertEqual(self.player.info["Method"], "Transcode")

        def test_get_remote_moustafa_mode_unchanged(self):
            self.settings["useDirectPaths"] = "0"
            self.player.get(copy.deepcopy(SOURCE))
            self.mapping.assert_not_called()
            self.assertEqual(self.player.info["Method"], "DirectStream")

    class ApiMapping(unittest.TestCase):
        def test_real_api_missing_malformed_and_valid_configuration(self):
            source = ast.parse((PATCHED / "jellyfin_kodi/helper/api.py").read_text())
            methods = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == "API")
            env = dict(json=json, LOG=Mock(), map_native_path=native.map_native_path,
                       xbmcvfs=types.SimpleNamespace(translatePath=lambda p: "fixture-data.json"))
            exec(compile(ast.Module(body=[methods], type_ignores=[]), "real-patched-api", "exec"), env)
            for config in ("not json", "{}", '{"Servers": []}', '{"Servers": [{"paths": null}]}'):
                with patch("builtins.open", mock_open(read_data=config)):
                    self.assertIsNone(env["API"](ITEM).get_native_file_path(ITEM["Path"]))
            with patch("builtins.open", side_effect=FileNotFoundError()):
                self.assertIsNone(env["API"](ITEM).get_native_file_path(ITEM["Path"]))
            config = json.dumps({"Servers": [{"paths": MAPPINGS}]})
            with patch("builtins.open", mock_open(read_data=config)):
                self.assertEqual(env["API"](ITEM).get_native_file_path(ITEM["Path"]),
                                 native.map_native_path(ITEM["Path"], MAPPINGS))


if __name__ == "__main__":
    unittest.main()
