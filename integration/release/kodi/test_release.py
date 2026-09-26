import importlib.util,json,shutil,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import Mock

HERE=Path(__file__).resolve().parent;FORK=HERE.parents[2]
sys.argv_payload=None;generated=None
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module
transaction=load('transaction',HERE/'transaction.py');installer=load('release_install',HERE/'install.py');builder=load('release_build',HERE/'build.py')

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='portable-release-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'kodi';self.payload=Path(self.temp.name)/'payload'
        # Use generated outputs supplied by the caller/test launcher.
        source=Path(sys.argv_payload) if sys.argv_payload else None
        if source:shutil.copytree(source,self.payload)
        else:self.skipTest('payload fixture not supplied')
        versions=installer.VERSIONS
        for name,version in versions.items():
            addon=self.root/'addons'/name;addon.mkdir(parents=True,exist_ok=True)
            (addon/'addon.xml').write_text('<addon id="'+name+'" version="'+version+'"/>')
        copies={
          'addons/plugin.video.habibi.resume/client.py':HERE/'baseline-r6/client.py',
          'addons/plugin.video.habibi.resume/default.py':HERE/'baseline-r6/default.py',
          'addons/skin.arctic.fuse.3/shortcuts/generator/data/setup/search_path.xml':HERE/'baseline-r6/search_path.xml',
          installer.SEARCH_SKIN:HERE/'baseline-r6/Includes_Search.xml',
        }
        for relative,source_path in copies.items():
            target=self.root/relative;target.parent.mkdir(parents=True,exist_ok=True)
            if relative==installer.SEARCH_SKIN:
                data=source_path.read_bytes();self.assertEqual(data[-1:],b'\n');target.write_bytes(data[:-1])
            else:shutil.copy2(source_path,target)
        home=self.root/'addons/plugin.video.habibi.resume';shutil.copy2(self.payload/'search.py',home/'search.py')
        http=self.root/'addons/plugin.video.jellyfin/jellyfin_kodi/jellyfin/http.py';http.parent.mkdir(parents=True);shutil.copy2(self.payload/'jellyfin/http.py',http)
        venom=self.root/'addons/plugin.video.venom.tv'
        for name in installer.VENOM_OUT:shutil.copy2(self.payload/'venom'/name,venom/name)
        helper=self.root/'addons/plugin.video.jellyfin/jellyfin_kodi/helper';helper.mkdir(parents=True)
        for name in installer.NATIVE_OUT:
            src=self.payload/(name if name=='native_originals.py' else 'jellyfin/'+name);shutil.copy2(src,helper/name)
        jfdata=self.root/'userdata/addon_data/plugin.video.jellyfin';jfdata.mkdir(parents=True)
        (jfdata/'settings.xml').write_text('<settings><setting id="useDirectPaths">1</setting><setting id="playFromStream">true</setting><setting id="playFromTranscode">false</setting></settings>')
        self.profile={'name':'fixture','variant':'local','hostnames':['fixture','CoreELEC'],'mac':'00:11:22:33:44:55','jellyfin_user_id':'a'*32,
                      'native_paths':{'/media/movies/':'nfs://192.168.1.2/movies/'}}
        (jfdata/'data.json').write_text(json.dumps({'Servers':[{'UserId':'a'*32,'paths':self.profile['native_paths']}]}))
        files={}
        for path in self.root.rglob('*'):
            if path.is_file() and path.name!='verified-build.json':files[str(path.relative_to(self.root))]=installer.sha(path.read_bytes())
        manifest=home/'verified-build.json';manifest.write_text(json.dumps({'versions':versions,'files':files,'review_scope':'fixture'},indent=2)+'\n')

    def test_already_installed_exact_cohort_is_idempotent(self):
        self.assertEqual(installer.build_changes(self.root,self.payload,self.profile),{})

    def test_remote_exact_jellyfin_cohort_is_idempotent(self):
        venom=self.root/'addons/plugin.video.venom.tv'
        for name in installer.REMOTE_OUT:
            source=self.payload/('venom/shared_favorites.py' if name=='shared_favorites.py' else 'remote-venom/'+name)
            shutil.copy2(source,venom/name)
        marker=self.root/'userdata/addon_data/plugin.video.venom.tv/remote-native.json';marker.parent.mkdir(parents=True,exist_ok=True)
        marker.write_text('{"enabled":true,"reason":"Remote-house profile: authenticated Jellyfin catalogue and playback, no private gateway dependency"}\n')
        settings=self.root/'userdata/addon_data/plugin.video.jellyfin/settings.xml'
        settings.write_text('<settings><setting id="useDirectPaths">0</setting><setting id="playFromStream">true</setting><setting id="playFromTranscode">false</setting></settings>')
        manifest=self.root/'addons/plugin.video.habibi.resume/verified-build.json';record=json.loads(manifest.read_text())
        for name in installer.REMOTE_OUT:record['files']['addons/plugin.video.venom.tv/'+name]=installer.sha((venom/name).read_bytes())
        manifest.write_text(json.dumps(record,indent=2)+'\n')
        profile={**self.profile,'variant':'remote','native_paths':{}}
        self.assertEqual(installer.build_changes(self.root,self.payload,profile),{})

    def test_unrelated_whole_file_drift_and_stale_manifest_fail(self):
        client=self.root/'addons/plugin.video.habibi.resume/client.py';client.write_text(client.read_text()+'\n# drift\n')
        with self.assertRaisesRegex(RuntimeError,'whole-file'):installer.build_changes(self.root,self.payload,self.profile)
        self.setUp()
        manifest=self.root/'addons/plugin.video.habibi.resume/verified-build.json';data=json.loads(manifest.read_text())
        data['files']['addons/plugin.video.habibi.resume/client.py']='0'*64;manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(RuntimeError,'manifest drift'):installer.build_changes(self.root,self.payload,self.profile)

    def test_profile_rejects_extra_fields(self):
        path=Path(self.temp.name)/'profile.json';path.write_text(json.dumps({**self.profile,'token':'no'}))
        with self.assertRaisesRegex(RuntimeError,'unknown/missing'):installer.load_profile(path)

    def test_remote_profile_requires_canonical_public_host_and_local_rejects_it(self):
        path=Path(self.temp.name)/'remote-profile.json'
        remote={**self.profile,'variant':'remote','native_paths':{},
                'remote_public_host':'jellyfin.example.test'}
        path.write_text(json.dumps(remote))
        self.assertEqual(installer.load_profile(path)['remote_public_host'],'jellyfin.example.test')
        path.write_text(json.dumps({**remote,'remote_public_host':'HTTPS://JELLYFIN.EXAMPLE.TEST'}))
        with self.assertRaisesRegex(RuntimeError,'canonical public hostname'):installer.load_profile(path)
        path.write_text(json.dumps({**self.profile,'remote_public_host':'jellyfin.example.test'}))
        with self.assertRaisesRegex(RuntimeError,'Local profile'):installer.load_profile(path)

    def test_remote_unowned_bridge_is_exact_not_a_manifest_bypass(self):
        for relative,digest in installer.REMOTE_UNTRACKED_BASE.items():
            args=[relative,digest,None,installer.REMOTE_UNTRACKED_MANIFEST,True]
            self.assertTrue(installer.reviewed_untracked_remote(*args))
            for index,bad in [(0,'addons/unreviewed/file.py'),(1,'0'*64),
                              (2,'0'*64),(3,'0'*64),(4,False)]:
                changed=list(args);changed[index]=bad
                self.assertFalse(installer.reviewed_untracked_remote(*changed))

    def test_keyboard_interrupt_rolls_back_written_file(self):
        root=Path(self.temp.name)/'transaction';root.mkdir();target=root/'file';target.write_bytes(b'old')
        plan=transaction.Plan({target:b'new'},{target:b'old'});starts=0
        def run(args,**kwargs):
            nonlocal starts
            if args[1]=='start':
                starts+=1
                if starts==1:raise KeyboardInterrupt()
            return types.SimpleNamespace(returncode=0)
        with self.assertRaisesRegex(RuntimeError,'originals restored'):transaction.deploy(root,plan,Path(self.temp.name)/'backup',run=run,idle_check=lambda:None,wait_ready=lambda:None)
        self.assertEqual(target.read_bytes(),b'old');self.assertEqual(starts,2)

if __name__=='__main__':
    if len(sys.argv)>1:sys.argv_payload=sys.argv.pop(1)
    else:
        generated=tempfile.TemporaryDirectory(prefix='portable-release-built-')
        sys.argv_payload=str(Path(generated.name)/'payload');builder.build(sys.argv_payload)
    unittest.main()
