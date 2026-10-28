import contextlib
import hashlib
import importlib.util
import os
import tempfile
import unittest
from unittest import mock
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("stage", HERE / "stage.py")
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class TestStage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "profile"
        self.root.mkdir()
        (self.root / stage.MARKER).write_text("fixture\n")
        skin = self.root / "addons/skin.arctic.fuse.3"
        skin.mkdir(parents=True)
        (skin / "addon.xml").write_text('<addon version="3.3.1"/>')
        receipt = self.root / "addons/plugin.video.habibi.resume/verified-build.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text("{}")
        for name in ("userdata/addon_data/skin.arctic.fuse.3",
                     "userdata/addon_data/script.skinvariables"):
            path = self.root / name
            path.mkdir(parents=True)
            (path / "settings.xml").write_text("<settings/>")
        gui = self.root / "userdata/guisettings.xml"
        gui.parent.mkdir(parents=True, exist_ok=True)
        gui.write_text("<settings/>")

        self.artifact = Path(self.tmp.name) / "tmdb.zip"
        requires = "".join(
            f'<import addon="{key}" version="{value}"/>'
            for key, value in stage.dependencies.TMDB_REQUIREMENTS.items()
        )
        xml = (
            f'<addon id="{stage.dependencies.TMDB_ID}" '
            f'version="{stage.dependencies.TMDB_VERSION}"><requires>{requires}'
            "</requires></addon>"
        )
        with zipfile.ZipFile(self.artifact, "w") as archive:
            archive.writestr(f"{stage.dependencies.TMDB_ID}/addon.xml", xml)
            archive.writestr(f"{stage.dependencies.TMDB_ID}/resources/main.py", b"reviewed")
        with zipfile.ZipFile(self.artifact) as archive:
            archive.extractall(self.root / "addons")

    @contextlib.contextmanager
    def official_fixture(self):
        blob = self.artifact.read_bytes()
        entries = stage.dependencies._zip_payload(blob)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                stage.dependencies, "TMDB_ARTIFACT_SHA256", hashlib.sha256(blob).hexdigest()))
            stack.enter_context(mock.patch.object(
                stage.dependencies, "TMDB_PAYLOAD_SHA256", stage.dependencies._payload_hash(entries)))
            stack.enter_context(mock.patch.object(
                stage.dependencies, "TMDB_PAYLOAD_FILE_COUNT", len(entries)))
            yield

    def test_stage_copies_only_private_fixture_and_keeps_rollback(self):
        out = Path(self.tmp.name) / "out"
        with self.official_fixture():
            result = stage.stage(
                Path(os.environ["ARCTIC_FUSE_3410_SOURCE"]), self.root, out, self.artifact)
            self.assertEqual(result["status"], "staged-only-requires-real-kodi-generation")
            self.assertEqual(result["schema"], 3)
            self.assertEqual(result["tmdbhelper"], stage.dependencies.reviewed_binding())
        self.assertTrue(result["candidate_skin_sha256"])
        self.assertTrue((out / "rollback/addons/skin.arctic.fuse.3/addon.xml").is_file())
        self.assertTrue((out / "candidate/addons/skin.arctic.fuse.3/shortcuts/generator/data/base/search_selector_owned.xml").is_file())

    def test_live_or_unmarked_profile_is_rejected(self):
        (self.root / stage.MARKER).unlink()
        with self.assertRaises(ValueError):
            stage.validate_profile(self.root)

    def test_same_version_but_changed_profile_payload_is_rejected_before_output(self):
        changed = self.root / "addons" / stage.dependencies.TMDB_ID / "resources/main.py"
        changed.write_bytes(b"different")
        out = Path(self.tmp.name) / "out-changed"
        with self.official_fixture():
            with self.assertRaisesRegex(ValueError, "payload differs"):
                stage.stage(Path(os.environ["ARCTIC_FUSE_3410_SOURCE"]),
                            self.root, out, self.artifact)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
