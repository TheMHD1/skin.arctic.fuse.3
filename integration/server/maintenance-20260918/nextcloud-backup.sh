#!/usr/bin/env bash
#
# Nightly Nextcloud backup.
# - Dumps MariaDB nextcloud DB
# - Tars /data/config/nextcloud (configs + apps, excludes user data which lives at /data/media/nextcloud_data)
# - Grandfather-Father-Son retention: 7 daily + 4 weekly + 3 monthly (up to 14 dirs)
# - Puts Nextcloud in maintenance mode for the config tar to get a consistent snapshot
#
set -euo pipefail
umask 077

BACKUP_ROOT=/root/backups/nextcloud
DAILY_KEEP=7
WEEKLY_KEEP=4
MONTHLY_KEEP=3
DATE=$(date +%F_%H%M)
DEST="$BACKUP_ROOT/$DATE"
LOG="$BACKUP_ROOT/backup.log"

exec >>"$LOG" 2>&1
trap 'rc=$?; echo "[$(date -Is)] FATAL: ${BASH_SOURCE[0]} died at line $LINENO (exit $rc)"' ERR
echo "[$(date -Is)] === nextcloud-backup start ==="

mkdir -p "$DEST"

cleanup() {
    docker exec -u www-data nextcloud php occ maintenance:mode --off >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[$(date -Is)] enabling maintenance mode before database/config snapshot"
docker exec -u www-data nextcloud php occ maintenance:mode --on >/dev/null

echo "[$(date -Is)] mysqldump nextcloud DB"
docker exec nextcloud_db sh -c \
    'MYSQL_PWD="$MYSQL_PASSWORD" mysqldump --single-transaction --default-character-set=utf8mb4 -u "$MYSQL_USER" "$MYSQL_DATABASE"' \
    | gzip > "$DEST/nextcloud-db.sql.gz"

echo "[$(date -Is)] tar /data/config/nextcloud (excluding large caches)"
tar --warning=no-file-changed \
    --exclude='*/data/appdata_*/preview/*' \
    --exclude='*/data/appdata_*/dav-photocache/*' \
    --exclude='*/data/*/cache/*' \
    --exclude='*/data/*/uploads/*' \
    -czf "$DEST/nextcloud-config.tar.gz" -C /data/config nextcloud

gzip -t "$DEST/nextcloud-db.sql.gz"
tar -tzf "$DEST/nextcloud-config.tar.gz" nextcloud/config/config.php >/dev/null

echo "[$(date -Is)] disabling maintenance mode"
docker exec -u www-data nextcloud php occ maintenance:mode --off >/dev/null

echo "[$(date -Is)] sizes:"
du -h "$DEST"/*

# --- Retention policy: 7 daily + 4 weekly + 3 monthly ---
# Backups are directories named YYYY-MM-DD_HHMM (daily) or weekly-* / monthly-* (promoted).
# Strategy: anything older than DAILY_KEEP daily dirs is considered for promotion:
#   - age 7..30 days  -> promote to weekly-<name> if weekly slots free, else delete
#   - age >30 days    -> promote to monthly-<name> if monthly slots free, else delete
# Then trim weekly/monthly to their KEEP limits.
echo "[$(date -Is)] applying retention (daily=$DAILY_KEEP weekly=$WEEKLY_KEEP monthly=$MONTHLY_KEEP)"
cd "$BACKUP_ROOT" || exit 1

now_epoch=$(date +%s)

# Step 1: Process daily dirs beyond DAILY_KEEP
# ls -1td lists newest first; tail skips the ones we keep.
{ ls -1td 20*_*/ 2>/dev/null || true; } | sed 's:/$::' | tail -n +$((DAILY_KEEP+1)) | while read -r d; do
    [ -d "$d" ] || continue
    mtime=$(stat -c %Y "$d")
    age_days=$(( (now_epoch - mtime) / 86400 ))
    if [ "$age_days" -le 30 ]; then
        weekly_count=$(find . -maxdepth 1 -type d -name "weekly-*" | wc -l)
        if [ "$weekly_count" -lt "$WEEKLY_KEEP" ]; then
            echo "  promote daily -> weekly: $d (age ${age_days}d)"
            mv "$d" "weekly-$d"
            continue
        fi
    fi
    if [ "$age_days" -gt 30 ]; then
        monthly_count=$(find . -maxdepth 1 -type d -name "monthly-*" | wc -l)
        if [ "$monthly_count" -lt "$MONTHLY_KEEP" ]; then
            echo "  promote daily -> monthly: $d (age ${age_days}d)"
            mv "$d" "monthly-$d"
            continue
        fi
    fi
    echo "  delete daily: $d (age ${age_days}d)"
    rm -rf "$d"
done

# Step 2: Trim weekly beyond WEEKLY_KEEP
{ ls -1td weekly-*/ 2>/dev/null || true; } | sed 's:/$::' | tail -n +$((WEEKLY_KEEP+1)) | while read -r d; do
    [ -d "$d" ] || continue
    echo "  delete weekly: $d"
    rm -rf "$d"
done

# Step 3: Trim monthly beyond MONTHLY_KEEP
{ ls -1td monthly-*/ 2>/dev/null || true; } | sed 's:/$::' | tail -n +$((MONTHLY_KEEP+1)) | while read -r d; do
    [ -d "$d" ] || continue
    echo "  delete monthly: $d"
    rm -rf "$d"
done

echo "[$(date -Is)] retention done. Current state:"
ls -1td 20*_*/ weekly-*/ monthly-*/ 2>/dev/null | sed 's:/$::' || true

echo "[$(date -Is)] === nextcloud-backup done ==="
