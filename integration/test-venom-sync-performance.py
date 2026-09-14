"""Prove excluded scan events do not fetch full metadata or enter Kodi writers."""
import ast
from contextlib import nullcontext
from pathlib import Path
import queue
import threading
import types
import unittest

class Input(queue.Queue):
    def get(self, *args, **kwargs):return super().get(block=False)

class Tests(unittest.TestCase):
    def worker(self, responses):
        source=ast.parse((Path(__file__).parent/'venom-jellyfin-downloader.py').read_text())
        node=next(x for x in source.body if isinstance(x,ast.ClassDef) and x.name=='GetItemWorker')
        calls=[]
        def request(req, session):
            calls.append(dict(req['params']))
            result=responses.pop(0)
            if isinstance(result,Exception):raise result
            return result
        ns={'threading':threading,'queue':queue,'requests':types.SimpleNamespace(Session=lambda:nullcontext()),
            'api':types.SimpleNamespace(info=lambda:'FULL'), 'window':lambda *a:False,
            'HTTPException':type('HTTPException',(Exception,),{}),
            'LOG':types.SimpleNamespace(info=lambda *a:None,error=lambda *a:None,exception=lambda *a:None)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'downloader-test','exec'),ns)
        source=Input();source.put(['iptv','normal']);out={'Movie':queue.Queue()};accepted=[]
        worker=ns['GetItemWorker'](types.SimpleNamespace(http=types.SimpleNamespace(request=request)),source,out,
            lambda item:item.get('Path','').startswith('/iptv/'),lambda:accepted.append(True))
        worker.run()
        self.assertEqual(source.unfinished_tasks,0)
        return calls,out,accepted

    def test_all_excluded_never_full_download_or_writer(self):
        calls,out,count=self.worker([{'Items':[{'Id':'iptv','Path':'/iptv/movie','Type':'Movie'}]}])
        self.assertEqual(len(calls),1);self.assertEqual(calls[0]['Fields'],'Path')
        self.assertTrue(out['Movie'].empty());self.assertEqual(count,[])

    def test_mixed_keeps_normal_update(self):
        item={'Id':'normal','Path':'/media/movie','Type':'Movie'}
        calls,out,count=self.worker([{'Items':[{'Id':'iptv','Path':'/iptv/movie'},item]},{'Items':[item]}])
        self.assertEqual(calls[1]['Ids'],'normal');self.assertEqual(calls[1]['Fields'],'FULL')
        self.assertEqual(out['Movie'].get(),item);self.assertEqual(len(count),1)

    def test_errors_release_queue_accounting(self):
        calls,out,count=self.worker([RuntimeError('network')])
        self.assertEqual(count,[]);self.assertTrue(out['Movie'].empty())

if __name__=='__main__':unittest.main()
