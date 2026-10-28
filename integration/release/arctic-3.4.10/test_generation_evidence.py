import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("generation_evidence", HERE / "generation_evidence.py")
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


class GenerationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stage = self.root / "stage"
        self.candidate = self.stage / "candidate/addons/skin.arctic.fuse.3"
        (self.candidate / "1080i").mkdir(parents=True)
        (self.candidate / "addon.xml").write_text(
            '<addon id="skin.arctic.fuse.3" version="3.4.10" />'
        )
        (self.candidate / "1080i/base.xml").write_text("<includes />")
        (self.candidate / "media").mkdir()
        (self.candidate / "media/keep.txt").write_text("unchanged")
        (self.stage / "stage.json").write_text(json.dumps({
            "schema": 3,
            "candidate_skin_sha256": evidence.directory_transaction.tree_hash(self.candidate),
        }))
        self.generated = self.root / "generated"
        shutil.copytree(self.candidate, self.generated)
        markers = b"".join(b"<include name=\"" + marker + b"\" />" for marker in evidence.MARKERS)
        (self.generated / "1080i/script-skinvariables-generator-includes-.xml").write_bytes(
            b"<includes>" + markers + b"</includes>"
        )
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.profile = {
            "cohort": "local", "hostname": "CoreELEC", "wlan_mac": "aa:bb",
            "jellyfin_user_id": "user", "jellyfin_address": "http://jellyfin",
            "remote_marker_sha256": None,
        }
        self.menu = {
            "userdata/addon_data/skin.arctic.fuse.3": "1" * 64,
            "userdata/addon_data/script.skinvariables": "2" * 64,
        }
        self.dependencies = {"script.skinvariables": "3" * 64}

    def create(self):
        return evidence.write(
            runtime_home=self.runtime, stage=self.stage, generated_skin=self.generated,
            profile=self.profile, menu_inputs=self.menu,
            runtime_dependencies=self.dependencies, tool_root=HERE,
        )

    def test_writes_and_revalidates_complete_private_evidence(self):
        result = self.create()
        path = Path(result["path"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result["body"]["generated_files"], {
            "1080i/script-skinvariables-generator-includes-.xml":
                evidence.sha_file(self.generated / "1080i/script-skinvariables-generator-includes-.xml")
        })
        self.assertEqual(
            evidence.validate(path, result["sha256"], stage=self.stage,
                              generated_skin=self.generated, profile=self.profile, tool_root=HERE),
            result["body"],
        )

    def test_rejects_non_generated_change_missing_candidate_and_bad_generated_xml(self):
        (self.generated / "media/keep.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "Non-generated"):
            evidence.body(stage=self.stage, generated_skin=self.generated, profile=self.profile,
                          menu_inputs=self.menu, runtime_dependencies=self.dependencies,
                          tool_root=HERE)
        (self.generated / "media/keep.txt").write_text("unchanged")
        (self.generated / "addon.xml").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            evidence.body(stage=self.stage, generated_skin=self.generated, profile=self.profile,
                          menu_inputs=self.menu, runtime_dependencies=self.dependencies,
                          tool_root=HERE)
        shutil.copy2(self.candidate / "addon.xml", self.generated / "addon.xml")
        generated = self.generated / "1080i/script-skinvariables-generator-includes-.xml"
        generated.write_text("not XML")
        with self.assertRaisesRegex(ValueError, "not XML"):
            evidence.body(stage=self.stage, generated_skin=self.generated, profile=self.profile,
                          menu_inputs=self.menu, runtime_dependencies=self.dependencies,
                          tool_root=HERE)

    def test_rejects_missing_markers_unreviewed_outputs_and_symlinks(self):
        generated = self.generated / "1080i/script-skinvariables-generator-includes-.xml"
        generated.write_text("<includes />")
        with self.assertRaisesRegex(ValueError, "managed route"):
            evidence.body(stage=self.stage, generated_skin=self.generated, profile=self.profile,
                          menu_inputs=self.menu, runtime_dependencies=self.dependencies,
                          tool_root=HERE)
        generated.unlink()
        (self.generated / "1080i/unreviewed.xml").write_text("<includes />")
        with self.assertRaisesRegex(ValueError, "Non-generated"):
            evidence.body(stage=self.stage, generated_skin=self.generated, profile=self.profile,
                          menu_inputs=self.menu, runtime_dependencies=self.dependencies,
                          tool_root=HERE)
        (self.generated / "1080i/unreviewed.xml").unlink()
        (self.generated / "linked").symlink_to(self.generated / "addon.xml")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            evidence.body(stage=self.stage, generated_skin=self.generated, profile=self.profile,
                          menu_inputs=self.menu, runtime_dependencies=self.dependencies,
                          tool_root=HERE)

    def test_accepts_reviewed_user_slug_and_rejects_hostile_generator_filenames(self):
        default = self.generated / "1080i/script-skinvariables-generator-includes-.xml"
        payload = default.read_bytes()
        default.unlink()
        reviewed_user = self.generated / "1080i/script-skinvariables-generator-includes-user-Omar95.xml"
        reviewed_user.write_bytes(payload)
        generated = evidence.validate_generated_tree(self.candidate, self.generated)
        self.assertEqual(set(generated), {
            "1080i/script-skinvariables-generator-includes-user-Omar95.xml"
        })

        reviewed_user.unlink()
        for name in (
            "script-skinvariables-generator-includes-main.xml",
            "script-skinvariables-generator-includes-user-.xml",
            "script-skinvariables-generator-includes-user-Omar_95.xml",
            "script-skinvariables-generator-includes-user-Omar95.xml.bak",
            "script-skinvariables-generator-includes-..xml",
        ):
            with self.subTest(name=name):
                hostile = self.generated / "1080i" / name
                hostile.write_bytes(payload)
                with self.assertRaisesRegex(ValueError, "Non-generated"):
                    evidence.validate_generated_tree(self.candidate, self.generated)
                hostile.unlink()

    def test_rejects_tamper_hash_mode_and_identity(self):
        result = self.create()
        path = Path(result["path"])
        with self.assertRaisesRegex(ValueError, "hash drift"):
            evidence.validate(path, "0" * 64, stage=self.stage,
                              generated_skin=self.generated, profile=self.profile, tool_root=HERE)
        path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "Unsafe generation evidence"):
            evidence.validate(path, result["sha256"], stage=self.stage,
                              generated_skin=self.generated, profile=self.profile, tool_root=HERE)
        path.chmod(0o600)
        changed = dict(self.profile, jellyfin_user_id="another-user")
        with self.assertRaisesRegex(ValueError, "content drift"):
            evidence.validate(path, result["sha256"], stage=self.stage,
                              generated_skin=self.generated, profile=changed, tool_root=HERE)

    def test_refuses_second_receipt_and_invalid_stage_or_hash_maps(self):
        self.create()
        with self.assertRaisesRegex(ValueError, "not new"):
            self.create()
        (self.stage / "stage.json").write_text(json.dumps({"schema": 2}))
        with self.assertRaisesRegex(ValueError, "schema-3"):
            evidence.body(stage=self.stage, generated_skin=self.generated, profile=self.profile,
                          menu_inputs=self.menu, runtime_dependencies=self.dependencies,
                          tool_root=HERE)
        (self.stage / "stage.json").write_text(json.dumps({
            "schema": 3,
            "candidate_skin_sha256": evidence.directory_transaction.tree_hash(self.candidate),
        }))
        with self.assertRaisesRegex(ValueError, "menu input"):
            evidence.body(stage=self.stage, generated_skin=self.generated, profile=self.profile,
                          menu_inputs={"x": "bad"}, runtime_dependencies=self.dependencies,
                          tool_root=HERE)


if __name__ == "__main__":
    unittest.main()
