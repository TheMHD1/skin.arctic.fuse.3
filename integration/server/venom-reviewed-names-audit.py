"""Read-only comparison of every curated channel against reviewed display names."""
import json
import runpy
from pathlib import Path
from urllib.parse import urlencode

root = Path('/data/config/iptv-venom')
api = runpy.run_path('/root/iptv-jellyfin-admin.py')['api']
clean = runpy.run_path(str(root/'venom-channel-names.py'))['clean_name']
source = json.loads((root/'curated-channels.json').read_text())
native = json.loads((root/'curated-native-channels.json').read_text())
expected = {str(c['stream_id']): clean(c['name']) for g in source['groups'] for c in g['channels']}
ids = {c['id']: str(c['gateway_id']) for g in native['groups'] for c in g['channels']}
uid = next(u['Id'] for u in api('/Users') if u['Name'].lower() == 'habibi')
actual = {}
keys = list(ids)
for offset in range(0, len(keys), 80):
    result = api('/Users/'+uid+'/Items?'+urlencode({'Ids':','.join(keys[offset:offset+80]), 'Limit':80, 'EnableImages':'false'}))
    actual.update({c['Id']:c['Name'] for c in result['Items']})
mismatches = [{'id':iid, 'actual':actual.get(iid), 'expected':expected[gid]} for iid,gid in ids.items() if actual.get(iid)!=expected[gid]]
print(json.dumps({'groups':len(native['groups']), 'unique_channels':len(ids), 'matched':len(ids)-len(mismatches), 'mismatches':mismatches}, ensure_ascii=False))
