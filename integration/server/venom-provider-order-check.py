"""Read-only provider-order audit for every enabled Jellyfin account."""
import json
from pathlib import Path
import runpy

def verify(summaries,collections,provider_names):
    expected_pins=['collection-'+g['id'] for g in collections]
    if [s['id'] for s in summaries[:len(expected_pins)]]!=expected_pins:
        raise ValueError('Pinned collections missing or misordered')
    if any(type(s['channelCount']) is not int or s['channelCount']<=0 for s in summaries):
        raise ValueError('Empty or malformed category')
    rest=summaries[len(expected_pins):]
    actual=[s['name'] for s in rest]
    if len(actual)!=len(set(actual)):raise ValueError('Duplicate provider category names')
    known=set(provider_names)
    expected=[name for name in provider_names if name in actual]
    if [name for name in actual if name in known]!=expected:
        raise ValueError('Provider category order differs from source')
    return {'provider_groups':len(rest),'known_ordered':len(expected),'unranked_new_groups':sum(name not in known for name in actual)}

def main():
    root=Path('/data/config/iptv-venom')
    api=runpy.run_path('/root/iptv-jellyfin-admin.py')['api']
    collections=json.loads((root/'curated-native-channels.json').read_text())['groups']
    names=[r['category_name'] for r in json.loads((root/'provider-order.json').read_text())['source_categories']]
    users=api('/Users');results=[]
    for user in users:
        if not user['Policy'].get('EnableLiveTvAccess'):raise ValueError('Missing account Live TV access')
        report=verify(api('/LiveTvCategories?userId='+user['Id']),collections,names)
        results.append(report)
    print(json.dumps({'verified_accounts':len(results),'pinned_groups':len(collections),'provider_counts':sorted(set(r['provider_groups'] for r in results)),'unranked_new_groups':max((r['unranked_new_groups'] for r in results),default=0),'empty_groups':0}))

if __name__=='__main__':main()
