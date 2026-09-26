#!/usr/bin/env python3
"""Bounded recovery of approved season searches through supported APIs only."""

from __future__ import annotations

import argparse
import contextlib
from datetime import datetime
import fcntl
import json
from pathlib import Path, PurePosixPath
import sqlite3
import time
import urllib.parse
import urllib.request


def timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo else None
    except ValueError:
        return None


def positive_id(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class JsonApi:
    def __init__(self, base, key):
        parsed = urllib.parse.urlsplit(base)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("API base URL must use HTTP(S) without embedded credentials, query or fragment")
        self.base, self.key = base.rstrip("/"), key

    def call(self, route, params=None, body=None):
        url = self.base + "/" + route.lstrip("/")
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            url,
            data=data,
            headers={"X-Api-Key": self.key, "Accept": "application/json", "Content-Type": "application/json"},
            method="GET" if body is None else "POST",
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.load(response)


def open_state(path, apply):
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        return sqlite3.connect(path)
    db = sqlite3.connect(":memory:")
    if path.exists():
        with sqlite3.connect(f"file:{urllib.parse.quote(str(path))}?mode=ro", uri=True) as source:
            source.backup(db)
    return db


class SearchGuard:
    def __init__(self, seerr, instances, db, apply=False, clock=time.time):
        self.seerr, self.instances, self.db = seerr, instances, db
        self.apply, self.clock = apply, clock
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS attempts (
            request_id INTEGER NOT NULL, season INTEGER NOT NULL,
            service_id INTEGER NOT NULL, series_id INTEGER NOT NULL,
            started_at REAL NOT NULL, state TEXT NOT NULL, command_id INTEGER,
            PRIMARY KEY(request_id,season))""")
        self.db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.commit()

    def requests(self):
        rows = []
        for skip in range(0, 2000, 100):
            data = self.seerr.call(
                "api/v1/request", {"take": 100, "skip": skip, "sort": "added", "sortDirection": "desc"}
            )
            batch, total = data.get("results"), (data.get("pageInfo") or {}).get("results")
            if not isinstance(batch, list) or not isinstance(total, int):
                raise ValueError("incomplete Seerr snapshot")
            rows.extend(batch)
            if len(rows) >= total:
                return rows
            if not batch:
                raise ValueError("incomplete Seerr snapshot")
        raise ValueError("Seerr snapshot exceeds bounded pages")

    def candidate(self, request, season):
        created = timestamp(request.get("createdAt"))
        if request.get("type") != "tv" or request.get("status") != 2 or not positive_id(request.get("id")):
            return "request-inactive", None
        if created is None or not 180 <= self.clock() - created <= 86400:
            return "request-age", None
        requested = [s for s in request.get("seasons") or [] if s.get("seasonNumber") == season]
        if len(requested) != 1 or requested[0].get("status") != 2:
            return "season-inactive", None
        media = request.get("media") or {}
        suffix = "4k" if request.get("is4k") else ""
        if media.get("status" + suffix) in {5, 6, 7}:
            return "media-inactive", None
        service, series = media.get("serviceId" + suffix), media.get("externalServiceId" + suffix)
        instance = self.instances.get(service)
        if not instance or not positive_id(series) or not positive_id(media.get("tvdbId")):
            return "unmapped", None
        if request.get("serverId") is not None and request["serverId"] != service:
            return "service-mismatch", None
        return None, (instance, service, series, created, media["tvdbId"])

    def queue(self, api):
        rows = []
        for page in range(1, 21):
            data = api.call(
                "api/v3/queue",
                {"page": page, "pageSize": 100, "includeEpisode": "true", "includeUnknownSeriesItems": "true"},
            )
            batch, total = data.get("records"), data.get("totalRecords")
            if not isinstance(batch, list) or not isinstance(total, int):
                raise ValueError("incomplete Sonarr queue")
            rows.extend(batch)
            if len(rows) >= total:
                return rows
            if not batch:
                raise ValueError("incomplete Sonarr queue")
        raise ValueError("Sonarr queue exceeds bounded pages")

    def eligible(self, request, season):
        reason, mapping = self.candidate(request, season)
        if reason:
            return reason, None
        instance, service, series_id, created, tvdb = mapping
        api = instance["api"]
        series = api.call("api/v3/series/" + str(series_id))
        if series.get("id") != series_id or series.get("tvdbId") != tvdb:
            return "identity-mismatch", None
        path = series.get("path")
        roots = instance.get("allowed_roots") or []
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or ".." in PurePosixPath(path).parts
            or not any(
                PurePosixPath(path).is_relative_to(PurePosixPath(root)) and PurePosixPath(path) != PurePosixPath(root)
                for root in roots
                if isinstance(root, str) and root.startswith("/")
            )
        ):
            return "unknown-path", None
        if series.get("monitored") is not True or not any(
            s.get("seasonNumber") == season and s.get("monitored") is True for s in series.get("seasons") or []
        ):
            return "unmonitored", None
        episodes = api.call("api/v3/episode", {"seriesId": series_id})
        if not isinstance(episodes, list) or any(e.get("seriesId") != series_id for e in episodes):
            return "episode-identity", None
        missing = [
            e
            for e in episodes
            if e.get("seasonNumber") == season
            and e.get("hasFile") is False
            and e.get("monitored") is True
            and timestamp(e.get("airDateUtc")) is not None
            and timestamp(e["airDateUtc"]) <= self.clock()
        ]
        if not missing:
            return "no-aired-missing", None
        if any(e.get("lastSearchTime") and timestamp(e["lastSearchTime"]) is None for e in missing):
            return "unknown-search-time", None
        if all((timestamp(e.get("lastSearchTime")) or 0) >= created for e in missing):
            return "already-searched", None
        episode_ids = {e.get("id") for e in episodes if positive_id(e.get("id"))}
        commands = api.call("api/v3/command")
        for command in commands:
            if command.get("status") not in {"queued", "started"}:
                continue
            body = command.get("body") or {}
            name = (command.get("name") or body.get("name") or "").lower()
            if (
                name == "missingepisodesearch"
                or body.get("seriesId") == series_id
                or series_id in (body.get("seriesIds") or [])
                or episode_ids.intersection(body.get("episodeIds") or [])
            ):
                return "active-command", None
        for row in self.queue(api):
            episode = row.get("episode") or {}
            if (row.get("seriesId") or episode.get("seriesId")) == series_id:
                number = episode.get("seasonNumber", row.get("seasonNumber"))
                if number is None or number == season:
                    return "existing-queue", None
        return None, (api, service, series_id)

    def resume(self, request_id, season, row):
        service, series, started, state, command_id = row
        if state not in {"attempting", "uncertain", "command:queued", "command:started"}:
            return "journalled"
        instance = self.instances.get(service)
        if not instance:
            return "journal-unmapped"
        api = instance["api"]
        commands = [api.call("api/v3/command/" + str(command_id))] if command_id else api.call("api/v3/command")
        matches = [
            c
            for c in commands
            if (c.get("name") or (c.get("body") or {}).get("name")) == "SeasonSearch"
            and (c.get("body") or {}).get("seriesId") == series
            and (c.get("body") or {}).get("seasonNumber") == season
            and (command_id or (timestamp(c.get("queued")) or 0) >= started - 2)
        ]
        if len(matches) == 1 and positive_id(matches[0].get("id")):
            if self.apply:
                self.db.execute(
                    "UPDATE attempts SET state=?,command_id=? WHERE request_id=? AND season=?",
                    ("command:" + str(matches[0].get("status", "unknown")), matches[0]["id"], request_id, season),
                )
                self.db.commit()
            return "reconciled-command"
        return "uncertain-retained"

    def run(self):
        counts = {}
        checked = 0
        cursor_row = self.db.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()
        cursor = tuple(json.loads(cursor_row[0])) if cursor_row else (0, -1)
        snapshot = self.requests()
        candidates = [
            (request, season)
            for request in snapshot
            for season in sorted(
                {
                    s.get("seasonNumber")
                    for s in request.get("seasons") or []
                    if isinstance(s.get("seasonNumber"), int) and s["seasonNumber"] >= 0
                }
            )
        ]
        candidates.sort(key=lambda pair: ((pair[0].get("id", 0), pair[1]) <= cursor, pair[0].get("id", 0), pair[1]))
        for request, season in candidates:
            # Cheap filters do not consume the five-request/season work budget.
            reason, mapping = self.candidate(request, season)
            if reason:
                counts[reason] = counts.get(reason, 0) + 1
                continue
            if checked >= 5:
                counts["budget-deferred"] = counts.get("budget-deferred", 0) + 1
                continue
            checked += 1
            request_id = request["id"]
            if self.apply:
                self.db.execute(
                    "INSERT INTO meta VALUES('cursor',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (json.dumps([request_id, season]),),
                )
                self.db.commit()
            row = self.db.execute(
                "SELECT service_id,series_id,started_at,state,command_id FROM attempts WHERE request_id=? AND season=?",
                (request_id, season),
            ).fetchone()
            try:
                if row:
                    outcome = self.resume(request_id, season, row)
                else:
                    reason, context = self.eligible(request, season)
                    if reason:
                        outcome = reason
                    elif not self.apply:
                        outcome = "would-search"
                    else:
                        # Refetch the request, monitoring, last searches, commands
                        # and queue immediately before journalling and submitting.
                        fresh = self.seerr.call("api/v1/request/" + str(request_id))
                        if fresh.get("id") != request_id:
                            reason, context = "request-identity", None
                        else:
                            reason, context = self.eligible(fresh, season)
                        if reason:
                            outcome = "fresh-" + reason
                        else:
                            api, service, series = context
                            self.db.execute(
                                "INSERT INTO attempts VALUES(?,?,?,?,?,'attempting',NULL)",
                                (request_id, season, service, series, self.clock()),
                            )
                            self.db.commit()
                            try:
                                command = api.call(
                                    "api/v3/command",
                                    body={"name": "SeasonSearch", "seriesId": series, "seasonNumber": season},
                                )
                                if not isinstance(command, dict) or not positive_id(command.get("id")):
                                    raise ValueError("search acceptance has no command ID")
                                self.db.execute(
                                    "UPDATE attempts SET command_id=? WHERE request_id=? AND season=?",
                                    (command["id"], request_id, season),
                                )
                                self.db.commit()
                                row = self.db.execute(
                                    "SELECT service_id,series_id,started_at,state,command_id FROM attempts WHERE request_id=? AND season=?",
                                    (request_id, season),
                                ).fetchone()
                                outcome = self.resume(request_id, season, row)
                            except (OSError, ValueError, TypeError):
                                self.db.execute(
                                    "UPDATE attempts SET state='uncertain' WHERE request_id=? AND season=?",
                                    (request_id, season),
                                )
                                self.db.commit()
                                outcome = "uncertain-retained"
            except (OSError, ValueError, TypeError):
                outcome = "read-error"
            counts[outcome] = counts.get(outcome, 0) + 1
        return {"apply": self.apply, "checked": checked, "outcomes": counts}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    seerr = JsonApi(config["seerr_url"], Path(config["seerr_key_file"]).read_text().strip())
    instances = {}
    for row in config["sonarr_instances"]:
        if row["service_id"] in instances:
            raise ValueError("duplicate Seerr service mapping")
        instances[row["service_id"]] = {
            "api": JsonApi(row["url"], Path(row["key_file"]).read_text().strip()),
            "allowed_roots": row["allowed_roots"],
        }
    state = Path(config["state_db"])
    with contextlib.ExitStack() as stack:
        if args.apply:
            state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            lock = stack.enter_context(state.with_suffix(".lock").open("a+"))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(json.dumps({"skipped": "search guard lock busy"}))
                return
        db = open_state(state, args.apply)
        stack.callback(db.close)
        print(json.dumps(SearchGuard(seerr, instances, db, args.apply).run(), sort_keys=True))


if __name__ == "__main__":
    main()
