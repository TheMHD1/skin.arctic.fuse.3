import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("arctic_install", HERE / "install.py")
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)


class ArcticInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.storage = Path(self.temporary.name) / "storage"
        self.root = self.storage / ".kodi"
        self.root.mkdir(parents=True)
        (self.storage / ".cache").mkdir()
        (self.storage / ".cache/hostname").write_text("fixture\n")
        (self.storage / ".config").mkdir()
        self.old_skin = self.root / install.SKIN
        (self.old_skin / "1080i").mkdir(parents=True)
        (self.old_skin / "addon.xml").write_text(
            '<addon id="skin.arctic.fuse.3" version="3.3.1" />')
        for number in range(15):
            (self.old_skin / "1080i" / f"historical-{number:02d}.xml").write_text(
                f"<include>{number}</include>")
        skin_entries = {str(path.relative_to(self.root)): install.sha(path)
                        for path in sorted(self.old_skin.rglob("*")) if path.is_file()}
        self.nonskin = self.root / "addons/plugin.video.fixture/source.py"
        self.nonskin.parent.mkdir(parents=True)
        self.nonskin.write_text("preserved-parent-source\n")
        manifest = {"files": {**skin_entries,
                               str(self.nonskin.relative_to(self.root)): install.sha(self.nonskin)}}
        self.manifest = self.storage / install.base.MANIFEST
        self.manifest.parent.mkdir(parents=True, exist_ok=True)
        self.manifest.write_bytes(install.canonical(manifest))
        subset = {name: digest for name, digest in manifest["files"].items()
                  if name.startswith("addons/skin.arctic.fuse.3/")}
        historical = install.sha_bytes(install.compact_canonical(dict(sorted(subset.items()))))
        self.historical_patch = patch.object(install, "HISTORICAL_SKIN_SHA256", historical)
        self.historical_patch.start()
        self.addCleanup(self.historical_patch.stop)
        final_before = dict(install.base.FINAL)
        install.base.FINAL.update(local=install.sha(self.manifest), remote=install.sha(self.manifest))
        self.addCleanup(lambda: (install.base.FINAL.clear(), install.base.FINAL.update(final_before)))

        skinvars = self.root / "addons/script.skinvariables/addon.xml"
        skinvars.parent.mkdir(parents=True)
        skinvars.write_text('<addon id="script.skinvariables" version="2.2.10" />')
        self.tmdb = self.root / "addons" / install.dependencies.TMDB_ID
        (self.tmdb / "resources").mkdir(parents=True)
        requirements = "".join(f'<import addon="{key}" version="{value}" />'
                               for key, value in install.dependencies.TMDB_REQUIREMENTS.items())
        (self.tmdb / "addon.xml").write_text(
            f'<addon id="{install.dependencies.TMDB_ID}" '
            f'version="{install.dependencies.TMDB_VERSION}"><requires>{requirements}'
            "</requires></addon>")
        (self.tmdb / "resources/main.py").write_text("reviewed")
        entries = {str(path.relative_to(self.tmdb)): path.read_bytes()
                   for path in self.tmdb.rglob("*") if path.is_file()}
        for item in (
            patch.object(install.dependencies, "TMDB_PAYLOAD_SHA256",
                         install.dependencies._payload_hash(entries)),
            patch.object(install.dependencies, "TMDB_PAYLOAD_FILE_COUNT", len(entries)),
        ):
            item.start()
            self.addCleanup(item.stop)

        for relative, value in (
            ("userdata/addon_data/skin.arctic.fuse.3/settings.xml",
             '<settings version="2">\n'
             '  <setting id="menu.alpha" default="true">one</setting>\n'
             '  <setting id="menu.beta">two</setting>\n'
             '  <setting id="menu.empty" />\n'
             '</settings>\n'),
            ("userdata/addon_data/skin.arctic.fuse.3/menu-layout.json", '{"layout":"main"}\n'),
            ("userdata/addon_data/script.skinvariables/settings.xml", "<settings>vars</settings>"),
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
        gui = self.root / "userdata/guisettings.xml"
        gui.parent.mkdir(parents=True, exist_ok=True)
        gui.write_text("<settings>gui</settings>")
        jellyfin = self.root / "userdata/addon_data/plugin.video.jellyfin/data.json"
        jellyfin.parent.mkdir(parents=True)
        jellyfin.write_text(json.dumps({"Servers": [{"UserId": "u", "address": "http://j"}]}))

        self.stage = Path(self.temporary.name) / "stage"
        self.candidate = self.stage / "candidate" / install.SKIN
        shutil.copytree(self.old_skin, self.candidate)
        (self.candidate / "addon.xml").write_text(
            '<addon id="skin.arctic.fuse.3" version="3.4.10" />')
        rollback = self.stage / "rollback"
        menu_relatives = (
            "userdata/addon_data/skin.arctic.fuse.3",
            "userdata/addon_data/script.skinvariables",
        )
        for relative in menu_relatives:
            shutil.copytree(self.root / relative, rollback / relative)
        self.record = {
            "schema": 3, "status": "staged-only-requires-real-kodi-generation",
            "upstream_commit": install.overlay.UPSTREAM_COMMIT,
            "tmdbhelper": install.dependencies.reviewed_binding(),
            "rollback": {
                "addons/skin.arctic.fuse.3": "directory",
                **{relative: "directory" for relative in menu_relatives},
            },
            "source_skin_sha256": install.directory_transaction.tree_hash(self.old_skin),
            "source_resume_receipt_sha256": install.sha(self.manifest),
            "candidate_skin_sha256": install.directory_transaction.tree_hash(self.candidate),
        }
        (self.stage / "stage.json").write_bytes(install.canonical(self.record))
        self.generated = Path(self.temporary.name) / "generated-skin"
        shutil.copytree(self.candidate, self.generated)
        markers = b"".join(b'<include name="' + marker + b'" />'
                           for marker in install.generation_evidence.MARKERS)
        (self.generated / "1080i/script-skinvariables-generator-includes-.xml").write_bytes(
            b"<includes>" + markers + b"</includes>")
        self.dependencies = {
            "script.skinvariables": install.directory_transaction.tree_hash(skinvars.parent)}
        self.menu = {relative: install.directory_transaction.tree_hash(rollback / relative)
                     for relative in menu_relatives}
        self.profile = {
            "cohort": "local", "hostname": "fixture", "wlan_mac": "aa:bb",
            "jellyfin_user_id": "u", "jellyfin_address": "http://j",
            "remote_marker_sha256": None,
        }
        self.parent_absent = self.storage / ".config/future-parent-state"
        self.parent_expected = {
            self.manifest: self.manifest.read_bytes(), self.nonskin: self.nonskin.read_bytes(),
            self.storage / ".cache/hostname": (self.storage / ".cache/hostname").read_bytes(),
            jellyfin: jellyfin.read_bytes(), self.parent_absent: None,
        }
        for name in skin_entries:
            path = self.root / name
            self.parent_expected[path] = path.read_bytes()
        self.parent_pending = False
        self.prepare_private_evidence("local")

    def guard(self, root, profile):
        self.assertEqual(Path(root), self.storage)
        for path, expected in self.parent_expected.items():
            current = path.read_bytes() if path.exists() else None
            if current != expected:
                raise ValueError("fixture parent source drift: " + str(path))
        changes = {self.nonskin: b"pending"} if self.parent_pending else {}
        return install.transaction.Plan(changes, dict(self.parent_expected))

    def prepare_private_evidence(self, cohort):
        self.profile["cohort"] = cohort
        self.profile["remote_marker_sha256"] = "f" * 64 if cohort == "remote" else None
        runtime = Path(self.temporary.name) / ("runtime-" + cohort)
        runtime.mkdir(mode=0o700)
        result = install.generation_evidence.write(
            runtime_home=runtime, stage=self.stage, generated_skin=self.generated,
            profile=self.profile, menu_inputs=self.menu,
            runtime_dependencies=self.dependencies, tool_root=HERE)
        self.evidence_path = Path(result["path"])
        self.profile[install.EVIDENCE_PROFILE_KEY] = result["sha256"]
        parent = install.plan(self.storage, self.stage, self.profile, self.guard)
        body = install._receipt_body(
            storage_root=self.storage, stage=self.stage, profile=self.profile,
            parent=parent, evidence=result["body"], evidence_sha256=result["sha256"],
            adapter_tool_root=HERE)
        self.profile[install.RECEIPT_PROFILE_KEY] = install.sha_bytes(install.canonical(body))

    def deployment(self):
        return install.deployment_plan(
            self.storage, self.stage, self.profile, self.generated,
            self.evidence_path, self.dependencies, parent_guard=self.guard)

    @staticmethod
    def fake_run(calls):
        def run(args, **_kwargs):
            calls.append(list(args))
            return types.SimpleNamespace(stdout="active\n", returncode=0)
        return run

    def execute_proof(self, _run, script):
        original = sys.modules.get("xbmcvfs")
        sys.modules["xbmcvfs"] = types.SimpleNamespace(translatePath=lambda _value: str(self.old_skin))
        try:
            exec(compile(script.read_text(), str(script), "exec"), {})
        finally:
            if original is None:
                del sys.modules["xbmcvfs"]
            else:
                sys.modules["xbmcvfs"] = original

    def apply(self, **overrides):
        calls = []
        arguments = dict(
            hostname_reader=lambda: "fixture", mac_reader=lambda: "aa:bb",
            run=self.fake_run(calls), parent_guard=self.guard, idle_func=lambda: None,
            wait_stopped_func=lambda: None, ready_func=lambda: None,
            send_proof=self.execute_proof, stability_sleeper=lambda _seconds: None)
        arguments.update(overrides)
        result = install.apply_release(
            self.storage, self.stage, self.profile, self.generated,
            self.evidence_path, self.dependencies, **arguments)
        return result, calls

    def test_plan_keeps_dynamic_parent_and_rejects_pending_parent(self):
        result = install.plan(self.storage, self.stage, self.profile, self.guard)
        self.assertEqual(result.expected, self.parent_expected)
        self.assertEqual(result[self.old_skin], self.candidate)
        self.parent_pending = True
        with self.assertRaisesRegex(ValueError, "pending"):
            install.plan(self.storage, self.stage, self.profile, self.guard)

    def test_historical_projection_uses_reviewed_compact_digest(self):
        manifest = json.loads(self.manifest.read_bytes())
        subset = dict(sorted((name, digest) for name, digest in manifest["files"].items()
                             if name.startswith("addons/skin.arctic.fuse.3/")))
        self.assertNotEqual(install.sha_bytes(install.canonical(subset)),
                            install.HISTORICAL_SKIN_SHA256)
        self.assertEqual(install.sha_bytes(install.compact_canonical(subset)),
                         install.HISTORICAL_SKIN_SHA256)

    def test_receipt_binds_both_cohorts_without_fixed_parent_count(self):
        for cohort in ("local", "remote"):
            if cohort == "remote":
                self.prepare_private_evidence(cohort)
            with self.subTest(cohort=cohort):
                prepared = self.deployment()
                body = json.loads(prepared.receipt_raw)
                self.assertEqual(body["cohort"], cohort)
                self.assertEqual(len(body["parent_snapshot"]), len(self.parent_expected))
                self.assertEqual(body["historical_skin_count"], 16)
                self.assertEqual(body["generated_skin_sha256"],
                                 install.directory_transaction.tree_hash(self.generated))

    def test_dependency_and_menu_drift_fail_before_stop(self):
        wrong = dict(self.dependencies, unexpected="0" * 64)
        with self.assertRaisesRegex(ValueError, "dependency closure"):
            install.deployment_plan(
                self.storage, self.stage, self.profile, self.generated,
                self.evidence_path, wrong, parent_guard=self.guard)
        menu = self.root / "userdata/addon_data/skin.arctic.fuse.3/settings.xml"
        menu.write_text(
            '<settings version="2"><setting id="menu.alpha" default="true">changed</setting>'
            '<setting id="menu.beta">two</setting><setting id="menu.empty" /></settings>')
        with self.assertRaisesRegex(ValueError, "settings changed"):
            self.deployment()

    def test_skin_settings_order_only_drift_is_stage_bound_and_accepted(self):
        settings = self.root / "userdata/addon_data/skin.arctic.fuse.3/settings.xml"
        settings.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<settings version="2"><setting id="menu.empty"></setting>\n'
            '<setting id="menu.beta">two</setting>\n'
            '<setting default="true" id="menu.alpha">one</setting></settings>\n')
        prepared = self.deployment()
        self.assertEqual(json.loads(prepared.receipt_raw)["menu_inputs"], self.menu)

    def test_menu_snapshot_hash_preserves_component_wise_path_order(self):
        root = self.storage / "nested-menu"
        for relative in ("a/x", "a-b/x", "a.b", "a0", "z"):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative)
        contents, digest = install._menu_tree_snapshot(root)
        self.assertIn("a", contents)
        self.assertEqual(digest, install.directory_transaction.tree_hash(root))

    def test_menu_snapshot_rejects_links_specials_and_size_limits(self):
        root = self.storage / "unsafe-menu"
        root.mkdir()
        source = root / "source"
        source.write_bytes(b"reviewed")
        unsafe = root / "unsafe"
        unsafe.symlink_to(source)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            install._menu_tree_snapshot(root)
        unsafe.unlink()
        os.link(source, unsafe)
        with self.assertRaisesRegex(ValueError, "multiply-linked"):
            install._menu_tree_snapshot(root)
        unsafe.unlink()
        os.mkfifo(unsafe)
        with self.assertRaisesRegex(ValueError, "Special"):
            install._menu_tree_snapshot(root)
        unsafe.unlink()
        with patch.object(install, "MAX_MENU_INPUT_FILE_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "file is too large"):
                install._menu_tree_snapshot(root)
        with patch.object(install, "MAX_MENU_INPUT_TREE_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "tree is too large"):
                install._menu_tree_snapshot(root)

    def test_menu_snapshot_rejects_file_replacement_during_read(self):
        root = self.storage / "unstable-menu"
        root.mkdir()
        source = root / "source"
        source.write_bytes(b"reviewed")
        original_read = install.os.read
        replaced = [False]

        def replacing_read(fd, amount):
            payload = original_read(fd, amount)
            if not replaced[0]:
                replacement = root / "replacement"
                replacement.write_bytes(b"reviewed")
                replacement.replace(source)
                replaced[0] = True
            return payload

        with patch.object(install.os, "read", side_effect=replacing_read):
            with self.assertRaisesRegex(ValueError, "changed while reading"):
                install._menu_tree_snapshot(root)

    def test_skin_settings_value_field_and_attribute_drift_are_rejected(self):
        settings = self.root / "userdata/addon_data/skin.arctic.fuse.3/settings.xml"
        original = settings.read_bytes()
        variants = {
            "value": (
                '<settings version="2"><setting id="menu.alpha" default="true">different</setting>'
                '<setting id="menu.beta">two</setting><setting id="menu.empty" /></settings>'),
            "added field": (
                '<settings version="2"><setting id="menu.alpha" default="true">one</setting>'
                '<setting id="menu.beta">two</setting><setting id="menu.empty" />'
                '<setting id="menu.added">new</setting></settings>'),
            "deleted field": (
                '<settings version="2"><setting id="menu.alpha" default="true">one</setting>'
                '<setting id="menu.empty" /></settings>'),
            "attribute": (
                '<settings version="2"><setting id="menu.alpha">one</setting>'
                '<setting id="menu.beta">two</setting><setting id="menu.empty" /></settings>'),
            "root attribute": (
                '<settings version="3"><setting id="menu.alpha" default="true">one</setting>'
                '<setting id="menu.beta">two</setting><setting id="menu.empty" /></settings>'),
        }
        for label, payload in variants.items():
            with self.subTest(label=label):
                settings.write_text(payload)
                with self.assertRaisesRegex(ValueError, "settings changed"):
                    self.deployment()
                settings.write_bytes(original)

    def test_skin_menu_other_bytes_and_membership_remain_exact(self):
        root = self.root / "userdata/addon_data/skin.arctic.fuse.3"
        other = root / "menu-layout.json"
        original = other.read_bytes()
        other.write_text('{"layout":"changed"}\n')
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            self.deployment()
        other.write_bytes(original)
        added = root / "unexpected.txt"
        added.write_text("unexpected")
        with self.assertRaisesRegex(ValueError, "membership changed"):
            self.deployment()
        added.unlink()
        other.unlink()
        with self.assertRaisesRegex(ValueError, "membership changed"):
            self.deployment()

    def test_skin_menu_reference_must_still_match_generation_evidence(self):
        reference = (self.stage / "rollback/userdata/addon_data/skin.arctic.fuse.3"
                     / "settings.xml")
        reference.write_text("<settings />")
        with self.assertRaisesRegex(ValueError, "reference drift"):
            self.deployment()

    def test_skin_settings_duplicate_nested_and_unsafe_xml_are_rejected(self):
        settings = self.root / "userdata/addon_data/skin.arctic.fuse.3/settings.xml"
        variants = {
            "duplicate": (
                '<settings version="2"><setting id="menu.alpha" default="true">one</setting>'
                '<setting id="menu.alpha" default="true">one</setting>'
                '<setting id="menu.beta">two</setting><setting id="menu.empty" /></settings>'),
            "nested": (
                '<settings version="2"><setting id="menu.alpha" default="true">'
                '<value>one</value></setting><setting id="menu.beta">two</setting>'
                '<setting id="menu.empty" /></settings>'),
            "comment": (
                '<settings version="2"><!-- hidden --><setting id="menu.alpha" '
                'default="true">one</setting><setting id="menu.beta">two</setting>'
                '<setting id="menu.empty" /></settings>'),
            "processing instruction": (
                '<settings version="2"><?unsafe value?><setting id="menu.alpha" '
                'default="true">one</setting><setting id="menu.beta">two</setting>'
                '<setting id="menu.empty" /></settings>'),
            "doctype/entity": (
                '<!DOCTYPE settings [<!ENTITY one "one">]><settings version="2">'
                '<setting id="menu.alpha" default="true">&one;</setting>'
                '<setting id="menu.beta">two</setting><setting id="menu.empty" /></settings>'),
            "unexpected child": (
                '<settings version="2"><other id="menu.alpha">one</other>'
                '<setting id="menu.beta">two</setting><setting id="menu.empty" /></settings>'),
        }
        for label, payload in variants.items():
            with self.subTest(label=label):
                settings.write_text(payload)
                with self.assertRaisesRegex(ValueError, "Arctic setting|Unsafe"):
                    self.deployment()

    def test_success_accepts_tree_and_retains_old_projection(self):
        proofs = [0]
        def counted_proof(run, script):
            proofs[0] += 1
            self.execute_proof(run, script)
        result, calls = self.apply(send_proof=counted_proof)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(install.version(self.old_skin / "addon.xml"), "3.4.10")
        accepted = install.installed_plan(
            self.storage, self.stage, self.profile, self.generated, self.evidence_path)
        self.assertFalse(accepted)
        journal = install.directory_transaction.load(self.old_skin)
        self.assertEqual(journal["state"]["phase"], "accepted")
        self.assertEqual(install.directory_transaction.tree_hash(journal["old"]),
                         self.record["source_skin_sha256"])
        self.assertEqual([item[1] for item in calls if item[:1] == ["systemctl"]],
                         ["stop", "start"])
        self.assertEqual(proofs[0], 2)

    def test_active_playback_refusal_never_stops_or_mutates(self):
        calls = []
        with self.assertRaisesRegex(RuntimeError, "playback"):
            install.apply_release(
                self.storage, self.stage, self.profile, self.generated,
                self.evidence_path, self.dependencies,
                hostname_reader=lambda: "fixture", mac_reader=lambda: "aa:bb",
                run=self.fake_run(calls), parent_guard=self.guard,
                idle_func=lambda: (_ for _ in ()).throw(RuntimeError("active playback")))
        self.assertEqual(calls, [])
        self.assertEqual(install.version(self.old_skin / "addon.xml"), "3.3.1")

    def test_failed_proof_restores_settings_and_absence(self):
        protected = self.root / "userdata/guisettings.xml"
        before = protected.read_bytes()
        absent = self.root / "userdata/addon_data/plugin.video.themoviedb.helper"

        attempts = [0]
        def bad_proof(run, script):
            attempts[0] += 1
            if attempts[0] == 1:
                protected.write_text("candidate changed settings")
                absent.mkdir(parents=True)
                raise RuntimeError("proof failed")
            self.execute_proof(run, script)

        with self.assertRaisesRegex(RuntimeError, "exact 3.3.1 state restored"):
            self.apply(send_proof=bad_proof)
        self.assertEqual(install.version(self.old_skin / "addon.xml"), "3.3.1")
        self.assertEqual(protected.read_bytes(), before)
        self.assertFalse(absent.exists())
        self.assertFalse((self.storage / install.RECEIPT).exists())

    def test_receipt_failure_after_start_rolls_back(self):
        def fail_writer(*_args, **_kwargs):
            raise OSError("full filesystem")
        with self.assertRaisesRegex(RuntimeError, "exact 3.3.1 state restored"):
            self.apply(writer=fail_writer)
        self.assertEqual(install.version(self.old_skin / "addon.xml"), "3.3.1")
        self.assertFalse((self.storage / install.RECEIPT).exists())

    def test_prepare_that_fails_after_durable_state_is_reloaded_and_rolled_back(self):
        real_prepare = install.directory_transaction.prepare
        def lost_return(*args, **kwargs):
            real_prepare(*args, **kwargs)
            raise OSError("caller lost prepared transaction")
        with patch.object(install.directory_transaction, "prepare", side_effect=lost_return):
            with self.assertRaisesRegex(RuntimeError, "exact 3.3.1 state restored"):
                self.apply()
        recovered = install.directory_transaction.load(self.old_skin)
        self.assertEqual(recovered["state"]["phase"], "rolled-back")
        self.assertEqual(install.version(self.old_skin / "addon.xml"), "3.3.1")

    def test_unproven_recovery_stop_withholds_rollback_and_second_start(self):
        calls = []
        stops = [0]
        def run(args, **_kwargs):
            calls.append(list(args))
            if args[:3] == ["systemctl", "stop", "kodi"]:
                stops[0] += 1
                if stops[0] == 2:
                    raise subprocess.CalledProcessError(1, args)
            return types.SimpleNamespace(stdout="active\n", returncode=0)
        with self.assertRaisesRegex(RuntimeError, "ALARM"):
            install.apply_release(
                self.storage, self.stage, self.profile, self.generated,
                self.evidence_path, self.dependencies,
                hostname_reader=lambda: "fixture", mac_reader=lambda: "aa:bb",
                run=run, parent_guard=self.guard, idle_func=lambda: None,
                wait_stopped_func=lambda: None, ready_func=lambda: None,
                send_proof=lambda *_: (_ for _ in ()).throw(RuntimeError("proof")),
                stability_sleeper=lambda _seconds: None)
        self.assertEqual(install.version(self.old_skin / "addon.xml"), "3.4.10")
        service_actions = [item[1] for item in calls if item[:1] == ["systemctl"]]
        self.assertEqual(service_actions, ["stop", "start", "stop"])

    def test_rollback_failure_leaves_kodi_stopped_and_does_not_claim_restore(self):
        calls = []
        with patch.object(install.directory_transaction, "rollback",
                          side_effect=RuntimeError("rollback storage failure")):
            with self.assertRaisesRegex(RuntimeError, "ALARM"):
                install.apply_release(
                    self.storage, self.stage, self.profile, self.generated,
                    self.evidence_path, self.dependencies,
                    hostname_reader=lambda: "fixture", mac_reader=lambda: "aa:bb",
                    run=self.fake_run(calls), parent_guard=self.guard,
                    idle_func=lambda: None, wait_stopped_func=lambda: None,
                    ready_func=lambda: None,
                    send_proof=lambda *_: (_ for _ in ()).throw(RuntimeError("proof")),
                    stability_sleeper=lambda _seconds: None)
        self.assertEqual(install.version(self.old_skin / "addon.xml"), "3.4.10")
        service_actions = [item[1] for item in calls if item[:1] == ["systemctl"]]
        self.assertEqual(service_actions, ["stop", "start", "stop"])

    def test_post_stop_parent_drift_prevents_switch(self):
        original = self.nonskin.read_bytes()
        def drift():
            self.nonskin.write_text("changed outside transaction")
        with self.assertRaisesRegex(RuntimeError, "ALARM"):
            self.apply(idle_func=drift)
        self.assertEqual(install.version(self.old_skin / "addon.xml"), "3.3.1")
        self.nonskin.write_bytes(original)

    def test_parent_drift_after_rollback_snapshot_prevents_switch(self):
        calls = [0]
        original = self.nonskin.read_bytes()
        def late_guard(root, profile):
            calls[0] += 1
            if calls[0] == 3:
                self.nonskin.write_text("raced during rollback copy")
            return self.guard(root, profile)
        with self.assertRaisesRegex(RuntimeError, "ALARM"):
            self.apply(parent_guard=late_guard)
        self.assertEqual(calls[0], 4)
        self.assertEqual(install.version(self.old_skin / "addon.xml"), "3.3.1")
        self.nonskin.write_bytes(original)

    def test_installed_guard_rejects_parent_and_old_skin_drift(self):
        self.apply()
        self.nonskin.write_text("drift")
        with self.assertRaisesRegex(ValueError, "parent source drift"):
            install.installed_plan(
                self.storage, self.stage, self.profile, self.generated, self.evidence_path)
        self.nonskin.write_bytes(self.parent_expected[self.nonskin])
        old = install.directory_transaction.load(self.old_skin)["old"]
        (old / "1080i/historical-00.xml").write_text("drift")
        with self.assertRaisesRegex(ValueError, "parent source drift|historical|preserved"):
            install.installed_plan(
                self.storage, self.stage, self.profile, self.generated, self.evidence_path)

    def test_power_loss_state_recovers_while_kodi_inactive(self):
        prepared = self.deployment()
        active = install.directory_transaction.prepare(
            prepared.target, prepared.generated, install.PROTECTED,
            recovery_root=self.root / ".arctic3410-recovery", bindings=prepared.bindings)
        install.directory_transaction.switch(active)
        receipt = self.storage / install.RECEIPT
        receipt_temporary = receipt.with_name(receipt.name + ".arctic3410-tmp")
        receipt_temporary.write_bytes(prepared.receipt_raw[:128]);receipt_temporary.chmod(0o600)
        calls = []
        result = install.recover_release(
            self.storage, self.stage, self.profile, self.generated, self.evidence_path,
            run=self.fake_run(calls), parent_guard=self.guard,
            unit_state_func=lambda: "inactive", wait_stopped_func=lambda: None,
            ready_func=lambda: None, send_proof=self.execute_proof)
        self.assertEqual(result["status"], "rolled-back")
        self.assertEqual(install.version(self.old_skin / "addon.xml"), "3.3.1")
        self.assertFalse(receipt_temporary.exists())
        self.assertEqual(len(list((active["root"] / "interrupted-receipts").glob("*.partial"))), 1)
        calls.clear()
        again = install.recover_release(
            self.storage, self.stage, self.profile, self.generated, self.evidence_path,
            run=self.fake_run(calls), parent_guard=self.guard,
            unit_state_func=lambda: "active", ready_func=lambda: None,
            send_proof=self.execute_proof)
        self.assertEqual(again["status"], "rolled-back-noop")
        self.assertEqual(calls, [])

    def test_recovery_refuses_ambiguous_unit_state(self):
        prepared = self.deployment()
        active = install.directory_transaction.prepare(
            prepared.target, prepared.generated, install.PROTECTED,
            recovery_root=self.root / ".arctic3410-recovery", bindings=prepared.bindings)
        install.directory_transaction.switch(active)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            install.recover_release(
                self.storage, self.stage, self.profile, self.generated, self.evidence_path,
                parent_guard=self.guard, unit_state_func=lambda: "deactivating")

    def test_rolled_back_recovery_retries_a_failed_old_kodi_start(self):
        prepared = self.deployment()
        active = install.directory_transaction.prepare(
            prepared.target, prepared.generated, install.PROTECTED,
            recovery_root=self.root / ".arctic3410-recovery", bindings=prepared.bindings)
        install.directory_transaction.switch(active)
        calls = []
        def failing_start(args, **_kwargs):
            calls.append(list(args))
            if args[:3] == ["systemctl", "start", "kodi"]:
                raise subprocess.CalledProcessError(1, args)
            return types.SimpleNamespace(stdout="inactive\n", returncode=0)
        with self.assertRaises(subprocess.CalledProcessError):
            install.recover_release(
                self.storage, self.stage, self.profile, self.generated, self.evidence_path,
                run=failing_start, parent_guard=self.guard, unit_state_func=lambda: "inactive",
                wait_stopped_func=lambda: None, ready_func=lambda: None,
                send_proof=self.execute_proof)
        self.assertEqual(install.directory_transaction.load(self.old_skin)["state"]["phase"],
                         "rolled-back")
        calls.clear()
        result = install.recover_release(
            self.storage, self.stage, self.profile, self.generated, self.evidence_path,
            run=self.fake_run(calls), parent_guard=self.guard,
            unit_state_func=lambda: "inactive", ready_func=lambda: None,
            send_proof=self.execute_proof)
        self.assertEqual(result["status"], "rolled-back-noop")
        self.assertEqual([item[1] for item in calls if item[:1] == ["systemctl"]], ["start"])

    def test_accepted_recovery_is_noop(self):
        self.apply()
        calls = []
        result = install.recover_release(
            self.storage, self.stage, self.profile, self.generated, self.evidence_path,
            run=self.fake_run(calls), parent_guard=self.guard,
            unit_state_func=lambda: (_ for _ in ()).throw(AssertionError("must not inspect")))
        self.assertEqual(result["status"], "accepted-noop")
        self.assertEqual(calls, [])

    def test_accepted_receipt_permissions_are_exact(self):
        self.apply()
        receipt = self.storage / install.RECEIPT
        receipt.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "metadata"):
            install.installed_plan(
                self.storage, self.stage, self.profile, self.generated, self.evidence_path)

    def test_accepted_guard_rejects_live_proof_evidence_tamper(self):
        self.apply()
        journal = install.directory_transaction.load(self.old_skin)
        nonce = journal["state"]["bindings"]["live_proof_nonce"]
        _script, receipt = install.lifecycle._live_proof_paths(journal["root"], nonce)
        receipt.write_text("{}")
        receipt.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError, "proof"):
            install.installed_plan(
                self.storage, self.stage, self.profile, self.generated, self.evidence_path)


if __name__ == "__main__":
    unittest.main()
