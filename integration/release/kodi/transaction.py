"""Fail-closed Kodi file transaction shared by the portable release installer."""
import json
import os
import socket
import subprocess
import time
from pathlib import Path

# CoreELEC's Kodi unit may consume its normal 30-second stop grace while an
# update dialog is unwinding.  Keep the caller alive long enough to observe the
# completed stop; this is not permission to write until the post-stop snapshot
# validates.
SYSTEMCTL_TIMEOUT = 45

class Plan(dict):
    def __init__(self,changes,expected):super().__init__(changes);self.expected=expected

def require(condition,message):
    if not condition:raise RuntimeError(message)

def rpc(method):
    with socket.create_connection(('127.0.0.1',9090),3) as sock:
        sock.settimeout(3);sock.sendall(json.dumps({'jsonrpc':'2.0','id':1,'method':method}).encode())
        data=b'';deadline=time.monotonic()+4
        while len(data)<65536:
            remaining=deadline-time.monotonic();require(remaining>0,'Kodi JSON-RPC deadline exceeded')
            sock.settimeout(min(3,remaining));chunk=sock.recv(8192);require(chunk,'Kodi closed JSON-RPC')
            data+=chunk
            try:response=json.loads(data)
            except (ValueError,UnicodeDecodeError):continue
            require(response.get('id')==1 and 'result' in response,'Kodi JSON-RPC error')
            return response['result']
        raise RuntimeError('Kodi JSON-RPC response too large')

def idle():require(rpc('Player.GetActivePlayers')==[],'Wait until Kodi is idle, including paused playback')
def ready():
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        try:
            if rpc('JSONRPC.Ping')=='pong':return
        except (OSError,RuntimeError):pass
        time.sleep(.5)
    raise RuntimeError('Kodi did not become ready after startup')

def atomic_write(path,payload,mode=0o644):
    temp=path.with_name(path.name+'.audit-tmp');out=temp.open('xb')
    try:
        with out:out.write(payload);out.flush();os.fsync(out.fileno())
        temp.chmod(mode);os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)

def deploy(root,plan,backup,run=subprocess.run,idle_check=idle,wait_ready=ready,write=atomic_write):
    if not plan:return False
    require(isinstance(plan,Plan),'Deployment requires a reviewed snapshot')
    def validate():
        for path,expected in plan.expected.items():
            require((path.read_bytes() if path.exists() else None)==expected,'Source changed since planning: '+str(path))
        for path in plan:require(not path.with_name(path.name+'.audit-tmp').exists(),'Foreign staging file: '+str(path))
    validate();idle_check();backup.mkdir(parents=True,mode=0o700,exist_ok=False)
    originals={p:(p.read_bytes(),p.stat().st_mode&0o777) if p.exists() else (None,0o644) for p in plan}
    for path,(payload,mode) in originals.items():
        if payload is not None:
            saved=backup/path.relative_to(root);saved.parent.mkdir(parents=True,exist_ok=True);atomic_write(saved,payload,mode)
    (backup/'change-paths.json').write_text(json.dumps([
        {'path':str(path.relative_to(root)),'existed':originals[path][0] is not None} for path in plan
    ],indent=2))
    validate();idle_check();written=[]
    try:
        run(['systemctl','stop','kodi'],check=True,timeout=SYSTEMCTL_TIMEOUT);validate()
        for path,payload in plan.items():written.append(path);write(path,payload,originals[path][1])
        run(['systemctl','start','kodi'],check=True,timeout=SYSTEMCTL_TIMEOUT);wait_ready()
    except (Exception,KeyboardInterrupt) as failure:
        try:
            run(['systemctl','stop','kodi'],check=False,timeout=SYSTEMCTL_TIMEOUT)
            for path in reversed(written):
                payload,mode=originals[path]
                if payload is None:path.unlink(missing_ok=True)
                else:atomic_write(path,payload,mode)
            run(['systemctl','start','kodi'],check=True,timeout=SYSTEMCTL_TIMEOUT);wait_ready()
        except Exception as recovery:
            raise RuntimeError('Deployment/recovery failed; inspect '+str(backup)) from recovery
        raise RuntimeError('Deployment failed; originals restored; backup '+str(backup)) from failure
    return True
