import contextlib,importlib.util,io,json,os,types,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('revisions',Path(__file__).with_name('venom-series-revisions.py'))
revisions=importlib.util.module_from_spec(spec);spec.loader.exec_module(revisions)
class Tests(unittest.TestCase):
    def test_revisions_are_order_independent_deduplicated_and_identity_sensitive(self):
        self.assertEqual(revisions.revision(['2',1,2]),revisions.revision([1,2]))
        self.assertNotEqual(revisions.revision([1,2]),revisions.revision([1,3]))
        with self.assertRaises(ValueError):revisions.revision([0])
    def test_weekly_success_cache_is_bypassed_only_for_new_identity_revision(self):
        old=(100,'ok');now=101
        self.assertTrue(revisions.due(old,None,'new',now))
        self.assertTrue(revisions.due(old,'old','new',now))
        self.assertFalse(revisions.due(old,'new','new',now))
        self.assertFalse(revisions.due(old,'old',None,now))
        self.assertTrue(revisions.due(old,'new','new',100+604800))
        self.assertTrue(revisions.due(None,None,None,now))
    def test_failed_or_empty_detail_fetches_keep_six_hour_backoff(self):
        for status in ('error','empty'):
            self.assertFalse(revisions.due((100,status),'old','new',101))
            self.assertTrue(revisions.due((100,status),'old','new',21700))
        self.assertTrue(revisions.due((100,'ok'),'new','new',101,canary=True))
    def test_query_maps_xc_relation_ids_to_all_active_provider_episode_ids(self):
        calls=[]
        class Rows:
            def __init__(self,rows):self.rows=rows
            def filter(self,**kwargs):calls.append(kwargs);return self
            def values_list(self,*args):calls.append(args);return self
            def distinct(self):return self
            def order_by(self,*args):return self
            def iterator(self,**kwargs):return iter(self.rows)
            def __iter__(self):return iter(self.rows)
        models=types.ModuleType('apps.vod.models')
        models.M3USeriesRelation=types.SimpleNamespace(objects=Rows([(101,10),(102,10),(103,20)]))
        models.M3UEpisodeRelation=types.SimpleNamespace(objects=Rows([(10,1),(10,2),(20,3)]))
        django=types.ModuleType('django');django.setup=lambda:None
        output=io.StringIO()
        with patch.dict('sys.modules',{'django':django,'apps.vod.models':models}),patch.dict(os.environ),contextlib.redirect_stdout(output):
            exec(compile(revisions.QUERY,'read-only-revision-query','exec'),{})
        result=json.loads(output.getvalue())['revisions']
        self.assertEqual(result,{'101':revisions.revision([1,2]),'102':revisions.revision([1,2]),'103':revisions.revision([3])})
        self.assertEqual(calls[0],{'m3u_account__is_active':True});self.assertEqual(calls[1],('id','series_id'))
        self.assertIn(('episode__series_id','episode_id'),calls)
    def test_loader_is_bounded_and_accepts_django_informational_prefix(self):
        def run(args,**kwargs):
            self.assertEqual(kwargs['timeout'],20);self.assertTrue(kwargs['check'])
            return types.SimpleNamespace(stdout='INFO startup\n'+json.dumps({'schema':1,'revisions':{'1':revisions.revision([2])}}))
        self.assertEqual(revisions.load(run),{'1':revisions.revision([2])})
        for payload in ({'schema':0,'revisions':{}},{'schema':1,'revisions':{'bad':'x'}},{'schema':1,'revisions':{'1':'secret'}}):
            with self.assertRaises(ValueError):revisions.load(lambda *a,**k:types.SimpleNamespace(stdout=json.dumps(payload)))
    def test_exporter_stores_post_fetch_ids_and_retains_legacy_safety_limits(self):
        source=Path(__file__).with_name('venom-jellyfin-export.py').read_text()
        compile(source,'exporter','exec')
        self.assertIn('series_revisions.revision(episode_ids)',source)
        self.assertIn('args.max_seconds',source);self.assertIn('args.series_limit',source)
        self.assertIn('fcntl.LOCK_EX|fcntl.LOCK_NB',source);self.assertIn('MIN_FREE_BYTES=8*1024*1024*1024',source)
        self.assertIn("current=revisions.get(item_id)",source)
        self.assertIn("episode_identity_revision_deferred",source)
    def test_installer_accepts_only_known_sources_and_is_idempotent(self):
        import tempfile
        spec=importlib.util.spec_from_file_location('freshness_install',Path(__file__).with_name('venom-series-freshness-install.py'))
        install=importlib.util.module_from_spec(spec);spec.loader.exec_module(install)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';target=root/'target';source.mkdir();target.mkdir()
            for name in install.AFTER:(source/name).write_bytes(b'new')
            (target/install.EXPORT).write_bytes(b'old')
            with patch.object(install,'HERE',source),patch.object(install,'BEFORE',install.sha(b'old')),patch.dict(install.AFTER,dict.fromkeys(install.AFTER,install.sha(b'new'))):
                writes,expected=install.plan(target);self.assertEqual(len(writes),2)
                for path,data in writes.items():path.write_bytes(data)
                self.assertFalse(install.plan(target)[0])
                (target/install.EXPORT).write_bytes(b'foreign')
                with self.assertRaisesRegex(ValueError,'Unreviewed'):install.plan(target)
if __name__=='__main__':unittest.main()
