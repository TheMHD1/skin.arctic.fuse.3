#!/usr/bin/env bash
# Source-only candidate acceptance.  No live provider/data/config mount is used.
set -euo pipefail

candidate_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir=${1:?usage: $0 /path/to/fresh-Dispatcharr-v0.33.0-checkout}

test "$(git -C "$source_dir" rev-parse HEAD)" = \
  2fa13a6707bdf0dae87e0c494bcd3ca282cdeb3e
test -z "$(git -C "$source_dir" status --porcelain)" || {
  echo "refusing dirty source checkout: fixture applies a patch in place" >&2
  exit 2
}
git -C "$source_dir" apply --check "$candidate_dir/dispatcharr-0.33-habibi.patch"
git -C "$source_dir" apply "$candidate_dir/dispatcharr-0.33-habibi.patch"

# AIO runs its own disposable PostgreSQL/Redis.  Starting the stock entrypoint
# avoids silently falling back to a host database.  The temporary data mount is
# deliberately empty and removed on exit.
fixture_name="dispatcharr-033-fixture-$$"
fixture_data=$(mktemp -d)
chmod 0777 "$fixture_data"
cleanup() {
  docker rm -f "$fixture_name" >/dev/null 2>&1 || true
  # AIO initializes PostgreSQL as its service user, so host-side cleanup can
  # lack permission. Use the already pinned image as root with no network, then
  # remove only this mktemp directory. Never touch caller data or named volumes.
  docker run --rm --network none --user 0 --entrypoint /bin/sh \
    -v "$fixture_data:/fixture:rw" \
    ghcr.io/dispatcharr/dispatcharr:0.33.0@sha256:96bc548978c68e684677da7895692eeeefb7f0b2edfa38311dac2b702c61d236 \
    -c 'find /fixture -mindepth 1 -delete' >/dev/null 2>&1 || true
  rmdir "$fixture_data" >/dev/null 2>&1 || true
}
trap cleanup EXIT
# The AIO entrypoint runs collectstatic, so the disposable source checkout
# must be writable. It is a throwaway clone, never the maintained checkout.
docker run -d --name "$fixture_name" \
  --network none \
  -e DJANGO_SECRET_KEY=dispatcharr-isolated-fixture-only \
  -e DISPATCHARR_ENV=aio -e DISPATCHARR_LOG_LEVEL=warning \
  -v "$source_dir:/app" -v "$fixture_data:/data" \
  ghcr.io/dispatcharr/dispatcharr:0.33.0@sha256:96bc548978c68e684677da7895692eeeefb7f0b2edfa38311dac2b702c61d236 >/dev/null
for _ in $(seq 1 30); do
  docker exec "$fixture_name" sh -lc 'pg_isready -q && redis-cli ping | grep -qx PONG' && break
  sleep 1
done
docker exec "$fixture_name" sh -lc \
  'cd /app && python manage.py test apps.m3u.tests.test_credential_transform apps.channels.tests.test_ts_proxy_keepalive apps.proxy.live_proxy.tests.test_xc_hls apps.proxy.live_proxy.tests.test_habibi_033_regressions apps.proxy.vod_proxy.tests.test_xc_head_metadata'

# Version-controlled static transport contract for the retained nginx config.
nginx="$candidate_dir/../dispatcharr-nginx.conf"
grep -A8 'location /live/' "$nginx" | grep -qx '        uwsgi_buffering off;'
grep -A8 'location /live/' "$nginx" | grep -qx '        uwsgi_read_timeout 300s;'
grep -A8 'location /live/' "$nginx" | grep -qx '        uwsgi_send_timeout 300s;'
