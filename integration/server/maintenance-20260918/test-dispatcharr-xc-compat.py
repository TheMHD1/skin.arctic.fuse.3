"""Pure URL/credential regression tests: no database, network, or provider access."""
import ast,logging,sys,types,typing,unittest
from pathlib import Path
from unittest.mock import patch
import regex
sys.path.insert(0,'/app')
from apps.m3u.credentials import get_transformed_credentials
tree=ast.parse(Path('/app/apps/proxy/live_proxy/url_utils.py').read_text())
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['_resolve_live_stream_url','transform_url']]
ns={'regex':regex,'logger':logging.getLogger('test'),'Optional':typing.Optional,
    'URL_TRANSFORM_REGEX_TIMEOUT':0.1,'M3UAccount':types.SimpleNamespace(Types=types.SimpleNamespace(XC='XC'))}
exec(compile(ast.Module(body=nodes,type_ignores=[]),'url_utils.py','exec'),ns)
resolve=ns['_resolve_live_stream_url']
N=types.SimpleNamespace
class Tests(unittest.TestCase):
    def setUp(self):
        self.a=N(account_type='XC',server_url='http://provider/base',username='user',password='pass',name='test',pk=1)
        self.s=N(stream_id='441305',url='http://old/live/stale/credentials/441305.ts')
    def profile(self,search=r'^(.*)$',replace='$1'):return N(name='test',pk=1,search_pattern=search,replace_pattern=replace)
    def test_current_login_not_stale_url(self):
        self.assertEqual(resolve(self.s,self.a,self.profile()),'http://provider/base/live/user/pass/441305.ts')
    def test_hls_real_channel(self):
        self.assertEqual(resolve(self.s,self.a,self.profile(r'\.ts$','.m3u8')),'http://provider/base/live/user/pass/441305.m3u8')
    def test_hls_credentials_for_vod(self):
        self.assertEqual(get_transformed_credentials(self.a,self.profile(r'\.ts$','.m3u8')),('http://provider/base','user','pass'))
    def test_credential_rewrite(self):
        self.assertEqual(resolve(self.s,self.a,self.profile('user/pass','other/login')),'http://provider/base/live/other/login/441305.ts')
    def test_live_only_regex(self):
        self.assertEqual(resolve(self.s,self.a,self.profile(r'(?<=/live/)user/pass','other/login')),'http://provider/base/live/other/login/441305.ts')
    def test_unmatched_fails_closed(self):
        self.assertIsNone(resolve(self.s,self.a,self.profile('wrong/login','other/login')))
        self.assertEqual(get_transformed_credentials(self.a,self.profile('wrong/login','other/login')),(None,None,None))
    def test_invalid_synthetic_id_rejected(self):
        self.assertEqual(get_transformed_credentials(self.a,self.profile('1234','5678')),(None,None,None))
    def test_timeout_fails_closed(self):
        with patch('regex.subn',side_effect=TimeoutError):
            self.assertIsNone(resolve(self.s,self.a,self.profile()))
            self.assertEqual(get_transformed_credentials(self.a,self.profile()),(None,None,None))
    def test_missing_login_rejected(self):
        self.a.password='';self.assertIsNone(resolve(self.s,self.a,self.profile()))
    def test_ordinary_m3u_url_still_works(self):
        self.a.account_type='STD'
        self.assertEqual(resolve(self.s,self.a,self.profile()),self.s.url)
    def test_api_base_normalization(self):
        self.a.server_url='http://provider/base/player_api.php?username=ignored'
        self.assertEqual(resolve(self.s,self.a,self.profile()),'http://provider/base/live/user/pass/441305.ts')
unittest.main()
