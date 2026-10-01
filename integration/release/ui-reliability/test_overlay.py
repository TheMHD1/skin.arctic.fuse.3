import ast
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import overlay


class Tests(unittest.TestCase):
    def test_unknown_source_rejected(self):
        for name in overlay.BEFORE:
            with self.assertRaises(ValueError):overlay.transform(name,b'unknown')

    def test_rating_predicate_uses_info_labels_not_variables(self):
        self.assertNotIn('$VAR',overlay.RATING)
        self.assertTrue(overlay.RATING.startswith('['))
        self.assertTrue(overlay.RATING.endswith(']'))
        for name in ('imdb','tmdb','Habibi.Rating.Community'):
            self.assertIn(name,overlay.RATING)

    def test_bridge_scopes_cache_and_bounds(self):
        source=overlay.bridge('def library_index():\n    pass\n\ndef route(item):\n    pass\n')
        tree=ast.parse(source)
        func=tree.body[0]
        module=ast.Module(body=[func],type_ignores=[])
        props={};calls=[];auth={'Servers':[{'address':'https://example.invalid','UserId':'test','AccessToken':'one'}]}
        class File:
            def __init__(self,path):self.path=path
            def exists(self):return True
            def read_text(self):return json.dumps(auth if self.path.endswith('data.json') else {'movies':['owned']})
        class Window:
            def getProperty(self,key):return props.get(key,'')
            def setProperty(self,key,value):props[key]=value
        class Client:
            def __init__(self,server,scopes):self.user=server['UserId'];self.scopes=scopes
            def scope_ids(self,kind):return ['owned'] if kind=='movies' else []
            def request(self,path,**params):
                calls.append(params)
                return {'Items':[{'Id':'1','Type':'Movie','ProviderIds':{'Tmdb':'99'}}]}
        import time
        env={'sys':sys,'json':json,'time':time,'Path':File,
             'xbmcgui':types.SimpleNamespace(Window=lambda _:Window()),
             'xbmcvfs':types.SimpleNamespace(translatePath=lambda p:p)}
        with patch.dict(sys.modules,{'client':types.SimpleNamespace(Client=Client)}):
            exec(compile(module,'bridge','exec'),env)
            self.assertIn('movie:99',env['library_index']())
            env['library_index']();self.assertEqual(len(calls),1)
            self.assertEqual(calls[0]['ParentId'],'owned')
            self.assertEqual(calls[0]['IncludeItemTypes'],'Movie')
            self.assertLessEqual(calls[0]['timeout'],2)
            auth['Servers'][0]['AccessToken']='two'
            env['library_index']();self.assertEqual(len(calls),2)
            props['Habibi.Home.Refresh']='changed'
            env['library_index']();self.assertEqual(len(calls),3)
            # A huge owned root is bounded and never cached as complete.
            props.clear();calls.clear()
            def huge(self,path,**params):
                calls.append(params)
                return {'Items':[{'Id':str(n),'Type':'Movie','ProviderIds':{}} for n in range(500)]}
            Client.request=huge
            env['library_index']()
            self.assertEqual(len(calls),8)
            self.assertNotIn('Habibi.Discover.OwnedIndex.v2',props)

    def test_focus_waits_for_visible_results_and_respects_new_navigation(self):
        # Test the actual transformed apply_entries method from the reviewed
        # common browser plus the remote-specific restoration anchor.
        source=(HERE.parents[1]/'plugin.video.venom.tv/browser.py').read_text()
        tree=ast.parse(source)
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Browser')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='apply_entries')
        text=ast.get_source_segment(source,method)
        text=text.replace('        self.render()',"        self.render()\n        if snapshot.get('focus_grid_when_ready'):\n            self.focus_grid_when_ready=False\n            if self.visible_entries and self.getFocusId() in (910,920):\n                self.setFocusId(920)")
        env={'PAGE':80,'catalogue':types.SimpleNamespace(search_text=lambda s:s)}
        exec(text,env)
        obj=types.SimpleNamespace(closed=False,kind='live',render=lambda:None,
            visible_entries=[1],getFocusId=lambda:910,setFocusId=lambda v:setattr(obj,'focus',v))
        snapshot={'query':'','page':0,'focus_grid_when_ready':True}
        env['apply_entries'](obj,snapshot,[]);self.assertEqual(obj.focus,920)
        obj.focus=901;obj.getFocusId=lambda:901
        env['apply_entries'](obj,snapshot,[]);self.assertEqual(obj.focus,901)
        obj.visible_entries=[];obj.getFocusId=lambda:910
        env['apply_entries'](obj,snapshot,[]);self.assertEqual(obj.focus,901)


if __name__=='__main__':unittest.main()
