#!/bin/sh
# Called by the private, hash-guarded post-sub integration before AI work.
# Do not source post-sub.sh here: it contains private Jellyfin credentials.
set -eu
root=${SUBTITLE_SCRIPT_ROOT:-/config/scripts}
video=$1
subtitle=$2
exec python3 "$root/subtitle-raw-arrival.py" arrival "$video" "$subtitle" --root "$root"
