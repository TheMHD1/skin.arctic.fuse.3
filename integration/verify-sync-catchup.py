"""Isolated 2.2 tests, run through check-catchup.py rather than the legacy suite."""
import ast,json,unittest
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parent
def method(file,name,namespace):
    node=next(n for n in ast.walk(ast.parse(file.read_text())) if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(file),'exec'),namespace)
    return namespace[name]

class CatchupTests(unittest.TestCase):
    def test_api_exclusions_are_json_not_a_type_filter(self):
        fn=method(ROOT/'venom-jellyfin-api.py','get_sync_queue',{'json':json})
        target=SimpleNamespace(_get=lambda path,params:(path,params))
        path,query=fn(target,'DATE','music',['/iptv/movies/','/iptv/series/'])
        self.assertEqual('music',query['filter'])
        self.assertEqual(['/iptv/movies/','/iptv/series/'],json.loads(query['excludePathPrefixes']))
        self.assertTrue(path.endswith('/GetItems'))

    def test_default_request_remains_backwards_compatible(self):
        fn=method(ROOT/'venom-jellyfin-api.py','get_sync_queue',{'json':json})
        target=SimpleNamespace(_get=lambda path,params:params)
        self.assertEqual({'LastUpdateDT':'DATE','filter':'None'},fn(target,'DATE'))

    def exclusions(self,whitelist,excluded):
        calls=[]
        client=SimpleNamespace(get_item=lambda ident:{'CollectionType':'movies'},get_sync_queue=lambda *args,**kwargs:calls.append(kwargs))
        policy={'Whitelist':whitelist,'ExcludedLibraryPaths':excluded}
        env={'get_sync':lambda:policy,'settings':lambda key:'DATE','LOG':SimpleNamespace(info=lambda *args:None)}
        fn=method(ROOT/'venom-jellyfin-library.py','fast_sync',env)
        self.assertTrue(fn(SimpleNamespace(server=SimpleNamespace(jellyfin=client))))
        return calls[0]['excluded_paths']

    def test_only_explicit_unsynced_roots_excluded(self):
        self.assertEqual(['/iptv/'],self.exclusions(['normal'],{'/iptv/':'iptv'}))

    def test_selected_library_overrides_exclusion(self):
        self.assertEqual([],self.exclusions(['Mixed:iptv'],{'/iptv/':'iptv'}))

    def test_missing_policy_excludes_nothing(self):
        self.assertEqual([],self.exclusions(['normal'],{}))

if __name__=='__main__':unittest.main()
