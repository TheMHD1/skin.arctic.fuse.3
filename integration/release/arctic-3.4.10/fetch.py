"""Fetch the only upstream checkout accepted by the 3.4.10 candidate tests."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from overlay import UPSTREAM_COMMIT

UPSTREAM_URL = "https://github.com/jurialmunkey/skin.arctic.fuse.3.git"


def fetch(output: Path) -> Path:
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError("upstream output must be absent or empty")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(output)], check=True)
    subprocess.run(["git", "remote", "add", "origin", UPSTREAM_URL], cwd=output, check=True)
    subprocess.run(["git", "fetch", "-q", "--depth=1", "origin", UPSTREAM_COMMIT], cwd=output, check=True)
    subprocess.run(["git", "checkout", "-q", "--detach", "FETCH_HEAD"], cwd=output, check=True)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=output, text=True).strip()
    if actual != UPSTREAM_COMMIT:
        raise RuntimeError("fetched unexpected Arctic source")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=output, text=True):
        raise RuntimeError("fetched Arctic source is not clean")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    print(fetch(parser.parse_args().output))
