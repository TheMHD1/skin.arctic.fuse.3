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
    ".gitignore", ".gitattributes", ".github/workflows/integration.yml", "addon.xml", "LICENSE.txt", "README.md", "AGENTS.md",
    "1080i/Includes_Search.xml", "shortcuts/generator/data/setup/search_path.xml",
    "1080i/Includes_Labels.xml", "1080i/Includes_Layouts.xml", "1080i/Includes_Objects.xml",
    "shortcuts/generator/data/base/search_selector.xml",
    "shortcuts/generator/data/base/search_selector_wall.xml",
    "shortcuts/generator/data/base/search_selector_venom.xml",
    "shortcuts/generator/data/base/search_selector_wall_venom.xml",
    "shortcuts/skinvariables-generator.json",
    "shortcuts/skinvariables-shortcut-searchwidgets.json",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    return sorted(n for n in names if n and (n.startswith("integration/") or n in EXTRA)
                  and n != MANIFEST.relative_to(ROOT).as_posix())


def relevant(name):
    return name.startswith("integration/") or name in EXTRA


def unstaged_sources():
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    unstaged = subprocess.check_output(
        ["git", "diff", "--name-only", "-z"], cwd=ROOT).decode().split("\0")
    manifest_name = MANIFEST.relative_to(ROOT).as_posix()
    return sorted({name for name in untracked + unstaged
                   if name and relevant(name) and name != manifest_name})


def write():
    pending = unstaged_sources()
    if pending:
        raise SystemExit("Review and stage sources before recording them:\n" + "\n".join(pending))
    payload = {
        "schema": 1,
        "release": "2026-09-23-library-home-ratings",
        "meaning": "Reviewed source bytes, not a runtime credential/settings backup or proof of deployment",
        "status": {
            "local_kodi_r6": "deployed-and-accepted",
            "local_kodi_r7": "deployed-source-and-live-api-accepted",
            "remote_kodi_r6": "source-tested-not-deployed",
            "remote_kodi_r7": "not-deployed",
            "jellyfin_nextup": "deployed-26-account-readonly-audit-passed",
            "web_search": "deployed-mobile-browser-verified",
            "web_library_home": "deployed-owned-only-favorites-recently-watched-and-top-rated-browser-verified",
            "my_media_order": "supported-preference-updated-and-verified-26-accounts",
            "imdb_ratings": "deployed-optional-fail-open-201-of-202-distinct-ids",
            "kodi_search_ratings": "deployed-device-api-30-ratings-55ms-physical-badge-visual-pending",
            "request_ready": "timer-deployed-no-real-completion-delivery-yet",
            "remote_original_p7": "pending",
            "coreelec_update": "local-am9-nightly-20260922-hybrid-verified-two-boots-physical-av-pending",
            "provider_403_retry": "deployed-fixture-tested-not-live-recovery-proven",
            "dovi_companion_provenance": "known-gap-not-fixed",
        },
        "upstream": {
            "jellyfin-kodi": "a1aeda1352eb49c16d8da877121ea2068a7a7508",
            "jellyfin-server": "ee91c75e777da41a9c4f4855e70adc604fbf2ef8",
            "jellyfin-web": "fae41f33eb7cd636a9ef68984adb82bb247a6e1b",
        },
        "files": {n: digest(ROOT / n) for n in sources()},
    }
    MANIFEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Recorded {len(payload['files'])} source hashes; stage the manifest with this reviewed release.")


def verify():
    # Git-free source archives remain supported; in a clone also enforce exact
    # tracked inventory completeness and reject overlooked untracked sources.
    payload = json.loads(MANIFEST.read_text())
    if payload.get("schema") != 1 or not payload.get("files"):
        raise SystemExit("Invalid or empty source inventory")
    errors = []
    if (ROOT / ".git").exists():
        tracked = set(sources())
        listed = set(payload["files"])
        errors.extend(f"Unlisted tracked source: {name}" for name in sorted(tracked - listed))
        errors.extend(f"No longer tracked source: {name}" for name in sorted(listed - tracked))
        errors.extend(f"Unstaged source: {name}" for name in unstaged_sources())
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
