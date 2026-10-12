import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

spec = importlib.util.spec_from_file_location("recovery", Path(__file__).with_name("recover.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Fake:
    def __init__(self):
        self.calls = []
        self.source = {"target": mod.ROOT, "source": mod.DATASET, "fstype": "zfs", "options": "rw"}
        self.unit_options = "bind,ro"
        self.export_options = "ro,noatime"
        self.missing = 0

    def __call__(self, args):
        self.calls.append(args)
        if args[0] == "findmnt":
            path = args[3]
            if path == mod.ROOT:
                if self.missing:
                    self.missing -= 1
                    raise subprocess.CalledProcessError(1, args)
                row = self.source
                if row is None:
                    raise subprocess.CalledProcessError(1, args)
            else:
                name = path.rsplit("/", 1)[1]
                row = {"target": path, "source": mod.DATASET + "[/" + name + "]",
                       "fstype": "zfs", "options": self.export_options}
            return json.dumps({"filesystems": [row]})
        if args[:2] == ["systemctl", "cat"]:
            name = "movies" if "movies" in args[2] else "shows"
            return "[Unit]\nAssertPathIsMountPoint=/tank/media\n[Mount]\nWhat=%s/%s\nWhere=/srv/ugoos-media/%s\nType=none\nOptions=%s\n" % (
                mod.ROOT, name, name, self.unit_options)
        if args[:2] == ["systemctl", "start"]:
            return ""
        raise AssertionError(args)


class RecoveryTests(unittest.TestCase):
    def test_only_existing_two_units_start(self):
        fake = Fake()
        mod.restore(fake)
        self.assertEqual([a for a in fake.calls if a[:2] == ["systemctl", "start"]],
                         [["systemctl", "start", *mod.UNITS.values()], ["systemctl", "start", "nfs-server.service"]])

    def test_absent_source_never_mounts(self):
        fake = Fake(); fake.source = None
        with self.assertRaises(RuntimeError): mod.restore(fake)
        self.assertFalse(any(a[0] == "systemctl" for a in fake.calls))

    def test_wrong_source_fails_closed(self):
        fake = Fake(); fake.source["source"] = "wrong/data"
        with self.assertRaises(RuntimeError): mod.restore(fake)
        self.assertFalse(any(a[0] == "systemctl" for a in fake.calls))

    def test_rw_unit_rejected_before_start(self):
        fake = Fake(); fake.unit_options = "bind,rw"
        with self.assertRaises(RuntimeError): mod.restore(fake)
        self.assertFalse(any(a[:2] == ["systemctl", "start"] for a in fake.calls))

    def test_rw_result_not_accepted(self):
        fake = Fake(); fake.export_options = "rw"
        with self.assertRaises(RuntimeError): mod.restore(fake)
        self.assertNotIn(["systemctl", "start", "nfs-server.service"], fake.calls)

    def test_late_source_is_recovered(self):
        fake = Fake(); fake.missing = 2
        ticks = [0]
        mod.wait_and_restore(fake, lambda: ticks[0], lambda n: ticks.__setitem__(0, ticks[0] + n))
        self.assertEqual(ticks[0], 4)

    def test_timeout_is_finite_without_mount(self):
        fake = Fake(); fake.source = None
        ticks = [0]
        with self.assertRaises(RuntimeError):
            mod.wait_and_restore(fake, lambda: ticks[0], lambda n: ticks.__setitem__(0, ticks[0] + n))
        self.assertEqual(ticks[0], 60)
        self.assertFalse(any(a[0] == "systemctl" for a in fake.calls))

    def test_service_retries_are_bounded(self):
        unit = Path(__file__).with_name("am9-media-mount-recovery.service").read_text()
        for expected in ("StartLimitIntervalSec=45min", "StartLimitBurst=6", "RestartSec=5min"):
            self.assertIn(expected, unit)


if __name__ == "__main__": unittest.main()
