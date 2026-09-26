#!/usr/bin/env python3
"""Hash-guarded migration of the private Bazarr post-sub cohort.

The private script contains credentials, so this module neither embeds nor
prints it. It removes every legacy library-scan route, records arrival before
AI, and turns later legacy scan calls into durable arrival no-ops.
"""
import argparse
import hashlib
import re
from pathlib import Path


def digest(data): return hashlib.sha256(data).hexdigest()


def transform(text, hook='${SCRIPT_DIR:-/config/scripts}/subtitle-arrival-hook.sh'):
    if '# habibi raw subtitle arrival (hash-guarded)' in text:
        raise RuntimeError('arrival migration already present; review private cohort')
    scan_helper = re.compile(r'# ── Helper: trigger Jellyfin library scan .*?(?=# ── Helper: extract numeric score)', re.S)
    text, count = scan_helper.subn('', text, count=1)
    if count != 1:
        raise RuntimeError('reviewed legacy scan helper not found exactly once')
    delayed = re.compile(r'^[ \t]*curl -s -X POST \\\n(?:.*\n){0,4}?[ \t]*echo "\$\(date -Iseconds\) \[bg\] Jellyfin scan triggered" >> "\$LOG"\n', re.M)
    replacement = '                            "' + hook + '" "$VIDEO_PATH" "$FOUND_PATH" >> "$LOG" 2>&1 || true\n'
    text, delayed_count = delayed.subn(replacement, text)
    if delayed_count != 1:
        raise RuntimeError('reviewed delayed legacy scan route not found exactly once')
    text = re.sub(r'\bjellyfin_scan\b', 'subtitle_arrival', text)
    marker = 'log "===== POST-PROCESS START ====="\n'
    if text.count(marker) != 1:
        raise RuntimeError('reviewed post-sub start marker not found exactly once')
    helper = ('# habibi raw subtitle arrival (hash-guarded)\n'
              'subtitle_arrival() {\n'
              '    "' + hook + '" "$VIDEO_PATH" "$SUB_PATH" >> "$LOG" 2>&1 || log "subtitle arrival enqueue deferred"\n'
              '}\n'
              'subtitle_arrival\n\n')
    text = text.replace(marker, helper + marker)
    forbidden = ('jellyfin_scan', 'Library/Media/Updated', 'ScheduledTasks', 'RefreshLibrary', '/Library/Refresh')
    if any(token in text for token in forbidden):
        raise RuntimeError('legacy scan route remains after transform')
    return text


def install(path, expected, hook=None):
    path = Path(path); original = path.read_bytes()
    if digest(original) != expected:
        raise RuntimeError('post-sub.sh SHA-256 mismatch; inspect/review before changing it')
    updated = transform(original.decode('utf-8'), hook or '${SCRIPT_DIR:-/config/scripts}/subtitle-arrival-hook.sh')
    temporary = path.with_name(path.name + '.arrival-hook.tmp')
    temporary.write_text(updated)
    temporary.chmod(path.stat().st_mode)
    temporary.replace(path)
    return digest(updated.encode())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--post-sub', required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--hook')
    args = parser.parse_args()
    print(install(args.post_sub, args.expected_sha256, args.hook))


if __name__ == '__main__': main()
