"""Opt-in Native-mode library originals; no provider, account or DV guessing.

Installed as jellyfin_kodi/helper/native_originals.py with the paired patch.
TCP preflight bounds a dead host/port check, NOT Kodi VFS or midstream faults.
"""
import ipaddress
import socket
from urllib.parse import unquote, urlsplit


def eligible(item, source, native_mode, force_transcode):
    if str(native_mode) != "1" or force_transcode:
        return False
    if item.get("MediaType") != "Video" or item.get("Type") not in ("Movie", "Episode"):
        return False
    if item.get("SourceType", "Library") != "Library":
        return False
    if str(source.get("Protocol", "")).lower() != "file" or not source.get("SupportsDirectPlay"):
        return False
    if source.get("Type") == "Placeholder" or any(source.get(key) for key in (
        "RequiresOpening", "RequiresClosing", "RequiresLooping", "IsInfiniteStream"
    )):
        return False
    containers = str(source.get("Container", "")).lower().split(",")
    if "strm" in [value.strip() for value in containers]:
        return False
    return not any(str(value or "").lower().endswith(".strm") for value in (
        item.get("Path"), source.get("Path")
    ))


def _safe_path(path):
    return (
        isinstance(path, str) and path.startswith("/") and not path.startswith("//")
        and not any(char in path for char in ("\\", "\x00", "\r", "\n", "?", "|"))
        and not any(part in (".", "..") for part in unquote(path).split("/"))
    )


def map_native_path(path, mappings):
    """Return (Kodi NFS URI, literal private host), or no trusted candidate.

    Only the longest exact configured prefix wins. An explicit narrower SMB or
    invalid mapping must not fall through to a broader NFS mapping.
    """
    if not _safe_path(path) or not isinstance(mappings, dict):
        return None
    matches = []
    for prefix, replacement in mappings.items():
        if not _safe_path(prefix):
            continue
        prefix = prefix.rstrip("/") + "/"
        if path.startswith(prefix) and len(path) > len(prefix):
            matches.append((len(prefix), prefix, replacement))
    if not matches:
        return None
    longest = max(entry[0] for entry in matches)
    chosen = [entry for entry in matches if entry[0] == longest]
    _, prefix, replacement = chosen[0]
    if not isinstance(replacement, str) or any(entry[2] != replacement for entry in chosen):
        return None
    try:
        target = urlsplit(replacement)
        if (target.scheme.lower() != "nfs" or target.username is not None
                or target.password is not None or target.query or target.fragment
                or target.port not in (None, 2049) or not target.hostname
                or "%" in target.hostname or not _safe_path(target.path)):
            return None
        host = ipaddress.ip_address(target.hostname)
        private = host.is_private or (host.version == 4 and host in ipaddress.ip_network("100.64.0.0/10"))
        if not private or host.is_loopback or host.is_unspecified or host.is_multicast:
            return None
    except (TypeError, ValueError):
        return None
    # Kodi's NFS path is passed to libnfs without URL-decoding the filename.
    # Keep spaces, Unicode, # and % literally, matching existing native paths.
    # NFS option delimiters ? and | were rejected by _safe_path above.
    mapped = replacement.rstrip("/") + "/" + path[len(prefix):]
    return mapped, str(host)


def available_native_path(candidate, exists, connect=None):
    """Do not commit playback state until both preflight and VFS succeed."""
    if candidate is None:
        return None
    mapped, host = candidate
    connect = connect or socket.create_connection
    try:
        with connect((host, 2049), timeout=0.5):
            pass
        if exists(mapped):
            return mapped
    except Exception:
        # No credential-bearing path, provider URL, or raw exception in logs.
        pass
    return None
