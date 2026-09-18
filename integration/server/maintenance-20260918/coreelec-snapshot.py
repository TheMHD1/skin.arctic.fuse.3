"""Keep daily hard-linked versions of the completed, restricted rsync mirror."""
import datetime
import fcntl
import os
from pathlib import Path
import shutil
import subprocess

base=Path('/data/config/coreelec-backups')
source=base/'ugoos-am9-pro'
versions=base/'ugoos-am9-pro-versions'
versions.mkdir(mode=0o700,parents=True,exist_ok=True)
with (versions/'.lock').open('w') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    marker=source/'status/last-success-utc'
    if not marker.exists() or (source/'status/backup-running').exists():raise SystemExit('No completed backup ready')
    stamp=marker.read_text().strip()
    day=datetime.datetime.fromisoformat(stamp.replace('Z','+00:00')).strftime('%Y-%m-%d')
    target=versions/day
    if target.exists():
        if not target.is_dir() or target.is_symlink():raise RuntimeError('Invalid existing snapshot target')
        print('Daily snapshot already exists; nothing to do:',target)
        raise SystemExit(0)
    stage=versions/(day+'.partial')
    if stage.exists():raise SystemExit('Incomplete snapshot requires review: '+str(stage))
    subprocess.run(['cp','-al',str(source),str(stage)],check=True)
    if marker.read_text().strip()!=stamp or (source/'status/backup-running').exists():
        shutil.rmtree(stage)
        raise SystemExit('Backup changed during snapshot; retry next hour')
    stage.rename(target)
    # Retain14 dated snapshots; only remove validated direct children we created.
    dated=sorted(p for p in versions.iterdir() if p.is_dir() and len(p.name)==10 and p.name[4]==p.name[7]=='-')
    for old in dated[:-14]:
        datetime.date.fromisoformat(old.name)
        if old.is_symlink():raise RuntimeError('Refusing symlink snapshot')
        shutil.rmtree(old)
    print('Snapshot complete:',target)
