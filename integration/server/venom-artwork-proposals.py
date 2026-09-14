"""Offline logo research worksheet; never changes live artwork."""
import json,re,runpy
from pathlib import Path
root=Path(__file__).parent
clean=runpy.run_path(str(root/'venom-channel-names.py'))['clean_name']
key=runpy.run_path(str(root/'venom-reviewed-artwork.py'))['key']
def norm(s):return re.sub(r'[^A-Z0-9]','',s.upper())
channels=json.loads(Path('/tmp/iptv-channels.json').read_text())
logos=json.loads(Path('/tmp/iptv-logos.json').read_text())
available={l['channel']:l for l in logos if l['in_use'] and l['format']=='PNG'}
manifest=json.loads(Path('/tmp/curated-now.json').read_text())
seen=set()
for group in manifest['groups']:
    for row in group['channels']:
        label=key(clean(row['name']))
        if label in seen:continue
        seen.add(label)
        matches=[c for c in channels if c['id'] in available and norm(c['name'])==norm(label)]
        preferred=[c for c in matches if c['country'].lower() in (['ca'] if group['id']=='en-canada' else ['uk','us','ca','it'] if group['id'].startswith('en-') else ['sa','ae','qa','eg','jo','sy','lb'])]
        print(json.dumps({'name':label,'matches':[{'id':c['id'],'name':c['name']} for c in preferred or matches]},ensure_ascii=False))
