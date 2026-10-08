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
        names=list(install.overlay.BEFORE[cohort])+['addons/unchanged/source.py']
        before={}
        for name in names:
            path=root/'.kodi'/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(('input:'+name).encode());before[path]=path.read_bytes()
        manifest={'files':{name:install.sha(before[root/'.kodi'/name]) for name in names},'am9_ux_release':install.previous.RELEASE}
        path=root/install.MANIFEST;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n');before[path]=path.read_bytes()
        outputs={name:install.sha(('output:'+name).encode()) for name in install.overlay.BEFORE[cohort]}
        outputs[install.overlay.HELPER]=install.sha((HERE/'favorite_refresh.py').read_bytes())
        final={**manifest,'files':{**manifest['files'],**outputs},'am9_performance_release':install.RELEASE}
        digest=install.sha((json.dumps(final,indent=2,sort_keys=True)+'\n').encode())
        return before,outputs,digest

    def test_complete_snapshot_and_idempotence_both_cohorts(self):
        for cohort in ('local','remote'):
            with self.subTest(cohort=cohort),tempfile.TemporaryDirectory() as d:
                root=Path(d);before,outputs,digest=self.fixture(root,cohort)
                protected=root/'.cache/connman/wifi-own/settings';protected.parent.mkdir(parents=True);protected.write_bytes(b'own network')
                with patch.object(install.shared,'identity',return_value={}), \
                     patch.object(install.previous,'plan',return_value=install.transaction.Plan({},before)) as parent, \
                     patch.dict(install.AFTER,{cohort:outputs}),patch.dict(install.FINAL,{cohort:digest}), \
                     patch.object(install.overlay,'transform',side_effect=lambda n,d,c:('output:'+n).encode()):
                    changes=install.plan(root,{'cohort':cohort});parent.assert_called_once()
                    self.assertEqual(len(changes),6);self.assertEqual(changes.expected[protected],b'own network')
                    for path,data in changes.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                    self.assertFalse(install.plan(root,{'cohort':cohort}))
                    (root/'.kodi/addons/unchanged/source.py').write_bytes(b'drift')
                    with self.assertRaisesRegex(ValueError,'source drift'):install.plan(root,{'cohort':cohort})

    def test_foreign_helper_receipt_and_symlink_fail_closed(self):
        for obstacle in ('helper','receipt','symlink'):
            with self.subTest(obstacle=obstacle),tempfile.TemporaryDirectory() as d:
                root=Path(d);before,outputs,digest=self.fixture(root,'remote')
                with patch.object(install.shared,'identity',return_value={}), \
                     patch.object(install.previous,'plan',return_value=install.transaction.Plan({},before)), \
                     patch.dict(install.AFTER,{'remote':outputs}),patch.dict(install.FINAL,{'remote':digest}), \
                     patch.object(install.overlay,'transform',side_effect=lambda n,d,c:('output:'+n).encode()):
                    if obstacle=='receipt':
                        path=root/install.RECEIPT;path.parent.mkdir(parents=True);path.write_bytes(b'foreign')
                    else:
                        path=root/'.kodi'/install.overlay.HELPER
                        if obstacle=='helper':path.write_bytes(b'foreign')
                        else:path.symlink_to(root/install.MANIFEST)
                    with self.assertRaises(ValueError):install.plan(root,{'cohort':'remote'})

    def test_helper_pin_is_same_for_both_and_no_private_receipt_fields(self):
        for cohort in ('local','remote'):
            self.assertEqual(install.AFTER[cohort][install.overlay.HELPER],install.sha((HERE/'favorite_refresh.py').read_bytes()))
            value=json.loads(install.receipt(cohort,install.FINAL[cohort]))
            self.assertEqual(set(value),{'schema','release','cohort','manifest_sha256','acceptance'})

if __name__=='__main__':unittest.main()
