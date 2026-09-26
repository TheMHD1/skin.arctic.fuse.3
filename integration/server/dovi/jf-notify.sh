#!/usr/bin/env bash
set -euo pipefail
# Native ARR import hooks enqueue exact imported files. No Jellyfin API call or
# media probe runs in the ARR container. The fifteen-minute sweep stays the repair backstop.
readonly trigger_dir=/data/media/compatibility
event="${radarr_eventtype:-${sonarr_eventtype:-unknown}}"
if [[ "$event" == Test ]]; then
    printf 'DoVi compatibility automation hook: test ok\n'
    exit 0
fi
app=sonarr
title="${sonarr_series_path:-}"
video="${sonarr_episodefile_path:-}"
item="${sonarr_series_id:-}"
if [[ -n "${radarr_eventtype:-}" ]]; then
    app=radarr
    title="${radarr_movie_path:-}"
    video="${radarr_moviefile_path:-}"
    item="${radarr_movie_id:-}"
fi
install -d -m 0755 "$trigger_dir"
if [[ "$event" == Download && "$item" =~ ^[0-9]+$ && -n "$title" && "$video" == "$title/"* \
      && "$title" != *$'\n'* && "$video" != *$'\n'* && "$title" != */../* && "$video" != */../* ]]; then
    case "$title" in
        /data/media/movies/*|/data/media/shows/*)
            readonly spool="$trigger_dir/.dovi-import-queue"
            install -d -m 0755 "$spool"
            temporary=$(mktemp "$trigger_dir/.dovi-import.XXXXXX")
            printf 'v1\n%s\n%s\n%s\n%s\n%s\n%s\n' "$(date -u +%FT%TZ)" "$app" "$item" "$title" "$video" "$event" > "$temporary"
            chmod 0644 "$temporary"
            mv "$temporary" "$spool/${temporary##*/}.event"
            printf 'DoVi exact-import publication queued\n'
            exit 0
            ;;
    esac
fi
# Rename/delete/unknown legacy events keep their existing full repair trigger.
temporary=$(mktemp "$trigger_dir/.dovi-trigger.XXXXXX")
printf '%s\t%s\n' "$(date -u +%FT%TZ)" "$event" > "$temporary"
chmod 0644 "$temporary"
mv -f "$temporary" "$trigger_dir/.dovi-reconcile.trigger"
printf 'DoVi compatibility reconciliation requested: %s\n' "$event"
