#!/usr/bin/env python3
"""Restore only the two existing read-only AM9 exports once their ZFS source exists."""
import argparse
import configparser
import json
import os
import socket
import subprocess
import time

ROOT = "/tank/media"
DATASET = "tank/media"
UNITS = {name: "srv-ugoos\\x2dmedia-%s.mount" % name for name in ("movies", "shows")}


def run(args):
    return subprocess.check_output(args, text=True, timeout=20)


def info(path, runner=run):
    try:
        data = json.loads(runner(["findmnt", "--json", "--mountpoint", path,
                                  "--output", "TARGET,SOURCE,FSTYPE,OPTIONS"]))
    except subprocess.CalledProcessError as error:
        if error.returncode == 1:
            return None
        raise
    rows = data.get("filesystems", [])
    if len(rows) != 1 or rows[0].get("target") != path:
        raise RuntimeError("Ambiguous or nonexact mount")
    return rows[0]


def ready(runner=run):
    row = info(ROOT, runner)
    if row is None:
        return False
    if row.get("source") != DATASET or row.get("fstype") != "zfs":
        raise RuntimeError("Unexpected source filesystem; refusing restoration")
    return True


def restore(runner=run):
    if not ready(runner):
        raise RuntimeError("Source not mounted")
    # Validate both units before starting either. Preserve the original assertion.
    for name, unit in UNITS.items():
        # Active bind-mount properties report the kernel's ZFS source/type,
        # not the unit's configured What/Type. Validate the actual unit source.
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(runner(["systemctl", "cat", unit]))
        values = config["Mount"]
        if (config["Unit"].get("AssertPathIsMountPoint") != ROOT
                or values.get("What") != ROOT + "/" + name
                or values.get("Where") != "/srv/ugoos-media/" + name
                or values.get("Type") != "none"
                or not {"bind", "ro"}.issubset(set(values.get("Options", "").split(",")))
                or "rw" in values.get("Options", "").split(",")):
            raise RuntimeError("Unexpected export unit; review required")
    runner(["systemctl", "start", *UNITS.values()])
    for name in UNITS:
        row = info("/srv/ugoos-media/" + name, runner)
        if (not row or row.get("source") != DATASET + "[/" + name + "]"
                or row.get("fstype") != "zfs"
                or "ro" not in row.get("options", "").split(",")):
            raise RuntimeError("Export not mounted read-only from the expected source")
    # Its existing RequiresMountsFor dependency can leave it skipped at boot too.
    # Starting an already-active daemon is a no-op, not a restart/export reload.
    runner(["systemctl", "start", "nfs-server.service"])
    print("Both existing read-only AM9 media mounts verified")


def wait_and_restore(runner=run, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + 60
    while not ready(runner):
        if clock() >= deadline:
            raise RuntimeError("Source readiness timeout; no mount attempted")
        sleep(2)
    restore(runner)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or socket.gethostname() != args.host:
        raise SystemExit("Exact private deployment host and root required")
    wait_and_restore()
