#!/usr/bin/env python3
"""Prepare pinned server source and tests. Never deploys or contacts Jellyfin."""
import argparse
from pathlib import Path
import shutil
import subprocess

PIN = "ee91c75e777da41a9c4f4855e70adc604fbf2ef8"
UPSTREAM = "https://github.com/jellyfin/jellyfin.git"
HERE = Path(__file__).resolve().parent


def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True)


def prepare(destination, source=None):
    destination = Path(destination).resolve()
    # Deliberately refuse even an empty existing directory: never overwrite a
    # checkout or delete user files to make a build succeed.
    destination.mkdir(parents=True, exist_ok=False)
    run("git", "init", "-q", str(destination))
    repository = str(Path(source).resolve()) if source else UPSTREAM
    run("git", "fetch", "-q", "--depth=1", repository, PIN, cwd=destination)
    run("git", "checkout", "-q", "--detach", "FETCH_HEAD", cwd=destination)
    actual = run("git", "rev-parse", "HEAD", cwd=destination).stdout.strip()
    if actual != PIN:
        raise RuntimeError("Unexpected upstream revision")
    for patch in (HERE.parent.parent / "patches/jellyfin-12.1-onepace.patch", HERE / "continue-watching.patch"):
        path = str(patch)
        run("git", "apply", "--check", path, cwd=destination)
        run("git", "apply", path, cwd=destination)
    for filename, target in (
        ("BaseItemRepositoryResumeDedupTests.cs", "tests/Jellyfin.Server.Implementations.Tests/Item"),
    ):
        shutil.copyfile(HERE / filename, destination / target / filename)
    print(f"Prepared Jellyfin 12.1 source at {destination}; no build or deployment performed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new, nonexistent destination directory")
    parser.add_argument("--source", type=Path, help="optional local Git repository containing the exact pin")
    args = parser.parse_args()
    prepare(args.output, args.source)
