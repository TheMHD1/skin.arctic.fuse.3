import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock
from contextlib import redirect_stdout

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
        self.assertIn('<setting id="lookandfeel.skin">skin.estuary</setting>', settings)
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
                rpc=lambda method, params=None: [],
                binary_validator=lambda path: self.assertEqual(path, Path("/usr/lib/kodi/kodi.bin")),
                preflight_func=preflight,
                ports_validator=lambda: calls.append("ports"),
                send_generator=lambda run, helper: calls.append(("generator", str(helper))),
                launcher=lambda run, unit, home, binary: calls.append(("launch", unit, str(home))),
                stop_owned_unit=lambda run, unit: calls.append(("stop-owned", unit)),
                dependency_preflight=lambda *args: {probe.SKINVARIABLES: "h"},
                send_path_proof=lambda run, helper: calls.append(("path-proof", str(helper))),
                wait_for_path_proof=lambda home, nonce: {"special://home": "private"},
                activate_private_skin=lambda rpc, addons: calls.append(("activate", tuple(sorted(addons)))) or sorted(addons),
                wait_for_active_skin=lambda timeout, rpc: calls.append(("active-skin", timeout)),
            )
        finally:
            probe.lifecycle.idle = original_idle
            probe.prepare_home = original_prepare
            probe._wait_for_generation = original_wait
        self.assertEqual(len(preflights), 2)
        self.assertLess(calls.index(("systemctl", "stop", "kodi")), calls.index("ports"))
        self.assertLess(calls.index(("path-proof", "/usr/bin/kodi-send")),
                        calls.index(("generator", "/usr/bin/kodi-send")))
        self.assertLess(calls.index(("activate", (probe.SKIN_ID,))), calls.index(("path-proof", "/usr/bin/kodi-send")))
        self.assertTrue(any(call[0] == "stop-owned" for call in calls if isinstance(call, tuple)))
        self.assertEqual(calls[-1], ("systemctl", "start", "kodi"))
        self.assertEqual(result["generated"], [str(generated)])

    def test_activation_enables_only_closure_verifies_every_addon_and_switches_skin(self):
        calls = []
        enabled = set()

        def rpc(method, params=None):
            calls.append((method, params))
            if method == "Addons.SetAddonEnabled":
                self.assertTrue(params["enabled"])
                enabled.add(params["addonid"])
                return "OK"
            if method == "Addons.GetAddonDetails":
                return {"addon": {"enabled": params["addonid"] in enabled}}
            if method == "Settings.SetSettingValue":
                self.assertEqual(params, {"setting": "lookandfeel.skin", "value": probe.SKIN_ID})
                return True
            self.fail("unexpected RPC method: " + method)

        closure = {probe.SKIN_ID, probe.SKINVARIABLES, "script.module.infotagger"}
        self.assertEqual(probe._activate_private_skin(rpc, closure), sorted(closure))
        set_calls = [params["addonid"] for method, params in calls if method == "Addons.SetAddonEnabled"]
        self.assertEqual(set_calls, sorted(closure))
        self.assertEqual(calls[-1][0], "Settings.SetSettingValue")

        with self.assertRaises(RuntimeError):
            probe._activate_private_skin(rpc, {probe.SKINVARIABLES})

    def test_wait_for_active_skin_requires_candidate(self):
        responses = iter([{"skin": "skin.estuary"}, {"skin": probe.SKIN_ID}])
        original_sleep = probe.time.sleep
        try:
            probe.time.sleep = lambda _: None
            probe._wait_for_active_skin(1, lambda method, params=None: next(responses))
        finally:
            probe.time.sleep = original_sleep

    def test_builtin_captures_kodi_send_chatter_and_main_emits_one_apply_receipt(self):
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            return types.SimpleNamespace(stdout="Sending: noisy helper output\n", stderr="")

        helper = Path("/usr/bin/kodi-send")
        with mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "is_symlink", return_value=False):
            probe._send_builtin(run, helper, "RunScript(test)")
        self.assertEqual(calls[0][0], ["/usr/bin/kodi-send", "--action=RunScript(test)"])
        self.assertEqual(calls[0][1], {
            "check": True, "timeout": 10, "capture_output": True, "text": True,
        })

        profile = Path(self.tmp.name) / "profile.json"
        profile.write_text(json.dumps({"cohort": "local"}))
        stdout = io.StringIO()
        args = [
            "generation_probe.py", "--apply", "--stage", str(self.stage),
            "--profile", str(profile), "--runtime-home",
            str(self.root / ".arctic3410-generation/run-json"),
        ]
        with mock.patch.object(sys, "argv", args), \
             mock.patch.object(probe, "preflight", return_value={}), \
             mock.patch.object(probe, "runtime_dependency_preflight", return_value={"skinvariables": "hash"}), \
             mock.patch.object(probe, "run_probe", return_value={"generated": ["private.xml"]}), \
             redirect_stdout(stdout):
            probe.main()
        rendered = stdout.getvalue()
        self.assertEqual(rendered.count("\n{"), 0)
        receipt = json.loads(rendered)
        self.assertEqual(receipt["mode"], "probe")
        self.assertEqual(receipt["result"], {"generated": ["private.xml"]})


if __name__ == "__main__":
    unittest.main()
