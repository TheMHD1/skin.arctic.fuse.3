"""Inspect, but never install, the TMDb Helper artifact required by Arctic 3.4.10."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET
import zipfile

TMDB_ID = "plugin.video.themoviedb.helper"
TMDB_VERSION = "6.19.1"
TMDB_COMMIT = "61917067582cb860ace3c3013a80eea17724c637"
MINIMUM_TMDB = (6, 17, 9)
MINIMUM_SKINVARIABLES = (2, 2, 9)
TMDB_REQUIREMENTS = {
    "script.module.requests": "2.9.1",
    "script.module.pil": "1.1.7",
    "script.module.addon.signals": "0.0.6",
    "script.module.jurialmunkey": "0.2.35",
    "script.module.infotagger": "0.1.0",
    "script.module.qrcode": "6.1.0",
}


def version(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except (AttributeError, ValueError):
        raise ValueError("invalid addon version") from None


def addon_xml_from_zip(path: Path) -> bytes:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        for name in names:
            member = PurePosixPath(name)
            if member.is_absolute() or ".." in member.parts:
                raise ValueError("unsafe addon archive member")
        candidates = [name for name in names if name.endswith("/addon.xml") and len(PurePosixPath(name).parts) == 2]
        if len(candidates) != 1:
            raise ValueError("artifact needs exactly one top-level addon.xml")
        return archive.read(candidates[0])


def review_tmdb_artifact(path: Path) -> dict:
    path = Path(path)
    xml = addon_xml_from_zip(path) if path.suffix == ".zip" else (path / "addon.xml").read_bytes()
    addon = ET.fromstring(xml)
    if addon.tag != "addon" or addon.get("id") != TMDB_ID:
        raise ValueError("not a TMDb Helper artifact")
    if addon.get("version") != TMDB_VERSION:
        raise ValueError("unreviewed TMDb Helper version")
    requirements = {item.get("addon"): item.get("version") for item in addon.findall("./requires/import")}
    if {key: requirements.get(key) for key in TMDB_REQUIREMENTS} != TMDB_REQUIREMENTS:
        raise ValueError("TMDb Helper dependency set differs from reviewed v6.19.1 source")
    return {"id": TMDB_ID, "version": TMDB_VERSION, "commit": TMDB_COMMIT,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
            "requirements": TMDB_REQUIREMENTS}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    print(json.dumps(review_tmdb_artifact(parser.parse_args().artifact), indent=2, sort_keys=True))
