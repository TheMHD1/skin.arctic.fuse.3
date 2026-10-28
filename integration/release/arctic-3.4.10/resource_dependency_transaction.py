"""Guarded native deployment for Arctic 3.4.10's two image resources.

This is a library, not a public installer.  The private paired orchestrator must
hold :func:`deployment_lock` continuously through this transaction and the skin
transaction.  Kodi performs registration itself: after the exact trees are
installed, normal Kodi starts, scans ``special://home/addons``, and the module
uses ``Addons.SetAddonEnabled`` once per resource.  It never synthesizes Kodi
database rows.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import time
import urllib.parse
import xml.etree.ElementTree as ET

import directory_transaction
import generation_probe

RELEASE = "arctic-3.4.10-resources.1"
JOURNAL_SCHEMA = 1
RECEIPT_SCHEMA = 1
BOOTSTRAP_SCHEMA = 1
DATABASE_SCHEMA = 33
DATABASE_NAME = "Addons33.db"
PINS = {key: dict(value) for key, value in generation_probe.REVIEWED_RESOURCES.items()}
IDS = tuple(sorted(PINS))
SHA = re.compile(r"[0-9a-f]{64}\Z")
PHASES = {"initializing", "prepared", "directories-installed", "verified",
          "rollback-db-preserved", "rollback-db-restored", "accepted", "rolled-back"}
MAX_DB = 256 * 1024 * 1024
MAX_RECORD = 256 * 1024


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def fsync_file(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def safe_absolute(path):
    path = Path(os.path.abspath(path))
    cursor = path
    while True:
        if cursor.is_symlink():
            raise ValueError("symlink in resource transaction ancestry")
        if cursor == cursor.parent:
            return path
        cursor = cursor.parent


def paths(storage_root):
    storage = safe_absolute(storage_root).resolve()
    kodi = safe_absolute(storage / ".kodi").resolve()
    recovery = safe_absolute(kodi / ".arctic3410-resource-recovery")
    result = {
        "storage": storage,
        "kodi": kodi,
        "addons": safe_absolute(kodi / "addons"),
        "database": safe_absolute(kodi / "userdata/Database" / DATABASE_NAME),
        "lock": safe_absolute(kodi / ".arctic3410-deployment.lock"),
        "bootstrap": safe_absolute(kodi / ".arctic3410-resource-bootstrap.json"),
        "root": recovery,
        "candidates": safe_absolute(recovery / "candidates"),
        "backup": safe_absolute(recovery / (DATABASE_NAME + ".old")),
        "failed": safe_absolute(recovery / "failed"),
        "journal": safe_absolute(recovery / "transaction.json"),
        "receipt": safe_absolute(recovery / "accepted.json"),
    }
    return result


class HeldLock:
    def __init__(self, path, descriptor):
        self.path = Path(path)
        self.descriptor = descriptor
        self.active = True

    def close(self):
        if self.active:
            fcntl.flock(self.descriptor, fcntl.LOCK_UN)
            os.close(self.descriptor)
            self.active = False


@contextlib.contextmanager
def deployment_lock(storage_root):
    """Acquire the lock the orchestrator must retain through the skin switch."""
    value = paths(storage_root)
    if value["kodi"].is_symlink() or not value["kodi"].is_dir():
        raise RuntimeError("Kodi root is missing or unsafe")
    fd = os.open(value["lock"], os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    held = HeldLock(value["lock"], fd)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077:
            raise RuntimeError("deployment lock metadata is unsafe")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield held
    finally:
        held.close()


def require_lock(lock, expected):
    if (not isinstance(lock, HeldLock) or not lock.active
            or lock.path != expected or lock.descriptor < 0):
        raise RuntimeError("shared Arctic deployment lock is not held")
    info_fd = os.fstat(lock.descriptor)
    info_path = expected.stat(follow_symlinks=False)
    if (info_fd.st_dev, info_fd.st_ino) != (info_path.st_dev, info_path.st_ino):
        raise RuntimeError("shared Arctic deployment lock was replaced")


def tree_state(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("regular reviewed resource tree required")
    result = {}
    for item in [root, *sorted(root.rglob("*"))]:
        if item.is_symlink():
            raise ValueError("symlink in reviewed resource tree")
        info = item.stat(follow_symlinks=False)
        relative = "." if item == root else str(item.relative_to(root))
        if item.is_dir():
            result[relative] = {"kind": "directory", "mode": stat.S_IMODE(info.st_mode),
                                "uid": info.st_uid, "gid": info.st_gid}
        elif item.is_file() and stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            data = item.read_bytes()
            result[relative] = {"kind": "file", "mode": stat.S_IMODE(info.st_mode),
                                "uid": info.st_uid, "gid": info.st_gid,
                                "size": len(data), "sha256": sha(data)}
        else:
            raise ValueError("special or linked file in reviewed resource tree")
    return result


def resource(path, addon_id):
    state = tree_state(path)
    addon_xml = Path(path) / "addon.xml"
    if not addon_xml.is_file():
        raise ValueError("resource addon.xml is missing")
    root = ET.fromstring(addon_xml.read_bytes())
    pin = PINS[addon_id]
    tree_sha = directory_transaction.tree_hash(path)
    if root.get("id") != addon_id or root.get("version") != pin["version"] or tree_sha != pin["sha256"]:
        raise ValueError("reviewed resource drift: " + addon_id)
    return {"version": pin["version"], "tree_sha256": tree_sha,
            "metadata_sha256": sha(canonical(state))}


def sources(source_root):
    source = safe_absolute(source_root).resolve()
    if source.is_symlink() or not source.is_dir() or {p.name for p in source.iterdir()} != set(IDS):
        raise ValueError("reviewed source must contain exactly the resource pair")
    return {addon_id: resource(source / addon_id, addon_id) for addon_id in IDS}


def regular(path, maximum):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("required regular file is missing or unsafe: " + str(path))
    info = path.stat(follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
            or not 0 < info.st_size <= maximum):
        raise RuntimeError("required file metadata is unsafe: " + str(path))
    return info


def private_directory(path, *, create=False):
    path = safe_absolute(path)
    if create and not path.exists():
        path.mkdir(mode=0o700)
        fsync_dir(path.parent)
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError("private recovery directory is missing or unsafe: " + str(path))
    info = path.stat(follow_symlinks=False)
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError("private recovery directory metadata is unsafe: " + str(path))
    return path


def db_uri(path):
    return "file:" + urllib.parse.quote(str(path), safe="/") + "?mode=ro"


def db_rows(path):
    regular(path, MAX_DB)
    try:
        connection = sqlite3.connect(db_uri(path), uri=True, timeout=2)
        try:
            if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise RuntimeError("add-on database integrity failure")
            if connection.execute("SELECT idVersion FROM version").fetchall() != [(DATABASE_SCHEMA,)]:
                raise RuntimeError("unexpected add-on database schema")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(installed)")}
            if not {"addonID", "enabled", "disabledReason"}.issubset(columns):
                raise RuntimeError("installed table fields are incomplete")
            marks = ",".join("?" for _ in IDS)
            rows = connection.execute(
                f"SELECT addonID,enabled,disabledReason FROM installed WHERE addonID IN ({marks})",
                IDS).fetchall()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise RuntimeError("add-on database read failure") from exc
    if len(rows) != len({row[0] for row in rows}):
        raise RuntimeError("duplicate resource database rows")
    return {row[0]: (int(row[1]), int(row[2])) for row in rows}


def db_state(path):
    info = regular(path, MAX_DB)
    db_rows(path)
    data = path.read_bytes()
    return {"sha256": sha(data), "size": len(data), "mode": stat.S_IMODE(info.st_mode),
            "uid": info.st_uid, "gid": info.st_gid}


def _sql_identifier(value):
    return '"' + str(value).replace('"', '""') + '"'


def _cell(value):
    if value is None: return ["null", None]
    if isinstance(value, bytes): return ["blob", value.hex()]
    if isinstance(value, bool): return ["integer", int(value)]
    if isinstance(value, int): return ["integer", value]
    if isinstance(value, float): return ["real", value.hex()]
    if isinstance(value, str): return ["text", value]
    raise RuntimeError("unsupported SQLite value in semantic snapshot")


def db_semantic(path, *, omit_resources):
    """Hash every schema/row byte, optionally omitting only the two owned rows."""
    regular(path, MAX_DB)
    try:
        connection = sqlite3.connect(db_uri(path), uri=True, timeout=2)
        try:
            if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise RuntimeError("add-on database integrity failure")
            schema_rows = connection.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name,tbl_name"
            ).fetchall()
            tables = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
            contents = {}
            for table in tables:
                columns = [row[1] for row in connection.execute(
                    "PRAGMA table_info(" + _sql_identifier(table) + ")").fetchall()]
                rows = connection.execute("SELECT * FROM " + _sql_identifier(table)).fetchall()
                if omit_resources and table == "installed":
                    if "addonID" not in columns:
                        raise RuntimeError("installed table lacks addonID")
                    index = columns.index("addonID")
                    rows = [row for row in rows if row[index] not in IDS]
                encoded = [[_cell(item) for item in row] for row in rows]
                encoded.sort(key=canonical)
                contents[table] = {"columns": columns, "rows": encoded}
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise RuntimeError("add-on database semantic read failure") from exc
    return sha(canonical({"schema": [[_cell(item) for item in row] for row in schema_rows],
                          "tables": contents}))


def no_sidecars(database):
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = database.with_name(database.name + suffix)
        if sidecar.exists() or sidecar.is_symlink():
            raise RuntimeError("add-on database has a writer sidecar")


def pending_path(path, payload):
    return path.with_name(path.name + ".pending." + sha(payload))


def pending_records(path):
    prefix = path.name + ".pending."
    result = []
    if not path.parent.is_dir() or path.parent.is_symlink():
        return result
    for item in path.parent.iterdir():
        if item.name.startswith(prefix):
            suffix = item.name[len(prefix):]
            if not SHA.fullmatch(suffix):
                raise RuntimeError("foreign pending-record namespace entry")
            result.append(item)
    return sorted(result)


def read_pending(path):
    suffix = path.name.rsplit(".pending.", 1)[-1]
    info = regular(path, MAX_RECORD)
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise RuntimeError("pending record permissions are unsafe")
    raw = path.read_bytes()
    if sha(raw) != suffix:
        raise RuntimeError("pending record hash binding failed")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("pending record is invalid") from exc
    if canonical(value) != raw:
        raise RuntimeError("pending record is not canonical")
    return value, raw


def _commit_record(source, target):
    os.replace(source, target)


def atomic_record(path, value):
    payload = canonical(value)
    temporary = pending_path(path, payload)
    if temporary.exists() or temporary.is_symlink():
        pending_value, pending_raw = read_pending(temporary)
        if pending_value != value or pending_raw != payload:
            raise RuntimeError("pending record content collision")
    else:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        fsync_dir(path.parent)
    _commit_record(temporary, path)
    fsync_dir(path.parent)


def read_record(path):
    info = regular(path, MAX_RECORD)
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise RuntimeError("private transaction record permissions are unsafe")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("invalid transaction record") from exc
    if canonical(value) != raw:
        raise RuntimeError("transaction record is not canonical")
    return value, raw


def journal_shape(value, value_paths):
    keys = {"schema", "release", "phase", "cohort", "profile_binding_sha256",
            "transaction_nonce", "storage_root", "resources", "database",
            "accepted_receipt_sha256"}
    if (not isinstance(value, dict) or set(value) != keys or value.get("schema") != JOURNAL_SCHEMA
            or value.get("release") != RELEASE or value.get("phase") not in PHASES
            or value.get("cohort") not in {"local", "remote"}
            or not SHA.fullmatch(str(value.get("profile_binding_sha256")))
            or not SHA.fullmatch(str(value.get("transaction_nonce")))
            or value.get("storage_root") != str(value_paths["storage"])
            or not isinstance(value.get("resources"), dict)
            or set(value["resources"]) != set(IDS)):
        raise RuntimeError("invalid resource transaction journal")
    accepted_sha = value.get("accepted_receipt_sha256")
    if ((value.get("phase") == "accepted" and not SHA.fullmatch(str(accepted_sha)))
            or (value.get("phase") != "accepted" and accepted_sha is not None)):
        raise RuntimeError("invalid resource transaction journal")
    for addon_id in IDS:
        expected = PINS[addon_id]
        row = value["resources"][addon_id]
        if (not isinstance(row, dict)
                or set(row) != {"version", "tree_sha256", "metadata_sha256", "old"}
                or row.get("version") != expected["version"]
                or row.get("tree_sha256") != expected["sha256"]
                or not SHA.fullmatch(str(row.get("metadata_sha256"))) or row.get("old") != "absent"):
            raise RuntimeError("invalid resource transaction journal")
    database = value.get("database")
    if (not isinstance(database, dict)
            or set(database) != {"path", "sha256", "size", "mode", "uid", "gid"}
            or database.get("path") != str(value_paths["database"])
            or not SHA.fullmatch(str(database.get("sha256")))
            or not all(isinstance(database.get(k), int) for k in ("size", "mode", "uid", "gid"))):
        raise RuntimeError("invalid resource transaction journal")
    return value


def read_journal(value_paths):
    value, raw = read_record(value_paths["journal"])
    return journal_shape(value, value_paths), raw


def read_bootstrap(value_paths):
    value, _ = read_record(value_paths["bootstrap"])
    if not isinstance(value, dict) or set(value) != {"schema", "journal"} or value.get("schema") != BOOTSTRAP_SCHEMA:
        raise RuntimeError("invalid resource bootstrap record")
    state = journal_shape(value.get("journal"), value_paths)
    if state["phase"] != "initializing":
        raise RuntimeError("invalid resource bootstrap phase")
    return state


def clear_bootstrap(value_paths):
    bootstrap = value_paths["bootstrap"]
    if bootstrap.exists() or bootstrap.is_symlink():
        regular(bootstrap, MAX_RECORD)
        bootstrap.unlink(); fsync_dir(bootstrap.parent)


def reconcile_bootstrap(value_paths):
    """Reconcile a crash before the recovery journal became authoritative."""
    state = read_bootstrap(value_paths)
    if any((value_paths["addons"] / addon_id).exists()
           or (value_paths["addons"] / addon_id).is_symlink() for addon_id in IDS):
        raise RuntimeError("resource target appeared during bootstrap")
    expected = {k: state["database"][k] for k in ("sha256", "size", "mode", "uid", "gid")}
    no_sidecars(value_paths["database"])
    if db_state(value_paths["database"]) != expected or db_rows(value_paths["database"]):
        raise RuntimeError("database changed during bootstrap")
    root = value_paths["root"]
    if root.exists() or root.is_symlink():
        private_directory(root)
        children = list(root.iterdir())
        for item in children:
            prefix = value_paths["journal"].name + ".pending."
            if not item.name.startswith(prefix) or item.is_symlink() or not item.is_file():
                raise RuntimeError("foreign state in unjournaled recovery root")
            pending, _ = read_pending(item)
            if journal_shape(pending, value_paths) != state:
                raise RuntimeError("bootstrap and pending journal differ")
        quarantine = safe_absolute(root.parent / (
            ".arctic3410-resource-bootstrap-failed-" + state["transaction_nonce"]))
        if quarantine.exists() or quarantine.is_symlink():
            raise RuntimeError("bootstrap recovery evidence already exists")
        os.replace(root, quarantine); fsync_dir(root.parent)
    clear_bootstrap(value_paths)
    return state


def reconcile_pending_bootstrap(value_paths):
    """Quarantine an exact fsynced bootstrap intent left before its rename."""
    records = pending_records(value_paths["bootstrap"])
    if len(records) != 1:
        raise RuntimeError("bootstrap pending namespace is ambiguous")
    value, raw = read_pending(records[0])
    if not isinstance(value, dict) or set(value) != {"schema", "journal"} or value.get("schema") != BOOTSTRAP_SCHEMA:
        raise RuntimeError("invalid pending bootstrap record")
    state = journal_shape(value.get("journal"), value_paths)
    if state["phase"] != "initializing":
        raise RuntimeError("invalid pending bootstrap phase")
    no_sidecars(value_paths["database"])
    expected = {k: state["database"][k] for k in ("sha256", "size", "mode", "uid", "gid")}
    if db_state(value_paths["database"]) != expected or db_rows(value_paths["database"]):
        raise RuntimeError("database changed after pending bootstrap intent")
    if any((value_paths["addons"] / addon_id).exists()
           or (value_paths["addons"] / addon_id).is_symlink() for addon_id in IDS):
        raise RuntimeError("resource target appeared after pending bootstrap intent")
    if value_paths["root"].exists() or value_paths["root"].is_symlink():
        raise RuntimeError("recovery root exists without committed bootstrap")
    evidence = safe_absolute(value_paths["kodi"] / (
        ".arctic3410-resource-bootstrap-pending-" + state["transaction_nonce"] + ".json"))
    if evidence.exists() or evidence.is_symlink():
        raise RuntimeError("pending bootstrap evidence already exists")
    _commit_record(records[0], evidence); fsync_dir(evidence.parent)
    if evidence.read_bytes() != raw:
        raise RuntimeError("pending bootstrap quarantine mismatch")
    return state


def set_phase(transaction, phase, *, accepted_receipt_sha256=None):
    state = dict(transaction["state"]); state["phase"] = phase
    if phase == "accepted":
        if not SHA.fullmatch(str(accepted_receipt_sha256)):
            raise ValueError("accepted receipt hash is required")
        state["accepted_receipt_sha256"] = accepted_receipt_sha256
    elif state.get("accepted_receipt_sha256") is not None:
        raise RuntimeError("accepted receipt binding cannot be removed")
    atomic_record(transaction["paths"]["journal"], state)
    transaction["state"] = state


def systemctl(*args):
    return subprocess.run(["systemctl", *args], text=True, capture_output=True,
                          timeout=30, check=False)


def kodi_state():
    result = systemctl("show", "kodi", "--property=ActiveState,SubState,MainPID", "--no-pager")
    if result.returncode:
        raise RuntimeError("Kodi unit inspection failed")
    values = {}
    for line in result.stdout.splitlines():
        key, sep, value = line.partition("=")
        if not sep or key in values:
            raise RuntimeError("invalid Kodi unit state")
        values[key] = value
    if set(values) != {"ActiveState", "SubState", "MainPID"} or not values["MainPID"].isdigit():
        raise RuntimeError("invalid Kodi unit state")
    return values["ActiveState"], values["SubState"], int(values["MainPID"])


def require_stopped(reader=kodi_state):
    active, sub, pid = reader()
    if active not in {"inactive", "failed"} or sub not in {"dead", "failed"} or pid:
        raise RuntimeError("Kodi is not proved stopped")


def accepted_shape(value, state, value_paths):
    keys = {"schema", "release", "state", "cohort", "profile_binding_sha256",
            "transaction_nonce", "lock_path", "database_schema", "pre_database_sha256",
            "post_database_sha256", "resources"}
    if (not isinstance(value, dict) or set(value) != keys or value.get("schema") != RECEIPT_SCHEMA
            or value.get("release") != RELEASE or value.get("state") != "accepted"
            or value.get("cohort") != state["cohort"]
            or value.get("profile_binding_sha256") != state["profile_binding_sha256"]
            or value.get("transaction_nonce") != state["transaction_nonce"]
            or value.get("lock_path") != str(value_paths["lock"])
            or value.get("database_schema") != DATABASE_SCHEMA
            or value.get("pre_database_sha256") != state["database"]["sha256"]
            or not SHA.fullmatch(str(value.get("post_database_sha256")))
            or not isinstance(value.get("resources"), dict) or set(value["resources"]) != set(IDS)):
        raise RuntimeError("invalid accepted resource receipt")
    for addon_id in IDS:
        pin = PINS[addon_id]; row = value["resources"][addon_id]
        if row != {"version": pin["version"], "tree_sha256": pin["sha256"],
                   "enabled": True, "disabled_reason": 0}:
            raise RuntimeError("invalid accepted resource receipt")
    return value


def verify_accepted(storage_root, *, lock):
    """Prove idempotence only through this module's accepted journal+receipt."""
    value_paths = paths(storage_root); require_lock(lock, value_paths["lock"])
    state, _ = read_journal(value_paths)
    if state["phase"] != "accepted":
        raise RuntimeError("resource transaction is not accepted")
    receipt, raw = read_record(value_paths["receipt"])
    receipt = accepted_shape(receipt, state, value_paths)
    if sha(raw) != state["accepted_receipt_sha256"]:
        raise RuntimeError("accepted resource receipt changed")
    for addon_id in IDS:
        actual = resource(value_paths["addons"] / addon_id, addon_id)
        if actual != {k: state["resources"][addon_id][k]
                      for k in ("version", "tree_sha256", "metadata_sha256")}:
            raise RuntimeError("accepted resource tree changed")
    if db_rows(value_paths["database"]) != {addon_id: (1, 0) for addon_id in IDS}:
        raise RuntimeError("accepted resource registration changed")
    # The complete post-DB hash is immutable transaction provenance.  Later
    # unrelated Kodi add-on activity may legitimately change the database, so
    # idempotence is the accepted receipt plus the exact two trees and rows,
    # not a permanent freeze of every other add-on record.
    return {"receipt": receipt, "receipt_sha256": sha(raw)}


def plan(storage_root, source_root, *, lock):
    value_paths = paths(storage_root); require_lock(lock, value_paths["lock"])
    reviewed = sources(source_root)
    present = {addon_id for addon_id in IDS
               if (value_paths["addons"] / addon_id).exists()
               or (value_paths["addons"] / addon_id).is_symlink()}
    rows = db_rows(value_paths["database"])
    bootstrap_pending = pending_records(value_paths["bootstrap"])
    if (not present and not rows and not value_paths["root"].exists()
            and not value_paths["bootstrap"].exists() and not bootstrap_pending):
        return {"release": RELEASE, "changes": list(IDS), "sources": reviewed}
    if present or rows or value_paths["root"].exists():
        accepted = verify_accepted(storage_root, lock=lock)
        return {"release": RELEASE, "changes": [], "sources": reviewed, **accepted}
    raise RuntimeError("partial or foreign resource state")


def prepare(storage_root, source_root, *, cohort, profile_binding_sha256,
            transaction_nonce, lock, restart_on_error, state_reader=kodi_state):
    if cohort not in {"local", "remote"} or not SHA.fullmatch(str(profile_binding_sha256)) or not SHA.fullmatch(str(transaction_nonce)):
        raise ValueError("invalid paired resource transaction binding")
    if not callable(restart_on_error):
        raise ValueError("restart_on_error callback is required")
    value_paths = paths(storage_root); require_lock(lock, value_paths["lock"])
    # From this point onward the caller has declared normal Kodi intentionally
    # stopped.  Every safely recoverable failure below therefore restarts it.
    # An unproved stop is the exception: issuing another start would race an
    # unknown process, so fail before entering the recovery block.
    require_stopped(state_reader)
    transaction = None
    database = None
    try:
        current = plan(storage_root, source_root, lock=lock)
        if not current["changes"]:
            return None
        no_sidecars(value_paths["database"])
        database = db_state(value_paths["database"])
        state = {"schema": JOURNAL_SCHEMA, "release": RELEASE, "phase": "initializing",
                 "cohort": cohort, "profile_binding_sha256": profile_binding_sha256,
                 "transaction_nonce": transaction_nonce, "storage_root": str(value_paths["storage"]),
                 "accepted_receipt_sha256": None,
                 "resources": {addon_id: {**current["sources"][addon_id], "old": "absent"}
                               for addon_id in IDS},
                 "database": {"path": str(value_paths["database"]), **database}}
        if value_paths["bootstrap"].exists() or value_paths["bootstrap"].is_symlink():
            raise RuntimeError("foreign or unfinished resource bootstrap exists")
        atomic_record(value_paths["bootstrap"], {"schema": BOOTSTRAP_SCHEMA, "journal": state})
        value_paths["root"].mkdir(mode=0o700); fsync_dir(value_paths["root"].parent)
        atomic_record(value_paths["journal"], state)
        clear_bootstrap(value_paths)
        transaction = {"paths": value_paths, "state": state}
        value_paths["candidates"].mkdir(mode=0o700)
        source = safe_absolute(source_root).resolve()
        for addon_id in IDS:
            shutil.copytree(source / addon_id, value_paths["candidates"] / addon_id,
                            copy_function=shutil.copy2, symlinks=False)
            if resource(value_paths["candidates"] / addon_id, addon_id) != current["sources"][addon_id]:
                raise RuntimeError("resource candidate metadata changed during copy")
        shutil.copy2(value_paths["database"], value_paths["backup"], follow_symlinks=False)
        if db_state(value_paths["backup"]) != database:
            raise RuntimeError("add-on database backup mismatch")
        for item in sorted(value_paths["root"].rglob("*")):
            if item.is_file(): fsync_file(item)
        for item in sorted((p for p in value_paths["root"].rglob("*") if p.is_dir()),
                           key=lambda p: len(p.parts), reverse=True): fsync_dir(item)
        fsync_dir(value_paths["root"]); set_phase(transaction, "prepared")
        return transaction
    except BaseException as failure:
        try:
            if transaction is None and value_paths["journal"].is_file():
                transaction = load(storage_root, lock=lock)
            if transaction is not None:
                rollback(transaction, lock=lock, state_reader=state_reader)
                clear_bootstrap(value_paths)
            else:
                if value_paths["bootstrap"].exists():
                    reconcile_bootstrap(value_paths)
                else:
                    require(not any((value_paths["addons"] / addon_id).exists()
                                    for addon_id in IDS),
                            "resource target appeared before bootstrap commit")
                    require(not db_rows(value_paths["database"]),
                            "resource rows appeared before bootstrap commit")
            restart_on_error()
        except BaseException as recovery:
            raise RuntimeError("resource preparation failed; old Kodi restart withheld") from recovery
        raise failure


def load(storage_root, *, lock):
    value_paths = paths(storage_root); require_lock(lock, value_paths["lock"])
    state, _ = read_journal(value_paths)
    return {"paths": value_paths, "state": state}


def _rename(source, target):
    os.replace(source, target)


def install_directories(transaction, *, lock, state_reader=kodi_state):
    value_paths = transaction["paths"]; require_lock(lock, value_paths["lock"]); require_stopped(state_reader)
    state, _ = read_journal(value_paths)
    if state != transaction["state"] or state["phase"] != "prepared":
        raise RuntimeError("resource transaction is not prepared")
    no_sidecars(value_paths["database"])
    expected_db = {k: state["database"][k] for k in ("sha256", "size", "mode", "uid", "gid")}
    if db_state(value_paths["database"]) != expected_db:
        raise RuntimeError("add-on database changed after snapshot")
    for addon_id in IDS:
        target = value_paths["addons"] / addon_id; candidate = value_paths["candidates"] / addon_id
        if target.exists() or target.is_symlink():
            raise RuntimeError("resource target appeared during transaction")
        if resource(candidate, addon_id) != {k: state["resources"][addon_id][k]
                                             for k in ("version", "tree_sha256", "metadata_sha256")}:
            raise RuntimeError("resource candidate changed before rename")
        _rename(candidate, target)
        fsync_dir(value_paths["candidates"]); fsync_dir(value_paths["addons"])
    set_phase(transaction, "directories-installed")


def default_rpc(method, params=None):
    import socket
    request = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None: request["params"] = params
    try:
        with socket.create_connection(("127.0.0.1", 9090), timeout=5) as client:
            deadline = time.monotonic() + 5
            client.sendall((json.dumps(request, separators=(",", ":")) + "\n").encode())
            data = b""
            while len(data) <= 65536:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if data: raise RuntimeError("Kodi JSON-RPC incomplete or invalid response")
                    raise RPCNotReady("Kodi JSON-RPC transport deadline")
                client.settimeout(remaining)
                chunk = client.recv(4096)
                if not chunk:
                    if data: raise RuntimeError("Kodi JSON-RPC incomplete or invalid response")
                    raise RPCNotReady("Kodi JSON-RPC transport closed")
                data += chunk
                try: response = json.loads(data)
                except UnicodeDecodeError as exc:
                    raise RuntimeError("Kodi JSON-RPC invalid UTF-8") from exc
                except json.JSONDecodeError:
                    continue
                if (not isinstance(response, dict) or response.get("id") != 1
                        or response.get("jsonrpc") != "2.0" or "error" in response
                        or "result" not in response):
                    raise RuntimeError("Kodi JSON-RPC semantic failure")
                return response["result"]
    except (TimeoutError, OSError) as exc:
        raise RPCNotReady("Kodi JSON-RPC transport unavailable") from exc
    raise RuntimeError("Kodi JSON-RPC response oversized")


def start_kodi():
    result = systemctl("start", "kodi")
    if result.returncode: raise RuntimeError("Kodi start failed")


def stop_kodi(state_reader=kodi_state, clock=time.monotonic, sleeper=time.sleep):
    result = systemctl("stop", "kodi")
    if result.returncode: raise RuntimeError("Kodi stop failed")
    deadline = clock() + 45; last = None
    while clock() < deadline:
        try: require_stopped(state_reader); return
        except Exception as exc: last = exc; sleeper(min(.25, max(0, deadline - clock())))
    raise RuntimeError("Kodi stop could not be proved") from last


class RPCNotReady(OSError):
    """Only this transport condition is retryable during Kodi startup."""


def wait_ready(rpc, clock=time.monotonic, sleeper=time.sleep):
    deadline = clock() + 60; last = None
    while clock() < deadline:
        try:
            result = rpc("Player.GetActivePlayers")
        except (RPCNotReady, ConnectionRefusedError, ConnectionResetError, TimeoutError) as exc:
            last = exc; sleeper(min(.25, max(0, deadline - clock()))); continue
        if result != []:
            raise RuntimeError("Kodi unexpectedly started playback")
        return
    raise RuntimeError("Kodi readiness deadline expired") from last


def native_enable(rpc):
    """One semantic attempt per resource; only readiness is retried."""
    for addon_id in IDS:
        if rpc("Addons.SetAddonEnabled", {"addonid": addon_id, "enabled": True}) != "OK":
            raise RuntimeError("Kodi rejected resource enable: " + addon_id)
        details = rpc("Addons.GetAddonDetails", {"addonid": addon_id,
                                                  "properties": ["enabled", "version"]})
        addon = details.get("addon") if isinstance(details, dict) else None
        if (not isinstance(addon, dict) or addon.get("addonid") != addon_id
                or addon.get("enabled") is not True or addon.get("version") != PINS[addon_id]["version"]):
            raise RuntimeError("Kodi resource registration proof failed: " + addon_id)


def prove_owned_database_delta(candidate, backup):
    candidate_state, backup_state = db_state(candidate), db_state(backup)
    for key in ("mode", "uid", "gid"):
        if candidate_state[key] != backup_state[key]:
            raise RuntimeError("add-on database metadata changed during transaction")
    if db_rows(backup):
        raise RuntimeError("pre-change database unexpectedly contains resource rows")
    rows = db_rows(candidate)
    if not set(rows).issubset(IDS):
        raise RuntimeError("foreign resource rows appeared during transaction")
    if db_semantic(candidate, omit_resources=True) != db_semantic(backup, omit_resources=True):
        raise RuntimeError("non-resource database content changed during transaction")


def restore_database(transaction):
    value_paths, old = transaction["paths"], transaction["state"]["database"]
    expected = {k: old[k] for k in ("sha256", "size", "mode", "uid", "gid")}
    if db_state(value_paths["backup"]) != expected:
        raise RuntimeError("database backup drift")
    if db_rows(value_paths["backup"]):
        raise RuntimeError("database backup has foreign resource rows")
    failed = private_directory(value_paths["failed"], create=True)
    evidence = failed / (DATABASE_NAME + ".failed")
    database = value_paths["database"]
    temporary = database.with_name(
        DATABASE_NAME + ".restore." + transaction["state"]["transaction_nonce"] + ".tmp")
    if ((temporary.exists() or temporary.is_symlink())
            and transaction["state"]["phase"] != "rollback-db-preserved"):
        raise RuntimeError("foreign restore temporary predates durable recovery phase")
    if database.exists() or database.is_symlink():
        current = db_state(database)
        if current == expected:
            if evidence.exists():
                prove_owned_database_delta(evidence, value_paths["backup"])
                set_phase(transaction, "rollback-db-restored")
            return
        prove_owned_database_delta(database, value_paths["backup"])
        if evidence.exists() or evidence.is_symlink():
            raise RuntimeError("foreign failed database evidence exists")
        # CAS immediately before the destructive rename.  A concurrent writer
        # after semantic proof is never overwritten.
        if db_state(database) != current:
            raise RuntimeError("database changed during rollback CAS")
        os.replace(database, evidence); fsync_dir(database.parent); fsync_dir(failed)
        set_phase(transaction, "rollback-db-preserved")
    else:
        if not evidence.is_file() or evidence.is_symlink():
            raise RuntimeError("database disappeared without owned failed evidence")
        prove_owned_database_delta(evidence, value_paths["backup"])
        if transaction["state"]["phase"] != "rollback-db-preserved":
            set_phase(transaction, "rollback-db-preserved")
    if temporary.exists() or temporary.is_symlink():
        if temporary.is_symlink() or not temporary.is_file():
            raise RuntimeError("foreign restore temporary exists")
        # Once the exact live DB is durably preserved, this fixed private path
        # can only be our interrupted copy.  Accept it if complete; otherwise
        # remove only that owned regular temporary and recopy the backup.
        if transaction["state"]["phase"] != "rollback-db-preserved":
            raise RuntimeError("restore temporary is not bound to a durable recovery phase")
        info = temporary.stat(follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != expected["uid"] or info.st_gid != expected["gid"]
                or stat.S_IMODE(info.st_mode) != expected["mode"]
                or info.st_size > expected["size"]):
            raise RuntimeError("restore temporary metadata is unsafe")
        try:
            complete = db_state(temporary) == expected
        except RuntimeError:
            complete = False
        if not complete:
            temporary.unlink(); fsync_dir(temporary.parent)
    if not temporary.exists():
        shutil.copy2(value_paths["backup"], temporary, follow_symlinks=False); fsync_file(temporary)
    if db_state(temporary) != expected:
        raise RuntimeError("database restore temporary mismatch")
    os.replace(temporary, database); fsync_dir(database.parent)
    if db_state(database) != expected: raise RuntimeError("database restoration mismatch")
    set_phase(transaction, "rollback-db-restored")


def preflight_database_recovery(value_paths, old):
    """Prove a restorable DB layout before moving either live resource tree."""
    expected = {k: old[k] for k in ("sha256", "size", "mode", "uid", "gid")}
    backup = value_paths["backup"]
    if db_state(backup) != expected or db_rows(backup):
        raise RuntimeError("database backup is not the exact clean snapshot")
    database = value_paths["database"]
    evidence = value_paths["failed"] / (DATABASE_NAME + ".failed")
    if database.exists() or database.is_symlink():
        current = db_state(database)
        if current != expected:
            prove_owned_database_delta(database, backup)
        if evidence.exists():
            if current != expected:
                raise RuntimeError("live and failed changed databases both exist")
            prove_owned_database_delta(evidence, backup)
    else:
        if not evidence.is_file() or evidence.is_symlink():
            raise RuntimeError("database disappeared without owned failed evidence")
        prove_owned_database_delta(evidence, backup)


def rollback(transaction, *, lock, state_reader=kodi_state, allow_accepted=False):
    value_paths = transaction["paths"]; require_lock(lock, value_paths["lock"]); require_stopped(state_reader)
    state, _ = read_journal(value_paths)
    if state != transaction["state"]: raise RuntimeError("resource journal changed")
    if state["phase"] == "accepted" and not allow_accepted: raise RuntimeError("accepted resource rollback refused")
    if state["phase"] == "rolled-back": return
    no_sidecars(value_paths["database"])
    expected_db = {k: state["database"][k] for k in ("sha256", "size", "mode", "uid", "gid")}
    if state["phase"] == "initializing":
        if db_state(value_paths["database"]) != expected_db or db_rows(value_paths["database"]):
            raise RuntimeError("database changed during transaction initialization")
    else:
        preflight_database_recovery(value_paths, state["database"])
    # Preflight the complete pair before the first rename.  A replaced target
    # quarantines the whole recovery state without producing a half-rollback.
    failed = value_paths["failed"]
    if failed.exists() or failed.is_symlink():
        private_directory(failed)
    actions = []
    for addon_id in IDS:
        target = value_paths["addons"] / addon_id; candidate = value_paths["candidates"] / addon_id
        candidate_evidence = failed / (
            addon_id + ".candidate." + state["transaction_nonce"])
        if target.exists() or target.is_symlink():
            try:
                actual = resource(target, addon_id)
            except (ValueError, OSError) as exc:
                raise RuntimeError("resource target changed; rollback quarantined") from exc
            expected = {k: state["resources"][addon_id][k] for k in actual}
            if actual != expected:
                raise RuntimeError("resource target changed; rollback quarantined")
            actions.append(("target", addon_id, target))
        elif candidate.exists():
            # During initializing, copytree may have been interrupted at any
            # byte.  This exact owned candidate root has never been eligible
            # for rename, so it is safe to remove without accepting its bytes.
            if state["phase"] != "initializing":
                try:
                    actual = resource(candidate, addon_id)
                except (ValueError, OSError) as exc:
                    raise RuntimeError("resource candidate changed; rollback quarantined") from exc
                expected = {k: state["resources"][addon_id][k] for k in actual}
                if actual != expected:
                    raise RuntimeError("resource candidate changed; rollback quarantined")
            actions.append(("candidate", addon_id, candidate))
        elif candidate_evidence.exists() or candidate_evidence.is_symlink():
            if candidate_evidence.is_symlink() or not candidate_evidence.is_dir():
                raise RuntimeError("candidate evidence is unsafe")
            if state["phase"] == "initializing":
                tree_state(candidate_evidence)
            else:
                actual = resource(candidate_evidence, addon_id)
                expected = {k: state["resources"][addon_id][k] for k in actual}
                if actual != expected:
                    raise RuntimeError("candidate evidence changed; rollback quarantined")
            actions.append(("candidate-preserved", addon_id, candidate_evidence))
        elif (failed / addon_id).exists():
            try:
                actual = resource(failed / addon_id, addon_id)
            except (ValueError, OSError) as exc:
                raise RuntimeError("failed resource evidence changed; rollback quarantined") from exc
            expected = {k: state["resources"][addon_id][k] for k in actual}
            if actual != expected:
                raise RuntimeError("failed resource evidence changed; rollback quarantined")
            actions.append(("preserved", addon_id, failed / addon_id))
        elif state["phase"] not in {"initializing", "prepared", "rollback-db-restored"}:
            raise RuntimeError("resource disappeared; rollback quarantined")
    for kind, addon_id, source in actions:
        destination = (failed / addon_id if kind == "target" else
                       failed / (addon_id + ".candidate." + state["transaction_nonce"]))
        if kind == "target" and (destination.exists() or destination.is_symlink()):
            raise RuntimeError("foreign failed resource evidence exists")
        if kind == "candidate" and (destination.exists() or destination.is_symlink()):
            raise RuntimeError("foreign candidate evidence exists")
    private_directory(failed, create=True)
    for kind, addon_id, source in actions:
        if kind == "target":
            os.replace(source, failed / addon_id)
            fsync_dir(value_paths["addons"]); fsync_dir(failed)
        elif kind == "candidate":
            os.replace(source, failed / (
                addon_id + ".candidate." + state["transaction_nonce"]))
            fsync_dir(value_paths["candidates"]); fsync_dir(failed)
    if not value_paths["database"].exists() or db_state(value_paths["database"]) != expected_db:
        restore_database(transaction)
    if any((value_paths["addons"] / addon_id).exists() for addon_id in IDS) or db_rows(value_paths["database"]):
        raise RuntimeError("resource rollback verification failed")
    set_phase(transaction, "rolled-back")


def activate_native(transaction, *, lock, start=start_kodi, stop=stop_kodi,
                    state_reader=kodi_state, rpc=default_rpc, clock=time.monotonic,
                    sleeper=time.sleep):
    value_paths = transaction["paths"]; require_lock(lock, value_paths["lock"])
    state, _ = read_journal(value_paths)
    if state != transaction["state"] or state["phase"] != "directories-installed":
        raise RuntimeError("resource directories are not ready")
    require_stopped(state_reader)
    try:
        start(); wait_ready(rpc, clock, sleeper); native_enable(rpc)
        stop(); require_stopped(state_reader); no_sidecars(value_paths["database"])
        if db_rows(value_paths["database"]) != {addon_id: (1, 0) for addon_id in IDS}:
            raise RuntimeError("authoritative stopped database readback failed")
        prove_owned_database_delta(value_paths["database"], value_paths["backup"])
        for addon_id in IDS:
            actual = resource(value_paths["addons"] / addon_id, addon_id)
            expected = {k: state["resources"][addon_id][k] for k in actual}
            if actual != expected:
                raise RuntimeError("resource changed during native activation")
        set_phase(transaction, "verified")
    except BaseException as failure:
        try:
            stop(); require_stopped(state_reader)
            rollback(transaction, lock=lock, state_reader=state_reader)
            start()
        except BaseException as recovery:
            raise RuntimeError("resource failure quarantined; old Kodi restart withheld") from recovery
        raise failure


def prove_acceptance_live(transaction, receipt, *, state_reader):
    value_paths, state = transaction["paths"], transaction["state"]
    require_stopped(state_reader); no_sidecars(value_paths["database"])
    accepted_shape(receipt, state, value_paths)
    state, _ = read_journal(value_paths)
    if state != transaction["state"] or state["phase"] != "verified":
        raise RuntimeError("resource journal changed before acceptance")
    for addon_id in IDS:
        actual = resource(value_paths["addons"] / addon_id, addon_id)
        expected = {k: state["resources"][addon_id][k] for k in actual}
        if actual != expected:
            raise RuntimeError("resource changed before acceptance")
    if db_rows(value_paths["database"]) != {addon_id: (1, 0) for addon_id in IDS}:
        raise RuntimeError("resource registration changed before acceptance")
    prove_owned_database_delta(value_paths["database"], value_paths["backup"])
    post = db_state(value_paths["database"])
    if post["sha256"] != receipt["post_database_sha256"]:
        raise RuntimeError("post-registration database changed before acceptance")


def prove_acceptance(transaction, receipt, *, state_reader, expected_raw=None):
    value_paths = transaction["paths"]
    actual_receipt, raw = read_record(value_paths["receipt"])
    if expected_raw is not None and raw != expected_raw:
        raise RuntimeError("acceptance receipt changed before commit")
    if actual_receipt != receipt:
        raise RuntimeError("acceptance receipt content changed before commit")
    prove_acceptance_live(transaction, receipt, state_reader=state_reader)
    return raw


def accept(transaction, *, lock, state_reader=kodi_state):
    value_paths = transaction["paths"]; require_lock(lock, value_paths["lock"])
    require_stopped(state_reader); no_sidecars(value_paths["database"])
    state, _ = read_journal(value_paths)
    if state != transaction["state"] or state["phase"] != "verified":
        raise RuntimeError("resources are not verified")
    for addon_id in IDS:
        actual = resource(value_paths["addons"] / addon_id, addon_id)
        expected = {k: state["resources"][addon_id][k] for k in actual}
        if actual != expected:
            raise RuntimeError("resource changed before acceptance")
    if db_rows(value_paths["database"]) != {addon_id: (1, 0) for addon_id in IDS}:
        raise RuntimeError("resource registration changed before acceptance")
    prove_owned_database_delta(value_paths["database"], value_paths["backup"])
    post = db_state(value_paths["database"])
    receipt = {"schema": RECEIPT_SCHEMA, "release": RELEASE, "state": "accepted",
               "cohort": state["cohort"], "profile_binding_sha256": state["profile_binding_sha256"],
               "transaction_nonce": state["transaction_nonce"], "lock_path": str(value_paths["lock"]),
               "database_schema": DATABASE_SCHEMA, "pre_database_sha256": state["database"]["sha256"],
               "post_database_sha256": post["sha256"],
               "resources": {addon_id: {"version": PINS[addon_id]["version"],
                                         "tree_sha256": PINS[addon_id]["sha256"],
                                         "enabled": True, "disabled_reason": 0} for addon_id in IDS}}
    if value_paths["receipt"].exists() or value_paths["receipt"].is_symlink():
        raise RuntimeError("foreign dependency acceptance receipt exists")
    receipt_raw = canonical(receipt)
    atomic_record(value_paths["receipt"], receipt)
    prove_acceptance(transaction, receipt, state_reader=state_reader,
                     expected_raw=receipt_raw)
    set_phase(transaction, "accepted", accepted_receipt_sha256=sha(receipt_raw))
    verified = verify_accepted(value_paths["storage"], lock=lock)
    return verified


def recover(storage_root, *, lock, state_reader=kodi_state, stop=stop_kodi,
            start=start_kodi, restart_old=True):
    value_paths = paths(storage_root); require_lock(lock, value_paths["lock"])
    bootstrap_pending = pending_records(value_paths["bootstrap"])
    if (not value_paths["bootstrap"].exists() and bootstrap_pending):
        try: require_stopped(state_reader)
        except RuntimeError: stop(); require_stopped(state_reader)
        reconcile_pending_bootstrap(value_paths)
        if restart_old: start()
        return {"state": "bootstrap-pending-rolled-back"}
    if value_paths["bootstrap"].exists() or value_paths["bootstrap"].is_symlink():
        try: require_stopped(state_reader)
        except RuntimeError: stop(); require_stopped(state_reader)
        bootstrap_state = read_bootstrap(value_paths)
        if value_paths["journal"].exists():
            journal_state, _ = read_journal(value_paths)
            for key in ("release", "cohort", "profile_binding_sha256", "transaction_nonce",
                        "storage_root", "resources", "database"):
                if journal_state[key] != bootstrap_state[key]:
                    raise RuntimeError("bootstrap/journal binding mismatch")
            clear_bootstrap(value_paths)
        else:
            reconcile_bootstrap(value_paths)
            if restart_old: start()
            return {"state": "bootstrap-rolled-back"}
    transaction = load(storage_root, lock=lock)
    if transaction["state"]["phase"] == "accepted":
        result = verify_accepted(storage_root, lock=lock)
        if restart_old:
            try: require_stopped(state_reader)
            except RuntimeError: return result
            start()
        return result
    # A crash can occur after the fsynced acceptance receipt and before the
    # accepted journal replacement.  Complete only that exact, live-verified
    # transition; never infer acceptance from installed directories alone.
    receipt_pending = pending_records(transaction["paths"]["receipt"])
    if (transaction["state"]["phase"] == "verified"
            and not transaction["paths"]["receipt"].exists() and receipt_pending):
        if len(receipt_pending) != 1:
            raise RuntimeError("acceptance pending namespace is ambiguous")
        try: require_stopped(state_reader)
        except RuntimeError: stop(); require_stopped(state_reader)
        receipt, raw = read_pending(receipt_pending[0])
        prove_acceptance_live(transaction, receipt, state_reader=state_reader)
        _commit_record(receipt_pending[0], transaction["paths"]["receipt"])
        fsync_dir(transaction["paths"]["receipt"].parent)
        prove_acceptance(transaction, receipt, state_reader=state_reader,
                         expected_raw=raw)
        set_phase(transaction, "accepted", accepted_receipt_sha256=sha(raw))
        result = verify_accepted(storage_root, lock=lock)
        if restart_old: start()
        return result
    if transaction["state"]["phase"] == "verified" and transaction["paths"]["receipt"].exists():
        try: require_stopped(state_reader)
        except RuntimeError: stop(); require_stopped(state_reader)
        receipt, raw = read_record(transaction["paths"]["receipt"])
        prove_acceptance(transaction, receipt, state_reader=state_reader,
                         expected_raw=raw)
        set_phase(transaction, "accepted", accepted_receipt_sha256=sha(raw))
        result = verify_accepted(storage_root, lock=lock)
        if restart_old: start()
        return result
    try: require_stopped(state_reader)
    except RuntimeError: stop(); require_stopped(state_reader)
    rollback(transaction, lock=lock, state_reader=state_reader)
    if restart_old: start()
    return {"state": "rolled-back"}
