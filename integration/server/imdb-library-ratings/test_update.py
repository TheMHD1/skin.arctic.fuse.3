#!/usr/bin/env python3
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("imdb_library_update", Path(__file__).with_name("update.py"))
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)


class RatingsTests(unittest.TestCase):
    def make_gz(self, path, rows, header=update.HEADER):
        with gzip.open(path, "wb") as out:
            out.write(header)
            for row in rows:
                out.write(row)

    def test_only_exact_owned_ids_published(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ratings.gz"
            self.make_gz(path, [b"tt12\t8.7\t100\n", b"tt13\t4.1\t20\n", b"tt14\t9.9\t3\n"])
            self.assertEqual(update.parse_dataset(path, {"tt12", "tt14"}, min_rows=3),
                             {"tt12": {"rating": 8.7, "votes": 100}, "tt14": {"rating": 9.9, "votes": 3}})

    def test_bad_header_values_and_short_source_fail(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ratings.gz"
            self.make_gz(path, [b"tt12\t8.7\t100\n"], b"wrong\theader\n")
            with self.assertRaisesRegex(RuntimeError, "header"):
                update.parse_dataset(path, {"tt12"}, min_rows=1)
            self.make_gz(path, [b"tt12\t11.0\t100\n"])
            with self.assertRaisesRegex(RuntimeError, "Out-of-range"):
                update.parse_dataset(path, {"tt12"}, min_rows=1)
            self.make_gz(path, [b"tt12\t8.7\t100\n"])
            with self.assertRaisesRegex(RuntimeError, "threshold"):
                update.parse_dataset(path, {"tt12"}, min_rows=100_000)

    def test_duplicate_and_zero_match_fail(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ratings.gz"
            self.make_gz(path, [b"tt12\t8.7\t100\n", b"tt12\t8.6\t101\n"])
            with self.assertRaisesRegex(RuntimeError, "Duplicate"):
                update.parse_dataset(path, {"tt12"}, min_rows=1)
            with self.assertRaisesRegex(RuntimeError, "No owned"):
                update.parse_dataset(path, {"tt99"}, min_rows=1)

    def test_scope_excludes_venom_and_nonmedia_even_if_api_returns_boxset(self):
        views = [
            {"Name": "Movies", "CollectionType": "movies", "ItemId": "owned"},
            {"Name": "Venom Movies", "CollectionType": "movies", "ItemId": "venom"},
            {"Name": "Collections", "CollectionType": "boxsets", "ItemId": "boxes"},
            {"Name": "Shoko Anime", "CollectionType": None, "ItemId": "mixed"},
        ]
        calls = []
        def fake_api(base, token, path, params=None):
            if path == "/Library/VirtualFolders":
                return views
            calls.append(params["ParentId"])
            if params["ParentId"] == "owned":
                return {"Items": [
                    {"Type": "Movie", "ProviderIds": {"Imdb": "tt123"}},
                    {"Type": "BoxSet", "ProviderIds": {"Imdb": "tt999"}},
                ], "TotalRecordCount": 2}
            return {"Items": [{"Type": "Series", "ProviderIds": {"imdb": "tt456"}}], "TotalRecordCount": 1}
        with mock.patch.object(update, "api_json", side_effect=fake_api):
            self.assertEqual(update.owned_ids("http://localhost", "key"), {"tt123", "tt456"})
        self.assertEqual(calls, ["owned", "mixed"])

    def test_failed_dataset_keeps_previous_published_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            keyfile = root / "key"
            keyfile.write_text("fixture-key")
            published = root / update.OUTPUT_NAME
            published.write_text('{"old":true}\n')
            candidate = root / "candidate.gz"
            self.make_gz(candidate, [b"tt123\t9.0\t100\n"])
            args = mock.Mock(output_dir=str(root), jellyfin_key_file=str(keyfile), jellyfin_url="http://localhost")
            with mock.patch.object(update, "owned_ids", return_value={"tt123"}), \
                    mock.patch.object(update, "download", return_value=(candidate, None, {})):
                with self.assertRaisesRegex(RuntimeError, "threshold"):
                    update.run(args)
            self.assertEqual(json.loads(published.read_text()), {"old": True})


if __name__ == "__main__":
    unittest.main()
