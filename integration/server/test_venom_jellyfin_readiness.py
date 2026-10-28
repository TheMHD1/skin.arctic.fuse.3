"""Regression tests for the artwork service's Jellyfin readiness boundary."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "venom_jellyfin_readiness", HERE / "venom-jellyfin-readiness.py"
)
readiness = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(readiness)


PUBLIC_INFO = json.dumps(
    {
        "ProductName": "Jellyfin Server",
        "Version": "12.1-test",
        "StartupWizardCompleted": True,
    }
).encode()


class ScenarioHandler(BaseHTTPRequestHandler):
    scenarios: ClassVar[list[tuple[int, bytes, dict[str, str], float]]] = []
    seen_headers: ClassVar[list[dict[str, str]]] = []

    def do_GET(self):
        type(self).seen_headers.append(dict(self.headers.items()))
        status, body, headers, delay = type(self).scenarios.pop(0)
        if delay:
            time.sleep(delay)
        try:
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *_args):
        pass


class ScenarioServer:
    def __init__(self, scenarios):
        handler = type("BoundScenarioHandler", (ScenarioHandler,), {})
        handler.scenarios = list(scenarios)
        handler.seen_headers = []
        self.handler = handler
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def url(self, path="/System/Info/Public"):
        return f"http://127.0.0.1:{self.server.server_port}{path}"


class ReadinessTests(unittest.TestCase):
    def test_cli_absolute_deadline_rejects_slow_trickling_body(self):
        class TrickleHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    self.send_response(200)
                    self.send_header("Content-Length", "100")
                    self.end_headers()
                    for _ in range(100):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                        time.sleep(0.1)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), TrickleHandler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            environment = dict(os.environ)
            environment[readiness.ENVIRONMENT_KEY] = f"http://127.0.0.1:{server.server_port}/health"
            started = time.monotonic()
            result = subprocess.run(
                [sys.executable, str(HERE / "venom-jellyfin-readiness.py"), "--budget-seconds", "1"],
                env=environment, capture_output=True, text=True, timeout=3,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("absolute deadline", result.stderr)
            self.assertLess(time.monotonic() - started, 2.0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_real_http_unavailable_then_recovers_without_auth(self):
        scenarios = [
            (503, b"starting", {}, 0),
            (200, PUBLIC_INFO, {"Content-Type": "application/json"}, 0),
        ]
        with ScenarioServer(scenarios) as server:
            attempts = readiness.wait_until_ready(
                server.url(),
                budget_seconds=1,
                attempt_timeout_seconds=0.2,
                retry_interval_seconds=0.02,
            )
            self.assertEqual(attempts, 2)
            self.assertEqual(len(server.handler.seen_headers), 2)
            for headers in server.handler.seen_headers:
                self.assertNotIn("Authorization", headers)

    def test_strict_status_redirect_and_body_fail_closed(self):
        cases = {
            "non-200": (503, b"starting", {}, 0),
            "redirect": (
                302,
                b"",
                {"Location": "/System/Info/Public"},
                0,
            ),
            "malformed": (200, b"not-json", {}, 0),
            "setup-incomplete": (
                200,
                json.dumps(
                    {
                        "ProductName": "Jellyfin Server",
                        "Version": "12.1-test",
                        "StartupWizardCompleted": False,
                    }
                ).encode(),
                {},
                0,
            ),
        }
        for name, scenario in cases.items():
            with self.subTest(name=name), ScenarioServer([scenario]) as server:
                ready, reason = readiness.probe_once(server.url(), 0.3)
                self.assertFalse(ready)
                self.assertNotEqual(reason, "ready")

    def test_health_endpoint_requires_exact_healthy_body(self):
        with ScenarioServer([(200, b"Healthy\n", {}, 0)]) as server:
            self.assertEqual(
                readiness.probe_once(server.url("/health"), 0.3),
                (True, "ready"),
            )
        with ScenarioServer([(200, b"Degraded", {}, 0)]) as server:
            self.assertEqual(
                readiness.probe_once(server.url("/health"), 0.3),
                (False, "invalid-readiness-body"),
            )

    def test_timeout_obeys_total_budget(self):
        with ScenarioServer([(200, PUBLIC_INFO, {}, 0.5)] * 4) as server:
            started = time.monotonic()
            with self.assertRaises(readiness.ReadinessError):
                readiness.wait_until_ready(
                    server.url(),
                    budget_seconds=0.25,
                    attempt_timeout_seconds=0.1,
                    retry_interval_seconds=0.02,
                )
            self.assertLess(time.monotonic() - started, 0.45)

    def test_url_rejects_credentials_private_shape_and_nonpublic_path(self):
        for value in (
            "http://user:pass@example.invalid/System/Info/Public",
            "file:///System/Info/Public",
            "http://example.invalid/Users",
            "http://example.invalid/health?token=secret",
            " http://example.invalid/health",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                readiness.validate_url(value)

    def test_private_admin_origin_check_is_exact_and_does_not_call_api(self):
        calls = []

        def loader(path):
            calls.append(path)
            return {
                "BASE": "https://JELLYFIN.example/",
                "api": lambda *_args: self.fail("origin preflight called authenticated API"),
            }

        readiness.check_private_admin_origin(
            "https://jellyfin.example/System/Info/Public", loader=loader
        )
        self.assertEqual(calls, [readiness.ADMIN_HELPER])
        with self.assertRaisesRegex(ValueError, "origins differ"):
            readiness.check_private_admin_origin(
                "https://jellyfin.example:444/health", loader=loader
            )


class ServiceContractTests(unittest.TestCase):
    def test_readiness_precedes_all_existing_mutating_commands_and_retries_cap(self):
        text = (HERE / "venom-reviewed-artwork.service").read_text()
        preflight = "ExecStartPre=/usr/bin/python3 /data/config/iptv-venom/venom-jellyfin-readiness.py"
        artwork = "ExecStart=/usr/bin/python3 /data/config/iptv-venom/venom-reviewed-artwork-run.py --limit 1000"
        self.assertLess(text.index(preflight), text.index(artwork))
        self.assertIn("--check-admin-origin", text[text.index(preflight):text.index(artwork)])
        self.assertNotIn("ExecStartPost=", text)
        self.assertIn("EnvironmentFile=/etc/venom-reviewed-artwork.env", text)
        self.assertIn("StartLimitIntervalSec=2h", text)
        self.assertIn("StartLimitBurst=6", text)
        self.assertIn("Restart=on-failure", text)
        self.assertIn("RestartSec=10min", text)
        self.assertIn("TimeoutStartSec=20min", text)

    def test_unit_contains_no_private_url_or_literal_ip(self):
        text = (HERE / "venom-reviewed-artwork.service").read_text()
        self.assertNotRegex(text, r"https?://")
        self.assertNotRegex(text, r"(?:\d{1,3}\.){3}\d{1,3}")


if __name__ == "__main__":
    unittest.main()
