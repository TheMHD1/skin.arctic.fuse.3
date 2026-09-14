"""Snapshot channel identities, refresh guide, then verify name-only changes."""
import json
from pathlib import Path
import runpy
import sys
from urllib.parse import urlencode

root=Path('/data/config/iptv-venom')
api=runpy.run_path('/root/iptv-jellyfin-admin.py')['api']
uid=next(u['Id'] for u in api('/Users') if u['Name'].casefold()=='habibi')
rows=[]
for offset in range(0,20000,500):
    page=api('/LiveTv/Channels?'+urlencode(dict(UserId=uid,StartIndex=offset,Limit=500,AddCurrentProgram=False,EnableImages=False,EnableUserData=True)))
    rows.extend(page['Items'])
    if offset+len(page['Items'])>=page['TotalRecordCount']:break
snapshot={r['Id']:{'name':r['Name'],'number':r.get('ChannelNumber'),'favourite':r.get('UserData',{}).get('IsFavorite',False)} for r in rows}
curated=json.loads((root/'curated-native-channels.json').read_text())
users=api('/Users')
print(json.dumps({'curated_unique':curated['unique_channels'],'groups':{g['id']:len(g['channels']) for g in curated['groups']},'accounts':len(users),'live_enabled':sum(bool(u['Policy'].get('EnableLiveTvAccess')) for u in users)}))
path=root/'channel-names-before.json'
if '--before' in sys.argv:
    if not path.exists():
        path.write_text(json.dumps(snapshot,ensure_ascii=False));path.chmod(0o600)
    print(json.dumps({'snapshot_channels':len(snapshot)}))
elif '--verify' in sys.argv:
    before=json.loads(path.read_text())
    assert set(before)==set(snapshot),'Channel identities changed'
    changed=[(k,before[k]['name'],v['name']) for k,v in snapshot.items() if before[k]['name']!=v['name']]
    assert all(before[k]['number']==v['number'] for k,v in snapshot.items()),'Channel numbers changed'
    # Report favourite differences, without resetting any concurrent user choice.
    print(json.dumps({'stable_ids':len(snapshot),'renamed':len(changed),'examples':changed[:8],'favourite_changes':sum(before[k]['favourite']!=v['favourite'] for k,v in snapshot.items())},ensure_ascii=False))
if '--refresh' in sys.argv:
    task=next(t for t in api('/ScheduledTasks') if t.get('Key')=='RefreshGuide')
    if task['State']=='Idle':api('/ScheduledTasks/Running/'+task['Id'],method='POST')
    print(json.dumps({'refresh_previous_state':task['State']}))
