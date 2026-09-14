"""Repair missing curated artwork using explicitly reviewed station matches.

Existing working images are preserved. External fetches use no server token.
Only validated, size-bounded PNGs are uploaded via Jellyfin's image API.
"""
import argparse,base64,fcntl,hashlib,json,re,runpy,struct,urllib.request
from pathlib import Path
from urllib.parse import urlencode

ROOT=Path('/data/config/iptv-venom')
_clean_name=runpy.run_path(str(Path(__file__).with_name('venom-channel-names.py')))['clean_name']
def key(name):
    name=_clean_name(name)
    name=re.sub(r'^(MBC|OSN)\s*[:.]\s*',r'\1 ',name,flags=re.I)
    name=re.sub(r'\s*· BACKUP.*$','',name.upper())
    name=re.sub(r'\[NOT 24/7\]|\(\d{3,4}P\)',' ',name)
    name=re.sub(r'(?<!\w)(?:[468]K|UHD|FHD|HDF|HD|SD|1080P|720P|50FPS)(?!\w)\.?\+?',' ',name)
    return re.sub(r'\s+',' ',name).strip(' /')

def main():
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--limit',type=int,default=250);p.add_argument('--missing-only',action='store_true');args=p.parse_args()
    lock=(ROOT/'reviewed-artwork.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    helper=runpy.run_path('/root/iptv-jellyfin-admin.py');api=helper['api'];base=helper['BASE']
    token=(ROOT/'jellyfin-api-key').read_text().strip()
    headers={'Authorization':'MediaBrowser Token="'+token+'"'}
    def request(path,data=None,mime=None):
        h={**headers}
        if mime:h['Content-Type']=mime
        with urllib.request.urlopen(urllib.request.Request(base+path,data=data,headers=h),timeout=15) as r:return r.read(4*1024*1024+1)
    mapping=json.loads((ROOT/'venom-reviewed-artwork.json').read_text())
    native=json.loads((ROOT/'curated-native-channels.json').read_text())
    ids={c['id']:c['gateway_id'] for g in native['groups'] for c in g['channels']}
    scopes={}
    for g in native['groups']:
        for c in g['channels']:scopes.setdefault(c['id'],'AR' if g['id'].startswith('ar-') else 'CA' if g['id']=='en-canada' else 'EN')
    catalogue=json.loads((ROOT/'live-catalogue-redacted.json').read_text())
    categories={str(c['category_id']):c['category_name'] for c in catalogue['categories']}
    source={str(c['stream_id']):c for c in catalogue['channels']}
    language=runpy.run_path(str(ROOT/'venom-sports-entertainment.py'))['language']
    for iid,gid in ids.items():
        c=source.get(str(gid),{});cat=categories.get(str(c.get('category_id')),'')
        lang=language(c.get('name',''),cat)
        if lang and scopes[iid]!='CA':scopes[iid]='AR' if lang=='ar' else 'EN'
    uid=next(u['Id'] for u in api('/Users') if u['Name'].lower()=='habibi')
    items=[];keys=list(ids)
    for i in range(0,len(keys),80):items+=api('/Users/'+uid+'/Items?'+urlencode({'Ids':','.join(keys[i:i+80]),'Limit':80}))['Items']
    cache=ROOT/'reviewed-logo-cache';cache.mkdir(exist_ok=True)
    ledger_path=ROOT/'reviewed-artwork-applied.json';ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    count=preserved=unmatched=0;errors=[];download_failures=set();missing=[]
    for item in items:
        match=mapping.get(scopes[item['Id']]+':'+key(item['Name'])) or mapping.get(key(item['Name']))
        iid=item['Id']
        if item.get('ImageTags',{}).get('Primary'):
            if args.missing_only:preserved+=1;continue
            try:
                if len(request('/Items/'+iid+'/Images/Primary?maxWidth=64'))>100:preserved+=1;continue
            except Exception:pass
        if not match:
            unmatched+=1;missing.append({'id':iid,'name':item['Name'],'scope':scopes[iid]});continue
        if count>=args.limit:break
        if not args.apply:count+=1;continue
        try:
            url=match['url']
            if url in download_failures:
                errors.append({'name':item['Name'],'error':'source_unavailable_this_pass'});continue
            path=cache/(hashlib.sha256(url.encode()).hexdigest()+'.png')
            if path.exists():data=path.read_bytes()
            else:
                try:
                    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'PersonalChannelArtwork/1.0'}),timeout=12) as r:data=r.read(4*1024*1024+1)
                    if not (100<len(data)<=4*1024*1024 and (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff'))):raise ValueError('Not a bounded PNG/JPEG')
                    if data.startswith(b'\x89PNG'):
                        width,height=struct.unpack('>II',data[16:24])
                        if not (16<=width<=8192 and 16<=height<=8192):raise ValueError('Invalid dimensions')
                    path.write_bytes(data)
                except Exception:
                    download_failures.add(url);raise
            request('/Items/'+iid+'/Images/Primary',base64.b64encode(data),'image/png' if data.startswith(b'\x89PNG') else 'image/jpeg')
            if len(request('/Items/'+iid+'/Images/Primary?maxWidth=128'))<100:raise ValueError('Image readback failed')
            ledger[iid]={'gateway_id':ids[iid],'station':match['channel'],'url':url,'name':item['Name'],'kind':match.get('kind','station-logo')}
            tmp=ledger_path.with_suffix('.tmp');tmp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2));tmp.chmod(0o600);tmp.replace(ledger_path)
            count+=1
            if count<=3 or count%25==0:print(json.dumps({'uploaded':count,'name':item['Name']}),flush=True)
        except Exception as exc:errors.append({'name':item['Name'],'error':type(exc).__name__})
    report={'total':len(items),'apply':args.apply,'repaired' if args.apply else 'planned':count,'preserved':preserved,'unmatched':unmatched,'errors':errors,'missing':missing}
    (ROOT/'reviewed-artwork-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
