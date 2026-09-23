#!/usr/bin/env python3
"""Persist request-ready events and offer them to idle Jellyfin sessions.

No inbound listener or Seerr webhook is required. Credentials are read from
private files at runtime and are never stored in the SQLite outbox.
"""
import argparse
import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


AVAILABLE = 5
ACTIVE_REQUEST = {2, 5}  # Seerr APPROVED / COMPLETED; media can be ready before completion.
ID = re.compile(r"^[0-9a-f]{32}$", re.I)
NON_MEDIA_VIEWS = {"collections", "playlists", "live tv", "music", "photos", "home videos", "books", "audiobooks"}


def valid_id(value):
    return isinstance(value, str) and bool(ID.fullmatch(value))


def ready_in_seerr(request):
    if request.get("status") not in ACTIVE_REQUEST:
        return False
    media = request.get("media") or {}
    if request.get("type") == "movie":
        return media.get("status4k" if request.get("is4k") else "status") == AVAILABLE
    if request.get("type") == "tv":
        seasons = request.get("seasons") or []
        # Seerr SeasonRequest belongs to this request (including is4k) and has
        # only status. Media-library Season has separate status/status4k.
        return bool(seasons) and all(
            isinstance(row.get("seasonNumber"), int) and row.get("seasonNumber") >= 0
            and row.get("status") == AVAILABLE for row in seasons if isinstance(row, dict)
        ) and len(seasons) == sum(isinstance(row, dict) for row in seasons)
    return False


def media_id(request):
    media = request.get("media") or {}
    value = media.get("jellyfinMediaId4k" if request.get("is4k") else "jellyfinMediaId")
    return value if valid_id(value) else None


def owned_views(views, kind):
    allowed = {"movie": "movies", "tv": "tvshows"}
    result = []
    for view in views:
        if not valid_id(view.get("Id")):
            continue
        name = " ".join((view.get("Name") or "").casefold().split())
        if name.startswith("venom ") or name in NON_MEDIA_VIEWS:
            continue
        collection = view.get("CollectionType")
        if collection == allowed[kind] or (collection is None and view.get("Type") in {"CollectionFolder", "UserView"}):
            result.append(view["Id"])
    return result


def playable(item):
    return bool(item and item.get("Type") in {"Movie", "Episode"} and any(
        source.get("Id") or source.get("Path") for source in item.get("MediaSources") or []
        if isinstance(source, dict)
    ))


def jellyfin_authorization(token):
    return 'MediaBrowser Token="' + token + '"'


class JsonApi:
    def __init__(self, base_url, token, header, timeout=8):
        self.base = base_url.rstrip("/")
        self.token = token
        self.header = header
        self.timeout = timeout

    def call(self, path, params=None, body=None):
        url = self.base + "/" + path.lstrip("/")
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {self.header: self.token, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers,
                                         method="POST" if data is not None else "GET")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            if response.status == 204:
                return None
            return json.load(response)


class RequestReady:
    def __init__(self, seerr, jellyfin, db, page_size=100, max_pages=20, verify_per_cycle=20, clock=time.time):
        self.seerr = seerr
        self.jellyfin = jellyfin
        self.db = db
        self.page_size = page_size
        self.max_pages = max_pages
        self.verify_per_cycle = verify_per_cycle
        self.clock = clock
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY, suppressed INTEGER NOT NULL)")
        self.db.execute("""CREATE TABLE IF NOT EXISTS events (
            request_id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, item_id TEXT NOT NULL,
            title TEXT NOT NULL, seasons TEXT NOT NULL, created_at REAL NOT NULL,
            next_attempt REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            accepted_at REAL
        )""")
        self.db.commit()

    def requests_snapshot(self):
        rows = []
        for page in range(self.max_pages):
            data = self.seerr.call("api/v1/request", {"take": self.page_size, "skip": page * self.page_size,
                                                       "sort": "added", "sortDirection": "asc"})
            if not isinstance(data, dict):
                raise ValueError("Seerr request response is not an object")
            batch = data.get("results")
            total = (data.get("pageInfo") or {}).get("results")
            if not isinstance(batch, list) or not isinstance(total, int) or not all(isinstance(row, dict) for row in batch):
                raise ValueError("Seerr request response has no bounded page metadata")
            rows.extend(batch)
            if len(rows) >= total:
                return rows
            if not batch:
                raise ValueError("Seerr returned an empty incomplete page")
        raise ValueError("Seerr requests exceed configured page bound")

    def jellyfin_ready(self, request, view_cache):
        user_id = (request.get("requestedBy") or {}).get("jellyfinUserId")
        item_id = media_id(request)
        kind = request.get("type")
        if not valid_id(user_id) or not item_id or kind not in {"movie", "tv"}:
            return None
        if user_id not in view_cache:
            views = self.jellyfin.call(f"Users/{user_id}/Views")
            view_cache[user_id] = views.get("Items") or []
        parents = owned_views(view_cache[user_id], kind)
        if not parents:
            return None
        item_type = "Movie" if kind == "movie" else "Series"
        matched = False
        for parent in parents:
            page = self.jellyfin.call("Items", {"UserId": user_id, "ParentId": parent,
                "Recursive": "true", "IncludeItemTypes": item_type, "Ids": item_id,
                "Limit": 1, "EnableTotalRecordCount": "false"})
            if any(row.get("Id") == item_id and row.get("Type") == item_type for row in page.get("Items") or []):
                matched = True
                break
        if not matched:
            return None
        item = self.jellyfin.call(f"Users/{user_id}/Items/{item_id}")
        if item.get("Id") != item_id or item.get("Type") != item_type:
            return None
        if kind == "movie":
            if not playable(item):
                return None
        else:
            for season in sorted({row["seasonNumber"] for row in request["seasons"]}):
                episodes = self.jellyfin.call("Items", {"UserId": user_id, "ParentId": item_id,
                    "Recursive": "true", "IncludeItemTypes": "Episode", "ParentIndexNumber": season,
                    "IsMissing": "false", "Limit": 50, "EnableTotalRecordCount": "false"})
                ids = [row.get("Id") for row in episodes.get("Items") or [] if valid_id(row.get("Id"))]
                found = False
                for episode_id in ids:
                    episode = self.jellyfin.call(f"Users/{user_id}/Items/{episode_id}")
                    if episode.get("SeriesId") == item_id and episode.get("ParentIndexNumber") == season and playable(episode):
                        found = True
                        break
                if not found:
                    return None
        title = re.sub(r"\s+", " ", item.get("Name") or "Requested media").strip()
        return user_id, item_id, title[:180]

    def collect(self):
        snapshot = self.requests_snapshot()  # No state change on partial/error response.
        first = self.db.execute("SELECT value FROM meta WHERE key='initialized'").fetchone() is None
        if first:
            with self.db:
                for request in snapshot:
                    if isinstance(request.get("id"), int):
                        self.db.execute("INSERT OR IGNORE INTO requests VALUES (?,?)",
                                        (request["id"], int(ready_in_seerr(request))))
                self.db.execute("INSERT INTO meta VALUES ('initialized','1')")
            return 0
        view_cache = {}
        created = 0
        candidates = []
        for request in snapshot:
            request_id = request.get("id")
            if not isinstance(request_id, int):
                continue
            with self.db:
                self.db.execute("INSERT OR IGNORE INTO requests VALUES (?,0)", (request_id,))
            suppressed = self.db.execute("SELECT suppressed FROM requests WHERE id=?", (request_id,)).fetchone()[0]
            if suppressed or not ready_in_seerr(request) or self.db.execute(
                "SELECT 1 FROM events WHERE request_id=?", (request_id,)).fetchone():
                continue
            candidates.append(request)
        cursor_row = self.db.execute("SELECT value FROM meta WHERE key='verify_cursor'").fetchone()
        cursor = int(cursor_row[0]) if cursor_row else 0
        if candidates:
            start = cursor % len(candidates)
            candidates = (candidates[start:] + candidates[:start])[:self.verify_per_cycle]
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('verify_cursor',?)",
                            (str(cursor + len(candidates)),))
        for request in candidates:
            request_id = request["id"]
            try:
                verified = self.jellyfin_ready(request, view_cache)
            except (OSError, ValueError, KeyError, urllib.error.HTTPError):
                # Keep this request eligible for a later cycle; one unavailable
                # user or server response must not starve other requesters.
                continue
            if not verified:
                continue
            user_id, item_id, title = verified
            seasons = json.dumps(sorted({row["seasonNumber"] for row in request.get("seasons") or []}))
            now = self.clock()
            with self.db:
                cursor = self.db.execute("""INSERT OR IGNORE INTO events
                    (request_id,user_id,item_id,title,seasons,created_at,next_attempt)
                    VALUES (?,?,?,?,?,?,?)""", (request_id, user_id, item_id, title, seasons, now, now))
                created += cursor.rowcount
        return created

    def deliver(self, limit=20):
        now = self.clock()
        pending = self.db.execute("""SELECT request_id,user_id,title,seasons,attempts FROM events
            WHERE accepted_at IS NULL AND next_attempt<=? ORDER BY created_at LIMIT ?""", (now, limit)).fetchall()
        if not pending:
            return 0
        sessions = self.jellyfin.call("Sessions", {"ActiveWithinSeconds": 120}) or []
        if not isinstance(sessions, list):
            raise ValueError("Jellyfin session response is not a list")
        accepted = 0
        for request_id, user_id, title, seasons_json, attempts in pending:
            own = [s for s in sessions if s.get("UserId") == user_id and s.get("IsActive")]
            capable = [s for s in own if valid_id(s.get("Id")) and
                       "DisplayMessage" in (s.get("SupportedCommands") or [])]
            if any(s.get("NowPlayingItem") for s in own) or not capable:
                self._defer(request_id, attempts, 60)
                continue
            seasons = json.loads(seasons_json)
            suffix = " — season " + ", ".join(map(str, seasons)) if seasons else ""
            message = {"Header": "Your request is ready", "Text": title + suffix + " is available in your library.", "TimeoutMs": 8000}
            try:
                self.jellyfin.call(f"Sessions/{capable[0]['Id']}/Message", body=message)
            except (OSError, ValueError, urllib.error.HTTPError):
                self._defer(request_id, attempts + 1, min(3600, 30 * 2 ** min(attempts, 7)))
                continue
            with self.db:
                self.db.execute("UPDATE events SET accepted_at=?, attempts=? WHERE request_id=? AND accepted_at IS NULL",
                                (now, attempts + 1, request_id))
            accepted += 1
        return accepted

    def _defer(self, request_id, attempts, seconds):
        with self.db:
            self.db.execute("UPDATE events SET next_attempt=?, attempts=? WHERE request_id=? AND accepted_at IS NULL",
                            (self.clock() + seconds, attempts, request_id))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    seerr = JsonApi(config["seerr_url"], Path(config["seerr_key_file"]).read_text().strip(), "X-Api-Key")
    jellyfin_token = Path(config["jellyfin_key_file"]).read_text().strip()
    jellyfin = JsonApi(config["jellyfin_url"], jellyfin_authorization(jellyfin_token), "Authorization")
    db = sqlite3.connect(config["state_db"], timeout=10)
    worker = RequestReady(seerr, jellyfin, db)
    while True:
        try:
            created = worker.collect()
            accepted = worker.deliver()
            print(json.dumps({"created": created, "session_accepted": accepted}))
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            print(json.dumps({"error_type": type(error).__name__}), flush=True)
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            break
        time.sleep(max(30, int(config.get("poll_seconds", 300))))


if __name__ == "__main__":
    main()
