#!/usr/bin/env python3
"""Publish newly verified curated channels and seed native favourites resumably."""
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path('/data/config/iptv-venom')

def main():
    lock=(ROOT/'promote-tested.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return
    def run(script,*args):
        subprocess.run([sys.executable,str(ROOT/script),*args],check=True)
    run('venom-curate-channels.py','--approve-tested')
    manifest=json.loads((ROOT/'curated-channels.json').read_text())
    fingerprint=hashlib.sha256(json.dumps(manifest,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    marker=ROOT/'promoted-collections.sha256'
    if marker.exists() and marker.read_text().strip()==fingerprint:
        print(json.dumps({'event':'promotion_unchanged'}),flush=True);return
    run('venom-seed-favourites.py','--apply')
    run('venom-publish-collections.py')
    temp=marker.with_suffix('.tmp');temp.write_text(fingerprint+'\n');temp.chmod(0o600);temp.replace(marker)
    print(json.dumps({'event':'promotion_finished','channels':manifest['unique_channels']}),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'event':'promotion_error','type':type(exc).__name__}),flush=True);raise SystemExit(1)
