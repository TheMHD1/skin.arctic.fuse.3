#!/usr/bin/env python3
"""Publish IMDb ratings for Jellyfin's owned Movie/Series IDs only.

No global IMDb database is retained. The official compressed source is cached
privately to support conditional requests; the published JSON is small.
"""

import argparse
import datetime as dt
import fcntl
import gzip
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request

SOURCE_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
HEADER = b"tconst\taverageRating\tnumVotes\n"
ID_RE = re.compile(rb"tt[0-9]+\Z")
MAX_COMPRESSED = 64 * 1024 * 1024
MAX_UNCOMPRESSED = 512 * 1024 * 1024
MAX_ROWS = 8_000_000
MAX_LIBRARY_ITEMS = 50_000
OUTPUT_NAME = "imdb-library-ratings.json"
CACHE_NAME = "title.ratings.tsv.gz"
STATE_NAME = "download-state.json"


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_bytes(path, data):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=".imdb-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
        fsync_dir(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def api_json(base, token, path, params=None):
    url = base.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f'MediaBrowser Token="{token}"', "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Jellyfin HTTP {resp.status}")
        return json.load(resp)


def owned_ids(base, token):
    views = api_json(base, token, "/Library/VirtualFolders")
    allowed = []
    for view in views:
        name = str(view.get("Name") or "")
        kind = view.get("CollectionType")
        if name.casefold().startswith("venom"):
            continue
        if kind not in ("movies", "tvshows", None, "mixed"):
            continue
        # Null/mixed supports Shoko-style media; names known to be nonmedia
        # are never treated as an all-library fallback.
        if name.casefold() in {"collections", "playlists", "live tv", "music", "books", "photos"}:
            continue
        if view.get("ItemId"):
            allowed.append(view["ItemId"])
    if not allowed:
        raise RuntimeError("No owned media views found; refusing an all-library query")
    ids = set()
    scanned = 0
    for parent in allowed:
        start = 0
        while True:
            data = api_json(base, token, "/Items", {
                "ParentId": parent, "Recursive": "true", "IncludeItemTypes": "Movie,Series",
                "Fields": "ProviderIds", "StartIndex": start, "Limit": 500,
            })
            rows = data.get("Items") or []
            if not isinstance(rows, list):
                raise RuntimeError("Malformed Jellyfin item page")
            scanned += len(rows)
            if scanned > MAX_LIBRARY_ITEMS:
                raise RuntimeError("Owned-library item cap exceeded")
            for item in rows:
                if item.get("Type") not in ("Movie", "Series"):
                    continue
                providers = item.get("ProviderIds") or {}
                imdb = next((v for k, v in providers.items() if k.casefold() == "imdb"), None)
                if isinstance(imdb, str) and re.fullmatch(r"tt[0-9]+", imdb):
                    ids.add(imdb)
            start += len(rows)
            total = data.get("TotalRecordCount")
            if not rows or (isinstance(total, int) and start >= total) or len(rows) < 500:
                break
    if not ids:
        raise RuntimeError("No owned IMDb IDs found; keeping prior output")
    return ids


class FixedHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname != "datasets.imdbws.com" or parsed.path != "/title.ratings.tsv.gz":
            raise RuntimeError("Dataset redirect outside fixed official URL")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(cache, state, output_dir):
    headers = {"User-Agent": "HabibiOwnedLibraryIMDbRatings/1.0"}
    if cache.is_file():
        if state.get("etag"):
            headers["If-None-Match"] = state["etag"]
        if state.get("last_modified"):
            headers["If-Modified-Since"] = state["last_modified"]
    req = urllib.request.Request(SOURCE_URL, headers=headers)
    opener = urllib.request.build_opener(FixedHostRedirect())
    try:
        response = opener.open(req, timeout=40)
    except urllib.error.HTTPError as exc:
        if exc.code == 304 and cache.is_file() and cache.stat().st_size > 0:
            return cache, None, state
        raise
    with response:
        if response.status != 200:
            raise RuntimeError(f"Dataset HTTP {response.status}")
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_COMPRESSED:
            raise RuntimeError("Dataset compressed length exceeds cap")
        fd, name = tempfile.mkstemp(prefix=".imdb-download-", dir=output_dir)
        try:
            size = 0
            with os.fdopen(fd, "wb") as out:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    size += len(block)
                    if size > MAX_COMPRESSED:
                        raise RuntimeError("Dataset compressed size exceeds cap")
                    out.write(block)
                out.flush()
                os.fsync(out.fileno())
            if size == 0:
                raise RuntimeError("Empty dataset download")
            new_state = {
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
            }
            return Path(name), Path(name), new_state
        except BaseException:
            os.unlink(name)
            raise


def parse_dataset(gz_path, wanted, *, min_rows=100_000):
    found = {}
    rows = 0
    uncompressed = 0
    with gzip.open(gz_path, "rb") as src:
        while True:
            # Official rows are tiny. Bound each read so a corrupt gzip cannot
            # allocate an enormous single line before the global size check.
            line = src.readline(256)
            if not line:
                break
            if not line.endswith(b"\n"):
                raise RuntimeError("Oversized or unterminated dataset row")
            uncompressed += len(line)
            if uncompressed > MAX_UNCOMPRESSED:
                raise RuntimeError("Dataset uncompressed size exceeds cap")
            if rows == 0:
                if line != HEADER:
                    raise RuntimeError("Unexpected IMDb ratings header")
                rows = 1
                continue
            rows += 1
            if rows > MAX_ROWS + 1:
                raise RuntimeError("Dataset row cap exceeded")
            fields = line.rstrip(b"\n").split(b"\t")
            if len(fields) != 3 or not ID_RE.fullmatch(fields[0]):
                raise RuntimeError(f"Invalid dataset row {rows}")
            try:
                rating = float(fields[1])
                votes = int(fields[2])
            except ValueError as exc:
                raise RuntimeError(f"Invalid dataset value at row {rows}") from exc
            if not 0 <= rating <= 10 or votes < 1 or not rating == rating:
                raise RuntimeError(f"Out-of-range dataset value at row {rows}")
            imdb = fields[0].decode("ascii")
            if imdb in wanted:
                if imdb in found:
                    raise RuntimeError("Duplicate owned IMDb ID in dataset")
                found[imdb] = {"rating": rating, "votes": votes}
    if rows - 1 < min_rows:
        raise RuntimeError("Dataset row count below safe publication threshold")
    if not found:
        raise RuntimeError("No owned IMDb ratings matched; keeping prior output")
    return found


def run(args):
    output_dir = Path(args.output_dir)
    if not output_dir.is_dir():
        raise RuntimeError("Private output directory must already exist")
    if output_dir.is_symlink():
        raise RuntimeError("Output directory must not be a symlink")
    token = Path(args.jellyfin_key_file).read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("Empty Jellyfin key file")
    with (output_dir / ".imdb-library-ratings.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        wanted = owned_ids(args.jellyfin_url, token)
        cache = output_dir / CACHE_NAME
        state_path = output_dir / STATE_NAME
        state = json.loads(state_path.read_text()) if state_path.is_file() else {}
        downloaded, temporary, new_state = download(cache, state, output_dir)
        try:
            ratings = parse_dataset(downloaded, wanted)
            payload = {"schema": 1, "fetched_at": utc_now(), "source_url": SOURCE_URL,
                       "ratings": dict(sorted(ratings.items()))}
            encoded = (json.dumps(payload, separators=(",", ":"), ensure_ascii=True) + "\n").encode()
            if temporary:
                os.chmod(temporary, 0o600)
                os.replace(temporary, cache)
                temporary = None
                fsync_dir(output_dir)
                atomic_bytes(state_path, (json.dumps(new_state, separators=(",", ":")) + "\n").encode())
            atomic_bytes(output_dir / OUTPUT_NAME, encoded)
            return len(wanted), len(ratings)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jellyfin-url", required=True, help="Private Jellyfin base URL")
    parser.add_argument("--jellyfin-key-file", required=True)
    parser.add_argument("--output-dir", required=True, help="Existing private directory")
    args = parser.parse_args()
    owned, matched = run(args)
    print(f"Updated owned IMDb ratings: {matched}/{owned} IDs")


if __name__ == "__main__":
    main()
