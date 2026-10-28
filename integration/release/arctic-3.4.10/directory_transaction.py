"""Recoverable two-rename full-skin switch; no Kodi lifecycle or identity policy.

It is not crash-atomic: a journal records the rename phase so a later adapter
can restore the preserved old tree after power loss.
"""
from __future__ import annotations
import hashlib, os, shutil
from pathlib import Path

def tree_hash(root):
    root=Path(root); h=hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if path.is_symlink(): raise ValueError('symlink in skin tree')
        if path.is_file():
            rel=str(path.relative_to(root)).encode(); h.update(len(rel).to_bytes(4,'big')); h.update(rel)
            data=path.read_bytes(); h.update(len(data).to_bytes(8,'big')); h.update(data)
    return h.hexdigest()

def _unlinked_absolute(path):
    """Reject a path whose leaf *or any parent* is a symlink before resolve."""
    path=Path(os.path.abspath(path))
    current=path
    while True:
        if current.is_symlink(): raise ValueError('symlink in source/target ancestry')
        if current.parent==current: return path
        current=current.parent

def snapshot_protected(root, backup, protected):
    root=Path(root).resolve()
    if backup.exists(): raise RuntimeError('protected backup already exists')
    saved=[]
    for relative in protected:
        relative=Path(relative)
        if relative.is_absolute() or '..' in relative.parts: raise ValueError('unsafe protected path')
        path=root/relative
        current=path
        while current != root:
            if current.is_symlink(): raise ValueError('symlink in protected path')
            current=current.parent
        if path.exists():
            out=Path(backup)/'protected'/relative;out.parent.mkdir(parents=True,exist_ok=True)
            if path.is_dir(): shutil.copytree(path,out)
            else: shutil.copy2(path,out)
            saved.append(relative)
    return saved

def _write_journal(path, phase):
    path.write_text('{"phase":"'+phase+'"}\n'); os.sync()

def replace(target, source, protected=(), verify=tree_hash, recovery_root=None, write_journal=_write_journal):
    """Recoverably switch full trees, retaining the old tree until verification.

    The two same-filesystem renames are intentionally *not* described as one
    atomic transaction: a power loss between them needs journal-led recovery.
    Synchronous exceptions and process-control exceptions are rolled back when
    possible before they are re-raised.
    """
    target,source=_unlinked_absolute(target),_unlinked_absolute(source)
    # Only resolve after inspecting lexical paths: resolve() hides a symlinked
    # target or ancestor, which is unsafe for an appliance update.
    target,source=target.resolve(),source.resolve()
    if target in source.parents or source in target.parents or target==source: raise ValueError('source/target overlap')
    if not target.is_dir() or not source.is_dir() or target.is_symlink() or source.is_symlink(): raise ValueError('regular source/target directories required')
    parent=target.parent
    recovery_root=(_unlinked_absolute(recovery_root) if recovery_root is not None else
                   _unlinked_absolute(parent.parent/'.arctic3410-recovery'))
    recovery_root=recovery_root.resolve()
    if recovery_root in target.parents or target in recovery_root.parents: raise ValueError('unsafe recovery location')
    if recovery_root.exists() and not recovery_root.is_dir(): raise ValueError('recovery root is not a directory')
    recovery_root.mkdir(mode=0o700,parents=True,exist_ok=True)
    if recovery_root.stat().st_dev != parent.stat().st_dev: raise ValueError('recovery must share target filesystem')
    old=recovery_root/(target.name+'.old'); new=recovery_root/(target.name+'.new'); failed=recovery_root/(target.name+'.failed')
    backup=recovery_root/(target.name+'.protected'); journal=recovery_root/(target.name+'.journal.json')
    if any(path.exists() for path in (old,new,failed,backup,journal)): raise RuntimeError('foreign transaction directory exists')
    expected=verify(source); original=verify(target)
    try:
        shutil.copytree(source,new,symlinks=False)
        if verify(new)!=expected: raise RuntimeError('staged skin hash mismatch')
        snapshot_protected(parent.parent,backup,protected)
    except BaseException:
        if new.exists(): shutil.rmtree(new)
        raise
    old_preserved=False
    try:
        # This whole phase is recoverable, not crash-atomic.  In particular a
        # full filesystem after the first rename must restore old immediately.
        write_journal(journal,'prepared')
        os.replace(target,old); old_preserved=True
        write_journal(journal,'old-preserved')
        os.replace(new,target)
        if verify(target)!=expected: raise RuntimeError('installed skin hash mismatch')
        write_journal(journal,'verified')
        return {'old':old,'protected':backup,'hash':expected,'journal':journal}
    except BaseException:
        if old_preserved:
            if target.exists(): os.replace(target,failed)
            if old.exists(): os.replace(old,target)
            if verify(target)!=original:
                raise RuntimeError('rollback tree verification failed')
            # If the second rename never occurred, this is merely the staged
            # candidate rather than recovery evidence.  Remove it so a later
            # guarded transaction does not mistake it for an unfinished swap.
            if new.exists(): shutil.rmtree(new)
            try: write_journal(journal,'rolled-back')
            except Exception: pass # old tree is restored; retain failed evidence
        raise
