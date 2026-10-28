"""Immutable evidence for one accepted isolated Arctic generation run."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import xml.etree.ElementTree as ET

import directory_transaction


SCHEMA = 1
RECORD = "arctic-3.4.10-isolated-generation"
EVIDENCE_NAME = "generation-evidence.json"
GENERATED = re.compile(r"1080i/script-skinvariables-generator-includes-[^/]+\.xml\Z")
IDENTITY_KEYS = (
    "cohort", "hostname", "wlan_mac", "jellyfin_user_id",
    "jellyfin_address", "remote_marker_sha256",
)
MARKERS = (
    b"skinvariables-searchwidgets-combined-selector-owned",
    b"skinvariables-searchwidgets-combined-selector-venom",
    b"skinvariables-searchwidgets-standard-selector-owned",
    b"skinvariables-searchwidgets-standard-selector-venom",
)
EVIDENCE_KEYS = {
    "schema", "record", "cohort", "profile_identity_sha256",
    "stage_record_sha256", "candidate_skin_sha256", "generated_skin_sha256",
    "generated_files", "menu_inputs", "runtime_dependencies", "tool_sha256",
}
MAX_EVIDENCE_BYTES = 256 * 1024


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(Path(path).read_bytes())


def canonical(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def identity_hash(profile: dict) -> str:
    require(profile.get("cohort") in {"local", "remote"}, "Invalid generation cohort")
    identity = {}
    for key in IDENTITY_KEYS:
        value = profile.get(key)
        if key == "remote_marker_sha256" and value is None:
            identity[key] = None
            continue
        require(isinstance(value, str) and value.strip(), "Missing generation identity field: " + key)
        identity[key] = value.lower() if key == "wlan_mac" else value
    return sha_bytes(canonical(identity))


def tool_hashes(tool_root: Path) -> dict[str, str]:
    root = Path(tool_root).resolve()
    result = {}
    for name in ("generation_probe.py", "generation_evidence.py"):
        path = root / name
        require(path.is_file() and not path.is_symlink(), "Missing generation tool source: " + name)
        result[name] = sha_file(path)
    return result


def _regular_tree(root: Path) -> dict[str, bytes]:
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "Unsafe generation tree")
    result = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "Symlink in generation tree")
        if path.is_dir():
            continue
        require(path.is_file(), "Special file in generation tree")
        result[str(path.relative_to(root))] = path.read_bytes()
    return result


def validate_generated_tree(candidate: Path, generated: Path) -> dict[str, str]:
    """Require candidate bytes plus only fresh, valid generator include files."""
    baseline = _regular_tree(candidate)
    final = _regular_tree(generated)
    generated_files = {}
    for relative, data in final.items():
        if GENERATED.fullmatch(relative):
            require(data, "Empty generated include")
            try:
                ET.fromstring(data)
            except ET.ParseError as exc:
                raise ValueError("Generated include is not XML: " + relative) from exc
            generated_files[relative] = sha_bytes(data)
        else:
            require(relative in baseline and baseline[relative] == data,
                    "Non-generated candidate file changed: " + relative)
    for relative, data in baseline.items():
        if GENERATED.fullmatch(relative):
            continue
        require(final.get(relative) == data, "Candidate file missing after generation: " + relative)
    require(generated_files, "No generated selector include was produced")
    combined = b"".join(final[name] for name in sorted(generated_files))
    for marker in MARKERS:
        require(marker in combined, "Generated selectors omit managed route: " + marker.decode())
    return dict(sorted(generated_files.items()))


def body(*, stage: Path, generated_skin: Path, profile: dict,
         menu_inputs: dict[str, str], runtime_dependencies: dict[str, str],
         tool_root: Path) -> dict:
    stage = Path(stage).resolve()
    record_path = stage / "stage.json"
    require(record_path.is_file() and not record_path.is_symlink(), "Missing schema-3 stage record")
    record = json.loads(record_path.read_bytes())
    require(record.get("schema") == 3, "Generation evidence requires schema-3 stage")
    candidate = stage / "candidate/addons/skin.arctic.fuse.3"
    candidate_hash = directory_transaction.tree_hash(candidate)
    require(candidate_hash == record.get("candidate_skin_sha256"), "Stage candidate drift")
    generated_files = validate_generated_tree(candidate, generated_skin)
    require(isinstance(menu_inputs, dict) and menu_inputs, "Missing generation menu inputs")
    require(isinstance(runtime_dependencies, dict) and runtime_dependencies,
            "Missing generation dependency closure")
    for mapping, label in ((menu_inputs, "menu input"),
                           (runtime_dependencies, "runtime dependency")):
        for name, digest in mapping.items():
            require(isinstance(name, str) and name and isinstance(digest, str)
                    and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                    "Invalid " + label + " hash")
    return {
        "schema": SCHEMA,
        "record": RECORD,
        "cohort": profile["cohort"],
        "profile_identity_sha256": identity_hash(profile),
        "stage_record_sha256": sha_file(record_path),
        "candidate_skin_sha256": candidate_hash,
        "generated_skin_sha256": directory_transaction.tree_hash(generated_skin),
        "generated_files": generated_files,
        "menu_inputs": dict(sorted(menu_inputs.items())),
        "runtime_dependencies": dict(sorted(runtime_dependencies.items())),
        "tool_sha256": tool_hashes(tool_root),
    }


def write(*, runtime_home: Path, stage: Path, generated_skin: Path, profile: dict,
          menu_inputs: dict[str, str], runtime_dependencies: dict[str, str],
          tool_root: Path) -> dict:
    runtime_home = Path(runtime_home).resolve()
    path = runtime_home / EVIDENCE_NAME
    require(runtime_home.name and path.parent == runtime_home and not path.exists(),
            "Generation evidence path is not new and private")
    value = body(stage=stage, generated_skin=generated_skin, profile=profile,
                 menu_inputs=menu_inputs, runtime_dependencies=runtime_dependencies,
                 tool_root=tool_root)
    payload = canonical(value)
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        parent = os.open(runtime_home, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": str(path), "sha256": sha_bytes(payload), "body": value}


def private_bytes(path: Path) -> bytes:
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path, "Unsafe generation evidence path")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0
                and 0 < info.st_size <= MAX_EVIDENCE_BYTES,
                "Unsafe generation evidence file")
        raw = os.read(descriptor, MAX_EVIDENCE_BYTES + 1)
        require(len(raw) == info.st_size, "Generation evidence changed while reading")
        return raw
    finally:
        os.close(descriptor)


def validate(path: Path, expected_sha256: str, *, stage: Path, generated_skin: Path,
             profile: dict, tool_root: Path) -> dict:
    require(isinstance(expected_sha256, str)
            and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
            "Missing exact generation evidence hash")
    raw = private_bytes(path)
    require(sha_bytes(raw) == expected_sha256, "Generation evidence hash drift")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed generation evidence") from exc
    require(isinstance(value, dict) and set(value) == EVIDENCE_KEYS,
            "Unexpected generation evidence schema")
    require(canonical(value) == raw, "Generation evidence is not canonical")
    rebuilt = body(stage=stage, generated_skin=generated_skin, profile=profile,
                   menu_inputs=value["menu_inputs"],
                   runtime_dependencies=value["runtime_dependencies"], tool_root=tool_root)
    require(rebuilt == value, "Generation evidence content drift")
    return value
