"""Guarded, isolated on-device SkinVariables generation probe.

The public CLI is deliberately dry-run by default.  ``--apply`` is a bounded
same-device Kodi session: it first proves the complete paired cohort and the
real appliance identity, refuses active playback, stops normal Kodi, and starts
only a directly-owned ``kodi.bin`` process using a newly-created minimal HOME.
It never invokes ``kodi.sh`` or writes into the active Kodi profile.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import time
import xml.etree.ElementTree as ET

import install
import lifecycle

SKIN_ID = "skin.arctic.fuse.3"
SKIN_PATH = Path("addons") / SKIN_ID
SKINVARIABLES = "script.skinvariables"
BUILTIN_PREFIXES = ("xbmc.", "kodi.")
FORBIDDEN_PREFIXES = ("service.", "repository.", "pvr.")
FORBIDDEN_IDS = {"plugin.video.jellyfin", "service.tailscale"}
GENERATOR = "RunScript(script.skinvariables,action=buildtemplate,force=true,no_reload=true)"
MAX_RUNTIME_SECONDS = 90
START_TIMEOUT_SECONDS = 35
GENERATION_TIMEOUT_SECONDS = 45
SAFE_MENU_INPUTS = (
    Path("userdata/addon_data/skin.arctic.fuse.3"),
    Path("userdata/addon_data/script.skinvariables"),
)
PATH_PROOF_SCHEMA = 1
PATH_PROOF_SCRIPT = "arctic3410-path-proof.py"
PATH_PROOF_RECEIPT_PREFIX = "arctic3410-path-proof-"
PATH_PROOF_RECEIPT_SUFFIX = ".json"
PATH_PROOF_TIMEOUT_SECONDS = 10
PATH_PROOF_MAX_BYTES = 4096
ADDONS_DATABASE_FILENAME = "Addons33.db"
ADDONS_DATABASE_SCHEMA = 33
SKIN_ACTIVATION_TIMEOUT_SECONDS = 20
REVIEWED_RESOURCES = {
    "resource.images.arctic.weather": {
        "version": "1.0.4",
        # Payload tree only; review-clone .git metadata is intentionally never
        # copied to the appliance staging package.
        "sha256": "c1d8f304c3d7caa499d74d47008c5e43de986b63b390a5f7dd546a603514d9b4",
    },
    "resource.images.arctic.splash": {
        "version": "1.1.0",
        "sha256": "9ade774d111debcb799200b46724b2d9bc5babfcbaf27bb6d866072fda1f6fbe",
    },
}


def _tree_hash(root: Path) -> str:
    """Hash a regular addon tree without silently following links."""
    return install.directory_transaction.tree_hash(root)


def _version(value: str) -> tuple[int, ...]:
    # Kodi add-ons commonly append build metadata such as ``+matrix.3``.
    # Comparison is deliberately limited to the numeric upstream portion.
    match = re.match(r"[0-9]+(?:\.[0-9]+)*", value)
    if not match:
        raise ValueError(f"unsupported addon version: {value!r}")
    return tuple(int(part) for part in match.group(0).split("."))


def _at_least(actual: str, minimum: str) -> bool:
    left, right = _version(actual), _version(minimum)
    length = max(len(left), len(right))
    return left + (0,) * (length - len(left)) >= right + (0,) * (length - len(right))


def _addon_metadata(path: Path) -> tuple[str, str, list[tuple[str, str, bool]]]:
    addon_xml = path / "addon.xml"
    if path.is_symlink() or not addon_xml.is_file() or addon_xml.is_symlink():
        raise ValueError(f"unsafe or incomplete addon: {path}")
    root = ET.fromstring(addon_xml.read_bytes())
    addon_id, version = root.get("id"), root.get("version")
    if not addon_id or not version or addon_id != path.name:
        raise ValueError(f"invalid addon metadata: {path}")
    imports = []
    requires = root.find("requires")
    if requires is not None:
        for item in requires.findall("import"):
            dependency, minimum = item.get("addon"), item.get("version", "0")
            if not dependency:
                raise ValueError(f"dependency without id: {path}")
            optional = item.get("optional", "false").strip().lower() == "true"
            imports.append((dependency, minimum, optional))
    return addon_id, version, imports


def _safe_addon_id(addon_id: str) -> None:
    if addon_id.startswith(FORBIDDEN_PREFIXES) or addon_id in FORBIDDEN_IDS:
        raise ValueError(f"runtime stage refuses service/repository addon: {addon_id}")


def reviewed_resources(root: Path | None) -> dict[str, Path]:
    """Accept only the two reviewed unpacked resource trees, never arbitrary ZIPs."""
    if root is None:
        return {}
    root = Path(root).resolve()
    result = {}
    for addon_id, pin in REVIEWED_RESOURCES.items():
        source = root / addon_id
        found_id, version, _ = _addon_metadata(source)
        if found_id != addon_id or version != pin["version"] or _tree_hash(source) != pin["sha256"]:
            raise ValueError(f"reviewed resource drift: {addon_id}")
        result[addon_id] = source
    return result


def _source_addon(addon_id: str, live_addons: Path, system_addons: Path,
                  reviewed: dict[str, Path]) -> Path:
    _safe_addon_id(addon_id)
    if addon_id in REVIEWED_RESOURCES:
        if addon_id not in reviewed:
            raise ValueError(f"required reviewed resource is not staged: {addon_id}")
        return reviewed[addon_id]
    candidates = (live_addons / addon_id, system_addons / addon_id)
    found = [candidate for candidate in candidates if candidate.is_dir()]
    if len(found) != 1:
        raise ValueError(f"missing or ambiguous dependency source: {addon_id}")
    return found[0]


def dependency_closure(candidate_skin: Path, live_addons: Path,
                       system_addons: Path, reviewed_root: Path | None = None) -> dict[str, Path]:
    """Resolve the exact non-builtin dependency closure needed to load the skin.

    The candidate skin itself is separate; every other addon is copied from an
    explicitly selected live or CoreELEC system addon directory.  No userdata,
    repositories, services, credentials, or unrelated plugin is admitted.
    """
    candidate_skin = Path(candidate_skin)
    addon_id, _, imports = _addon_metadata(candidate_skin)
    if addon_id != SKIN_ID:
        raise ValueError("candidate is not the Arctic Fuse skin")
    pending = list(imports)
    reviewed = reviewed_resources(reviewed_root)
    result: dict[str, Path] = {}
    while pending:
        dependency, minimum, optional = pending.pop()
        if dependency.startswith(BUILTIN_PREFIXES):
            continue
        try:
            _safe_addon_id(dependency)
        except ValueError:
            if optional:
                continue
            raise
        if dependency in result:
            _, installed, _ = _addon_metadata(result[dependency])
            if not _at_least(installed, minimum):
                raise ValueError(f"dependency version too old: {dependency}")
            continue
        try:
            source = _source_addon(dependency, Path(live_addons), Path(system_addons), reviewed)
        except ValueError:
            if optional:
                continue
            raise
        found_id, installed, imports = _addon_metadata(source)
        if found_id != dependency or not _at_least(installed, minimum):
            raise ValueError(f"dependency version too old: {dependency}")
        result[dependency] = source
        pending.extend(imports)
    if SKINVARIABLES not in result:
        raise ValueError("candidate skin did not resolve SkinVariables")
    return result


def _runtime_home(storage_root: Path, runtime_home: Path) -> Path:
    storage_root = Path(storage_root).resolve()
    runtime_home = Path(runtime_home)
    if not runtime_home.is_absolute() or runtime_home.is_symlink():
        raise ValueError("runtime HOME must be a new absolute non-symlink path")
    allowed_parent = storage_root / ".arctic3410-generation"
    # Deliberately inspect lexical components before resolve: a symlinked parent
    # could otherwise redirect supposedly isolated writes into live userdata.
    probe = runtime_home
    while probe != probe.parent:
        if probe.is_symlink():
            raise ValueError("runtime HOME has a symlinked ancestor")
        probe = probe.parent
    runtime_home = runtime_home.resolve()
    if runtime_home.parent != allowed_parent.resolve() or runtime_home.exists():
        raise ValueError("runtime HOME must be a new direct child of the private staging root")
    return runtime_home


def preflight(storage_root: Path, stage: Path, profile: dict,
              hostname_reader=None, mac_reader=None) -> dict[Path, Path]:
    """Perform the complete read-only parent/source/identity guard."""
    storage_root = Path(storage_root).resolve()
    root = storage_root / ".kodi"
    hostname_reader = hostname_reader or (lambda: lifecycle.appliance_hostname(storage_root))
    mac_reader = mac_reader or lifecycle.appliance_mac
    changes = install.plan(storage_root, stage, profile)
    lifecycle.identity(root, profile, hostname_reader(), mac_reader())
    return changes


def runtime_dependency_preflight(storage_root: Path, stage: Path,
                                system_addons: Path = Path("/usr/share/kodi/addons"),
                                reviewed_root: Path | None = None) -> dict[str, str]:
    """Verify the complete runtime dependency closure before Kodi is stopped."""
    storage_root, stage = Path(storage_root).resolve(), Path(stage).resolve()
    candidate = stage / "candidate" / SKIN_PATH
    closure = dependency_closure(candidate, storage_root / ".kodi/addons",
                                 Path(system_addons), reviewed_root)
    return {addon_id: _tree_hash(path) for addon_id, path in sorted(closure.items())}


def safe_menu_inputs(stage: Path) -> dict[Path, str]:
    """Verify the two staged, account-free inputs that define menu shape.

    The stage rollback was created from the exact current cohort.  We use its
    skin and SkinVariables data, never live userdata, and reject paths/content
    that resemble credentials.  The returned hashes are checked again after
    copying and become part of the private probe receipt.
    """
    stage = Path(stage).resolve()
    record = json.loads((stage / "stage.json").read_text())
    result: dict[Path, str] = {}
    for relative in SAFE_MENU_INPUTS:
        if record.get("rollback", {}).get(str(relative)) != "directory":
            raise ValueError(f"stage lacks reviewed menu input: {relative}")
        source = stage / "rollback" / relative
        if not source.is_dir() or source.is_symlink():
            raise ValueError(f"unsafe staged menu input: {relative}")
        for item in source.rglob("*"):
            if item.is_symlink() or not item.is_file():
                if item.is_symlink():
                    raise ValueError(f"symlink in staged menu input: {relative}")
                continue
            lowered = item.name.lower()
            if any(word in lowered for word in ("password", "credential", "token", "secret")):
                raise ValueError(f"credential-like menu input name: {item.name}")
            # Menu configuration is text/XML.  Reject credential fields rather
            # than importing a permissive copy of arbitrary addon data.
            text = item.read_bytes().lower()
            if any(marker in text for marker in (b"password", b"access_token", b"api_key", b"credential")):
                raise ValueError(f"credential-like menu input content: {item.name}")
        result[relative] = _tree_hash(source)
    return result


def _path_proof_receipt(runtime_home: Path, nonce: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", nonce):
        raise ValueError("invalid path-proof nonce")
    return (Path(runtime_home).resolve() / ".kodi" / "userdata"
            / f"{PATH_PROOF_RECEIPT_PREFIX}{nonce}{PATH_PROOF_RECEIPT_SUFFIX}")


def _write_path_proof_script(runtime_home: Path, nonce: str) -> Path:
    """Write a nonce-bound Kodi script that proves *runtime* special paths.

    Kodi's debug log is neither a complete nor a stable record of special-path
    mappings.  This script instead executes inside the transient Kodi process
    and writes only through its resolved ``special://profile`` path.
    """
    receipt = _path_proof_receipt(runtime_home, nonce)
    script = receipt.with_name(PATH_PROOF_SCRIPT)
    payload = {
        "schema": PATH_PROOF_SCHEMA,
        "nonce": nonce,
        "receipt": receipt.name,
    }
    source = """import json
import os
import xbmcvfs

PAYLOAD = {payload}
paths = ("special://home", "special://profile", "special://skin")
mappings = {{path: xbmcvfs.translatePath(path) for path in paths}}
target = os.path.join(mappings["special://profile"], PAYLOAD["receipt"])
temporary = target + ".tmp"
with open(temporary, "w", encoding="utf-8") as handle:
    json.dump({{"schema": PAYLOAD["schema"], "nonce": PAYLOAD["nonce"], "mappings": mappings}}, handle,
              sort_keys=True, separators=(",", ":"))
    handle.flush()
    os.fsync(handle.fileno())
os.replace(temporary, target)
""".format(payload=json.dumps(payload, sort_keys=True))
    script.write_text(source, encoding="utf-8")
    return script


def prepare_home(storage_root: Path, stage: Path, runtime_home: Path,
                 system_addons: Path = Path("/usr/share/kodi/addons"),
                 reviewed_root: Path | None = None,
                 path_proof_nonce: str | None = None) -> dict:
    """Create an isolated Kodi HOME and return a write receipt for its closure."""
    storage_root, stage = Path(storage_root).resolve(), Path(stage).resolve()
    runtime_home = _runtime_home(storage_root, runtime_home)
    root = storage_root / ".kodi"
    candidate = stage / "candidate" / SKIN_PATH
    if not candidate.is_dir() or _tree_hash(candidate) != json.loads((stage / "stage.json").read_text())["candidate_skin_sha256"]:
        raise ValueError("candidate skin is missing or drifted")
    closure = dependency_closure(candidate, root / "addons", Path(system_addons), reviewed_root)
    menu_inputs = safe_menu_inputs(stage)
    addons = runtime_home / ".kodi" / "addons"
    addons.mkdir(parents=True, mode=0o700)
    shutil.copytree(candidate, addons / SKIN_ID, symlinks=False)
    receipt = {SKIN_ID: _tree_hash(addons / SKIN_ID)}
    for addon_id, source in sorted(closure.items()):
        shutil.copytree(source, addons / addon_id, symlinks=False)
        receipt[addon_id] = _tree_hash(addons / addon_id)
    userdata = runtime_home / ".kodi" / "userdata"
    userdata.mkdir(mode=0o700)
    # A fresh Kodi Addons database discovers copied add-ons as disabled. Start
    # on built-in Estuary. A first private-only Kodi start will create its own
    # Addons33 database; after it is stopped, the exact audited closure is
    # enabled offline inside that fresh database. Never seed/copy the active
    # profile's database merely to make the sandbox load a skin.
    (userdata / "guisettings.xml").write_text(
        '<settings version="2">'
        '<setting id="lookandfeel.skin">skin.estuary</setting>'
        # CoreELEC's default JSON-RPC server is loopback TCP 9090; the event
        # client is configurable and otherwise disabled in a new Kodi profile.
        # Keep it loopback-only so the temporary instance is not exposed.
        '<setting id="services.esenabled">true</setting>'
        '<setting id="services.esport">9777</setting>'
        '<setting id="services.esallinterfaces">false</setting>'
        '</settings>\n'
    )
    (userdata / "addon_data" / SKINVARIABLES).mkdir(parents=True, mode=0o700)
    copied_inputs = {}
    for relative, expected_hash in menu_inputs.items():
        source = stage / "rollback" / relative
        destination = runtime_home / ".kodi" / relative
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, symlinks=False)
        copied_hash = _tree_hash(destination)
        if copied_hash != expected_hash:
            raise RuntimeError(f"staged menu input copy mismatch: {relative}")
        copied_inputs[str(relative)] = copied_hash
    if path_proof_nonce is not None:
        _write_path_proof_script(runtime_home, path_proof_nonce)
    validate_minimal_home(runtime_home, set(receipt), path_proof_nonce)
    return {"home": str(runtime_home), "addons": receipt, "menu_inputs": copied_inputs}


def validate_minimal_home(runtime_home: Path, allowed_addons: set[str],
                          path_proof_nonce: str | None = None) -> None:
    """Reject any stage path outside the intentionally tiny profile surface."""
    runtime_home = Path(runtime_home).resolve()
    kodi = runtime_home / ".kodi"
    allowed = {Path("addons") / addon for addon in allowed_addons}
    allowed |= {Path("userdata/guisettings.xml"), *SAFE_MENU_INPUTS}
    if path_proof_nonce is not None:
        _path_proof_receipt(runtime_home, path_proof_nonce)
        allowed.add(Path("userdata") / PATH_PROOF_SCRIPT)
    for item in kodi.rglob("*"):
        relative = item.relative_to(kodi)
        if item.is_symlink():
            raise ValueError("symlink in runtime stage")
        if any(relative == entry or entry in relative.parents or relative in entry.parents
               for entry in allowed):
            continue
        raise ValueError(f"unexpected runtime stage path: {relative}")


def _port_available(port: int, kind: int) -> None:
    probe = socket.socket(socket.AF_INET, kind)
    try:
        probe.bind(("127.0.0.1", port))
    except OSError as exc:
        raise RuntimeError(f"required Kodi port {port} is already occupied") from exc
    finally:
        probe.close()


def validate_ports() -> None:
    """Ensure normal Kodi released its JSON-RPC and event-client ports."""
    _port_available(9090, socket.SOCK_STREAM)
    _port_available(9777, socket.SOCK_DGRAM)


def _wait_for_rpc(timeout: int, rpc=lifecycle.rpc) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if rpc("Player.GetActivePlayers") == []:
                return
            raise RuntimeError("staged Kodi unexpectedly started playback")
        except Exception as exc:
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError("staged Kodi JSON-RPC did not become ready") from last_error


def _wait_for_private_addons_enabled(rpc, addon_ids: set[str], timeout: int = 10,
                                     *, clock=time.monotonic, sleeper=time.sleep) -> list[str]:
    """Poll Kodi's database-backed enabled state until the audited closure settles."""
    pending = set(addon_ids)
    deadline = clock() + timeout
    while clock() < deadline:
        for addon_id in tuple(sorted(pending)):
            details = rpc("Addons.GetAddonDetails", {"addonid": addon_id, "properties": ["enabled"]})
            if details.get("addon", {}).get("enabled") is True:
                pending.remove(addon_id)
        if not pending:
            return sorted(addon_ids)
        sleeper(0.25)
    raise RuntimeError("Kodi did not enable private add-ons: " + ", ".join(sorted(pending)))


def _private_addons_database(runtime_home: Path) -> Path:
    runtime_home = Path(runtime_home).resolve()
    database = runtime_home / ".kodi" / "userdata" / "Database" / ADDONS_DATABASE_FILENAME
    if (runtime_home not in database.parents or database.parent.is_symlink()
            or database.is_symlink() or not database.is_file()):
        raise RuntimeError("fresh private Kodi Addons database is missing or unsafe")
    for sidecar in (database.with_name(database.name + suffix)
                    for suffix in ("-journal", "-wal", "-shm")):
        if sidecar.exists():
            raise RuntimeError("private Kodi Addons database has an uncheckpointed sidecar")
    return database


def enable_private_addons_offline(runtime_home: Path, addon_ids: set[str]) -> dict[str, int]:
    """Enable only an audited closure in a fresh, stopped private Addons33 DB.

    Kodi Piers stores disabled state solely in ``installed.enabled`` and
    ``installed.disabledReason``. This is intentionally a two-phase sandbox
    operation: Kodi itself first discovers all staged add-ons and creates the
    database; after its exact transient unit is confirmed gone, this function
    changes only the selected private rows in one SQLite transaction.
    """
    addon_ids = set(addon_ids)
    if not addon_ids or SKIN_ID not in addon_ids:
        raise RuntimeError("private runtime closure does not contain the candidate skin")
    for addon_id in addon_ids:
        _safe_addon_id(addon_id)
    database = _private_addons_database(runtime_home)
    try:
        # The file has already been required to exist and to be private/regular.
        # Do not encode an operator-supplied HOME path into a SQLite URI: URI
        # metacharacters in its final component could otherwise alter parsing.
        connection = sqlite3.connect(database)
        try:
            if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise RuntimeError("private Kodi Addons database integrity check failed")
            if connection.execute("SELECT idVersion FROM version").fetchall() != [(ADDONS_DATABASE_SCHEMA,)]:
                raise RuntimeError("unexpected private Kodi Addons database schema")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(installed)")}
            required = {"addonID", "enabled", "disabledReason"}
            if not required.issubset(columns):
                raise RuntimeError("private Kodi Addons database lacks required installed fields")
            placeholders = ",".join("?" for _ in addon_ids)
            rows = connection.execute(
                f"SELECT addonID, enabled, disabledReason FROM installed WHERE addonID IN ({placeholders})",
                tuple(sorted(addon_ids)),
            ).fetchall()
            found = {row[0] for row in rows}
            if found != addon_ids or len(rows) != len(addon_ids):
                raise RuntimeError("fresh private Kodi Addons database lacks the audited closure")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                f"UPDATE installed SET enabled=1, disabledReason=0 WHERE addonID IN ({placeholders})",
                tuple(sorted(addon_ids)),
            )
            verified = connection.execute(
                f"SELECT addonID, enabled, disabledReason FROM installed WHERE addonID IN ({placeholders})",
                tuple(sorted(addon_ids)),
            ).fetchall()
            if {row[0] for row in verified} != addon_ids or any(row[1:] != (1, 0) for row in verified):
                raise RuntimeError("private Kodi Addons database did not enable the audited closure")
            connection.commit()
            return {"schema": ADDONS_DATABASE_SCHEMA, "closure_count": len(addon_ids)}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise RuntimeError("private Kodi Addons database update failed") from exc


def _activate_private_skin(rpc, addon_ids: set[str], run, kodi_send: Path) -> list[str]:
    """Load a pre-enabled private candidate and verify the complete closure."""
    addon_ids = set(addon_ids)
    if not addon_ids or SKIN_ID not in addon_ids:
        raise RuntimeError("private runtime closure does not contain the candidate skin")
    for addon_id in addon_ids:
        _safe_addon_id(addon_id)
    # LoadSkin has no approval dialog. The preceding offline DB transaction
    # makes the candidate and exact closure available before this second start.
    _send_builtin(run, kodi_send, "LoadSkin(" + SKIN_ID + ")")
    enabled = _wait_for_private_addons_enabled(rpc, addon_ids)
    return enabled


def _wait_for_active_skin(timeout: int, rpc=lifecycle.rpc) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = rpc("Settings.GetSkinSettings")
            if result.get("skin") == SKIN_ID:
                return
            last_error = RuntimeError(f"active skin is {result.get('skin')!r}")
        except Exception as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError("isolated Kodi did not activate the candidate skin") from last_error


def _validate_path_proof_receipt(runtime_home: Path, nonce: str) -> dict[str, str]:
    """Fail closed unless an in-process Kodi receipt proves all three paths."""
    receipt = _path_proof_receipt(runtime_home, nonce)
    expected_profile = (Path(runtime_home).resolve() / ".kodi" / "userdata").resolve()
    if receipt.parent.resolve() != expected_profile or receipt.is_symlink() or not receipt.is_file():
        raise RuntimeError("Kodi did not create a private path-proof receipt")
    if receipt.stat().st_size > PATH_PROOF_MAX_BYTES:
        raise RuntimeError("Kodi path-proof receipt is too large")
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Kodi path-proof receipt is invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema", "nonce", "mappings"}:
        raise RuntimeError("Kodi path-proof receipt has unexpected fields")
    if payload.get("schema") != PATH_PROOF_SCHEMA or payload.get("nonce") != nonce:
        raise RuntimeError("Kodi path-proof receipt nonce/schema mismatch")
    mappings = payload.get("mappings")
    if not isinstance(mappings, dict):
        raise RuntimeError("Kodi path-proof receipt has invalid mappings")
    expected = {
        "special://home": Path(runtime_home).resolve() / ".kodi",
        "special://profile": expected_profile,
        "special://skin": Path(runtime_home).resolve() / ".kodi" / "addons" / SKIN_ID,
    }
    if set(mappings) != set(expected):
        raise RuntimeError("Kodi path-proof receipt has unexpected mapping keys")
    normalized: dict[str, str] = {}
    for special, location in expected.items():
        value = mappings.get(special)
        if not isinstance(value, str) or not value or "\x00" in value:
            raise RuntimeError(f"Kodi path-proof receipt has invalid {special} mapping")
        mapped = Path(value).resolve()
        if mapped != location.resolve():
            raise RuntimeError(f"unsafe {special} mapping: {mapped}")
        normalized[special] = str(mapped)
    return normalized


def _wait_for_path_proof(runtime_home: Path, nonce: str, timeout: int = PATH_PROOF_TIMEOUT_SECONDS) -> dict[str, str]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return _validate_path_proof_receipt(runtime_home, nonce)
        except RuntimeError as exc:
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError("Kodi did not prove private special-path mappings") from last_error


def _generated_files(runtime_home: Path) -> list[Path]:
    skin = runtime_home / ".kodi" / "addons" / SKIN_ID / "1080i"
    return sorted(skin.glob("script-skinvariables-generator-includes-*.xml"))


def clear_generated_outputs(runtime_home: Path) -> dict[str, str]:
    """Snapshot and remove only generated files inside the private runtime skin."""
    runtime_home = Path(runtime_home).resolve()
    root = runtime_home / ".kodi/addons" / SKIN_ID / "1080i"
    if runtime_home not in root.parents:
        raise ValueError("unsafe runtime generated-output path")
    previous = {}
    for item in _generated_files(runtime_home):
        if item.is_symlink() or not item.is_file():
            raise ValueError("unsafe generated output")
        previous[item.name] = hashlib.sha256(item.read_bytes()).hexdigest()
        item.unlink()
    return previous


def _validate_generated_selectors(files: list[Path]) -> None:
    """Require fresh XML to retain every managed selector pipeline."""
    combined = b"".join(item.read_bytes() for item in files)
    for marker in (
        b"skinvariables-searchwidgets-combined-selector-owned",
        b"skinvariables-searchwidgets-combined-selector-venom",
        b"skinvariables-searchwidgets-standard-selector-owned",
        b"skinvariables-searchwidgets-standard-selector-venom",
    ):
        if marker not in combined:
            raise RuntimeError(f"generated selectors omit managed route: {marker.decode()}")
    for item in files:
        try:
            ET.fromstring(item.read_bytes())
        except ET.ParseError as exc:
            raise RuntimeError(f"generated include is not XML: {item.name}") from exc


def _wait_for_generation(runtime_home: Path, timeout: int,
                         existing_before: set[str] | None = None) -> list[Path]:
    existing_before = existing_before or set()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        files = _generated_files(runtime_home)
        if files and all(item.stat().st_size > 0 for item in files):
            if any(item.name in existing_before for item in files):
                time.sleep(0.25)
                continue
            _validate_generated_selectors(files)
            return files
        time.sleep(0.25)
    raise RuntimeError("SkinVariables generated no non-empty include file")


def _send_builtin(run, kodi_send: Path, action: str) -> None:
    if (kodi_send != Path("/usr/bin/kodi-send") or kodi_send.name != "kodi-send"
            or kodi_send.is_symlink() or not kodi_send.is_file()):
        raise ValueError("refusing a nonstandard kodi-send helper")
    # CoreELEC's kodi-send emits a human-readable ``Sending: ...`` line on
    # stdout.  The public CLI is intentionally a one-JSON-object interface so
    # that its private receipt can be parsed without accepting arbitrary log
    # prefixes.  Keep that helper chatter captured while still failing on a
    # non-zero exit or timeout.
    run([str(kodi_send), "--action=" + action], check=True, timeout=10,
        capture_output=True, text=True)


def _send_path_proof(run, kodi_send: Path) -> None:
    _send_builtin(run, kodi_send, "RunScript(special://profile/" + PATH_PROOF_SCRIPT + ")")


def _send_generator(run, kodi_send: Path) -> None:
    _send_builtin(run, kodi_send, GENERATOR)


def _validate_kodi_binary(kodi_bin: Path) -> None:
    if (kodi_bin != Path("/usr/lib/kodi/kodi.bin") or kodi_bin.is_symlink()
            or not kodi_bin.is_file()):
        raise ValueError("requires the direct CoreELEC kodi.bin executable")


def _unit_name(runtime_home: Path, phase: str = "generation") -> str:
    if phase not in {"bootstrap", "generation"}:
        raise ValueError("unsupported isolated Kodi phase")
    digest = hashlib.sha256((str(Path(runtime_home).resolve()) + "\0" + phase).encode()).hexdigest()[:16]
    return "arctic3410-" + phase + "-" + digest


def _launch_isolated_kodi(run, unit: str, runtime_home: Path, kodi_bin: Path) -> None:
    """Launch direct kodi.bin in a transient mount namespace, never kodi.sh."""
    command = [
        "systemd-run", "--no-block", "--collect", "--unit=" + unit,
        "--property=Type=exec",
        # These are enforcement, not merely before/after evidence.  A Kodi
        # build that ignores HOME cannot modify live profile/flash in this unit.
        "--property=ReadOnlyPaths=/storage/.kodi",
        "--property=ReadOnlyPaths=/flash",
        "--property=ReadWritePaths=" + str(runtime_home),
        "--property=PrivateTmp=yes",
        "--property=NoNewPrivileges=yes",
        "--property=ProtectSystem=strict",
        "/usr/bin/env", "HOME=" + str(runtime_home),
        "KODI_TEMP=" + str(runtime_home / ".kodi/temp"),
        "PATH=/usr/bin:/bin", str(kodi_bin), "--standalone", "-fs", "--debug",
    ]
    run(command, check=True, timeout=15)


def _stop_owned_unit(run, unit: str, *, clock=time.monotonic, sleeper=time.sleep) -> None:
    """Stop and prove reaping of this exact transient unit.

    A successful ``systemctl stop`` alone is not enough: the earlier d01 probe
    returned after stop timed out and normal Kodi raced the private process for
    port 9090. Normal Kodi can restart only after this unit is inactive/dead
    with no main PID, or has been collected completely.
    """
    deadline = clock() + 30
    killed = False
    last_error: Exception | None = None
    while clock() < deadline:
        try:
            state = run(
                ["systemctl", "show", unit, "--no-page",
                 "--property=LoadState", "--property=ActiveState",
                 "--property=SubState", "--property=MainPID"],
                check=False, timeout=5, capture_output=True, text=True,
            )
            values = {}
            for line in (getattr(state, "stdout", "") or "").splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    values[key] = value
            if values.get("LoadState") == "not-found" or (
                values.get("ActiveState") == "inactive"
                and values.get("SubState") == "dead"
                and values.get("MainPID") in {"", "0"}
            ):
                return
        except subprocess.TimeoutExpired as exc:
            last_error = exc

        stop_timed_out = False
        try:
            run(["systemctl", "stop", unit], check=False, timeout=10)
        except subprocess.TimeoutExpired as exc:
            last_error = exc
            stop_timed_out = True
        # Escalate only the hashed unit created for this runtime HOME, never a
        # process selected by executable name or the normal kodi.service.
        if not killed and (stop_timed_out or clock() + 5 >= deadline):
            try:
                run(["systemctl", "kill", "--kill-who=all", "--signal=SIGKILL", unit],
                    check=False, timeout=10)
            except subprocess.TimeoutExpired as exc:
                last_error = exc
            killed = True
        sleeper(0.25)
    detail = f": {last_error}" if last_error else ""
    raise RuntimeError("owned isolated Kodi unit did not terminate before normal Kodi restart" + detail)


def run_probe(storage_root: Path, stage: Path, profile: dict, runtime_home: Path,
              *, hostname_reader=None, mac_reader=None,
              kodi_bin: Path = Path("/usr/lib/kodi/kodi.bin"),
              kodi_send: Path = Path("/usr/bin/kodi-send"),
              system_addons: Path = Path("/usr/share/kodi/addons"),
              run=subprocess.run, rpc=lifecycle.rpc,
              binary_validator=_validate_kodi_binary,
              preflight_func=preflight, ports_validator=validate_ports,
              send_generator=_send_generator, launcher=_launch_isolated_kodi,
              stop_owned_unit=_stop_owned_unit,
              reviewed_addons_root: Path | None = None,
              dependency_preflight=runtime_dependency_preflight,
              send_path_proof=_send_path_proof,
              wait_for_path_proof=_wait_for_path_proof,
              activate_private_skin=_activate_private_skin,
              wait_for_active_skin=_wait_for_active_skin,
              enable_private_addons=enable_private_addons_offline) -> dict:
    """Run the bounded probe; only call after an operator chooses ``--apply``."""
    kodi_bin = Path(kodi_bin)
    binary_validator(kodi_bin)
    storage_root, stage = Path(storage_root).resolve(), Path(stage).resolve()
    # This first pass is read-only; the same complete preflight runs again after
    # normal Kodi is stopped, closing the source/identity race before staging.
    preflight_func(storage_root, stage, profile, hostname_reader, mac_reader)
    dependency_preflight(storage_root, stage, system_addons, reviewed_addons_root)

    cleanup_confirmed = {"value": True}

    def mutate():
        preflight_func(storage_root, stage, profile, hostname_reader, mac_reader)
        dependency_preflight(storage_root, stage, system_addons, reviewed_addons_root)
        ports_validator()
        path_proof_nonce = secrets.token_hex(32)
        receipt = prepare_home(storage_root, stage, runtime_home, system_addons,
                               reviewed_addons_root, path_proof_nonce)
        previous_generated = clear_generated_outputs(runtime_home)
        bootstrap_unit = _unit_name(runtime_home, "bootstrap")
        generation_unit = _unit_name(runtime_home, "generation")
        try:
            # Phase 1 is deliberately Estuary-only. It lets Kodi discover the
            # staged closure and create a fresh Addons33 database, which is
            # then safely edited while no Kodi process owns it.
            launcher(run, bootstrap_unit, runtime_home, kodi_bin)
            try:
                _wait_for_rpc(START_TIMEOUT_SECONDS, rpc)
            finally:
                try:
                    stop_owned_unit(run, bootstrap_unit)
                except Exception:
                    cleanup_confirmed["value"] = False
                    raise
            ports_validator()
            bootstrap = enable_private_addons(runtime_home, set(receipt["addons"]))
            # Phase 1 has its own hard RPC readiness bound and is fully stopped
            # before the private DB update.  The existing generation budget
            # starts only for phase 2; this is not an unbounded retry or a
            # timeout extension for the prior stalled enablement path.
            started = time.monotonic()
            launcher(run, generation_unit, runtime_home, kodi_bin)
            _wait_for_rpc(START_TIMEOUT_SECONDS, rpc)
            enabled_addons = activate_private_skin(rpc, set(receipt["addons"]), run, kodi_send)
            wait_for_active_skin(SKIN_ACTIVATION_TIMEOUT_SECONDS, rpc)
            if time.monotonic() - started > MAX_RUNTIME_SECONDS:
                raise RuntimeError("staged Kodi startup exceeded runtime budget")
            send_path_proof(run, kodi_send)
            mappings = wait_for_path_proof(runtime_home, path_proof_nonce)
            if time.monotonic() - started > MAX_RUNTIME_SECONDS:
                raise RuntimeError("staged Kodi path proof exceeded runtime budget")
            send_generator(run, kodi_send)
            # Old outputs were removed before launch, so any file now observed
            # was created by this owned runtime even if it has the same name.
            generated = _wait_for_generation(runtime_home, GENERATION_TIMEOUT_SECONDS)
            if time.monotonic() - started > MAX_RUNTIME_SECONDS:
                raise RuntimeError("staged Kodi generation exceeded runtime budget")
            return {"receipt": receipt, "bootstrap": bootstrap,
                    "enabled_addons": enabled_addons, "path_mappings": mappings,
                    "removed_generated": previous_generated, "generated": [str(item) for item in generated]}
        finally:
            # ``systemd-run --no-block`` can report a transport error after
            # PID 1 accepted the bootstrap request. Reap both exact hashed
            # units in reverse launch order, even if the bootstrap inner
            # cleanup already saw it gone. Do not kill by executable name and
            # never touch normal kodi.service.
            cleanup_errors = []
            for owned_unit in (generation_unit, bootstrap_unit):
                try:
                    stop_owned_unit(run, owned_unit)
                except Exception as exc:
                    cleanup_confirmed["value"] = False
                    cleanup_errors.append(exc)
            if cleanup_errors:
                if len(cleanup_errors) == 1:
                    raise cleanup_errors[0]
                detail = "; ".join(str(error) for error in cleanup_errors)
                raise RuntimeError("multiple isolated Kodi units failed cleanup: " + detail) from cleanup_errors[0]

    return lifecycle.with_stopped_kodi(
        mutate, run=run, restart_permitted=lambda: cleanup_confirmed["value"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", type=Path, default=Path("/storage"))
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--runtime-home", type=Path, required=True)
    parser.add_argument("--reviewed-addons-root", type=Path,
                        help="private root containing only the two reviewed Arctic resource trees")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text())
    changes = preflight(args.storage_root, args.stage, profile)
    dependencies = runtime_dependency_preflight(args.storage_root, args.stage,
                                                reviewed_root=args.reviewed_addons_root)
    summary = {"mode": "probe" if args.apply else "plan-only", "release": install.RELEASE,
               "cohort": profile["cohort"], "changes": [str(item) for item in changes],
               "runtime_home": str(args.runtime_home), "generator": GENERATOR,
               "runtime_dependencies": dependencies}
    if args.apply:
        summary["result"] = run_probe(args.storage_root, args.stage, profile, args.runtime_home,
                                      reviewed_addons_root=args.reviewed_addons_root)
    # Emit one JSON object for either plan-only or apply.  In particular, do
    # not serialize a plan before the apply result: callers retain a single
    # receipt even when kodi-send itself is chatty.
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
