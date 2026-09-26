"""Regression tests for the conservative remote-native manifest/gate."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import shutil
import unittest
from unittest.mock import Mock

HERE = Path(__file__).resolve().parent
for name in ("manifest", "gate"):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
manifest, gate = sys.modules["manifest"], sys.modules["gate"]
adapter_spec = importlib.util.spec_from_file_location("kodi_adapter", HERE / "kodi_adapter.py")
adapter = importlib.util.module_from_spec(adapter_spec)
adapter_spec.loader.exec_module(adapter)


def stream(index, kind, codec, **kwargs):
    tags = {"language": kwargs.get("language", "eng")}
    if "title" in kwargs:
        tags["title"] = kwargs["title"]
    result = {"index": index, "codec_type": kind, "codec_name": codec, "tags": tags,
              "disposition": {"default": kwargs.get("default", 0), "forced": kwargs.get("forced", 0)}}
    if kind == "audio":
        result.update(channels=kwargs.get("channels", 6), channel_layout=kwargs.get("layout", "5.1"))
    return result


def probe(profile, streams=None, seconds="100.2"):
    return {"format": {"duration": seconds}, "streams": [
        {"codec_type": "video", "side_data_list": [{"dv_profile": profile,
                                                          "dv_bl_signal_compatibility_id": 1 if profile == 8 else 0}]},
        *(streams or [stream(1, "audio", "eac3"), stream(2, "subtitle", "subrip", default=1)]),
    ]}


class Publisher(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.media, self.compat, self.view = self.root / "media", self.root / "compat", self.root / "view"
        self.source = self.media / "movies" / "Film.mkv"
        self.companion = self.compat / "movies" / "Film - P8.1 Compatibility.mkv"
        self.source.parent.mkdir(parents=True); self.companion.parent.mkdir(parents=True); self.view.joinpath("movies").mkdir(parents=True)
        self.source.write_bytes(b"p7"); self.companion.write_bytes(b"p8")
        self.view.joinpath("movies/Film.mkv").hardlink_to(self.companion)

    def runner(self, responses):
        def run(*args, **kwargs):
            return type("Result", (), {"returncode": 0, "stdout": json.dumps(responses.pop(0))})()
        return run

    def test_accepts_exact_pair_and_rejects_mismatch(self):
        logical, entry = manifest.build_entry(self.source, self.media, self.compat, self.view,
                                              self.runner([probe(7), probe(8)]))
        self.assertEqual(logical, "/data/media/movies/Film.mkv")
        self.assertEqual(entry["streams"][0]["channel_layout"], "5.1")
        with self.assertRaises(manifest.Reject):
            manifest.build_entry(self.source, self.media, self.compat, self.view,
                                 self.runner([probe(7), probe(8, [stream(1, "audio", "aac")])]))

    def test_profile_duration_and_view_inode_fail_closed(self):
        for responses in ([probe(8), probe(8)], [probe(7, seconds="100"), probe(8, seconds="102")]):
            with self.assertRaises(manifest.Reject):
                manifest.build_entry(self.source, self.media, self.compat, self.view, self.runner(responses))
        self.view.joinpath("movies/Film.mkv").unlink(); self.view.joinpath("movies/Film.mkv").write_bytes(b"not companion")
        with self.assertRaises(manifest.Reject):
            manifest.build_entry(self.source, self.media, self.compat, self.view, self.runner([probe(7), probe(8)]))

    def test_source_change_and_unsafe_path_are_rejected(self):
        responses = [probe(7), probe(8)]
        calls = 0
        def changing_runner(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.source.write_bytes(b"changed")
            return type("Result", (), {"returncode": 0, "stdout": json.dumps(responses.pop(0))})()
        with self.assertRaises(manifest.Reject):
            manifest.build_entry(self.source, self.media, self.compat, self.view, changing_runner)
        outside = self.media / "other.mkv"; outside.write_bytes(b"x")
        with self.assertRaises(manifest.Reject):
            manifest.relative_source(outside, self.media)

    def test_companion_scan_derives_only_exact_canonical_names(self):
        scanned = manifest.scan_companions(self.media, self.compat)
        self.assertEqual(scanned, [self.source])
        for number in range(manifest.MAX_ENTRIES):
            path = self.compat / "shows" / ("S%04d - P8.1 Compatibility.mkv" % number)
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"x")
        with self.assertRaises(manifest.Reject):
            manifest.scan_companions(self.media, self.compat)


class RuntimeGate(unittest.TestCase):
    def setUp(self):
        self.signature = [
            {"index": 1, "type": "audio", "codec": "eac3", "language": "eng", "title": "",
             "default": True, "forced": False, "channels": 6, "channel_layout": "5.1(side)"},
            {"index": 2, "type": "subtitle", "codec": "subrip", "language": "eng", "title": "",
             "default": False, "forced": False, "channels": None, "channel_layout": None},
        ]
        self.manifest = {"schema": manifest.SCHEMA, "created_at": 100, "expires_at": 200, "entries": {"/data/media/movies/Film.mkv": {
            "original": {"size": 10, "mtime": 4, "mtime_ns": 4_000_000_000, "inode": 8},
            "companion": {"size": 9, "mtime": 5, "mtime_ns": 5_000_000_000, "inode": 9}, "streams": self.signature}}}
        self.source = {"Path": "/data/media/movies/Film.mkv", "Size": 9, "MediaStreams": [
            {"Index": 1, "Type": "Audio", "Codec": "eac3", "Language": "eng",
             "IsDefault": True, "IsForced": False, "Channels": 6, "ChannelLayout": "5.1"},
            {"Index": 2, "Type": "Subtitle", "Codec": "subrip", "Language": "eng",
             "IsDefault": False, "IsForced": False},
        ]}

    def test_exact_entry_only(self):
        self.assertTrue(gate.allows_native(self.manifest, "/data/media/movies/Film.mkv", {"size": 10, "mtime": 4, "inode": 8}, self.source))
        for changed in ({"size": 11, "mtime": 4}, {"size": 10, "mtime": 5}, {"size": 10, "mtime": 4, "inode": 7}):
            self.assertFalse(gate.allows_native(self.manifest, "/data/media/movies/Film.mkv", changed, self.source))
        self.assertFalse(gate.allows_native(self.manifest, "/data/media/movies/Film.mkv/../x", {"size": 10, "mtime": 4}, self.source))

    def test_two_missing_signatures_are_not_equal_proof(self):
        self.manifest['entries']['/data/media/movies/Film.mkv'].pop('streams')
        self.source.pop('MediaStreams')
        self.assertFalse(gate.allows_native(self.manifest, '/data/media/movies/Film.mkv',
                                           {'size': 10, 'mtime': 4}, self.source))

    def test_iso_language_aliases_preserve_semantic_identity(self):
        for old,new in [('chi','zho'),('cze','ces'),('fre','fra'),('ger','deu')]:
            self.signature[0]['language']=old
            self.source['MediaStreams'][0]['Language']=new
            self.assertTrue(gate.allows_native(self.manifest, '/data/media/movies/Film.mkv',
                                               {'size':10,'mtime':4}, self.source))
        self.source['MediaStreams'][0]['Language']='ara'
        self.assertFalse(gate.allows_native(self.manifest, '/data/media/movies/Film.mkv',
                                           {'size':10,'mtime':4}, self.source))

    def test_jellyfin_drift_and_external_subtitle_handling(self):
        changed = dict(self.source, Size=8)
        self.assertFalse(gate.allows_native(self.manifest, "/data/media/movies/Film.mkv", {"size": 10, "mtime": 4}, changed))
        changed = dict(self.source, MediaStreams=[dict(self.source["MediaStreams"][0], Index=2)])
        self.assertFalse(gate.allows_native(self.manifest, "/data/media/movies/Film.mkv", {"size": 10, "mtime": 4}, changed))
        external = dict(self.source, MediaStreams=self.source["MediaStreams"] + [{"Index": 7, "Type": "Subtitle", "Codec": "subrip", "IsExternal": True}])
        self.assertTrue(gate.allows_native(self.manifest, "/data/media/movies/Film.mkv", {"size": 10, "mtime": 4}, external))
        self.assertFalse(gate.allows_native(self.manifest, "/data/media/movies/Film.mkv", {"size": 10, "mtime": 4}, dict(self.source, Path="/other")))

    def test_external_prefix_renumbering_is_allowed_but_semantic_order_is_not(self):
        external = [{"Index": value, "Type": "Subtitle", "Codec": "subrip", "IsExternal": True}
                    for value in range(1, 6)]
        embedded = dict(self.source["MediaStreams"][0], Index=6, ChannelLayout="5.1")
        subtitle = dict(self.source["MediaStreams"][1], Index=7)
        source = dict(self.source, MediaStreams=external + [embedded, subtitle])
        self.assertTrue(gate.allows_native(self.manifest, "/data/media/movies/Film.mkv", {"size": 10, "mtime": 4}, source))
        reordered = dict(source, MediaStreams=external + [subtitle, embedded])
        self.assertFalse(gate.allows_native(self.manifest, "/data/media/movies/Film.mkv", {"size": 10, "mtime": 4}, reordered))
        duplicate = dict(source, MediaStreams=external + [dict(embedded, Index=5)])
        self.assertFalse(gate.allows_native(self.manifest, "/data/media/movies/Film.mkv", {"size": 10, "mtime": 4}, duplicate))

    def test_manifest_limits_expiry_and_malformed(self):
        valid = json.dumps(self.manifest).encode()
        self.assertIsNotNone(gate.load_manifest(lambda n: valid, 200))
        self.assertIsNone(gate.load_manifest(lambda n: valid, 201))
        self.assertIsNone(gate.load_manifest(lambda n: b"{", 1))
        self.assertIsNone(gate.load_manifest(lambda n: b"x" * (manifest.MAX_MANIFEST_BYTES + 1), 1))
        duplicate = dict(self.manifest, entries={"/data/media/movies/Film.mkv": {}, "/data/media/movies/Other.mkv": {}})
        duplicate["entries"] = {str(i): {} for i in range(manifest.MAX_ENTRIES + 1)}
        self.assertIsNone(gate.load_manifest(lambda n: json.dumps(duplicate).encode(), 1))


class AdapterConfig(unittest.TestCase):
    def setUp(self):
        self.config = {"schema": adapter.CONFIG_SCHEMA, "enabled": True, "hostname": "example-am9",
                       "wifi_mac": "00:11:22:33:44:55", "mappings": {
                           "/data/media/movies/": "nfs://100.64.0.1/movies/",
                           "/data/media/shows/": "nfs://100.64.0.1/shows/"},
                       "manifest_uri": "nfs://100.64.0.1/.native/verified-p7-v1.json"}

    def test_only_exact_bound_device_configuration_is_accepted(self):
        self.assertIs(adapter.validate_config(self.config), self.config)
        raw = json.dumps(self.config).encode()
        self.assertIsNotNone(adapter.load_config(lambda n: raw, "example-am9", "00:11:22:33:44:55"))
        self.assertIsNone(adapter.load_config(lambda n: raw, "other-am9", "00:11:22:33:44:55"))
        for key, value in (("enabled", False), ("manifest_uri", "nfs://100.64.0.1/movies/x.json"),
                           ("wifi_mac", "not-a-mac"), ("hostname", "Bad Host")):
            changed = dict(self.config, **{key: value})
            self.assertIsNone(adapter.validate_config(changed))

    def test_actual_three_argument_hook_falls_back_without_kodi_or_config(self):
        self.assertIsNone(adapter.remote_original_path({}, {}, False))

    def test_runtime_package_imports_with_the_release_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "jellyfin_kodi" / "helper"
            remote = root / "remote_native"; remote.mkdir(parents=True)
            shutil.copy(HERE.parent / "jellyfin_native_originals.py", root / "native_originals.py")
            for name in ("__init__.py", "manifest.py", "gate.py", "kodi_adapter.py"):
                shutil.copy(HERE / name, remote / name)
            (root.parent / "__init__.py").write_text(""); (root / "__init__.py").write_text("")
            sys.path.insert(0, temp)
            try:
                package = __import__("jellyfin_kodi.helper.remote_native.kodi_adapter", fromlist=["remote_original_path"])
                self.assertTrue(callable(package.remote_original_path))
            finally:
                sys.path.remove(temp)
                for name in list(sys.modules):
                    if name == "jellyfin_kodi" or name.startswith("jellyfin_kodi."):
                        del sys.modules[name]


if __name__ == "__main__":
    unittest.main()
