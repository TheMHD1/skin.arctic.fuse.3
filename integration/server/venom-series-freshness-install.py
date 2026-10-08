"""Install pinned catalogue freshness code; default is a no-write plan."""
import argparse,fcntl,hashlib,json,os,shutil,socket,sqlite3,subprocess,time
from pathlib import Path
ROOT=Path('/data/config/iptv-venom');HERE=Path(__file__).resolve().parent
EXPORT='venom-jellyfin-export.py';HELPER='venom-series-revisions.py'
BEFORE='60705b4c0beafc976ad7094fa9bfd2aa70821f016aaa73f9f0a624498573ae33'
AFTER={EXPORT:'75df0447a2d32fe6db8909f28cd7f9c1a63e50aaf07ef1eb3a5e864f7b39fac8',
       HELPER:'482a7fe059cdbaa9f579765f7dba6f1ea350dfca483744164d7cc36a96e759cb'}
def sha(data):return hashlib.sha256(data).hexdigest()
def regular(path):
    for parent in (path,*path.parents):
        if parent.is_symlink():raise ValueError('Symlink in installation path')
    return path
def plan(root=ROOT):
    expected={};writes={}
    for name,digest in AFTER.items():
        source=regular(HERE/name).read_bytes()
        if sha(source)!=digest:raise ValueError('Release source drift')
        target=regular(root/name);old=target.read_bytes() if target.exists() else None;expected[target]=old
        if old is not None and sha(old)==digest:continue
        if (name==EXPORT and (old is None or sha(old)!=BEFORE)) or (name==HELPER and old is not None):
            raise ValueError('Unreviewed installed source')
        writes[target]=source
    return writes,expected
def atomic(path,data,mode):
    temporary=path.with_name(path.name+'.freshness-tmp')
    with temporary.open('xb') as out:out.write(data);out.flush();os.fsync(out.fileno())
    temporary.chmod(mode);os.replace(temporary,path)
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if socket.gethostname()!='Media-LXC':raise SystemExit('Wrong server')
    writes,expected=plan();print(json.dumps({'changes':[p.name for p in writes],'apply':args.apply}))
    if not args.apply or not writes:return
    if shutil.disk_usage(ROOT).free<8*1024**3:raise SystemExit('Insufficient free space')
    if subprocess.run(['systemctl','is-active','--quiet','venom-jellyfin-export.service']).returncode==0:
        raise SystemExit('Export is running; wait for its bounded pass')
    with regular(ROOT/'catalogue-export.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        backup=ROOT/'backup'/('series-freshness-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
        backup.mkdir(parents=True,mode=0o700,exist_ok=False)
        for target,old in expected.items():
            if (target.read_bytes() if target.exists() else None)!=old:raise ValueError('Source changed after plan')
            if old is not None:shutil.copy2(target,backup/target.name)
        state=ROOT/'catalogue-progress.sqlite3'
        if state.exists():
            with sqlite3.connect(state.as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(backup/'catalogue-progress.sqlite3') as destination:
                source.backup(destination)
        written=[]
        try:
            for target,data in sorted(writes.items(),key=lambda item:item[0].name==EXPORT):
                mode=target.stat().st_mode&0o777 if target.exists() else 0o640
                atomic(target,data,mode);written.append(target)
            assert not plan()[0]
        except BaseException:
            for target in reversed(written):
                old=expected[target]
                if old is None:target.unlink()
                else:atomic(target,old,(backup/target.name).stat().st_mode&0o777)
            raise
        print('Applied; own code/database snapshot:',backup)
if __name__=='__main__':main()
