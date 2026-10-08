import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import jellystat_policy as p

class Tests(unittest.TestCase):
    def snapshot(self,**changes):
        return {'postgres_major':15,'jellystat_image':p.IMAGE,
                'procedure_md5':p.PROCEDURE_MD5,'settings':{},'role':'jellystat','database':'jellystat',**changes}
    def test_read_only_and_idempotent(self):
        for settings,apply in [({},False),(p.POLICY,True)]:
            execute=Mock();backup=Mock();restart=Mock()
            p.deploy(lambda:self.snapshot(settings=settings),execute,backup,restart,Path('/unused'),apply)
            execute.assert_not_called();backup.assert_not_called();restart.assert_not_called()
    def test_apply_backups_first_retains_other_defaults_and_cancels_exact_old_work(self):
        state=self.snapshot(settings={'search_path':'custom'});events=[]
        def execute(sql):
            events.append(sql)
            if sql.startswith('ALTER'):state['settings']={**state['settings'],**p.POLICY}
        with tempfile.TemporaryDirectory() as d:
            journal=Path(d)/'journal.json'
            p.deploy(lambda:state,execute,lambda:events.append('backup'),lambda:events.append('restart'),journal,True)
            self.assertEqual(events[0],'backup');self.assertEqual(events[-1],'restart')
            self.assertIn('query=\'CALL jd_remove_orphaned_data()\'',events[2])
            self.assertIn("interval '20 minutes'",events[2]);self.assertEqual(state['settings']['search_path'],'custom')
            self.assertEqual(journal.stat().st_mode&0o777,0o600)
    def test_unknown_schema_policy_and_identity_fail_closed(self):
        for changes in ({'postgres_major':16},{'procedure_md5':'foreign'},{'jellystat_image':p.IMAGE+'foreign'},
                        {'settings':{'work_mem':'1GB'}},{'role':'jellystat;DROP DATABASE anything'}):
            execute=Mock()
            with self.assertRaises(ValueError):p.deploy(lambda:self.snapshot(**changes),execute,Mock(),Mock(),Path('/unused'),True)
            execute.assert_not_called()
    def test_readback_failure_restores_only_our_three_settings(self):
        with tempfile.TemporaryDirectory() as d:
            execute=Mock();restart=Mock()
            with self.assertRaisesRegex(RuntimeError,'readback'):
                p.deploy(lambda:self.snapshot(),execute,Mock(),restart,Path(d)/'journal',True)
            self.assertIn('RESET work_mem',execute.call_args.args[0]);restart.assert_called_once()

if __name__=='__main__':unittest.main()
