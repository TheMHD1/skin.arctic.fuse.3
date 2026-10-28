"""Additive local-only acceptance boundary for the restricted-rsync repair.

This module never installs the worker and never starts Kodi, the backup worker,
or any other service.  The already-reviewed private installer owns the worker
change.  This layer only composes the complete parent plan and, when supplied
with an exactly preauthorized private evidence record, prepares the one public
receipt that records successful live acceptance.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import time


HERE = Path(__file__).resolve().parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load reviewed parent release")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


previous = load(
    "local_backup_receiver_parent",
    HERE.parent / "library-transactions" / "install.py",
)
transaction = previous.transaction
shared = previous.shared

RELEASE = "am9-local-backup-receiver-20261028.1"
PARENT_RELEASE = previous.RELEASE
WORKER = ".config/scripts/coreelec-backup.sh"
RECEIPT = ".config/am9-local-backup-receiver-release.json"
BEFORE = "bb2b0dea4bc1d3acacec305514417e52119b8566554744aaad928466d4cf48cd"
AFTER = "d063c27e77590ffd45d900ad968b33bbf4b7cc723ce0d25b555e0301adae8842"
OVERLAY_SHA256 = "258665cceaebda7d9ff079493618873a3353587a4d4076cd0791d57a6db66f3a"
OVERLAY_COMMIT = "7e66165e715658dc84071ea7476ea05956e8690a"
SHA = re.compile(r"[0-9a-f]{64}\Z")
EVIDENCE_PROFILE_KEYS = {
    "local_backup_receiver_evidence_sha256",
    "local_backup_receiver_installer_receipt_sha256",
    "local_backup_receiver_receipt_sha256",
}
EVIDENCE_KEYS = {
    "schema",
    "record",
    "cohort",
    "hostname",
    "wlan_mac",
    "worker_sha256",
    "installer_status",
    "installer_receipt_sha256",
    "service_result",
    "service_exit_status",
    "service_started_at",
    "service_finished_at",
    "destination_last_success_at",
    "backed_up_worker_sha256",
    "sqlite_quick_checks",
    "recorded_at",
}
RECEIPT_KEYS = {
    "schema",
    "release",
    "cohort",
    "parent_release",
    "parent_receipt_sha256",
    "previous_worker_sha256",
    "worker_sha256",
    "overlay_sha256",
    "overlay_commit",
    "acceptance",
    "evidence_sha256",
    "installer_receipt_sha256",
    "destination_last_success_at",
    "sqlite_quick_checks",
    "accepted_at",
}
MAX_EVIDENCE_BYTES = 64 * 1024
MAX_EVIDENCE_AGE = 24 * 60 * 60
MAX_SERVICE_SECONDS = 15 * 60
MAX_RECORDING_DELAY = 15 * 60


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def private_bytes(path: Path, label: str, limit: int = MAX_EVIDENCE_BYTES) -> bytes:
    """Read one owner-private regular file through a no-follow descriptor."""
    try:
        require(path.is_absolute() and path.resolve(strict=True) == path,
                "Unsafe private " + label)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            info = os.fstat(descriptor)
            require(
                stat.S_ISREG(info.st_mode)
                and info.st_nlink == 1
                and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) & 0o077 == 0
                and 0 < info.st_size <= limit,
                "Unsafe private " + label,
            )
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                raw = stream.read(limit + 1)
            require(0 < len(raw) <= limit and len(raw) == info.st_size,
                    "Unsafe private " + label)
            return raw
        finally:
            os.close(descriptor)
    except (OSError, RuntimeError) as exc:
        raise ValueError("Unsafe private " + label) from exc


def profile_hash(profile: dict, key: str) -> str:
    value = profile.get(key)
    require(isinstance(value, str) and SHA.fullmatch(value) is not None,
            "Missing exact private acceptance hash: " + key)
    return value


def parse_time(value: object, label: str) -> int:
    require(isinstance(value, str) and value.endswith("Z"), "Invalid " + label)
    try:
        parsed = datetime.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("Invalid " + label) from exc
    require(parsed.tzinfo is not None, "Invalid " + label)
    return int(parsed.timestamp())


def parent_receipt(root: Path, parent) -> bytes:
    path = shared.regular(root, previous.RECEIPT)
    raw = path.read_bytes()
    require(parent.expected.get(path) == raw,
            "Parent receipt is outside the complete expected snapshot")
    return raw


def validate_private_evidence(path: Path, profile: dict, now: int) -> tuple[dict, str]:
    raw = private_bytes(path, "acceptance evidence")
    evidence_hash = profile_hash(profile, "local_backup_receiver_evidence_sha256")
    require(sha(raw) == evidence_hash, "Private acceptance evidence hash drift")
    try:
        evidence = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed private acceptance evidence") from exc
    require(isinstance(evidence, dict) and set(evidence) == EVIDENCE_KEYS,
            "Unexpected private acceptance evidence schema")
    require(canonical(evidence) == raw,
            "Private acceptance evidence is not canonical")
    require(
        type(evidence["schema"]) is int
        and evidence["schema"] == 1
        and evidence["record"] == "coreelec-local-backup-receiver-acceptance"
        and evidence["cohort"] == "local"
        and evidence["hostname"] == profile.get("hostname")
        and str(evidence["wlan_mac"]).lower() == str(profile.get("wlan_mac")).lower(),
        "Private acceptance evidence belongs to another appliance",
    )
    require(
        evidence["worker_sha256"] == AFTER
        and evidence["backed_up_worker_sha256"] == AFTER
        and evidence["installer_status"] == "installed-backup-acceptance-pending"
        and evidence["installer_receipt_sha256"]
        == profile_hash(profile, "local_backup_receiver_installer_receipt_sha256"),
        "Private acceptance evidence is not bound to the reviewed install",
    )
    require(
        evidence["service_result"] == "success"
        and type(evidence["service_exit_status"]) is int
        and evidence["service_exit_status"] == 0,
        "Backup service did not complete successfully",
    )
    checks = evidence["sqlite_quick_checks"]
    require(
        isinstance(checks, dict)
        and set(checks) == {"count", "all_ok"}
        and type(checks["count"]) is int
        and checks["count"] == 14
        and checks["all_ok"] is True,
        "Exactly fourteen SQLite quick checks did not pass",
    )
    started = parse_time(evidence["service_started_at"], "service start time")
    marker = parse_time(evidence["destination_last_success_at"], "destination status marker")
    finished = parse_time(evidence["service_finished_at"], "service finish time")
    recorded = parse_time(evidence["recorded_at"], "evidence recording time")
    require(
        started <= marker <= finished <= recorded <= now + 300
        and finished - started <= MAX_SERVICE_SECONDS
        and recorded - finished <= MAX_RECORDING_DELAY
        and 0 <= now - recorded <= MAX_EVIDENCE_AGE,
        "Acceptance evidence is stale or chronologically inconsistent",
    )
    return evidence, evidence_hash


def receipt_body(profile: dict, parent_raw: bytes, evidence: dict, evidence_hash: str) -> dict:
    return {
        "schema": 1,
        "release": RELEASE,
        "cohort": "local",
        "parent_release": PARENT_RELEASE,
        "parent_receipt_sha256": sha(parent_raw),
        "previous_worker_sha256": BEFORE,
        "worker_sha256": AFTER,
        "overlay_sha256": OVERLAY_SHA256,
        "overlay_commit": OVERLAY_COMMIT,
        "acceptance": "live-backup-verified",
        "evidence_sha256": evidence_hash,
        "installer_receipt_sha256": profile_hash(
            profile, "local_backup_receiver_installer_receipt_sha256"
        ),
        "destination_last_success_at": evidence["destination_last_success_at"],
        "sqlite_quick_checks": 14,
        "accepted_at": evidence["recorded_at"],
    }


def validate_final_receipt(raw: bytes, profile: dict, parent_raw: bytes) -> None:
    receipt_hash = profile_hash(profile, "local_backup_receiver_receipt_sha256")
    require(sha(raw) == receipt_hash, "Local backup receiver receipt hash drift")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed local backup receiver receipt") from exc
    require(isinstance(value, dict) and set(value) == RECEIPT_KEYS,
            "Unexpected local backup receiver receipt schema")
    require(canonical(value) == raw, "Local backup receiver receipt is not canonical")
    require(
        type(value["schema"]) is int
        and value["schema"] == 1
        and value["release"] == RELEASE
        and value["cohort"] == "local"
        and value["parent_release"] == PARENT_RELEASE
        and value["parent_receipt_sha256"] == sha(parent_raw)
        and value["previous_worker_sha256"] == BEFORE
        and value["worker_sha256"] == AFTER
        and value["overlay_sha256"] == OVERLAY_SHA256
        and value["overlay_commit"] == OVERLAY_COMMIT
        and value["acceptance"] == "live-backup-verified"
        and value["evidence_sha256"]
        == profile_hash(profile, "local_backup_receiver_evidence_sha256")
        and value["installer_receipt_sha256"]
        == profile_hash(profile, "local_backup_receiver_installer_receipt_sha256")
        and type(value["sqlite_quick_checks"]) is int
        and value["sqlite_quick_checks"] == 14,
        "Local backup receiver receipt content drift",
    )
    marker = parse_time(value["destination_last_success_at"], "receipt status marker")
    accepted = parse_time(value["accepted_at"], "receipt acceptance time")
    require(marker <= accepted, "Local backup receiver receipt chronology drift")


def plan(root: Path, profile: dict):
    """Validate the final additive state without proposing source installation."""
    parent = previous.plan(root, profile)
    receipt = shared.regular(root, RECEIPT)
    cohort = profile.get("cohort")
    if cohort == "remote":
        require(receipt not in parent.expected and receipt not in parent,
                "Parent release already owns local backup receiver receipt")
        require(not (EVIDENCE_PROFILE_KEYS & set(profile)),
                "Remote profile contains local acceptance material")
        require(not receipt.exists(), "Local-only backup receiver receipt exists remotely")
        parent.expected[receipt] = None
        return parent
    require(cohort == "local", "Unsupported backup receiver cohort")
    worker = shared.regular(root, WORKER)
    require(worker not in parent.expected and worker not in parent
            and receipt not in parent.expected and receipt not in parent,
            "Parent release already owns local backup receiver state")
    worker_raw = worker.read_bytes()
    require(sha(worker_raw) == AFTER, "Local backup receiver worker drift")
    parent.expected[worker] = worker_raw
    require(receipt.exists(), "Local backup receiver acceptance receipt is missing")
    receipt_raw = receipt.read_bytes()
    validate_final_receipt(receipt_raw, profile, parent_receipt(root, parent))
    parent.expected[receipt] = receipt_raw
    return parent


def acceptance_plan(root: Path, profile: dict, evidence_path: Path, now: int | None = None):
    """Prepare only the exact receipt after independently recorded live acceptance."""
    require(profile.get("cohort") == "local", "Acceptance recording is local-only")
    parent = previous.plan(root, profile)
    require(not parent, "Complete parent release is not yet converged")
    worker = shared.regular(root, WORKER)
    worker_raw = worker.read_bytes()
    require(sha(worker_raw) == AFTER, "Reviewed receiver-compatible worker is not installed")
    receipt = shared.regular(root, RECEIPT)
    require(worker not in parent.expected and worker not in parent
            and receipt not in parent.expected and receipt not in parent,
            "Parent release already owns local backup receiver state")
    require(not receipt.exists(), "Acceptance receipt already exists")
    evidence, evidence_hash = validate_private_evidence(
        evidence_path, profile, int(time.time()) if now is None else now
    )
    raw = canonical(receipt_body(profile, parent_receipt(root, parent), evidence, evidence_hash))
    require(
        sha(raw) == profile_hash(profile, "local_backup_receiver_receipt_sha256"),
        "Prepared acceptance receipt does not match the private reviewed digest",
    )
    # Retain every parent expected key/value exactly; own only the worker and
    # absent receipt preimage.  A separate reviewed recorder may consume this
    # plan, but this public layer never writes it or starts a service.
    parent.expected[worker] = worker_raw
    parent.expected[receipt] = None
    parent[receipt] = raw
    return parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/storage"))
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    profile = json.loads(private_bytes(args.profile, "profile"))
    changes = (
        acceptance_plan(args.root, profile, args.evidence)
        if args.evidence is not None
        else plan(args.root, profile)
    )
    print(json.dumps({
        "release": RELEASE,
        "cohort": profile.get("cohort"),
        "mode": "acceptance-plan-only" if args.evidence is not None else "plan-only",
        "changes": [str(path.relative_to(args.root)) for path in changes],
        "expected_count": len(changes.expected),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
