#!/usr/bin/env python3
"""Maintain the single-library Jellyfin compatibility view.

Canonical media stays under /data/media/{movies,shows}.  Ordinary files are
hard-linked into the Jellyfin view.  A Dolby Vision Profile 7 video is exposed
only after its validated Profile 8.1 companion exists; the view then links to
the companion instead of the master.  The canonical path and filename are
preserved inside the view, so Jellyfin item paths do not change.

The program is deliberately idempotent.  It caches probes by inode signature,
queues missing P8.1 work, atomically replaces stale view links, and removes
orphan compatibility files only after a grace period.  Dry-run is the default.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from subtitle_view_filter import hidden_sources, retired_sources, digest as subtitle_digest


VIDEO_SUFFIXES = {".mkv", ".mp4", ".m4v", ".ts", ".m2ts", ".avi", ".mov", ".webm"}
COMPAT_SUFFIX = " - P8.1 Compatibility"
EPISODE_KEY = re.compile(r"(?i)\bS\d{1,2}E\d{1,3}(?:-E\d{1,3})?\b")


@dataclass(frozen=True)
class Root:
    name: str
    source: Path
    compatibility: Path
    view: Path


def roots(media_root: Path, compatibility_root: Path, view_root: Path) -> tuple[Root, ...]:
    return tuple(
        Root(name, media_root / name, compatibility_root / name, view_root / name)
        for name in ("movies", "shows")
    )


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS probe (
            path TEXT PRIMARY KEY,
            device INTEGER NOT NULL,
            inode INTEGER NOT NULL,
            size INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            dv_profile INTEGER NOT NULL,
            description TEXT NOT NULL,
            last_seen INTEGER NOT NULL,
            probe_ok INTEGER NOT NULL DEFAULT 1,
            checked_at INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    probe_columns = {row[1] for row in db.execute("PRAGMA table_info(probe)")}
    if "probe_ok" not in probe_columns:
        db.execute("ALTER TABLE probe ADD COLUMN probe_ok INTEGER NOT NULL DEFAULT 1")
    if "checked_at" not in probe_columns:
        db.execute("ALTER TABLE probe ADD COLUMN checked_at INTEGER NOT NULL DEFAULT 0")
        db.execute("UPDATE probe SET checked_at=last_seen WHERE checked_at=0")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS absent (
            path TEXT PRIMARY KEY,
            first_seen INTEGER NOT NULL
        )
        """
    )
    return db


def signature(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def parse_profile(text: str) -> int:
    lowered = text.lower()
    if "dvhe.07" in lowered or "profile 7" in lowered:
        return 7
    if "dvhe.08" in lowered or "profile 8" in lowered:
        return 8
    return 0


PROBE_RETRY_SECONDS = 300


def probe(path: Path, db: sqlite3.Connection, now: int) -> tuple[int | None, str]:
    sig = signature(path)
    row = db.execute(
        "SELECT device,inode,size,mtime_ns,dv_profile,description,probe_ok,checked_at "
        "FROM probe WHERE path=?",
        (str(path),),
    ).fetchone()
    # Before probe_ok existed, a failed mediainfo process was persisted as the
    # same empty/profile-0 shape as an ordinary file.  Real SDR video output is
    # normally the explicit field separator (`|`); an empty description is not
    # trusted.  Invalidate such a legacy row only when its path is encountered,
    # rather than forcing a full-library re-probe after migration.
    if row and int(row[4]) == 0 and not str(row[5]).strip() and int(row[6]):
        due = now - PROBE_RETRY_SECONDS
        db.execute("UPDATE probe SET probe_ok=0,checked_at=? WHERE path=?", (due, str(path)))
        row = (*row[:6], 0, due)
    if row and tuple(row[:4]) == sig and int(row[6]):
        db.execute("UPDATE probe SET last_seen=? WHERE path=?", (now, str(path)))
        return int(row[4]), str(row[5])
    if row and tuple(row[:4]) == sig and now - int(row[7]) < PROBE_RETRY_SECONDS:
        # A failed probe is unknown, never equivalent to SDR/non-P7.  Keep a
        # safe existing P8 view, or withhold a new view until the short retry.
        db.execute("UPDATE probe SET last_seen=? WHERE path=?", (now, str(path)))
        return None, str(row[5])

    # A pool migration or file-preserving rebalance changes the backing
    # device/inode while retaining the file's size and nanosecond mtime.  In
    # that exact case the cached probe still describes the same content.  Move
    # the cache entry to the new inode instead of re-reading every multi-GB
    # video with mediainfo; doing so can otherwise keep the compatibility view
    # stale for days by exhausting the systemd timeout on every pass.
    if row and int(row[6]) and tuple(row[2:4]) == sig[2:4]:
        db.execute(
            "UPDATE probe SET device=?,inode=?,last_seen=? WHERE path=?",
            (sig[0], sig[1], now, str(path)),
        )
        return int(row[4]), str(row[5])

    try:
        result = subprocess.run(
            ["mediainfo", "--Output=Video;%HDR_Format%|%HDR_Format_Profile%", str(path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=90,
        )
        description = result.stdout.strip()
        returncode = result.returncode
    except subprocess.TimeoutExpired:
        description = ""
        returncode = 124
    # Exit zero with no video-field output is still unknown (for example a
    # malformed/no-video container), while the literal `|` is valid SDR output.
    probe_ok = returncode == 0 and bool(description)
    profile = parse_profile(description) if probe_ok else 0
    if not probe_ok:
        description = f"probe-error: mediainfo-exit-{returncode}"
    db.execute(
        """
        INSERT INTO probe(path,device,inode,size,mtime_ns,dv_profile,description,last_seen,probe_ok,checked_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(path) DO UPDATE SET
          device=excluded.device,inode=excluded.inode,size=excluded.size,
          mtime_ns=excluded.mtime_ns,dv_profile=excluded.dv_profile,
          description=excluded.description,last_seen=excluded.last_seen,
          probe_ok=excluded.probe_ok,checked_at=excluded.checked_at
        """,
        (str(path), *sig, profile, description, now, int(probe_ok), now),
    )
    return (profile if probe_ok else None), description


def retry_allows(path: Path, retry_state: Path, now: int) -> bool:
    """Return false for a known unchanged cooldown or an unreadable state DB.

    The converter remains the authoritative enforcement point.  This merely
    prevents reconciler churn; uncertainty deliberately does not enqueue work.
    """
    if not retry_state.exists():
        return True
    stat = path.stat()
    fingerprint = f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}"
    try:
        with sqlite3.connect(f"file:{retry_state}?mode=ro", uri=True, timeout=5) as retry_db:
            row = retry_db.execute(
                "SELECT signature, available FROM retries WHERE path=?", (str(path),)
            ).fetchone()
    except sqlite3.Error as exc:
        print(f"warning: retry state unavailable for {path}: {exc}; withholding queue admission", file=sys.stderr)
        return False
    return not row or row[0] != fingerprint or float(row[1]) <= now


def worker_token(worker: Path) -> str | None:
    if not worker.is_file():
        return None
    match = re.search(r'^JK="([^"]+)"$', worker.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else None


def seed_from_jellyfin(
    db: sqlite3.Connection, url: str, token: str, valid_paths: set[str], now: int
) -> int:
    params = urllib.parse.urlencode(
        {
            "recursive": "true",
            "includeItemTypes": "Movie,Episode",
            "fields": "Path,MediaStreams",
            "enableImages": "false",
            "enableTotalRecordCount": "false",
            "limit": "100000",
        }
    )
    request = urllib.request.Request(
        f"{url.rstrip('/')}/Items?{params}", headers={"Authorization": f'MediaBrowser Token="{token}"'}
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.load(response)
    count = 0
    for item in payload.get("Items", []):
        path_value = item.get("Path")
        if not path_value or path_value not in valid_paths:
            continue
        path = Path(path_value)
        try:
            sig = signature(path)
        except OSError:
            continue
        video = next(
            (stream for stream in item.get("MediaStreams") or [] if stream.get("Type") == "Video"),
            {},
        )
        profile = int(video.get("DvProfile") or 0)
        description = str(video.get("VideoDoViTitle") or video.get("VideoRangeType") or "")
        db.execute(
            """
            INSERT INTO probe(path,device,inode,size,mtime_ns,dv_profile,description,last_seen,probe_ok,checked_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(path) DO UPDATE SET
              device=excluded.device,inode=excluded.inode,size=excluded.size,
              mtime_ns=excluded.mtime_ns,dv_profile=excluded.dv_profile,
              description=excluded.description,last_seen=excluded.last_seen,
              probe_ok=excluded.probe_ok,checked_at=excluded.checked_at
            """,
            (path_value, *sig, profile, description, now, 1, now),
        )
        count += 1
    return count


def compatibility_path(root: Root, source: Path) -> Path:
    relative = source.relative_to(root.source)
    return root.compatibility / relative.with_name(
        f"{relative.stem}{COMPAT_SUFFIX}{relative.suffix}"
    )


def compatibility_fallbacks(root: Root, source: Path) -> list[Path]:
    """Find a preserved P8 sibling after ARR changes the master filename."""
    relative = source.relative_to(root.source)
    directory = root.compatibility / relative.parent
    if not directory.is_dir():
        return []
    candidates = sorted(directory.glob(f"*{COMPAT_SUFFIX}.mkv"))
    if root.name == "movies":
        return candidates if len(candidates) == 1 else []
    match = EPISODE_KEY.search(source.name)
    if not match:
        return []
    key = match.group(0).lower()
    matches = [candidate for candidate in candidates if key in candidate.name.lower()]
    return matches if len(matches) == 1 else []


def master_path(root: Root, compatibility: Path) -> Path | None:
    try:
        relative = compatibility.relative_to(root.compatibility)
    except ValueError:
        return None
    if COMPAT_SUFFIX not in relative.stem:
        return None
    name = relative.stem.removesuffix(COMPAT_SUFFIX) + relative.suffix
    return root.source / relative.with_name(name)


def same_inode(left: Path, right: Path) -> bool:
    try:
        a, b = left.stat(), right.stat()
    except OSError:
        return False
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def atomic_link(source: Path, destination: Path, apply: bool) -> str:
    if same_inode(source, destination):
        return "unchanged"
    if not apply:
        return "would-link"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.stat().st_dev != destination.parent.stat().st_dev:
        raise OSError(f"hardlink crosses filesystems: {source} -> {destination}")
    temporary = destination.parent / f".{destination.name}.link-{os.getpid()}"
    with contextlib.suppress(FileNotFoundError):
        temporary.unlink()
    os.link(source, temporary)
    os.replace(temporary, destination)
    if not same_inode(source, destination):
        raise OSError(f"hardlink verification failed: {destination}")
    return "linked"


def enqueue(path: Path, queue: Path, lock_path: Path, apply: bool) -> bool:
    if not apply:
        return True
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.touch(exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock, queue.open("r+", encoding="utf-8") as handle:
        fcntl.flock(lock, fcntl.LOCK_EX)
        values = {line.rstrip("\n") for line in handle}
        if str(path) in values:
            return False
        handle.seek(0, os.SEEK_END)
        handle.write(str(path) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return True


def unlink(path: Path, apply: bool) -> str:
    if not path.exists() and not path.is_symlink():
        return "missing"
    if not apply:
        return "would-unlink"
    path.unlink()
    return "unlinked"


def remove_empty_dirs(root: Path, apply: bool) -> int:
    if not root.exists():
        return 0
    removed = 0
    for current, _, _ in os.walk(root, topdown=False):
        path = Path(current)
        if path == root:
            continue
        try:
            next(path.iterdir())
        except StopIteration:
            if apply:
                path.rmdir()
            removed += 1
        except OSError:
            continue
    return removed


def notify_jellyfin(url: str, token: str, folders: set[str]) -> int:
    sent = 0
    for folder in sorted(folders):
        body = json.dumps({"Updates": [{"Path": folder, "UpdateType": "Modified"}]}).encode()
        request = urllib.request.Request(
            f"{url.rstrip('/')}/Library/Media/Updated",
            data=body,
            headers={"Authorization": f'MediaBrowser Token="{token}"', "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20):
                sent += 1
        except OSError as exc:
            print(f"warning: Jellyfin notification failed for {folder}: {exc}", file=sys.stderr)
    return sent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--media-root", type=Path, default=Path("/data/media"))
    parser.add_argument(
        "--compatibility-root", type=Path, default=Path("/data/media/compatibility/dovi-p8")
    )
    parser.add_argument(
        "--view-root", type=Path, default=Path("/data/media/compatibility/jellyfin-view")
    )
    parser.add_argument("--queue", type=Path, default=Path("/data/config/_dovi/compat-queue.txt"))
    parser.add_argument("--queue-lock", type=Path, default=Path("/run/dovi-compat-queue.lock"))
    parser.add_argument("--state", type=Path, default=Path("/data/config/_dovi/library-view.sqlite"))
    parser.add_argument("--retry-state", type=Path, default=Path("/data/config/_dovi/retry-state.sqlite"))
    parser.add_argument("--worker", type=Path, default=Path("/data/config/_dovi/process-queue.sh"))
    parser.add_argument("--jellyfin", default="http://192.168.2.172:8096")
    parser.add_argument("--seed-jellyfin", action="store_true")
    parser.add_argument("--notify-jellyfin", action="store_true")
    parser.add_argument("--cleanup-grace", type=int, default=900)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    started = time.monotonic()
    now = int(time.time())
    configured_roots = roots(args.media_root, args.compatibility_root, args.view_root)
    for root in configured_roots:
        if not root.source.is_dir():
            raise SystemExit(f"missing canonical root: {root.source}")
        if args.apply:
            root.compatibility.mkdir(parents=True, exist_ok=True)
            root.view.mkdir(parents=True, exist_ok=True)

    db = connect(args.state)
    canonical: dict[Path, tuple[Root, Path]] = {}
    all_canonical_paths: set[str] = set()
    hidden_subtitle_inputs: dict[str, str] = {}
    retired_subtitle_inputs: dict[str, str] = {}
    for root in configured_roots:
        for current, _, filenames in os.walk(root.source):
            for filename in filenames:
                if filename.endswith('.subengine.json'):
                    hidden_subtitle_inputs.update(hidden_sources(Path(current) / filename))
                    retired_subtitle_inputs.update(retired_sources(Path(current) / filename))
            for filename in filenames:
                source = Path(current) / filename
                if source.is_file():
                    if str(source) in hidden_subtitle_inputs:
                        continue
                    canonical[root.view / source.relative_to(root.source)] = (root, source)
                    all_canonical_paths.add(str(source))

    token = worker_token(args.worker)
    seeded = 0
    if args.seed_jellyfin:
        # After the compatibility cutover, Jellyfin's logical paths resolve to
        # the view, not necessarily canonical source bytes.  Seeding a probe
        # cache by that logical path could label a P7 source as P8.  The normal
        # unit never needs this bootstrap switch; refuse it until an explicit
        # source/view inode-aware seeder is implemented and tested.
        raise SystemExit("--seed-jellyfin is unsafe after compatibility-view cutover and is disabled")

    counts = {
        "canonical_files": len(canonical),
        "seeded": seeded,
        "profile7": 0,
        "compat_ready": 0,
        "compat_adopted_after_rename": 0,
        "queued": 0,
        "queue_deferred": 0,
        "probe_deferred": 0,
        "view_linked": 0,
        "view_unchanged": 0,
        "view_waiting": 0,
        "view_removed": 0,
        "compat_removed": 0,
        "empty_dirs_removed": 0,
        "errors": 0,
    }
    changed_folders: set[str] = set()

    for view, (root, source) in sorted(canonical.items(), key=lambda item: str(item[0])):
        try:
            db.execute("DELETE FROM absent WHERE path=?", (str(source),))
            desired = source
            if source.suffix.lower() in VIDEO_SUFFIXES:
                profile, _ = probe(source, db, now)
                if profile is None:
                    if view.is_file():
                        existing_profile, _ = probe(view, db, now)
                        if existing_profile == 8:
                            counts["view_unchanged"] += 1
                            continue
                        status = unlink(view, args.apply)
                        if status in {"unlinked", "would-unlink"}:
                            counts["view_removed"] += 1
                            changed_folders.add(str(source.parent))
                    counts["probe_deferred"] += 1
                    counts["view_waiting"] += 1
                    continue
                if profile == 7:
                    counts["profile7"] += 1
                    compatibility = compatibility_path(root, source)
                    compatibility_profile = 0
                    if compatibility.is_file():
                        compatibility_profile, _ = probe(compatibility, db, now)
                    if compatibility_profile != 8:
                        for fallback in compatibility_fallbacks(root, source):
                            fallback_profile, _ = probe(fallback, db, now)
                            if fallback_profile != 8:
                                continue
                            result = atomic_link(fallback, compatibility, args.apply)
                            if result in {"linked", "would-link"}:
                                counts["compat_adopted_after_rename"] += 1
                            if args.apply:
                                compatibility_profile, _ = probe(compatibility, db, now)
                            else:
                                compatibility = fallback
                                compatibility_profile = fallback_profile
                            break
                    if compatibility_profile == 8:
                        desired = compatibility
                        counts["compat_ready"] += 1
                    else:
                        if retry_allows(source, args.retry_state, now):
                            if enqueue(source, args.queue, args.queue_lock, args.apply):
                                counts["queued"] += 1
                        else:
                            counts["queue_deferred"] += 1
                        if view.is_file():
                            existing_profile, _ = probe(view, db, now)
                            if existing_profile == 8:
                                counts["view_unchanged"] += 1
                                continue
                            status = unlink(view, args.apply)
                            if status in {"unlinked", "would-unlink"}:
                                counts["view_removed"] += 1
                                changed_folders.add(str(source.parent))
                        counts["view_waiting"] += 1
                        continue

            result = atomic_link(desired, view, args.apply)
            if result in {"linked", "would-link"}:
                counts["view_linked"] += 1
                changed_folders.add(str(source.parent))
            else:
                counts["view_unchanged"] += 1
        except (OSError, subprocess.SubprocessError) as exc:
            counts["errors"] += 1
            print(f"error: {source}: {exc}", file=sys.stderr)

    # A view entry has no valid master.  This is the normal delete/rename path.
    for root in configured_roots:
        if not root.view.exists():
            continue
        for current, _, filenames in os.walk(root.view):
            for filename in filenames:
                view = Path(current) / filename
                if view in canonical:
                    continue
                relative = view.relative_to(root.view)
                missing_source = root.source / relative
                if str(missing_source) in retired_subtitle_inputs and not missing_source.exists():
                    try:
                        if subtitle_digest(view) == retired_subtitle_inputs[str(missing_source)]:
                            status = unlink(view, args.apply)
                            if status in {'unlinked', 'would-unlink'}:
                                counts['view_removed'] += 1
                                changed_folders.add(str(missing_source.parent))
                    except OSError:
                        pass
                    continue
                if str(missing_source) in hidden_subtitle_inputs:
                    # A verified replacement hides only this view hardlink;
                    # canonical human/provider input is never removed.
                    try:
                        if subtitle_digest(missing_source) == hidden_subtitle_inputs[str(missing_source)]:
                            status = unlink(view, args.apply)
                            if status in {'unlinked', 'would-unlink'}:
                                counts['view_removed'] += 1
                                changed_folders.add(str(missing_source.parent))
                    except OSError:
                        pass
                    continue
                row = db.execute(
                    "SELECT first_seen FROM absent WHERE path=?", (str(missing_source),)
                ).fetchone()
                if row is None:
                    db.execute(
                        "INSERT INTO absent(path,first_seen) VALUES(?,?)",
                        (str(missing_source), now),
                    )
                    continue
                if now - int(row[0]) < args.cleanup_grace:
                    continue
                status = unlink(view, args.apply)
                if status in {"unlinked", "would-unlink"}:
                    counts["view_removed"] += 1
                    changed_folders.add(str(missing_source.parent))

    # Compatibility copies follow the canonical master.  Missing masters get a
    # short grace interval to avoid deleting across an ARR atomic rename window.
    for root in configured_roots:
        if not root.compatibility.exists():
            continue
        for current, _, filenames in os.walk(root.compatibility):
            for filename in filenames:
                compatibility = Path(current) / filename
                if not compatibility.is_file() or COMPAT_SUFFIX not in compatibility.stem:
                    continue
                source = master_path(root, compatibility)
                if source is None:
                    continue
                if source.is_file():
                    db.execute("DELETE FROM absent WHERE path=?", (str(source),))
                    # A same-inode P8 file is a zero-cost preservation hardlink
                    # awaiting its P7 recovery.  A different-inode companion is
                    # obsolete once the master has become non-P7.
                    source_profile, _ = probe(source, db, now)
                    if source_profile is not None and source_profile != 7 and not same_inode(source, compatibility):
                        status = unlink(compatibility, args.apply)
                        if status in {"unlinked", "would-unlink"}:
                            counts["compat_removed"] += 1
                    continue
                row = db.execute("SELECT first_seen FROM absent WHERE path=?", (str(source),)).fetchone()
                if row is None:
                    db.execute("INSERT INTO absent(path,first_seen) VALUES(?,?)", (str(source), now))
                    continue
                if now - int(row[0]) < args.cleanup_grace:
                    continue
                status = unlink(compatibility, args.apply)
                if status in {"unlinked", "would-unlink"}:
                    counts["compat_removed"] += 1
                db.execute("DELETE FROM absent WHERE path=?", (str(source),))

    for root in configured_roots:
        counts["empty_dirs_removed"] += remove_empty_dirs(root.view, args.apply)
        counts["empty_dirs_removed"] += remove_empty_dirs(root.compatibility, args.apply)

    # Bound stale cache rows without deleting current probe state.
    db.execute("DELETE FROM probe WHERE last_seen < ?", (now - 90 * 86400,))
    db.commit()

    notified = 0
    if args.apply and args.notify_jellyfin and changed_folders:
        if not token:
            print("warning: Jellyfin token missing; no notifications sent", file=sys.stderr)
        else:
            notified = notify_jellyfin(args.jellyfin, token, changed_folders)
    counts["jellyfin_notifications"] = notified
    counts["elapsed_seconds"] = round(time.monotonic() - started, 3)
    counts["applied"] = args.apply
    print(json.dumps(counts, sort_keys=True))
    if counts["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
