#!/usr/bin/env python3
"""Build an atomic, fail-closed manifest for remote P7-original playback.

This is deliberately a *publisher-side* tool.  It never changes a library,
the compatibility view, or a media file.  An entry is emitted only when the
current canonical P7 file, its P8.1 companion, and the Jellyfin view are a
stable, exact-layout pair.  Anything uncertain is omitted, causing Kodi to
use its ordinary HTTPS/P8 playback path.

The manifest contains no server address, credential, provider URL, or title
metadata.  It is intended to be copied to an already authenticated device by
a separate deployment step.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any


SCHEMA = "remote-native-originals/v1"
MAX_ENTRIES = 8192
MAX_MANIFEST_BYTES = 3 * 1024 * 1024
COMPAT_SUFFIX = " - P8.1 Compatibility"


class Reject(ValueError):
    """A media pair is not safe to publish as native."""


def file_revision(path: Path) -> dict[str, int]:
    stat = path.stat()
    if not path.is_file() or path.is_symlink() or stat.st_size <= 0:
        raise Reject("not a regular nonempty file")
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "mtime": int(stat.st_mtime), "inode": stat.st_ino}


def stable_revision(path: Path, before: dict[str, int]) -> None:
    if file_revision(path) != before:
        raise Reject("file changed while being probed")


def relative_source(source: Path, media_root: Path) -> str:
    try:
        relative = source.resolve(strict=True).relative_to(media_root.resolve(strict=True))
    except (ValueError, OSError) as exc:
        raise Reject("source outside media root") from exc
    if relative.parts[0:1] not in (("movies",), ("shows",)) or source.suffix.lower() != ".mkv":
        raise Reject("unsupported source root or extension")
    if any(part in ("", ".", "..") for part in relative.parts):
        raise Reject("unsafe relative source")
    return "/data/media/" + relative.as_posix()


def paired_paths(source: Path, media_root: Path, compatibility_root: Path,
                 view_root: Path) -> tuple[str, Path, Path]:
    logical = relative_source(source, media_root)
    relative = Path(logical.removeprefix("/data/media/"))
    companion = compatibility_root / relative.with_name(relative.stem + COMPAT_SUFFIX + relative.suffix)
    view = view_root / relative
    return logical, companion, view


def _ffprobe_json(path: Path, runner=subprocess.run) -> dict[str, Any]:
    result = runner(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        check=False, capture_output=True, text=True, timeout=90,
    )
    if result.returncode != 0:
        raise Reject("ffprobe failed")
    try:
        value = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise Reject("ffprobe returned invalid JSON") from exc
    if not isinstance(value, dict) or not isinstance(value.get("streams"), list):
        raise Reject("ffprobe lacks streams")
    return value


def _profile(stream: dict[str, Any]) -> int | None:
    """Read ffprobe's DOVI configuration record without guessing from names."""
    candidates: list[Any] = [stream]
    candidates.extend(item for item in stream.get("side_data_list", []) if isinstance(item, dict))
    for item in candidates:
        value = item.get("dv_profile")
        try:
            profile = int(value)
        except (TypeError, ValueError):
            continue
        if profile in (7, 8):
            return profile
    return None


def _video_profile(probe: dict[str, Any]) -> int:
    profiles = {_profile(stream) for stream in probe["streams"] if stream.get("codec_type") == "video"}
    profiles.discard(None)
    if len(profiles) != 1:
        raise Reject("missing or ambiguous DOVI profile")
    return profiles.pop()


def _p8_compatibility_id(probe: dict[str, Any]) -> int | None:
    values = set()
    for stream in probe["streams"]:
        if stream.get("codec_type") != "video":
            continue
        for side_data in stream.get("side_data_list", []):
            if not isinstance(side_data, dict):
                continue
            try:
                values.add(int(side_data.get("dv_bl_signal_compatibility_id")))
            except (TypeError, ValueError):
                pass
    return values.pop() if len(values) == 1 else None


def _bool(value: Any) -> bool:
    return value in (1, True, "1", "true", "True")


def stream_signature(probe: dict[str, Any]) -> list[dict[str, Any]]:
    """Ordered audio + embedded subtitle layout, including Jellyfin indexes.

    The supplied P8 companion is the same container Jellyfin exposes through
    the compatibility view.  Kodi must see the same indexes/default choices
    before it is allowed to open the P7 original.
    """
    signature: list[dict[str, Any]] = []
    for stream in probe["streams"]:
        kind = stream.get("codec_type")
        if kind not in ("audio", "subtitle"):
            continue
        index = stream.get("index")
        if not isinstance(index, int) or index < 0:
            raise Reject("missing stream index")
        tags = stream.get("tags") if isinstance(stream.get("tags"), dict) else {}
        disposition = stream.get("disposition") if isinstance(stream.get("disposition"), dict) else {}
        # ffprobe's layout field is meaningful for audio only.  Preserve an
        # explicit null for subtitles so a malformed audio/subtitle swap is
        # never silently normalized.
        signature.append({
            "index": index,
            "type": kind,
            "codec": canonical_codec(stream.get("codec_name")),
            "language": str(tags.get("language") or "und").lower(),
            "title": str(tags.get("title") or ""),
            "default": _bool(disposition.get("default")),
            "forced": _bool(disposition.get("forced")),
            "channels": int(stream["channels"]) if kind == "audio" and str(stream.get("channels", "")).isdigit() else None,
            "channel_layout": str(stream.get("channel_layout") or "") if kind == "audio" else None,
        })
    if not signature:
        raise Reject("no embedded audio or subtitle signature")
    if any(not entry["codec"] for entry in signature):
        raise Reject("stream codec missing")
    return signature


def canonical_codec(value: Any) -> str:
    """Bridge ffprobe/Jellyfin's known spellings without weakening equality."""
    codec = str(value or "").lower()
    return {"hdmv_pgs_subtitle": "pgssub", "dvd_subtitle": "dvdsub", "srt": "subrip"}.get(codec, codec)


def duration(probe: dict[str, Any]) -> float:
    raw = (probe.get("format") or {}).get("duration")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise Reject("duration unavailable") from exc
    if not value > 0:
        raise Reject("invalid duration")
    return value


def view_is_companion(view: Path, companion: Path) -> bool:
    try:
        if view.is_symlink():
            return False
        left, right = view.stat(), companion.stat()
    except OSError:
        return False
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def build_entry(source: Path, media_root: Path, compatibility_root: Path,
                view_root: Path, runner=subprocess.run) -> tuple[str, dict[str, Any]]:
    logical, companion, view = paired_paths(source, media_root, compatibility_root, view_root)
    original_before = file_revision(source)
    companion_before = file_revision(companion)
    if not view_is_companion(view, companion):
        raise Reject("Jellyfin view is not the current companion inode")
    original_probe = _ffprobe_json(source, runner)
    companion_probe = _ffprobe_json(companion, runner)
    stable_revision(source, original_before)
    stable_revision(companion, companion_before)
    if not view_is_companion(view, companion):
        raise Reject("Jellyfin view changed while being probed")
    if _video_profile(original_probe) != 7:
        raise Reject("original is not DOVI profile 7")
    if _video_profile(companion_probe) != 8:
        raise Reject("companion is not DOVI profile 8")
    if _p8_compatibility_id(companion_probe) != 1:
        raise Reject("companion is not P8.1")
    source_duration, companion_duration = duration(original_probe), duration(companion_probe)
    if abs(source_duration - companion_duration) > 1.0:
        raise Reject("duration differs by more than one second")
    original_streams, companion_streams = stream_signature(original_probe), stream_signature(companion_probe)
    if original_streams != companion_streams:
        raise Reject("audio/subtitle layout differs")
    return logical, {
        "original": original_before,
        "companion": companion_before,
        "duration_seconds": round(companion_duration, 3),
        "streams": companion_streams,
    }


def atomic_write(path: Path, payload: dict[str, Any], mode: int = 0o644) -> None:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise Reject("manifest exceeds maximum size")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".remote-native-", dir=path.parent)
    try:
        # NFS exports use all_squash.  There are no credentials in this
        # manifest; it must therefore be readable by the restricted NFS user.
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def scan_companions(media_root: Path, compatibility_root: Path) -> list[Path]:
    """Enumerate the exact canonical counterpart of every named P8 companion.

    A filesystem traversal error or an over-limit result is an incomplete
    scan.  Callers must not publish a partial manifest in that case.
    """
    sources = []
    def scan_error(error):
        raise Reject("companion scan incomplete: " + str(error))
    try:
        for category in ("movies", "shows"):
            root = compatibility_root / category
            if not root.is_dir():
                continue
            for current, directories, filenames in os.walk(root, onerror=scan_error):
                directories.sort()
                for filename in sorted(filenames):
                    if not filename.endswith(COMPAT_SUFFIX + ".mkv"):
                        continue
                    if len(sources) >= MAX_ENTRIES:
                        raise Reject("companion scan exceeds entry limit")
                    companion = Path(current) / filename
                    relative = companion.relative_to(compatibility_root)
                    original_name = filename.removesuffix(COMPAT_SUFFIX + ".mkv") + ".mkv"
                    source = media_root / relative.with_name(original_name)
                    sources.append(source)
    except OSError as exc:
        raise Reject("companion scan incomplete") from exc
    return sorted(sources)


def _report(path: Path, rejected: dict[str, str]) -> None:
    atomic_write(path, {"rejected": rejected}, mode=0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-root", type=Path, default=Path("/data/media"))
    parser.add_argument("--compatibility-root", type=Path, default=Path("/data/media/compatibility/dovi-p8"))
    parser.add_argument("--view-root", type=Path, default=Path("/data/media/compatibility/jellyfin-view"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", action="append", type=Path,
                        help="canonical P7 .mkv; repeat, with an explicit scoped caller")
    parser.add_argument("--scan-companions", action="store_true",
                        help="bounded full companion scan; refuses to publish on incomplete enumeration")
    parser.add_argument("--report", type=Path, help="private mode-0600 rejection report")
    args = parser.parse_args()
    if not args.source and not args.scan_companions:
        parser.error("one or more --source values or --scan-companions is required")
    sources = list(args.source or [])
    if args.scan_companions:
        try:
            sources.extend(scan_companions(args.media_root, args.compatibility_root))
        except Reject as exc:
            if args.report:
                _report(args.report, {"scan": str(exc)})
            raise SystemExit(str(exc))
    if len(sources) > MAX_ENTRIES:
        raise SystemExit("source count exceeds entry limit; manifest not changed")
    entries: dict[str, dict[str, Any]] = {}
    rejected: dict[str, str] = {}
    for source in sources:
        try:
            logical, entry = build_entry(source, args.media_root, args.compatibility_root, args.view_root)
            if logical in entries:
                raise Reject("duplicate logical path")
            if len(entries) >= MAX_ENTRIES:
                raise Reject("entry limit reached")
            entries[logical] = entry
        except (OSError, Reject, subprocess.TimeoutExpired) as exc:
            rejected[str(source)] = str(exc)
    if args.report:
        _report(args.report, rejected)
    now = int(time.time())
    atomic_write(args.output, {"schema": SCHEMA, "created_at": now, "expires_at": now + 86400,
                               "entries": entries})
    print(json.dumps({"published": len(entries), "rejected": len(rejected)}, sort_keys=True))
    # Rejections are intentionally only a count in normal output; deployment
    # logs may contain title paths and must remain private.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
