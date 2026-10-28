"""Regression tests for the Dispatcharr 0.33 local compatibility port.

These tests cover local safety behavior only: bounded admission, provider
ownership, and downstream keepalives. They contain no provider configuration.
"""

from unittest.mock import MagicMock

from django.test import SimpleTestCase

from apps.proxy.live_proxy.server import ProxyServer
from apps.proxy.live_proxy.views import _wait_for_stream_capacity


def _result(url=None, reason="maximum connection limits"):
    return (url, None, False, None, False, reason, None)


class OwnershipFailClosedTests(SimpleTestCase):
    def test_unavailable_redis_cannot_create_a_new_owner(self):
        server = ProxyServer.__new__(ProxyServer)
        server.redis_client = None
        self.assertFalse(server.try_acquire_ownership("channel"))

    def test_redis_command_failure_cannot_create_a_new_owner(self):
        server = ProxyServer.__new__(ProxyServer)
        server.redis_client = MagicMock()
        server.worker_id = "worker"
        server._execute_redis_command = MagicMock(return_value=None)
        self.assertFalse(server.try_acquire_ownership("channel"))


class AdmissionBudgetTests(SimpleTestCase):
    def test_capacity_retries_until_a_slot_becomes_available(self):
        calls = []
        times = iter((0.0, 0.0, 0.1))

        def fetch():
            calls.append(None)
            return _result() if len(calls) == 1 else _result("https://provider/live")

        sleeps = []
        result, attempts = _wait_for_stream_capacity(
            fetch, 0, clock=lambda: next(times), sleep=sleeps.append
        )
        self.assertEqual(attempts, 2)
        self.assertEqual(result[0], "https://provider/live")
        self.assertEqual(sleeps, [0.1])

    def test_non_capacity_failure_is_not_retried(self):
        result, attempts = _wait_for_stream_capacity(
            lambda: _result(reason="bad credentials"), 30,
            clock=lambda: 0.0, sleep=lambda _: self.fail("must not sleep"),
        )
        self.assertEqual(attempts, 1)
        self.assertEqual(result[5], "bad credentials")
