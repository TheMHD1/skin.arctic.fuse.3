"""Cheap safety checks; do not start Docker, open media or contact Jellyfin."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("publication_e2e", Path(__file__).with_name("run.py"))
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class SafetyTests(unittest.TestCase):
    def test_without_run_never_constructs_fixture(self):
        with patch.object(sys, "argv", ["run.py"]), patch.object(harness, "Fixture") as fixture:
            harness.main()
        fixture.assert_not_called()

    def test_fixture_paths_and_names_are_generated_not_production(self):
        fixture = harness.Fixture(types.SimpleNamespace(keep=False))
        try:
            self.assertTrue(fixture.name.startswith("publication-e2e-"))
            self.assertTrue(fixture.network.startswith(fixture.name))
            self.assertTrue(fixture.root.name.startswith("publication-e2e-"))
            self.assertNotEqual(str(fixture.root), "/data/media")
            self.assertIsNone(fixture.token)
        finally:
            fixture.cleanup()
        self.assertFalse(fixture.root.exists())

    def test_cleanup_removes_only_owned_exact_container_and_network(self):
        fixture = harness.Fixture(types.SimpleNamespace(keep=False))
        fixture.container_started = fixture.network_created = True
        with patch.object(harness, "command") as command:
            fixture.cleanup()
        self.assertEqual(command.call_args_list[0].args, ("docker", "rm", "-f", fixture.name))
        self.assertEqual(command.call_args_list[1].args, ("docker", "network", "rm", fixture.network))

    def test_scan_or_changed_execution_fails_acceptance(self):
        fixture = object.__new__(harness.Fixture)
        fixture.baseline_scan = {"EndTimeUtc": "fixture-baseline"}
        for state, result in (("Running", fixture.baseline_scan), ("Idle", {"EndTimeUtc": "changed"})):
            with self.subTest(state=state), patch.object(fixture, "scan_state", return_value=(state, result)):
                with self.assertRaises(AssertionError):
                    fixture.assert_no_scan()
        with patch.object(fixture, "scan_state", return_value=("Idle", fixture.baseline_scan)):
            fixture.assert_no_scan()

    def test_explicit_candidate_plan_still_has_no_side_effects(self):
        with patch.object(sys, "argv", ["run.py", "--expected-version", "12.4", "--artwork",
                                       "--plugin-dll", "/private/candidate.dll",
                                       "--plugin-meta", "/private/meta.json"]), patch.object(harness, "Fixture") as fixture:
            harness.main()
        fixture.assert_not_called()

    def test_cleanup_permission_repair_is_scoped_to_generated_fixture(self):
        fixture = harness.Fixture(types.SimpleNamespace(keep=False, image="local/reviewed:fixture"))
        real_remove = harness.shutil.rmtree
        try:
            with patch.object(harness.shutil, "rmtree", side_effect=[PermissionError(), None]), patch.object(harness, "command") as command:
                fixture.cleanup()
            args = command.call_args.args
            self.assertIn(str(fixture.root) + ":/fixture", args)
            self.assertIn("none", args)
            self.assertIn("/bin/sh", args)
            self.assertEqual(args[-1], str(harness.os.getuid()) + ":" + str(harness.os.getgid()))
            self.assertNotIn("/data/media:/fixture", args)
        finally:
            real_remove(fixture.root)


if __name__ == "__main__":
    unittest.main()
