"""Apply gateway-aligned names with Jellyfin's normal metadata editor API.

Private full-item backups; stable IDs; preserves user-edited names. Dry run by
default. Uses complete item DTO, never a partial metadata update that could
clear unrelated fields. Does not rebuild channels or alter playback paths.
"""
import argparse
import fcntl
import json
from pathlib import Path
import runpy

ROOT=Path('/data/config/iptv-venom')
PROTECTED=('Id','Type','ChannelNumber','Path','ParentId','ProviderIds','Genres','Tags',
           'OfficialRating','CustomRating','LockData','LockedFields','Overview','Studios',
           'PremiereDate','ProductionYear','PreferredMetadataLanguage','PreferredMetadataCountryCode')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--limit',type=int,default=1);parser.add_argument('--curated',action='store_true');args=parser.parse_args()
    lock=(ROOT/'jellyfin-clean-names.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    policy=runpy.run_path(str(ROOT/'venom-channel-names.py'))
    clean=policy['clean_name']
    api=runpy.run_path('/root/iptv-jellyfin-admin.py')['api']
    uid=next(u['Id'] for u in api('/Users') if u['Name'].casefold()=='habibi')
    before=json.loads((ROOT/'channel-names-before.json').read_text())
    if args.curated:
        native=json.loads((ROOT/'curated-native-channels.json').read_text())
        ids={c['id'] for g in native['groups'] for c in g['channels']}
        before={i:v for i,v in before.items() if i in ids}
    # A bounded list snapshot avoids thousands of individual reads on reruns.
    # Re-read the full DTO immediately before every actual metadata update.
    names={}
    for offset in range(0,20000,500):
        page=api('/LiveTv/Channels?UserId='+uid+'&StartIndex='+str(offset)+'&Limit=500&AddCurrentProgram=false&EnableImages=false')
        names.update({row['Id']:row['Name'] for row in page['Items']})
        if offset+len(page['Items'])>=page['TotalRecordCount']:break
    backups=ROOT/'backups'/'jellyfin-channel-name-items';backups.mkdir(mode=0o700,exist_ok=True)
    changed=skipped=0
    for iid,old in before.items():
        desired=clean(old['name'])
        if desired==old['name']:continue
        if names.get(iid)==desired:skipped+=1;continue
        item=api('/Users/'+uid+'/Items/'+iid)
        if item['Name']==desired:skipped+=1;continue
        if item['Name'] not in (old['name'], policy['previous_clean_name'](old['name'])):continue  # Preserve unrelated manual edits.
        if item['Type']!='TvChannel' or item['Id']!=iid:raise ValueError('Wrong item type/identity')
        if not args.apply:
            print(json.dumps({'id':iid,'before':item['Name'],'after':desired},ensure_ascii=False));changed+=1
        else:
            path=backups/(iid+'.json')
            if not path.exists():
                with path.open('x') as f:
                    path.chmod(0o600);json.dump(item,f,ensure_ascii=False)
            api('/Items/'+iid,{**item,'Name':desired},'POST')
            actual=api('/Users/'+uid+'/Items/'+iid)
            mismatches=[field for field in PROTECTED if item.get(field)!=actual.get(field)]
            if actual['Name']!=desired or mismatches:
                raise ValueError('Name update verification failed: '+','.join(mismatches))
            if item.get('UserData',{}).get('IsFavorite')!=actual.get('UserData',{}).get('IsFavorite'):
                raise ValueError('Favourite changed during name verification')
            changed+=1
            if changed<=3 or changed%100==0:print(json.dumps({'changed':changed,'name':desired},ensure_ascii=False),flush=True)
        if changed>=args.limit:break
    print(json.dumps({'changed':changed,'already_clean':skipped,'apply':args.apply}),flush=True)

if __name__=='__main__':main()
