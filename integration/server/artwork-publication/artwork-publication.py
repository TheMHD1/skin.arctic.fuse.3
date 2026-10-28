#!/usr/bin/env python3
"""Bounded, exact-item recovery for a missing Jellyfin Primary image.

This is deliberately not a library scanner.  Call ``enqueue`` only after a
trusted import/discovery path has obtained the Jellyfin item ID.  The worker
then confirms the exact item remains under one canonical title root, skips an
existing Primary image, and asks Jellyfin to fetch images only for that item.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

DELAYS = (30, 120, 600, 1800, 7200, 21600, 43200)
MAX_AGE = 48 * 3600
VERIFY_WINDOW = 600
ITEM_ID = re.compile(r"^(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", re.I)


def canonical_id(value: str) -> str:
    if not isinstance(value, str) or not ITEM_ID.fullmatch(value):
        raise ValueError("invalid Jellyfin item ID")
    return uuid.UUID(value).hex


def connect(state: Path):
    state.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(state)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("""CREATE TABLE IF NOT EXISTS jobs(
      item_id TEXT NOT NULL, title_root TEXT NOT NULL, revision TEXT NOT NULL,
      state TEXT NOT NULL, attempts INTEGER NOT NULL, first_seen REAL NOT NULL,
      next_attempt REAL NOT NULL, error TEXT NOT NULL DEFAULT '', updated REAL NOT NULL,
      refresh_requested REAL NOT NULL DEFAULT 0,
      PRIMARY KEY(item_id,revision))""")
    if "refresh_requested" not in {row[1] for row in db.execute("PRAGMA table_info(jobs)")}:
        db.execute("ALTER TABLE jobs ADD COLUMN refresh_requested REAL NOT NULL DEFAULT 0")
    db.commit()
    return db


def title_root(value: str, media_root: Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute() or "\x00" in value:
        raise ValueError("invalid title root")
    candidate = candidate.resolve(strict=False)
    canonical = media_root.resolve(strict=False)
    try:
        relative = candidate.relative_to(canonical)
    except ValueError as error:
        raise ValueError("title root outside canonical media") from error
    if len(relative.parts) != 2 or relative.parts[0] not in {"movies", "shows"}:
        raise ValueError("title root is not one canonical movie or series directory")
    return candidate


def enqueue(db, item_id: str, root: Path, now=None):
    item_id = canonical_id(item_id)
    now = time.time() if now is None else now
    revision = item_id + "\0" + str(root)
    with db:
        db.execute("""INSERT INTO jobs(item_id,title_root,revision,state,attempts,first_seen,next_attempt,updated)
          VALUES(?,?,?,'pending',0,?,?,?)
          ON CONFLICT(item_id,revision) DO UPDATE SET updated=excluded.updated""",
          (item_id, str(root), revision, now, now, now))


class Api:
    def __init__(self, config):
        self.url = str(config["jellyfin_url"]).rstrip("/")
        parsed = urllib.parse.urlsplit(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("invalid private Jellyfin URL")
        self.token = Path(config["token_file"]).read_text().strip()
        if not self.token:
            raise ValueError("empty Jellyfin token")

    def request(self, route, method="GET"):
        request = urllib.request.Request(self.url + route, method=method,
            data=b"" if method == "POST" else None,
            headers={"Authorization": 'MediaBrowser Token="' + self.token + '"'})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read() or b"{}")


def primary_present(item):
    if (item.get("ImageTags") or {}).get("Primary"):
        return True
    return any(image.get("ImageType") == "Primary" for image in item.get("ImageInfos") or [])


def exact_item(api: Api, item_id: str, root: Path):
    result = api.request("/Items?Ids=" + urllib.parse.quote(item_id, safe="") + "&Fields=Path,ImageInfos")
    items = result.get("Items") or []
    if len(items) != 1 or canonical_id(items[0].get("Id")) != canonical_id(item_id) or not isinstance(items[0].get("Path"), str):
        raise LookupError("exact item not indexed")
    path = Path(items[0]["Path"]).resolve(strict=False)
    # Jellyfin Series path is the directory; Movie path may be its file.
    if path != root and path.parent != root:
        raise ValueError("item path no longer matches canonical title root")
    return items[0]


def error_kind(error):
    if isinstance(error, urllib.error.HTTPError):
        if error.code == 409: return "not-ready"
        if error.code in {401, 403}: return "auth"
        if error.code == 429 or error.code >= 500: return "down"
        return "api-error"
    if isinstance(error, (urllib.error.URLError, TimeoutError, OSError)):
        return "down"
    if isinstance(error, LookupError): return "index-wait"
    return "invalid" if isinstance(error, ValueError) else "error"


def defer(db, row, error, now):
    item_id, root, revision, _, attempts, first_seen, _, _ = row[:8]
    kind = error_kind(error)
    # Busy index/discovery is expected; it must not exhaust the failure budget.
    waiting = kind in {"not-ready", "index-wait"}
    attempts += 0 if waiting else 1
    dead = now - first_seen >= MAX_AGE or attempts >= 8 or kind in {"auth", "invalid"}
    delay = 30 if waiting else DELAYS[min(attempts - 1, len(DELAYS) - 1)]
    verifying = len(row) > 8 and row[3] == "verifying" and now - row[8] < VERIFY_WINDOW
    state = "dead" if dead else "verifying" if verifying else "waiting"
    with db:
        db.execute("UPDATE jobs SET state=?,attempts=?,next_attempt=?,error=?,updated=? WHERE item_id=? AND revision=?",
            (state, attempts, now + delay, kind, now, item_id, revision))


def work(db, api, limit=4, now=None):
    now = time.time() if now is None else now
    rows = list(db.execute("SELECT item_id,title_root,revision,state,attempts,first_seen,next_attempt,error,refresh_requested FROM jobs WHERE state IN ('pending','waiting','verifying') AND next_attempt<=? ORDER BY first_seen LIMIT ?", (now, limit)))
    result = {"completed": 0, "deferred": 0, "dead": 0}
    for row in rows:
        if now - row[5] >= MAX_AGE:
            with db:
                db.execute("UPDATE jobs SET state='dead',error='expired',updated=? WHERE item_id=? AND revision=?", (now, row[0], row[2]))
            result["dead"] += 1
            continue
        try:
            item = exact_item(api, row[0], Path(row[1]))
            if primary_present(item):
                with db:
                    db.execute("UPDATE jobs SET state='complete',error='',updated=? WHERE item_id=? AND revision=?", (now, row[0], row[2]))
                result["completed"] += 1
                continue
            if row[3] == "verifying":
                if now - row[8] >= VERIFY_WINDOW:
                    raise RuntimeError("accepted refresh produced no Primary image")
                with db:
                    db.execute("UPDATE jobs SET next_attempt=?,error='image-wait',updated=? WHERE item_id=? AND revision=?", (now + 30, now, row[0], row[2]))
                result["deferred"] += 1
                continue
            query = urllib.parse.urlencode({"MetadataRefreshMode": "None", "ImageRefreshMode": "Default",
                "ReplaceAllMetadata": "false", "ReplaceAllImages": "false", "RegenerateTrickplay": "false"})
            api.request("/Items/" + urllib.parse.quote(row[0], safe="") + "/Refresh?" + query, "POST")
            # An accepted request is not completion. Poll the exact item without
            # resubmitting a refresh every 30 seconds while the shared queue runs.
            with db:
                db.execute("UPDATE jobs SET state='verifying',refresh_requested=?,next_attempt=?,error='image-wait',updated=? WHERE item_id=? AND revision=?", (now, now + 30, now, row[0], row[2]))
            result["deferred"] += 1
        except Exception as error:
            defer(db, row, error, now)
            current = db.execute("SELECT state FROM jobs WHERE item_id=? AND revision=?", (row[0], row[2])).fetchone()[0]
            result["dead" if current == "dead" else "deferred"] += 1
    return result


def status(db):
    return {"jobs": [{"state": state, "error": error, "count": count}
                     for state, error, count in db.execute("SELECT state,error,count(*) FROM jobs GROUP BY state,error ORDER BY state,error")]}


@contextlib.contextmanager
def single_worker(state: Path):
    """Prevent timer/manual worker overlap without blocking durable enqueue."""
    with Path(str(state) + ".worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("enqueue", "work", "status"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--item-id")
    parser.add_argument("--title-root")
    parser.add_argument("--limit", type=int, default=4)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    state, media = Path(config["state_db"]), Path(config.get("media_root", "/data/media"))
    with contextlib.closing(connect(state)) as db:
        if args.action == "enqueue":
            if not args.item_id or not args.title_root: parser.error("enqueue requires --item-id and --title-root")
            enqueue(db, args.item_id, title_root(args.title_root, media))
            print(json.dumps({"queued": 1}, sort_keys=True))
        elif args.action == "status":
            print(json.dumps(status(db), sort_keys=True))
        else:
            with single_worker(state) as acquired:
                result = work(db, Api(config), max(1, min(args.limit, 16))) if acquired else {"busy": True}
                print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
