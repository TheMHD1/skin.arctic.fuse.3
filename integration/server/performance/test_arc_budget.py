import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import arc_budget as a

class Tests(unittest.TestCase):
    def test_only_budget_changes(self):
        source='options zfs zfs_arc_max=24 zfs_arc_min=8 zfetch_max_distance=123\n'
        self.assertEqual(a.configured(source,12,4),'options zfs zfs_arc_max=12 zfs_arc_min=4 zfetch_max_distance=123\n')
    def test_ambiguous_or_missing_fail_closed(self):
        for source in ('options zfs zfs_arc_max=24','options zfs zfs_arc_max=24 zfs_arc_min=8 zfs_arc_max=24'):
            with self.assertRaises(ValueError):a.configured(source,12,4)
    def test_order_and_readback(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for k,v in [('zfs_arc_min',8),('zfs_arc_max',24)]:(root/k).write_text(str(v))
            writes=[];original=Path.write_text
            def write(path,text):writes.append(path.name);return original(path,text)
            with patch.object(Path,'write_text',write):old=a.apply(root,12,4)
            self.assertEqual(writes,['zfs_arc_min','zfs_arc_max'])
            self.assertEqual(old,{'zfs_arc_min':8,'zfs_arc_max':24})
    def test_persist_preserves_mode_and_uses_reviewed_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'zfs.conf';path.write_bytes(b'before');path.chmod(0o640);calls=[]
            a.persist(path,b'before',b'after',lambda:calls.append(path.read_bytes()))
            self.assertEqual(calls,[b'after']);self.assertEqual(path.stat().st_mode&0o777,0o640)
            with self.assertRaisesRegex(ValueError,'drift'):a.persist(path,b'before',b'after',lambda:None)
    def test_failed_refresh_restores_full_configuration_and_initramfs(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'zfs.conf';path.write_bytes(b'before');calls=[]
            def refresh():
                calls.append(path.read_bytes())
                if len(calls)==1:raise RuntimeError('failed refresh')
            with self.assertRaisesRegex(RuntimeError,'failed refresh'):a.persist(path,b'before',b'after',refresh)
            self.assertEqual(calls,[b'after',b'before']);self.assertEqual(path.read_bytes(),b'before')

if __name__=='__main__':unittest.main()
