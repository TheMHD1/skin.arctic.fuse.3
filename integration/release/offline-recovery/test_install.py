import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import install


class Tests(unittest.TestCase):
    def profile(self):
        return {'hostname':'appliance', 'cohort':'local', 'offline_recovery':{
            'maintenance_host':'maintenance','storage_uuid':'own-uuid','disk_serial':'own-serial'}}

    def probe(self, root, **overrides):
        outputs = {'findmnt':json.dumps({'filesystems':[{'target':str(root),'source':'/dev/sdz2','fstype':'ext4','options':'rw,relatime'}]}),
                   'blkid':'own-uuid','lsblk-parent':'sdz','lsblk-serial':'own-serial'}
        outputs.update(overrides)
        def run(*args):
            key = args[0] if args[0] != 'lsblk' else ('lsblk-parent' if 'PKNAME' in args else 'lsblk-serial')
            return outputs[key]
        return run

    def test_guard_accepts_exact_host_mount_and_media(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            self.assertEqual(install.guard(root,self.profile(),self.probe(root),lambda:'maintenance'),'/dev/sdz2')

    def test_guard_rejects_foreign_identity_and_mount(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for key,value in [('blkid','other'),('lsblk-serial','other'),('lsblk-parent','')]:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    install.guard(root,self.profile(),self.probe(root,**{key:value}),lambda:'maintenance')
            for target,fs,options in [('/', 'ext4','rw'),(str(root),'vfat','rw'),(str(root),'ext4','ro')]:
                bad=json.dumps({'filesystems':[{'target':target,'source':'/dev/sdz2','fstype':fs,'options':options}]})
                with self.assertRaises(ValueError):install.guard(root,self.profile(),self.probe(root,findmnt=bad),lambda:'maintenance')
            with self.assertRaises(ValueError):install.guard(root,self.profile(),self.probe(root),lambda:'appliance')
            with self.assertRaises(ValueError):install.guard(root,self.profile(),self.probe(root),lambda:'other-host')

    def test_root_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);link=root/'link';link.symlink_to(root)
            for target in (Path('/'),link):
                with self.assertRaises(ValueError):install.guard(target,self.profile(),self.probe(root),lambda:'maintenance')

    def fixture(self, root):
        a=root/'.kodi/addons/example/source.py';a.parent.mkdir(parents=True);a.write_bytes(b'old');a.chmod(0o640)
        b=root/'.config/new-receipt.json'
        return a,b,install.release.transaction.Plan({a:b'new',b:b'receipt'},{a:b'old',b:None})

    def test_apply_preserves_modes_and_never_calls_systemctl(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a,b,plan=self.fixture(root)
            with patch.object(install.release,'plan',return_value={}),patch.object(install.os,'chown'):
                self.assertTrue(install.deploy(root,self.profile(),plan,root/'backup/run',check_guard=lambda *a:None))
            self.assertEqual(a.read_bytes(),b'new');self.assertEqual(b.read_bytes(),b'receipt')
            self.assertEqual(a.stat().st_mode&0o777,0o640)
            self.assertEqual((root/'backup/run/.kodi/addons/example/source.py').read_bytes(),b'old')

    def test_drift_or_staging_fails_before_write(self):
        for drift in ('source','staging'):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);a,b,plan=self.fixture(root)
                if drift=='source':a.write_bytes(b'drift')
                else:a.with_name(a.name+'.audit-tmp').write_bytes(b'foreign')
                with self.assertRaises(ValueError):install.deploy(root,self.profile(),plan,root/'backup/run',check_guard=lambda *a:None)
                self.assertFalse(b.exists());self.assertFalse((root/'backup').exists())

    def test_parent_symlink_or_backup_symlink_rejected(self):
        for obstacle in ('parent','backup'):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);a,b,plan=self.fixture(root)
                if obstacle=='parent':
                    parent=a.parent; saved=root/'moved';parent.rename(saved);parent.symlink_to(saved)
                else:
                    other=root/'other';other.mkdir();(root/'backup').symlink_to(other)
                with self.assertRaises(ValueError):
                    install.deploy(root,self.profile(),plan,root/'backup/run',check_guard=lambda *a:None)
                self.assertEqual(a.read_bytes(),b'old');self.assertFalse(b.exists())

    def test_failure_rolls_back_and_convergence_required(self):
        for failure in ('write','convergence'):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);a,b,plan=self.fixture(root)
                def write(p,data,mode):
                    install.release.transaction.atomic_write(p,data,mode)
                    if p==b:raise RuntimeError('interrupted after replacement')
                with patch.object(install.release,'plan',return_value={'not-converged':b'x'}),patch.object(install.os,'chown'):
                    with self.assertRaises((RuntimeError,ValueError)):
                        install.deploy(root,self.profile(),plan,root/'backup/run',check_guard=lambda *a:None,
                            write=write if failure=='write' else install.release.transaction.atomic_write)
                self.assertEqual(a.read_bytes(),b'old');self.assertFalse(b.exists())

    def test_image_verification(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'image';p.write_bytes(b'recovery')
            install.verified_image(p,hashlib.sha256(b'recovery').hexdigest())
            with self.assertRaises(ValueError):install.verified_image(p,'0'*64)


if __name__=='__main__':unittest.main()
