#!/usr/bin/env python3
"""Guarded private-worker transform; never copies/redacts credential lines."""
import argparse
from pathlib import Path


def transform(text):
    start = text.index('jf_refresh(){')
    end = text.index('# Persistent cooldown', start)
    block = text[start:end]
    if '/Library/Media/Updated' not in block or text.count('jf_refresh') != 1:
        raise ValueError('unexpected worker refresh block; review required')
    replacement = '''companion_publish(){
  local result
  result=$(python3 "$DIR/dovi-import-fast.py" --config "$DIR/fast-import.json" --companion-ready "$1" 2>/dev/null)
  if [ "$?" = 0 ]; then
    log "companion publication handoff: $result"
  else
    log "companion publication handoff unavailable; periodic repair retained"
  fi
}

'''
    trigger = '         touch /data/media/compatibility/.dovi-reconcile.trigger'
    if text.count(trigger) != 1:
        raise ValueError('unexpected worker completion trigger; review required')
    text = text[:start] + replacement + text[end:]
    return text.replace(trigger, '         companion_publish "$FILE"')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        raise ValueError('write a separate staged output; never modify running worker')
    # Explicit source/output deployment transform, retaining private lines exactly.
    args.output.write_text(transform(args.source.read_text()))
    args.output.chmod(args.source.stat().st_mode & 0o777)
