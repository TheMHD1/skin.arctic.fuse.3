import ast
from pathlib import Path
tree=ast.parse(Path(__file__).with_name('ugoos-jellyfin-player.py').read_text())
method=next(x for x in ast.walk(tree) if isinstance(x,ast.FunctionDef) and x.name=='_convert_media_segments')
ns={}
exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),'segment-test','exec'),ns)
convert=lambda items: ns['_convert_media_segments'](None,{'Items':items})
def segment(kind,start,end):return {'Type':kind,'StartTicks':start*1e7,'EndTicks':end*1e7,'ItemId':'item'}
assert convert([]) is None
assert convert([segment('Unknown',0,10)]) is None
assert convert([segment('Intro',-1,3),segment('Intro',3,2),segment('Intro',0,float('nan'))]) is None
items=[segment('Intro',10,20),segment('Intro',10,20),segment('Intro',15,21),segment('Outro',90,100),segment('Outro',110,120)]
result=convert(items)
assert len(result)==3
assert [(x['Type'],x['Start'],x['End']) for x in result.values()]==[('Introduction',10,21),('Credits',90,100),('Credits',110,120)]
assert len(convert([segment('Outro',90,100),segment('Outro',100,110)]))==1
assert len(convert([segment('Intro',0,10),segment('Recap',0,10)]))==2
assert convert(items)==convert(list(reversed(items)))
print('PASS: invalid/unknown, duplicates, overlap, adjacency, separate segments, distinct types, stable ordering')
