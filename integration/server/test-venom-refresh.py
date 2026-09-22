import ast
import fcntl
import json
import os
from pathlib import Path
import tempfile
import types
import unittest

class Tests(unittest.TestCase):
    def run_helper(self, root, status='Idle', fail=False):
        calls=[]
        def api(path, **kwargs):
            if path=='/Library/VirtualFolders':return [{'Name':'Venom Movies','ItemId':'m','RefreshStatus':status}]
            calls.append(path)
            if fail:raise RuntimeError('server unavailable')
        tree=ast.parse(Path(__file__).with_name('venom-jellyfin-libraries.py').read_text())
        node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='main')
        ns=dict(ROOT=root,api=api,names={'Venom Movies':('movies','/config/venom-catalogue/movies')},
                sys=types.SimpleNamespace(argv=['helper','--refresh']),json=json,os=os,fcntl=fcntl,
                shutil=types.SimpleNamespace(disk_usage=lambda p:types.SimpleNamespace(free=20*1024**3)))
        exec(compile(ast.Module(body=[node],type_ignores=[]),'refresh-test','exec'),ns)
        ns['main']();return calls

    def test_unchanged_export_does_not_repeat_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(len(self.run_helper(root)),1)
            self.assertEqual(self.run_helper(root),[])
            (root/'refresh-dirty-movies').write_text('new-generation')
            self.assertEqual(len(self.run_helper(root)),1)

    def test_queued_retains_dirty_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(self.run_helper(root,'Queued'),[])
            self.assertFalse((root/'refresh-requested.json').exists())
            self.assertEqual(len(self.run_helper(root)),1)

    def test_failed_request_not_acknowledged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaises(RuntimeError):self.run_helper(root,fail=True)
            self.assertFalse((root/'refresh-requested.json').exists())

if __name__=='__main__':unittest.main()
