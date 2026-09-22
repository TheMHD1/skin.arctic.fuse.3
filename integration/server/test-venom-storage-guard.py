import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('guard',Path(__file__).with_name('venom-storage-guard.py'))
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)

class Tests(unittest.TestCase):
    def setUp(self):
        if importlib.util.find_spec('apsw') is None:
            override=patch.object(guard,'open_database',lambda path:sqlite3.connect('file:'+str(path)+'?mode=rw',uri=True,timeout=1))
            override.start();self.addCleanup(override.stop)
    def test_checkpoint_preserves_rows_and_respects_reader(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'test.db'
            # Never mix two SQLite library implementations in one process:
            # their independent POSIX-lock registries are not coordinated.
            if importlib.util.find_spec('apsw') is not None:
                import apsw
                connect=lambda path:apsw.Connection(str(path))
            else:connect=lambda path:sqlite3.connect(path,isolation_level=None)
            writer=connect(p)
            writer.execute('pragma journal_mode=WAL')
            writer.execute('create table sample(value)')
            writer.execute('insert into sample values (1)')
            self.assertEqual(guard.reclaim(p,1)['wal_after'],0)
            reader=connect(p);reader.execute('begin')
            self.assertEqual(reader.execute('select count(*) from sample').fetchone()[0],1)
            writer.execute('insert into sample values (2)')
            self.assertEqual(guard.reclaim(p,1)['action'],'busy_retry_later')
            self.assertEqual(reader.execute('select count(*) from sample').fetchone()[0],1)
            reader.execute('rollback');reader.close()
            self.assertEqual(guard.reclaim(p,1)['wal_after'],0)
            self.assertEqual(writer.execute('select count(*) from sample').fetchone()[0],2)
            writer.close()
    def test_below_threshold_does_not_open_database(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'missing.db'
            self.assertEqual(guard.reclaim(p)['action'],'below_threshold')
            self.assertFalse(p.exists())

if __name__=='__main__':unittest.main()
