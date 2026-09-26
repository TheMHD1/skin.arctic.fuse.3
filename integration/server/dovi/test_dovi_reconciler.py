"""Isolated regression tests: never opens live media, databases, or queues."""
import concurrent.futures
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
# Subtitle filtering belongs to a separately tested publisher. These tests
# exercise only probe, retry admission, and the shared queue critical section.
stub = types.ModuleType("subtitle_view_filter")
stub.hidden_sources = lambda _: {}
stub.retired_sources = lambda _: {}
stub.digest = lambda _: "unused"
spec = importlib.util.spec_from_file_location(
    "dovi_reconciler_under_test", HERE / "dovi-library-view-20260922.py"
)
dovi = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = dovi
with patch.dict(sys.modules, {"subtitle_view_filter": stub}):
    spec.loader.exec_module(dovi)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.media = self.root / "sample.mkv"
        self.media.write_bytes(b"fixture-not-a-real-video")
        self.db = dovi.connect(self.root / "probe.sqlite")
        self.addCleanup(self.db.close)

    def result(self, output="|", code=0):
        return subprocess.CompletedProcess([], code, stdout=output)

    def test_blank_success_is_unknown_and_cools_down(self):
        with patch.object(dovi.subprocess, "run", return_value=self.result("")) as probe:
            self.assertIsNone(dovi.probe(self.media, self.db, 1000)[0])
            self.assertIsNone(dovi.probe(self.media, self.db, 1001)[0])
            self.assertEqual(probe.call_count, 1)
        self.assertEqual(self.db.execute("SELECT probe_ok FROM probe").fetchone()[0], 0)

    def test_timeout_is_unknown_not_sdr(self):
        with patch.object(dovi.subprocess, "run", side_effect=subprocess.TimeoutExpired("mediainfo", 90)):
            profile, description = dovi.probe(self.media, self.db, 1000)
        self.assertIsNone(profile)
        self.assertIn("124", description)

    def test_real_sdr_separator_is_valid_and_cached(self):
        with patch.object(dovi.subprocess, "run", return_value=self.result("|")) as probe:
            self.assertEqual(dovi.probe(self.media, self.db, 1000), (0, "|"))
            self.assertEqual(dovi.probe(self.media, self.db, 1400), (0, "|"))
            self.assertEqual(probe.call_count, 1)

    def test_legacy_blank_profile_zero_reprobes(self):
        self.db.execute(
            "INSERT INTO probe VALUES(?,?,?,?,?,?,?,?,?,?)",
            (str(self.media), *dovi.signature(self.media), 0, "", 900, 1, 900),
        )
        with patch.object(dovi.subprocess, "run", return_value=self.result("Dolby Vision|dvhe.07")) as probe:
            self.assertEqual(dovi.probe(self.media, self.db, 1000)[0], 7)
            self.assertEqual(probe.call_count, 1)

    def test_expired_unknown_reprobes(self):
        with patch.object(dovi.subprocess, "run", side_effect=[self.result("", 1), self.result("Dolby Vision|dvhe.07")]) as probe:
            self.assertIsNone(dovi.probe(self.media, self.db, 1000)[0])
            self.assertEqual(dovi.probe(self.media, self.db, 1300)[0], 7)
            self.assertEqual(probe.call_count, 2)

    def test_changed_file_bypasses_failed_probe_cooldown(self):
        with patch.object(dovi.subprocess, "run", side_effect=[self.result("", 1), self.result("Dolby Vision|dvhe.07")]):
            self.assertIsNone(dovi.probe(self.media, self.db, 1000)[0])
            self.media.write_bytes(b"different-size-replacement")
            self.assertEqual(dovi.probe(self.media, self.db, 1001)[0], 7)

    def test_retry_admission_honours_fingerprint_and_time(self):
        state = self.root / "retry.sqlite"
        stat = self.media.stat()
        signature = f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}"
        with sqlite3.connect(state) as db:
            db.execute("CREATE TABLE retries(path TEXT, signature TEXT, available REAL)")
            db.execute("INSERT INTO retries VALUES(?,?,?)", (str(self.media), signature, 1300))
        self.assertFalse(dovi.retry_allows(self.media, state, 1000))
        self.assertTrue(dovi.retry_allows(self.media, state, 1300))
        self.media.write_bytes(b"replacement-with-new-size")
        self.assertTrue(dovi.retry_allows(self.media, state, 1001))

    def test_invalid_retry_database_withholds_admission(self):
        state = self.root / "retry.sqlite"
        state.write_bytes(b"invalid database fixture")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(dovi.retry_allows(self.media, state, 1000))

    def test_parallel_queue_append_deduplicates_without_loss(self):
        queue = self.root / "queue.txt"
        lock = self.root / "local-queue.lock"
        paths = [self.root / f"movie-{i}.mkv" for i in range(64)] * 2
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda path: dovi.enqueue(path, queue, lock, True), paths))
        lines = queue.read_text().splitlines()
        self.assertEqual(len(lines), 64)
        self.assertEqual(set(lines), {str(path) for path in paths})
        self.assertEqual(sum(results), 64)

    def test_disabled_logical_path_seed_cannot_relabel_masters(self):
        for name in ("movies", "shows"):
            (self.root / "media" / name).mkdir(parents=True)
        args = ["test", "--seed-jellyfin", "--media-root", str(self.root / "media"),
                "--state", str(self.root / "seed.sqlite"), "--notification-state", str(self.root / "seed-notify.sqlite"), "--worker", str(self.root / "absent-worker")]
        with patch.object(sys, "argv", args), patch.object(dovi, "seed_from_jellyfin") as seed:
            with self.assertRaisesRegex(SystemExit, "unsafe.*disabled"):
                dovi.main()
            seed.assert_not_called()


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.media = self.root / "media"
        for name in ("movies", "shows"):
            (self.media / name).mkdir(parents=True)
        self.state = self.root / "state.sqlite"
        self.view = self.root / "view"

    def run_main(self, apply=True, notify_only=False, extra=()):
        args = ["test", "--notify-jellyfin", "--media-root", str(self.media),
                "--compatibility-root", str(self.root / "compat"), "--view-root", str(self.view),
                "--state", str(self.root / "probe.sqlite"), "--notification-state", str(self.state), "--queue", str(self.root / "queue"),
                "--publication-lock", str(self.root / "publication.lock"), "--title-locks", str(self.root / "title-locks"),
                "--queue-lock", str(self.root / "queue.lock"),
                "--run-lock", str(self.root / "run.lock"),
                "--retry-state", str(self.root / "retry.sqlite"), "--worker", str(self.root / "worker")]
        if apply:
            args.append("--apply")
        if notify_only:
            args.append("--notify-only")
        args.extend(extra)
        with patch.object(sys, "argv", args), patch.object(dovi, "worker_token", return_value="fixture"), patch.object(dovi, "verify_publication", return_value=True), contextlib.redirect_stdout(io.StringIO()):
            dovi.main()

    def pending(self):
        with sqlite3.connect(self.state) as db:
            return {row[0] for row in db.execute("SELECT folder FROM notification_outbox")}

    def test_scoped_import_ignores_unrelated_files_and_preserves_orphan(self):
        title = self.media / 'shows' / 'Office'
        title.mkdir()
        touched = title / 'one.mkv'
        touched.write_bytes(b'fixture')
        (title / 'other.mkv').write_bytes(b'fixture')
        (title / 'other.subengine.json').write_text('{}')
        orphan = self.view / 'shows' / 'Office' / 'old.mkv'
        orphan.parent.mkdir(parents=True)
        orphan.write_bytes(b'keep')
        def probe(path, *_):
            self.assertEqual(path, touched)
            return 0, '|'
        with patch.object(dovi, 'probe', side_effect=probe), patch.object(dovi, 'notify_jellyfin', return_value=1), patch.object(dovi, 'hidden_sources', side_effect=AssertionError('unrelated marker read')):
            self.run_main(extra=['--scope-title', str(title), '--scope-file', str(touched)])
        self.assertTrue(orphan.exists())
        self.assertTrue((self.view / 'shows' / 'Office' / 'one.mkv').is_file())

    def test_notify_only_is_independent_of_full_scan_lock(self):
        import fcntl
        with (self.root / 'run.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(dovi, 'probe', side_effect=AssertionError('publisher probed media')):
                self.run_main(notify_only=True)
        self.assertTrue(self.state.exists())

    def test_failed_post_replayed_when_next_run_has_unchanged_view(self):
        source = self.media / "movies" / "fixture-title" / "a.mkv"
        source.parent.mkdir()
        source.write_bytes(b"fixture")
        with patch.object(dovi.time, "time", return_value=1000), patch.object(dovi, "probe", return_value=(0, "|")), patch.object(dovi, "notify_jellyfin", return_value=0) as send:
            self.run_main()
            self.assertEqual(send.call_count, 1)
        self.assertEqual(self.pending(), {str(source.parent)})
        with patch.object(dovi.time, "time", return_value=1060), patch.object(dovi, "probe", return_value=(0, "|")), patch.object(dovi, "notify_jellyfin", return_value=1) as send, patch.object(dovi, "atomic_link", wraps=dovi.atomic_link) as link:
            self.run_main()
            self.assertEqual(send.call_count, 1)
            self.assertEqual(link.call_count, 1)
        self.assertEqual(self.pending(), set())

    def test_new_video_notified_before_later_slow_probe(self):
        title = self.media / "movies" / "fixture-title"
        title.mkdir()
        for name in ("a.mkv", "z.mkv"):
            (title / name).write_bytes(b"fixture")
        events = []
        def probe(path, *_):
            events.append(path.name)
            if path.name == "z.mkv":
                self.assertIn("sent", events)
            return 0, "|"
        def send(*_):
            self.assertTrue((self.view / "movies" / "fixture-title" / "a.mkv").is_file())
            events.append("sent")
            return 1
        with patch.object(dovi, "probe", side_effect=probe), patch.object(dovi, "notify_jellyfin", side_effect=send):
            self.run_main()
        self.assertEqual(events[:3], ["a.mkv", "sent", "z.mkv"])

    def test_crash_before_link_leaves_durable_intent(self):
        source = self.media / "movies" / "fixture-title" / "a.mkv"
        source.parent.mkdir()
        source.write_bytes(b"fixture")
        db = dovi.connect(self.state)
        self.addCleanup(db.close)
        outbox = dovi.NotificationOutbox(db, "fixture", "fixture", True, self.media)
        with patch.object(dovi, "atomic_link", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                outbox.link(source, self.view / "a.mkv", str(source.parent), True)
        self.assertEqual(self.pending(), {str(source.parent)})
        self.assertFalse((self.view / "a.mkv").exists())

    def test_removal_intent_is_committed_before_unlink(self):
        view = self.root / "old.mkv"
        view.write_bytes(b"fixture")
        folder = self.media / "shows" / "fixture-title" / "Season 01"
        db = dovi.connect(self.state)
        self.addCleanup(db.close)
        outbox = dovi.NotificationOutbox(db, "fixture", "fixture", True, self.media)
        def interrupted(*_):
            self.assertEqual(self.pending(), {str(self.media / "shows" / "fixture-title")})
            raise KeyboardInterrupt
        with patch.object(dovi, "unlink", side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            outbox.remove(view, str(folder), True)
        self.assertTrue(view.exists())

    def test_crash_after_link_before_ack_replays_durable_intent(self):
        source = self.media / "movies" / "fixture-title" / "a.mkv"
        source.parent.mkdir()
        source.write_bytes(b"fixture")
        with patch.object(dovi, "probe", return_value=(0, "|")), patch.object(dovi, "notify_jellyfin", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_main()
        self.assertTrue((self.view / "movies" / "fixture-title" / "a.mkv").exists())
        self.assertEqual(self.pending(), {str(source.parent)})
        with patch.object(dovi, "probe", return_value=(0, "|")), patch.object(dovi, "notify_jellyfin", return_value=1) as send:
            self.run_main()
            self.assertEqual(send.call_count, 1)
        self.assertEqual(self.pending(), set())

    def test_dry_run_does_not_link_or_send_or_change_outbox(self):
        source = self.media / "movies" / "a.mkv"
        source.write_bytes(b"fixture")
        with dovi.connect(self.state) as db:
            db.execute("INSERT INTO notification_outbox(folder) VALUES(?)", ("fixture-pending",))
        with patch.object(dovi, "probe", return_value=(0, "|")), patch.object(dovi, "notify_jellyfin") as send:
            self.run_main(apply=False)
            send.assert_not_called()
        self.assertEqual(self.pending(), {"fixture-pending"})
        self.assertFalse(self.view.exists())
        self.assertFalse((self.root / "queue").exists())

    def test_root_and_outside_scopes_link_without_staging_global_notification(self):
        source = self.media / "movies" / "root-level.mkv"
        source.write_bytes(b"fixture")
        with patch.object(dovi, "probe", return_value=(0, "|")), \
             patch.object(dovi, "notify_jellyfin") as send, \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            self.run_main()
            send.assert_not_called()
        self.assertTrue((self.view / "movies" / "root-level.mkv").is_file())
        self.assertEqual(self.pending(), set())
        self.assertIn("publication scope skipped", errors.getvalue())

        with dovi.connect(self.state) as db, contextlib.redirect_stderr(io.StringIO()):
            outbox = dovi.NotificationOutbox(db, "fixture", "fixture", True, self.media)
            outbox.stage(str(self.media / "movies" / ".." / "shows" / "fixture-title"))
            outbox.stage(str(self.root / "outside" / "fixture-title"))
        self.assertEqual(self.pending(), set())

    def test_persisted_invalid_scopes_are_discarded_without_notification(self):
        invalid = {
            str(self.media / "movies"),
            str(self.media / "shows" / ".." / "movies" / "fixture-title"),
            str(self.root / "outside" / "fixture-title"),
        }
        with dovi.connect(self.state) as db:
            db.executemany("INSERT INTO notification_outbox(folder) VALUES(?)", ((folder,) for folder in invalid))
            db.execute("INSERT INTO notification_outbox(folder) VALUES(NULL)")
        with patch.object(dovi, "notify_jellyfin") as send, \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            self.run_main(notify_only=True)
            send.assert_not_called()
        self.assertEqual(self.pending(), set())
        self.assertEqual(errors.getvalue().count("invalid Jellyfin publication intent discarded"), 4)

    def test_p7_and_unknown_are_not_published(self):
        for name in ("p7.mkv", "unknown.mkv"):
            (self.media / "movies" / name).write_bytes(b"fixture")
        with patch.object(dovi, "probe", side_effect=lambda p, *_: (7, "P7") if p.name == "p7.mkv" else (None, "unknown")), patch.object(dovi, "notify_jellyfin") as send:
            self.run_main()
            send.assert_not_called()
        self.assertFalse((self.view / "movies" / "p7.mkv").exists())
        self.assertFalse((self.view / "movies" / "unknown.mkv").exists())
        self.assertEqual(self.pending(), set())

    def test_cooldown_persists_across_runs_and_coalesces_seasons(self):
        folder = self.media / "shows" / "fixture-title"
        with dovi.connect(self.state) as db, patch.object(dovi, "notify_jellyfin", return_value=1) as send:
            first = dovi.NotificationOutbox(db, "fixture", "fixture", True, self.media)
            with patch.object(dovi.time, "time", return_value=1000):
                first.stage(str(folder / "Season 1"))
                first.flush(force=True)
            self.assertEqual(send.call_count, 1)
            with patch.object(dovi.time, "time", return_value=1001):
                first.stage(str(folder / "Season 2"))
                first.flush(force=True)
            second = dovi.NotificationOutbox(db, "fixture", "fixture", True, self.media)
            with patch.object(dovi.time, "time", return_value=1059):
                second.flush(force=True)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(self.pending(), {str(folder)})
            with patch.object(dovi.time, "time", return_value=1060):
                second.flush(force=True)
            self.assertEqual(send.call_count, 2)
            self.assertEqual(self.pending(), set())

    def test_notify_only_does_not_walk_or_probe(self):
        with dovi.connect(self.state) as db:
            db.execute("INSERT INTO notification_outbox(folder) VALUES(?)", (str(self.media / "shows" / "fixture"),))
        with patch.object(dovi.os, "walk", side_effect=AssertionError("must not walk media")), patch.object(dovi, "probe", side_effect=AssertionError("must not probe")), patch.object(dovi, "notify_jellyfin", return_value=1) as send:
            self.run_main(notify_only=True)
            self.assertEqual(send.call_count, 1)
        self.assertEqual(self.pending(), set())

    def test_busy_process_lock_skips_without_database_mutation(self):
        with (self.root / "run.lock").open("a+") as lock:
            dovi.fcntl.flock(lock, dovi.fcntl.LOCK_EX | dovi.fcntl.LOCK_NB)
            with patch.object(dovi, "connect") as connect:
                self.run_main()
                connect.assert_not_called()


class TargetedRefreshTests(unittest.TestCase):
    def response(self, value, status=200):
        response = io.BytesIO(json.dumps(value).encode())
        response.status = status
        return response

    def test_bridge_accepts_actual_jellyfin_pascal_case_and_optional_camel_case(self):
        folder = "/fixture/shows/title"
        for result in ({"ItemId": "native-id", "Queued": True, "Created": True},
                       {"itemId": "native-id", "queued": True, "created": True}):
            with self.subTest(result=result):
                targets = {}
                catalogs = {"virtual-folders": [{"ItemId": "library", "Locations": ["/fixture/shows"]}]}
                with patch.object(dovi, "refresh_target", return_value=None), patch.object(
                        dovi.urllib.request, "urlopen", return_value=self.response(result, 202)) as post:
                    self.assertEqual(dovi.notify_jellyfin("http://fixture", "fixture", {folder}, targets,
                        catalogs, {}, True, {folder: {"Tvdb": "12345"}}), 1)
                self.assertEqual(targets[folder], "native-id")
                self.assertTrue(post.call_args.args[0].full_url.endswith("/Habibi/LibraryExperience/DiscoverTitle"))

    def test_lookup_requires_exact_series_path_and_unique_identity(self):
        folder = "/fixture/shows/title"
        wrong = {"Id": "wrong", "Type": "Series", "Path": "/other/shows/title", "Name": "title"}
        right = {"Id": "right", "Type": "Series", "Path": folder}
        with patch.object(dovi.urllib.request, "urlopen", return_value=self.response({"Items": [wrong, right]})):
            self.assertEqual(dovi.refresh_target("http://fixture", "fixture", folder), "right")
        with patch.object(dovi.urllib.request, "urlopen", return_value=self.response({"Items": [right, dict(right, Id="duplicate")]})):
            self.assertIsNone(dovi.refresh_target("http://fixture", "fixture", folder))

    def test_movie_lookup_requires_exact_containing_folder(self):
        folder = "/fixture/movies/title"
        movie = {"Id": "movie", "Type": "Movie", "Path": folder + "/video.mkv"}
        with patch.object(dovi.urllib.request, "urlopen", return_value=self.response({"Items": [movie]})):
            self.assertEqual(dovi.refresh_target("http://fixture", "fixture", folder), "movie")

    def test_localized_name_resolves_from_exact_owning_library_catalog(self):
        folder = "/fixture/shows/Title (2017) [source-id]"
        localized = {"Id": "localized", "Type": "Series", "Name": "Unrelated localized display name", "Path": folder}
        libraries = [{"ItemId": "shows", "Locations": ["/fixture/shows"]},
                     {"ItemId": "iptv", "Locations": ["/fixture/live"]}]
        cache = {}
        responses = [self.response({"Items": []}), self.response(libraries),
                     self.response({"Items": [localized]}), self.response({"Items": []})]
        with patch.object(dovi.urllib.request, "urlopen", side_effect=responses) as get:
            self.assertEqual(dovi.refresh_target("http://fixture", "fixture", folder, cache), "localized")
            self.assertEqual(dovi.refresh_target("http://fixture", "fixture", folder, cache), "localized")
        urls = [call.args[0].full_url for call in get.call_args_list]
        self.assertEqual(sum("VirtualFolders" in url for url in urls), 1)
        catalog_urls = [url for url in urls if "ParentId=" in url]
        self.assertEqual(len(catalog_urls), 1)
        self.assertIn("ParentId=shows", catalog_urls[0])
        self.assertNotIn("iptv", catalog_urls[0])

    def test_owning_catalog_is_paginated_before_exact_path_selection(self):
        folder = "/fixture/movies/Title"
        movie = {"Id": "movie", "Type": "Movie", "Path": folder + "/video.mkv"}
        page = [{"Id": str(i), "Type": "Movie", "Path": "/other/" + str(i) + "/video.mkv"} for i in range(200)]
        responses = [self.response({"Items": []}),
                     self.response([{"ItemId": "movies", "Locations": ["/fixture/movies"]}]),
                     self.response({"Items": page}), self.response({"Items": [movie]})]
        with patch.object(dovi.urllib.request, "urlopen", side_effect=responses) as get:
            self.assertEqual(dovi.refresh_target("http://fixture", "fixture", folder, {}), "movie")
        self.assertIn("StartIndex=200", get.call_args.args[0].full_url)

    def test_target_post_preserves_metadata_and_images_and_caches_lookup(self):
        folder = "/fixture/shows/title"
        cache = {}
        def response(*_args, **_kwargs):
            return self.response({}, status=204)
        with patch.object(dovi, "refresh_target", return_value="fixture-id") as lookup, patch.object(dovi.urllib.request, "urlopen", side_effect=response) as post:
            self.assertEqual(dovi.notify_jellyfin("http://fixture", "fixture", {folder}, cache), 1)
            self.assertEqual(dovi.notify_jellyfin("http://fixture", "fixture", {folder}, cache), 1)
            self.assertEqual(lookup.call_count, 1)
        request = post.call_args.args[0]
        self.assertIn("/Items/fixture-id/Refresh?", request.full_url)
        self.assertIn("metadataRefreshMode=Default", request.full_url)
        self.assertIn("imageRefreshMode=None", request.full_url)
        self.assertIn("replaceAllMetadata=false", request.full_url)
        self.assertIn("replaceAllImages=false", request.full_url)
        self.assertNotIn("recursive", request.full_url.lower())
        self.assertEqual(request.data, b"")

    def test_new_title_never_falls_back_to_media_update(self):
        folder = "/fixture/shows/new-title"
        with patch.object(dovi, "refresh_target", return_value=None), patch.object(dovi.urllib.request, "urlopen", return_value=self.response({}, status=204)) as post:
            self.assertEqual(dovi.notify_jellyfin("http://fixture", "fixture", {folder}), 0)
            post.assert_not_called()

    def test_non_2xx_response_not_acknowledged(self):
        with patch.object(dovi, "refresh_target", return_value="fixture"), patch.object(dovi.urllib.request, "urlopen", return_value=self.response({}, status=202)):
            self.assertEqual(dovi.notify_jellyfin("http://fixture", "fixture", {"/fixture"}), 1)
        with patch.object(dovi, "refresh_target", return_value="fixture"), patch.object(dovi.urllib.request, "urlopen", return_value=self.response({}, status=300)):
            self.assertEqual(dovi.notify_jellyfin("http://fixture", "fixture", {"/fixture"}), 0)


class DurablePublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.title = self.root / 'shows' / 'Office'
        self.title.mkdir(parents=True)
        self.video = self.title / 'episode.mkv'
        self.video.write_bytes(b'fixture')
        self.db = dovi.connect(self.root / 'publication.sqlite')
        self.addCleanup(self.db.close)
        self.outbox = dovi.NotificationOutbox(self.db, 'http://fixture', 'fixture', True, self.root)

    def test_existing_link_scoped_import_stages_without_mutation(self):
        view = self.root / 'view.mkv'
        view.hardlink_to(self.video)
        self.assertEqual(self.outbox.link(self.video, view, str(self.title), True, self.video, dovi.signature(self.video), True), 'unchanged')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM notification_outbox').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT path FROM notification_expected').fetchone()[0], str(self.video))

    def test_cas_ack_preserves_new_event_and_expected(self):
        self.outbox.stage(str(self.title), 'first', self.video)
        revision = self.db.execute('SELECT revision FROM notification_outbox').fetchone()[0]
        self.outbox.stage(str(self.title), 'changed', self.video)
        self.outbox.acknowledge(str(self.title), revision)
        self.assertEqual(self.db.execute('SELECT revision FROM notification_outbox').fetchone()[0], revision + 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM notification_expected').fetchone()[0], 1)

    def test_dead_fingerprint_dedup_and_changed_reactivation(self):
        self.outbox.stage(str(self.title), 'first', self.video)
        row = self.db.execute('SELECT revision,first_seen FROM notification_outbox').fetchone()
        self.outbox.deadletter(str(self.title), row[0], 8, row[1], 'down')
        self.outbox.stage(str(self.title), 'first', self.video)
        self.assertEqual(self.db.execute('SELECT dead,attempts FROM notification_outbox').fetchone(), (1, 8))
        self.outbox.stage(str(self.title), 'changed', self.video)
        self.assertEqual(self.db.execute('SELECT dead,attempts FROM notification_outbox').fetchone(), (0, 0))

    def test_queued_not_acknowledged_and_no_repost_during_verification(self):
        self.outbox.stage(str(self.title), 'first', self.video)
        self.outbox.targets[str(self.title)] = 'series-id'
        now = self.db.execute('SELECT first_seen FROM notification_outbox').fetchone()[0]
        with patch.object(dovi, 'notify_jellyfin', return_value=1) as post, patch.object(dovi, 'verify_publication', return_value=False), patch.object(dovi.time, 'time', return_value=now + 100):
            self.outbox.flush(True)
            self.assertEqual(self.db.execute('SELECT phase FROM notification_outbox').fetchone()[0], 'await_index')
            self.db.execute('UPDATE notification_outbox SET next_attempt=0')
            self.db.commit()
            self.outbox.flush(True)
            self.assertEqual(post.call_count, 1)
        with patch.object(dovi, 'verify_publication', return_value=True), patch.object(dovi.time, 'time', return_value=now + 1000):
            self.db.execute('UPDATE notification_outbox SET next_attempt=0')
            self.db.commit()
            self.outbox.failed.clear()
            self.outbox.flush(True)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM notification_outbox').fetchone()[0], 0)

    def test_item_path_without_local_media_source_is_not_proof(self):
        with patch.object(dovi.urllib.request, 'urlopen', return_value=contextlib.closing(io.BytesIO(json.dumps({'Items': [{'Path': str(self.video), 'MediaSources': []}]}).encode()))):
            self.assertFalse(dovi.verify_publication('http://fixture', 'fixture', 'series', {str(self.video)}))

    def test_shared_outage_circuit_stops_batch_and_dead_does_not_send(self):
        self.outbox.stage(str(self.title), 'first', self.video)
        other = self.root / 'shows' / 'Other'
        self.outbox.stage(str(other), 'second')
        def failure(url, token, folders, targets, catalogs, failures, *_):
            failures[next(iter(folders))] = 'down'
            return 0
        with patch.object(dovi, 'notify_jellyfin', side_effect=failure) as send:
            self.outbox.flush(True)
            self.assertEqual(send.call_count, 1)
        self.outbox.failed.clear()
        with patch.object(dovi, 'notify_jellyfin') as send:
            self.outbox.flush(True)
            send.assert_not_called()
        self.db.execute('DELETE FROM notification_meta')
        self.db.execute('UPDATE notification_outbox SET attempts=8,next_attempt=0')
        self.db.commit()
        with patch.object(dovi, 'notify_jellyfin') as send:
            self.outbox.flush(True)
            send.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM notification_deadletters').fetchone()[0], 2)

    def test_upgrade_prunes_only_absent_old_path_and_requires_new_video(self):
        self.outbox.stage(str(self.title), 'first', self.video)
        replacement = self.title / 'upgraded.mkv'
        self.video.rename(replacement)
        self.outbox.stage(str(self.title), 'upgrade', replacement)
        self.db.execute("UPDATE notification_outbox SET phase='await_index',target_id='series'")
        self.db.commit()
        def visible(url, token, target, expected):
            self.assertEqual(expected, {str(replacement)})
            return True
        with patch.object(dovi, 'verify_publication', side_effect=visible), patch.object(dovi, 'notify_jellyfin') as post:
            self.outbox.flush(True)
            post.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM notification_outbox').fetchone()[0], 0)

    def test_missing_title_root_fails_closed_without_ack_or_poll(self):
        self.outbox.stage(str(self.title), 'first', self.video)
        self.db.execute("UPDATE notification_outbox SET phase='await_index',target_id='series'")
        self.db.commit()
        self.title.rename(self.root / 'temporarily-unmounted')
        with patch.object(dovi, 'verify_publication') as verify, patch.object(dovi, 'notify_jellyfin') as post:
            self.outbox.flush(True)
            verify.assert_not_called()
            post.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM notification_expected').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT attempts FROM notification_outbox').fetchone()[0], 0)

    def test_paused_writer_blocks_ready_send_without_spending_attempt(self):
        self.outbox.title_locks = self.root / 'title-locks'
        with self.outbox.mutation_lock(str(self.title), True):
            self.outbox.stage(str(self.title), 'paused', self.video)
            with patch.object(dovi, 'notify_jellyfin') as post, patch.object(dovi, 'verify_publication') as verify:
                self.outbox.flush(True)
                post.assert_not_called()
                verify.assert_not_called()
        self.assertEqual(self.db.execute('SELECT attempts FROM notification_outbox').fetchone()[0], 0)
        self.assertEqual(self.outbox.attempted, 0)
        self.outbox.targets[str(self.title)] = 'series'
        def send(*_):
            # HTTP executes only after the commit-section gate released its lock.
            self.assertTrue(self.outbox.commit_section_clear(str(self.title)))
            return 1
        with patch.object(dovi, 'notify_jellyfin', side_effect=send), patch.object(dovi, 'verify_publication', return_value=True):
            self.outbox.flush(True)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM notification_outbox').fetchone()[0], 0)

    def test_paused_writer_blocks_await_index_ack(self):
        self.outbox.title_locks = self.root / 'title-locks'
        self.outbox.stage(str(self.title), 'paused', self.video)
        self.db.execute("UPDATE notification_outbox SET phase='await_index',target_id='series'")
        self.db.commit()
        with self.outbox.mutation_lock(str(self.title), True):
            with patch.object(dovi, 'notify_jellyfin') as post, patch.object(dovi, 'verify_publication', return_value=True) as verify:
                self.outbox.flush(True)
                post.assert_not_called()
                verify.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM notification_outbox').fetchone()[0], 1)
        self.assertEqual(self.outbox.attempted, 0)
        with patch.object(dovi, 'verify_publication', return_value=True):
            self.outbox.flush(True)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM notification_outbox').fetchone()[0], 0)

    def test_failed_link_intent_cannot_send_then_repair_preserves_budget(self):
        view = self.root / 'view.mkv'
        view.write_bytes(b'stale old view')
        with patch.object(dovi, 'atomic_link', side_effect=OSError('simulated commit failure')):
            with self.assertRaises(OSError):
                self.outbox.link(self.video, view, str(self.title), True, self.video, dovi.signature(self.video))
        self.assertEqual(self.db.execute('SELECT phase FROM notification_outbox').fetchone()[0], 'staging')
        self.db.execute('UPDATE notification_outbox SET attempts=2')
        self.db.commit()
        original = self.db.execute('SELECT revision,first_seen FROM notification_outbox').fetchone()
        with patch.object(dovi, 'notify_jellyfin') as post, patch.object(dovi, 'verify_publication') as verify:
            self.outbox.flush(True)
            post.assert_not_called()
            verify.assert_not_called()
        self.outbox.link(self.video, view, str(self.title), True, self.video, dovi.signature(self.video))
        self.assertEqual(self.db.execute('SELECT revision,first_seen FROM notification_outbox').fetchone(), original)
        self.assertEqual(self.db.execute('SELECT phase,attempts FROM notification_outbox').fetchone(), ('ready', 2))

    def test_crash_after_link_recovers_even_unchanged_full_backstop_link(self):
        view = self.root / 'view.mkv'
        with patch.object(self.outbox, 'complete_mutation', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.outbox.link(self.video, view, str(self.title), True, self.video, dovi.signature(self.video))
        self.assertTrue(dovi.same_inode(self.video, view))
        self.assertEqual(self.db.execute('SELECT phase FROM notification_outbox').fetchone()[0], 'staging')
        self.assertEqual(self.outbox.link(self.video, view, str(self.title), True, self.video, dovi.signature(self.video)), 'unchanged')
        self.assertEqual(self.db.execute('SELECT phase FROM notification_outbox').fetchone()[0], 'ready')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM notification_mutations').fetchone()[0], 0)

    def test_one_title_never_acknowledges_another_uncommitted_file(self):
        self.outbox.stage(str(self.title), 'existing-ready', self.video)
        first = self.root / 'view-one.mkv'
        second = self.root / 'view-two.mkv'
        marker = self.outbox.stage(str(self.title), 'uncommitted-one', self.video, first)
        later = self.outbox.stage(str(self.title), 'committed-two', self.video, second)
        self.outbox.complete_mutation(later)
        with patch.object(dovi, 'notify_jellyfin') as post:
            self.outbox.flush(True)
            post.assert_not_called()
        self.assertEqual(self.db.execute('SELECT phase FROM notification_outbox').fetchone()[0], 'staging')
        newer = self.outbox.stage(str(self.title), 'replacement-one', self.video, first)
        self.outbox.complete_mutation(marker)
        self.assertEqual(self.db.execute('SELECT fingerprint FROM notification_mutations').fetchone()[0], 'replacement-one')
        self.outbox.complete_mutation(newer)
        self.assertEqual(self.db.execute('SELECT phase FROM notification_outbox').fetchone()[0], 'ready')

    def test_crash_after_unlink_can_finalize_proven_absence(self):
        view = self.root / 'old-view.mkv'
        view.write_bytes(b'old view')
        with patch.object(self.outbox, 'complete_mutation', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.outbox.remove(view, str(self.title), True)
        self.assertFalse(view.exists())
        self.assertEqual(self.db.execute('SELECT phase FROM notification_outbox').fetchone()[0], 'staging')
        with patch.object(dovi, 'notify_jellyfin', return_value=1):
            self.outbox.flush(True)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM notification_outbox').fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
