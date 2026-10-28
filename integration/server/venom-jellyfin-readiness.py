"""Bounded, unauthenticated Jellyfin readiness gate for artwork maintenance."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import signal
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

ENVIRONMENT_KEY = "VENOM_JELLYFIN_READINESS_URL"
MAX_BODY_BYTES = 64 * 1024
MAX_BUDGET_SECONDS = 60.0
ALLOWED_PATHS = frozenset(("/System/Info/Public", "/health"))
ADMIN_HELPER = "/root/iptv-jellyfin-admin.py"


class ReadinessError(RuntimeError):
    """The endpoint did not become strictly ready within its budget."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep a redirect from turning a non-200 endpoint into an apparent pass."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_url(value: str) -> str:
    if not value or value != value.strip():
        raise ValueError(f"{ENVIRONMENT_KEY} is missing or has surrounding space")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("readiness URL must use http or https")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("readiness URL must have a host and no embedded credentials")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("readiness URL has an invalid port") from exc
    if parsed.path not in ALLOWED_PATHS or parsed.query or parsed.fragment:
        raise ValueError("readiness URL must be an exact public Jellyfin health endpoint")
    return value


def normalized_origin(value: str) -> tuple[str, str, int]:
    """Return the exact network origin of a validated readiness URL.

    The artwork worker has credentials and must only talk to the same Jellyfin
    origin that the unauthenticated readiness probe checked.  Compare the
    effective port too: an omitted HTTP/HTTPS port is not interchangeable with
    a non-default port, even when the hostname is the same.
    """
    validate_url(value)
    parsed = urllib.parse.urlsplit(value)
    assert parsed.hostname is not None  # established by validate_url()
    return (
        parsed.scheme.lower(),
        parsed.hostname.lower(),
        parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
    )


def normalized_admin_origin(value: str) -> tuple[str, str, int]:
    """Validate the authenticated helper's BASE as an origin, not a URL path."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("authenticated Jellyfin base is missing or malformed")
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("authenticated Jellyfin base has invalid origin shape")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("authenticated Jellyfin base has invalid port") from exc
    return parsed.scheme, parsed.hostname.lower(), port


def require_matching_admin_origin(readiness_url: str, admin_base: str) -> None:
    if normalized_origin(readiness_url) != normalized_admin_origin(admin_base):
        raise ValueError("readiness and authenticated Jellyfin origins differ")


def check_private_admin_origin(
    readiness_url: str,
    *,
    helper_path: str = ADMIN_HELPER,
    loader=runpy.run_path,
) -> None:
    """Load only the private helper definition and compare its exact BASE.

    This check does not call the helper's authenticated API and does not open any
    artwork lock, cache, report, pending or ledger path.
    """
    helper = loader(helper_path)
    if not isinstance(helper, dict) or "BASE" not in helper:
        raise ValueError("private Jellyfin helper has no BASE")
    require_matching_admin_origin(readiness_url, helper["BASE"])


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate public-info key")
        result[key] = value
    return result


def _valid_body(path: str, body: bytes) -> bool:
    if path == "/health":
        return body.strip() == b"Healthy"
    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return False
    return (
        isinstance(value, dict)
        and isinstance(value.get("ProductName"), str)
        and value["ProductName"].casefold().startswith("jellyfin")
        and isinstance(value.get("Version"), str)
        and bool(value["Version"].strip())
        and value.get("StartupWizardCompleted") is True
    )


def probe_once(
    url: str,
    timeout: float,
    *,
    opener: urllib.request.OpenerDirector | None = None,
) -> tuple[bool, str]:
    endpoint = urllib.parse.urlsplit(url).path
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/plain;q=0.9",
            "User-Agent": "VenomArtworkReadiness/1.0",
        },
        method="GET",
    )
    # A private readiness URL must not leak to a process-wide HTTP proxy.
    client = opener or urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect()
    )
    try:
        with client.open(request, timeout=timeout) as response:
            if response.status != 200:
                return False, f"http-{response.status}"
            body = response.read(MAX_BODY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        try:
            return False, f"http-{exc.code}"
        finally:
            exc.close()
    except (urllib.error.URLError, TimeoutError, OSError):
        return False, "transport-error"
    if len(body) > MAX_BODY_BYTES:
        return False, "response-too-large"
    if not _valid_body(endpoint, body):
        return False, "invalid-readiness-body"
    return True, "ready"


def wait_until_ready(
    url: str,
    *,
    budget_seconds: float = 60.0,
    attempt_timeout_seconds: float = 3.0,
    retry_interval_seconds: float = 3.0,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    validate_url(url)
    if not 0 < budget_seconds <= MAX_BUDGET_SECONDS:
        raise ValueError("readiness budget must be greater than zero and at most 60s")
    if not 0 < attempt_timeout_seconds <= 5:
        raise ValueError("attempt timeout must be greater than zero and at most 5s")
    if not 0 <= retry_interval_seconds <= 5:
        raise ValueError("retry interval must be between zero and 5s")

    deadline = clock() + budget_seconds
    attempts = 0
    last_reason = "not-attempted"
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            break
        attempts += 1
        ready, last_reason = probe_once(
            url, min(attempt_timeout_seconds, remaining)
        )
        if ready:
            return attempts
        remaining = deadline - clock()
        if remaining <= 0:
            break
        sleeper(min(retry_interval_seconds, remaining))
    raise ReadinessError(
        f"Jellyfin readiness failed after {attempts} attempts ({last_reason})"
    )


def _bounded_float(name: str, minimum: float, maximum: float):
    def parse(value: str) -> float:
        try:
            number = float(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{name} must be numeric") from exc
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(
                f"{name} must be between {minimum:g} and {maximum:g} seconds"
            )
        return number

    return parse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--budget-seconds",
        type=_bounded_float("budget", 1, MAX_BUDGET_SECONDS),
        default=60.0,
    )
    parser.add_argument(
        "--attempt-timeout-seconds",
        type=_bounded_float("attempt timeout", 2, 5),
        default=3.0,
    )
    parser.add_argument(
        "--retry-interval-seconds",
        type=_bounded_float("retry interval", 2, 5),
        default=3.0,
    )
    parser.add_argument(
        "--check-admin-origin",
        action="store_true",
        help="also require the private authenticated helper BASE to match this endpoint",
    )
    args = parser.parse_args()
    def deadline_expired(_signum, _frame):
        raise ReadinessError("Jellyfin readiness absolute deadline exceeded")

    # Socket timeouts alone can be extended by a slow-trickling body or DNS.
    # This Linux CLI owns its process, so a real timer bounds the whole check.
    previous_handler = signal.signal(signal.SIGALRM, deadline_expired)
    signal.setitimer(signal.ITIMER_REAL, args.budget_seconds)
    try:
        readiness_url = os.environ.get(ENVIRONMENT_KEY, "")
        attempts = wait_until_ready(
            readiness_url,
            budget_seconds=args.budget_seconds,
            attempt_timeout_seconds=args.attempt_timeout_seconds,
            retry_interval_seconds=args.retry_interval_seconds,
        )
        if args.check_admin_origin:
            check_private_admin_origin(readiness_url)
    except (ReadinessError, ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f"readiness failed: {exc}\n")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
    print(f"Jellyfin readiness passed after {attempts} attempt(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
