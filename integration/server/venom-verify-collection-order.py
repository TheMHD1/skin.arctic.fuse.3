"""Read-only: compare published collection order to the actual category API."""
import json
from pathlib import Path
import runpy
import sys
from urllib.parse import urlencode

root=Path('/data/config/iptv-venom')
api=runpy.run_path('/root/iptv-jellyfin-admin.py')['api']
manifest=json.loads((root/'curated-native-channels.json').read_text())
users=api('/Users') if '--all-users' in sys.argv else [{'Id':'e8b8de94cf1d443687f6297395efe4ae','Policy':{'EnableLiveTvAccess':True}}]
ids=list(dict.fromkeys(c['id'] for g in manifest['groups'] for c in g['channels']))
for user in users:
    uid=user['Id']
    if not user['Policy'].get('EnableLiveTvAccess'):
        raise RuntimeError('Account missing requested Live TV access: '+uid)
    visible=set()
    for offset in range(0,len(ids),80):
        page=api('/Users/'+uid+'/Items?'+urlencode(dict(Ids=','.join(ids[offset:offset+80]),Limit=80,EnableImages=False)))
        visible.update(item['Id'] for item in page['Items'])
    counts={}
    for group in manifest['groups']:
        expected=[channel['id'] for channel in group['channels'] if channel['id'] in visible]
        actual=[]
        for offset in range(0,max(1,len(expected)),250):
            query=urlencode(dict(userId=uid,startIndex=offset,limit=250,addCurrentProgram=False))
            page=api('/LiveTvCategories/collection-'+group['id']+'/Channels?'+query)
            actual.extend(item['Id'] for item in page['Items'])
            if page['TotalRecordCount']!=len(expected):
                raise RuntimeError('Collection count mismatch: '+uid+' '+group['id'])
        if expected!=actual:raise RuntimeError('Collection ordering/visibility mismatch: '+uid+' '+group['id'])
        counts[group['id']]=len(actual)
    print(json.dumps({'user_id':uid,'groups':counts,'exact_order_and_visibility_verified':True}),flush=True)
print(json.dumps({'verified_accounts':len(users),'manifest_channels':len(ids)}),flush=True)
