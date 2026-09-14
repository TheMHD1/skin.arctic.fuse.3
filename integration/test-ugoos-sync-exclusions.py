"""Explicit unsynced paths must skip ancestry calls without hiding selected libraries."""
import ast
import logging
from pathlib import Path
from types import SimpleNamespace

tree=ast.parse(Path(__file__).with_name('ugoos-jellyfin-utils.py').read_text())
fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='find_library')
fn.body=[n for n in fn.body if not isinstance(n,ast.ImportFrom)]
sync={'Whitelist':['main'],'ExcludedLibraryPaths':{'/config/venom-catalogue/movies/':'venom'}}
ns={'get_sync':lambda:sync,'LOG':logging.getLogger(__name__)}
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<sync>','exec'),ns)
calls=[]
server=SimpleNamespace(jellyfin=SimpleNamespace(get_ancestors=lambda item:calls.append(item) or [{'Id':'main'},{'Id':'venom'}]))
find=ns['find_library']
assert find(server,{'Id':'1','Path':'/config/venom-catalogue/movies/Movie 1/movie.strm'})=={}
assert not calls
assert find(server,{'Id':'2','Path':'/media/Movies/movie.mkv'})['Id']=='main'
assert calls==['2']
sync['Whitelist']=['Mixed:venom']
assert find(server,{'Id':'3','Path':'/config/venom-catalogue/movies/Movie 1/movie.strm'})['Id']=='venom'
assert calls==['2','3']
assert find(server,{'Id':'4'})['Id']=='venom'
print('PASS: excluded sync avoids API fanout; normal paths, selected libraries and missing paths retain ancestry lookup')
