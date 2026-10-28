import copy
import datetime
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("local_backup_receiver_install", HERE / "install.py")
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)


NOW = 1793196000


def utc(seconds):
    return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Tests(unittest.TestCase):
    def fixture(self, root: Path, cohort="local", expected_count=3):
        parent_receipt = root / install.previous.RECEIPT
        parent_receipt.parent.mkdir(parents=True)
        parent_receipt.write_bytes(b"exact-parent-receipt\n")
        manifest = root / ".kodi/addons/plugin.video.habibi.resume/verified-build.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_bytes(b"immutable-historical-manifest\n")
        identity = root / ".cache/hostname"
        identity.parent.mkdir(parents=True)
        identity.write_bytes(("fake-local-am9\n" if cohort == "local" else "fake-remote-am9\n").encode())
        expected = {
            parent_receipt: parent_receipt.read_bytes(),
            manifest: manifest.read_bytes(),
            identity: identity.read_bytes(),
        }
        while len(expected) < expected_count:
            item = root / ("parent-expected-%03d" % len(expected))
            item.write_bytes((item.name + "\n").encode())
            expected[item] = item.read_bytes()
        parent = install.transaction.Plan({}, expected)
        profile = {
            "cohort": cohort,
            "hostname": "fake-local-am9" if cohort == "local" else "fake-remote-am9",
            "wlan_mac": "02:00:00:00:00:01" if cohort == "local" else "02:00:00:00:00:02",
        }
        return parent, profile, manifest

    def evidence(self, root: Path, profile: dict):
        value = {
            "schema": 1,
            "record": "coreelec-local-backup-receiver-acceptance",
            "cohort": "local",
            "hostname": profile["hostname"],
            "wlan_mac": profile["wlan_mac"],
            "worker_sha256": install.AFTER,
            "installer_status": "installed-backup-acceptance-pending",
            "installer_receipt_sha256": "a" * 64,
            "service_result": "success",
            "service_exit_status": 0,
            "service_started_at": utc(NOW - 20),
            "service_finished_at": utc(NOW - 10),
            "destination_last_success_at": utc(NOW - 11),
            "backed_up_worker_sha256": install.AFTER,
            "sqlite_quick_checks": {"count": 14, "all_ok": True},
            "recorded_at": utc(NOW - 5),
        }
        path = root.parent / "private-acceptance.json"
        path.write_bytes(install.canonical(value))
        path.chmod(0o600)
        profile.update({
            "local_backup_receiver_evidence_sha256": install.sha(path.read_bytes()),
            "local_backup_receiver_installer_receipt_sha256": "a" * 64,
        })
        return path, value

    def finish_profile(self, root, parent, profile, evidence_path, evidence):
        body = install.receipt_body(
            profile,
            parent.expected[root / install.previous.RECEIPT],
            evidence,
            install.sha(evidence_path.read_bytes()),
        )
        raw = install.canonical(body)
        profile["local_backup_receiver_receipt_sha256"] = install.sha(raw)
        return raw

    def test_local_acceptance_preserves_parent_and_adds_only_worker_and_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "storage"
            root.mkdir()
            parent, profile, manifest = self.fixture(root, expected_count=73)
            worker = root / install.WORKER
            worker.parent.mkdir(parents=True)
            worker.write_bytes(b"receiver-compatible-worker")
            with patch.object(install, "AFTER", install.sha(worker.read_bytes())):
                evidence_path, evidence = self.evidence(root, profile)
                receipt_raw = self.finish_profile(root, parent, profile, evidence_path, evidence)
                baseline = dict(parent.expected)
                with patch.object(install.previous, "plan", return_value=parent):
                    result = install.acceptance_plan(root, profile, evidence_path, now=NOW)
                self.assertEqual({key: result.expected[key] for key in baseline}, baseline)
                self.assertEqual(set(result.expected) - set(baseline), {worker, root / install.RECEIPT})
                self.assertEqual(set(result), {root / install.RECEIPT})
                self.assertEqual(result[root / install.RECEIPT], receipt_raw)
                self.assertEqual(manifest.read_bytes(), b"immutable-historical-manifest\n")
                (root / install.RECEIPT).write_bytes(receipt_raw)
                parent_final = install.transaction.Plan({}, dict(baseline))
                with patch.object(install.previous, "plan", return_value=parent_final):
                    final = install.plan(root, profile)
                self.assertFalse(final)
                self.assertEqual({key: final.expected[key] for key in baseline}, baseline)
                self.assertEqual(len(final.expected), len(baseline) + 2)

    def test_remote_adds_only_absence_and_never_reads_local_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "storage"
            root.mkdir()
            parent, profile, _ = self.fixture(root, cohort="remote", expected_count=77)
            baseline = dict(parent.expected)
            worker = root / install.WORKER
            worker.parent.mkdir(parents=True)
            worker.symlink_to(root / "must-not-be-read")
            with patch.object(install.previous, "plan", return_value=parent):
                result = install.plan(root, profile)
            self.assertEqual({key: result.expected[key] for key in baseline}, baseline)
            self.assertEqual(set(result.expected) - set(baseline), {root / install.RECEIPT})
            self.assertIsNone(result.expected[root / install.RECEIPT])
            self.assertTrue(worker.is_symlink())
            self.assertEqual(len(result.expected), len(baseline) + 1)
            (root / install.RECEIPT).write_bytes(b"copied-local-receipt")
            with patch.object(install.previous, "plan", return_value=install.transaction.Plan({}, baseline)):
                with self.assertRaisesRegex(ValueError, "exists remotely"):
                    install.plan(root, profile)

    def test_parent_ownership_collision_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "storage"
            root.mkdir()
            parent, profile, _ = self.fixture(root)
            worker = root / install.WORKER
            worker.parent.mkdir(parents=True)
            worker.write_bytes(b"receiver-compatible-worker")
            parent.expected[worker] = worker.read_bytes()
            with patch.object(install.previous, "plan", return_value=parent):
                with self.assertRaisesRegex(ValueError, "already owns"):
                    install.plan(root, profile)

    def test_old_worker_or_arbitrary_evidence_cannot_be_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "storage"
            root.mkdir()
            parent, profile, _ = self.fixture(root)
            worker = root / install.WORKER
            worker.parent.mkdir(parents=True)
            worker.write_bytes(b"old-worker")
            evidence_path, evidence = self.evidence(root, profile)
            receipt_raw = self.finish_profile(root, parent, profile, evidence_path, evidence)
            del receipt_raw  # The exact receipt cannot make an old worker acceptable.
            with patch.object(install.previous, "plan", return_value=parent):
                with self.assertRaisesRegex(ValueError, "not installed"):
                    install.acceptance_plan(root, profile, evidence_path, now=NOW)
            worker.write_bytes(b"receiver-compatible-worker")
            with patch.object(install, "AFTER", install.sha(worker.read_bytes())):
                evidence["worker_sha256"] = install.AFTER
                evidence["backed_up_worker_sha256"] = install.AFTER
                cases = (
                    ("service_exit_status", 1, "successfully"),
                    ("cohort", "remote", "another appliance"),
                    ("installer_receipt_sha256", "b" * 64, "reviewed install"),
                    ("backed_up_worker_sha256", "b" * 64, "reviewed install"),
                    ("sqlite_quick_checks", {"count": 13, "all_ok": True}, "fourteen"),
                    ("recorded_at", utc(NOW - install.MAX_EVIDENCE_AGE - 10), "stale"),
                )
                for key, value, message in cases:
                    changed = copy.deepcopy(evidence)
                    changed[key] = value
                    evidence_path.write_bytes(install.canonical(changed))
                    profile["local_backup_receiver_evidence_sha256"] = install.sha(evidence_path.read_bytes())
                    raw = install.canonical(install.receipt_body(
                        profile,
                        parent.expected[root / install.previous.RECEIPT],
                        changed,
                        profile["local_backup_receiver_evidence_sha256"],
                    ))
                    profile["local_backup_receiver_receipt_sha256"] = install.sha(raw)
                    with self.subTest(key=key), patch.object(
                        install.previous, "plan", return_value=install.transaction.Plan({}, dict(parent.expected))
                    ):
                        with self.assertRaisesRegex(ValueError, message):
                            install.acceptance_plan(root, profile, evidence_path, now=NOW)
                changed = copy.deepcopy(evidence)
                changed.update({
                    "service_started_at": utc(NOW - 7200),
                    "destination_last_success_at": utc(NOW - 7195),
                    "service_finished_at": utc(NOW - 7190),
                })
                evidence_path.write_bytes(install.canonical(changed))
                profile["local_backup_receiver_evidence_sha256"] = install.sha(
                    evidence_path.read_bytes()
                )
                raw = install.canonical(install.receipt_body(
                    profile,
                    parent.expected[root / install.previous.RECEIPT],
                    changed,
                    profile["local_backup_receiver_evidence_sha256"],
                ))
                profile["local_backup_receiver_receipt_sha256"] = install.sha(raw)
                with patch.object(
                    install.previous,
                    "plan",
                    return_value=install.transaction.Plan({}, dict(parent.expected)),
                ):
                    with self.assertRaisesRegex(ValueError, "stale"):
                        install.acceptance_plan(root, profile, evidence_path, now=NOW)
                evidence_path.write_text(json.dumps(evidence))
                profile["local_backup_receiver_evidence_sha256"] = install.sha(
                    evidence_path.read_bytes()
                )
                raw = install.canonical(install.receipt_body(
                    profile,
                    parent.expected[root / install.previous.RECEIPT],
                    evidence,
                    profile["local_backup_receiver_evidence_sha256"],
                ))
                profile["local_backup_receiver_receipt_sha256"] = install.sha(raw)
                with patch.object(
                    install.previous,
                    "plan",
                    return_value=install.transaction.Plan({}, dict(parent.expected)),
                ):
                    with self.assertRaisesRegex(ValueError, "not canonical"):
                        install.acceptance_plan(root, profile, evidence_path, now=NOW)
                evidence_path.unlink()
                evidence_path.symlink_to(root / "missing")
                with patch.object(install.previous, "plan", return_value=parent):
                    with self.assertRaisesRegex(ValueError, "Unsafe"):
                        install.acceptance_plan(root, profile, evidence_path, now=NOW)

    def test_parent_changes_and_receipt_digest_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "storage"
            root.mkdir()
            parent, profile, _ = self.fixture(root)
            worker = root / install.WORKER
            worker.parent.mkdir(parents=True)
            worker.write_bytes(b"receiver-compatible-worker")
            with patch.object(install, "AFTER", install.sha(worker.read_bytes())):
                evidence_path, evidence = self.evidence(root, profile)
                receipt_raw = self.finish_profile(root, parent, profile, evidence_path, evidence)
                pending_parent = install.transaction.Plan({root / "parent-change": b"x"}, dict(parent.expected))
                with patch.object(install.previous, "plan", return_value=pending_parent):
                    with self.assertRaisesRegex(ValueError, "not yet converged"):
                        install.acceptance_plan(root, profile, evidence_path, now=NOW)
                receipt = root / install.RECEIPT
                receipt.write_bytes(receipt_raw + b" ")
                with patch.object(install.previous, "plan", return_value=parent):
                    with self.assertRaisesRegex(ValueError, "hash drift"):
                        install.plan(root, profile)


if __name__ == "__main__":
    unittest.main()
