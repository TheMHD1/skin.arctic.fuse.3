#!/usr/bin/env bash
# Host-side P7->P8.1 compatibility-copy processor (HARDENED v5,
# NVMe-accelerated). Arr-LXC, driven by dovi-convert.timer.
#
# The Profile 7 source is the immutable master. This worker stream-copies the base
# layer (NO re-encode, lossless), discards the enhancement layer, rewrites the RPU
# to P8.1, and writes a separate file under /data/media/compatibility/dovi-p8.
# It never renames, replaces, truncates, or otherwise mutates the source master.
#
# TIERING (v3): the heavy scratch passes (HEVC extract + dovi_tool convert) run on the
# NVMe fast tier (/fast, if mounted) instead of the HDD, then the final remux is written
# straight to a hidden temp on the media volume and atomically renamed into place. This
# keeps ~200GB of per-file churn off the spinning disks. If /fast is not mounted it
# transparently falls back to the on-HDD scratch dir, so it is always safe to run.
#
# Safety:
#   * single-instance flock
#   * reboot-safe: work snapshot (queue.work) checkpointed after every file
#   * only DV-P7 MKVs touched; disk-space precheck on the chosen scratch tier
#   * compatibility copy published ONLY if output passes ALL of: size>=60% of source, strict P8.1
#     identification, exact video-packet preservation, non-video track preservation,
#     clean full-stream timestamp probe, duration parity, and decoder smoke tests.
#     Atomic rename => no partial file ever seen; source master remains untouched.
#   * after success, atomically trigger the same-path Jellyfin view reconciler
# MODE=dryrun skips conversion but still mutates queue/log/scratch state.
# This sanitized source is a preservation reference, not a commissioning tool.
# Never execute it against real host paths for a test; use bash -n only.
set -uo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin   # include /usr/local/bin for dovi_tool
# Keep deterministic tool output while preserving Unicode media and track names.
# Plain C made mediainfo treat Unicode paths as missing and made mkvmerge emit
# invalid/truncated JSON for Unicode track titles.  C.UTF-8 ships with Debian.
export LC_ALL=C.UTF-8 LANG=C.UTF-8

MODE="${MODE:-live}"
DIR=/data/config/_dovi
Q="$DIR/compat-queue.txt"
WQ="$DIR/compat-queue.work"
HDD_SCRATCH="$DIR/tmp"           # fallback scratch (on the HDD-backed mergerfs)
FAST_SCRATCH="/fast/_dovi_tmp"   # preferred scratch (NVMe branch mounted into this LXC)
COMPAT_ROOT="/data/media/compatibility/dovi-p8"
LOG="$DIR/fel-to-p8.log"
MARGIN_PCT=110                   # generic free-space margin
SCRATCH_PCT=160                  # NVMe scratch needs ~1.5x source (two HEVC essences)
JF="${JELLYFIN_URL:-http://jellyfin:8096}"
JK="[REDACTED: runtime Jellyfin API token]"
NTFY_URL="${NTFY_URL:-http://ntfy:8090}"; NTFY_TOPIC="${NTFY_TOPIC:-media-alerts}"
LOG_MAX=5242880                  # trim log when it exceeds ~5MB
mkdir -p "$DIR" "$HDD_SCRATCH" "$COMPAT_ROOT/movies" "$COMPAT_ROOT/shows"
log(){ printf '%s %s\n' "$(date -Is)" "$*" >> "$LOG"; }
ntfy(){ curl -s -m 10 -H "Title: DoVi convert" -H "Tags: warning" -d "$1" "$NTFY_URL/$NTFY_TOPIC" >/dev/null 2>&1 || true; }

exec 9>/run/dovi-process-queue.lock; flock -n 9 || exit 0   # lock on LOCAL fs — mergerfs/FUSE does not serialize flock reliably

# Reconciler appends and worker queue-drains share this short critical section.
# The conversion flock protects WQ processing; this separate local lock makes
# Q -> WQ snapshotting and every later requeue atomic against a reconciler run.
QUEUE_LOCK="/run/dovi-compat-queue.lock"
queue_append(){
  local queued_path="$1"
  exec 8>"$QUEUE_LOCK"
  flock 8
  printf '%s\n' "$queued_path" >> "$Q"
  flock -u 8
  exec 8>&-
}

# keep the log bounded
if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG" 2>/dev/null || echo 0)" -gt "$LOG_MAX" ]; then
  tail -n 2000 "$LOG" > "$LOG.trim" 2>/dev/null && mv -f "$LOG.trim" "$LOG"
fi

# flock guarantees we are the only instance -> any leftover job dirs are crash debris
rm -rf "$HDD_SCRATCH"/job.* 2>/dev/null
[ -d "$FAST_SCRATCH" ] && rm -rf "$FAST_SCRATCH"/job.* 2>/dev/null

for t in mediainfo ffmpeg ffprobe mkvmerge dovi_tool jq curl; do
  command -v "$t" >/dev/null || { log "FATAL missing tool: $t"; ntfy "FATAL: missing tool $t on arr-lxc — DoVi conversions halted"; exit 1; }
done
converted=0; failed=0

# pick scratch tier for a given source size: NVMe if mounted and roomy, else HDD
pick_scratch(){   # $1 = source size bytes; echoes chosen dir
  local need=$(( $1 * SCRATCH_PCT / 100 ))
  # Security hardening deliberately exposes only scoped FastData mounts.  Test
  # the dedicated DoVi mount itself rather than its unmounted /fast parent.
  if mountpoint -q "$FAST_SCRATCH" 2>/dev/null; then
    local ff; ff=$(df -P --block-size=1 "$FAST_SCRATCH" 2>/dev/null | awk 'NR==2{print $4}')
    if [ -n "$ff" ] && [ "$ff" -ge "$need" ]; then echo "$FAST_SCRATCH"; return; fi
  fi
  echo "$HDD_SCRATCH"
}

# --- Build/refresh the reboot-safe work snapshot -------------------------------------
exec 8>"$QUEUE_LOCK"
flock 8
touch "$WQ"
if [ -s "$Q" ]; then cat "$Q" >> "$WQ" 2>/dev/null; : > "$Q"; fi
flock -u 8
exec 8>&-
sort -u "$WQ" -o "$WQ" 2>/dev/null
[ -s "$WQ" ] || { rm -f "$WQ"; exit 0; }

dur(){ ffprobe -v error -show_entries format=duration -of csv=p=0 "$1" 2>/dev/null | cut -d. -f1; }
vpackets(){ ffprobe -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of default=nw=1:nk=1 "$1" 2>/dev/null | head -1; }
tracksig(){
  mkvmerge -J "$1" 2>/dev/null | jq -c '[.tracks[] | select(.type != "video") |
    [.type,.properties.codec_id,(.properties.language // "und"),
     (.properties.default_track // false),(.properties.forced_track // false)]]' 2>/dev/null
}
decode_smoke(){ # file, position seconds; video + first audio (if present)
  ffmpeg -nostdin -v error -ss "$2" -t 2 -i "$1" -map 0:v:0 -map '0:a:0?' -sn -f null - >/dev/null 2>&1
}
pop_done(){ grep -vxF -- "$1" "$WQ" > "$WQ.tmp" 2>/dev/null; mv -f "$WQ.tmp" "$WQ" 2>/dev/null || true; }

companion_publish(){
  local result
  result=$(python3 "$DIR/dovi-import-fast.py" --config "$DIR/fast-import.json" --companion-ready "$1" 2>/dev/null)
  if [ "$?" = 0 ]; then
    log "companion publication handoff: $result"
  else
    log "companion publication handoff unavailable; periodic repair retained"
  fi
}

# Persistent cooldown also covers external reconciliation re-enqueues.
RETRY_HELPER="$DIR/dovi-retry-state.py"
record_failure(){
  local rc
  python3 "$RETRY_HELPER" failure "$FILE" --signature "$SOURCE_SIGNATURE"
  rc=$?
  if [ "$rc" = 76 ]; then
    log "source changed during failed attempt; requeue replacement: $FILE"
    queue_append "$FILE"
    return 0
  fi
  [ "$rc" = 0 ] || { log "ERROR cannot persist conversion failure; retaining snapshot"; exit 1; }
  python3 "$RETRY_HELPER" check "$FILE"
  rc=$?
  case "$rc" in
    0) queue_append "$FILE"; log "requeued for one retry: $FILE";;
    75) log "conversion deferred for 24h after two failures: $FILE";;
    *) log "ERROR cannot read conversion cooldown; retaining snapshot"; exit 1;;
  esac
}

# --- Drain the snapshot one file at a time, checkpointing after each ------------------
while IFS= read -r FILE; do
  [ -n "$FILE" ] || continue
  if ! [ -f "$FILE" ]; then log "skip missing: $FILE"; pop_done "$FILE"; continue; fi
  case "$FILE" in *.mkv) ;; *) log "skip non-mkv: $FILE"; pop_done "$FILE"; continue;; esac

  case "$FILE" in
    /data/media/movies/*)
      REL="${FILE#/data/media/movies/}"
      DEST="$COMPAT_ROOT/movies/${REL%.mkv} - P8.1 Compatibility.mkv"
      ;;
    /data/media/shows/*)
      REL="${FILE#/data/media/shows/}"
      DEST="$COMPAT_ROOT/shows/${REL%.mkv} - P8.1 Compatibility.mkv"
      ;;
    *)
      log "skip path outside supported master roots: $FILE"
      pop_done "$FILE"
      continue
      ;;
  esac

  DV="$(mediainfo --Output='Video;%HDR_Format%|%HDR_Format_Profile%' "$FILE" 2>/dev/null)"
  case "$DV" in
    *dvhe.07*|*"Profile 7"*|*"profile 7"*) ;;
    *) log "skip not-P7 [$DV]: $(basename "$FILE")"; pop_done "$FILE"; continue;;
  esac

  if [ "$MODE" != "live" ]; then log "DRYRUN P7 (would create $DEST) [$DV]: $FILE"; pop_done "$FILE"; continue; fi

  if [ -f "$DEST" ]; then
    EXISTING="$(mediainfo --Output='Video;%HDR_Format_Profile%' "$DEST" 2>/dev/null)"
    if printf '%s' "$EXISTING" | grep -Eqi 'dvhe\.08|profile 8'; then
      log "skip valid compatibility copy already exists [$EXISTING]: $DEST"
    else
      log "ERROR refusing to overwrite invalid existing compatibility file [$EXISTING]: $DEST"
      ntfy "Manual review required: invalid compatibility file already exists: $(basename "$DEST")"
      failed=$((failed+1))
    fi
    pop_done "$FILE"
    continue
  fi

  SZI=$(stat -c%s "$FILE")
  # Check scratch capacity before the expensive full-file packet count.  The
  # old order reread a large remux every five minutes when scratch was full.
  SCR="$(pick_scratch "$SZI")"
  FREE=$(df -P --block-size=1 "$SCR" | awk 'NR==2{print $4}')
  if [ "$FREE" -lt $(( SZI * MARGIN_PCT / 100 )) ]; then
    log "SKIP low disk before packet scan on scratch $SCR (free=$((FREE/1024/1024))MB), requeue: $FILE"
    pop_done "$FILE"; queue_append "$FILE"
    continue
  fi

  DESTDIR="$(dirname "$DEST")"
  mkdir -p "$DESTDIR"
  OUTFREE=$(df -P --block-size=1 "$DESTDIR" | awk 'NR==2{print $4}')
  if [ "$OUTFREE" -lt $(( SZI * MARGIN_PCT / 100 )) ]; then
    log "SKIP low destination space (free=$((OUTFREE/1024/1024))MB), requeue: $FILE"
    pop_done "$FILE"; queue_append "$FILE"
    continue
  fi

  SOURCE_SIGNATURE=$(python3 "$RETRY_HELPER" snapshot "$FILE")
  RETRY_STATUS=$?
  case "$RETRY_STATUS" in
    0) ;;
    75) log "SKIP conversion cooldown (unchanged source): $FILE"; pop_done "$FILE"; continue;;
    76) log "source changed during admission; requeue: $FILE"; queue_append "$FILE"; pop_done "$FILE"; continue;;
    *) log "ERROR cooldown unavailable; retaining snapshot: $FILE"; exit 1;;
  esac
  FAIL_BEFORE=$failed
  CONVERTED_BEFORE=$converted
  VPI=$(vpackets "$FILE")
  TSI=$(tracksig "$FILE")
  case "$VPI" in ''|*[!0-9]*)
    log "ERROR cannot count input video packets; original kept: $FILE"; failed=$((failed+1)); record_failure; pop_done "$FILE"; continue;;
  esac
  if [ -z "$TSI" ]; then
    log "ERROR cannot fingerprint input tracks; original kept: $FILE"; failed=$((failed+1)); record_failure; pop_done "$FILE"; continue
  fi
  TIER="HDD"; [ "$SCR" = "$FAST_SCRATCH" ] && TIER="NVMe"
  W="$(mktemp -d "$SCR/job.XXXXXX")"
  ERR="$W/err.log"
  TMPOUT="$DESTDIR/.dovi.$(basename "$DEST").tmp"   # hidden temp beside final copy
  rm -f "$TMPOUT" 2>/dev/null
  log "convert START ($((SZI/1024/1024))MB, scratch=$TIER): $FILE"
  ok=1; stage=""
  stage=ffmpeg;   ffmpeg -nostdin -v error -i "$FILE" -map 0:v:0 -c copy -bsf:v hevc_mp4toannexb "$W/v.hevc" 2>"$ERR" || ok=0
  if [ "$ok" = 1 ] && grep -Eqi 'non monotonically increasing dts|invalid nal|corrupt|error applying bitstream' "$ERR"; then
    stage=ffmpeg-timeline; ok=0
  fi
  [ "$ok" = 1 ] && { stage=dovi_tool; dovi_tool -m 2 convert --discard -i "$W/v.hevc" -o "$W/v.p8.hevc" >/dev/null 2>>"$ERR" || ok=0; }
  [ "$ok" = 1 ] && rm -f "$W/v.hevc"                                  # free NVMe early
  [ "$ok" = 1 ] && { stage=mkvmerge; mkvmerge -q -o "$TMPOUT" "$W/v.p8.hevc" -D "$FILE" 2>>"$ERR" || ok=0; }
  if [ "$ok" = 1 ]; then
    SZO=$(stat -c%s "$TMPOUT" 2>/dev/null || echo 0)
    P8="$(mediainfo --Output='Video;%HDR_Format_Profile%' "$TMPOUT" 2>/dev/null)"
    DI=$(dur "$FILE"); DO=$(dur "$TMPOUT")
    DELTA=$(( DI>DO ? DI-DO : DO-DI ))
    VPO=$(vpackets "$TMPOUT")
    TSO=$(tracksig "$TMPOUT")
    COMPAT_ERR="$W/compat.err"
    ffmpeg -nostdin -v error -i "$TMPOUT" -map 0:v:0 -c copy -f hevc -y /dev/null 2>"$COMPAT_ERR" || true
    MID=$(( DO / 2 )); TAIL=$(( DO > 120 ? DO - 120 : 0 ))
    SMOKE=1
    decode_smoke "$TMPOUT" 0 || SMOKE=0
    [ "$SMOKE" = 1 ] && decode_smoke "$TMPOUT" "$MID" || SMOKE=0
    [ "$SMOKE" = 1 ] && decode_smoke "$TMPOUT" "$TAIL" || SMOKE=0
    if   [ "$SZO" -lt $((SZI*60/100)) ];        then log "ABORT small output ($SZO<$SZI): $FILE"; rm -f "$TMPOUT"; failed=$((failed+1)); ntfy "ABORT small output: $(basename "$FILE")"
    elif ! printf '%s' "$P8" | grep -Eqi 'dvhe\.08|profile 8'; then log "ABORT output not Profile 8 [$P8]: $FILE"; rm -f "$TMPOUT"; failed=$((failed+1)); ntfy "ABORT not Profile 8 [$P8]: $(basename "$FILE")"
    elif [ -z "$DI" ] || [ -z "$DO" ] || [ "$DELTA" -gt $(( DI/50 + 2 )) ]; then
         log "ABORT duration mismatch (in=${DI}s out=${DO}s): $FILE"; rm -f "$TMPOUT"; failed=$((failed+1)); ntfy "ABORT duration mismatch: $(basename "$FILE")"
    elif [ -z "$VPO" ] || [ "$VPO" != "$VPI" ]; then
         log "ABORT video packet mismatch (in=$VPI out=${VPO:-unknown}): $FILE"; rm -f "$TMPOUT"; failed=$((failed+1)); ntfy "ABORT video packet mismatch: $(basename "$FILE")"
    elif [ "$TSO" != "$TSI" ]; then
         log "ABORT non-video track mismatch: $FILE"; rm -f "$TMPOUT"; failed=$((failed+1)); ntfy "ABORT track mismatch: $(basename "$FILE")"
    elif [ -s "$COMPAT_ERR" ]; then
         CTAIL=$(head -3 "$COMPAT_ERR" | tr '\n' ' ' | cut -c1-300)
         log "ABORT compatibility probe errors [$CTAIL]: $FILE"; rm -f "$TMPOUT"; failed=$((failed+1)); ntfy "ABORT timestamp/bitstream errors: $(basename "$FILE")"
    elif [ "$SMOKE" != 1 ]; then
         log "ABORT decoder smoke test failed: $FILE"; rm -f "$TMPOUT"; failed=$((failed+1)); ntfy "ABORT decode test: $(basename "$FILE")"
    elif mv "$TMPOUT" "$DEST"; then
         log "compat DONE master-preserved P7->P8.1 [$P8] ($SZI->$SZO, packets=$VPO, tracks=preserved, scratch=$TIER): $FILE -> $DEST"
         # The compatibility view owns Jellyfin delivery.  Trigger its atomic
         # relink immediately; its service then notifies Jellyfin using the
         # unchanged canonical item path.
         companion_publish "$FILE"
         converted=$((converted+1))
    else
         log "ERROR compatibility publish failed, master untouched: $FILE"; rm -f "$TMPOUT" 2>/dev/null; failed=$((failed+1)); ntfy "ERROR compatibility publish failed: $(basename "$FILE")"
    fi
  else
    ETAIL=$(tail -3 "$ERR" 2>/dev/null | tr '\n' ' ' | cut -c1-300)
    log "ERROR $stage failed [$ETAIL], original kept: $FILE"; rm -f "$TMPOUT" 2>/dev/null; failed=$((failed+1))
    ntfy "ERROR $stage: $(basename "$FILE") — $ETAIL"

  fi
  if [ "$failed" -gt "$FAIL_BEFORE" ]; then
    record_failure
  elif [ "$converted" -gt "$CONVERTED_BEFORE" ]; then
    python3 "$RETRY_HELPER" clear "$FILE" --signature "$SOURCE_SIGNATURE"
    CLEAR_STATUS=$?
    case "$CLEAR_STATUS" in 0|76) ;; *) log "ERROR cooldown clear failed; retaining snapshot"; exit 1;; esac
  fi
  rm -rf "$W"
  pop_done "$FILE"
done < "$WQ"
rm -f "$WQ"
[ "$converted" -gt 0 ] && log "DRAIN summary: compatibility-copies=$converted failed=$failed"
if [ "$failed" -gt 0 ]; then
  ntfy "DoVi drain finished: $converted converted, $failed failed (see fel-to-p8.log)"
  exit 1
fi
exit 0
