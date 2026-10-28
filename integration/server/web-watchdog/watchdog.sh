#!/usr/bin/env bash
# Narrow recovery for web 5xx with an independently healthy native API.
# Endpoint is deployment configuration: it must match the published listener.
set -u
JF=${JELLYFIN_WATCHDOG_URL:-http://127.0.0.1:8096}
NAME=jellyfin
STATE=${JELLYFIN_WATCHDOG_STATE:-/var/lib/jellyfin-web-watchdog}
LOG=${JELLYFIN_WATCHDOG_LOG:-/var/log/jellyfin-web-watchdog.log}
COOLDOWN=900

# No authenticated URL or shell interpolation is needed for these public probes.
case "$JF" in
  http://*|https://*) ;;
  *) echo 'web-watchdog: invalid endpoint scheme' >&2; exit 64 ;;
esac
case "$JF" in
  *'@'*|*'?'*|*'#'*|*[[:space:]]*) echo 'web-watchdog: endpoint must not contain credentials/query/whitespace' >&2; exit 64 ;;
esac
JF=${JF%/}
mkdir -p "$STATE"
# Serialize manual and timer invocations; never issue simultaneous restarts.
exec 9>"$STATE/lock"
flock -n 9 || exit 0
log(){ echo "$(date -Iseconds) $*" >> "$LOG"; }
probe(){ curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 10 "$1" 2>/dev/null || true; }
web=$(probe "$JF/web/index.html")
api=$(probe "$JF/health")
if [[ "$web" == 200 ]]; then
  date +%s > "$STATE/last_ok"
  exit 0
fi
if [[ "$api" != 200 ]]; then
  log "web=$web api=$api -> API also unavailable; no web-only recovery"
  exit 0
fi
case "$web" in
  5[0-9][0-9]) ;;
  *) log "web=$web api=200 -> not a web 5xx; no restart"; exit 0 ;;
esac
now=$(date +%s)
last=$(cat "$STATE/last_restart" 2>/dev/null || echo 0)
[[ "$last" =~ ^[0-9]+$ ]] || last=$now
# Also fail safe if the clock moved backwards after a reboot/time adjustment.
if (( now < last || now - last < COOLDOWN )); then
  log 'web-only 5xx within restart cooldown; no restart'
  exit 0
fi
# Re-probe immediately before mutation: transient one-request errors must not
# cause a restart after the Web UI has already recovered.
[[ $(probe "$JF/web/index.html") =~ ^5[0-9][0-9]$ && $(probe "$JF/health") == 200 ]] || exit 0
echo "$now" > "$STATE/last_restart"
log "persistent web-only 5xx; restarting only container $NAME"
if docker restart "$NAME" >> "$LOG" 2>&1; then
  log 'container restart completed'
else
  log 'container restart failed; retained cooldown and diagnostic evidence'
  exit 1
fi
