"""Execute pinned workers/models against isolated SQLite and delayed fetches."""
import ast,importlib.util,queue,sqlite3,tempfile,threading,types,unittest
from pathlib import Path
from unittest.mock import Mock
import overlay
HERE=Path(__file__).resolve().parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
build=load('transaction_build',HERE.parent/'kodi/build.py')
removal=load('transaction_removal',HERE.parent/'library-removal/overlay.py')

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();root=build.prepare_jellyfin(Path(cls.temp.name))
        cls.before={overlay.LIBRARY:removal.transform((root/'jellyfin_kodi/library.py').read_bytes()),
                    overlay.MOVIES:(root/'jellyfin_kodi/objects/movies.py').read_bytes()}
        cls.after={name:overlay.transform(name,data) for name,data in cls.before.items()}
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def run_worker(self,kind,dbtype,items,failure=None,stop=False,original=False):
        events=[];log=Mock();created=[]
        class LibraryException(Exception):pass
        class LibraryExitException(LibraryException):pass
        with tempfile.TemporaryDirectory() as d:
            def observer():
                for path in Path(d).glob('*.db'):
                    conn=sqlite3.connect(path,timeout=.01)
                    try:conn.execute('INSERT INTO entries VALUES (?)',('external',));conn.commit()
                    finally:conn.close()
                events.append('unlocked')
            class DB:
                def __init__(self,name):self.db_file=name
                def __enter__(self):
                    self.conn=sqlite3.connect(Path(d)/(self.db_file+'.db'),timeout=.01)
                    self.conn.execute('PRAGMA journal_mode=WAL')
                    self.conn.execute('CREATE TABLE IF NOT EXISTS entries (value TEXT)');self.conn.commit()
                    created.append(self);return self
                def __exit__(self,*args):
                    self.conn.commit();self.conn.close();return False
            class Pending:
                def __init__(self):self.items=list(items);self.done=0
                def get(self,timeout):
                    observer() # includes the otherwise one-second empty-queue wait
                    if not self.items:raise queue.Empty
                    return self.items.pop(0)
                def task_done(self):self.done+=1
            class Model:
                def __init__(self,server,jellyfindb,kodidb,path):self.dbs=(kodidb,jellyfindb)
                def __getattr__(self,name):
                    def mutate(item):
                        for db in self.dbs:db.conn.execute('INSERT INTO entries VALUES (?)',(name,))
                        events.append(name)
                        if failure=='exit':raise LibraryExitException()
                        ident=item.get('Id') if isinstance(item,dict) else item
                        if failure==ident:
                            raise ValueError('isolated handler failure')
                    return mutate
            def window(name):
                observer() # GUI stop guard must not hold an open SQLite write
                return stop
            payload=self.before[overlay.LIBRARY] if original else self.after[overlay.LIBRARY]
            node=next(n for n in ast.parse(payload).body if isinstance(n,ast.ClassDef) and n.name==kind)
            namespace={'threading':threading,'Database':DB,'Movies':Model,'TVShows':Model,'MusicVideos':Model,'Music':Model,
                'queue':queue,'LOG':log,'LibraryException':LibraryException,'LibraryExitException':LibraryExitException,
                'window':window,'settings':lambda name:False,'get_sync':lambda:{},
                'excluded_stream_item':lambda item,policy:item.get('Excluded',False),'api':Mock()}
            exec(compile(ast.Module(body=[node],type_ignores=[]),'real-worker','exec'),namespace)
            pending=Pending();lock=threading.Lock()
            args=(pending,queue.Queue(),lock,dbtype,None,False) if kind=='UpdateWorker' else (pending,lock,dbtype,None,False)
            worker=namespace[kind](*args)
            worker.run();observer()
            self.assertEqual(pending.done,len(items) if not stop and failure!='exit' else 1)
            self.assertTrue(worker.is_done)
            self.assertFalse(lock.locked())
            return events,pending,log

    def test_all_three_workers_commit_each_item_before_queue_or_gui_waits(self):
        for kind in ('UpdateWorker','UserDataWorker','RemovedWorker'):
            for dbtype in ('video','music'):
                media='Movie' if dbtype=='video' else 'Audio'
                with self.subTest(worker=kind,db=dbtype):
                    events,pending,log=self.run_worker(kind,dbtype,[{'Id':'a','Type':media,'Name':'a'},{'Id':'b','Type':media,'Name':'b'}])
                    self.assertEqual(sum(event!='unlocked' for event in events),2)
                    self.assertFalse(log.exception.called)
    def test_original_worker_reproduces_sqlite_writer_block_at_gui_wait(self):
        with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):
            self.run_worker('UpdateWorker','video',[{'Id':'a','Type':'Movie','Name':'a'}],original=True)
    def test_collection_removal_dispatch_and_unsupported_skip_survive(self):
        for dbtype,typeset in (('video',('Unknown','Movie','BoxSet','Series','Season','Episode','MusicVideo','Audio')),
                               ('music',('Movie','MusicAlbum','MusicArtist','AlbumArtist','Audio','BoxSet'))):
            items=[{'Id':str(i),'Type':kind} for i,kind in enumerate(typeset)]
            events,pending,log=self.run_worker('RemovedWorker',dbtype,items)
            expected=6 if dbtype=='video' else 4
            self.assertEqual(sum(event!='unlocked' for event in events),expected)
            self.assertEqual(log.warning.call_count,len(items)-expected)
            self.assertFalse(log.exception.called)
    def test_excluded_update_has_one_task_done_and_no_model_write(self):
        events,pending,log=self.run_worker('UpdateWorker','video',[{'Id':'x','Type':'Movie','Excluded':True}])
        self.assertEqual(set(events),{'unlocked'});self.assertFalse(log.exception.called)
    def test_handler_error_preserves_partial_commit_and_next_item(self):
        for kind in ('UpdateWorker','UserDataWorker','RemovedWorker'):
            events,pending,log=self.run_worker(kind,'video',[{'Id':'bad','Type':'Movie','Name':'b'},{'Id':'good','Type':'Movie','Name':'g'}],failure='bad')
            self.assertEqual(sum(event!='unlocked' for event in events),2);self.assertEqual(log.exception.call_count,1)
    def test_stop_and_exit_release_both_writes_and_balance_dequeued_item(self):
        for kind in ('UpdateWorker','UserDataWorker','RemovedWorker'):
            for options in ({'stop':True},{'failure':'exit'}):
                self.run_worker(kind,'video',[{'Id':'a','Type':'Movie','Name':'a'},{'Id':'b','Type':'Movie','Name':'b'}],**options)

    def collection(self,new=False,fail_page=None):
        tree=ast.parse(self.after[overlay.MOVIES]);cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Movies')
        methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('boxset','boxset_current')]
        for method in methods:method.decorator_list=[]
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'video.db';conn=sqlite3.connect(path)
            conn.execute('CREATE TABLE entries (value TEXT)');conn.commit();events=[]
            def write(*args):conn.execute('INSERT INTO entries VALUES (?)',('write',));events.append('write');return 9
            def pages(ident):
                self.assertEqual(ident,'collection')
                for i in range(3):
                    self.assertFalse(conn.in_transaction)
                    other=sqlite3.connect(path,timeout=.01)
                    try:other.execute('INSERT INTO entries VALUES (?)',('outside',));other.commit()
                    finally:other.close()
                    events.append('fetch')
                    if i==fail_page:raise OSError('isolated network interruption')
                    yield {'Items':[{'Id':str(i),'Name':'item'}]}
            api=types.SimpleNamespace(get_overview=lambda value:value,get_all_artwork=lambda value:{})
            ns={'server':types.SimpleNamespace(get_movies_by_boxset=pages),
                'api':types.SimpleNamespace(API=lambda *args:api),'values':lambda *args:(),
                'QU':Mock(),'QUEM':Mock(),'LOG':Mock()}
            exec(compile(ast.Module(body=methods,type_ignores=[]),'real-collection','exec'),ns)
            model=types.SimpleNamespace(server=types.SimpleNamespace(auth=types.SimpleNamespace(server_id='server',get_server_info=lambda ident:{'address':'test'})),
                objects=types.SimpleNamespace(map=lambda *args:{'Id':'collection','Overview':'','Title':'collection'}),
                update_boxset=write,add_boxset=write,set_boxset=write,remove_from_boxset=write,
                artwork=types.SimpleNamespace(add=write),jellyfin_db=types.SimpleNamespace(
                    get_item_id_by_parent_id=lambda *args:[],get_item_by_id=lambda *args:(1,),
                    update_parent_id=write,add_reference=write))
            model.boxset_current=types.MethodType(ns['boxset_current'],model)
            try:
                if fail_page is not None:
                    with self.assertRaises(OSError):ns['boxset'](model,{},None if new else (9,))
                    self.assertNotIn('write',events);self.assertFalse(conn.in_transaction)
                else:
                    ns['boxset'](model,{},None if new else (9,))
                    self.assertEqual(events[:3],['fetch']*3);self.assertTrue(conn.in_transaction)
            finally:conn.rollback();conn.close()
    def test_all_network_pages_precede_collection_sql_for_new_and_existing_sets(self):
        self.collection(new=True);self.collection(new=False)
    def test_first_or_later_network_failure_cannot_leave_partial_collection_writes(self):
        for new in (True,False):
            for page in (0,2):self.collection(new=new,fail_page=page)
    def test_unrelated_ast_is_preserved_and_drift_rejected(self):
        for name in self.before:
            trees=[ast.parse(self.before[name]),ast.parse(self.after[name])]
            for tree in trees:
                for cls in tree.body:
                    if not isinstance(cls,ast.ClassDef):continue
                    remove={'run'} if name==overlay.LIBRARY and cls.name in ('UpdateWorker','UserDataWorker','RemovedWorker') else (
                        {'boxset','boxset_current'} if name==overlay.MOVIES and cls.name=='Movies' else set())
                    cls.body=[n for n in cls.body if not isinstance(n,ast.FunctionDef) or n.name not in remove]
            self.assertEqual(ast.dump(trees[0]),ast.dump(trees[1]))
            with self.assertRaisesRegex(ValueError,'transaction source'):overlay.transform(name,b'foreign')
if __name__=='__main__':unittest.main()
