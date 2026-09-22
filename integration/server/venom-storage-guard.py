"""Bounded SQLite WAL reclamation; never delete DB/WAL files or run VACUUM."""
import json
from pathlib import Path
import shutil
import time

DATABASE=Path('/data/config/jellyfin/data/data/jellyfin.db')
THRESHOLD=256*1024*1024

def open_database(path):
    import apsw
    if tuple(map(int,apsw.sqlitelibversion().split('.'))) < (3,51,3):
        raise RuntimeError('Storage guard requires SQLite with the WAL-reset fix')
    db=apsw.Connection(str(path),flags=apsw.SQLITE_OPEN_READWRITE)
    db.set_busy_timeout(10000)
    return db

def reclaim(path=DATABASE,threshold=THRESHOLD):
    wal=Path(str(path)+'-wal')
    before=wal.stat().st_size if wal.exists() else 0
    result={'wal_before':before,'action':'below_threshold'}
    if before>=threshold:
        # READWRITE without CREATE cannot create a replacement database. SQLite
        # coordinates with active readers/writers; busy means retry next timer.
        db=open_database(path)
        try:
            busy,frames,checkpointed=db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        finally:db.close()
        result.update(action='busy_retry_later' if busy else 'checkpointed',busy=busy,frames=frames,checkpointed=checkpointed)
    result['wal_after']=wal.stat().st_size if wal.exists() else 0
    result['free_bytes']=shutil.disk_usage(path.parent).free
    result['time']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    return result

if __name__=='__main__':print(json.dumps(reclaim()),flush=True)
