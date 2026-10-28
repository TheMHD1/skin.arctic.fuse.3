"""Guarded paired Arctic Fuse 3.4.10 release adapter.

The public command line remains plan-only.  ``apply_release`` and
``recover_release`` are deliberately injectable library seams for a separately
reviewed private controller.  They never run the generator: a complete private
generation evidence record must already exist before Kodi is stopped.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import time
import xml.etree.ElementTree as ET

import dependencies
import directory_transaction
import generation_evidence
import lifecycle
import overlay


HERE = Path(__file__).resolve().parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load reviewed parent release")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


latest = load("arctic3410_latest_parent", HERE.parent / "local-backup-receiver" / "install.py")
base = latest.previous
transaction = base.transaction

RELEASE = "arctic-3.4.10-paired.2"
PARENT_RELEASE = latest.RELEASE
SKIN = Path("addons/skin.arctic.fuse.3")
SKIN_RELATIVE = ".kodi/addons/skin.arctic.fuse.3"
RECEIPT = ".config/am9-arctic-3410-release.json"
PROTECTED = (
    "userdata/addon_data/skin.arctic.fuse.3",
    "userdata/addon_data/script.skinvariables",
    "userdata/addon_data/plugin.video.themoviedb.helper",
    "userdata/guisettings.xml",
)
EVIDENCE_PROFILE_KEY = "arctic3410_generation_evidence_sha256"
RECEIPT_PROFILE_KEY = "arctic3410_release_receipt_sha256"
HISTORICAL_SKIN_COUNT = 16
HISTORICAL_SKIN_SHA256 = "d3bd5dafeb9a7e25dbc894589fc8249e6d13c36aaa8a74c3db1efb193787417d"
SHA = re.compile(r"[0-9a-f]{64}\Z")
RECEIPT_SCHEMA = 1
RECEIPT_KEYS = {
    "schema", "release", "cohort", "parent_release", "parent_manifest_sha256",
    "parent_snapshot", "parent_snapshot_sha256", "historical_skin_count",
    "historical_skin_sha256", "source_skin_sha256", "stage_record_sha256",
    "upstream_commit", "tmdbhelper", "candidate_skin_sha256",
    "generation_evidence_sha256", "generated_skin_sha256", "generated_files",
    "menu_inputs", "runtime_dependencies", "profile_identity_sha256",
    "generation_tool_sha256", "adapter_tool_sha256", "acceptance",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(Path(path).read_bytes())


def canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def compact_canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def version(path: Path) -> str | None:
    return ET.fromstring(Path(path).read_bytes()).get("version")


def profile_hash(profile: dict, key: str) -> str:
    value = profile.get(key)
    require(isinstance(value, str) and SHA.fullmatch(value) is not None,
            "Missing exact private Arctic hash: " + key)
    return value


def _relative(root: Path, path: Path) -> str:
    root, path = Path(root).resolve(), Path(path).resolve()
    require(path == root or root in path.parents, "Parent evidence escaped storage root")
    relative = str(path.relative_to(root))
    require(relative and relative != ".", "Invalid parent evidence path")
    return relative


def _regular(root: Path, relative: str) -> Path:
    value = PurePosixPath(relative)
    require(not value.is_absolute() and value.parts and ".." not in value.parts,
            "Unsafe receipt path")
    current = Path(root)
    for component in value.parts:
        current = current / component
        require(not current.is_symlink(), "Symlink in guarded receipt path: " + relative)
    return current


def _snapshot_map(root: Path, expected: dict[Path, bytes | None]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for path, payload in expected.items():
        relative = _relative(root, path)
        require(relative not in result, "Duplicate parent evidence path")
        require(payload is None or isinstance(payload, bytes), "Invalid parent expected payload")
        result[relative] = None if payload is None else sha_bytes(payload)
    require(result, "Parent cohort preflight produced no evidence")
    return dict(sorted(result.items()))


def _snapshot_hash(snapshot: dict[str, str | None]) -> str:
    return sha_bytes(canonical(snapshot))


def _skin_manifest(raw: bytes) -> dict[str, str]:
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed immutable parent manifest") from exc
    files = manifest.get("files")
    require(isinstance(files, dict), "Immutable parent manifest lacks files")
    prefix = "addons/skin.arctic.fuse.3/"
    subset = {name: digest for name, digest in files.items() if name.startswith(prefix)}
    require(len(subset) == HISTORICAL_SKIN_COUNT, "Unexpected historical skin manifest cardinality")
    for name, digest in subset.items():
        require(isinstance(name, str) and isinstance(digest, str)
                and SHA.fullmatch(digest) is not None,
                "Invalid historical skin manifest entry")
    require(sha_bytes(compact_canonical(dict(sorted(subset.items()))))
            == HISTORICAL_SKIN_SHA256,
            "Historical skin manifest projection drift")
    return dict(sorted(subset.items()))


def _stage_record(stage: Path) -> tuple[dict, bytes]:
    path = Path(stage).resolve() / "stage.json"
    require(path.is_file() and not path.is_symlink(), "Missing schema-3 stage record")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed schema-3 stage record") from exc
    required = {
        "schema", "upstream_commit", "tmdbhelper", "source_skin_sha256",
        "source_resume_receipt_sha256", "candidate_skin_sha256", "rollback",
    }
    require(isinstance(value, dict) and required.issubset(value),
            "Incomplete schema-3 stage record")
    require(value["schema"] == 3 and value["upstream_commit"] == overlay.UPSTREAM_COMMIT,
            "Unreviewed candidate stage provenance")
    for key in ("source_skin_sha256", "source_resume_receipt_sha256",
                "candidate_skin_sha256"):
        require(isinstance(value.get(key), str) and SHA.fullmatch(value[key]) is not None,
                "Invalid schema-3 stage hash")
    dependencies.require_reviewed_binding(value["tmdbhelper"])
    return value, raw


def _adapter_tool_hashes(tool_root: Path = HERE) -> dict[str, str]:
    result = {}
    for name in ("install.py", "directory_transaction.py", "lifecycle.py",
                 "generation_evidence.py"):
        path = Path(tool_root).resolve() / name
        require(path.is_file() and not path.is_symlink(), "Missing Arctic adapter source: " + name)
        result[name] = sha(path)
    return result


def canonical_parent_plan(storage_root: Path, profile: dict):
    return latest.plan(Path(storage_root), profile)


def plan(storage_root: Path, stage: Path, profile: dict,
         parent_guard=canonical_parent_plan):
    """Validate the complete accepted parent and exact pre-upgrade source."""
    storage_root, stage = Path(storage_root).resolve(), Path(stage).resolve()
    require(storage_root.is_absolute() and not storage_root.is_symlink(), "Unsafe storage root")
    parent = parent_guard(storage_root, profile)
    require(hasattr(parent, "expected") and parent.expected, "Missing canonical parent evidence")
    require(not parent, "Canonical parent release has pending changes")
    root = storage_root / ".kodi"
    skin = root / SKIN
    receipt = root / "addons/plugin.video.habibi.resume/verified-build.json"
    record, _ = _stage_record(stage)
    require(skin.is_dir() and not skin.is_symlink()
            and version(skin / "addon.xml") == "3.3.1",
            "Unreviewed current Arctic cohort")
    require(directory_transaction.tree_hash(skin) == record["source_skin_sha256"]
            and sha(receipt) == record["source_resume_receipt_sha256"],
            "Staged source or resume receipt drift")
    require(version(root / "addons/script.skinvariables/addon.xml") == "2.2.10",
            "Dependency drift: script.skinvariables")
    binding = dependencies.require_reviewed_binding(record["tmdbhelper"])
    dependencies.review_live_tmdb(root / "addons" / dependencies.TMDB_ID, binding)
    candidate = stage / "candidate" / SKIN
    require(candidate.is_dir() and not candidate.is_symlink()
            and version(candidate / "addon.xml") == "3.4.10"
            and directory_transaction.tree_hash(candidate) == record["candidate_skin_sha256"],
            "Invalid staged candidate")
    manifest_path = storage_root / base.MANIFEST
    manifest_raw = manifest_path.read_bytes()
    require(sha_bytes(manifest_raw) == base.FINAL[profile["cohort"]],
            "Immutable parent manifest digest drift")
    _skin_manifest(manifest_raw)
    return transaction.Plan({skin: candidate}, dict(parent.expected))


def _current_menu_inputs(storage_root: Path, names: dict[str, str]) -> dict[str, str]:
    result = {}
    for relative, expected in names.items():
        require(isinstance(relative, str) and isinstance(expected, str)
                and SHA.fullmatch(expected) is not None,
                "Invalid generation menu-input binding")
        path = _regular(Path(storage_root) / ".kodi", relative)
        require(path.is_dir() and not path.is_symlink(), "Missing live generation menu input")
        result[relative] = directory_transaction.tree_hash(path)
    return dict(sorted(result.items()))


def _receipt_body(*, storage_root: Path, stage: Path, profile: dict, parent,
                  evidence: dict, evidence_sha256: str, adapter_tool_root: Path) -> dict:
    record, stage_raw = _stage_record(stage)
    parent_snapshot = _snapshot_map(storage_root, parent.expected)
    manifest_raw = (Path(storage_root) / base.MANIFEST).read_bytes()
    return {
        "schema": RECEIPT_SCHEMA,
        "release": RELEASE,
        "cohort": profile["cohort"],
        "parent_release": PARENT_RELEASE,
        "parent_manifest_sha256": sha_bytes(manifest_raw),
        "parent_snapshot": parent_snapshot,
        "parent_snapshot_sha256": _snapshot_hash(parent_snapshot),
        "historical_skin_count": HISTORICAL_SKIN_COUNT,
        "historical_skin_sha256": HISTORICAL_SKIN_SHA256,
        "source_skin_sha256": record["source_skin_sha256"],
        "stage_record_sha256": sha_bytes(stage_raw),
        "upstream_commit": record["upstream_commit"],
        "tmdbhelper": record["tmdbhelper"],
        "candidate_skin_sha256": record["candidate_skin_sha256"],
        "generation_evidence_sha256": evidence_sha256,
        "generated_skin_sha256": evidence["generated_skin_sha256"],
        "generated_files": evidence["generated_files"],
        "menu_inputs": evidence["menu_inputs"],
        "runtime_dependencies": evidence["runtime_dependencies"],
        "profile_identity_sha256": evidence["profile_identity_sha256"],
        "generation_tool_sha256": evidence["tool_sha256"],
        "adapter_tool_sha256": _adapter_tool_hashes(adapter_tool_root),
        "acceptance": "live-skin-loaded-inprocess-and-source-guarded",
    }


class DeploymentPlan:
    def __init__(self, *, storage_root: Path, target: Path, generated: Path,
                 receipt_path: Path, receipt_raw: bytes, parent, evidence: dict,
                 bindings: dict[str, str]):
        self.storage_root = storage_root
        self.target = target
        self.generated = generated
        self.receipt_path = receipt_path
        self.receipt_raw = receipt_raw
        self.parent = parent
        self.evidence = evidence
        self.bindings = bindings

    @property
    def fingerprint(self) -> str:
        return sha_bytes(self.receipt_raw)


def deployment_plan(storage_root: Path, stage: Path, profile: dict,
                    generated_skin: Path, evidence_path: Path,
                    runtime_dependencies: dict[str, str], *,
                    parent_guard=canonical_parent_plan,
                    adapter_tool_root: Path = HERE) -> DeploymentPlan:
    """Bind one exact generated tree to a complete, unchanged parent snapshot."""
    storage_root, stage = Path(storage_root).resolve(), Path(stage).resolve()
    generated_skin = Path(generated_skin).resolve()
    preinstall = plan(storage_root, stage, profile, parent_guard)
    evidence_sha = profile_hash(profile, EVIDENCE_PROFILE_KEY)
    evidence = generation_evidence.validate(
        Path(evidence_path), evidence_sha, stage=stage, generated_skin=generated_skin,
        profile=profile, tool_root=adapter_tool_root,
    )
    require(evidence["runtime_dependencies"] == dict(sorted(runtime_dependencies.items())),
            "Runtime dependency closure changed after generation")
    require(_current_menu_inputs(storage_root, evidence["menu_inputs"])
            == evidence["menu_inputs"], "Live menu inputs changed after generation")
    target, _candidate = next(iter(preinstall.items()))
    receipt_path = _regular(storage_root, RECEIPT)
    require(not receipt_path.exists(), "Arctic release receipt already exists")
    receipt_temporary = receipt_path.with_name(receipt_path.name + ".arctic3410-tmp")
    require(not receipt_temporary.exists() and not receipt_temporary.is_symlink(),
            "Interrupted Arctic receipt write requires recovery")
    body = _receipt_body(storage_root=storage_root, stage=stage, profile=profile,
                         parent=preinstall, evidence=evidence,
                         evidence_sha256=evidence_sha, adapter_tool_root=adapter_tool_root)
    raw = canonical(body)
    expected_receipt = profile_hash(profile, RECEIPT_PROFILE_KEY)
    require(sha_bytes(raw) == expected_receipt,
            "Prepared Arctic receipt does not match private reviewed digest")
    bindings = {
        "release": RELEASE,
        "stage_record_sha256": body["stage_record_sha256"],
        "generation_evidence_sha256": evidence_sha,
        "release_receipt_sha256": expected_receipt,
        "parent_snapshot_sha256": body["parent_snapshot_sha256"],
        "live_proof_nonce": sha_bytes(raw + b"\0live-proof"),
    }
    return DeploymentPlan(storage_root=storage_root, target=target,
                          generated=generated_skin, receipt_path=receipt_path,
                          receipt_raw=raw, parent=preinstall, evidence=evidence,
                          bindings=bindings)


def _read_receipt(path: Path, profile: dict) -> tuple[dict, bytes]:
    require(path.is_file() and not path.is_symlink(), "Arctic release receipt is missing")
    info = path.stat(follow_symlinks=False)
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o600 and 0 < info.st_size <= 1024 * 1024,
            "Arctic release receipt metadata is unsafe")
    raw = path.read_bytes()
    require(sha_bytes(raw) == profile_hash(profile, RECEIPT_PROFILE_KEY),
            "Arctic release receipt hash drift")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed Arctic release receipt") from exc
    require(isinstance(value, dict) and set(value) == RECEIPT_KEYS
            and canonical(value) == raw, "Unexpected Arctic release receipt schema")
    require(value["schema"] == RECEIPT_SCHEMA and value["release"] == RELEASE
            and value["cohort"] == profile.get("cohort")
            and value["parent_release"] == PARENT_RELEASE
            and value["historical_skin_count"] == HISTORICAL_SKIN_COUNT
            and value["historical_skin_sha256"] == HISTORICAL_SKIN_SHA256
            and value["acceptance"] == "live-skin-loaded-inprocess-and-source-guarded",
            "Arctic release receipt identity drift")
    return value, raw


def _actual_parent_payload(storage_root: Path, old_skin: Path,
                           relative: str) -> bytes | None:
    prefix = SKIN_RELATIVE + "/"
    if relative.startswith(prefix):
        path = _regular(old_skin, relative[len(prefix):])
    else:
        path = _regular(storage_root, relative)
    if not path.exists():
        return None
    require(path.is_file() and not path.is_symlink(), "Parent projection is not a regular file")
    return path.read_bytes()


def _validate_parent_projection(storage_root: Path, old_skin: Path,
                                receipt: dict) -> dict[Path, bytes | None]:
    snapshot = receipt["parent_snapshot"]
    require(isinstance(snapshot, dict) and snapshot
            and _snapshot_hash(snapshot) == receipt["parent_snapshot_sha256"],
            "Parent snapshot receipt drift")
    expected: dict[Path, bytes | None] = {}
    for relative, digest in snapshot.items():
        require(isinstance(relative, str)
                and (digest is None or isinstance(digest, str) and SHA.fullmatch(digest)),
                "Invalid parent snapshot member")
        payload = _actual_parent_payload(storage_root, old_skin, relative)
        require((None if payload is None else sha_bytes(payload)) == digest,
                "Accepted parent source drift: " + relative)
        expected[_regular(storage_root, relative)] = payload
    manifest_path = _regular(storage_root, base.MANIFEST)
    manifest_raw = manifest_path.read_bytes()
    require(sha_bytes(manifest_raw) == base.FINAL[receipt["cohort"]]
            == receipt["parent_manifest_sha256"],
            "Immutable parent manifest changed after Arctic upgrade")
    subset = _skin_manifest(manifest_raw)
    for name, digest in subset.items():
        relative = name[len("addons/skin.arctic.fuse.3/"):]
        path = _regular(old_skin, relative)
        require(path.is_file() and sha(path) == digest,
                "Historical parent skin source drift: " + name)
    require(directory_transaction.tree_hash(old_skin) == receipt["source_skin_sha256"],
            "Full preserved 3.3.1 skin drift")
    return expected


def installed_plan(storage_root: Path, stage: Path, profile: dict,
                   generated_skin: Path, evidence_path: Path,
                   *, adapter_tool_root: Path = HERE):
    """Validate an accepted 3.4.10 state without rewriting old manifests."""
    storage_root, stage = Path(storage_root).resolve(), Path(stage).resolve()
    root = storage_root / ".kodi"
    target = root / SKIN
    receipt_path = _regular(storage_root, RECEIPT)
    receipt, raw = _read_receipt(receipt_path, profile)
    record, stage_raw = _stage_record(stage)
    require(receipt["stage_record_sha256"] == sha_bytes(stage_raw)
            and receipt["upstream_commit"] == record["upstream_commit"]
            and receipt["tmdbhelper"] == record["tmdbhelper"]
            and receipt["source_skin_sha256"] == record["source_skin_sha256"]
            and receipt["candidate_skin_sha256"] == record["candidate_skin_sha256"],
            "Accepted stage binding drift")
    evidence_sha = profile_hash(profile, EVIDENCE_PROFILE_KEY)
    evidence = generation_evidence.validate(
        Path(evidence_path), evidence_sha, stage=stage,
        generated_skin=Path(generated_skin), profile=profile, tool_root=adapter_tool_root,
    )
    require(receipt["generation_evidence_sha256"] == evidence_sha
            and receipt["generated_skin_sha256"] == evidence["generated_skin_sha256"]
            and receipt["generated_files"] == evidence["generated_files"]
            and receipt["menu_inputs"] == evidence["menu_inputs"]
            and receipt["runtime_dependencies"] == evidence["runtime_dependencies"]
            and receipt["profile_identity_sha256"] == evidence["profile_identity_sha256"]
            and receipt["generation_tool_sha256"] == evidence["tool_sha256"]
            and receipt["adapter_tool_sha256"] == _adapter_tool_hashes(adapter_tool_root),
            "Accepted generation/source binding drift")
    require(target.is_dir() and not target.is_symlink()
            and version(target / "addon.xml") == "3.4.10"
            and directory_transaction.tree_hash(target) == receipt["generated_skin_sha256"],
            "Accepted live Arctic tree drift")
    for relative, digest in receipt["generated_files"].items():
        require(sha(_regular(target, relative)) == digest,
                "Accepted generated selector drift: " + relative)
    active = directory_transaction.load(target)
    state = active["state"]
    proof_nonce = sha_bytes(raw + b"\0live-proof")
    lifecycle.validate_live_skin_proof(active["root"], proof_nonce, target)
    _proof_script, proof_receipt = lifecycle._live_proof_paths(active["root"], proof_nonce)
    proof_receipt_sha = sha(proof_receipt)
    expected_bindings = {
        "release": RELEASE,
        "stage_record_sha256": receipt["stage_record_sha256"],
        "generation_evidence_sha256": receipt["generation_evidence_sha256"],
        "release_receipt_sha256": sha_bytes(raw),
        "parent_snapshot_sha256": receipt["parent_snapshot_sha256"],
        "live_proof_nonce": proof_nonce,
        "live_proof_receipt_sha256": proof_receipt_sha,
        "accepted_receipt_sha256": sha_bytes(raw),
    }
    require(state["phase"] == "accepted" and state["candidate_sha256"] == receipt["generated_skin_sha256"]
            and state["old_sha256"] == receipt["source_skin_sha256"]
            and state["bindings"] == expected_bindings,
            "Accepted recovery journal drift")
    expected = _validate_parent_projection(storage_root, active["old"], receipt)
    expected[receipt_path] = raw
    return transaction.Plan({}, expected)


def _atomic_write(path: Path, payload: bytes, mode: int = 0o600) -> None:
    path = Path(path)
    require(path.parent.is_dir() and not path.parent.is_symlink(), "Unsafe receipt parent")
    temporary = path.with_name(path.name + ".arctic3410-tmp")
    require(not path.exists() and not temporary.exists(), "Receipt path is not new")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_exact_receipt(path: Path, expected: bytes) -> None:
    if not path.exists():
        return
    require(path.is_file() and not path.is_symlink() and path.read_bytes() == expected,
            "Refusing to remove changed Arctic receipt")
    path.unlink()
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def _quarantine_receipt_temporary(receipt_path: Path, recovery_root: Path) -> Path | None:
    temporary = receipt_path.with_name(receipt_path.name + ".arctic3410-tmp")
    if not temporary.exists() and not temporary.is_symlink():
        return None
    require(not temporary.is_symlink() and temporary.is_file(),
            "Unsafe interrupted Arctic receipt temporary")
    info = temporary.stat(follow_symlinks=False)
    require(info.st_nlink == 1 and info.st_uid == os.geteuid()
            and not stat.S_IMODE(info.st_mode) & 0o077
            and info.st_size <= 1024 * 1024,
            "Unsafe interrupted Arctic receipt temporary metadata")
    payload = temporary.read_bytes()
    evidence = Path(recovery_root) / "interrupted-receipts"
    evidence.mkdir(mode=0o700, exist_ok=True)
    destination = evidence / (sha_bytes(payload) + ".json.partial")
    if destination.exists():
        require(not destination.is_symlink() and destination.is_file()
                and destination.read_bytes() == payload,
                "Interrupted Arctic receipt evidence collision")
        temporary.unlink()
    else:
        os.replace(temporary, destination)
    for directory in (evidence, Path(recovery_root), temporary.parent):
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return destination


def _send_live_proof(run, script: Path, kodi_send: Path = Path("/usr/bin/kodi-send")) -> None:
    require(kodi_send == Path("/usr/bin/kodi-send") and kodi_send.is_file()
            and not kodi_send.is_symlink(), "Refusing nonstandard kodi-send")
    run([str(kodi_send), "--action=RunScript(" + str(script) + ")"], check=True,
        timeout=10, capture_output=True, text=True)


def _durable_proof_hash(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), "Live proof receipt is missing")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                         | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(descriptor)
        payload = os.read(descriptor, 4097)
    finally:
        os.close(descriptor)
    require(0 < len(payload) <= 4096, "Live proof receipt size is unsafe")
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    return sha_bytes(payload)


def _run_unit(run, action: str) -> None:
    run(["systemctl", action, "kodi"], check=True, timeout=45)


def _unit_state(run=subprocess.run) -> str:
    result = run(["systemctl", "show", "kodi", "--property=ActiveState", "--value"],
                 check=True, timeout=5, capture_output=True, text=True)
    state = result.stdout.strip()
    require(state in {"active", "inactive"}, "Kodi unit is in an ambiguous state")
    return state


def apply_release(storage_root: Path, stage: Path, profile: dict,
                  generated_skin: Path, evidence_path: Path,
                  runtime_dependencies: dict[str, str], *,
                  hostname_reader=None, mac_reader=None, run=subprocess.run,
                  parent_guard=canonical_parent_plan,
                  idle_func=lifecycle.idle, wait_stopped_func=lifecycle.wait_stopped,
                  ready_func=lifecycle.ready, send_proof=_send_live_proof,
                  proof_writer=lifecycle.write_live_skin_proof_script,
                  proof_reuser=lambda root, nonce: lifecycle.write_live_skin_proof_script(
                      root, nonce, reuse=True),
                  proof_resetter=lifecycle.reset_live_skin_proof_receipt,
                  proof_recovery_resetter=lifecycle.recover_live_skin_proof_receipt,
                  proof_waiter=lifecycle.wait_live_skin_proof,
                  writer=_atomic_write, stability_sleeper=time.sleep,
                  stability_seconds: float = 3.0, adapter_tool_root: Path = HERE):
    """Apply one reviewed generated tree with durable rollback and acceptance."""
    storage_root = Path(storage_root).resolve()
    root = storage_root / ".kodi"
    hostname_reader = hostname_reader or (lambda: lifecycle.appliance_hostname(storage_root))
    mac_reader = mac_reader or lifecycle.appliance_mac
    lifecycle.identity(root, profile, hostname_reader(), mac_reader())
    initial = deployment_plan(storage_root, stage, profile, generated_skin, evidence_path,
                              runtime_dependencies, parent_guard=parent_guard,
                              adapter_tool_root=adapter_tool_root)
    idle_func()
    active = None
    transaction_started = False
    proof_script = None
    proof_nonce = None
    try:
        _run_unit(run, "stop")
        wait_stopped_func()
        lifecycle.identity(root, profile, hostname_reader(), mac_reader())
        refreshed = deployment_plan(storage_root, stage, profile, generated_skin, evidence_path,
                                    runtime_dependencies, parent_guard=parent_guard,
                                    adapter_tool_root=adapter_tool_root)
        require(refreshed.fingerprint == initial.fingerprint
                and refreshed.bindings == initial.bindings,
                "Arctic deployment inputs changed while Kodi stopped")
        transaction_started = True
        active = directory_transaction.prepare(
            refreshed.target, refreshed.generated, PROTECTED,
            recovery_root=root / ".arctic3410-recovery", bindings=refreshed.bindings,
        )
        final_pre_switch = deployment_plan(
            storage_root, stage, profile, generated_skin, evidence_path,
            runtime_dependencies, parent_guard=parent_guard,
            adapter_tool_root=adapter_tool_root)
        require(final_pre_switch.fingerprint == initial.fingerprint
                and final_pre_switch.bindings == initial.bindings,
                "Arctic deployment inputs changed while preparing rollback")
        directory_transaction.switch(active)
        proof_nonce = refreshed.bindings["live_proof_nonce"]
        proof_script, proof_receipt = proof_writer(active["root"], proof_nonce)
        _run_unit(run, "start")
        ready_func()
        send_proof(run, proof_script)
        proof_waiter(active["root"], proof_nonce, refreshed.target)
        stability_sleeper(stability_seconds)
        proof_resetter(active["root"], proof_nonce)
        send_proof(run, proof_script)
        proof_waiter(active["root"], proof_nonce, refreshed.target)
        proof_receipt_sha = _durable_proof_hash(proof_receipt)
        require(directory_transaction.tree_hash(refreshed.target)
                == refreshed.evidence["generated_skin_sha256"],
                "Live skin changed during startup verification")
        writer(refreshed.receipt_path, refreshed.receipt_raw, 0o600)
        directory_transaction.accept(
            active, refreshed.fingerprint,
            {"live_proof_receipt_sha256": proof_receipt_sha})
        installed_plan(storage_root, stage, profile, generated_skin, evidence_path,
                       adapter_tool_root=adapter_tool_root)
        return {"release": RELEASE, "cohort": profile["cohort"],
                "receipt_sha256": refreshed.fingerprint,
                "journal": str(active["journal"]), "status": "accepted"}
    except BaseException as failure:
        recovery_errors = []
        stopped_verified = False
        receipt_removed = False
        rollback_complete = not transaction_started
        try:
            _run_unit(run, "stop")
            wait_stopped_func()
            stopped_verified = True
        except BaseException as exc:
            recovery_errors.append("stop: " + repr(exc))
        if stopped_verified:
            try:
                _remove_exact_receipt(initial.receipt_path, initial.receipt_raw)
                receipt_removed = True
            except BaseException as exc:
                recovery_errors.append("receipt: " + repr(exc))
            if transaction_started and receipt_removed:
                try:
                    active = directory_transaction.load(
                        initial.target, root / ".arctic3410-recovery", allow_temporary=True)
                    if active["state"]["phase"] == "rolled-back":
                        require(directory_transaction.tree_hash(initial.target)
                                == active["state"]["old_sha256"],
                                "rolled-back skin drift after preparation failure")
                    else:
                        directory_transaction.rollback(active, allow_accepted=True)
                    rollback_complete = True
                except BaseException as exc:
                    recovery_errors.append("rollback: " + repr(exc))
        else:
            recovery_errors.append("rollback withheld: Kodi stop is unproven")
        if stopped_verified and receipt_removed and rollback_complete:
            try:
                _run_unit(run, "start")
                ready_func()
                if active is not None:
                    proof_nonce = active["state"]["bindings"]["live_proof_nonce"]
                    proof_script, _receipt = proof_reuser(active["root"], proof_nonce)
                    proof_recovery_resetter(active["root"], proof_nonce)
                    send_proof(run, proof_script)
                    proof_waiter(active["root"], proof_nonce, initial.target, version="3.3.1")
                plan(storage_root, stage, profile, parent_guard)
            except BaseException as exc:
                recovery_errors.append("old-start: " + repr(exc))
        else:
            recovery_errors.append("old start withheld: rollback is not proven complete")
        if recovery_errors:
            raise RuntimeError("Arctic deployment/recovery failed; ALARM: "
                               + "; ".join(recovery_errors)) from failure
        raise RuntimeError("Arctic deployment failed; exact 3.3.1 state restored") from failure


def recover_release(storage_root: Path, stage: Path, profile: dict,
                    generated_skin: Path, evidence_path: Path, *,
                    run=subprocess.run, parent_guard=canonical_parent_plan,
                    idle_func=lifecycle.idle, wait_stopped_func=lifecycle.wait_stopped,
                    ready_func=lifecycle.ready, unit_state_func=None,
                    send_proof=_send_live_proof,
                    proof_reuser=lambda root, nonce: lifecycle.write_live_skin_proof_script(
                        root, nonce, reuse=True),
                    proof_recovery_resetter=lifecycle.recover_live_skin_proof_receipt,
                    proof_waiter=lifecycle.wait_live_skin_proof,
                    adapter_tool_root: Path = HERE):
    """Recover only this release's durable, unaccepted transaction."""
    storage_root = Path(storage_root).resolve()
    root, target = storage_root / ".kodi", storage_root / ".kodi" / SKIN
    active = directory_transaction.load(
        target, root / ".arctic3410-recovery", allow_temporary=True)
    if active["state"]["phase"] == "accepted":
        installed_plan(storage_root, stage, profile, generated_skin, evidence_path,
                       adapter_tool_root=adapter_tool_root)
        return {"status": "accepted-noop"}
    _quarantine_receipt_temporary(_regular(storage_root, RECEIPT), active["root"])
    if active["state"]["phase"] == "rolled-back":
        require(not _regular(storage_root, RECEIPT).exists(),
                "Rolled-back transaction still has an acceptance receipt")
        require(directory_transaction.tree_hash(target) == active["state"]["old_sha256"],
                "Rolled-back old skin drift")
        state = _unit_state(run) if unit_state_func is None else unit_state_func()
        require(state in {"active", "inactive"}, "Kodi unit is in an ambiguous state")
        if state == "inactive":
            _run_unit(run, "start")
        ready_func()
        nonce = active["state"]["bindings"].get("live_proof_nonce")
        require(isinstance(nonce, str) and SHA.fullmatch(nonce) is not None,
                "Recovery journal lacks exact live-proof nonce")
        script, _receipt = proof_reuser(active["root"], nonce)
        proof_recovery_resetter(active["root"], nonce)
        send_proof(run, script)
        proof_waiter(active["root"], nonce, target, version="3.3.1")
        plan(storage_root, stage, profile, parent_guard)
        return {"status": "rolled-back-noop"}
    state = _unit_state(run) if unit_state_func is None else unit_state_func()
    if state == "active":
        idle_func()
    else:
        require(state == "inactive", "Kodi unit is in an ambiguous state")
    _run_unit(run, "stop")
    try:
        wait_stopped_func()
        receipt = _regular(storage_root, RECEIPT)
        if receipt.exists():
            raw = receipt.read_bytes()
            require(sha_bytes(raw) == profile_hash(profile, RECEIPT_PROFILE_KEY),
                    "Foreign receipt blocks recovery")
            _remove_exact_receipt(receipt, raw)
        directory_transaction.rollback(active)
    except BaseException:
        raise RuntimeError("Arctic recovery failed; Kodi remains stopped; inspect durable journal")
    _run_unit(run, "start")
    ready_func()
    nonce = active["state"]["bindings"].get("live_proof_nonce")
    require(isinstance(nonce, str) and SHA.fullmatch(nonce) is not None,
            "Recovery journal lacks exact live-proof nonce")
    script, _receipt = proof_reuser(active["root"], nonce)
    proof_recovery_resetter(active["root"], nonce)
    send_proof(run, script)
    proof_waiter(active["root"], nonce, target, version="3.3.1")
    plan(storage_root, stage, profile, parent_guard)
    return {"status": "rolled-back"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", type=Path, default=Path("/storage"))
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_bytes())
    changes = plan(args.storage_root, args.stage, profile)
    print(json.dumps({
        "release": RELEASE,
        "cohort": profile.get("cohort"),
        "mode": "apply-disabled" if args.apply else "plan-only",
        "changes": [str(path.relative_to(args.storage_root)) for path in changes],
        "parent_expected_count": len(changes.expected),
    }, indent=2, sort_keys=True))
    if args.apply:
        raise SystemExit("apply remains disabled pending independent adapter review and private approval")


if __name__ == "__main__":
    main()
