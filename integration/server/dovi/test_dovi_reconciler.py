"""Isolated regression tests: never opens live media, databases, or queues."""
import concurrent.futures
import contextlib
import importlib.util
import io
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
# Subtitle filtering belongs to a separately tested publisher. These tests
# exercise only probe, retry admission, and the shared queue critical section.
stub = types.ModuleType("subtitle_view_filter")
stub.hidden_sources = lambda _: {}
stub.retired_sources = lambda _: {}
stub.digest = lambda _: "unused"
spec = importlib.util.spec_from_file_location(
    "dovi_reconciler_under_test", HERE / "dovi-library-view-20260922.py"
)
dovi = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = dovi
with patch.dict(sys.modules, {"subtitle_view_filter": stub}):
    spec.loader.exec_module(dovi)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.media = self.root / "sample.mkv"
        self.media.write_bytes(b"fixture-not-a-real-video")
        self.db = dovi.connect(self.root / "probe.sqlite")
        self.addCleanup(self.db.close)

    def result(self, output="|", code=0):
        return subprocess.CompletedProcess([], code, stdout=output)

    def test_blank_success_is_unknown_and_cools_down(self):
        with patch.object(dovi.subprocess, "run", return_value=self.result("")) as probe:
            self.assertIsNone(dovi.probe(self.media, self.db, 1000)[0])
            self.assertIsNone(dovi.probe(self.media, self.db, 1001)[0])
            self.assertEqual(probe.call_count, 1)
        self.assertEqual(self.db.execute("SELECT probe_ok FROM probe").fetchone()[0], 0)

    def test_timeout_is_unknown_not_sdr(self):
        with patch.object(dovi.subprocess, "run", side_effect=subprocess.TimeoutExpired("mediainfo", 90)):
            profile, description = dovi.probe(self.media, self.db, 1000)
        self.assertIsNone(profile)
        self.assertIn("124", description)

    def test_real_sdr_separator_is_valid_and_cached(self):
        with patch.object(dovi.subprocess, "run", return_value=self.result("|")) as probe:
            self.assertEqual(dovi.probe(self.media, self.db, 1000), (0, "|"))
            self.assertEqual(dovi.probe(self.media, self.db, 1400), (0, "|"))
            self.assertEqual(probe.call_count, 1)

    def test_legacy_blank_profile_zero_reprobes(self):
        self.db.execute(
            "INSERT INTO probe VALUES(?,?,?,?,?,?,?,?,?,?)",
            (str(self.media), *dovi.signature(self.media), 0, "", 900, 1, 900),
        )
        with patch.object(dovi.subprocess, "run", return_value=self.result("Dolby Vision|dvhe.07")) as probe:
            self.assertEqual(dovi.probe(self.media, self.db, 1000)[0], 7)
            self.assertEqual(probe.call_count, 1)

    def test_expired_unknown_reprobes(self):
        with patch.object(dovi.subprocess, "run", side_effect=[self.result("", 1), self.result("Dolby Vision|dvhe.07")]) as probe:
            self.assertIsNone(dovi.probe(self.media, self.db, 1000)[0])
            self.assertEqual(dovi.probe(self.media, self.db, 1300)[0], 7)
            self.assertEqual(probe.call_count, 2)

    def test_changed_file_bypasses_failed_probe_cooldown(self):
        with patch.object(dovi.subprocess, "run", side_effect=[self.result("", 1), self.result("Dolby Vision|dvhe.07")]):
            self.assertIsNone(dovi.probe(self.media, self.db, 1000)[0])
            self.media.write_bytes(b"different-size-replacement")
            self.assertEqual(dovi.probe(self.media, self.db, 1001)[0], 7)

    def test_retry_admission_honours_fingerprint_and_time(self):
        state = self.root / "retry.sqlite"
        stat = self.media.stat()
        signature = f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}"
        with sqlite3.connect(state) as db:
            db.execute("CREATE TABLE retries(path TEXT, signature TEXT, available REAL)")
            db.execute("INSERT INTO retries VALUES(?,?,?)", (str(self.media), signature, 1300))
        self.assertFalse(dovi.retry_allows(self.media, state, 1000))
        self.assertTrue(dovi.retry_allows(self.media, state, 1300))
        self.media.write_bytes(b"replacement-with-new-size")
        self.assertTrue(dovi.retry_allows(self.media, state, 1001))

    def test_invalid_retry_database_withholds_admission(self):
        state = self.root / "retry.sqlite"
        state.write_bytes(b"invalid database fixture")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(dovi.retry_allows(self.media, state, 1000))

    def test_parallel_queue_append_deduplicates_without_loss(self):
        queue = self.root / "queue.txt"
        lock = self.root / "local-queue.lock"
        paths = [self.root / f"movie-{i}.mkv" for i in range(64)] * 2
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda path: dovi.enqueue(path, queue, lock, True), paths))
        lines = queue.read_text().splitlines()
        self.assertEqual(len(lines), 64)
        self.assertEqual(set(lines), {str(path) for path in paths})
        self.assertEqual(sum(results), 64)

    def test_disabled_logical_path_seed_cannot_relabel_masters(self):
        for name in ("movies", "shows"):
            (self.root / "media" / name).mkdir(parents=True)
        args = ["test", "--seed-jellyfin", "--media-root", str(self.root / "media"),
                "--state", str(self.root / "seed.sqlite"), "--worker", str(self.root / "absent-worker")]
        with patch.object(sys, "argv", args), patch.object(dovi, "seed_from_jellyfin") as seed:
            with self.assertRaisesRegex(SystemExit, "unsafe.*disabled"):
                dovi.main()
            seed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
