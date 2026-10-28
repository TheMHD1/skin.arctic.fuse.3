"""Verify the exact TMDb Helper artifact and installed payload used by Arctic."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import xml.etree.ElementTree as ET
import zipfile

TMDB_ID = "plugin.video.themoviedb.helper"
TMDB_VERSION = "6.19.2"
TMDB_COMMIT = "3a515987b0405d6e2298081edb71f8ab3099ecff"
TMDB_REPOSITORY_COMMIT = "1fd8db862c63066c2bd51df3183f2839874c9fff"
TMDB_ARTIFACT_SHA256 = "686a0f412a3183ea46c00b958e526e4b3e76bb44a902bea1aa305aa23b112560"
TMDB_PAYLOAD_SHA256 = "f59cd113967da3c2ad6c20d7eca853d73948a716339ea18d9c419967f8e8881d"
TMDB_PAYLOAD_FILE_COUNT = 715
MINIMUM_TMDB = (6, 17, 9)
MINIMUM_SKINVARIABLES = (2, 2, 9)
TMDB_REQUIREMENTS = {
    "xbmc.python": "3.0.1",
    "script.module.requests": "2.9.1",
    "script.module.pil": "1.1.7",
    "script.module.addon.signals": "0.0.6",
    "script.module.jurialmunkey": "0.2.35",
    "script.module.infotagger": "0.1.0",
    "script.module.qrcode": "6.1.0",
}
_PYC = re.compile(r"^(?P<stem>.+)\.cpython-\d+(?:\.opt-\d+)?\.pyc$")


def version(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except (AttributeError, ValueError):
        raise ValueError("invalid addon version") from None


def reviewed_binding() -> dict:
    """Return the complete immutable provenance accepted by a fresh stage."""
    return {
        "id": TMDB_ID,
        "version": TMDB_VERSION,
        "commit": TMDB_COMMIT,
        "repository_commit": TMDB_REPOSITORY_COMMIT,
        "artifact_sha256": TMDB_ARTIFACT_SHA256,
        "payload_sha256": TMDB_PAYLOAD_SHA256,
        "payload_file_count": TMDB_PAYLOAD_FILE_COUNT,
        "requirements": dict(TMDB_REQUIREMENTS),
    }


def require_reviewed_binding(value: object) -> dict:
    expected = reviewed_binding()
    if value != expected:
        raise ValueError("TMDb Helper stage provenance differs from reviewed artifact")
    return expected


def _payload_hash(entries: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relative, data in sorted(entries.items()):
        name = relative.encode("utf-8")
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _zip_payload(blob: bytes) -> dict[str, bytes]:
    entries: dict[str, bytes] = {}
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as error:
        raise ValueError("invalid TMDb Helper ZIP") from error
    with archive:
        infos = archive.infolist()
        if len([item.filename for item in infos]) != len(set(item.filename for item in infos)):
            raise ValueError("duplicate TMDb Helper archive member")
        for info in infos:
            name = info.filename
            if "\\" in name:
                raise ValueError("unsafe TMDb Helper archive member")
            member = PurePosixPath(name)
            canonical = str(member)
            if (not name or member.is_absolute() or ".." in member.parts or
                    name.rstrip("/") != canonical or not member.parts or
                    member.parts[0] != TMDB_ID):
                raise ValueError("unsafe TMDb Helper archive member")
            unix_mode = info.external_attr >> 16
            if stat.S_ISLNK(unix_mode):
                raise ValueError("symlink in TMDb Helper archive")
            if info.is_dir():
                continue
            if stat.S_IFMT(unix_mode) and not stat.S_ISREG(unix_mode):
                raise ValueError("special file in TMDb Helper archive")
            if len(member.parts) < 2:
                raise ValueError("file outside TMDb Helper addon root")
            relative = str(PurePosixPath(*member.parts[1:]))
            entries[relative] = archive.read(info)
    return entries


def _requirements(xml: bytes) -> dict[str, str]:
    try:
        addon = ET.fromstring(xml)
    except ET.ParseError as error:
        raise ValueError("invalid TMDb Helper addon.xml") from error
    if addon.tag != "addon" or addon.get("id") != TMDB_ID:
        raise ValueError("not a TMDb Helper artifact")
    if addon.get("version") != TMDB_VERSION:
        raise ValueError("unreviewed TMDb Helper version")
    imports = addon.findall("./requires/import")
    pairs = [(item.get("addon"), item.get("version")) for item in imports]
    if any(not key or not value for key, value in pairs) or len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("invalid or duplicate TMDb Helper dependency")
    requirements = dict(pairs)
    if requirements != TMDB_REQUIREMENTS:
        raise ValueError("TMDb Helper dependency set differs from reviewed v6.19.2 source")
    return requirements


def review_tmdb_artifact(path: Path) -> dict:
    """Accept only the official omega ZIP pinned by byte and payload hashes."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".zip":
        raise ValueError("TMDb Helper artifact must be one regular ZIP")
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != TMDB_ARTIFACT_SHA256:
        raise ValueError("unreviewed TMDb Helper ZIP digest")
    entries = _zip_payload(blob)
    if len(entries) != TMDB_PAYLOAD_FILE_COUNT or _payload_hash(entries) != TMDB_PAYLOAD_SHA256:
        raise ValueError("unreviewed TMDb Helper payload")
    addon_xml = entries.get("addon.xml")
    if addon_xml is None:
        raise ValueError("TMDb Helper archive lacks addon.xml")
    _requirements(addon_xml)
    return reviewed_binding()


def _runtime_pyc(relative: Path, live_files: set[str]) -> bool:
    if len(relative.parts) < 2 or relative.parts[-2] != "__pycache__":
        return False
    match = _PYC.fullmatch(relative.name)
    if not match:
        return False
    source = relative.parent.parent / (match.group("stem") + ".py")
    return str(source) in live_files


def review_live_tmdb(path: Path, binding: object) -> dict:
    """Verify installed source, tolerating only Python's derived cache files."""
    require_reviewed_binding(binding)
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("installed TMDb Helper is not a regular directory")
    entries: dict[str, bytes] = {}
    pyc: list[Path] = []
    directories: set[str] = set()
    for current in sorted(path.rglob("*")):
        if current.is_symlink():
            raise ValueError("symlink in installed TMDb Helper")
        if current.is_dir():
            directories.add(str(current.relative_to(path)))
            continue
        if not current.is_file():
            raise ValueError("special file in installed TMDb Helper")
        relative = current.relative_to(path)
        if relative.suffix == ".pyc" and relative.parent.name == "__pycache__":
            pyc.append(relative)
            continue
        entries[str(relative)] = current.read_bytes()
    live_files = set(entries)
    if any(not _runtime_pyc(relative, live_files) for relative in pyc):
        raise ValueError("unreviewed Python cache file in installed TMDb Helper")
    expected_directories: set[str] = set()
    for relative in [Path(name) for name in live_files] + pyc:
        parent = relative.parent
        while parent != Path("."):
            expected_directories.add(str(parent))
            parent = parent.parent
    if directories != expected_directories:
        raise ValueError("unreviewed directory in installed TMDb Helper")
    if len(entries) != TMDB_PAYLOAD_FILE_COUNT or _payload_hash(entries) != TMDB_PAYLOAD_SHA256:
        raise ValueError("installed TMDb Helper payload differs from reviewed source")
    addon_xml = entries.get("addon.xml")
    if addon_xml is None:
        raise ValueError("installed TMDb Helper lacks addon.xml")
    _requirements(addon_xml)
    return {**reviewed_binding(), "runtime_pyc_files": len(pyc)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    print(json.dumps(review_tmdb_artifact(parser.parse_args().artifact), indent=2, sort_keys=True))
