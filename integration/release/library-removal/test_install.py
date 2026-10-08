import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import install
class Tests(unittest.TestCase):
    def fixture(self,root):
        source=root/'.kodi'/install.overlay.SOURCE;source.parent.mkdir(parents=True);source.write_bytes(b'input')
        other=root/'.kodi/addons/untouched.py';other.write_bytes(b'untouched')
        manifest={'files':{install.overlay.SOURCE:install.sha(b'input'),'addons/untouched.py':install.sha(b'untouched')},
            'am9_venom_lifecycle_release':install.previous.RELEASE}
        path=root/install.MANIFEST;path.parent.mkdir(parents=True);path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
        manifest['files'][install.overlay.SOURCE]=install.sha(b'output');manifest['am9_library_removal_release']=install.RELEASE
        digest=install.sha((json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode())
        return digest,{p:p.read_bytes() for p in (source,other,path)}
    def test_both_cohorts_compose_and_repeat_without_changes(self):
        for cohort in ('local','remote'):
            with self.subTest(cohort=cohort),tempfile.TemporaryDirectory() as d:
                root=Path(d);digest,expected=self.fixture(root)
                network=root/'.cache/connman/own/settings';network.parent.mkdir(parents=True);network.write_bytes(b'own')
                with patch.object(install.shared,'identity',return_value={}), \
                     patch.object(install.previous,'plan',return_value=install.transaction.Plan({},expected)), \
                     patch.object(install.overlay,'transform',return_value=b'output'), \
                     patch.object(install,'AFTER',install.sha(b'output')),patch.dict(install.FINAL,{cohort:digest}):
                    changes=install.plan(root,{'cohort':cohort});self.assertEqual(len(changes),3)
                    self.assertEqual(changes.expected[network],b'own')
                    for path,data in changes.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                    self.assertFalse(install.plan(root,{'cohort':cohort}))
                    (root/'.kodi/addons/untouched.py').write_bytes(b'drift')
                    with self.assertRaisesRegex(ValueError,'source drift'):install.plan(root,{'cohort':cohort})
    def test_foreign_or_symlink_receipt_and_parent_drift_fail_closed(self):
        for obstacle in ('receipt','symlink','parent'):
            with self.subTest(obstacle=obstacle),tempfile.TemporaryDirectory() as d:
                root=Path(d);digest,expected=self.fixture(root)
                with patch.object(install.shared,'identity',return_value={}), \
                     patch.object(install.previous,'plan',return_value=install.transaction.Plan({},expected)), \
                     patch.object(install.overlay,'transform',return_value=b'output'), \
                     patch.object(install,'AFTER',install.sha(b'output')),patch.dict(install.FINAL,{'remote':digest}):
                    item=root/(install.previous.RECEIPT if obstacle=='parent' else install.RECEIPT)
                    item.parent.mkdir(parents=True)
                    if obstacle=='symlink':item.symlink_to(root/install.MANIFEST)
                    else:item.write_bytes(b'foreign')
                    with self.assertRaises(ValueError):install.plan(root,{'cohort':'remote'})
    def test_identity_errors_are_not_suppressed_and_receipts_contain_no_secrets(self):
        with tempfile.TemporaryDirectory() as d,patch.object(install.shared,'identity',side_effect=ValueError('wrong account')):
            with self.assertRaisesRegex(ValueError,'wrong account'):install.plan(Path(d),{'cohort':'remote'})
        self.assertEqual(set(json.loads(install.receipt('remote',install.FINAL['remote']))),
            {'schema','release','cohort','manifest_sha256','acceptance'})
if __name__=='__main__':unittest.main()
