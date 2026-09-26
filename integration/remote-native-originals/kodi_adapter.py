"""Kodi-facing opt-in adapter for verified remote P7 originals.

This is copied as `jellyfin_kodi/helper/remote_originals.py` only by the
remote-device release builder.  It deliberately does not read `data.json` or
enable global Native mode: an unlisted item remains on the existing HTTPS/P8
route.  All functions accept dependencies for isolated regression tests.
"""
from __future__ import annotations

import json
import ipaddress
import re
import socket
import time
from urllib.parse import urlsplit

CONFIG_SCHEMA = "remote-native-originals/config-v1"
CONFIG_LIMIT = 32 * 1024
MAC = re.compile(r"^[0-9a-f]{2}(?::[0-9a-f]{2}){5}$")
HOST = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
REQUIRED_MAPPINGS = {"/data/media/movies/", "/data/media/shows/"}
MANIFEST_PATH = "/.native/verified-p7-v1.json"


def _bytes(value):
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return None


def _uri_host(uri):
    try:
        target = urlsplit(uri)
        if (target.scheme.lower() != "nfs" or target.username or target.password or target.query or target.fragment
                or target.port not in (None, 2049) or not target.hostname):
            return None
        host = ipaddress.ip_address(target.hostname)
        permitted = host.is_private or (host.version == 4 and host in ipaddress.ip_network("100.64.0.0/10"))
        return str(host) if permitted and not host.is_loopback and not host.is_unspecified and not host.is_multicast else None
    except (AttributeError, ValueError):
        return None


def validate_config(config):
    """Pure config validation, also used by the release builder."""
    if not isinstance(config, dict) or config.get("schema") != CONFIG_SCHEMA or config.get("enabled") is not True:
        return None
    expected_host, expected_mac = config.get("hostname"), config.get("wifi_mac")
    if not isinstance(expected_host, str) or not HOST.fullmatch(expected_host):
        return None
    if not isinstance(expected_mac, str) or not MAC.fullmatch(expected_mac):
        return None
    mappings, manifest_uri = config.get("mappings"), config.get("manifest_uri")
    if not isinstance(mappings, dict) or set(mappings) != REQUIRED_MAPPINGS or not isinstance(manifest_uri, str):
        return None
    hosts = [_uri_host(mappings[prefix]) for prefix in sorted(REQUIRED_MAPPINGS)]
    if any(host is None for host in hosts):
        return None
    # The only reachable native data is the two read-only library roots and
    # the one versioned manifest.  Do not turn this opt-in into a generic NFS
    # browser merely because its config is local.
    try:
        if urlsplit(mappings["/data/media/movies/"]).path != "/movies/":
            return None
        if urlsplit(mappings["/data/media/shows/"]).path != "/shows/":
            return None
        if urlsplit(manifest_uri).path != MANIFEST_PATH:
            return None
    except (AttributeError, ValueError):
        return None
    manifest_host = _uri_host(manifest_uri)
    if len(set(hosts)) != 1 or manifest_host not in hosts:
        return None
    return config


def load_config(read_limited, hostname, wifi_mac):
    """Validate a device-bound, two-root private opt-in configuration."""
    try:
        raw = _bytes(read_limited(CONFIG_LIMIT + 1))
        if raw is None or len(raw) > CONFIG_LIMIT:
            return None
        config = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    config = validate_config(config)
    if config is None or hostname != config["hostname"] or str(wifi_mac).lower() != config["wifi_mac"]:
        return None
    return config


def _connect(host, connect):
    try:
        with connect((host, 2049), timeout=0.5):
            return True
    except Exception:
        return False


def _vfs_stat(vfs, path):
    """Normalize Kodi's callable Stat API.  Missing precision rejects."""
    try:
        stat = vfs.Stat(path)
        size = stat.st_size() if callable(getattr(stat, "st_size", None)) else stat.st_size
        mtime = stat.st_mtime() if callable(getattr(stat, "st_mtime", None)) else stat.st_mtime
        inode = stat.st_ino() if callable(getattr(stat, "st_ino", None)) else getattr(stat, "st_ino", 0)
        return {"size": int(size), "mtime": int(mtime), "inode": int(inode or 0)}
    except Exception:
        return None


def _read_vfs(vfs, path, limit):
    handle = None
    try:
        handle = vfs.File(path)
        return _bytes(handle.read(limit))
    finally:
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass


def _remote_original_path(item, source, force_transcode, *, config_read, hostname, wifi_mac,
                          vfs, connect=None, now=None):
    """Return a native NFS P7 path only for a current exact manifest entry."""
    # Keep these imports out of module import time: release tooling validates a
    # private config from a source checkout where Kodi's helper package does
    # not exist yet.
    from .. import native_originals
    from . import gate
    connect = connect or socket.create_connection
    now = int(time.time()) if now is None else int(now)
    config = load_config(config_read, hostname, wifi_mac)
    if config is None or not native_originals.eligible(item, source, "1", force_transcode):
        return None
    candidate = native_originals.map_native_path(item.get("Path"), config["mappings"])
    if candidate is None:
        return None
    mapped, host = candidate
    # Do the bounded network reachability test before either potentially slow
    # NFS VFS operation.  A VFS call itself is not safely cancellable in Kodi.
    if not _connect(host, connect):
        return None
    manifest = gate.load_manifest(lambda limit: _read_vfs(vfs, config["manifest_uri"], limit), now)
    original_stat = _vfs_stat(vfs, mapped)
    if not gate.allows_native(manifest, item.get("Path"), original_stat, source):
        return None
    # Reuse the maintained final availability check.  It also keeps existing
    # VFS existence semantics and fails closed if the NFS route disappears.
    return native_originals.available_native_path(candidate, vfs.exists, connect)


def _runtime_config_read(xbmcvfs):
    path = xbmcvfs.translatePath(
        "special://profile/addon_data/plugin.video.jellyfin/remote-originals.json")
    def read_limited(limit):
        with open(path, "rb") as handle:
            return handle.read(limit)
    return read_limited


def _runtime_wifi_mac():
    with open("/sys/class/net/wlan0/address", "rt", encoding="ascii") as handle:
        return handle.read().strip().lower()


def remote_original_path(item, source, force_transcode):
    """Kodi's three-argument optional native-original hook.

    It is intentionally an all-error-to-None boundary: missing private config,
    unavailable NFS, a changed platform interface, or a broken optional helper
    can never prevent the pre-existing HTTPS playback branch from running.
    """
    try:
        import xbmcvfs
        return _remote_original_path(
            item, source, force_transcode,
            config_read=_runtime_config_read(xbmcvfs), hostname=socket.gethostname(),
            wifi_mac=_runtime_wifi_mac(), vfs=xbmcvfs,
        )
    except Exception:
        return None
