"""Read-only audit: distinguish missing initial seeding from later removals."""
import json
from pathlib import Path
import runpy
import sqlite3

ROOT=Path('/data/config/iptv-venom')

def main():
    api=runpy.run_path('/root/iptv-jellyfin-admin.py')['api']
    items=runpy.run_path(str(ROOT/'venom-seed-favourites.py'))['user_items']
    groups=json.loads((ROOT/'curated-native-channels.json').read_text())['groups']
    ids=set(c['id'] for g in groups for c in g['channels'])
    db=sqlite3.connect('file:'+str(ROOT/'seed-favourites.sqlite3')+'?mode=ro',uri=True)
    results=[]
    for user in api('/Users'):
        uid=user['Id'];rows=items(api,uid,sorted(ids))
        visible={r['Id'] for r in rows}
        favourites={r['Id'] for r in rows if r.get('UserData',{}).get('IsFavorite')}
        done={r[0] for r in db.execute("select item_id from seeds where user_id=? and status='done'",(uid,))}
        result={'user_id':uid,'live_enabled':bool(user['Policy'].get('EnableLiveTvAccess')),
                'expected':len(ids),'visible':len(ids&visible),'favourites':len(ids&favourites),
                'unseeded':len(ids-done),'previously_seeded_now_removed':len((ids&done&visible)-favourites)}
        results.append(result);print(json.dumps(result),flush=True)
    print(json.dumps({'accounts':len(results),'missing_visibility':sum(r['expected']-r['visible'] for r in results),
                      'unseeded_total':sum(r['unseeded'] for r in results),
                      'disabled_live':sum(not r['live_enabled'] for r in results)}),flush=True)

if __name__=='__main__':main()
