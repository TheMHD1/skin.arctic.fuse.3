import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location("artwork", Path(__file__).with_name("artwork-publication.py"))
artwork = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artwork)


class ArtworkPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.media = Path(self.tmp.name) / "media"
        self.root = self.media / "movies" / "Title"; self.root.mkdir(parents=True)
        self.video = self.root / "Title.mkv"; self.video.write_bytes(b"fixture")
        self.db = artwork.connect(Path(self.tmp.name) / "state.sqlite"); self.addCleanup(self.db.close)
        self.item = "11111111-1111-1111-1111-111111111111"

    def test_rejects_noncanonical_root_and_bad_id(self):
        with self.assertRaises(ValueError): artwork.title_root("/tmp/no", self.media)
        with self.assertRaises(ValueError): artwork.enqueue(self.db, "not-an-id", self.root)

    def test_existing_primary_completes_without_refresh(self):
        artwork.enqueue(self.db, self.item, self.root, now=1)
        api = Mock(); api.request.return_value = {"Items": [{"Id": self.item, "Path": str(self.video), "ImageTags": {"Primary": "already-there"}}]}
        self.assertEqual(artwork.work(self.db, api, now=2), {"completed": 1, "deferred": 0, "dead": 0})
        self.assertEqual(api.request.call_count, 1)

    def test_missing_primary_refreshes_only_exact_item_then_waits(self):
        artwork.enqueue(self.db, self.item, self.root, now=1)
        api = Mock(); api.request.side_effect = [{"Items": [{"Id": self.item, "Path": str(self.video), "ImageTags": {}}]}, {}]
        self.assertEqual(artwork.work(self.db, api, now=2)["deferred"], 1)
        refresh = api.request.call_args_list[1].args[0]
        self.assertIn("/Items/" + artwork.canonical_id(self.item) + "/Refresh?", refresh)
        self.assertIn("ReplaceAllImages=false", refresh)
        self.assertIn("ImageRefreshMode=Default", refresh)
        self.assertEqual(self.db.execute("SELECT attempts,state,error FROM jobs").fetchone(), (0, "verifying", "image-wait"))

    def test_native_32_character_ids_and_hyphenated_ids_are_same_job(self):
        artwork.enqueue(self.db, self.item, self.root, now=1)
        artwork.enqueue(self.db, self.item.replace("-", "").upper(), self.root, now=2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)

    def test_accepted_refresh_is_polled_without_reposting(self):
        artwork.enqueue(self.db, self.item, self.root, now=1)
        missing = {"Items": [{"Id": self.item, "Path": str(self.video), "ImageTags": {}}]}
        api = Mock(); api.request.side_effect = [missing, {}, missing, missing]
        artwork.work(self.db, api, now=2)
        artwork.work(self.db, api, now=32)
        artwork.work(self.db, api, now=62)
        self.assertEqual(sum(len(call.args) > 1 and call.args[1] == "POST" for call in api.request.call_args_list), 1)

    def test_missing_image_after_verification_window_spends_failure_budget(self):
        artwork.enqueue(self.db, self.item, self.root, now=1)
        missing = {"Items": [{"Id": self.item, "Path": str(self.video), "ImageTags": {}}]}
        api = Mock(); api.request.side_effect = [missing, {}, missing]
        artwork.work(self.db, api, now=2)
        artwork.work(self.db, api, now=2 + artwork.VERIFY_WINDOW)
        self.assertEqual(self.db.execute("SELECT attempts,state FROM jobs").fetchone(), (1, "waiting"))

    def test_expired_job_is_not_refreshed_or_automatically_resurrected(self):
        artwork.enqueue(self.db, self.item, self.root, now=1)
        api = Mock()
        self.assertEqual(artwork.work(self.db, api, now=artwork.MAX_AGE + 2)["dead"], 1)
        api.request.assert_not_called()
        artwork.enqueue(self.db, self.item, self.root, now=artwork.MAX_AGE + 3)
        self.assertEqual(self.db.execute("SELECT state,first_seen FROM jobs").fetchone(), ("dead", 1))

    def test_path_mismatch_is_terminal_and_no_refresh(self):
        artwork.enqueue(self.db, self.item, self.root, now=1)
        api = Mock(); api.request.return_value = {"Items": [{"Id": self.item, "Path": "/other/movie.mkv"}]}
        self.assertEqual(artwork.work(self.db, api, now=2)["dead"], 1)
        self.assertEqual(api.request.call_count, 1)

    def test_409_waits_without_spending_budget(self):
        artwork.enqueue(self.db, self.item, self.root, now=1)
        row = self.db.execute("SELECT item_id,title_root,revision,state,attempts,first_seen,next_attempt,error FROM jobs").fetchone()
        error = __import__('urllib.error').error.HTTPError("http://fixture", 409, "busy", {}, None)
        self.addCleanup(error.close)
        artwork.defer(self.db, row, error, now=2)
        self.assertEqual(self.db.execute("SELECT attempts,state,error FROM jobs").fetchone(), (0, "waiting", "not-ready"))

    def test_worker_lock_excludes_a_second_worker_and_releases(self):
        state = Path(self.tmp.name) / "state.sqlite"
        with artwork.single_worker(state) as first:
            self.assertTrue(first)
            with artwork.single_worker(state) as second:
                self.assertFalse(second)
        with artwork.single_worker(state) as later:
            self.assertTrue(later)

    def test_busy_get_while_verifying_does_not_reset_refresh_phase(self):
        artwork.enqueue(self.db, self.item, self.root, now=1)
        missing = {"Items": [{"Id": self.item, "Path": str(self.video), "ImageTags": {}}]}
        error = __import__('urllib.error').error.HTTPError("http://fixture", 409, "busy", {}, None)
        self.addCleanup(error.close)
        api = Mock(); api.request.side_effect = [missing, {}, error, missing]
        artwork.work(self.db, api, now=2)
        artwork.work(self.db, api, now=32)
        artwork.work(self.db, api, now=62)
        self.assertEqual(sum(len(call.args) > 1 and call.args[1] == "POST" for call in api.request.call_args_list), 1)
        self.assertEqual(self.db.execute("SELECT attempts,state FROM jobs").fetchone(), (0, "verifying"))


if __name__ == "__main__":
    unittest.main()
