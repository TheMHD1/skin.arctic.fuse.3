"""Offline safety and payload tests; never contacts a Kodi device."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load('build')
installer = load('install')
generated = load('generated')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def generated_fixture():
    def params(index):
        return (f'<include content="Row"><param name="id">{502+index}</param>'
                '<param name="content">old</param><param name="include">Old</param>'
                '<param name="target">old</param></include>')
    def standard(index):
        item=502+index
        return (f'<include content="Widget_Row"><param name="id">{item}</param>'
                f'<param name="groupid">{item+200}</param><param name="label">Old</param>'
                '<param name="include">Old</param><content target="old">old</content></include>')
    def selector(index):
        item=502+index
        return (f'<item><label>Old</label><icon>old</icon>'
                f'<property name="guid">guid-{index}</property>'
                f'<property name="widget_id">$NUMBER[{item}]</property></item>')
    def info(index):
        return f'<include content="Search_Info"><param name="id">{502+index}</param></include>'
    return ('<includes>'
            '<include name="skinvariables-searchwidgets-combined">'+''.join(params(i) for i in range(6))+'</include>'
            '<include name="skinvariables-searchwidgets-wall">'+''.join(params(i) for i in range(6))+'</include>'
            '<include name="skinvariables-searchwidgets-standard"><include content="Hub_Widgets_Grouplist">'+''.join(standard(i) for i in range(6))+'</include></include>'
            '<include name="skinvariables-searchwidgets-selector">'+''.join(selector(i) for i in range(6))+'</include>'
            '<include name="skinvariables-searchwidgets-wall-selector">'+''.join(selector(i) for i in range(6))+'</include>'
            '<include name="skinvariables-searchwidgets-info">'+''.join(info(i) for i in range(6))+'</include>'
            '</includes>').encode()


def nodes_fixture():
    return (json.dumps([{'label':'Old','icon':'old','path':'Old','target':'old',
                         'widget_style':'Square','guid':f'guid-{index}'}
                        for index in range(6)],indent=4)+'\n').encode()


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix='library-experience-test-')
        self.addCleanup(self.tempdir.cleanup)
        self.temp = Path(self.tempdir.name)
        self.stage = self.temp/'payload'
        builder.build(self.stage, check_clean=False)
        self.root = self.temp/'kodi'
        self.profile = {'name':'fixture','variant':'local','hostnames':['fixture-host'],
                        'mac':'00:11:22:33:44:55','jellyfin_user_id':'a'*32,
                        'native_paths':{}}
        for name, version in installer.VERSIONS.items():
            path=self.root/'addons'/name/'addon.xml'
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('<addon id="'+name+'" version="'+version+'"/>')
        self.base = {}
        for relative in installer.BASE_HASHES:
            path=self.root/relative
            path.parent.mkdir(parents=True,exist_ok=True)
            if relative==installer.GENERATED:data=generated_fixture()
            elif relative==installer.NODES:data=nodes_fixture()
            else:data=('baseline '+relative).encode()
            path.write_bytes(data);self.base[relative]=sha(data)
        files={relative:digest for relative,digest in self.base.items()
               if 'searchwidgets.json' not in relative and relative!=installer.GENERATED}
        self.manifest=self.root/'addons/plugin.video.habibi.resume/verified-build.json'
        self.manifest.write_text(json.dumps({'versions':installer.VERSIONS,'files':files,
                                             'unrelated':'preserved'},indent=2)+'\n')
        self.generated_output=generated.transform((self.root/installer.GENERATED).read_bytes())
        self.nodes_output=generated.transform_nodes((self.root/installer.NODES).read_bytes())
        self.patches=(mock.patch.object(installer,'BASE_HASHES',self.base),
                      mock.patch.object(installer,'BASE_MANIFEST_HASH',sha(self.manifest.read_bytes())),
                      mock.patch.object(installer,'GENERATED_HASH',sha(self.generated_output)),
                      mock.patch.object(installer,'NODES_HASH',sha(self.nodes_output)))
        for patch in self.patches:
            patch.start();self.addCleanup(patch.stop)

    def snapshot(self):
        return {str(path.relative_to(self.root)):path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def test_payload_and_generated_sections(self):
        self.assertEqual(set(installer.payloads(self.stage)),set(installer.PAYLOAD_HASHES))
        root=ET.fromstring(self.generated_output)
        selector=next(node for node in root.findall('include')
                      if node.get('name')=='skinvariables-searchwidgets-selector')
        self.assertEqual([item.findtext('label').split('$INFO',1)[0] for item in selector],
                         ['Movies','Shows','Venom Movies — Not HD','Venom Shows — Not HD'])
        text=self.generated_output.decode()
        self.assertIn('mode=searchvenommovies&amp;query=',text)
        self.assertNotIn('Albums',text)
        self.assertEqual([row['label'] for row in json.loads(self.nodes_output)],
                         ['Movies','Shows','Venom Movies — Not HD','Venom Shows — Not HD'])

    def test_exact_plan_apply_second_run_and_unrelated_manifest_preserved(self):
        plan=installer.build_changes(self.root,self.stage,self.profile)
        self.assertEqual(len(plan),9)
        backup=self.temp/'backup'
        run=mock.Mock();ready=mock.Mock();idle=mock.Mock()
        self.assertTrue(installer.transaction.deploy(self.root,plan,backup,run=run,
                                                     wait_ready=ready,idle_check=idle))
        record=json.loads(self.manifest.read_text())
        self.assertEqual(record['unrelated'],'preserved')
        self.assertEqual(installer.build_changes(self.root,self.stage,self.profile),{})
        self.assertEqual(run.call_count,2)
        self.assertEqual(idle.call_count,2)

    def test_previous_r7_search_requires_matching_manifest_and_updates_two_paths(self):
        plan=installer.build_changes(self.root,self.stage,self.profile)
        installer.transaction.deploy(self.root,plan,self.temp/'before',run=mock.Mock(),
                                     wait_ready=mock.Mock(),idle_check=mock.Mock())
        relative=installer.TARGETS['home/search.py']
        previous=b'# previous reviewed R7 search fixture\n'
        (self.root/relative).write_bytes(previous)
        with mock.patch.object(installer,'PREVIOUS_SEARCH_HASH',sha(previous)):
            with self.assertRaisesRegex(RuntimeError,'manifest drift'):
                installer.build_changes(self.root,self.stage,self.profile)
            record=json.loads(self.manifest.read_text())
            record['files'][relative]=sha(previous)
            self.manifest.write_text(json.dumps(record,indent=2)+'\n')
            upgrade=installer.build_changes(self.root,self.stage,self.profile)
            self.assertEqual(set(upgrade),{self.root/relative,self.manifest})

    def test_reviewed_generator_reindent_updates_only_manifest(self):
        plan=installer.build_changes(self.root,self.stage,self.profile)
        installer.transaction.deploy(self.root,plan,self.temp/'before',run=mock.Mock(),
                                     wait_ready=mock.Mock(),idle_check=mock.Mock())
        target=self.root/installer.GENERATED
        rebuilt=target.read_bytes()+b'\n\n'
        target.write_bytes(rebuilt)
        with mock.patch.object(installer,'REBUILT_GENERATED_HASH',sha(rebuilt)):
            plan=installer.build_changes(self.root,self.stage,self.profile)
            self.assertEqual(set(plan),{self.manifest})
            record=json.loads(plan[self.manifest])
            self.assertEqual(record['files'][installer.GENERATED],sha(rebuilt))

    def test_drift_and_partial_output_fail_before_writes(self):
        before=self.snapshot()
        target=self.root/installer.TARGETS['home/client.py']
        target.write_bytes(b'unrelated drift')
        drift=self.snapshot()
        with self.assertRaisesRegex(RuntimeError,'Unreviewed or partial'):
            installer.build_changes(self.root,self.stage,self.profile)
        self.assertEqual(self.snapshot(),drift)
        target.write_bytes(before[str(target.relative_to(self.root))])
        (self.stage/'home/client.py').write_bytes(b'unreviewed payload')
        with self.assertRaisesRegex(RuntimeError,'Unreviewed payload'):
            installer.build_changes(self.root,self.stage,self.profile)

    def test_live_identity_and_active_playback_override(self):
        host=self.temp/'hostname';host.write_text('fixture-host\n')
        mac=self.temp/'mac';mac.write_text('00:11:22:33:44:55\n')
        account=self.root/'userdata/addon_data/plugin.video.jellyfin/data.json'
        account.parent.mkdir(parents=True);account.write_text(json.dumps({'Servers':[{'UserId':'a'*32}]}))
        plan=installer.live_plan(self.root,self.stage,self.profile,host,mac)
        self.assertIn(host,plan.expected);self.assertIn(account,plan.expected)
        default=installer.selected_idle_check(False)
        self.assertIs(default,installer.transaction.idle)
        notices=[];override=installer.selected_idle_check(True,notices.append)
        self.assertIsNone(override())
        self.assertIn('stop active or paused',notices[0])
        wrong=dict(self.profile,mac='ff:ff:ff:ff:ff:ff')
        with self.assertRaisesRegex(RuntimeError,'Hardware identity'):
            installer.live_plan(self.root,self.stage,wrong,host,mac)


if __name__=='__main__':
    unittest.main()
