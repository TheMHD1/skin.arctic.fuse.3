"""Exact-plugin search watcher upgrade; private configuration is read-only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

BEFORE='094da31cd5488417ff9567efd1d71e83ddf07f0bc8bf98bb809e2a19b8359766'
AFTER='043af78aa281437a8d8b9eacb9a62996ab977e57fb138305104890e5498b677d'
NAME='Jellyfin.Plugin.JellyfinEnhanced.dll'
def sha(data):return hashlib.sha256(data).hexdigest()

def active(request):
    if request('System/Info/Public')['Version']!='12.1.0':raise ValueError('Unreviewed Jellyfin version')
    plugins=[p for p in request('Plugins') if p.get('Name')=='Jellyfin Enhanced' and p.get('Status')=='Active']
    if len(plugins)!=1 or plugins[0].get('Version')!='12.7.0.0':raise ValueError('Unreviewed Enhanced plugin')
    return plugins[0]['Id']

def deploy(target,candidate,backup,request,stop,start,ready,apply=False):
    if target.is_symlink() or candidate.is_symlink():raise ValueError('Unsafe plugin path')
    before=target.read_bytes();output=candidate.read_bytes()
    if sha(before) not in (BEFORE,AFTER) or sha(output)!=AFTER:raise ValueError('Unreviewed Enhanced binary')
    ident=active(request);configuration=request('Plugins/'+ident+'/Configuration')
    if configuration.get('TagCacheServerMode') is not False:raise ValueError('Visible-card tag policy not applied')
    if sha(before)==AFTER:return {'changes':[],'restart':False}
    if not apply:return {'changes':[NAME],'restart':True}
    backup.mkdir(mode=0o700,parents=True,exist_ok=False)
    saved=backup/NAME;saved.write_bytes(before);saved.chmod(0o600)
    journal=backup/'configuration.private.json';journal.write_text(json.dumps(configuration,indent=2));journal.chmod(0o600)
    mode=target.stat().st_mode&0o777
    def write(data):
        fd,name=tempfile.mkstemp(prefix=target.name+'.performance-',dir=target.parent)
        temporary=Path(name)
        try:
            with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            temporary.chmod(mode);os.replace(temporary,target)
        finally:temporary.unlink(missing_ok=True)
    if target.read_bytes()!=before:raise ValueError('Plugin changed before stop')
    stop()
    try:
        if target.read_bytes()!=before:raise ValueError('Plugin changed during stop')
        write(output);start();ready()
        if target.read_bytes()!=output or active(request)!=ident:raise RuntimeError('Enhanced activation drift')
        if request('Plugins/'+ident+'/Configuration')!=configuration:raise RuntimeError('Enhanced configuration drift')
    except BaseException:
        stop()
        write(before);start();ready();raise
    return {'changes':[NAME],'restart':True,'configuration_preserved':True}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--backup',type=Path,required=True);p.add_argument('--url',required=True)
    p.add_argument('--token-file',type=Path,required=True);p.add_argument('--apply',action='store_true')
    a=p.parse_args();token=a.token_file.read_text().strip()
    def request(path):
        req=urllib.request.Request(a.url.rstrip('/')+'/'+path,headers={'Authorization':'MediaBrowser Token="'+token+'"'})
        with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
    def stop():subprocess.run(['docker','stop','--time','30','jellyfin'],check=True,timeout=45,stdout=subprocess.DEVNULL)
    def start():subprocess.run(['docker','start','jellyfin'],check=True,timeout=30,stdout=subprocess.DEVNULL)
    def ready():
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            try:active(request);return
            except (OSError,ValueError):time.sleep(1)
        raise RuntimeError('Enhanced did not activate')
    print(json.dumps(deploy(a.target,a.candidate,a.backup,request,stop,start,ready,a.apply)))
