import copy
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest


spec = importlib.util.spec_from_file_location("search_guard", Path(__file__).with_name("worker.py"))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
NOW = 1800957600


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def request(number=1):
    return {
        "id": number,
        "type": "tv",
        "status": 2,
        "createdAt": stamp(NOW - 600),
        "serverId": 3,
        "is4k": False,
        "media": {"serviceId": 3, "externalServiceId": 10, "tvdbId": 100},
        "seasons": [{"seasonNumber": 1, "status": 2}],
    }


class FakeSeerr:
    def __init__(self):
        self.rows = [request()]
        self.fresh_transform = lambda row: row

    def call(self, route, params=None, body=None):
        if route == "api/v1/request":
            return {"results": copy.deepcopy(self.rows), "pageInfo": {"results": len(self.rows)}}
        return self.fresh_transform(
            copy.deepcopy(next(r for r in self.rows if r["id"] == int(route.rsplit("/", 1)[1])))
        )


class FakeSonarr:
    def __init__(self):
        self.series = {
            "id": 10,
            "tvdbId": 100,
            "path": "/fixture/shows/title",
            "monitored": True,
            "seasons": [{"seasonNumber": 1, "monitored": True}],
        }
        self.episodes = [
            {
                "id": 11,
                "seriesId": 10,
                "seasonNumber": 1,
                "monitored": True,
                "hasFile": False,
                "airDateUtc": stamp(NOW - 1000),
            }
        ]
        self.commands = []
        self.rows = []
        self.posts = []
        self.timeout = False
        self.accept_before_timeout = False

    def call(self, route, params=None, body=None):
        if body is not None:
            self.posts.append(copy.deepcopy(body))
            command = {
                "id": 20 + len(self.posts),
                "name": "SeasonSearch",
                "body": copy.deepcopy(body),
                "status": "queued",
                "queued": stamp(NOW),
            }
            if not self.timeout or self.accept_before_timeout:
                self.commands.append(command)
            if self.timeout:
                raise TimeoutError("fixture uncertain transport")
            return copy.deepcopy(command)
        if route.startswith("api/v3/series/"):
            return copy.deepcopy(self.series)
        if route == "api/v3/episode":
            return copy.deepcopy(self.episodes)
        if route == "api/v3/command":
            return copy.deepcopy(self.commands)
        if route.startswith("api/v3/command/"):
            return copy.deepcopy(next(c for c in self.commands if c["id"] == int(route.rsplit("/", 1)[1])))
        if route == "api/v3/queue":
            return {"records": copy.deepcopy(self.rows), "totalRecords": len(self.rows)}
        raise AssertionError(route)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.seerr, self.sonarr = FakeSeerr(), FakeSonarr()
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)

    def guard(self, apply=True):
        return worker.SearchGuard(
            self.seerr,
            {3: {"api": self.sonarr, "allowed_roots": ["/fixture/shows"]}},
            self.db,
            apply=apply,
            clock=lambda: NOW,
        )

    def test_dropped_burst_search_gets_one_scoped_retry(self):
        self.seerr.rows.append(request(2))
        result = self.guard().run()
        self.assertEqual(self.sonarr.posts, [{"name": "SeasonSearch", "seriesId": 10, "seasonNumber": 1}])
        self.assertEqual(result["outcomes"]["reconciled-command"], 1)
        self.assertEqual(result["outcomes"]["active-command"], 1)
        self.assertEqual(self.db.execute("SELECT state FROM attempts").fetchone()[0], "command:queued")

    def test_native_search_after_request_is_not_repeated(self):
        self.sonarr.episodes[0]["lastSearchTime"] = stamp(NOW - 10)
        self.assertEqual(self.guard().run()["outcomes"], {"already-searched": 1})
        self.assertEqual(self.sonarr.posts, [])

    def test_monitored_false_and_cancelled_request_are_held(self):
        self.sonarr.series["seasons"][0]["monitored"] = False
        self.assertEqual(self.guard().run()["outcomes"], {"unmonitored": 1})
        self.seerr.rows[0]["status"] = 3
        self.assertEqual(self.guard().run()["outcomes"], {"request-inactive": 1})
        self.assertEqual(self.sonarr.posts, [])

    def test_completed_request_and_season_are_never_searched(self):
        self.seerr.rows[0]["status"] = 5
        self.assertEqual(self.guard().run()["outcomes"], {"request-inactive": 1})
        self.seerr.rows[0]["status"] = 2
        self.seerr.rows[0]["seasons"][0]["status"] = 5
        self.assertEqual(self.guard().run()["outcomes"], {"season-inactive": 1})
        self.assertEqual(self.sonarr.posts, [])

    def test_existing_download_queue_prevents_duplicate_search(self):
        self.sonarr.rows = [{"seriesId": 10, "episode": {"seasonNumber": 1}, "status": "completed"}]
        self.assertEqual(self.guard().run()["outcomes"], {"existing-queue": 1})
        self.assertEqual(self.sonarr.posts, [])

    def test_active_global_or_episode_command_prevents_search(self):
        self.sonarr.commands = [{"name": "MissingEpisodeSearch", "status": "started", "body": {}}]
        self.assertEqual(self.guard().run()["outcomes"], {"active-command": 1})
        self.sonarr.commands = [{"name": "EpisodeSearch", "status": "queued", "body": {"episodeIds": [11]}}]
        self.assertEqual(self.guard().run()["outcomes"], {"active-command": 1})

    def test_future_episodes_and_completed_files_are_not_candidates(self):
        self.sonarr.episodes[0]["airDateUtc"] = stamp(NOW + 1000)
        self.assertEqual(self.guard().run()["outcomes"], {"no-aired-missing": 1})
        self.sonarr.episodes[0]["airDateUtc"] = stamp(NOW - 1000)
        self.sonarr.episodes[0]["hasFile"] = True
        self.assertEqual(self.guard().run()["outcomes"], {"no-aired-missing": 1})

    def test_stale_or_not_yet_aged_requests_are_not_candidates(self):
        for age in (100, 86401):
            self.seerr.rows[0]["createdAt"] = stamp(NOW - age)
            self.assertEqual(self.guard().run()["outcomes"], {"request-age": 1})
        self.assertEqual(self.sonarr.posts, [])

    def test_fresh_cancellation_or_unmonitoring_before_post_is_respected(self):
        self.seerr.fresh_transform = lambda row: dict(row, status=3)
        self.assertEqual(self.guard().run()["outcomes"], {"fresh-request-inactive": 1})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 0)
        self.assertEqual(self.sonarr.posts, [])

    def test_fresh_unmonitoring_before_post_is_respected(self):
        original = self.sonarr.call
        reads = 0

        def call(route, params=None, body=None):
            nonlocal reads
            if route.startswith("api/v3/series/"):
                reads += 1
                if reads == 2:
                    self.sonarr.series["monitored"] = False
            return original(route, params, body)

        self.sonarr.call = call
        self.assertEqual(self.guard().run()["outcomes"], {"fresh-unmonitored": 1})
        self.assertEqual(self.sonarr.posts, [])

    def test_4k_requires_its_own_mapping(self):
        self.seerr.rows[0]["is4k"] = True
        self.assertEqual(self.guard().run()["outcomes"], {"unmapped": 1})
        self.seerr.rows[0]["media"].update(serviceId4k=3, externalServiceId4k=10)
        self.assertEqual(self.guard(apply=False).run()["outcomes"], {"would-search": 1})

    def test_malformed_search_time_and_available_media_fail_closed(self):
        self.sonarr.episodes[0]["lastSearchTime"] = "unknown"
        self.assertEqual(self.guard().run()["outcomes"], {"unknown-search-time": 1})
        self.seerr.rows[0]["media"]["status"] = 5
        self.assertEqual(self.guard().run()["outcomes"], {"media-inactive": 1})
        self.assertEqual(self.sonarr.posts, [])

    def test_uncertain_transport_is_journalled_before_post_and_not_repeated(self):
        self.sonarr.timeout = True
        guard = self.guard()
        original = self.sonarr.call

        def call(route, params=None, body=None):
            if body is not None:
                self.assertEqual(self.db.execute("SELECT state FROM attempts").fetchone()[0], "attempting")
            return original(route, params, body)

        self.sonarr.call = call
        self.assertEqual(guard.run()["outcomes"], {"uncertain-retained": 1})
        self.assertEqual(guard.run()["outcomes"], {"uncertain-retained": 1})
        self.assertEqual(len(self.sonarr.posts), 1)

    def test_accepted_but_lost_response_reconciles_existing_command(self):
        self.sonarr.timeout, self.sonarr.accept_before_timeout = True, True
        guard = self.guard()
        self.assertEqual(guard.run()["outcomes"], {"uncertain-retained": 1})
        self.assertEqual(guard.run()["outcomes"], {"reconciled-command": 1})
        self.sonarr.commands[0]["status"] = "completed"
        self.assertEqual(guard.run()["outcomes"], {"reconciled-command": 1})
        self.assertEqual(self.db.execute("SELECT state FROM attempts").fetchone()[0], "command:completed")
        self.assertEqual(len(self.sonarr.posts), 1)

    def test_identity_path_and_service_mapping_fail_closed(self):
        self.sonarr.series["tvdbId"] = 999
        self.assertEqual(self.guard().run()["outcomes"], {"identity-mismatch": 1})
        self.sonarr.series["tvdbId"] = 100
        self.sonarr.series["path"] = "/unknown/title"
        self.assertEqual(self.guard().run()["outcomes"], {"unknown-path": 1})
        self.seerr.rows[0]["media"]["serviceId"] = 999
        self.assertEqual(self.guard().run()["outcomes"], {"unmapped": 1})
        self.assertEqual(self.sonarr.posts, [])

    def test_readonly_default_does_not_post_or_record_attempt(self):
        self.assertEqual(self.guard(apply=False).run()["outcomes"], {"would-search": 1})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 0)
        self.assertEqual(self.sonarr.posts, [])

    def test_budget_is_five_and_cursor_rotates(self):
        self.seerr.rows = [request(n) for n in range(1, 7)]
        guard = self.guard()
        self.assertEqual(guard.run()["checked"], 5)
        self.assertEqual(json_cursor(self.db), [5, 1])
        self.assertEqual(guard.run()["checked"], 5)
        self.assertEqual(json_cursor(self.db), [4, 1])

    def test_dry_run_state_is_memory_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "absent.sqlite"
            db = worker.open_state(path, False)
            db.close()
            self.assertFalse(path.exists())
            with sqlite3.connect(path) as source:
                source.execute("CREATE TABLE fixture(value INTEGER)")
                source.execute("INSERT INTO fixture VALUES(1)")
            db = worker.open_state(path, False)
            db.execute("UPDATE fixture SET value=2")
            db.commit()
            db.close()
            with sqlite3.connect(path) as source:
                self.assertEqual(source.execute("SELECT value FROM fixture").fetchone()[0], 1)


def json_cursor(db):
    import json

    return json.loads(db.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
