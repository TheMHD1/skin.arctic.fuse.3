"""Add only the requested provider-family candidates without resetting old work."""
import json
import runpy
from pathlib import Path
root=Path('/data/config/iptv-venom')
extend=runpy.run_path(str(root/'venom-special-groups.py'))['extend']
path=root/'curated-candidates.json'
result=extend(json.loads(path.read_text()),json.loads((root/'live-catalogue-redacted.json').read_text()),set(),{},True)
tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2));tmp.chmod(0o600);tmp.replace(path)
print(json.dumps({'groups':[(g['id'],len(g['channels'])) for g in result['groups'][-2:]]}))
