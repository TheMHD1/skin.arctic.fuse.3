"""Run reviewed artwork and finalize its durable ledger without hiding errors."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

ROOT = Path('/data/config/iptv-venom')
WORKER = ROOT / 'venom-reviewed-artwork.py'
SOURCE_LEDGER = ROOT / 'reviewed-artwork-applied.json'
DESTINATION_LEDGER = Path('/data/config/dispatcharr/venom-artwork-applied.json')
PARTIAL_EXIT = 75
MAX_LEDGER_BYTES = 4 * 1024 * 1024
WORKER_TIMEOUT_SECONDS = 17 * 60
FINALIZER_TIMEOUT_SECONDS = 60
OVERRIDE_COMMAND = (
    '/usr/bin/docker', 'exec', 'dispatcharr', 'python', 'manage.py', 'shell', '-c',
    "exec(open('/data/venom-artwork-overrides.py').read())",
)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate ledger key')
        value[key] = item
    return value


def atomic_ledger_copy(source: Path, destination: Path) -> None:
    data = source.read_bytes()
    if not data or len(data) > MAX_LEDGER_BYTES:
        raise ValueError('ledger is empty or oversized')
    parsed = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_object)
    if not isinstance(parsed, dict):
        raise ValueError('ledger root must be an object')
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{destination.name}.', dir=destination.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def run_artwork(
    *,
    limit: int,
    missing_only: bool,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    source_ledger: Path = SOURCE_LEDGER,
    destination_ledger: Path = DESTINATION_LEDGER,
) -> int:
    command = ['/usr/bin/python3', str(WORKER), '--apply', '--limit', str(limit)]
    if missing_only:
        command.append('--missing-only')
    worker = runner(command, timeout=WORKER_TIMEOUT_SECONDS, check=False)
    if worker.returncode not in {0, PARTIAL_EXIT}:
        return worker.returncode if worker.returncode > 0 else 1
    original_status = worker.returncode
    try:
        atomic_ledger_copy(source_ledger, destination_ledger)
        finalizer = runner(list(OVERRIDE_COMMAND), timeout=FINALIZER_TIMEOUT_SECONDS, check=False)
        if finalizer.returncode != 0:
            return 1
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, subprocess.SubprocessError):
        return 1
    return original_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, required=True)
    parser.add_argument('--missing-only', action='store_true')
    args = parser.parse_args(argv)
    if not 0 <= args.limit <= 2000:
        parser.error('--limit must be between 0 and 2000')
    return run_artwork(limit=args.limit, missing_only=args.missing_only)


if __name__ == '__main__':
    raise SystemExit(main())
