"""Durable, recoverable whole-skin directory transaction."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat


JOURNAL_SCHEMA = 2
PHASES = {"initializing", "prepared", "old-preserved", "candidate-installed",
          "verified", "accepted", "rolled-back"}
SHA = re.compile(r"[0-9a-f]{64}\Z")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def tree_hash(root):
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("regular tree required")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("symlink in skin tree")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("special file in skin tree")
        relative = str(path.relative_to(root)).encode()
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _unlinked_absolute(path):
    path = Path(os.path.abspath(path))
    current = path
    while True:
        if current.is_symlink():
            raise ValueError("symlink in source/target ancestry")
        if current.parent == current:
            return path
        current = current.parent


def _relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("unsafe protected path")
    return path


def _metadata(path):
    info = path.stat(follow_symlinks=False)
    if stat.S_ISREG(info.st_mode):
        return {"kind": "file", "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid,
                "gid": info.st_gid, "sha256": sha_bytes(path.read_bytes())}
    if stat.S_ISDIR(info.st_mode):
        return {"kind": "directory", "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid,
                "gid": info.st_gid}
    raise ValueError("special file in protected state")


def _state(path):
    if not path.exists():
        return {"kind": "absent"}
    if path.is_symlink():
        raise ValueError("symlink in protected state")
    if path.is_file():
        return _metadata(path)
    if not path.is_dir():
        raise ValueError("special protected path")
    entries = {".": _metadata(path)}
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise ValueError("symlink in protected state")
        entries[str(item.relative_to(path))] = _metadata(item)
    return {"kind": "directory", "tree_sha256": tree_hash(path), "entries": entries}


def _apply_metadata(path, value):
    os.chmod(path, value["mode"], follow_symlinks=False)
    os.chown(path, value["uid"], value["gid"], follow_symlinks=False)


def _remove_exact(path):
    if not path.exists():
        return
    if path.is_symlink():
        raise RuntimeError("refusing protected symlink removal")
    if path.is_dir():
        shutil.rmtree(path)
    elif path.is_file():
        path.unlink()
    else:
        raise RuntimeError("refusing special protected path removal")


def _fsync_file(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(root):
    root = Path(root)
    for path in sorted(root.rglob("*")):
        if path.is_file():
            _fsync_file(path)
    directories = sorted((item for item in root.rglob("*") if item.is_dir()),
                         key=lambda item: len(item.parts), reverse=True)
    for path in directories:
        _fsync_directory(path)
    _fsync_directory(root)


def _canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _write_journal(path, state):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists():
        raise RuntimeError("foreign transaction journal temporary exists")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical(state))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _quarantine_journal_temporary(transaction):
    """Preserve an interrupted journal write before advancing recovery."""
    temporary = transaction["journal"].with_name(transaction["journal"].name + ".tmp")
    if not temporary.exists():
        return None
    if temporary.is_symlink() or not temporary.is_file():
        raise RuntimeError("unsafe interrupted journal temporary")
    info = temporary.stat(follow_symlinks=False)
    if (info.st_nlink != 1 or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > 16 * 1024 * 1024):
        raise RuntimeError("unsafe interrupted journal temporary metadata")
    payload = temporary.read_bytes()
    evidence = transaction["root"] / "interrupted-journals"
    evidence.mkdir(mode=0o700, exist_ok=True)
    destination = evidence / (sha_bytes(payload) + ".json.partial")
    if destination.exists():
        if destination.is_symlink() or not destination.is_file() or destination.read_bytes() != payload:
            raise RuntimeError("interrupted journal evidence collision")
        temporary.unlink()
    else:
        os.replace(temporary, destination)
    _fsync_directory(evidence)
    _fsync_directory(transaction["root"])
    return destination


def _read_journal(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("transaction journal is missing or unsafe")
    info = path.stat(follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077 or not 0 < info.st_size <= 16 * 1024 * 1024):
        raise RuntimeError("transaction journal metadata is unsafe")
    raw = path.read_bytes()
    value = json.loads(raw)
    required = {"schema", "phase", "target", "old_sha256", "candidate_sha256", "protected", "bindings"}
    if (not isinstance(value, dict) or set(value) != required
            or value.get("schema") != JOURNAL_SCHEMA or value.get("phase") not in PHASES
            or SHA.fullmatch(str(value.get("old_sha256"))) is None
            or SHA.fullmatch(str(value.get("candidate_sha256"))) is None
            or not isinstance(value.get("protected"), dict)
            or not isinstance(value.get("bindings"), dict)
            or any(not isinstance(key, str) or not isinstance(item, str)
                   for key, item in value.get("bindings", {}).items())):
        raise RuntimeError("invalid transaction journal")
    if _canonical(value) != raw:
        raise RuntimeError("noncanonical transaction journal")
    return value


def _paths(target, recovery_root=None):
    target = _unlinked_absolute(target).resolve()
    parent = target.parent
    recovery_root = (_unlinked_absolute(recovery_root) if recovery_root is not None else
                     _unlinked_absolute(parent.parent / ".arctic3410-recovery"))
    recovery_root = recovery_root.resolve()
    if recovery_root in target.parents or target in recovery_root.parents:
        raise ValueError("unsafe recovery location")
    name = target.name
    return {"target": target, "root": recovery_root, "old": recovery_root / (name + ".old"),
            "new": recovery_root / (name + ".new"), "failed": recovery_root / (name + ".failed"),
            "protected": recovery_root / (name + ".protected"),
            "journal": recovery_root / (name + ".journal.json")}


def _capture_protected(root, backup, protected):
    root = Path(root).resolve()
    if backup.exists():
        raise RuntimeError("protected backup already exists")
    backup.mkdir(parents=True, mode=0o700)
    records = {}
    for value in protected:
        relative = _relative(value)
        path = root / relative
        current = path
        while current != root:
            if current.is_symlink():
                raise ValueError("symlink in protected path")
            current = current.parent
        record = _state(path)
        records[str(relative)] = record
        if record["kind"] == "file":
            destination = backup / "protected" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        elif record["kind"] == "directory":
            destination = backup / "protected" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(path, destination)
    _fsync_tree(backup)
    return records


def snapshot_protected(root, backup, protected):
    records = _capture_protected(root, backup, protected)
    return [Path(name) for name, record in records.items() if record["kind"] != "absent"]


def _verify_state(path, expected):
    if _state(path) != expected:
        raise RuntimeError("protected rollback verification failed: " + str(path))


def _restore_protected(root, backup, records):
    root = Path(root).resolve()
    for value, record in records.items():
        relative = _relative(value)
        path = root / relative
        current = path
        while current != root:
            if current.is_symlink():
                raise RuntimeError("symlink appeared in protected path")
            current = current.parent
        _remove_exact(path)
        if record["kind"] == "absent":
            continue
        source = backup / "protected" / relative
        if record["kind"] == "file":
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, path)
            _apply_metadata(path, record)
        elif record["kind"] == "directory":
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, path)
            for name, metadata in sorted(record["entries"].items(),
                                         key=lambda item: len(Path(item[0]).parts), reverse=True):
                _apply_metadata(path if name == "." else path / name, metadata)
        else:
            raise RuntimeError("unknown protected rollback state")
    for value, record in records.items():
        _verify_state(root / _relative(value), record)
        restored = root / _relative(value)
        if restored.is_dir():
            _fsync_tree(restored)
        elif restored.is_file():
            _fsync_file(restored)
        _fsync_directory(restored.parent)


def prepare(target, source, protected=(), recovery_root=None, bindings=None,
            verify=tree_hash, write_journal=_write_journal):
    paths = _paths(target, recovery_root)
    source = _unlinked_absolute(source).resolve()
    target = paths["target"]
    if target in source.parents or source in target.parents or target == source:
        raise ValueError("source/target overlap")
    if not target.is_dir() or not source.is_dir() or target.is_symlink() or source.is_symlink():
        raise ValueError("regular source/target directories required")
    recovery = paths["root"]
    if recovery.exists() and not recovery.is_dir():
        raise ValueError("recovery root is not a directory")
    recovery.mkdir(mode=0o700, parents=True, exist_ok=True)
    if recovery.stat().st_dev != target.parent.stat().st_dev:
        raise ValueError("recovery must share target filesystem")
    if any(path.exists() for name, path in paths.items() if name not in {"target", "root"}):
        raise RuntimeError("foreign transaction state exists")
    bindings = {} if bindings is None else dict(bindings)
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in bindings.items()):
        raise ValueError("transaction bindings must be strings")
    candidate_hash, old_hash = verify(source), verify(target)
    initial = {"schema": JOURNAL_SCHEMA, "phase": "initializing", "target": str(target),
               "old_sha256": old_hash, "candidate_sha256": candidate_hash,
               "protected": {}, "bindings": bindings}
    transaction = {**paths, "state": initial, "verify": verify,
                   "write_journal": write_journal}
    _quarantine_journal_temporary(transaction)
    # A journal temporary can only predate all copies here: prepare does not
    # start copying until the initializing journal atomically commits.
    write_journal(paths["journal"], initial)
    try:
        shutil.copytree(source, paths["new"], symlinks=False)
        if verify(paths["new"]) != candidate_hash:
            raise RuntimeError("staged skin hash mismatch")
        protected_state = _capture_protected(target.parent.parent, paths["protected"], protected)
        state = {"schema": JOURNAL_SCHEMA, "phase": "prepared", "target": str(target),
                 "old_sha256": old_hash, "candidate_sha256": candidate_hash,
                 "protected": protected_state, "bindings": bindings}
        _fsync_tree(paths["new"])
        write_journal(paths["journal"], state)
        transaction["state"] = state
        return transaction
    except BaseException as failure:
        try:
            recovered = load(target, recovery_root, verify=verify,
                             write_journal=write_journal, allow_temporary=True)
            rollback(recovered)
        except BaseException as recovery:
            raise RuntimeError("transaction preparation/recovery failed") from recovery
        raise failure


def _phase(transaction, phase):
    state = dict(transaction["state"])
    state["phase"] = phase
    transaction["write_journal"](transaction["journal"], state)
    transaction["state"] = state


def load(target, recovery_root=None, verify=tree_hash, write_journal=_write_journal,
         allow_temporary=False):
    """Reconstruct an interrupted transaction solely from its durable journal."""
    paths = _paths(target, recovery_root)
    state = _read_journal(paths["journal"])
    if state["target"] != str(paths["target"]):
        raise RuntimeError("transaction journal targets another path")
    temporary = paths["journal"].with_name(paths["journal"].name + ".tmp")
    if temporary.exists() and not allow_temporary:
        raise RuntimeError("interrupted journal temporary requires explicit recovery")
    if (state["phase"] not in {"initializing", "rolled-back"}
            and (not paths["protected"].is_dir() or paths["protected"].is_symlink())):
        raise RuntimeError("protected recovery snapshot is missing or unsafe")
    return {**paths, "state": state, "verify": verify, "write_journal": write_journal}


def rollback(transaction, *, allow_accepted=False):
    _quarantine_journal_temporary(transaction)
    state = _read_journal(transaction["journal"])
    if state != transaction["state"]:
        raise RuntimeError("transaction journal changed")
    if state["phase"] == "accepted" and not allow_accepted:
        raise RuntimeError("refusing automatic rollback of accepted transaction")
    target, old, new, failed = (transaction[name] for name in ("target", "old", "new", "failed"))
    if state["phase"] == "initializing":
        require(not old.exists() and not failed.exists(),
                "rename occurred before prepared journal")
        require(target.is_dir() and transaction["verify"](target) == state["old_sha256"],
                "old skin changed during transaction initialization")
        if new.exists():
            _remove_exact(new)
        if transaction["protected"].exists():
            _remove_exact(transaction["protected"])
        _phase(transaction, "rolled-back")
        return transaction
    # Journal persistence deliberately follows each rename.  If power is lost
    # between the rename and its phase update, the actual old/target layout is
    # authoritative but must still match the two recorded hashes exactly.
    if old.exists() and target.exists():
        if failed.exists():
            raise RuntimeError("foreign failed-candidate evidence exists")
        require(target.is_dir() and transaction["verify"](target) == state["candidate_sha256"],
                "installed candidate changed before rollback")
        os.replace(target, failed)
        _fsync_directory(target.parent)
    if old.exists():
        require(transaction["verify"](old) == state["old_sha256"], "preserved old tree drift")
        os.replace(old, target)
        _fsync_directory(target.parent)
    elif target.exists() and transaction["verify"](target) == state["old_sha256"]:
        # Recovery may have completed both renames before power was lost while
        # committing the rolled-back phase.  Accept only that exact layout.
        if state["phase"] != "prepared":
            require(failed.is_dir() and not failed.is_symlink()
                    and transaction["verify"](failed) == state["candidate_sha256"],
                    "preserved old tree is missing without exact failed candidate")
    else:
        raise RuntimeError("preserved old tree is missing")
    if new.exists():
        shutil.rmtree(new)
    _restore_protected(target.parent.parent, transaction["protected"], state["protected"])
    require(transaction["verify"](target) == state["old_sha256"], "rollback tree verification failed")
    _phase(transaction, "rolled-back")
    return transaction


def switch(transaction):
    state = _read_journal(transaction["journal"])
    if state != transaction["state"] or state["phase"] != "prepared":
        raise RuntimeError("transaction is not prepared")
    target, old, new = (transaction[name] for name in ("target", "old", "new"))
    try:
        require(transaction["verify"](target) == state["old_sha256"],
                "old skin changed after recovery snapshot")
        for relative, expected in state["protected"].items():
            _verify_state(target.parent.parent / _relative(relative), expected)
        os.replace(target, old)
        _fsync_directory(target.parent)
        _phase(transaction, "old-preserved")
        os.replace(new, target)
        _fsync_directory(target.parent)
        _phase(transaction, "candidate-installed")
        if transaction["verify"](target) != state["candidate_sha256"]:
            raise RuntimeError("installed skin hash mismatch")
        _phase(transaction, "verified")
        return transaction
    except BaseException:
        rollback(transaction)
        raise


def accept(transaction, receipt_sha256, acceptance_bindings=None):
    state = _read_journal(transaction["journal"])
    if state != transaction["state"] or state["phase"] != "verified":
        raise RuntimeError("transaction is not verified")
    if SHA.fullmatch(str(receipt_sha256)) is None:
        raise ValueError("invalid accepted receipt hash")
    acceptance_bindings = {} if acceptance_bindings is None else dict(acceptance_bindings)
    if any(not isinstance(key, str) or not isinstance(value, str)
           for key, value in acceptance_bindings.items()):
        raise ValueError("invalid acceptance bindings")
    if "accepted_receipt_sha256" in acceptance_bindings or set(acceptance_bindings) & set(state["bindings"]):
        raise ValueError("acceptance binding overwrites prepared state")
    transaction["state"] = {**state, "bindings": {
        **state["bindings"], **acceptance_bindings,
        "accepted_receipt_sha256": receipt_sha256}}
    _phase(transaction, "accepted")
    return transaction


def replace(target, source, protected=(), verify=tree_hash, recovery_root=None,
            write_journal=_write_journal, bindings=None):
    transaction = prepare(target, source, protected, recovery_root, bindings,
                          verify=verify, write_journal=write_journal)
    switch(transaction)
    return {"old": transaction["old"], "protected": transaction["protected"],
            "hash": transaction["state"]["candidate_sha256"],
            "journal": transaction["journal"], "transaction": transaction}
