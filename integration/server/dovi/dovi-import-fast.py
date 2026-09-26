#!/usr/bin/env python3
"""Consume exact ARR import events without a full media/subtitle sweep."""
from __future__ import annotations

import argparse
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import sqlite3
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

DELAYS = (30, 120, 600, 1800, 7200, 21600, 43200)
MAX_AGE = 48 * 3600
VIDEOS = {".mkv", ".mp4", ".m4v", ".ts", ".m2ts", ".avi", ".mov", ".webm"}


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo else None
    except (ValueError, AttributeError):
        return None


class Api:
    def __init__(self, row):
        self.base = row["url"].rstrip("/")
        parsed = urllib.parse.urlsplit(self.base)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or not parsed.hostname:
            raise ValueError("invalid private ARR URL")
        self.key = Path(row["key_file"]).read_text().strip()

    def get(self, route, params=None):
        url = self.base + "/api/v3/" + route
        if params:
            url += "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(urllib.request.Request(url, headers={"X-Api-Key": self.key}), timeout=8) as response:
            return json.load(response)


def validate_event(event, media):
    title, video = Path(event["title"]), Path(event["file"])
    roots = (media / "movies", media / "shows")
    if ".." in title.parts or ".." in video.parts or title.parent not in roots or not video.is_relative_to(title):
        raise ValueError("import event is outside an exact canonical title")
    if video.suffix.lower() not in VIDEOS or event["app"] not in {"sonarr", "radarr"}:
        raise ValueError("unsupported import event")
    if title.parent != media / ("shows" if event["app"] == "sonarr" else "movies"):
        raise ValueError("import owner does not match canonical root")
    if not isinstance(event.get("item_id"), int) or event["item_id"] <= 0:
        raise ValueError("import event has no native item mapping")
    return title, video


def read_event(path):
    with path.open() as handle:
        text = handle.read(8193)
    if len(text) > 8192:
        raise ValueError("oversized import event")
    if text.startswith("{"):
        return json.loads(text)
    lines = text.splitlines()
    if len(lines) != 7 or lines[0] != "v1":
        raise ValueError("invalid import hook event")
    return {"created": timestamp(lines[1]), "app": lines[2], "item_id": int(lines[3]),
            "title": lines[4], "file": lines[5], "event": lines[6]}


def write_event(spool, name, event):
    descriptor, temporary = tempfile.mkstemp(prefix=".dovi-import-", dir=spool.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(event, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, spool / name)
        descriptor = os.open(spool, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def companion_revision(config, video):
    media = Path(config['media_root'])
    relative = video.relative_to(media)
    companion = Path(config.get('compatibility_root', str(media / 'compatibility' / 'dovi-p8'))) / relative.parent / (video.stem + ' - P8.1 Compatibility.mkv')
    if not companion.is_file() or companion.is_symlink():
        raise ValueError('companion is missing or unsafe')
    stat = companion.stat()
    return hashlib.sha256(repr((str(companion), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)).encode()).hexdigest()


class FastImports:
    def __init__(self, config, db, apis, execute=subprocess.run, clock=time.time):
        self.config, self.db, self.apis, self.execute, self.clock = config, db, apis, execute, clock
        self.media, self.spool, self.claims = (Path(config[key]) for key in ("media_root", "spool", "claims"))
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS fingerprints(fingerprint TEXT PRIMARY KEY,name TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS history_retry(app TEXT PRIMARY KEY,attempts INTEGER NOT NULL,first_seen REAL NOT NULL,next_due REAL NOT NULL,dead INTEGER NOT NULL)")
        self.identity_cache = {}
        self.db.execute("""CREATE TABLE IF NOT EXISTS jobs (
            name TEXT PRIMARY KEY,event TEXT NOT NULL,title TEXT NOT NULL,first_seen REAL NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,next_due REAL NOT NULL DEFAULT 0,
            state TEXT NOT NULL DEFAULT 'pending',error TEXT NOT NULL DEFAULT '')""")
        self.db.commit()

    def backfill(self):
        total = 0
        self.history_app = None
        for app, api in self.apis.items():
            retry = self.db.execute("SELECT attempts,first_seen,next_due,dead FROM history_retry WHERE app=?", (app,)).fetchone()
            if retry and (retry[3] or retry[2] > self.clock()):
                continue
            self.history_app = app
            saved = self.db.execute("SELECT value FROM meta WHERE key=?", ("history:" + app,)).fetchone()
            checkpoint = int(saved[0]) if saved else 0
            rows, finished = [], False
            for page in range(1, 21):
                data = api.get("history", {"page": page, "pageSize": 100, "sortKey": "date", "sortDirection": "descending"})
                records = data.get("records")
                if not isinstance(records, list) or not isinstance(data.get("totalRecords"), int):
                    raise ValueError("incomplete import history")
                for row in records:
                    when = timestamp(row.get("date"))
                    if not isinstance(row.get("id"), int) or when is None:
                        raise ValueError("invalid import history")
                    if row["id"] <= checkpoint or when < self.clock() - 86400:
                        finished = True
                        break
                    rows.append(row)
                if finished or page * 100 >= data["totalRecords"]:
                    finished = True
                    break
                if not records:
                    raise ValueError("empty incomplete import history")
            if not finished:
                raise ValueError("import history exceeds bounded pages")
            for row in rows:
                if row.get("eventType") != "downloadFolderImported":
                    continue
                item_id = row.get("seriesId" if app == "sonarr" else "movieId")
                video = (row.get("data") or {}).get("importedPath")
                if not isinstance(video, str):
                    continue
                path = Path(video)
                try:
                    relative = path.relative_to(self.media / ("shows" if app == "sonarr" else "movies"))
                    event = {"created": timestamp(row["date"]), "app": app, "item_id": item_id,
                             "title": str(self.media / ("shows" if app == "sonarr" else "movies") / relative.parts[0]),
                             "file": video, "event": "history-import"}
                    validate_event(event, self.media)
                except (ValueError, IndexError):
                    continue
                name = f"history-{app}-{row['id']}.event"
                if not self.db.execute("SELECT 1 FROM jobs WHERE name=?", (name,)).fetchone() and not (self.claims / name).exists():
                    write_event(self.spool, name, event)
                    total += 1
            # Queue writes are durable BEFORE advancing the native-history cursor.
            if rows:
                self.db.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                ("history:" + app, str(max(row["id"] for row in rows))))
                self.db.commit()
            self.db.execute("DELETE FROM history_retry WHERE app=?", (app,))
            self.db.commit()
        return total

    def claim(self):
        for source in sorted(self.spool.glob("*.event"))[:1000]:
            destination = self.claims / source.name
            if destination.exists():
                continue
            try:
                os.rename(source, destination)
            except FileNotFoundError:
                continue
        # Includes claims left by a crash before journalling or acknowledgement.
        for path in sorted(self.claims.glob("*.event"))[:1000]:
            if self.db.execute("SELECT 1 FROM jobs WHERE name=?", (path.name,)).fetchone():
                continue
            try:
                event = read_event(path)
                title, video = validate_event(event, self.media)
                stat = video.stat()
                companion = event.get('companion_revision')
                if companion is not None and companion != companion_revision(self.config, video):
                    raise ValueError('companion changed before event claim')
                fingerprint = hashlib.sha256(json.dumps([event['app'], event['item_id'], str(video), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, companion]).encode()).hexdigest()
                if self.db.execute("SELECT 1 FROM fingerprints WHERE fingerprint=?", (fingerprint,)).fetchone():
                    self.db.execute("INSERT INTO jobs(name,event,title,first_seen,state,error) VALUES(?,?,?,?,'duplicate','same-fingerprint')", (path.name, json.dumps(event), str(title), self.clock()))
                    self.db.commit()
                    path.unlink(missing_ok=True)
                    continue
                self.db.execute("INSERT INTO fingerprints VALUES(?,?)", (fingerprint, path.name))
                # A genuinely new import permits history polling after a terminal outage.
                self.db.execute("DELETE FROM history_retry WHERE app=? AND dead=1", (event['app'],))
                self.db.execute("INSERT INTO jobs(name,event,title,first_seen) VALUES(?,?,?,?)",
                                (path.name, json.dumps(event), str(title), event.get("created") or self.clock()))
            except (OSError, ValueError, KeyError, TypeError):
                self.db.execute("INSERT INTO jobs(name,event,title,first_seen,state,error) VALUES(?,?,?,?,'dead','invalid-event')",
                                (path.name, "{}", "", self.clock()))
            self.db.commit()

    def identity(self, event):
        title, video = validate_event(event, self.media)
        if not video.is_file():
            raise ValueError("imported file is no longer present")
        if title.is_symlink() or video.is_symlink() or not video.resolve().is_relative_to(title.resolve()):
            raise ValueError("imported file escapes its canonical title")
        api = self.apis.get(event["app"])
        if not api:
            raise ValueError("import event has no configured ARR owner")
        cache_key = (event['app'], event['item_id'], str(title))
        if cache_key not in self.identity_cache:
            self.identity_cache[cache_key] = api.get(("series/" if event["app"] == "sonarr" else "movie/") + str(event["item_id"]))
        row = self.identity_cache[cache_key]
        if row.get("id") != event["item_id"] or row.get("path") != str(title):
            raise ValueError("native import title identity/path changed")
        key = "Tvdb" if event["app"] == "sonarr" else "Tmdb"
        number = row.get("tvdbId" if key == "Tvdb" else "tmdbId")
        if not isinstance(number, int) or number <= 0:
            raise ValueError("native provider identity missing")
        return {key: str(number)}

    def companion_ready(self, video):
        # Recover journal mapping, then revalidate against CURRENT native ARR.
        self.identity_cache.clear()
        rows = self.db.execute("SELECT event FROM jobs WHERE json_extract(event,'$.file')=? ORDER BY first_seen DESC LIMIT 100", (str(video),)).fetchall()
        event = next((json.loads(row[0]) for row in rows if json.loads(row[0]).get('app') in self.apis), None)
        if event is None:
            relative = video.relative_to(self.media)
            app = 'sonarr' if relative.parts[0] == 'shows' else 'radarr' if relative.parts[0] == 'movies' else None
            if not app or app not in self.apis or len(relative.parts) < 3:
                raise ValueError('companion has no configured canonical owner')
            title = self.media / relative.parts[0] / relative.parts[1]
            catalog = self.apis[app].get('series' if app == 'sonarr' else 'movie')
            if not isinstance(catalog, list) or len(catalog) > 10000:
                raise ValueError('native title catalog exceeds bound')
            matches = [item for item in catalog if item.get('path') == str(title)]
            if len(matches) != 1:
                raise ValueError('companion has no unique native title mapping')
            event = {'app': app, 'item_id': matches[0].get('id'), 'title': str(title), 'file': str(video)}
        self.identity(event)
        revision = companion_revision(self.config, video)
        event.update(created=self.clock(), event='companion-ready', companion_revision=revision)
        name = 'companion-' + revision + '.event'
        if not self.db.execute('SELECT 1 FROM jobs WHERE name=?', (name,)).fetchone() and not (self.claims / name).exists():
            write_event(self.spool, name, event)
        self.db.execute("UPDATE jobs SET next_due=0 WHERE json_extract(event,'$.file')=? AND state='waiting' AND error='p7-companion-wait'", (str(video),))
        self.db.commit()
        return {'companion_event': 'queued', 'revision': revision}

    def defer(self, names, kind, waiting=False):
        for name in names:
            attempts, first_seen = self.db.execute("SELECT attempts,first_seen FROM jobs WHERE name=?", (name,)).fetchone()
            attempts += 0 if waiting else 1
            dead = attempts >= 8 or self.clock() - first_seen >= MAX_AGE
            delay = 300 if waiting else DELAYS[min(attempts - 1, 6)] * random.uniform(0.9, 1.1)
            self.db.execute("UPDATE jobs SET attempts=?,next_due=?,state=?,error=? WHERE name=?",
                            (attempts, self.clock() + delay, "dead" if dead else "waiting" if waiting else "pending", kind, name))
        self.db.commit()

    def run(self):
        result = {"backfilled": 0, "linked_jobs": 0, "deferred": 0, "read_errors": 0}
        try:
            result["backfilled"] = self.backfill()
        except (OSError, ValueError, TypeError):
            result["read_errors"] += 1
            # The history backstop itself must not hammer an unavailable native API.
            for app in ([self.history_app] if self.history_app else []):
                row = self.db.execute("SELECT attempts,first_seen FROM history_retry WHERE app=?", (app,)).fetchone()
                attempts, first_seen = (row[0] + 1, row[1]) if row else (1, self.clock())
                self.db.execute("INSERT INTO history_retry VALUES(?,?,?,?,?) ON CONFLICT(app) DO UPDATE SET attempts=excluded.attempts,next_due=excluded.next_due,dead=excluded.dead", (app, attempts, first_seen, self.clock() + DELAYS[min(attempts - 1, 6)] * random.uniform(.9, 1.1), int(attempts >= 8 or self.clock() - first_seen >= MAX_AGE)))
            self.db.commit()
        self.claim()
        self.db.execute("UPDATE jobs SET state='dead',error='expired' WHERE state IN ('pending','waiting') AND first_seen<=?",
                        (self.clock() - MAX_AGE,))
        self.db.commit()
        rows = list(self.db.execute("SELECT name,event,title FROM jobs WHERE state IN ('pending','waiting') AND next_due<=?", (self.clock(),)))
        grouped = {}
        for name, event, title in rows:
            grouped.setdefault(title, []).append((name, json.loads(event)))
        cursor = self.db.execute("SELECT value FROM meta WHERE key='title-cursor'").fetchone()
        titles = sorted(grouped, key=lambda title: (title <= (cursor[0] if cursor else ""), title))[:5]
        for title in titles:
            jobs = grouped[title]
            names = [name for name, _ in jobs]
            self.db.execute("INSERT INTO meta VALUES('title-cursor',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (title,))
            self.db.commit()
            try:
                identity = None
                for _, event in jobs:
                    current = self.identity(event)
                    if identity is not None and identity != current:
                        raise ValueError("conflicting import identity")
                    identity = current
                command = ["/usr/bin/python3", self.config["reconciler"], "--apply", "--notify-jellyfin",
                           "--media-root", str(self.media), "--scope-title", title,
                           "--state", self.config["scoped_state"], "--notification-state", self.config["notification_state"],
                           "--run-lock", self.config["reconcile_lock"], "--publication-lock", self.config["publication_lock"],
                           "--title-locks", self.config["title_locks"]]
                for option in ("view-root", "compatibility-root", "queue", "queue-lock", "retry-state", "worker", "jellyfin"):
                    if option.replace("-", "_") in self.config:
                        command += ["--" + option, self.config[option.replace("-", "_")]]
                if self.config.get("new_title_bridge"):
                    command.append("--new-title-bridge")
                for path in sorted({event["file"] for _, event in jobs}):
                    command += ["--scope-file", path]
                for key, value in (identity or {}).items():
                    command += ["--provider-id", key + "=" + value]
                process = self.execute(command, check=False, capture_output=True, text=True, timeout=600)
                data = json.loads(process.stdout.strip().splitlines()[-1])
                if process.returncode or data.get("errors"):
                    raise ValueError("scoped reconciliation failed")
                if data.get("skipped"):
                    self.defer(names, "scope-lock-busy", waiting=True)
                elif data.get("view_waiting"):
                    self.defer(names, "unknown-probe" if data.get("probe_deferred") else "p7-companion-wait", waiting=not data.get("probe_deferred"))
                else:
                    self.db.executemany("UPDATE jobs SET state='view-ready',error='' WHERE name=?", ((name,) for name in names))
                    self.db.commit()
                    for name in names:
                        (self.claims / name).unlink(missing_ok=True)
                    result["linked_jobs"] += len(names)
            except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired):
                self.defer(names, "scoped-error")
                result["deferred"] += len(names)
        result["pending"] = self.db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('pending','waiting')").fetchone()[0]
        result["deadletters"] = self.db.execute("SELECT COUNT(*) FROM jobs WHERE state='dead'").fetchone()[0]
        result["history_deadletters"] = self.db.execute("SELECT COUNT(*) FROM history_retry WHERE dead=1").fetchone()[0]
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument('--companion-ready', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if not isinstance(config.get("arr_instances"), list):
        raise ValueError("private ARR instance configuration required")
    for name in ("spool", "claims"):
        Path(config[name]).mkdir(parents=True, exist_ok=True, mode=0o755)
    if args.companion_ready:
        apis = {row['name']: Api(row) for row in config['arr_instances']}
        with sqlite3.connect(config['state_db']) as db:
            worker = FastImports(config, db, apis)
            try:
                print(json.dumps(worker.companion_ready(args.companion_ready), sort_keys=True))
            except (OSError, ValueError, KeyError, TypeError):
                print(json.dumps({'companion_event': 'deferred', 'reason': 'native-mapping-or-file-unavailable; full-backstop-retained'}))
        return
    with Path(config["worker_lock"]).open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"skipped": "fast-worker lock busy"}))
            return
        apis = {}
        for row in config["arr_instances"]:
            if row["name"] not in {"sonarr", "radarr"} or row["name"] in apis:
                raise ValueError("invalid/duplicate ARR instance")
            apis[row["name"]] = Api(row)
        with sqlite3.connect(config["state_db"]) as db:
            print(json.dumps(FastImports(config, db, apis).run(), sort_keys=True))


if __name__ == "__main__":
    main()
