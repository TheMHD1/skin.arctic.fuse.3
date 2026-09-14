"""Add high-quality candidates without replacing existing selections or queues."""
import json
import runpy
from pathlib import Path

ROOT=Path('/data/config/iptv-venom')

def stage(current, catalogue):
    module=runpy.run_path(str(Path(__file__).with_name('venom-curate-channels.py')))
    extended=runpy.run_path(str(Path(__file__).with_name('venom-special-groups.py')))['extend']
    proposed=extended(module['build'](catalogue,120),catalogue,set(),{},True)
    groups={g['id']:{**g,'channels':list(g['channels'])} for g in current['groups'] if not g.get('derived_quality')}
    additions=[]
    for group in proposed['groups']:
        target=groups.setdefault(group['id'],{**group,'channels':[]})
        ids={str(c['stream_id']) for c in target['channels']}
        for c in group['channels']:
            cid=str(c['stream_id'])
            if cid not in ids and module['high_quality_label'](c['name']):
                target['channels'].append(c);ids.add(cid)
                additions.append({'group':group['id'],'stream_id':cid,'name':c['name']})
    result={**current,'groups':list(groups.values())}
    result['unique_channels']=len({str(c['stream_id']) for g in result['groups'] for c in g['channels']})
    return result,additions

if __name__=='__main__':
    path=ROOT/'curated-candidates.json'
    result,added=stage(json.loads(path.read_text()),json.loads((ROOT/'live-catalogue-redacted.json').read_text()))
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2));temp.chmod(0o600);temp.replace(path)
    report={'added':added,'count':len(added)}
    (ROOT/'high-quality-staging-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))
