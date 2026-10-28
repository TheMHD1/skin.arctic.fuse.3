import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("generation_probe", HERE / "generation_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def addon(root, addon_id, version="1.0.0", imports=()):
    path = root / addon_id
    path.mkdir(parents=True)
    requires = "".join(
        f'<import addon="{name}" version="{minimum}" />' for name, minimum in imports
    )
    (path / "addon.xml").write_text(
        f'<addon id="{addon_id}" version="{version}"><requires>{requires}'
        "</requires></addon>"
    )
    (path / "payload.txt").write_text(addon_id)
    return path


class FakeProcess:
    def __init__(self):
        self.terminated = False
        self.killed = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout):
        return 0

    def kill(self):
        self.killed = True


class GenerationProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "storage"
        self.live = self.root / ".kodi/addons"
        self.system = Path(self.tmp.name) / "system-addons"
        self.stage = Path(self.tmp.name) / "stage"
        candidate = self.stage / "candidate/addons" / probe.SKIN_ID
        candidate.parent.mkdir(parents=True)
        addon(candidate.parent, probe.SKIN_ID, "3.4.10", ((probe.SKINVARIABLES, "2.2.9"),))
        addon(self.live, probe.SKINVARIABLES, "2.2.10", (
            ("script.module.jurialmunkey", "0.2.28"),
            ("script.module.infotagger", "0.0.5"),
        ))
        addon(self.live, "script.module.jurialmunkey", "0.2.35")
        addon(self.live, "script.module.infotagger", "0.1.0")
        addon(self.live, "plugin.video.jellyfin", "2.2.0")
        self.stage.mkdir(exist_ok=True)
        rollback = self.stage / "rollback"
        for relative in probe.SAFE_MENU_INPUTS:
            path = rollback / relative
            path.mkdir(parents=True)
            (path / "settings.xml").write_text("<settings><setting id=\"menu\">owned</setting></settings>")
        (self.stage / "stage.json").write_text(json.dumps({
            "candidate_skin_sha256": probe._tree_hash(candidate),
            "rollback": {str(relative): "directory" for relative in probe.SAFE_MENU_INPUTS},
        }))

    def test_prepare_copies_only_candidate_and_dependency_closure(self):
        runtime = self.root / ".arctic3410-generation/run-a"
        nonce = "a" * 64
        result = probe.prepare_home(self.root, self.stage, runtime, self.system,
                                    path_proof_nonce=nonce)
        copied = result["addons"]
        self.assertEqual(set(copied), {
            probe.SKIN_ID,
            probe.SKINVARIABLES,
            "script.module.jurialmunkey",
            "script.module.infotagger",
        })
        self.assertFalse((runtime / ".kodi/addons/plugin.video.jellyfin").exists())
        self.assertFalse((runtime / ".kodi/userdata/addon_data/plugin.video.jellyfin").exists())
        settings = (runtime / ".kodi/userdata/guisettings.xml").read_text()
        self.assertIn('<setting id="lookandfeel.skin">skin.arctic.fuse.3</setting>', settings)
        self.assertIn('<setting id="services.esenabled">true</setting>', settings)
        self.assertIn('<setting id="services.esport">9777</setting>', settings)
        self.assertIn('<setting id="services.esallinterfaces">false</setting>', settings)
        proof_script = runtime / ".kodi/userdata" / probe.PATH_PROOF_SCRIPT
        self.assertTrue(proof_script.is_file())
        self.assertIn("xbmcvfs.translatePath", proof_script.read_text())
        self.assertIn("os.replace", proof_script.read_text())
        probe.validate_minimal_home(runtime, set(copied), nonce)

    def test_service_dependency_and_extra_stage_file_are_rejected(self):
        candidate = self.stage / "candidate/addons" / probe.SKIN_ID
        addon_xml = candidate / "addon.xml"
        addon_xml.write_text(
            f'<addon id="{probe.SKIN_ID}" version="3.4.10"><requires>'
            '<import addon="service.tailscale" version="1.0.0" />'
            "</requires></addon>"
        )
        with self.assertRaises(ValueError):
            probe.dependency_closure(candidate, self.live, self.system)
        addon_xml.write_text(
            f'<addon id="{probe.SKIN_ID}" version="3.4.10"><requires>'
            f'<import addon="{probe.SKINVARIABLES}" version="2.2.9" />'
            '<import addon="service.tailscale" version="1.0.0" optional="true" />'
            "</requires></addon>"
        )
        closure = probe.dependency_closure(candidate, self.live, self.system)
        self.assertNotIn("service.tailscale", closure)
        addon_xml.write_text(
            f'<addon id="{probe.SKIN_ID}" version="3.4.10"><requires>'
            f'<import addon="{probe.SKINVARIABLES}" version="2.2.9" />'
            "</requires></addon>"
        )
        (self.stage / "stage.json").write_text(json.dumps({
            "candidate_skin_sha256": probe._tree_hash(candidate),
            "rollback": {str(relative): "directory" for relative in probe.SAFE_MENU_INPUTS},
        }))
        runtime = self.root / ".arctic3410-generation/run-b"
        probe.prepare_home(self.root, self.stage, runtime, self.system)
        (runtime / ".kodi/userdata/passwords.xml").write_text("must-not-be-here")
        with self.assertRaises(ValueError):
            probe.validate_minimal_home(runtime, {probe.SKIN_ID, probe.SKINVARIABLES,
                                                  "script.module.jurialmunkey", "script.module.infotagger"})

    def test_nonce_path_proof_requires_exact_private_kodi_mappings(self):
        runtime = self.root / ".arctic3410-generation/run-c"
        profile = runtime / ".kodi/userdata"
        profile.mkdir(parents=True)
        nonce = "b" * 64
        receipt = probe._path_proof_receipt(runtime, nonce)
        expected = {
            "special://home": str(runtime / ".kodi"),
            "special://profile": str(profile),
            "special://skin": str(runtime / ".kodi/addons" / probe.SKIN_ID),
        }
        receipt.write_text(json.dumps({
            "schema": probe.PATH_PROOF_SCHEMA,
            "nonce": nonce,
            "mappings": expected,
        }))
        self.assertEqual(probe._validate_path_proof_receipt(runtime, nonce), expected)

        receipt.write_text(json.dumps({
            "schema": probe.PATH_PROOF_SCHEMA,
            "nonce": "c" * 64,
            "mappings": expected,
        }))
        with self.assertRaises(RuntimeError):
            probe._validate_path_proof_receipt(runtime, nonce)

        receipt.write_text(json.dumps({
            "schema": probe.PATH_PROOF_SCHEMA,
            "nonce": nonce,
            "mappings": {**expected, "unexpected": "/tmp"},
        }))
        with self.assertRaises(RuntimeError):
            probe._validate_path_proof_receipt(runtime, nonce)

        receipt.write_text(json.dumps({
            "schema": probe.PATH_PROOF_SCHEMA,
            "nonce": nonce,
            "mappings": {**expected, "special://skin": "/storage/.kodi/addons/" + probe.SKIN_ID},
        }))
        with self.assertRaises(RuntimeError):
            probe._validate_path_proof_receipt(runtime, nonce)

    def test_path_proof_script_writes_nonce_receipt_atomically_inside_profile(self):
        runtime = self.root / ".arctic3410-generation/run-proof-script"
        profile = runtime / ".kodi/userdata"
        profile.mkdir(parents=True)
        nonce = "d" * 64
        script = probe._write_path_proof_script(runtime, nonce)
        mappings = {
            "special://home": str(runtime / ".kodi"),
            "special://profile": str(profile),
            "special://skin": str(runtime / ".kodi/addons" / probe.SKIN_ID),
        }
        original = sys.modules.get("xbmcvfs")
        sys.modules["xbmcvfs"] = types.SimpleNamespace(translatePath=mappings.__getitem__)
        try:
            exec(compile(script.read_text(), str(script), "exec"), {})
        finally:
            if original is None:
                del sys.modules["xbmcvfs"]
            else:
                sys.modules["xbmcvfs"] = original
        receipt = probe._path_proof_receipt(runtime, nonce)
        self.assertTrue(receipt.is_file())
        self.assertFalse(receipt.with_name(receipt.name + ".tmp").exists())
        self.assertEqual(probe._validate_path_proof_receipt(runtime, nonce), mappings)

    def test_reviewed_resources_are_exact_and_required_outputs_are_fresh(self):
        reviewed = Path(self.tmp.name) / "reviewed"
        weather = addon(reviewed, "resource.images.arctic.weather", "1.0.4")
        original_pins = probe.REVIEWED_RESOURCES
        try:
            probe.REVIEWED_RESOURCES = {
                "resource.images.arctic.weather": {
                    "version": "1.0.4", "sha256": probe._tree_hash(weather),
                },
            }
            self.assertEqual(probe.reviewed_resources(reviewed)[weather.name], weather)
            (weather / "payload.txt").write_text("drift")
            with self.assertRaises(ValueError):
                probe.reviewed_resources(reviewed)
        finally:
            probe.REVIEWED_RESOURCES = original_pins

        runtime = self.root / ".arctic3410-generation/run-e"
        output = runtime / ".kodi/addons" / probe.SKIN_ID / "1080i"
        output.mkdir(parents=True)
        stale = output / "script-skinvariables-generator-includes-main.xml"
        markers = "".join(
            f"<include name=\"{name}\" />" for name in (
                "skinvariables-searchwidgets-combined-selector-owned",
                "skinvariables-searchwidgets-combined-selector-venom",
                "skinvariables-searchwidgets-standard-selector-owned",
                "skinvariables-searchwidgets-standard-selector-venom",
            )
        )
        stale.write_text("<includes>" + markers + "</includes>")
        with self.assertRaises(RuntimeError):
            probe._wait_for_generation(runtime, 0, {stale.name})
        removed = probe.clear_generated_outputs(runtime)
        self.assertIn(stale.name, removed)
        self.assertFalse(stale.exists())

    def test_apply_rechecks_preflight_stops_only_owned_process_and_restarts_kodi(self):
        calls, preflights = [], []
        original_idle = probe.lifecycle.idle
        original_prepare = probe.prepare_home
        original_wait = probe._wait_for_generation
        try:
            probe.lifecycle.idle = lambda: calls.append("idle")
            probe.prepare_home = lambda *args, **kwargs: {"home": "private", "addons": {probe.SKIN_ID: "h"}}
            generated = self.root / ".arctic3410-generation/proof.xml"
            generated.parent.mkdir(parents=True)
            generated.write_text("ok")
            probe._wait_for_generation = lambda *args: [generated]

            def run(argv, **kwargs):
                calls.append(tuple(argv))

            def preflight(*args):
                preflights.append(args)
                return {Path("skin"): Path("candidate")}

            result = probe.run_probe(
                self.root, self.stage, {"cohort": "local"},
                self.root / ".arctic3410-generation/run-d",
                run=run,
                rpc=lambda method: [],
                binary_validator=lambda path: self.assertEqual(path, Path("/usr/lib/kodi/kodi.bin")),
                preflight_func=preflight,
                ports_validator=lambda: calls.append("ports"),
                send_generator=lambda run, helper: calls.append(("generator", str(helper))),
                launcher=lambda run, unit, home, binary: calls.append(("launch", unit, str(home))),
                stop_owned_unit=lambda run, unit: calls.append(("stop-owned", unit)),
                dependency_preflight=lambda *args: {probe.SKINVARIABLES: "h"},
                send_path_proof=lambda run, helper: calls.append(("path-proof", str(helper))),
                wait_for_path_proof=lambda home, nonce: {"special://home": "private"},
            )
        finally:
            probe.lifecycle.idle = original_idle
            probe.prepare_home = original_prepare
            probe._wait_for_generation = original_wait
        self.assertEqual(len(preflights), 2)
        self.assertLess(calls.index(("systemctl", "stop", "kodi")), calls.index("ports"))
        self.assertLess(calls.index(("path-proof", "/usr/bin/kodi-send")),
                        calls.index(("generator", "/usr/bin/kodi-send")))
        self.assertTrue(any(call[0] == "stop-owned" for call in calls if isinstance(call, tuple)))
        self.assertEqual(calls[-1], ("systemctl", "start", "kodi"))
        self.assertEqual(result["generated"], [str(generated)])


if __name__ == "__main__":
    unittest.main()
