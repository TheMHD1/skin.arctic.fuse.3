#!/usr/bin/env python3
"""Verify preserved release source in a clone or Git-free source archive.

Maintainers: stage the reviewed file set, then --write to regenerate the source
inventory. This hashes files only; it never changes Kodi or server runtime state.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "integration/release/source-manifest.json"
EXTRA = {
    ".gitignore", ".github/workflows/integration.yml", "addon.xml", "LICENSE.txt", "README.md", "AGENTS.md",
    "1080i/Includes_Search.xml", "shortcuts/generator/data/setup/search_path.xml",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    return sorted(n for n in names if n and (n.startswith("integration/") or n in EXTRA)
                  and n != MANIFEST.relative_to(ROOT).as_posix())


def write():
    payload = {
        "schema": 1,
        "release": "2026-09-22-r6-preservation",
        "meaning": "Reviewed source bytes, not a runtime credential/settings backup or proof of deployment",
        "status": {
            "local_kodi_r6": "deployed-and-accepted",
            "remote_kodi_r6": "source-tested-not-deployed",
            "remote_original_p7": "pending",
            "coreelec_update": "held-not-authorized",
            "provider_403_retry": "deployed-fixture-tested-not-live-recovery-proven",
            "dovi_companion_provenance": "known-gap-not-fixed",
        },
        "upstream": {
            "jellyfin-kodi": "a1aeda1352eb49c16d8da877121ea2068a7a7508",
            "jellyfin-server": "ee91c75e777da41a9c4f4855e70adc604fbf2ef8",
        },
        "files": {n: digest(ROOT / n) for n in sources()},
    }
    MANIFEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Recorded {len(payload['files'])} source hashes; stage the manifest with this reviewed release.")


def verify():
    # Verify listed source bytes, not the absence of unrelated local files.
    # Public archive hygiene is a separate reviewed staging/secret-scan step.
    payload = json.loads(MANIFEST.read_text())
    if payload.get("schema") != 1 or not payload.get("files"):
        raise SystemExit("Invalid or empty source inventory")
    errors = []
    for name, expected in payload["files"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"Unsafe inventory path: {name}")
            continue
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            errors.append(f"Missing/non-regular source: {name}")
        elif digest(path) != expected:
            errors.append(f"Changed source: {name}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"PASS: {len(payload['files'])} preserved source files match {payload['release']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="regenerate from explicitly staged/tracked sources")
    args = parser.parse_args()
    write() if args.write else verify()
