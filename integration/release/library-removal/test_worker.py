"""Execute the real patched RemovedWorker against isolated queue/database mocks."""
import ast,importlib.util,queue,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock
import overlay
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('removal_clean_build',HERE.parent/'kodi/build.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)

class Pending:
    def __init__(self,items):self.items=list(items);self.done=0
    def get(self,timeout):
        if not self.items:raise queue.Empty
        return self.items.pop(0)
    def task_done(self):self.done+=1
class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        source=build.prepare_jellyfin(Path(cls.temp.name))/'jellyfin_kodi/library.py'
        cls.before=source.read_bytes();cls.output=overlay.transform(cls.before)
        cls.movies=(source.parent/'objects/movies.py').read_text()
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def worker(self,dbtype,items,raise_on=None,stop=False):
        calls=[];log=Mock()
        class LibraryException(Exception):pass
        class LibraryExitException(LibraryException):pass
        class DB:
            def __init__(self,name):self.db_file=name
            def __enter__(self):return self
            def __exit__(self,*args):return False
        def model(kind):
            class Model:
                def __init__(self,*args):pass
                def remove(self,ident):
                    calls.append((kind,ident))
                    if raise_on==ident:raise ValueError('isolated failure')
                    if raise_on=='exit':raise LibraryExitException()
            return Model
        tree=ast.parse(self.output)
        cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='RemovedWorker')
        namespace={'threading':threading,'Database':DB,'Movies':model('movie'),'TVShows':model('tv'),
            'MusicVideos':model('musicvideo'),'Music':model('music'),'queue':queue,'LOG':log,
            'LibraryException':LibraryException,'LibraryExitException':LibraryExitException,'window':lambda name:stop}
        exec(compile(ast.Module(body=[cls],type_ignores=[]),'real-removed-worker','exec'),namespace)
        pending=Pending(items);worker=namespace['RemovedWorker'](pending,threading.Lock(),dbtype,None,False)
        worker.run();return worker,pending,calls,log
    def test_unknown_first_and_after_valid_items_never_reuse_previous_handler(self):
        rows=[{'Id':str(i),'Type':kind} for i,kind in enumerate(('Unknown','Movie','Unknown','BoxSet','Audio','Episode'))]
        worker,pending,calls,log=self.worker('video',rows)
        self.assertEqual(calls,[('movie','1'),('movie','3'),('tv','5')])
        self.assertEqual(log.warning.call_count,3);self.assertFalse(log.exception.called)
        self.assertTrue(worker.is_done);self.assertEqual(pending.done,len(rows))
    def test_all_video_and_music_types_are_routed_to_their_own_database(self):
        for dbtype,expected in (('video',{'Movie':'movie','BoxSet':'movie','Series':'tv','Season':'tv','Episode':'tv','MusicVideo':'musicvideo'}),
                                ('music',dict.fromkeys(('MusicAlbum','MusicArtist','AlbumArtist','Audio'),'music'))):
            rows=[{'Id':kind,'Type':kind} for kind in expected]
            worker,pending,calls,log=self.worker(dbtype,rows)
            self.assertEqual(calls,[(expected[kind],kind) for kind in expected])
            self.assertEqual(pending.done,len(rows));self.assertTrue(worker.is_done)
            self.assertFalse(log.exception.called)
    def test_cross_database_types_and_missing_type_do_not_delete_anything(self):
        for dbtype,kind in (('video','Audio'),('music','Movie'),('music','BoxSet')):
            worker,pending,calls,log=self.worker(dbtype,[{'Id':'x','Type':kind},{'Id':'y'}])
            self.assertEqual(calls,[]);self.assertEqual(pending.done,2);self.assertTrue(worker.is_done)
            self.assertEqual(log.warning.call_count,2);self.assertFalse(log.exception.called)
    def test_handler_failure_and_missing_id_leave_queue_balanced_and_allow_next_item(self):
        rows=[{'Id':'fail','Type':'Movie'},{'Type':'BoxSet'},{'Id':'good','Type':'Episode'}]
        worker,pending,calls,log=self.worker('video',rows,raise_on='fail')
        self.assertEqual(calls,[('movie','fail'),('tv','good')]);self.assertEqual(log.exception.call_count,2)
        self.assertEqual(pending.done,3);self.assertTrue(worker.is_done)
    def test_stop_and_library_exit_keep_existing_exit_semantics(self):
        for options in ({'stop':True},{'raise_on':'exit'}):
            worker,pending,calls,_=self.worker('video',[{'Id':'x','Type':'BoxSet'},{'Id':'y','Type':'Movie'}],**options)
            self.assertEqual(calls,[('movie','x')]);self.assertEqual(pending.done,1)
            self.assertEqual(len(pending.items),1);self.assertTrue(worker.is_done)
    def test_only_removed_worker_run_changes_and_unknown_source_is_rejected(self):
        left,right=ast.parse(self.before),ast.parse(self.output)
        for tree in (left,right):
            cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='RemovedWorker')
            cls.body=[node for node in cls.body if not isinstance(node,ast.FunctionDef) or node.name!='run']
        self.assertEqual(ast.dump(left),ast.dump(right))
        with self.assertRaisesRegex(ValueError,'removal source'):overlay.transform(b'foreign')
        # Movies.remove already has the correct supported set/collection path.
        self.assertIn('elif obj["Media"] == "set":',self.movies)
        self.assertIn('self.delete_boxset(',self.movies)

if __name__=='__main__':unittest.main()
