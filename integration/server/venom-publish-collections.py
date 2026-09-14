"""Publish redacted curated IDs and provider rank to the category plugin."""
import json
from pathlib import Path

root=Path('/data/config/iptv-venom')
native=json.loads((root/'curated-native-channels.json').read_text())
order=json.loads((root/'provider-order.json').read_text())
names=[r['category_name'] for r in order['source_categories']]
assert 100<len(names)<2000 and 200<=native['unique_channels']<=2000
assert all(len(group['channels'])<=1000 for group in native['groups'])
payload={'version':1,'provider_order':names,'groups':native['groups']}
target=Path('/data/config/jellyfin/data/plugins/Live TV Categories_0.3.0.0/channel-collections.json')
temp=target.with_suffix('.tmp');temp.write_text(json.dumps(payload,ensure_ascii=False));temp.chmod(0o644);temp.replace(target)
print(json.dumps({'published_groups':len(native['groups']),'provider_categories':len(names),'channels':native['unique_channels']}))
