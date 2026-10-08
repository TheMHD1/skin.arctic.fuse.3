import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import install
class Tests(unittest.TestCase):
    def fixture(self,root):
        expected={};manifest={'files':{},'am9_library_removal_release':install.previous.RELEASE}
        for name in (*install.overlay.BEFORE,'addons/untouched.py'):
            source=root/'.kodi'/name;source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes(b'input')
            expected[source]=b'input'
            if name!=install.overlay.MOVIES:manifest['files'][name]=install.sha(b'input')
        path=root/install.MANIFEST;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n');expected[path]=path.read_bytes()
        for name in install.overlay.BEFORE:manifest['files'][name]=install.sha(b'output')
        manifest['am9_library_transactions_release']=install.RELEASE
        digest=install.sha((json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode())
        return digest,expected
    def test_both_cohorts_compose_add_inventory_and_repeat_without_changes(self):
        for cohort in ('local','remote'):
            with self.subTest(cohort=cohort),tempfile.TemporaryDirectory() as d:
                root=Path(d);digest,expected=self.fixture(root)
                network=root/'.cache/connman/own/settings';network.parent.mkdir(parents=True);network.write_bytes(b'own')
                after=dict.fromkeys(install.overlay.BEFORE,install.sha(b'output'))
                with patch.object(install.shared,'identity',return_value={}), \
                     patch.object(install.previous,'plan',return_value=install.transaction.Plan({},expected)), \
                     patch.object(install.overlay,'transform',return_value=b'output'), \
                     patch.dict(install.AFTER,after),patch.dict(install.FINAL,{cohort:digest}):
                    changes=install.plan(root,{'cohort':cohort});self.assertEqual(len(changes),4)
                    self.assertEqual(changes.expected[network],b'own')
                    for path,data in changes.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                    self.assertFalse(install.plan(root,{'cohort':cohort}))
                    (root/'.kodi'/install.overlay.MOVIES).write_bytes(b'drift')
                    with self.assertRaisesRegex(ValueError,'source drift'):install.plan(root,{'cohort':cohort})
    def test_foreign_symlink_or_parent_receipt_fails_closed(self):
        for obstacle in ('receipt','symlink','parent'):
            with self.subTest(obstacle=obstacle),tempfile.TemporaryDirectory() as d:
                root=Path(d);digest,expected=self.fixture(root)
                with patch.object(install.shared,'identity',return_value={}), \
                     patch.object(install.previous,'plan',return_value=install.transaction.Plan({},expected)), \
                     patch.object(install.overlay,'transform',return_value=b'output'), \
                     patch.dict(install.AFTER,dict.fromkeys(install.overlay.BEFORE,install.sha(b'output'))), \
                     patch.dict(install.FINAL,{'remote':digest}):
                    item=root/(install.previous.RECEIPT if obstacle=='parent' else install.RECEIPT);item.parent.mkdir(parents=True)
                    if obstacle=='symlink':item.symlink_to(root/install.MANIFEST)
                    else:item.write_bytes(b'foreign')
                    with self.assertRaises(ValueError):install.plan(root,{'cohort':'remote'})
    def test_newly_inventoried_file_is_protected_by_transaction_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);digest,expected=self.fixture(root)
            # It was absent from the parent's inventory/expected snapshot.
            movies=root/'.kodi'/install.overlay.MOVIES;expected.pop(movies)
            with patch.object(install.shared,'identity',return_value={}), \
                 patch.object(install.previous,'plan',return_value=install.transaction.Plan({},expected)), \
                 patch.object(install.overlay,'transform',return_value=b'output'), \
                 patch.dict(install.AFTER,dict.fromkeys(install.overlay.BEFORE,install.sha(b'output'))), \
                 patch.dict(install.FINAL,{'remote':digest}):
                changes=install.plan(root,{'cohort':'remote'})
                self.assertEqual(changes.expected[movies],b'input')
    def test_identity_errors_and_public_receipt_fields(self):
        with tempfile.TemporaryDirectory() as d,patch.object(install.shared,'identity',side_effect=ValueError('wrong account')):
            with self.assertRaisesRegex(ValueError,'wrong account'):install.plan(Path(d),{'cohort':'remote'})
        for cohort in ('local','remote'):
            self.assertEqual(set(json.loads(install.receipt(cohort,install.FINAL[cohort]))),
                {'schema','release','cohort','manifest_sha256','acceptance'})
if __name__=='__main__':unittest.main()
