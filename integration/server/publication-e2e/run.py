#!/usr/bin/env python3
"""Opt-in, disposable real-Jellyfin publication acceptance. Never uses production state."""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
SERVER = HERE.parent
IMAGE = "jellyfin-custom:12.1-onepace-20260918"


def command(*args, timeout=120):
    result = subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout)
    return result.stdout.strip()


def wait_for(function, description, timeout=90):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            value = function()
            if value:
                return value
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(1)
    raise AssertionError("Timed out: " + description)


class Fixture:
    def __init__(self, args):
        self.args = args
        self.root = Path(tempfile.mkdtemp(prefix="publication-e2e-"))
        self.name = "publication-e2e-" + secrets.token_hex(6)
        self.network = self.name + "-net"
        self.token = None
        self.url = None
        self.container_started = False
        self.network_created = False
        self.proxy = None
        self.results = []
        self.source_files = [SERVER / name for name in (
            "dovi/dovi-library-view-20260922.py", "dovi/subtitle_view_filter.py",
            "subtitle-publication/subtitle-raw-arrival.py", "subtitle-publication/subtitle-publication-queue.py",
            "subtitle-publication/subtitle-jellyfin-sync.py", "subtitle-publication/subtitle-view-filter.py")]
        self.source_hashes = {str(path.relative_to(SERVER)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in self.source_files}
        for path in ("config", "cache", "media/movies", "media/shows", "view/movies", "view/shows", "compat", "locks", "tools", "subtitles"):
            (self.root / path).mkdir(parents=True)

    def api(self, path, data=None, method=None, raw=False):
        headers = {"Content-Type": "application/json", "Authorization":
                   'MediaBrowser Client="publication-e2e", Device="fixture", DeviceId="fixture", Version="1"' +
                   (', Token="' + self.token + '"' if self.token else "")}
        body = None if data is None else json.dumps(data).encode()
        request = urllib.request.Request(self.url + "/" + path, data=body, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=15) as response:
            content = response.read()
        def native_keys(value):
            if isinstance(value, dict):
                return {key[:1].upper() + key[1:]: native_keys(child) for key, child in value.items()}
            if isinstance(value, list):
                return [native_keys(child) for child in value]
            return value
        return content.decode("utf-8-sig") if raw else native_keys(json.loads(content)) if content else None

    def scan_state(self):
        tasks = self.api("ScheduledTasks")
        task = next(t for t in tasks if t["Key"] == "RefreshLibrary")
        return task["State"], task.get("LastExecutionResult")

    def assert_no_scan(self):
        state, result = self.scan_state()
        assert state == "Idle", "A global scan ran during scoped publication"
        assert result == self.baseline_scan, "Global scan execution changed during scoped publication"

    def check(self, name):
        self.assert_no_scan()
        self.results.append(name)
        print("PASS " + name, flush=True)

    def start(self):
        dll = SERVER / "library-experience-plugin/bin/Release/net10.0/Jellyfin.Plugin.LibraryExperience.dll"
        meta = SERVER / "library-experience-plugin/meta.json"
        assert dll.is_file(), "Build the pinned plugin first"
        assert json.loads(meta.read_text())["version"] == "1.2.0.0"
        self.image_id = command("docker", "image", "inspect", self.args.image, "--format", "{{.Id}}")
        self.plugin_hash = hashlib.sha256(dll.read_bytes()).hexdigest()
        plugin = self.root / "config/data/plugins/LibraryExperience_1.2.0.0"
        plugin.mkdir(parents=True)
        shutil.copy2(dll, plugin / dll.name)
        shutil.copy2(meta, plugin / meta.name)
        command("docker", "network", "create", "--internal", self.network)
        self.network_created = True
        command("docker", "run", "-d", "--name", self.name, "--network", self.network,
                "-e", "PUID=" + str(os.getuid()), "-e", "PGID=" + str(os.getgid()),
                "-v", str(self.root) + ":" + str(self.root),
                "-v", str(self.root / "config") + ":/config", "-v", str(self.root / "cache") + ":/cache",
                "-v", str(self.root / "view/movies") + ":" + str(self.root / "media/movies"),
                "-v", str(self.root / "view/shows") + ":" + str(self.root / "media/shows"), self.args.image)
        self.container_started = True
        # Docker intentionally suppresses published ports on internal networks.
        # A loopback-only ephemeral HTTP relay gives host workers their normal
        # HTTP contract while the server remains unable to reach the Internet.
        ip = command("docker", "inspect", self.name, "--format", '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
        target_url = "http://" + ip + ":8096"
        class Relay(http.server.BaseHTTPRequestHandler):
            def forward(self):
                length = int(self.headers.get("Content-Length", "0"))
                data = self.rfile.read(length) if length else (b"" if self.command == "POST" else None)
                headers = {key: value for key, value in self.headers.items() if key.lower() not in {"host", "connection"}}
                request = urllib.request.Request(target_url + self.path, data=data, headers=headers, method=self.command)
                try:
                    response = urllib.request.urlopen(request, timeout=20)
                except urllib.error.HTTPError as error:
                    response = error
                except OSError:
                    self.send_error(503)
                    return
                with response:
                    content = response.read()
                    self.send_response(response.status)
                    self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
            do_GET = do_POST = forward
            def log_message(self, *args):
                pass  # Never print credential-bearing request headers or paths.
        self.proxy = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Relay)
        threading.Thread(target=self.proxy.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:" + str(self.proxy.server_port)
        info = wait_for(lambda: self.api("System/Info/Public"), "isolated Jellyfin startup", 120)
        assert info["Version"].startswith("12.1"), "Review/rebase required for a different Jellyfin version"
        wait_for(lambda: self.api("Startup/User"), "startup user database readiness", 120)
        password = secrets.token_urlsafe(24)
        self.api("Startup/User", {"Name": "fixture-admin", "Password": password}, "POST")
        self.api("Startup/Configuration", {"ServerName": "publication-e2e", "UICulture": "en-US",
                 "MetadataCountryCode": "US", "PreferredMetadataLanguage": "en"}, "POST")
        self.api("Startup/RemoteAccess", {"EnableRemoteAccess": False, "EnableAutomaticPortMapping": False}, "POST")
        self.api("Startup/Complete", {}, "POST")
        auth = self.api("Users/AuthenticateByName", {"Username": "fixture-admin", "Pw": password}, "POST")
        self.token = auth["AccessToken"]
        # Native Jellyfin skips wholly empty physical roots, creating neither
        # a physical Folder nor PhysicalFolderIds. Establish unrelated anchors
        # during the permitted initial scan; tested imports are still absent.
        for kind, title, filename in (("movies", "Unrelated Anchor Movie", "Unrelated Anchor Movie.mkv"),
                                      ("shows", "Unrelated Anchor Series", "Unrelated Anchor Series - S01E01 - Anchor.mkv")):
            video = self.make_video(kind, title, filename)
            target = self.root / "view" / video.relative_to(self.root / "media")
            target.parent.mkdir(parents=True)
            os.link(video, target)
        # Provider selections are explicitly empty; the internal Docker network
        # independently blocks Internet access even if a future provider ignores them.
        options = {"EnableRealtimeMonitor": False, "EnableInternetProviders": False,
                   "EnableChapterImageExtraction": False, "EnableTrickplayImageExtraction": False,
                   "EnableAutomaticSeriesGrouping": False, "SaveLocalMetadata": False,
                   "MetadataSavers": [], "SubtitleFetchers": [],
                   "TypeOptions": [{"Type": kind, "MetadataFetchers": [], "ImageFetchers": [],
                                    "ImageOptions": []} for kind in ("Movie", "Series", "Season", "Episode")]}
        for kind, path in (("movies", "movies"), ("tvshows", "shows")):
            query = urllib.parse.urlencode({"name": path, "collectionType": kind,
                                           "paths": str(self.root / "media" / path), "refreshLibrary": "false"})
            self.api("Library/VirtualFolders?" + query, {"LibraryOptions": options}, "POST")
        # One empty-library scan is allowed exclusively during fixture bootstrap.
        self.api("Library/Refresh", method="POST")
        wait_for(lambda: self.scan_state()[0] == "Idle" and self.scan_state()[1], "initial empty-library scan", 120)
        time.sleep(2)
        self.baseline_scan = self.scan_state()[1]
        libraries = self.api("Library/VirtualFolders")
        assert len(libraries) == 2
        self.libraries = {Path(v["Locations"][0]).name: v["ItemId"] for v in libraries}
        self.anchors = self.api("Items?Recursive=true&IncludeItemTypes=Movie,Episode&Fields=Path,MediaSources")
        worker = self.root / "worker.sh"
        worker.write_text('JK="' + self.token + '"\n')
        worker.chmod(0o600)
        post_sub = self.root / "subtitles/post-sub.sh"
        post_sub.write_text('JELLYFIN_URL="' + self.url + '"\nJELLYFIN_KEY="' + self.token + '"\n')
        post_sub.chmod(0o600)
        # This fixture is known SDR. The adapter validates the generated video
        # with real ffprobe and supplies mediainfo's explicit SDR separator only.
        # It does not test HDR/DV classification or conversion admission.
        ffprobe = shutil.which("ffprobe")
        assert ffprobe, "ffprobe is required"
        adapter = self.root / "tools/mediainfo"
        adapter.write_text("#!/usr/bin/env python3\nimport subprocess,sys\n"
                           "subprocess.run([" + repr(ffprobe) + ",'-v','error','-select_streams','v:0','-show_entries',"
                           "'stream=codec_name','-of','csv=p=0',sys.argv[-1]],check=True,stdout=subprocess.DEVNULL)\nprint('|')\n")
        adapter.chmod(0o755)

    def make_video(self, kind, title, filename):
        path = self.root / "media" / kind / title / filename
        path.parent.mkdir(parents=True)
        ffmpeg = shutil.which("ffmpeg")
        assert ffmpeg, "ffmpeg is required"
        command(ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=5",
                "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "3", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path))
        return path

    def reconcile(self, video=None):
        argv = [sys.executable, str(SERVER / "dovi/dovi-library-view-20260922.py"), "--apply", "--notify-jellyfin",
                "--new-title-bridge", "--media-root", str(self.root / "media"), "--view-root", str(self.root / "view"),
                "--compatibility-root", str(self.root / "compat"), "--worker", str(self.root / "worker.sh"),
                "--jellyfin", self.url]
        for flag, name in (("--state", "probe.sqlite"), ("--notification-state", "publication.sqlite"),
                           ("--retry-state", "retry.sqlite"), ("--queue", "queue"), ("--queue-lock", "locks/queue"),
                           ("--publication-lock", "locks/publication"), ("--title-locks", "locks/titles"), ("--run-lock", "locks/run")):
            argv.extend((flag, str(self.root / name)))
        if video:
            argv.extend(("--scope-title", str(video.parent), "--scope-file", str(video)))
            for key, value in self.identities(video).items():
                argv.extend(("--provider-id", key + "=" + value))
        else:
            argv.append("--notify-only")
        env = dict(os.environ, PATH=str(self.root / "tools") + os.pathsep + os.environ["PATH"])
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError("Isolated reconciler failed: " + result.stderr[-1500:])
        self.assert_no_scan()

    def due(self):
        # Advance only this fixture's durable scheduler timestamps, not its clock
        # or retry logic; keeps an acceptance run bounded instead of sleeping 60s.
        with sqlite3.connect(self.root / "publication.sqlite") as db:
            db.execute("UPDATE notification_outbox SET next_attempt=0")
            db.execute("UPDATE notification_receipts SET sent_at=sent_at-61")

    def item(self, path, kind):
        query = urllib.parse.urlencode({"Recursive": "true", "IncludeItemTypes": kind,
                                       "Fields": "Path,MediaSources,MediaStreams,ProviderIds", "EnableImages": "false"})
        matches = [x for x in self.api("Items?" + query)["Items"] if x.get("Path") == str(path)]
        assert len(matches) <= 1, "Duplicate native item for exact path"
        return matches[0] if matches and matches[0].get("MediaSources") else None

    def await_item(self, path, kind):
        def poll():
            self.due()
            self.reconcile()
            return self.item(path, kind)
        return wait_for(poll, kind + " indexed with a playable file", 90)

    def subtitle(self, item):
        sources = item["MediaSources"]
        source = sources[0]
        tracks = [x for x in source.get("MediaStreams", []) if x["Type"] == "Subtitle" and x.get("IsExternal")]
        if not tracks:
            return None
        track = tracks[0]
        return self.api("Videos/{}/{}/Subtitles/{}/Stream.vtt".format(item["Id"], source["Id"], track["Index"]), raw=True)

    def raw_subtitle(self, action, video=None, subtitle=None):
        argv = [sys.executable, str(SERVER / "subtitle-publication/subtitle-raw-arrival.py"), action]
        if video:
            argv.extend((str(video), str(subtitle)))
        argv.extend(("--root", str(self.root / "subtitles"), "--canonical", str(self.root / "media"),
                     "--view", str(self.root / "view")))
        command(*argv, timeout=100)
        self.assert_no_scan()

    def raw_due(self):
        with sqlite3.connect(self.root / "subtitles/four-track-jobs.sqlite") as db:
            db.execute("UPDATE raw_subtitle_arrivals SET available=0,next_attempt=0 WHERE status='pending'")
            db.execute("UPDATE jellyfin_refresh_hints SET sent=sent-301")

    @staticmethod
    def identities(video):
        # Synthetic IDs, deliberately not a real catalogue title. Offline
        # providers cannot replace these before the assertion.
        return {"Tmdb": "991234567"} if "movies" in video.parts else {"Tvdb": "991234568", "Tmdb": "991234569"}

    def verify_discovery_identity(self, video, kind, indexed):
        if kind == "Episode":
            titles = self.api("Items?Recursive=true&IncludeItemTypes=Series&Fields=Path,ProviderIds")["Items"]
            title = next(item for item in titles if item.get("Path") == str(video.parent))
            library = self.libraries["shows"]
        else:
            title, library = indexed, self.libraries["movies"]
        assert all(title.get("ProviderIds", {}).get(key) == value for key, value in self.identities(video).items())
        body = {"libraryId": library, "expectedParentPath": str(video.parent.parent),
                "directoryName": video.parent.name, "kind": "Series" if kind == "Episode" else "Movie",
                "providerIds": self.identities(video)}
        result = self.api("Habibi/LibraryExperience/DiscoverTitle", body, "POST")
        assert result["ItemId"].replace("-", "") == title["Id"].replace("-", "")
        assert result["Created"] is False and result["Queued"] is True
        body["providerIds"] = {"Tmdb": "991234570"}
        try:
            self.api("Habibi/LibraryExperience/DiscoverTitle", body, "POST")
        except urllib.error.HTTPError as error:
            assert error.code == 409
        else:
            raise AssertionError("Conflicting native identity was not rejected")
        self.check(kind + " native provider-ID seed, plugin duplicate idempotency and conflicting-ID rejection")

    def exercise(self):
        movie = self.make_video("movies", "Fixture Movie (2026)", "Fixture Movie (2026).mkv")
        episode = self.make_video("shows", "Fixture Series", "Fixture Series - S01E01 - Pilot.mkv")
        for video, kind in ((movie, "Movie"), (episode, "Episode")):
            self.reconcile(video)
            indexed = self.await_item(video, kind)
            assert indexed["MediaSources"][0]["Protocol"] == "File"
            view = self.root / "view" / video.relative_to(self.root / "media")
            assert os.path.samefile(video, view), "Actual maintained publisher must create the view hardlink"
            original_id = indexed["Id"]
            self.check(kind + " real reconciler → new-title plugin → native playable item, no global scan")
            self.verify_discovery_identity(video, kind, indexed)
            self.reconcile(video)
            self.due()
            self.reconcile()
            assert self.item(video, kind)["Id"] == original_id
            self.check(kind + " duplicate event preserves exactly one native ID")
        subtitle = episode.with_suffix(".ar.srt")
        def replace(text):
            staging = subtitle.with_suffix(".new")
            staging.write_bytes(("\ufeff1\r\n00:00:00,500 --> 00:00:02,500\r\n" + text + "  \r\n\r\n").encode("utf-8"))
            os.replace(staging, subtitle)
            self.raw_subtitle("arrival", episode, subtitle)
        first, second = "مرحبا الإصدار الأول A", "مرحبا الإصدار الثاني B"
        for text in (first, second):
            replace(text)
            def served():
                self.raw_due()
                self.raw_subtitle("work")
                with sqlite3.connect(self.root / "subtitles/four-track-jobs.sqlite") as db:
                    completed = db.execute("SELECT status FROM raw_subtitle_arrivals WHERE fingerprint=?",
                                          (hashlib.sha256(subtitle.read_bytes()).hexdigest(),)).fetchone()
                    if not completed or completed[0] != "complete":
                        return None
                item = self.item(episode, "Episode")
                data = self.subtitle(item) if item else None
                return data if data and text in data else None
            content = wait_for(served, "native Arabic subtitle response " + text[-1], 90)
            assert "WEBVTT" in content and "00:00:00.500" in content
            if text == second:
                assert first not in content, "Replacement response retained stale subtitle content"
            view = self.root / "view" / subtitle.relative_to(self.root / "media")
            assert os.path.samefile(subtitle, view)
            self.check("Actual raw-arrival worker SRT " + text[-1] + " → view hardlink → exact native refresh → served_exact normalized SRT and VTT")
        with sqlite3.connect(self.root / "publication.sqlite") as db:
            self.due()
            self.reconcile()
            assert db.execute("SELECT COUNT(*) FROM notification_deadletters").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM notification_outbox").fetchone()[0] == 0
        self.check("Durable publication acknowledged only after native media-source indexing")
        for original in self.anchors["Items"]:
            current = self.api("Items?Ids=" + original["Id"] + "&Fields=Path,MediaSources")["Items"]
            assert len(current) == 1 and current[0]["Path"] == original["Path"]
            assert current[0]["MediaSources"] == original["MediaSources"]
        self.check("Unrelated anchor movie and episode retain native identity and media sources")
        request = urllib.request.Request(self.url + "/Habibi/LibraryExperience/DiscoverTitle",
                                         data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            assert error.code in {401, 403}
        else:
            raise AssertionError("Unauthenticated discovery was allowed")
        self.check("Native elevated endpoint rejects unauthenticated discovery")
        assert self.source_hashes == {str(path.relative_to(SERVER)): hashlib.sha256(path.read_bytes()).hexdigest()
                                      for path in self.source_files}, "Source bytes changed during E2E acceptance; rerun"
        return {"status": "passed", "jellyfinVersion": "12.1", "imageId": self.image_id,
                "pluginSha256": self.plugin_hash, "sourceSha256": self.source_hashes, "checks": self.results,
                "scope": "synthetic SDR; actual reconciler and real Jellyfin; not ARR hook/GPU/client playback"}

    def cleanup(self):
        if self.proxy:
            self.proxy.shutdown()
            self.proxy.server_close()
        if self.container_started:
            command("docker", "rm", "-f", self.name, timeout=30)
        if self.network_created:
            command("docker", "network", "rm", self.network, timeout=30)
        if not self.args.keep:
            shutil.rmtree(self.root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Explicitly authorize this isolated fixture run")
    parser.add_argument("--image", default=IMAGE, help="Already-local, reviewed Jellyfin 12.1 image; never pulled")
    parser.add_argument("--keep", action="store_true", help="Keep private temporary fixture after removing its container")
    args = parser.parse_args()
    if not args.run:
        print("Plan only: pass --run to create a localhost-only, Internet-isolated disposable Jellyfin fixture. No production mounts, DB or credentials.")
        return
    fixture = Fixture(args)
    try:
        fixture.start()
        print(json.dumps(fixture.exercise(), ensure_ascii=False, indent=2))
    finally:
        fixture.cleanup()
        if args.keep:
            print("Private fixture retained at " + str(fixture.root), file=sys.stderr)


if __name__ == "__main__":
    main()
