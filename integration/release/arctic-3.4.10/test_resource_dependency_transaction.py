import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "resource_dependency_transaction", HERE / "resource_dependency_transaction.py")
tx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tx)


def make_addon(root, addon_id, version):
    path = root / addon_id
    path.mkdir(parents=True)
    (path / "addon.xml").write_text(
        f'<addon id="{addon_id}" version="{version}">'
        '<extension point="kodi.resource.images"/></addon>')
    (path / "payload.txt").write_text("payload:" + addon_id)
    return path


class FakeKodi:
    def __init__(self, case):
        self.case = case
        self.running = False
        self.start_calls = 0
        self.stop_calls = 0
        self.rpc_calls = []
        self.ready_failures = 0
        self.fail_start_once = False
        self.semantic_denial = None
        self.lost_ack = None
        self.after_start = None

    def state(self):
        return ("active", "running", 123) if self.running else ("inactive", "dead", 0)

    def start(self):
        self.start_calls += 1
        if self.fail_start_once:
            self.fail_start_once = False
            raise RuntimeError("start failure")
        self.running = True
        # This is Kodi's native startup scan: it discovers copied directories
        # and inserts them disabled.  The transaction itself never does this.
        connection = sqlite3.connect(self.case.database)
        try:
            for addon_id in tx.IDS:
                if (self.case.addons / addon_id).is_dir():
                    connection.execute(
                        "INSERT OR IGNORE INTO installed(addonID,enabled,disabledReason) VALUES(?,?,?)",
                        (addon_id, 0, 0))
            connection.commit()
        finally:
            connection.close()
        if self.after_start is not None:
            self.after_start()

    def stop(self):
        self.stop_calls += 1
        self.running = False

    def rpc(self, method, params=None):
        self.rpc_calls.append((method, params))
        if method == "Player.GetActivePlayers":
            if self.ready_failures:
                self.ready_failures -= 1
                raise ConnectionRefusedError("not ready")
            return []
        addon_id = params["addonid"]
        if method == "Addons.SetAddonEnabled":
            if self.semantic_denial == addon_id:
                return "DENIED"
            connection = sqlite3.connect(self.case.database)
            try:
                connection.execute(
                    "UPDATE installed SET enabled=1,disabledReason=0 WHERE addonID=?", (addon_id,))
                connection.commit()
            finally:
                connection.close()
            if self.lost_ack == addon_id:
                raise ConnectionResetError("ack lost")
            return "OK"
        if method == "Addons.GetAddonDetails":
            return {"addon": {"addonid": addon_id, "enabled": True,
                              "version": tx.PINS[addon_id]["version"]}}
        raise AssertionError(method)


class ResourceTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = Path(self.temp.name) / "storage"
        self.addons = self.storage / ".kodi/addons"
        self.database = self.storage / ".kodi/userdata/Database/Addons33.db"
        self.addons.mkdir(parents=True)
        self.database.parent.mkdir(parents=True)
        connection = sqlite3.connect(self.database)
        connection.executescript(
            "CREATE TABLE version(idVersion INTEGER); INSERT INTO version VALUES(33);"
            "CREATE TABLE installed(addonID TEXT PRIMARY KEY,enabled INTEGER,"
            "disabledReason INTEGER);")
        connection.commit(); connection.close()
        self.source = Path(self.temp.name) / "source"
        self.source.mkdir()
        pins = {}
        for addon_id, version in (("resource.images.arctic.weather", "1.0.4"),
                                  ("resource.images.arctic.splash", "1.1.0")):
            path = make_addon(self.source, addon_id, version)
            pins[addon_id] = {"version": version,
                              "sha256": tx.directory_transaction.tree_hash(path)}
        self.pins = mock.patch.object(tx, "PINS", pins)
        self.pins.start(); self.addCleanup(self.pins.stop)
        self.binding = "b" * 64
        self.nonce = "c" * 64
        self.kodi = FakeKodi(self)

    def lock(self):
        return tx.deployment_lock(self.storage)

    def test_stop_kodi_enqueues_nonblocking_and_still_polls_terminal_state(self):
        calls, states, now = [], [
            ("active", "running", 123), ("inactive", "dead", 0)], [0.0]

        def systemctl(*args):
            calls.append(args)
            return type("Result", (), {"returncode": 0})()

        def state():
            return states.pop(0)

        with mock.patch.object(tx, "systemctl", side_effect=systemctl):
            tx.stop_kodi(state_reader=state, clock=lambda: now[0],
                         sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds))
        self.assertEqual(calls, [("--no-block", "stop", "kodi")])
        self.assertEqual(states, [])

    def test_stop_kodi_nonblocking_ack_never_substitutes_for_deadline_proof(self):
        calls, now = [], [0.0]

        def systemctl(*args):
            calls.append(args)
            return type("Result", (), {"returncode": 0})()

        with mock.patch.object(tx, "systemctl", side_effect=systemctl):
            with self.assertRaisesRegex(RuntimeError, "could not be proved"):
                tx.stop_kodi(state_reader=lambda: ("active", "running", 123),
                             clock=lambda: now[0],
                             sleeper=lambda seconds: now.__setitem__(
                                 0, now[0] + max(seconds, 0.25)))
        self.assertEqual(calls, [("--no-block", "stop", "kodi")])
        self.assertGreaterEqual(now[0], 45)

    def prepare(self, lock):
        return tx.prepare(self.storage, self.source, cohort="local",
                          profile_binding_sha256=self.binding,
                          transaction_nonce=self.nonce, lock=lock,
                          state_reader=self.kodi.state,
                          restart_on_error=self.kodi.start)

    def install(self, transaction, lock):
        tx.install_directories(transaction, lock=lock, state_reader=self.kodi.state)

    def activate(self, transaction, lock):
        tx.activate_native(transaction, lock=lock, start=self.kodi.start,
                           stop=self.kodi.stop, state_reader=self.kodi.state,
                           rpc=self.kodi.rpc, sleeper=lambda _: None)

    def full_verified(self, lock):
        transaction = self.prepare(lock); self.install(transaction, lock)
        self.activate(transaction, lock)
        return transaction

    def test_exact_native_registration_acceptance_and_idempotence(self):
        with self.lock() as lock:
            self.assertEqual(tx.plan(self.storage, self.source, lock=lock)["changes"], list(tx.IDS))
            transaction = self.full_verified(lock)
            methods = [item[0] for item in self.kodi.rpc_calls]
            self.assertEqual(methods.count("Addons.SetAddonEnabled"), 2)
            self.assertEqual(tx.db_rows(self.database), {addon_id: (1, 0) for addon_id in tx.IDS})
            result = tx.accept(transaction, lock=lock, state_reader=self.kodi.state)
            self.assertRegex(result["receipt_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(tx.plan(self.storage, self.source, lock=lock)["changes"], [])
            receipt = json.loads(tx.paths(self.storage)["receipt"].read_text())
            self.assertEqual(set(receipt["resources"]), set(tx.IDS))
            self.assertEqual(receipt["lock_path"], str(tx.paths(self.storage)["lock"]))
            self.assertEqual(tx.recover(self.storage, lock=lock,
                                        state_reader=self.kodi.state,
                                        start=self.kodi.start, stop=self.kodi.stop), result)

    def test_lock_is_mandatory_and_replaced_lock_is_rejected(self):
        with self.assertRaises(RuntimeError):
            tx.plan(self.storage, self.source, lock=None)
        with self.lock() as lock:
            path = tx.paths(self.storage)["lock"]
            moved = path.with_suffix(".old")
            path.replace(moved); path.write_text("")
            with self.assertRaisesRegex(RuntimeError, "replaced"):
                tx.plan(self.storage, self.source, lock=lock)

    def test_partial_or_foreign_live_state_never_becomes_idempotent(self):
        shutil = __import__("shutil")
        shutil.copytree(self.source / tx.IDS[0], self.addons / tx.IDS[0])
        with self.lock() as lock, self.assertRaises(RuntimeError):
            tx.plan(self.storage, self.source, lock=lock)
        shutil.rmtree(self.addons / tx.IDS[0])
        connection = sqlite3.connect(self.database)
        connection.execute("INSERT INTO installed VALUES(?,?,?)", (tx.IDS[0], 1, 0))
        connection.commit(); connection.close()
        with self.lock() as lock, self.assertRaises(RuntimeError):
            tx.plan(self.storage, self.source, lock=lock)

    def test_source_extra_symlink_tree_and_metadata_drift_fail(self):
        (self.source / "extra").mkdir()
        with self.lock() as lock, self.assertRaises(ValueError):
            tx.plan(self.storage, self.source, lock=lock)
        (self.source / "extra").rmdir()
        payload = self.source / tx.IDS[0] / "payload.txt"
        payload.write_text("drift")
        with self.lock() as lock, self.assertRaises(ValueError):
            tx.plan(self.storage, self.source, lock=lock)

    def test_prepare_requires_stopped_sidecar_free_database(self):
        self.kodi.running = True
        with self.lock() as lock, self.assertRaisesRegex(RuntimeError, "stopped"):
            self.prepare(lock)
        self.kodi.running = False
        self.database.with_name(self.database.name + "-wal").write_text("writer")
        with self.lock() as lock, self.assertRaisesRegex(RuntimeError, "sidecar"):
            self.prepare(lock)

    def test_dangling_database_sidecar_symlink_is_not_absent(self):
        sidecar = self.database.with_name(self.database.name + "-wal")
        sidecar.symlink_to(self.database.parent / "missing-wal-target")
        with self.lock() as lock, self.assertRaisesRegex(RuntimeError, "sidecar"):
            self.prepare(lock)
        self.assertTrue(self.kodi.running)

    def test_interrupted_candidate_copy_cleans_owned_partial_and_restores_service(self):
        real_copytree = tx.shutil.copytree
        def partial(source, destination, **kwargs):
            destination.mkdir(parents=True)
            (destination / "partial").write_text("incomplete")
            raise OSError("copy interrupted")
        with self.lock() as lock, mock.patch.object(tx.shutil, "copytree", side_effect=partial):
            with self.assertRaisesRegex(OSError, "copy interrupted"):
                tx.prepare(self.storage, self.source, cohort="local",
                           profile_binding_sha256=self.binding,
                           transaction_nonce=self.nonce, lock=lock,
                           state_reader=self.kodi.state,
                           restart_on_error=self.kodi.start)
            self.assertTrue(self.kodi.running)
            self.assertFalse(any((self.addons / item).exists() for item in tx.IDS))
            self.assertEqual(tx.db_rows(self.database), {})
            evidence = tx.paths(self.storage)["failed"] / (
                tx.IDS[0] + ".candidate." + self.nonce)
            self.assertTrue(evidence.is_dir())
        self.assertIsNotNone(real_copytree)

    def test_initial_journal_failure_restores_service_without_targets(self):
        original = tx.atomic_record
        def fail_journal(path, value):
            if path.name == "transaction.json":
                raise OSError("journal write failed")
            return original(path, value)
        with self.lock() as lock, mock.patch.object(tx, "atomic_record", side_effect=fail_journal):
            with self.assertRaisesRegex(OSError, "journal write failed"):
                self.prepare(lock)
            self.assertTrue(self.kodi.running)
            self.assertFalse(any((self.addons / item).exists() for item in tx.IDS))
            self.assertEqual(tx.db_rows(self.database), {})

    def test_process_death_after_recovery_root_creation_reconciles_from_bootstrap(self):
        original = tx.atomic_record
        def fail_journal(path, value):
            if path.name == "transaction.json": raise OSError("power loss")
            return original(path, value)
        with self.lock() as lock, \
             mock.patch.object(tx, "atomic_record", side_effect=fail_journal), \
             mock.patch.object(tx, "reconcile_bootstrap", side_effect=SystemExit("dead")):
            with self.assertRaisesRegex(RuntimeError, "restart withheld"):
                self.prepare(lock)
        self.assertTrue(tx.paths(self.storage)["bootstrap"].is_file())
        self.assertTrue(tx.paths(self.storage)["root"].is_dir())
        with self.lock() as lock:
            result = tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                                start=self.kodi.start, stop=self.kodi.stop)
            self.assertEqual(result, {"state": "bootstrap-rolled-back"})
            self.assertTrue(self.kodi.running)
            self.assertFalse(tx.paths(self.storage)["bootstrap"].exists())
            self.assertFalse(tx.paths(self.storage)["root"].exists())

    def test_process_death_before_bootstrap_rename_quarantines_exact_pending_intent(self):
        original = tx._commit_record
        def crash(source, target):
            if target == tx.paths(self.storage)["bootstrap"]:
                raise SystemExit("power loss before bootstrap rename")
            return original(source, target)
        with self.lock() as lock, mock.patch.object(tx, "_commit_record", side_effect=crash):
            with self.assertRaises(SystemExit):
                self.prepare(lock)
        self.assertFalse(tx.paths(self.storage)["bootstrap"].exists())
        self.assertEqual(len(tx.pending_records(tx.paths(self.storage)["bootstrap"])), 1)
        with self.lock() as lock:
            result = tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                                start=self.kodi.start, stop=self.kodi.stop)
            self.assertEqual(result, {"state": "bootstrap-pending-rolled-back"})
            self.assertFalse(tx.pending_records(tx.paths(self.storage)["bootstrap"]))
            evidence = list((self.storage / ".kodi").glob(
                ".arctic3410-resource-bootstrap-pending-*.json"))
            self.assertEqual(len(evidence), 1)

    def test_process_death_before_initial_journal_rename_recovers_from_bootstrap(self):
        original = tx._commit_record
        def crash(source, target):
            if target == tx.paths(self.storage)["journal"]:
                raise SystemExit("power loss before journal rename")
            return original(source, target)
        with self.lock() as lock, \
             mock.patch.object(tx, "_commit_record", side_effect=crash), \
             mock.patch.object(tx, "reconcile_bootstrap", side_effect=SystemExit("process dead")):
            with self.assertRaisesRegex(RuntimeError, "restart withheld"):
                self.prepare(lock)
        with self.lock() as lock:
            result = tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                                start=self.kodi.start, stop=self.kodi.stop)
            self.assertEqual(result, {"state": "bootstrap-rolled-back"})

    def test_nested_symlink_in_fixed_database_path_is_rejected(self):
        database_dir = self.database.parent
        real = database_dir.with_name("Database.real")
        database_dir.replace(real)
        database_dir.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            tx.paths(self.storage)

    def test_concurrent_database_change_before_rename_fails_without_targets(self):
        with self.lock() as lock:
            transaction = self.prepare(lock)
            connection = sqlite3.connect(self.database)
            connection.execute("CREATE TABLE unrelated(value INTEGER)")
            connection.commit(); connection.close()
            with self.assertRaisesRegex(RuntimeError, "changed after snapshot"):
                self.install(transaction, lock)
            self.assertFalse(any((self.addons / item).exists() for item in tx.IDS))

    def test_crash_between_pair_renames_recovers_exact_db_and_absence(self):
        with self.lock() as lock:
            transaction = self.prepare(lock)
            original = tx._rename
            calls = []
            def crash(source, target):
                original(source, target); calls.append(target)
                if len(calls) == 1: raise KeyboardInterrupt("power loss")
            with mock.patch.object(tx, "_rename", side_effect=crash), self.assertRaises(KeyboardInterrupt):
                self.install(transaction, lock)
            result = tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                                stop=self.kodi.stop, start=self.kodi.start)
            self.assertEqual(result, {"state": "rolled-back"})
            self.assertTrue(self.kodi.running)
            self.assertEqual(tx.db_rows(self.database), {})
            self.assertFalse(any((self.addons / item).exists() for item in tx.IDS))

    def test_crash_after_both_renames_before_journal_update_recovers(self):
        with self.lock() as lock:
            transaction = self.prepare(lock)
            original = tx.set_phase
            with mock.patch.object(tx, "set_phase", side_effect=OSError("journal lost")):
                with self.assertRaisesRegex(OSError, "journal lost"):
                    self.install(transaction, lock)
            self.assertTrue(all((self.addons / item).is_dir() for item in tx.IDS))
            self.assertEqual(tx.read_journal(tx.paths(self.storage))[0]["phase"], "prepared")
            result = tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                                stop=self.kodi.stop, start=self.kodi.start)
            self.assertEqual(result, {"state": "rolled-back"})
            self.assertFalse(any((self.addons / item).exists() for item in tx.IDS))
            self.assertIs(original, tx.set_phase)

    def test_cross_directory_install_fsyncs_source_then_destination_and_recovers_failure(self):
        with self.lock() as lock:
            transaction = self.prepare(lock)
            calls = []
            original = tx.fsync_dir
            def record(path):
                calls.append(Path(path)); return original(path)
            with mock.patch.object(tx, "fsync_dir", side_effect=record):
                self.install(transaction, lock)
            expected = []
            for _ in tx.IDS:
                expected.extend([transaction["paths"]["candidates"], transaction["paths"]["addons"]])
            self.assertEqual(calls[:4], expected)

        # Fresh fixture: lose durability after the first rename's source fsync.
        self.setUp()
        with self.lock() as lock:
            transaction = self.prepare(lock)
            original = tx.fsync_dir; failed = {"done": False}
            def fail_source(path):
                original(path)
                if Path(path) == transaction["paths"]["candidates"] and not failed["done"]:
                    failed["done"] = True; raise OSError("source fsync failed")
            with mock.patch.object(tx, "fsync_dir", side_effect=fail_source), self.assertRaises(OSError):
                self.install(transaction, lock)
            result = tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                                start=self.kodi.start, stop=self.kodi.stop)
            self.assertEqual(result, {"state": "rolled-back"})

    def test_rollback_fsyncs_both_parents_for_resource_and_database_renames(self):
        with self.lock() as lock:
            transaction = self.prepare(lock); self.install(transaction, lock)
            self.kodi.start(); self.kodi.stop()
            calls = []; original = tx.fsync_dir
            def record(path): calls.append(Path(path)); return original(path)
            with mock.patch.object(tx, "fsync_dir", side_effect=record):
                tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                           start=self.kodi.start, stop=self.kodi.stop)
            pairs = list(zip(calls, calls[1:]))
            self.assertGreaterEqual(pairs.count((transaction["paths"]["addons"],
                                                 transaction["paths"]["failed"])), 2)
            self.assertIn((self.database.parent, transaction["paths"]["failed"]), pairs)

    def test_target_appearing_before_first_rename_causes_no_mutation(self):
        import shutil
        with self.lock() as lock:
            transaction = self.prepare(lock)
            shutil.copytree(self.source / tx.IDS[0], self.addons / tx.IDS[0])
            with self.assertRaisesRegex(RuntimeError, "appeared"):
                self.install(transaction, lock)
            self.assertFalse((self.addons / tx.IDS[1]).exists())

    def test_prepared_candidate_metadata_drift_is_not_renamed_or_deleted(self):
        with self.lock() as lock:
            transaction = self.prepare(lock)
            candidate = transaction["paths"]["candidates"] / tx.IDS[0]
            os.chmod(candidate / "payload.txt", 0o600)
            with self.assertRaisesRegex(RuntimeError, "candidate changed"):
                tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                           start=self.kodi.start, stop=self.kodi.stop)
            self.assertTrue(candidate.is_dir())
            self.assertFalse(any((self.addons / item).exists() for item in tx.IDS))

    def test_startup_failure_restores_and_restarts_old_kodi(self):
        with self.lock() as lock:
            transaction = self.prepare(lock); self.install(transaction, lock)
            self.kodi.fail_start_once = True
            with self.assertRaisesRegex(RuntimeError, "start failure"):
                self.activate(transaction, lock)
            self.assertTrue(self.kodi.running)
            self.assertEqual(self.kodi.start_calls, 2)
            self.assertEqual(tx.db_rows(self.database), {})

    def test_lost_rpc_ack_rolls_back_exactly_and_does_not_retry_semantics(self):
        with self.lock() as lock:
            transaction = self.prepare(lock); self.install(transaction, lock)
            self.kodi.lost_ack = tx.IDS[0]
            with self.assertRaises(ConnectionResetError):
                self.activate(transaction, lock)
            calls = [call for call in self.kodi.rpc_calls
                     if call[0] == "Addons.SetAddonEnabled" and call[1]["addonid"] == tx.IDS[0]]
            self.assertEqual(len(calls), 1)
            self.assertTrue(self.kodi.running)
            self.assertEqual(tx.db_rows(self.database), {})

    def test_semantic_denial_is_not_retried_and_readiness_is_bounded_retry(self):
        with self.lock() as lock:
            transaction = self.prepare(lock); self.install(transaction, lock)
            self.kodi.ready_failures = 2
            self.kodi.semantic_denial = tx.IDS[0]
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                self.activate(transaction, lock)
            self.assertEqual(sum(call[0] == "Player.GetActivePlayers" for call in self.kodi.rpc_calls), 3)
            self.assertEqual(sum(call[0] == "Addons.SetAddonEnabled" for call in self.kodi.rpc_calls), 1)

    def test_active_playback_and_semantic_readiness_error_fail_immediately(self):
        for response in ([{"playerid": 1, "type": "video"}], RuntimeError("malformed JSON")):
            with self.subTest(response=repr(response)):
                calls = []
                def rpc(method):
                    calls.append(method)
                    if isinstance(response, Exception): raise response
                    return response
                with self.assertRaises(RuntimeError):
                    tx.wait_ready(rpc, sleeper=lambda _: self.fail("semantic result retried"))
                self.assertEqual(calls, ["Player.GetActivePlayers"])

    def test_uncertain_stop_failure_withholds_rollback_and_restart(self):
        with self.lock() as lock:
            transaction = self.prepare(lock); self.install(transaction, lock)
            starts = self.kodi.start_calls
            def uncertain_stop():
                raise RuntimeError("stop uncertain")
            with self.assertRaisesRegex(RuntimeError, "restart withheld"):
                tx.activate_native(transaction, lock=lock, start=self.kodi.start,
                                   stop=uncertain_stop, state_reader=self.kodi.state,
                                   rpc=self.kodi.rpc, sleeper=lambda _: None)
            self.assertTrue(self.kodi.running)
            self.assertEqual(self.kodi.start_calls, starts + 1)
            self.assertTrue(all((self.addons / item).exists() for item in tx.IDS))

    def test_native_start_unrelated_or_metadata_db_change_is_never_verified(self):
        for change in ("logical", "mode"):
            with self.subTest(change=change):
                if change == "mode":
                    self.setUp()
                with self.lock() as lock:
                    transaction = self.prepare(lock); self.install(transaction, lock)
                    if change == "logical":
                        def mutate():
                            connection = sqlite3.connect(self.database)
                            connection.execute("CREATE TABLE foreign_startup(value INTEGER)")
                            connection.commit(); connection.close()
                    else:
                        def mutate(): os.chmod(self.database, 0o640)
                    self.kodi.after_start = mutate
                    with self.assertRaisesRegex(RuntimeError, "restart withheld"):
                        self.activate(transaction, lock)
                    self.assertFalse(self.kodi.running)
                    self.assertEqual(tx.read_journal(tx.paths(self.storage))[0]["phase"],
                                     "directories-installed")

    def test_replaced_target_quarantines_without_partial_rollback_or_restart(self):
        with self.lock() as lock:
            transaction = self.prepare(lock); self.install(transaction, lock)
            (self.addons / tx.IDS[1] / "payload.txt").write_text("foreign")
            self.kodi.running = True
            starts = self.kodi.start_calls
            with self.assertRaisesRegex(RuntimeError, "changed"):
                tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                           stop=self.kodi.stop, start=self.kodi.start)
            self.assertFalse(self.kodi.running)
            self.assertEqual(self.kodi.start_calls, starts)
            self.assertTrue(all((self.addons / item).exists() for item in tx.IDS))

    def test_unrelated_database_drift_is_quarantined_not_overwritten(self):
        with self.lock() as lock:
            transaction = self.prepare(lock); self.install(transaction, lock)
            connection = sqlite3.connect(self.database)
            connection.execute("CREATE TABLE foreign_change(value INTEGER)")
            connection.commit(); connection.close()
            with self.assertRaisesRegex(RuntimeError, "non-resource"):
                tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                           start=self.kodi.start, stop=self.kodi.stop)
            self.assertFalse(self.kodi.running)
            self.assertTrue(all((self.addons / item).is_dir() for item in tx.IDS))
            connection = sqlite3.connect(self.database)
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE name='foreign_change'").fetchone(), (1,))
            connection.close()

    def test_owned_native_rows_are_the_only_database_delta_restored(self):
        before = tx.db_state(self.database)
        with self.lock() as lock:
            transaction = self.prepare(lock); self.install(transaction, lock)
            self.kodi.start(); self.kodi.stop()
            tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                       start=self.kodi.start, stop=self.kodi.stop)
            self.assertEqual(tx.db_state(self.database), before)

    def exercise_interrupted_db_phase(self, fail_phase):
        os.chmod(self.database, 0o644)
        before = tx.db_state(self.database)
        self.assertEqual(before["mode"], 0o644)
        with self.lock() as lock:
            transaction = self.prepare(lock); self.install(transaction, lock)
            self.kodi.start(); self.kodi.stop()
            original = tx.set_phase
            failed_once = {"value": False}
            def fail_selected(active, phase):
                if phase == fail_phase and not failed_once["value"]:
                    failed_once["value"] = True
                    raise OSError("phase fsync interrupted")
                return original(active, phase)
            with mock.patch.object(tx, "set_phase", side_effect=fail_selected):
                with self.assertRaises(OSError):
                    tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                               start=self.kodi.start, stop=self.kodi.stop)
            journal_phase = tx.read_journal(tx.paths(self.storage))[0]["phase"]
            if not self.database.exists() and journal_phase == "rollback-db-preserved":
                temporary = self.database.with_name(
                    tx.DATABASE_NAME + ".restore." + self.nonce + ".tmp")
                temporary.write_bytes(b"partial"); os.chmod(temporary, 0o644)
            result = tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                                start=self.kodi.start, stop=self.kodi.stop)
            self.assertEqual(result, {"state": "rolled-back"})
            self.assertEqual(tx.db_state(self.database), before)
            self.assertTrue(self.kodi.running)

    def test_interrupted_database_preserve_is_resumable(self):
        self.exercise_interrupted_db_phase("rollback-db-preserved")

    def test_interrupted_database_restore_is_resumable(self):
        self.exercise_interrupted_db_phase("rollback-db-restored")

    def test_interrupted_0644_database_copy_is_owned_only_after_preserved_phase(self):
        os.chmod(self.database, 0o644)
        before = tx.db_state(self.database)
        with self.lock() as lock:
            transaction = self.prepare(lock); self.install(transaction, lock)
            self.kodi.start(); self.kodi.stop()
            original = tx.shutil.copy2
            def partial_copy(source, destination, **kwargs):
                destination = Path(destination)
                if ".restore." in destination.name:
                    destination.write_bytes(b"partial"); os.chmod(destination, 0o644)
                    raise OSError("copy power loss")
                return original(source, destination, **kwargs)
            with mock.patch.object(tx.shutil, "copy2", side_effect=partial_copy):
                with self.assertRaisesRegex(OSError, "copy power loss"):
                    tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                               start=self.kodi.start, stop=self.kodi.stop)
            self.assertEqual(tx.read_journal(tx.paths(self.storage))[0]["phase"],
                             "rollback-db-preserved")
            temporary = self.database.with_name(
                tx.DATABASE_NAME + ".restore." + self.nonce + ".tmp")
            self.assertEqual(temporary.stat().st_mode & 0o777, 0o644)
            result = tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                                start=self.kodi.start, stop=self.kodi.stop)
            self.assertEqual(result, {"state": "rolled-back"})
            self.assertEqual(tx.db_state(self.database), before)

    def test_corrupt_replaced_database_quarantines_and_never_restarts(self):
        with self.lock() as lock:
            transaction = self.prepare(lock); self.install(transaction, lock)
            self.database.write_bytes(b"not sqlite")
            starts = self.kodi.start_calls
            with self.assertRaises(RuntimeError):
                tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                           start=self.kodi.start, stop=self.kodi.stop)
            self.assertFalse(self.kodi.running)
            self.assertEqual(self.kodi.start_calls, starts)
            self.assertTrue(all((self.addons / item).is_dir() for item in tx.IDS))

    def test_foreign_nonce_restore_temp_and_symlink_failed_dir_are_rejected(self):
        with self.lock() as lock:
            transaction = self.prepare(lock); self.install(transaction, lock)
            self.kodi.start(); self.kodi.stop()
            temporary = self.database.with_name(
                tx.DATABASE_NAME + ".restore." + self.nonce + ".tmp")
            temporary.write_text("foreign")
            with self.assertRaisesRegex(RuntimeError, "predates"):
                tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                           start=self.kodi.start, stop=self.kodi.stop)
        self.setUp()
        with self.lock() as lock:
            transaction = self.prepare(lock); self.install(transaction, lock)
            outside = Path(self.temp.name) / "outside-failed"; outside.mkdir()
            tx.paths(self.storage)["failed"].symlink_to(outside, target_is_directory=True)
            with self.assertRaises((ValueError, RuntimeError)):
                tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                           start=self.kodi.start, stop=self.kodi.stop)
            self.assertEqual(list(outside.iterdir()), [])

    def test_accepted_receipt_allows_unrelated_later_database_changes_only(self):
        with self.lock() as lock:
            transaction = self.full_verified(lock)
            tx.accept(transaction, lock=lock, state_reader=self.kodi.state)
            connection = sqlite3.connect(self.database)
            connection.execute("CREATE TABLE unrelated_after_acceptance(value INTEGER)")
            connection.commit(); connection.close()
            self.assertEqual(tx.plan(self.storage, self.source, lock=lock)["changes"], [])
            connection = sqlite3.connect(self.database)
            connection.execute("UPDATE installed SET enabled=0 WHERE addonID=?", (tx.IDS[0],))
            connection.commit(); connection.close()
            with self.assertRaisesRegex(RuntimeError, "registration"):
                tx.plan(self.storage, self.source, lock=lock)

    def test_interrupted_acceptance_completes_only_with_exact_receipt_and_live_state(self):
        with self.lock() as lock:
            transaction = self.full_verified(lock)
            original = tx.set_phase
            with mock.patch.object(tx, "set_phase", side_effect=OSError("journal fsync")):
                with self.assertRaises(OSError):
                    tx.accept(transaction, lock=lock, state_reader=self.kodi.state)
            self.assertEqual(tx.read_journal(tx.paths(self.storage))[0]["phase"], "verified")
            self.kodi.running = True
            result = tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                                stop=self.kodi.stop, start=self.kodi.start)
            self.assertRegex(result["receipt_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(tx.read_journal(tx.paths(self.storage))[0]["phase"], "accepted")
            # Make sure the mock did not mask later phase changes.
            self.assertIs(original, tx.set_phase)

    def test_process_death_before_receipt_or_accepted_journal_rename_recovers(self):
        for boundary in ("receipt", "journal"):
            with self.subTest(boundary=boundary):
                if boundary == "journal": self.setUp()
                with self.lock() as lock:
                    transaction = self.full_verified(lock)
                    original = tx._commit_record
                    failed = {"value": False}
                    def crash(source, target):
                        receipt_target = tx.paths(self.storage)["receipt"]
                        journal_target = tx.paths(self.storage)["journal"]
                        should_fail = (boundary == "receipt" and target == receipt_target)
                        if boundary == "journal" and target == journal_target:
                            value, _ = tx.read_pending(source)
                            should_fail = value.get("phase") == "accepted"
                        if should_fail and not failed["value"]:
                            failed["value"] = True
                            raise SystemExit("acceptance power loss")
                        return original(source, target)
                    with mock.patch.object(tx, "_commit_record", side_effect=crash):
                        with self.assertRaises(SystemExit):
                            tx.accept(transaction, lock=lock, state_reader=self.kodi.state)
                    result = tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                                        start=self.kodi.start, stop=self.kodi.stop)
                    self.assertRegex(result["receipt_sha256"], r"^[0-9a-f]{64}$")
                    self.assertEqual(tx.read_journal(tx.paths(self.storage))[0]["phase"], "accepted")

    def test_unknown_pending_record_is_never_deleted_or_committed(self):
        path = tx.paths(self.storage)["bootstrap"]
        foreign = path.with_name(path.name + ".pending." + "f" * 64)
        foreign.write_text("{}\n"); os.chmod(foreign, 0o600)
        with self.lock() as lock, self.assertRaisesRegex(RuntimeError, "hash binding"):
            tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                       start=self.kodi.start, stop=self.kodi.stop)
        self.assertTrue(foreign.is_file())

    def test_receipt_or_database_change_before_accept_phase_never_accepts(self):
        for change in ("receipt", "database"):
            with self.subTest(change=change):
                if change == "database": self.setUp()
                with self.lock() as lock:
                    transaction = self.full_verified(lock)
                    original = tx.atomic_record
                    def mutate(path, value):
                        original(path, value)
                        if path == tx.paths(self.storage)["receipt"]:
                            if change == "receipt":
                                altered = dict(value); altered["post_database_sha256"] = "e" * 64
                                path.write_bytes(tx.canonical(altered)); os.chmod(path, 0o600)
                            else:
                                connection = sqlite3.connect(self.database)
                                connection.execute("CREATE TABLE accept_race(value INTEGER)")
                                connection.commit(); connection.close()
                    with mock.patch.object(tx, "atomic_record", side_effect=mutate):
                        with self.assertRaises(RuntimeError):
                            tx.accept(transaction, lock=lock, state_reader=self.kodi.state)
                    self.assertEqual(tx.read_journal(tx.paths(self.storage))[0]["phase"], "verified")

    def test_foreign_or_incomplete_acceptance_receipt_is_rejected(self):
        with self.lock() as lock:
            transaction = self.full_verified(lock)
            tx.paths(self.storage)["receipt"].write_text("{}\n")
            os.chmod(tx.paths(self.storage)["receipt"], 0o600)
            with self.assertRaises(RuntimeError):
                tx.recover(self.storage, lock=lock, state_reader=self.kodi.state,
                           stop=self.kodi.stop, start=self.kodi.start)

    def test_shape_valid_replaced_accepted_receipt_fails_journal_hash_binding(self):
        with self.lock() as lock:
            transaction = self.full_verified(lock)
            tx.accept(transaction, lock=lock, state_reader=self.kodi.state)
            path = tx.paths(self.storage)["receipt"]
            receipt = json.loads(path.read_text())
            receipt["post_database_sha256"] = "d" * 64
            path.write_bytes(tx.canonical(receipt)); os.chmod(path, 0o600)
            with self.assertRaisesRegex(RuntimeError, "receipt changed"):
                tx.plan(self.storage, self.source, lock=lock)

    def test_accept_reproves_stopped_sidecar_trees_and_rows_before_write(self):
        with self.lock() as lock:
            transaction = self.full_verified(lock)
            self.kodi.running = True
            with self.assertRaisesRegex(RuntimeError, "stopped"):
                tx.accept(transaction, lock=lock, state_reader=self.kodi.state)
            self.kodi.running = False
            (self.addons / tx.IDS[0] / "payload.txt").write_text("replaced")
            with self.assertRaisesRegex((RuntimeError, ValueError), "drift|changed"):
                tx.accept(transaction, lock=lock, state_reader=self.kodi.state)
            self.assertFalse(tx.paths(self.storage)["receipt"].exists())

        self.setUp()
        with self.lock() as lock:
            transaction = self.full_verified(lock)
            os.chmod(self.database, 0o640)
            with self.assertRaisesRegex(RuntimeError, "metadata"):
                tx.accept(transaction, lock=lock, state_reader=self.kodi.state)
            self.assertFalse(tx.paths(self.storage)["receipt"].exists())


if __name__ == "__main__":
    unittest.main()
