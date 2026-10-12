"""Execute real transformed XC functions with no Django/provider dependencies."""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import sys

spec = importlib.util.spec_from_file_location('build',Path(__file__).with_name('build.py'))
build = importlib.util.module_from_spec(spec);spec.loader.exec_module(build)


class HeadTests(unittest.TestCase):
    def setUp(self):
        self.allowed=True;self.entitled=True;self.present=True;self.get_calls=[]
        self.user=SimpleNamespace(custom_properties={'xc_password':'test-secret'})
        relation=SimpleNamespace(movie=SimpleNamespace(uuid='movie-id'),episode=SimpleNamespace(uuid='episode-id'))
        test=self
        class Query:
            def select_related(self,*a):return self
            def filter(self,**kw):return self
            def order_by(self,*a):return self
            def first(self):return relation if test.present else None
        model=SimpleNamespace(objects=Query(),DoesNotExist=LookupError,MultipleObjectsReturned=LookupError)
        self.imports=patch.dict(sys.modules,{'apps.vod.models':SimpleNamespace(M3UMovieRelation=model,M3UEpisodeRelation=model)})
        self.imports.start();self.addCleanup(self.imports.stop)
        class Response(dict):
            def __init__(self,body=None,status=200,content_type=None):
                super().__init__();self.status_code=status;self.streaming=content_type is not None
                if content_type:self['Content-Type']=content_type
                self.body=body
        def stream(*args):self.get_calls.append(args);return Response(status=222)
        self.scope={'get_object_or_404':lambda *a,**kw:self.user,'User':object,
                    'network_access_allowed':lambda *a:self.allowed,
                    'is_vod_movies_enabled':lambda **kw:self.entitled,
                    'is_vod_series_enabled':lambda **kw:self.entitled,
                    'Response':Response,'JsonResponse':Response,'StreamingHttpResponse':Response,
                    'infer_content_type_from_url':lambda url:'video/mp4',
                    'stream_vod':stream}
        tree=ast.parse(build.rewrite(Path(__file__).with_name('xc_routes.fixture.py').read_text()))
        tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
        for n in tree.body:n.decorator_list=[]
        exec(compile(tree,'reviewed-xc-fixture','exec'),self.scope)

    def call(self,kind='episode',method='HEAD',password='test-secret'):
        request=SimpleNamespace(method=method,GET={});request._request=request
        return self.scope['stream_xc_'+kind](request,'test-user',password,10,'mp4')

    def test_drift_rejected(self):
        with self.assertRaises(ValueError): build.transform(b'unreviewed')

    def test_only_xc_get_head_targets(self):
        source=Path(__file__).with_name('build.py').read_text()
        self.assertIn('"stream_xc_movie"',source)
        self.assertIn('"stream_xc_episode"',source)
        self.assertIn('StreamingHttpResponse(iter(())',source)
        self.assertNotIn('max_streams =',source)
        self.assertNotIn('release_profile_slot(',source)

    def test_episode_head_has_no_stream_or_fake_size(self):
        response=self.call()
        self.assertEqual(response.status_code,200);self.assertTrue(response.streaming)
        self.assertEqual(response['Content-Type'],'video/mp4')
        self.assertEqual(response['Accept-Ranges'],'bytes')
        self.assertNotIn('Content-Length',response);self.assertEqual(self.get_calls,[])

    def test_movie_head_has_no_stream(self):
        self.assertEqual(self.call('movie').status_code,200);self.assertEqual(self.get_calls,[])

    def test_bad_password_rejected_both(self):
        for kind in ('movie','episode'):self.assertEqual(self.call(kind,password='wrong').status_code,401)
        self.assertEqual(self.get_calls,[])

    def test_missing_password_rejected(self):
        self.user.custom_properties={};self.assertEqual(self.call().status_code,401)

    def test_network_denial_preserved(self):
        self.allowed=False;self.assertEqual(self.call().status_code,403)

    def test_entitlement_denial_preserved(self):
        self.entitled=False
        for kind in ('movie','episode'):self.assertEqual(self.call(kind).status_code,403)

    def test_missing_relation_rejected(self):
        self.present=False
        for kind in ('movie','episode'):self.assertEqual(self.call(kind).status_code,404)

    def test_real_get_unchanged(self):
        for kind in ('movie','episode'):
            self.assertEqual(self.call(kind,'GET').status_code,222)
            self.assertEqual(self.get_calls[-1][1:3],(kind,kind+'-id'))


if __name__=='__main__':unittest.main()
