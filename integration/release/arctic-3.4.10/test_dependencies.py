import contextlib
import hashlib
import importlib.util
import shutil
import tempfile
import unittest
from unittest import mock
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dependencies", HERE / "dependencies.py")
dependencies = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dependencies)


def addon_xml(requirements, version=dependencies.TMDB_VERSION):
    imports = "".join(
        f'<import addon="{key}" version="{value}"/>'
        for key, value in requirements.items()
    )
    return (
        f'<addon id="{dependencies.TMDB_ID}" version="{version}">'
        f"<requires>{imports}</requires></addon>"
    )


class TestDependencies(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def artifact(self, name="tmdb.zip", requirements=None, version=None, payload=b"official"):
        requirements = requirements if requirements is not None else dependencies.TMDB_REQUIREMENTS
        version = version or dependencies.TMDB_VERSION
        path = Path(self.tmp.name) / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(f"{dependencies.TMDB_ID}/addon.xml", addon_xml(requirements, version))
            archive.writestr(f"{dependencies.TMDB_ID}/resources/main.py", payload)
        return path

    @contextlib.contextmanager
    def pinned(self, artifact):
        blob = artifact.read_bytes()
        entries = dependencies._zip_payload(blob)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                dependencies, "TMDB_ARTIFACT_SHA256", hashlib.sha256(blob).hexdigest()))
            stack.enter_context(mock.patch.object(
                dependencies, "TMDB_PAYLOAD_SHA256", dependencies._payload_hash(entries)))
            stack.enter_context(mock.patch.object(
                dependencies, "TMDB_PAYLOAD_FILE_COUNT", len(entries)))
            yield entries

    def extract(self, artifact, name="live"):
        root = Path(self.tmp.name) / name
        with zipfile.ZipFile(artifact) as archive:
            archive.extractall(root)
        return root / dependencies.TMDB_ID

    def test_exact_reviewed_artifact_and_complete_binding_are_accepted(self):
        artifact = self.artifact()
        with self.pinned(artifact):
            result = dependencies.review_tmdb_artifact(artifact)
            self.assertEqual(result, dependencies.reviewed_binding())
            self.assertEqual(result["version"], "6.19.2")
            self.assertEqual(result["commit"], dependencies.TMDB_COMMIT)
            self.assertEqual(result["repository_commit"], dependencies.TMDB_REPOSITORY_COMMIT)
            self.assertIn("xbmc.python", result["requirements"])

    def test_same_metadata_with_different_payload_fails_exact_zip_pin(self):
        reviewed = self.artifact("reviewed.zip")
        changed = self.artifact("changed.zip", payload=b"different code")
        with self.pinned(reviewed):
            with self.assertRaisesRegex(ValueError, "ZIP digest"):
                dependencies.review_tmdb_artifact(changed)

    def test_missing_extra_duplicate_dependency_and_wrong_version_fail_closed(self):
        cases = []
        missing = dict(dependencies.TMDB_REQUIREMENTS)
        missing.pop("script.module.qrcode")
        cases.append((missing, dependencies.TMDB_VERSION))
        extra = dict(dependencies.TMDB_REQUIREMENTS)
        extra["service.unreviewed"] = "1.0.0"
        cases.append((extra, dependencies.TMDB_VERSION))
        cases.append((dependencies.TMDB_REQUIREMENTS, "6.19.1"))
        for index, (requirements, version) in enumerate(cases):
            artifact = self.artifact(f"bad-{index}.zip", requirements, version)
            with self.subTest(index=index), self.pinned(artifact):
                with self.assertRaises(ValueError):
                    dependencies.review_tmdb_artifact(artifact)

        duplicate = Path(self.tmp.name) / "duplicate-dependency.zip"
        imports = dict(dependencies.TMDB_REQUIREMENTS)
        body = addon_xml(imports).replace(
            "</requires>", '<import addon="xbmc.python" version="3.0.1"/></requires>')
        with zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr(f"{dependencies.TMDB_ID}/addon.xml", body)
            archive.writestr(f"{dependencies.TMDB_ID}/resources/main.py", b"official")
        with self.pinned(duplicate):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                dependencies.review_tmdb_artifact(duplicate)

    def test_archive_traversal_duplicate_member_and_symlink_artifact_fail(self):
        unsafe = Path(self.tmp.name) / "unsafe.zip"
        with zipfile.ZipFile(unsafe, "w") as archive:
            archive.writestr("../addon.xml", "x")
            archive.writestr(f"{dependencies.TMDB_ID}/addon.xml", addon_xml(dependencies.TMDB_REQUIREMENTS))
        digest = hashlib.sha256(unsafe.read_bytes()).hexdigest()
        with mock.patch.object(dependencies, "TMDB_ARTIFACT_SHA256", digest):
            with self.assertRaisesRegex(ValueError, "unsafe"):
                dependencies.review_tmdb_artifact(unsafe)

        duplicate = Path(self.tmp.name) / "duplicate.zip"
        with self.assertWarns(UserWarning), zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr(f"{dependencies.TMDB_ID}/addon.xml", "one")
            archive.writestr(f"{dependencies.TMDB_ID}/addon.xml", "two")
        digest = hashlib.sha256(duplicate.read_bytes()).hexdigest()
        with mock.patch.object(dependencies, "TMDB_ARTIFACT_SHA256", digest):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                dependencies.review_tmdb_artifact(duplicate)

        reviewed = self.artifact("regular.zip")
        link = Path(self.tmp.name) / "linked.zip"
        link.symlink_to(reviewed)
        with self.pinned(reviewed):
            with self.assertRaisesRegex(ValueError, "regular ZIP"):
                dependencies.review_tmdb_artifact(link)

    def test_live_official_payload_with_derived_python_cache_is_accepted(self):
        artifact = self.artifact()
        with self.pinned(artifact):
            live = self.extract(artifact)
            cache = live / "resources/__pycache__"
            cache.mkdir()
            (cache / "main.cpython-314.opt-1.pyc").write_bytes(b"derived-cache")
            result = dependencies.review_live_tmdb(live, dependencies.reviewed_binding())
            self.assertEqual(result["runtime_pyc_files"], 1)

    def test_live_changed_missing_extra_and_symlink_payloads_fail(self):
        artifact = self.artifact()
        with self.pinned(artifact):
            baseline = self.extract(artifact, "baseline")
            mutations = {
                "changed": lambda root: (root / "resources/main.py").write_bytes(b"changed"),
                "missing": lambda root: (root / "resources/main.py").unlink(),
                "extra": lambda root: (root / "extra.txt").write_text("extra"),
                "empty-directory": lambda root: (root / "unreviewed-empty").mkdir(),
                "symlink": lambda root: (root / "linked.py").symlink_to("resources/main.py"),
                "orphan-pyc": lambda root: (
                    (root / "resources/__pycache__").mkdir(),
                    (root / "resources/__pycache__/orphan.cpython-314.pyc").write_bytes(b"bad"),
                ),
            }
            for name, mutate in mutations.items():
                live = Path(self.tmp.name) / name / dependencies.TMDB_ID
                shutil.copytree(baseline, live)
                mutate(live)
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        dependencies.review_live_tmdb(live, dependencies.reviewed_binding())

    def test_binding_drift_is_rejected_before_live_tree_is_read(self):
        binding = dependencies.reviewed_binding()
        binding["commit"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "provenance"):
            dependencies.review_live_tmdb(Path(self.tmp.name) / "absent", binding)


if __name__ == "__main__":
    unittest.main()
