"""Fail-closed manifest checks for the optional remote-native Kodi branch.

This module is pure apart from its injected readers.  The patched Kodi call
site must perform its existing 0.5-second TCP/NFS preflight *before* asking
this module to read the manifest.  Kodi VFS calls themselves cannot be made
reliably cancellable from Python, so a failed/hung VFS read must never be a
reason to bypass this gate.
"""
from __future__ import annotations

import json
from typing import Any, Callable

try:  # installed package / isolated direct-test fallback
    from .manifest import MAX_ENTRIES, MAX_MANIFEST_BYTES, SCHEMA, canonical_codec
except ImportError:  # pragma: no cover - runtime package always uses relative import
    from manifest import MAX_ENTRIES, MAX_MANIFEST_BYTES, SCHEMA, canonical_codec


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _language(value):
    # ISO639-2 bibliographic and terminologic spellings describe the same
    # language. Jellyfin normalizes these, while Matroska/ffprobe often keeps
    # the bibliographic spelling. This does not collapse different languages.
    aliases = {'alb': 'sqi', 'arm': 'hye', 'baq': 'eus', 'bur': 'mya',
               'chi': 'zho', 'cze': 'ces', 'dut': 'nld', 'fre': 'fra',
               'geo': 'kat', 'ger': 'deu', 'gre': 'ell', 'ice': 'isl',
               'mac': 'mkd', 'mao': 'mri', 'may': 'msa', 'per': 'fas',
               'rum': 'ron', 'slo': 'slk', 'tib': 'bod', 'wel': 'cym'}
    code = str(value or 'und').lower()
    return aliases.get(code, code)


def _revision(value: Any, *, require_inode: bool = False) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    size, mtime = _integer(value.get("size")), _integer(value.get("mtime"))
    inode = _integer(value.get("inode"))
    if size is None or size <= 0 or mtime is None or mtime < 0:
        return None
    if require_inode and (inode is None or inode <= 0):
        return None
    return {"size": size, "mtime": mtime, "inode": inode or 0}


def _no_duplicate_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def load_manifest(read_limited: Callable[[int], bytes], now: int) -> dict[str, Any] | None:
    """Read at most MAX+1 bytes.  Invalid/expired data is never tolerated."""
    try:
        raw = read_limited(MAX_MANIFEST_BYTES + 1)
        if not isinstance(raw, bytes) or len(raw) > MAX_MANIFEST_BYTES:
            return None
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_json)
    except (UnicodeDecodeError, ValueError, OSError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return None
    created, expires = _integer(data.get("created_at")), _integer(data.get("expires_at"))
    entries = data.get("entries")
    if (created is None or expires is None or created > now or expires < now or expires - created > 86400
            or not isinstance(entries, dict) or len(entries) > MAX_ENTRIES):
        return None
    return data


def jellyfin_stream_signature(source: dict[str, Any]) -> list[dict[str, Any]] | None:
    streams = source.get("MediaStreams")
    if not isinstance(streams, list):
        return None
    # Jellyfin 12 can prepend external sidecars then renumber *all* stream
    # indexes.  Validate the resulting index table for corruption, but never
    # use those transport indexes to identify the embedded container layout.
    indexes = set()
    for stream in streams:
        if not isinstance(stream, dict):
            return None
        index = _integer(stream.get("Index"))
        if index is None or index < 0 or index in indexes:
            return None
        indexes.add(index)
    signature = []
    for stream in streams:
        if not isinstance(stream, dict) or stream.get("Type") not in ("Audio", "Subtitle"):
            continue
        # Sidecars are mapped by Jellyfin independently.  They must not make a
        # verified container pair fail its native eligibility check.
        if stream.get("Type") == "Subtitle" and bool(stream.get("IsExternal")):
            continue
        kind = stream["Type"].lower()
        codec = str(stream.get("Codec") or "").lower()
        if not codec:
            return None
        signature.append({
            "type": "audio" if kind == "audio" else "subtitle", "codec": canonical_codec(codec),
            "language": _language(stream.get("Language")),
            "title": str(stream.get("Title") or ""),
            "default": bool(stream.get("IsDefault")), "forced": bool(stream.get("IsForced")),
            "channels": _integer(stream.get("Channels")) if kind == "audio" else None,
            # Jellyfin drops annotations such as `5.1(side)`.  Runtime
            # identity compares the canonical portion only; the publisher's
            # original-vs-companion ffprobe comparison remains exact.
            "channel_layout": str(stream.get("ChannelLayout") or "").split("(", 1)[0] if kind == "audio" else None,
        })
    return signature or None


def _manifest_runtime_signature(entry):
    """Drop raw ffprobe indexes only for Jellyfin's renumbered runtime view."""
    if not isinstance(entry, list):
        return None
    result = []
    for stream in entry:
        if not isinstance(stream, dict) or _integer(stream.get("index")) is None:
            return None
        copy = dict(stream)
        copy.pop("index", None)
        copy['language'] = _language(copy.get('language'))
        if copy.get("type") == "audio":
            copy["channel_layout"] = str(copy.get("channel_layout") or "").split("(", 1)[0]
        result.append(copy)
    return result


def allows_native(manifest: dict[str, Any] | None, logical_path: str, original_stat: dict[str, Any],
                  jellyfin_source: dict[str, Any]) -> bool:
    """Return True only for an exact, current P7/P8 mapping.

    `original_stat` comes from the mapped NFS original *after* network
    preflight.  Its inode is compared only if VFS gives a usable positive
    value; size and second-resolution mtime are mandatory.  The current
    Jellyfin source is the P8 companion exposed by the compatibility view.
    """
    if (not isinstance(manifest, dict) or not isinstance(logical_path, str)
            or not logical_path.startswith("/data/media/")
            or any(part in ("", ".", "..") for part in logical_path.split("/")[1:])):
        return False
    if not isinstance(jellyfin_source, dict) or jellyfin_source.get("Path") != logical_path:
        return False
    entry = manifest.get("entries", {}).get(logical_path)
    if not isinstance(entry, dict):
        return False
    original, companion = _revision(entry.get("original")), _revision(entry.get("companion"))
    current = _revision(original_stat)
    if not original or not companion or not current:
        return False
    if current["size"] != original["size"] or current["mtime"] != original["mtime"]:
        return False
    if current["inode"] > 0 and original["inode"] > 0 and current["inode"] != original["inode"]:
        return False
    source_size = _integer(jellyfin_source.get("Size"))
    if source_size is None or source_size != companion["size"]:
        return False
    actual = jellyfin_stream_signature(jellyfin_source)
    expected = _manifest_runtime_signature(entry.get("streams"))
    return actual is not None and expected is not None and actual == expected
