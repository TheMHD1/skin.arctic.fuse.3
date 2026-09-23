import importlib.util
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("request_ready_worker", Path(__file__).with_name("worker.py"))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

USER = "a" * 32
OTHER = "b" * 32
MOVIE = "c" * 32
SERIES = "d" * 32
EPISODE = "e" * 32
OWNED = "1" * 32
VENOM = "2" * 32
SESSION = "3" * 32


def request(number=1, kind="movie", media_status=5, seasons=None, requester=USER):
    return {"id": number, "status": 2, "type": kind, "is4k": False,
            "requestedBy": {"jellyfinUserId": requester},
            "media": {"status": media_status, "jellyfinMediaId": MOVIE if kind == "movie" else SERIES},
            "seasons": seasons or []}


class Seerr:
    def __init__(self, rows):
        self.rows = rows

    def call(self, path, params=None, body=None):
        start = params["skip"]
        return {"pageInfo": {"results": len(self.rows)}, "results": self.rows[start:start + params["take"]]}


class Jellyfin:
    def __init__(self):
        self.calls = []
        self.sessions = []
        self.fail_message = False
        self.playable = True
        self.episode_seasons = {1, 2}
        self.permitted = {USER}
        self.venom_only = False

    def call(self, path, params=None, body=None):
        self.calls.append((path, params, body))
        if path == "Sessions":
            return self.sessions
        if path.endswith("/Message"):
            if self.fail_message:
                raise OSError("offline")
            return None
        if path.endswith("/Views"):
            uid = path.split("/")[1]
            if uid not in self.permitted:
                return {"Items": []}
            views = [
                {"Id": OWNED, "Name": "Movies and Shows", "Type": "CollectionFolder", "CollectionType": None},
                {"Id": VENOM, "Name": "Venom Movies", "Type": "CollectionFolder", "CollectionType": "movies"}
            ]
            return {"Items": views[1:] if self.venom_only else views}
        if path == "Items":
            if params["ParentId"] == VENOM:
                return {"Items": []}
            if params["IncludeItemTypes"] == "Episode":
                season = params["ParentIndexNumber"]
                return {"Items": [{"Id": EPISODE}]} if season in self.episode_seasons else {"Items": []}
            item_id = params["Ids"]
            return {"Items": [{"Id": item_id, "Type": params["IncludeItemTypes"]}]}
        if path.endswith("/Items/" + EPISODE):
            season = next((p["ParentIndexNumber"] for route, p, _ in reversed(self.calls)
                           if route == "Items" and p["IncludeItemTypes"] == "Episode"), None)
            return {"Id": EPISODE, "Type": "Episode", "SeriesId": SERIES,
                    "ParentIndexNumber": season, "MediaSources": [{"Id": "source"}] if self.playable else []}
        if path.endswith("/Items/" + MOVIE):
            return {"Id": MOVIE, "Type": "Movie", "Name": "Ready Movie",
                    "MediaSources": [{"Id": "source"}] if self.playable else []}
        if path.endswith("/Items/" + SERIES):
            return {"Id": SERIES, "Type": "Series", "Name": "Ready Show"}
        raise AssertionError(path)


class RequestReadyTests(unittest.TestCase):
    def setUp(self):
        self.seerr = Seerr([])
        self.jellyfin = Jellyfin()
        self.now = 1000
        self.db = sqlite3.connect(":memory:")
        self.task = worker.RequestReady(self.seerr, self.jellyfin, self.db, page_size=2,
                                        max_pages=3, clock=lambda: self.now)

    def events(self):
        return self.db.execute("SELECT request_id,user_id,accepted_at,attempts FROM events ORDER BY request_id").fetchall()

    def test_initial_ready_requests_are_seeded_without_alert_and_new_request_is_durable(self):
        self.seerr.rows = [request(1)]
        self.assertEqual(0, self.task.collect())
        self.assertEqual([], self.events())
        self.seerr.rows.append(request(2))
        self.assertEqual(1, self.task.collect())
        self.assertEqual(0, self.task.collect())
        self.assertEqual([2], [row[0] for row in self.events()])

    def test_pending_at_boot_becomes_ready_only_for_requester_with_owned_playable_item(self):
        self.seerr.rows = [request(1, media_status=3)]
        self.task.collect()
        self.seerr.rows[0]["media"]["status"] = 5
        self.jellyfin.playable = False
        self.assertEqual(0, self.task.collect())
        self.jellyfin.playable = True
        self.assertEqual(1, self.task.collect())
        self.seerr.rows.append(request(2, requester=OTHER))
        self.assertEqual(0, self.task.collect())
        self.assertEqual([(1, USER, None, 0)], self.events())
        self.assertFalse(any(path.endswith("/Items/" + MOVIE) and path.startswith("Users/" + OTHER)
                             for path, _, _ in self.jellyfin.calls))

    def test_tv_waits_for_every_requested_season_and_accessible_episode(self):
        seasons = [{"seasonNumber": 1, "status": 5}, {"seasonNumber": 2, "status": 3}]
        self.seerr.rows = [request(1, kind="tv", media_status=4, seasons=seasons)]
        self.task.collect()
        self.assertEqual(0, self.task.collect())
        seasons[1]["status"] = 5
        self.jellyfin.episode_seasons = {1}
        self.assertEqual(0, self.task.collect())
        self.jellyfin.episode_seasons = {1, 2}
        self.assertEqual(1, self.task.collect())

    def test_4k_tv_uses_request_season_status_and_4k_media_id(self):
        candidate = request(1, kind="tv", media_status=3,
                            seasons=[{"seasonNumber": 1, "status": 5}])
        candidate["is4k"] = True
        candidate["media"]["status4k"] = 5
        candidate["media"]["jellyfinMediaId4k"] = "f" * 32
        self.assertTrue(worker.ready_in_seerr(candidate))
        self.assertEqual("f" * 32, worker.media_id(candidate))
        candidate["seasons"][0]["status"] = 2
        self.assertFalse(worker.ready_in_seerr(candidate))

    def test_venom_only_access_never_satisfies_owned_readiness(self):
        self.task.collect()
        self.seerr.rows = [request(1)]
        self.jellyfin.venom_only = True
        self.assertEqual(0, self.task.collect())
        self.assertEqual([], self.events())

    def test_session_delivery_defers_playback_and_retries_failure_without_duplicate(self):
        self.task.collect()
        self.seerr.rows = [request(1)]
        self.task.collect()
        self.jellyfin.sessions = [{"Id": SESSION, "UserId": OTHER, "IsActive": True,
                                  "SupportedCommands": ["DisplayMessage"]}]
        self.assertEqual(0, self.task.deliver())
        self.now += 61
        self.jellyfin.sessions = [{"Id": SESSION, "UserId": USER, "IsActive": True,
                                  "SupportedCommands": ["DisplayMessage"], "NowPlayingItem": {"Id": MOVIE}}]
        self.assertEqual(0, self.task.deliver())
        self.now += 61
        self.jellyfin.sessions[0]["NowPlayingItem"] = None
        self.jellyfin.fail_message = True
        self.assertEqual(0, self.task.deliver())
        self.assertIsNone(self.events()[0][2])
        self.now += 31
        self.jellyfin.fail_message = False
        self.assertEqual(1, self.task.deliver())
        self.assertEqual(0, self.task.deliver())
        self.assertIsNotNone(self.events()[0][2])
        messages = [(path, body) for path, _, body in self.jellyfin.calls if path.endswith("/Message")]
        self.assertTrue(all(path == f"Sessions/{SESSION}/Message" for path, _ in messages))

    def test_verification_budget_rotates_past_an_unplayable_request(self):
        self.task.verify_per_cycle = 1
        self.task.collect()
        self.seerr.rows = [request(1, requester=OTHER), request(2)]
        self.assertEqual(0, self.task.collect())
        self.assertEqual(1, self.task.collect())
        self.assertEqual([2], [row[0] for row in self.events()])

    def test_incomplete_snapshot_never_seeds_or_creates_events(self):
        self.seerr.rows = [request(i) for i in range(1, 8)]
        with self.assertRaises(ValueError):
            self.task.collect()
        self.assertIsNone(self.db.execute("SELECT value FROM meta WHERE key='initialized'").fetchone())

    def test_jellyfin_api_uses_current_authorization_header(self):
        api = worker.JsonApi("http://jellyfin.invalid", worker.jellyfin_authorization("private"), "Authorization")

        class Response:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        with patch.object(worker.urllib.request, "urlopen", return_value=Response()) as open_url:
            api.call("Sessions", body={"Text": "ready"})
        request_object = open_url.call_args.args[0]
        self.assertEqual('MediaBrowser Token="private"', request_object.get_header("Authorization"))
        self.assertIsNone(request_object.get_header("X-Emby-Token"))


if __name__ == "__main__":
    unittest.main()
