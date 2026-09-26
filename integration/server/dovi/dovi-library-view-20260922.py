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
import hashlib
import json
import os
import random
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
RETRY_DELAYS = (30, 120, 600, 1800, 7200, 21600, 43200)
MAX_NOTIFICATION_AGE = 48 * 3600


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
    db.execute("CREATE TABLE IF NOT EXISTS notification_outbox (folder TEXT PRIMARY KEY)")
    columns = {row[1] for row in db.execute("PRAGMA table_info(notification_outbox)")}
    if "revision" not in columns:
        db.execute("ALTER TABLE notification_outbox ADD COLUMN revision INTEGER NOT NULL DEFAULT 1")
    for name, declaration in {"attempts": "INTEGER NOT NULL DEFAULT 0", "first_seen": "REAL NOT NULL DEFAULT 0",
                              "next_attempt": "REAL NOT NULL DEFAULT 0", "dead": "INTEGER NOT NULL DEFAULT 0",
                              "error": "TEXT NOT NULL DEFAULT ''", "phase": "TEXT NOT NULL DEFAULT 'ready'",
                              "target_id": "TEXT"}.items():
        if name not in columns:
            db.execute(f"ALTER TABLE notification_outbox ADD COLUMN {name} {declaration}")
    db.execute("CREATE TABLE IF NOT EXISTS notification_receipts (folder TEXT PRIMARY KEY, sent_at REAL NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS notification_events (fingerprint TEXT PRIMARY KEY, folder TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS notification_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS notification_identity (folder TEXT PRIMARY KEY, provider_ids TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS notification_expected (folder TEXT NOT NULL,path TEXT NOT NULL,PRIMARY KEY(folder,path))")
    db.execute("""CREATE TABLE IF NOT EXISTS notification_mutations (
        folder TEXT NOT NULL,view TEXT NOT NULL,fingerprint TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'link',
        PRIMARY KEY(folder,view))""")
    if 'kind' not in {row[1] for row in db.execute('PRAGMA table_info(notification_mutations)')}:
        db.execute("ALTER TABLE notification_mutations ADD COLUMN kind TEXT NOT NULL DEFAULT 'link'")
    db.execute("""CREATE TABLE IF NOT EXISTS notification_deadletters (
        folder TEXT NOT NULL,revision INTEGER NOT NULL,attempts INTEGER NOT NULL,
        first_seen REAL NOT NULL,failed_at REAL NOT NULL,error TEXT NOT NULL,
        PRIMARY KEY(folder,revision,first_seen))""")
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


def publication_folder(folder: str, media_root: Path) -> str | None:
    path = Path(folder)
    for name in ("movies", "shows"):
        root = media_root / name
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        # A root-level file has no title directory to publish.  Never turn it
        # into a library-root update, and reject lexical traversal instead of
        # allowing `root / ".."` to broaden the notification scope.
        if relative.parts and ".." not in relative.parts:
            return str(root / relative.parts[0])
        return None
    return None


def refresh_target(url: str, token: str, folder: str,
                   catalogs: dict[str, list[dict]] | None = None) -> str | None:
    """Resolve a title by exact directory identity, never its display name alone."""
    query = urllib.parse.urlencode({"Recursive": "true", "IncludeItemTypes": "Series,Movie",
                                   "Fields": "Path", "SearchTerm": Path(folder).name, "Limit": 100})
    request = urllib.request.Request(f"{url.rstrip('/')}/Items?{query}",
                                    headers={"Authorization": f'MediaBrowser Token="{token}"'})
    with urllib.request.urlopen(request, timeout=20) as response:
        items = json.load(response).get("Items", [])
    def identities(values: list[dict]) -> set[str]:
        return {item["Id"] for item in values if item.get("Id") and (
            (item.get("Type") == "Series" and item.get("Path") == folder)
            or (item.get("Type") == "Movie" and item.get("Path")
                and str(Path(item["Path"]).parent) == folder))}

    ids = identities(items)
    if ids:
        return next(iter(ids)) if len(ids) == 1 else None

    # Display names may be localized or renamed independently of directories.
    # Query only the owning movie/show library's metadata, never all server items.
    catalogs = catalogs if catalogs is not None else {}
    headers = {"Authorization": f'MediaBrowser Token="{token}"'}
    if "virtual-folders" not in catalogs:
        request = urllib.request.Request(f"{url.rstrip('/')}/Library/VirtualFolders", headers=headers)
        with urllib.request.urlopen(request, timeout=20) as response:
            catalogs["virtual-folders"] = json.load(response)
    owners = {library["ItemId"] for library in catalogs["virtual-folders"]
              if library.get("ItemId") and any(Path(folder).is_relative_to(Path(location))
              for location in library.get("Locations", []) if location)}
    if len(owners) != 1:
        return None
    owner = next(iter(owners))
    if owner not in catalogs:
        values = []
        page_size = 200
        for start in range(0, 20000, page_size):
            query = urllib.parse.urlencode({"ParentId": owner, "Recursive": "true",
                                           "IncludeItemTypes": "Series,Movie", "Fields": "Path",
                                           "EnableImages": "false", "EnableTotalRecordCount": "false",
                                           "StartIndex": start, "Limit": page_size})
            request = urllib.request.Request(f"{url.rstrip('/')}/Items?{query}", headers=headers)
            with urllib.request.urlopen(request, timeout=20) as response:
                page = json.load(response).get("Items", [])
            values.extend(page)
            if len(page) < page_size:
                catalogs[owner] = values
                break
        else:
            raise OSError("owning title catalog exceeded bounded pagination; publication retained")
    ids = identities(catalogs[owner])
    return next(iter(ids)) if len(ids) == 1 else None


def notify_jellyfin(url: str, token: str, folders: set[str], targets: dict[str, str | None] | None = None,
                   catalogs: dict[str, list[dict]] | None = None, failures: dict | None = None,
                   new_title_bridge: bool = False, identities: dict | None = None) -> int:
    sent = 0
    targets = targets if targets is not None else {}
    catalogs = catalogs if catalogs is not None else {}
    failures = failures if failures is not None else {}
    for folder in sorted(folders):
        try:
            if folder not in targets:
                targets[folder] = refresh_target(url, token, folder, catalogs)
            target = targets[folder]
            if target:
                # In Jellyfin 12.1 a Folder refresh validates children recursively
                # by default. There is no recursive query option on this endpoint.
                query = urllib.parse.urlencode({"metadataRefreshMode": "Default", "imageRefreshMode": "None",
                                               "replaceAllMetadata": "false", "replaceAllImages": "false"})
                endpoint = f"Items/{urllib.parse.quote(target, safe='')}/Refresh?{query}"
                body = b""
            else:
                if not new_title_bridge:
                    failures[folder] = "bridge-unconfigured"
                    continue
                parent = str(Path(folder).parent)
                libraries = [library for library in catalogs.get("virtual-folders", [])
                             if library.get("ItemId") and parent in library.get("Locations", [])]
                if len(libraries) != 1:
                    failures[folder] = "library-mapping-unknown"
                    continue
                endpoint = "Habibi/LibraryExperience/DiscoverTitle"
                body = json.dumps({"libraryId": libraries[0]["ItemId"], "expectedParentPath": parent,
                    "directoryName": Path(folder).name, "kind": "Series" if Path(parent).name == "shows" else "Movie",
                    "providerIds": (identities or {}).get(folder, {})}).encode()
            request = urllib.request.Request(
                f"{url.rstrip('/')}/{endpoint}", data=body,
                headers={"Authorization": f'MediaBrowser Token="{token}"', "Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(request, timeout=20) as response:
                if 200 <= response.status < 300:
                    if not target:
                        result = json.load(response)
                        item_id = (result.get("ItemId") or result.get("itemId")) if isinstance(result, dict) else None
                        queued = (result.get("Queued", result.get("queued"))) if isinstance(result, dict) else False
                        if not item_id or queued is not True:
                            failures[folder] = "invalid-bridge-acceptance"
                            continue
                        targets[folder] = item_id
                    sent += 1
                else:
                    failures[folder] = "unexpected-http-status"
        except (OSError, ValueError, TypeError) as exc:
            code = getattr(exc, "code", None)
            failure = ("auth" if code in {401, 403} else "down" if code is None or code == 429 or code >= 500
                       else "not-ready" if code == 409 else "api-error")
            failures[folder] = failure
            print(f"warning: Jellyfin publication failed: {failure}", file=sys.stderr)
    return sent


def verify_publication(url: str, token: str, target: str | None, expected: set[str]) -> bool:
    if not expected:
        return True
    if not target:
        return False
    remaining = set(expected)
    kind = "Episode" if any("/shows/" in path for path in expected) else "Movie"
    for start in range(0, 4000, 200):
        query = {"Fields": "Path,MediaSources", "IncludeItemTypes": kind, "EnableImages": "false",
                 "EnableTotalRecordCount": "false", "Limit": 200, "StartIndex": start}
        query.update({"ParentId": target, "Recursive": "true"} if kind == "Episode" else {"Ids": target})
        request = urllib.request.Request(f"{url.rstrip('/')}/Items?{urllib.parse.urlencode(query)}",
                                        headers={"Authorization": f'MediaBrowser Token="{token}"'})
        with urllib.request.urlopen(request, timeout=20) as response:
            items = json.load(response).get("Items", [])
        for item in items:
            for source in item.get("MediaSources") or []:
                if source.get("Path") and source.get("Protocol", "File") == "File":
                    remaining.discard(source.get("Path"))
        if not remaining:
            return True
        if len(items) < 200:
            return False
    return False


class NotificationOutbox:
    """Persist intent before view changes; acknowledge verified indexed videos.

    The existing oneshot unit serializes runs. Failed folders are attempted once
    per run and survive unchanged subsequent reconciliations and process death.
    """

    def __init__(self, db: sqlite3.Connection, url: str, token: str | None, enabled: bool,
                 media_root: Path = Path("/data/media"), title_locks: Path | None = None,
                 publish_lock: Path | None = None, new_title_bridge: bool = False):
        self.db, self.url, self.token, self.enabled = db, url, token, enabled
        self.media_root = media_root
        self.title_locks, self.publish_lock = title_locks, publish_lock
        self.new_title_bridge = new_title_bridge
        self.targets: dict[str, str | None] = {}
        self.catalogs: dict[str, list[dict]] = {}
        self.failed: set[str] = set()
        self.sent = 0
        self.verified = 0
        self.attempted = 0
        self.last_flush = 0.0

    def stage(self, folder: str, fingerprint: str | None = None, expected_video: Path | None = None,
              mutation_view: Path | None = None, mutation_kind: str = 'link') -> tuple[str, str, str] | None:
        if self.enabled:
            publication = publication_folder(folder, self.media_root)
            if publication is None:
                print(f"warning: unsupported Jellyfin publication scope skipped: {folder}", file=sys.stderr)
                return
            fingerprint = fingerprint or "scope:" + folder
            if expected_video is not None:
                self.db.execute("INSERT OR IGNORE INTO notification_expected VALUES(?,?)", (publication, str(expected_video)))
            if self.db.execute("SELECT 1 FROM notification_events WHERE fingerprint=?", (fingerprint,)).fetchone():
                self.db.commit()
                if mutation_view is not None and self.db.execute(
                        "SELECT 1 FROM notification_mutations WHERE folder=? AND view=? AND fingerprint=?",
                        (publication, str(mutation_view), fingerprint)).fetchone():
                    return publication, str(mutation_view), fingerprint
                return None
            self.db.execute("INSERT INTO notification_events VALUES(?,?)", (fingerprint, publication))
            if mutation_view is not None:
                self.db.execute("INSERT INTO notification_mutations VALUES(?,?,?,?) ON CONFLICT(folder,view) DO UPDATE SET fingerprint=excluded.fingerprint,kind=excluded.kind",
                                (publication, str(mutation_view), fingerprint, mutation_kind))
            staging = self.db.execute("SELECT 1 FROM notification_mutations WHERE folder=?", (publication,)).fetchone()
            self.db.execute("""INSERT INTO notification_outbox(folder,first_seen,phase) VALUES(?,?,?)
                ON CONFLICT(folder) DO UPDATE SET revision=revision+1,attempts=0,first_seen=excluded.first_seen,
                next_attempt=0,dead=0,error='',phase=excluded.phase,target_id=NULL""", (publication, time.time(), 'staging' if staging else 'ready'))
            self.db.commit()
            return (publication, str(mutation_view), fingerprint) if mutation_view is not None else None

    def complete_mutation(self, marker: tuple[str, str, str] | None) -> None:
        if marker is None:
            return
        folder, view, fingerprint = marker
        removed = self.db.execute("DELETE FROM notification_mutations WHERE folder=? AND view=? AND fingerprint=?",
                                  (folder, view, fingerprint)).rowcount
        if removed:
            self.db.execute("UPDATE notification_outbox SET phase='ready' WHERE folder=? AND phase='staging' AND NOT EXISTS(SELECT 1 FROM notification_mutations WHERE folder=?)",
                            (folder, folder))
        self.db.commit()

    def flush(self, force: bool = False) -> None:
        if not self.enabled:
            return
        with contextlib.ExitStack() as stack:
            if self.publish_lock:
                lock = stack.enter_context(self.publish_lock.open("a+"))
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return
            self._flush(force)

    def _flush(self, force: bool = False) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        if not force and now - self.last_flush < 5:
            return
        self.last_flush = now
        # If unlink committed but its completion transaction was interrupted,
        # absence in an available parent proves that local removal completed.
        for folder, view, fingerprint in list(self.db.execute("SELECT folder,view,fingerprint FROM notification_mutations WHERE kind='unlink'")):
            path = Path(view)
            if (publication_folder(folder, self.media_root) == folder and path.parent.is_dir()
                    and self.commit_section_clear(folder) and not path.exists() and not path.is_symlink()):
                self.complete_mutation((folder, view, fingerprint))
        pending = {}
        invalid = []
        circuit = self.db.execute("SELECT value FROM notification_meta WHERE key='circuit_until'").fetchone()
        circuit_open = circuit is not None and float(circuit[0]) > time.time()
        for folder, revision, attempts, first_seen, due, dead, error, phase, target in self.db.execute(
                "SELECT folder,revision,attempts,first_seen,next_attempt,dead,error,phase,target_id FROM notification_outbox"):
            if not isinstance(folder, str) or publication_folder(folder, self.media_root) != folder:
                invalid.append(folder)
            elif not dead:
                if first_seen == 0:
                    first_seen = time.time()
                    self.db.execute("UPDATE notification_outbox SET first_seen=? WHERE folder=? AND revision=?", (first_seen, folder, revision))
                    self.db.commit()
                if time.time() - first_seen >= MAX_NOTIFICATION_AGE or attempts >= 8:
                    self.deadletter(folder, revision, attempts, first_seen, "expired" if attempts < 8 else error)
                elif phase != 'staging' and folder not in self.failed and due <= time.time() and not circuit_open and not (
                        error == "bridge-unconfigured" and not self.new_title_bridge):
                    pending[folder] = (revision, attempts, first_seen, phase, target)
        if invalid:
            self.db.executemany("DELETE FROM notification_outbox WHERE folder IS ?", ((folder,) for folder in invalid))
            self.db.commit()
            for folder in sorted(invalid, key=repr):
                print(f"warning: invalid Jellyfin publication intent discarded: {folder}", file=sys.stderr)
        if not self.token:
            if pending:
                print("warning: Jellyfin token missing; notifications retained", file=sys.stderr)
                self.failed.update(pending)
            return
        for folder in sorted(pending):
            if self.attempted >= 5:
                break
            revision, attempts, first_seen, phase, target = pending[folder]
            receipt = self.db.execute("SELECT sent_at FROM notification_receipts WHERE folder=?", (folder,)).fetchone()
            if phase == 'ready' and receipt and time.time() - receipt[0] < 60:
                continue
            if not self.commit_section_clear(folder):
                continue
            failures = {}
            self.attempted += 1
            expected = {row[0] for row in self.db.execute("SELECT path FROM notification_expected WHERE folder=?", (folder,))}
            # ARR upgrades/renames can remove an older pending filename. Prune
            # only exact absent canonical children while the root AND title are
            # present; a missing/unmounted title fails closed, never becomes ACK.
            title = Path(folder)
            if expected and (not title.parent.is_dir() or not title.is_dir() or title.is_symlink()):
                self.attempted -= 1
                continue
            obsolete = set()
            for path in expected:
                candidate = Path(path)
                if (candidate.is_relative_to(title) and '..' not in candidate.parts
                        and not candidate.exists() and not candidate.is_symlink()):
                    obsolete.add(path)
            if obsolete:
                # CAS protects expectations staged by another writer during
                # this read-only path check.
                self.db.executemany("DELETE FROM notification_expected WHERE folder=? AND path=? AND EXISTS(SELECT 1 FROM notification_outbox WHERE folder=? AND revision=?)",
                                    ((folder, path, folder, revision) for path in obsolete))
                self.db.commit()
                expected -= obsolete
            if phase == 'await_index':
                try:
                    if verify_publication(self.url, self.token, target, expected):
                        self.acknowledge(folder, revision)
                        self.verified += 1
                        continue
                    failures[folder] = "index-wait"
                except (OSError, ValueError, TypeError) as exc:
                    code = getattr(exc, "code", None)
                    failures[folder] = "auth" if code in {401,403} else "down"
                self.retry(folder, revision, attempts, first_seen, failures[folder])
                if failures[folder] in {'auth','down'}:
                    break
                continue
            identity = self.db.execute("SELECT provider_ids FROM notification_identity WHERE folder=?", (folder,)).fetchone()
            identities = {folder: json.loads(identity[0])} if identity else {}
            if notify_jellyfin(self.url, self.token, {folder}, self.targets, self.catalogs,
                              failures, self.new_title_bridge, identities) == 1:
                self.db.execute("UPDATE notification_outbox SET phase='await_index',target_id=?,attempts=?,next_attempt=?,error='' WHERE folder=? AND revision=?",
                                (self.targets.get(folder), attempts + 1, time.time() + 30, folder, revision))
                self.db.execute("INSERT INTO notification_receipts VALUES(?,?) ON CONFLICT(folder) DO UPDATE SET sent_at=excluded.sent_at",
                                (folder, time.time()))
                self.db.commit()
                self.sent += 1
                if not expected:
                    self.acknowledge(folder, revision)
                else:
                    try:
                        if verify_publication(self.url, self.token, self.targets.get(folder), expected):
                            self.acknowledge(folder, revision)
                            self.verified += 1
                    except (OSError, ValueError, TypeError):
                        # Acceptance is durable; the due verification phase will
                        # classify/back off a failure without reposting the refresh.
                        pass
            else:
                error = failures.get(folder, "api-error")
                self.retry(folder, revision, attempts, first_seen, error)
                if error in {"auth", "down"}:
                    break

    def acknowledge(self, folder, revision):
        removed = self.db.execute("DELETE FROM notification_outbox WHERE folder=? AND revision=?", (folder, revision)).rowcount
        if removed:
            self.db.execute("DELETE FROM notification_expected WHERE folder=?", (folder,))
        self.db.commit()

    def commit_section_clear(self, folder: str) -> bool:
        """Defer a paused view mutation; never retain a title lock across HTTP."""
        if self.title_locks is None:
            return True
        self.title_locks.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha256(folder.encode()).hexdigest() + '.lock'
        with (self.title_locks / name).open('a+') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
        return True

    def retry(self, folder, revision, attempts, first_seen, error):
        self.failed.add(folder)
        local = error in {"bridge-unconfigured", "library-mapping-unknown"}
        attempts += 0 if local else 1
        if attempts >= 8:
            self.deadletter(folder, revision, attempts, first_seen, error)
        else:
            delay = 300 if local else RETRY_DELAYS[max(0, attempts - 1)] * random.uniform(0.9, 1.1)
            self.db.execute("UPDATE notification_outbox SET attempts=?,next_attempt=?,error=? WHERE folder=? AND revision=?",
                            (attempts, time.time() + delay, error, folder, revision))
            self.db.commit()
        if error in {"auth", "down"}:
            self.db.execute("INSERT INTO notification_meta VALUES('circuit_until',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                            (str(time.time() + 120),))
            self.db.commit()

    def deadletter(self, folder, revision, attempts, first_seen, error):
        self.db.execute("INSERT OR IGNORE INTO notification_deadletters VALUES(?,?,?,?,?,?)",
                        (folder, revision, attempts, first_seen, time.time(), error))
        self.db.execute("UPDATE notification_outbox SET dead=1,attempts=?,error=? WHERE folder=? AND revision=?",
                        (attempts, error, folder, revision))
        self.db.commit()

    @contextlib.contextmanager
    def mutation_lock(self, folder: str, apply: bool):
        with contextlib.ExitStack() as stack:
            if apply and self.title_locks:
                self.title_locks.mkdir(parents=True, exist_ok=True)
                publication = publication_folder(folder, self.media_root) or folder
                name = hashlib.sha256(publication.encode()).hexdigest() + ".lock"
                lock = stack.enter_context((self.title_locks / name).open("a+"))
                fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def link(self, source: Path, view: Path, folder: str, apply: bool,
             master: Path | None = None, expected: tuple | None = None,
             ensure_publication: bool = False) -> str:
        with self.mutation_lock(folder, apply):
            marker = None
            if master is not None and expected is not None and signature(master) != expected:
                raise OSError("canonical file changed during probe; defer view mutation")
            unfinished = self.db.execute("SELECT 1 FROM notification_mutations WHERE folder=? AND view=?",
                                         (publication_folder(folder, self.media_root), str(view))).fetchone()
            if ensure_publication or unfinished or not same_inode(source, view):
                fingerprint = hashlib.sha256(repr(("link", str(master or source), expected or signature(source), signature(source), str(view))).encode()).hexdigest()
                expected_video = master or source
                marker = self.stage(folder, fingerprint, expected_video if expected_video.suffix.lower() in VIDEO_SUFFIXES else None, view)
            if master is not None and expected is not None and signature(master) != expected:
                raise OSError("canonical file changed before link commit; defer view mutation")
            result = atomic_link(source, view, apply)
            self.complete_mutation(marker)
            return result

    def remove(self, view: Path, folder: str, apply: bool, master: Path | None = None,
               expected: tuple | None = None, require_absent: Path | None = None) -> str:
        with self.mutation_lock(folder, apply):
            marker = None
            if master is not None and expected is not None and signature(master) != expected:
                raise OSError("canonical file changed during probe; defer view removal")
            if require_absent is not None and require_absent.exists():
                return "unchanged"
            if view.exists() or view.is_symlink():
                fingerprint = hashlib.sha256(repr(("remove", str(view), signature(view), str(master or require_absent))).encode()).hexdigest()
                marker = self.stage(folder, fingerprint, mutation_view=view, mutation_kind='unlink')
                removed_source = master or require_absent
                if removed_source is not None:
                    publication = publication_folder(folder, self.media_root)
                    self.db.execute("DELETE FROM notification_expected WHERE folder=? AND path=?", (publication, str(removed_source)))
                    self.db.commit()
            if master is not None and expected is not None and signature(master) != expected:
                raise OSError("canonical file changed before removal commit; defer view mutation")
            result = unlink(view, apply)
            self.complete_mutation(marker)
        self.flush(force=True)
        return result


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
    parser.add_argument("--notification-state", type=Path, default=Path("/data/config/_dovi/publication.sqlite"))
    parser.add_argument("--publication-lock", type=Path, default=Path("/run/dovi-library-notify.lock"))
    parser.add_argument("--title-locks", type=Path, default=Path("/run/dovi-library-title-locks"))
    parser.add_argument("--scope-title", type=Path)
    parser.add_argument("--scope-file", action="append", type=Path, default=[])
    parser.add_argument("--provider-id", action="append", default=[])
    parser.add_argument("--new-title-bridge", action="store_true")
    parser.add_argument("--retry-state", type=Path, default=Path("/data/config/_dovi/retry-state.sqlite"))
    parser.add_argument("--worker", type=Path, default=Path("/data/config/_dovi/process-queue.sh"))
    parser.add_argument("--jellyfin", default=os.environ.get("JELLYFIN_URL", "http://jellyfin:8096"))
    parser.add_argument("--seed-jellyfin", action="store_true")
    parser.add_argument("--notify-jellyfin", action="store_true")
    parser.add_argument("--notify-only", action="store_true", help="Drain due publication intents without walking or probing media")
    parser.add_argument("--run-lock", type=Path, default=Path("/run/dovi-library-view.lock"))
    parser.add_argument("--cleanup-grace", type=int, default=900)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.notify_only and not (args.apply and args.notify_jellyfin):
        parser.error("--notify-only requires --apply --notify-jellyfin")
    with contextlib.ExitStack() as stack:
        if args.apply and not args.notify_only:
            lock = stack.enter_context(args.run_lock.open("a+"))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(json.dumps({"skipped": "reconciler lock busy", "notify_only": args.notify_only}))
                return
        reconcile(args, stack)


def reconcile(args: argparse.Namespace, stack: contextlib.ExitStack) -> None:

    started = time.monotonic()
    now = int(time.time())
    # Dry-run retains the pre-existing probe cache behavior, but does not create
    # or migrate a production publication database.
    publication_db = connect(args.notification_state if args.apply else Path(':memory:'))
    stack.callback(publication_db.close)
    token = worker_token(args.worker)
    outbox = NotificationOutbox(publication_db, args.jellyfin, token, args.apply and args.notify_jellyfin,
                                args.media_root, args.title_locks, args.publication_lock, args.new_title_bridge)
    outbox.flush(force=True)
    if args.notify_only:
        print(json.dumps({"notify_only": True, "jellyfin_notifications": outbox.sent,
                          "jellyfin_verified": outbox.verified,
                          "jellyfin_deadletters": publication_db.execute("SELECT COUNT(*) FROM notification_deadletters").fetchone()[0],
                          "jellyfin_pending_notifications": publication_db.execute("SELECT COUNT(*) FROM notification_outbox").fetchone()[0]}))
        return
    db = connect(args.state)
    stack.callback(db.close)
    configured_roots = roots(args.media_root, args.compatibility_root, args.view_root)
    scoped_files = set(args.scope_file)
    if args.scope_title:
        if publication_folder(str(args.scope_title), args.media_root) != str(args.scope_title) or not scoped_files:
            raise SystemExit("scoped reconciliation requires an exact canonical title and imported files")
        if any(not path.is_relative_to(args.scope_title) or '..' in path.parts or path.suffix.lower() not in VIDEO_SUFFIXES
               or path.is_symlink() or not path.resolve().is_relative_to(args.scope_title.resolve()) for path in scoped_files) or args.scope_title.is_symlink():
            raise SystemExit("scoped input is outside its title or not a supported video")
        configured_roots = tuple(Root(root.name, args.scope_title,
            root.compatibility / args.scope_title.relative_to(root.source),
            root.view / args.scope_title.relative_to(root.source))
            for root in configured_roots if args.scope_title.is_relative_to(root.source))
        identity = dict(value.split("=", 1) for value in args.provider_id)
        if any(key not in {"Tvdb", "Tmdb", "Imdb"} or not re.fullmatch(r"tt\d+" if key == "Imdb" else r"\d+", value)
               for key, value in identity.items()):
            raise SystemExit("invalid scoped provider identity")
        if args.apply and identity:
            publication_db.execute("INSERT INTO notification_identity VALUES(?,?) ON CONFLICT(folder) DO UPDATE SET provider_ids=excluded.provider_ids",
                                   (str(args.scope_title), json.dumps(identity)))
            publication_db.commit()
    for root in configured_roots:
        if not root.source.is_dir():
            raise SystemExit(f"missing canonical root: {root.source}")
        if args.apply:
            root.compatibility.mkdir(parents=True, exist_ok=True)
            root.view.mkdir(parents=True, exist_ok=True)

    canonical: dict[Path, tuple[Root, Path]] = {}
    all_canonical_paths: set[str] = set()
    hidden_subtitle_inputs: dict[str, str] = {}
    retired_subtitle_inputs: dict[str, str] = {}
    for root in configured_roots:
        if scoped_files:
            # Only touched videos and same-stem siblings. Never enumerate/hash an
            # unrelated movie, subtitle marker or another episode in this title.
            selected: dict[Path, set[str]] = {}
            for video in scoped_files:
                names = selected.setdefault(video.parent, set())
                names.add(video.name)
                prefix = video.stem + "."
                names.update(p.name for p in video.parent.iterdir()
                             if p.name.startswith(prefix) and p.suffix.lower() not in VIDEO_SUFFIXES)
            walks = ((str(parent), [], names) for parent, names in selected.items())
        else:
            walks = os.walk(root.source)
        for current, _, filenames in walks:
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

    for view, (root, source) in sorted(canonical.items(), key=lambda item: str(item[0])):
        try:
            observed = signature(source)
            db.execute("DELETE FROM absent WHERE path=?", (str(source),))
            desired = source
            if source.suffix.lower() in VIDEO_SUFFIXES:
                # Do not hold sidecar publication behind a potentially slow probe.
                outbox.flush(force=True)
                profile, _ = probe(source, db, now)
                if profile is None:
                    if view.is_file():
                        existing_profile, _ = probe(view, db, now)
                        if existing_profile == 8:
                            counts["view_unchanged"] += 1
                            continue
                        status = outbox.remove(view, str(source.parent), args.apply, source, observed)
                        if status in {"unlinked", "would-unlink"}:
                            counts["view_removed"] += 1
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
                            status = outbox.remove(view, str(source.parent), args.apply, source, observed)
                            if status in {"unlinked", "would-unlink"}:
                                counts["view_removed"] += 1
                        counts["view_waiting"] += 1
                        continue

            result = outbox.link(desired, view, str(source.parent), args.apply, source, observed,
                                 ensure_publication=bool(args.scope_title))
            if result in {"linked", "would-link"}:
                counts["view_linked"] += 1
            else:
                counts["view_unchanged"] += 1
            outbox.flush(force=source.suffix.lower() in VIDEO_SUFFIXES)
        except (OSError, subprocess.SubprocessError) as exc:
            counts["errors"] += 1
            print(f"error: {source}: {exc}", file=sys.stderr)

    # A view entry has no valid master.  This is the normal delete/rename path.
    for root in (() if scoped_files else configured_roots):
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
                            status = outbox.remove(view, str(missing_source.parent), args.apply)
                            if status in {'unlinked', 'would-unlink'}:
                                counts['view_removed'] += 1
                    except OSError:
                        pass
                    continue
                if str(missing_source) in hidden_subtitle_inputs:
                    # A verified replacement hides only this view hardlink;
                    # canonical human/provider input is never removed.
                    try:
                        if subtitle_digest(missing_source) == hidden_subtitle_inputs[str(missing_source)]:
                            status = outbox.remove(view, str(missing_source.parent), args.apply)
                            if status in {'unlinked', 'would-unlink'}:
                                counts['view_removed'] += 1
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
                status = outbox.remove(view, str(missing_source.parent), args.apply, require_absent=missing_source)
                if status in {"unlinked", "would-unlink"}:
                    counts["view_removed"] += 1

    # Compatibility copies follow the canonical master.  Missing masters get a
    # short grace interval to avoid deleting across an ARR atomic rename window.
    for root in (() if scoped_files else configured_roots):
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

    for root in (() if scoped_files else configured_roots):
        counts["empty_dirs_removed"] += remove_empty_dirs(root.view, args.apply)
        counts["empty_dirs_removed"] += remove_empty_dirs(root.compatibility, args.apply)

    # Bound stale cache rows without deleting current probe state.
    db.execute("DELETE FROM probe WHERE last_seen < ?", (now - 90 * 86400,))
    db.commit()

    outbox.flush(force=True)
    counts["jellyfin_notifications"] = outbox.sent
    counts["jellyfin_verified"] = outbox.verified
    counts["jellyfin_pending_notifications"] = publication_db.execute("SELECT COUNT(*) FROM notification_outbox").fetchone()[0]
    counts["jellyfin_deadletters"] = publication_db.execute("SELECT COUNT(*) FROM notification_deadletters").fetchone()[0]
    counts["elapsed_seconds"] = round(time.monotonic() - started, 3)
    counts["applied"] = args.apply
    print(json.dumps(counts, sort_keys=True))
    if counts["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
