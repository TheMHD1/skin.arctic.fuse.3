import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import install


class Tests(unittest.TestCase):
    def fixture(self, root):
        browser=root/install.BROWSER;browser.parent.mkdir(parents=True)
        browser.write_bytes(b'fixture-browser')
        manifest=root/install.MANIFEST;manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({'files':{
            install.BROWSER.removeprefix('.kodi/'):install.sha(browser.read_bytes())}}))
        worker=root/'.config/fixture-backup.py';worker.parent.mkdir()
        worker.write_text(install.snapshot_overlay.OLD_IMPORT+'\n'
                          +install.snapshot_overlay.OLD_LOOP+'\n    pass\n')
        policy=root/'.config/device_backup_policy.py';policy.write_bytes(b'old-policy')
        return worker,policy,manifest

    def test_idempotency_selection_and_drift_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);worker,policy,manifest=self.fixture(root)
            digest=install.sha(worker.read_bytes())
            after=json.loads(manifest.read_text())
            after['files'][install.BROWSER.removeprefix('.kodi/')]=install.sha(b'repaired-browser')
            after.update(remote_catchup=install.LAYER, snapshot_worker_before_sha256=digest,
                         snapshot_worker_sha256=install.sha(install.snapshot_overlay.transform(worker.read_text()).encode()))
            after_digest=install.sha((json.dumps(after,indent=2,sort_keys=True)+'\n').encode())
            with patch.object(install,'BASE_MANIFEST',install.sha(manifest.read_bytes())), \
                 patch.object(install,'OLD_POLICY',install.sha(policy.read_bytes())), \
                 patch.object(install,'AFTER_MANIFEST',after_digest), \
                 patch.object(install.overlay,'transform',return_value=b'repaired-browser'):
                changes=install.plan(root,'.config/fixture-backup.py',digest)
                self.assertEqual(len(changes),4)
                self.assertEqual(list(changes)[:2],[policy,worker])
                for path,data in changes.items():path.write_bytes(data)
                self.assertFalse(install.plan(root,'.config/fixture-backup.py',digest))
                complete=manifest.read_bytes()
                manifest.write_bytes(complete+b'\n')
                with self.assertRaisesRegex(ValueError,'final manifest'):
                    install.plan(root,'.config/fixture-backup.py',digest)
                manifest.write_bytes(complete)
                worker.write_bytes(worker.read_bytes()+b'\n# drift\n')
                with self.assertRaisesRegex(ValueError,'worker drift'):
                    install.plan(root,'.config/fixture-backup.py',digest)

    def test_wrong_cohort_hash_and_unsafe_worker_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);worker,policy,manifest=self.fixture(root)
            with self.assertRaisesRegex(ValueError,'starting manifest'):
                install.plan(root,'.config/fixture-backup.py',install.sha(worker.read_bytes()))
            for name in ('../outside','/storage/outside','.kodi/worker.py'):
                with self.assertRaises(ValueError):install.plan(root,name,'unreviewed')


if __name__=='__main__':unittest.main()
