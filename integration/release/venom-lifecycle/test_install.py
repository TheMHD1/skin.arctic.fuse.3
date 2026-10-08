import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import install

class Tests(unittest.TestCase):
    def fixture(self,root):
        source=root/'.kodi'/install.overlay.BROWSER
        other=root/'.kodi/addons/unchanged.py'
        source.parent.mkdir(parents=True);source.write_bytes(b'input')
        other.parent.mkdir(parents=True,exist_ok=True);other.write_bytes(b'unchanged')
        hub=root/'.kodi'/install.overlay.HUB;hub.parent.mkdir(parents=True,exist_ok=True);hub.write_bytes(b'hub-input')
        raw={'files':{install.overlay.BROWSER:install.sha(b'input'),'addons/unchanged.py':install.sha(b'unchanged'),
                     install.overlay.HUB:install.sha(b'hub-input')},
             'am9_venom_entry_release':install.previous.RELEASE}
        path=root/install.MANIFEST;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(raw,indent=2,sort_keys=True)+'\n')
        output=b'output';raw['files'][install.overlay.BROWSER]=install.sha(output)
        raw['files'][install.overlay.HUB]=install.sha(b'hub-output')
        raw['am9_venom_lifecycle_release']=install.RELEASE
        final=install.sha((json.dumps(raw,indent=2,sort_keys=True)+'\n').encode())
        expected={p:p.read_bytes() for p in (source,other,hub,path)}
        return output,final,expected
    def test_both_cohorts_compose_preserve_identity_and_are_idempotent(self):
        for cohort in ('local','remote'):
            with self.subTest(cohort=cohort),tempfile.TemporaryDirectory() as d:
                root=Path(d);output,digest,expected=self.fixture(root)
                network=root/'.cache/connman/own/settings';network.parent.mkdir(parents=True);network.write_bytes(b'own')
                with patch.object(install.shared,'identity',return_value={}), \
                     patch.object(install.previous,'plan',return_value=install.transaction.Plan({},expected)), \
                     patch.object(install.overlay,'transform',return_value=output), \
                     patch.object(install.overlay,'hub',return_value=b'hub-output'), \
                     patch.object(install,'HUB_AFTER',install.sha(b'hub-output')), \
                     patch.dict(install.AFTER,{cohort:install.sha(output)}),patch.dict(install.FINAL,{cohort:digest}):
                    changes=install.plan(root,{'cohort':cohort})
                    self.assertEqual(len(changes),4);self.assertEqual(changes.expected[network],b'own')
                    for path,data in changes.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                    self.assertFalse(install.plan(root,{'cohort':cohort}))
                    (root/'.kodi/addons/unchanged.py').write_bytes(b'drift')
                    with self.assertRaisesRegex(ValueError,'source drift'):install.plan(root,{'cohort':cohort})
    def test_foreign_receipt_parent_and_symlink_fail_closed(self):
        for obstacle in ('receipt','parent','symlink'):
            with self.subTest(obstacle=obstacle),tempfile.TemporaryDirectory() as d:
                root=Path(d);output,digest,expected=self.fixture(root)
                with patch.object(install.shared,'identity',return_value={}), \
                     patch.object(install.previous,'plan',return_value=install.transaction.Plan({},expected)), \
                     patch.object(install.overlay,'transform',return_value=output), \
                     patch.object(install.overlay,'hub',return_value=b'hub-output'), \
                     patch.object(install,'HUB_AFTER',install.sha(b'hub-output')), \
                     patch.dict(install.AFTER,{'remote':install.sha(output)}),patch.dict(install.FINAL,{'remote':digest}):
                    path=root/(install.previous.RECEIPT if obstacle=='parent' else install.RECEIPT)
                    path.parent.mkdir(parents=True,exist_ok=True)
                    if obstacle=='symlink':path.symlink_to(root/install.MANIFEST)
                    else:path.write_bytes(b'foreign')
                    with self.assertRaises(ValueError):install.plan(root,{'cohort':'remote'})
    def test_public_receipt_has_no_identity_or_credentials(self):
        for cohort in ('local','remote'):
            self.assertEqual(set(json.loads(install.receipt(cohort,install.FINAL[cohort]))),
                             {'schema','release','cohort','manifest_sha256','acceptance'})
    def test_only_exact_failed_interim_candidate_can_migrate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);output,digest,expected=self.fixture(root)
            path=root/install.MANIFEST;manifest=json.loads(path.read_bytes())
            manifest['am9_venom_lifecycle_release']=install.RELEASE
            raw=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode();path.write_bytes(raw)
            interim=install.sha(raw);target=root/install.RECEIPT;target.parent.mkdir(parents=True)
            target.write_bytes(install.receipt('remote',interim))
            with patch.object(install.shared,'identity',return_value={}), \
                 patch.dict(install.INTERIMS,{interim:install.sha(b'input')}), \
                 patch.object(install.overlay,'hub',return_value=b'hub-output'), \
                 patch.object(install,'HUB_AFTER',install.sha(b'hub-output')), \
                 patch.dict(install.AFTER,{'remote':install.sha(output)}),patch.dict(install.FINAL,{'remote':digest}), \
                 patch.object(install.overlay,'replace',return_value=output.decode()):
                changes=install.plan(root,{'cohort':'remote'});self.assertEqual(len(changes),4)
                (root/'.kodi/addons/unchanged.py').write_bytes(b'drift')
                with self.assertRaisesRegex(ValueError,'Interim source drift'):install.plan(root,{'cohort':'remote'})

if __name__=='__main__':unittest.main()
