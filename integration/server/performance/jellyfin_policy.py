"""Use Enhanced's native visible-card tag pipeline on the reviewed large library."""
import argparse
import json
from pathlib import Path
import urllib.parse
import urllib.request

SERVER='12.1.0'
PLUGIN='12.7.0.0'

def proposed(config):
    if type(config.get('TagCacheServerMode')) is not bool:raise ValueError('Unreviewed Enhanced configuration')
    return {**config,'TagCacheServerMode':False}

def deploy(request,journal,apply=False):
    if request('GET','System/Info/Public')['Version']!=SERVER:raise ValueError('Unreviewed Jellyfin version')
    plugins=[p for p in request('GET','Plugins') if p.get('Name')=='Jellyfin Enhanced' and p.get('Status')=='Active']
    if len(plugins)!=1 or plugins[0].get('Version')!=PLUGIN:raise ValueError('Unreviewed Enhanced plugin')
    path='Plugins/'+plugins[0]['Id']+'/Configuration'
    before=request('GET',path);after=proposed(before)
    changes=[k for k in after if after[k]!=before[k]]
    result={'server':SERVER,'enhanced':PLUGIN,'changes':changes,'restart':False}
    if not apply or not changes:return result
    with journal.open('x') as f:
        journal.chmod(0o600);json.dump({'path':path,'before':before,'after':after},f,indent=2)
    try:
        request('POST',path,after)
        if request('GET',path)!=after:raise RuntimeError('Enhanced policy readback drift')
    except BaseException:
        request('POST',path,before)
        raise
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',required=True);p.add_argument('--token-file',type=Path,required=True)
    p.add_argument('--journal',type=Path,required=True);p.add_argument('--apply',action='store_true')
    a=p.parse_args();token=a.token_file.read_text().strip()
    def request(method,path,data=None):
        body=None if data is None else json.dumps(data).encode()
        req=urllib.request.Request(a.url.rstrip('/')+'/'+path,data=body,method=method,
            headers={'Authorization':'MediaBrowser Token="'+token+'"','Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=30) as response:
            raw=response.read();return json.loads(raw) if raw else None
    print(json.dumps(deploy(request,a.journal,a.apply)))
