import importlib.util
import io
import json
import sqlite3
import subprocess
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

    def test_offline_bootstrap_enables_only_audited_private_closure(self):
        runtime = self.root / ".arctic3410-generation/run-bootstrap-db"
        database = runtime / ".kodi/userdata/Database" / probe.ADDONS_DATABASE_FILENAME
        database.parent.mkdir(parents=True)
        connection = sqlite3.connect(database)
        connection.executescript("""
            CREATE TABLE version (idVersion integer, iCompressCount integer);
            INSERT INTO version VALUES (33, 0);
            CREATE TABLE installed (id INTEGER PRIMARY KEY, addonID TEXT UNIQUE,
                enabled BOOLEAN, installDate TEXT, lastUpdated TEXT, lastUsed TEXT,
                origin TEXT NOT NULL DEFAULT '', disabledReason INTEGER NOT NULL DEFAULT 0);
        """)
        closure = {probe.SKIN_ID, probe.SKINVARIABLES, "script.module.infotagger"}
        for addon_id in sorted(closure | {"unrelated.private.addon"}):
            connection.execute("INSERT INTO installed(addonID,enabled,disabledReason) VALUES(?,?,?)",
                               (addon_id, 0, 7))
        connection.commit()
        connection.close()

        self.assertEqual(probe.enable_private_addons_offline(runtime, closure),
                         {"schema": 33, "closure_count": 3})
        connection = sqlite3.connect(database)
        rows = dict(connection.execute("SELECT addonID,enabled FROM installed"))
        connection.close()
        self.assertTrue(all(rows[addon_id] == 1 for addon_id in closure))
        self.assertEqual(rows["unrelated.private.addon"], 0)

    def test_offline_bootstrap_rejects_incomplete_or_unclean_private_database(self):
        runtime = self.root / ".arctic3410-generation/run-bootstrap-reject"
        database = runtime / ".kodi/userdata/Database" / probe.ADDONS_DATABASE_FILENAME
        database.parent.mkdir(parents=True)
        connection = sqlite3.connect(database)
        connection.executescript("""
            CREATE TABLE version (idVersion integer, iCompressCount integer);
            INSERT INTO version VALUES (33, 0);
            CREATE TABLE installed (id INTEGER PRIMARY KEY, addonID TEXT UNIQUE,
                enabled BOOLEAN, disabledReason INTEGER NOT NULL DEFAULT 0);
        """)
        connection.execute("INSERT INTO installed(addonID,enabled,disabledReason) VALUES(?,?,?)",
                           (probe.SKIN_ID, 0, 7))
        connection.commit()
        connection.close()

        closure = {probe.SKIN_ID, probe.SKINVARIABLES}
        with self.assertRaisesRegex(RuntimeError, "lacks the audited closure"):
            probe.enable_private_addons_offline(runtime, closure)
        connection = sqlite3.connect(database)
        self.assertEqual(connection.execute(
            "SELECT enabled,disabledReason FROM installed WHERE addonID=?", (probe.SKIN_ID,)
        ).fetchone(), (0, 7))
        connection.close()

        database.with_name(database.name + "-journal").write_bytes(b"not-a-live-journal")
        with self.assertRaisesRegex(RuntimeError, "uncheckpointed sidecar"):
            probe.enable_private_addons_offline(runtime, {probe.SKIN_ID})

    def test_offline_bootstrap_rejects_wrong_schema_before_mutating_rows(self):
        runtime = self.root / ".arctic3410-generation/run-bootstrap-wrong-schema"
        database = runtime / ".kodi/userdata/Database" / probe.ADDONS_DATABASE_FILENAME
        database.parent.mkdir(parents=True)
        connection = sqlite3.connect(database)
        connection.executescript("""
            CREATE TABLE version (idVersion integer, iCompressCount integer);
            INSERT INTO version VALUES (32, 0);
            CREATE TABLE installed (id INTEGER PRIMARY KEY, addonID TEXT UNIQUE,
                enabled BOOLEAN, disabledReason INTEGER NOT NULL DEFAULT 0);
        """)
        connection.execute("INSERT INTO installed(addonID,enabled,disabledReason) VALUES(?,?,?)",
                           (probe.SKIN_ID, 0, 9))
        connection.commit()
        connection.close()

        with self.assertRaisesRegex(RuntimeError, "unexpected private Kodi Addons database schema"):
            probe.enable_private_addons_offline(runtime, {probe.SKIN_ID})
        connection = sqlite3.connect(database)
        self.assertEqual(connection.execute(
            "SELECT enabled,disabledReason FROM installed WHERE addonID=?", (probe.SKIN_ID,)
        ).fetchone(), (0, 9))
        connection.close()

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
                activate_private_skin=lambda rpc, addons, runner, helper: calls.append(("activate", tuple(sorted(addons)))) or sorted(addons),
                wait_for_active_skin=lambda timeout, rpc: calls.append(("active-skin", timeout)),
                enable_private_addons=lambda home, addons: calls.append(("bootstrap-db", tuple(sorted(addons)))) or {"schema": 33, "closure_count": len(addons)},
            )
        finally:
            probe.lifecycle.idle = original_idle
            probe.prepare_home = original_prepare
            probe._wait_for_generation = original_wait
        self.assertEqual(len(preflights), 2)
        self.assertLess(calls.index(("systemctl", "stop", "kodi")), calls.index("ports"))
        self.assertLess(calls.index(("path-proof", "/usr/bin/kodi-send")),
                        calls.index(("generator", "/usr/bin/kodi-send")))
        launches = [call for call in calls if isinstance(call, tuple) and call[0] == "launch"]
        self.assertEqual(len(launches), 2)
        self.assertIn("bootstrap", launches[0][1])
        self.assertIn("generation", launches[1][1])
        bootstrap_stop = next(index for index, call in enumerate(calls)
                              if isinstance(call, tuple) and call[0] == "stop-owned"
                              and "bootstrap" in call[1])
        bootstrap_update = calls.index(("bootstrap-db", (probe.SKIN_ID,)))
        generation_launch = calls.index(launches[1])
        self.assertLess(bootstrap_stop, bootstrap_update)
        self.assertLess(bootstrap_update, generation_launch)
        self.assertLess(calls.index(("bootstrap-db", (probe.SKIN_ID,))), calls.index(("activate", (probe.SKIN_ID,))))
        self.assertLess(calls.index(("activate", (probe.SKIN_ID,))), calls.index(("path-proof", "/usr/bin/kodi-send")))
        # Bootstrap is stopped before its private DB transaction, then both
        # exact units are proven gone again in the outer failure-safe cleanup.
        self.assertEqual(sum(1 for call in calls if isinstance(call, tuple) and call[0] == "stop-owned"), 3)
        self.assertEqual(calls[-1], ("systemctl", "start", "kodi"))
        self.assertEqual(result["generated"], [str(generated)])

    def test_bootstrap_launcher_error_still_reaps_both_hashed_units_before_restart(self):
        calls = []
        original_idle = probe.lifecycle.idle
        original_prepare = probe.prepare_home
        try:
            probe.lifecycle.idle = lambda: calls.append("idle")
            probe.prepare_home = lambda *args, **kwargs: {
                "home": "private", "addons": {probe.SKIN_ID: "h"},
            }

            def run(argv, **kwargs):
                calls.append(tuple(argv))

            def launcher(run, unit, home, binary):
                calls.append(("launch", unit))
                if "bootstrap" in unit:
                    raise RuntimeError("systemd-run transport failed after submission")

            with self.assertRaisesRegex(RuntimeError, "transport failed"):
                probe.run_probe(
                    self.root, self.stage, {"cohort": "local"},
                    self.root / ".arctic3410-generation/run-bootstrap-launch-error",
                    run=run,
                    rpc=lambda method, params=None: [],
                    binary_validator=lambda path: None,
                    preflight_func=lambda *args: {},
                    ports_validator=lambda: calls.append("ports"),
                    launcher=launcher,
                    stop_owned_unit=lambda run, unit: calls.append(("stop-owned", unit)),
                    dependency_preflight=lambda *args: {},
                )
        finally:
            probe.lifecycle.idle = original_idle
            probe.prepare_home = original_prepare

        stopped = [call[1] for call in calls if isinstance(call, tuple) and call[0] == "stop-owned"]
        self.assertEqual(len(stopped), 2)
        self.assertIn("generation", stopped[0])
        self.assertIn("bootstrap", stopped[1])
        self.assertEqual(calls[-1], ("systemctl", "start", "kodi"))

    def test_bootstrap_launcher_cleanup_failure_withholds_normal_kodi_restart(self):
        calls = []
        original_idle = probe.lifecycle.idle
        original_prepare = probe.prepare_home
        try:
            probe.lifecycle.idle = lambda: calls.append("idle")
            probe.prepare_home = lambda *args, **kwargs: {
                "home": "private", "addons": {probe.SKIN_ID: "h"},
            }

            def run(argv, **kwargs):
                calls.append(tuple(argv))

            def stop_owned(run, unit):
                calls.append(("stop-owned", unit))
                if "bootstrap" in unit:
                    raise RuntimeError("bootstrap unit cleanup not proven")

            with self.assertRaisesRegex(RuntimeError, "bootstrap unit cleanup not proven"):
                probe.run_probe(
                    self.root, self.stage, {"cohort": "local"},
                    self.root / ".arctic3410-generation/run-bootstrap-cleanup-error",
                    run=run,
                    rpc=lambda method, params=None: [],
                    binary_validator=lambda path: None,
                    preflight_func=lambda *args: {},
                    ports_validator=lambda: calls.append("ports"),
                    launcher=lambda *args: (_ for _ in ()).throw(
                        RuntimeError("systemd-run transport failed after submission")
                    ),
                    stop_owned_unit=stop_owned,
                    dependency_preflight=lambda *args: {},
                )
        finally:
            probe.lifecycle.idle = original_idle
            probe.prepare_home = original_prepare

        self.assertFalse(any(call == ("systemctl", "start", "kodi") for call in calls))

    def test_activation_enables_only_closure_verifies_every_addon_and_switches_skin(self):
        calls = []
        enabled = set()

        runtime = self.root / ".arctic3410-generation/activation"
        for addon_id, point in ((probe.SKIN_ID, "xbmc.gui.skin"),
                                (probe.SKINVARIABLES, "xbmc.python.script"),
                                ("plugin.video.themoviedb.helper", "xbmc.python.pluginsource"),
                                ("script.module.infotagger", "xbmc.python.module")):
            path = runtime / ".kodi/addons" / addon_id
            path.mkdir(parents=True, exist_ok=True)
            (path / "addon.xml").write_text(
                f'<addon id="{addon_id}" version="1.0.0"><extension point="{point}" /></addon>'
            )

        def rpc(method, params=None):
            calls.append((method, params))
            if method == "Addons.GetAddonDetails":
                return {"addon": {"enabled": params["addonid"] in enabled}}
            self.fail("unexpected RPC method: " + method)

        closure = {probe.SKIN_ID, probe.SKINVARIABLES, "plugin.video.themoviedb.helper", "script.module.infotagger"}
        builtin_calls = []
        def send_builtin(run, helper, action):
            builtin_calls.append(action)
            if action.startswith("LoadSkin("):
                enabled.update(closure)
        with mock.patch.object(probe, "_send_builtin", side_effect=send_builtin):
            self.assertEqual(probe._activate_private_skin(
                rpc, closure, lambda *args, **kwargs: None,
                Path("/usr/bin/kodi-send"),
            ), sorted(closure))
        self.assertEqual(builtin_calls, ["LoadSkin(skin.arctic.fuse.3)"])

        with self.assertRaises(RuntimeError):
            probe._activate_private_skin(rpc, {probe.SKINVARIABLES}, lambda *args, **kwargs: None,
                                         Path("/usr/bin/kodi-send"))

    def test_activation_rejects_never_enabled_closure(self):
        calls = []
        def never_enabled(method, params=None):
            calls.append((method, params))
            return {"addon": {"enabled": False}}

        clock = iter((0.0, 0.0, 10.01)).__next__
        with self.assertRaisesRegex(RuntimeError, probe.SKINVARIABLES):
            probe._wait_for_private_addons_enabled(
                never_enabled, {probe.SKINVARIABLES}, timeout=10,
                clock=clock, sleeper=lambda _: None,
            )
        self.assertEqual(calls, [(
            "Addons.GetAddonDetails",
            {"addonid": probe.SKINVARIABLES, "properties": ["enabled"]},
        )])

    def test_owned_unit_cleanup_proves_exact_unit_gone_before_returning(self):
        calls = []
        states = iter((
            "LoadState=loaded\nActiveState=active\nSubState=running\nMainPID=91\n",
            "LoadState=loaded\nActiveState=inactive\nSubState=dead\nMainPID=0\n",
        ))

        def run(argv, **kwargs):
            calls.append((tuple(argv), kwargs))
            if argv[1] == "show":
                return types.SimpleNamespace(stdout=next(states))
            return types.SimpleNamespace(stdout="")

        probe._stop_owned_unit(run, "arctic3410-generation-123")
        self.assertEqual(calls[0][0][0:3], ("systemctl", "show", "arctic3410-generation-123"))
        self.assertEqual(calls[1][0], ("systemctl", "stop", "arctic3410-generation-123"))
        self.assertEqual(calls[2][0][0:3], ("systemctl", "show", "arctic3410-generation-123"))

    def test_owned_unit_cleanup_escalates_only_the_exact_unit_after_stop_timeout(self):
        calls = []
        now = [0.0]
        states = iter((
            "LoadState=loaded\nActiveState=active\nSubState=running\nMainPID=91\n",
            "LoadState=not-found\nActiveState=inactive\nSubState=dead\nMainPID=0\n",
        ))

        def run(argv, **kwargs):
            calls.append(tuple(argv))
            if argv[1] == "show":
                return types.SimpleNamespace(stdout=next(states))
            if argv[1] == "stop":
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            return types.SimpleNamespace(stdout="")

        probe._stop_owned_unit(
            run, "arctic3410-generation-exact", clock=lambda: now[0],
            sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
        )
        self.assertIn(("systemctl", "kill", "--kill-who=all", "--signal=SIGKILL",
                       "arctic3410-generation-exact"), calls)
        self.assertNotIn(("systemctl", "kill", "--kill-who=all", "--signal=SIGKILL", "kodi"), calls)

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
