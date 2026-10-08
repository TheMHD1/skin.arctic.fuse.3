import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import install

class Tests(unittest.TestCase):
    def fixture(self,root,cohort):
        paths=[install.overlay.BROWSER,install.overlay.SERVICE]
        manifest=root/install.MANIFEST;manifest.parent.mkdir(parents=True)
        files={}
        for name in paths:
            p=root/'.kodi'/name;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(('before:'+name).encode());files[name]=install.sha(p.read_bytes())
        manifest.write_text(json.dumps({'files':files},sort_keys=True))
        after={name:install.sha(('after:'+name).encode()) for name in paths}
        after[install.overlay.SELECTOR]=install.sha((HERE/'search_selection.py').read_bytes())
        final={'files':after,'am9_ux_release':install.RELEASE}
        final_sha=install.sha((json.dumps(final,indent=2,sort_keys=True)+'\n').encode())
        original={p:p.read_bytes() for p in [manifest]+[root/'.kodi'/n for n in paths]}
        return original,after,final_sha

    def test_both_cohorts_compose_once_and_final_is_idempotent(self):
        for cohort in ('local','remote'):
            with self.subTest(cohort=cohort),tempfile.TemporaryDirectory() as d:
                root=Path(d);original,after,final=self.fixture(root,cohort)
                profile={'cohort':cohort,'AccessToken':'never-in-receipt'}
                with patch.object(install.shared,'identity',return_value={}), \
                     patch.object(install.shared,'plan',return_value=install.transaction.Plan({},original)), \
                     patch.dict(install.AFTER,{cohort:after}),patch.dict(install.FINAL,{cohort:final}), \
                     patch.object(install.overlay,'transform',side_effect=lambda n,d,c:('after:'+n).encode()):
                    changes=install.plan(root,profile);self.assertEqual(len(changes),5)
                    self.assertFalse(any('/userdata/' in str(p) for p in changes))
                    for p,data in changes.items():p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
                    self.assertFalse(install.plan(root,profile))
                    self.assertNotIn(b'never-in-receipt',(root/install.RECEIPT).read_bytes())
                    (root/'.kodi'/install.overlay.BROWSER).write_bytes(b'drift')
                    with self.assertRaisesRegex(ValueError,'source drift'):install.plan(root,profile)

    def test_unreviewed_final_manifest_and_existing_helper_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);original,after,final=self.fixture(root,'remote')
            profile={'cohort':'remote'}
            with patch.object(install.shared,'identity',return_value={}), \
                 patch.object(install.shared,'plan',return_value=install.transaction.Plan({},original)), \
                 patch.dict(install.AFTER,{'remote':after}),patch.dict(install.FINAL,{'remote':final}), \
                 patch.object(install.overlay,'transform',side_effect=lambda n,d,c:('after:'+n).encode()):
                p=root/'.kodi'/install.overlay.SELECTOR;p.write_bytes(b'foreign')
                with self.assertRaisesRegex(ValueError,'existing'):install.plan(root,profile)
                p.unlink()
                m=root/install.MANIFEST;m.write_text(json.dumps({'files':{},'am9_ux_release':install.RELEASE}))
                with self.assertRaisesRegex(ValueError,'final UX manifest'):install.plan(root,profile)

    def test_both_output_pins_reproduce_without_private_sources(self):
        common=HERE.parents[1]/'plugin.video.venom.tv/browser.py'
        local=install.shared.local_overlay.transform(install.overlay.BROWSER,common.read_bytes())
        remote=install.shared.remote.overlay.browser(
            install.shared.local_overlay.ui.browser(self.remote_base(common)))
        for cohort,data in [('local',local),('remote',remote.encode())]:
            name=install.overlay.BROWSER
            self.assertEqual(install.sha(install.overlay.transform(name,data,cohort)),install.AFTER[cohort][name])
        source=HERE.parents[1]/'plugin.video.habibi.resume/service.py'
        for cohort in ('local','remote'):
            name=install.overlay.SERVICE
            self.assertEqual(install.sha(install.overlay.transform(name,source.read_bytes(),cohort)),install.AFTER[cohort][name])

    def remote_base(self,common):
        import shutil,subprocess
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);shutil.copytree(common.parent,p/'addon')
            subprocess.run(['git','apply',str(HERE.parents[1]/'patches/venom-remote-performance.patch')],cwd=p/'addon',check=True)
            return (p/'addon/browser.py').read_text()

    def test_reviewed_interim_migrates_with_receipt_and_full_drift_guards(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cohort='remote';profile={'cohort':cohort}
            inputs={install.overlay.BROWSER:b'browser System.HasModalDialog',
                    install.overlay.SERVICE:b'service System.HasModalDialog',
                    install.overlay.SELECTOR:b'previous helper',
                    'addons/unmodified.py':b'preserved'}
            for name,data in inputs.items():
                p=root/'.kodi'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            old={'files':{n:install.sha(v) for n,v in inputs.items()},'am9_ux_release':install.RELEASE}
            path=root/install.MANIFEST;path.parent.mkdir(parents=True,exist_ok=True)
            raw=(json.dumps(old,indent=2,sort_keys=True)+'\n').encode();path.write_bytes(raw)
            old_sha=install.sha(raw)
            output={n:install.sha(inputs[n].replace(b'System.HasModalDialog',b'System.HasActiveModalDialog'))
                    for n in (install.overlay.BROWSER,install.overlay.SERVICE)}
            output[install.overlay.SELECTOR]=install.sha((HERE/'search_selection.py').read_bytes())
            final={**old,'files':{**old['files'],**output}}
            final_sha=install.sha((json.dumps(final,indent=2,sort_keys=True)+'\n').encode())
            receipt=root/install.RECEIPT;receipt.parent.mkdir(parents=True,exist_ok=True)
            receipt.write_text(json.dumps({'schema':1,'release':install.RELEASE,'cohort':cohort,
                'manifest_sha256':old_sha,'acceptance':'installed-source-live-checks-separate'},indent=2,sort_keys=True)+'\n')
            with patch.object(install.shared,'identity',return_value={}), \
                 patch.object(install.overlay,'remote_handoff',side_effect=lambda s:s), \
                 patch.dict(install.INTERIM,{cohort:{old_sha:{n:old['files'][n] for n in output}}}), \
                 patch.dict(install.AFTER,{cohort:output}),patch.dict(install.FINAL,{cohort:final_sha}):
                untouched=root/'.kodi/addons/unmodified.py';untouched.write_bytes(b'drift')
                with self.assertRaisesRegex(ValueError,'Interim source drift'):install.plan(root,profile)
                untouched.write_bytes(b'preserved')
                changes=install.plan(root,profile);self.assertEqual(len(changes),5)
                for p,data in changes.items():p.write_bytes(data)
                self.assertFalse(install.plan(root,profile))

if __name__=='__main__':unittest.main()
