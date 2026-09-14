"""Add full sports/entertainment candidates; preserve prior queues and records."""
import json
from pathlib import Path
import runpy

ROOT=Path('/data/config/iptv-venom')
if __name__=='__main__':
    path=ROOT/'curated-candidates.json'
    current=json.loads(path.read_text())
    catalogue=json.loads((ROOT/'live-catalogue-redacted.json').read_text())
    extend=runpy.run_path(str(ROOT/'venom-special-groups.py'))['extend']
    result=extend(current,catalogue,set(),{},True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2));temp.chmod(0o600);temp.replace(path)
    print(json.dumps({'unique_candidates':result['unique_channels'],'groups':[{'id':g['id'],'count':len(g['channels'])} for g in result['groups']]},ensure_ascii=False))
