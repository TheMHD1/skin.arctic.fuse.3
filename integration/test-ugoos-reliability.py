import ast
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

root=Path(__file__).parent
sys.path.insert(0,str(root/'plugin.video.habibi.resume'))
from integrity import check
from client import Client

with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp)/'patched.py';p.write_text('verified')
    manifest={'files':{'patched.py':hashlib.sha256(p.read_bytes()).hexdigest()}}
    assert check(tmp,manifest)==[]
    p.write_text('upstream update')
    assert len(check(tmp,manifest))==1
    assert p.read_text()=='upstream update' # Guard must never overwrite anything.

source=root/'kodiseerr-upstream/plugin.video.kodiseerr'
def functions(filename,names,env):
    tree=ast.parse((source/filename).read_text(encoding='utf-8-sig'))
    selected=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names]
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(filename),'exec'),env)

from urllib.parse import urlencode
env={'urlencode':urlencode}
functions('jellyfin_bridge.py',{'route','favorite_menu'},env)
movie={'Id':'a'*32,'Type':'Movie','UserData':{'IsFavorite':True}}
url,folder=env['route'](movie)
assert 'plugin.video.jellyfin/' in url and 'server=' not in url and not folder
assert env['favorite_menu'](movie)[0]=='Remove from Jellyfin Favorites'
series=dict(movie,Type='Series')
url,folder=env['route'](series)
assert 'mode=series' in url and folder

for response in (None,{'mediaInfo':{'status':2}},{'mediaInfo':{'status':3}},{'mediaInfo':{'status':5}}):
    calls=[]
    def api(endpoint,**kw):
        calls.append(kw.get('method','GET'))
        return response
    env={'api_client':NS(client=NS(api_request=api)),
         'xbmcgui':NS(Dialog=lambda:NS(ok=lambda *a:None,notification=lambda *a:None),NOTIFICATION_ERROR=3),
         'cache':NS(clear=lambda:None)}
    functions('requests_view.py',{'do_request'},env)
    env['do_request']('movie','1288445')
    assert calls==['GET'],calls
print('PASS: update guard detects drift without writing; exact playback/favorite routes; fresh duplicate/offline request guards')
