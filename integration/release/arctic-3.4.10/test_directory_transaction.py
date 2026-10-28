import importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;spec=importlib.util.spec_from_file_location('dt',HERE/'directory_transaction.py');dt=importlib.util.module_from_spec(spec);spec.loader.exec_module(dt)
class T(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.r=Path(self.t.name);self.target=self.r/'addons/skin';self.source=self.r/'candidate';self.target.mkdir(parents=True);self.source.mkdir();(self.target/'old.xml').write_text('old');(self.target/'extra.xml').write_text('remove');(self.source/'new.xml').write_text('new');(self.r/'userdata').mkdir();(self.r/'userdata/guisettings.xml').write_text('keep')
 def test_success_replaces_entire_tree_and_keeps_old(self):
  out=dt.replace(self.target,self.source,('userdata/guisettings.xml',));self.assertFalse((self.target/'extra.xml').exists());self.assertTrue((out['old']/'extra.xml').is_file());self.assertTrue((out['protected']/'protected/userdata/guisettings.xml').is_file());self.assertEqual(out['hash'],dt.tree_hash(self.target));self.assertNotEqual(out['old'].parent,self.target.parent)
 def test_forced_verify_failure_restores_old_tree(self):
  target_checks=0
  def bad(path):
   nonlocal target_checks
   if Path(path)==self.target:
    target_checks+=1
    if target_checks==2: raise RuntimeError('forced post-switch verify')
   return dt.tree_hash(path)
  with self.assertRaises(RuntimeError):dt.replace(self.target,self.source,verify=bad)
  self.assertTrue((self.target/'old.xml').is_file());self.assertTrue((self.target/'extra.xml').is_file());self.assertFalse((self.target/'new.xml').exists())
  self.assertFalse((self.r/'.arctic3410-recovery/skin.failed').exists())
 def test_journal_failure_after_old_rename_restores_old_tree(self):
  def broken(path,state):
   if state['phase']=='old-preserved': raise OSError('no space')
   dt._write_journal(path,state)
  with self.assertRaises(OSError):dt.replace(self.target,self.source,write_journal=broken)
  self.assertTrue((self.target/'old.xml').is_file());self.assertTrue((self.target/'extra.xml').is_file());self.assertFalse((self.target/'new.xml').exists())
 def test_keyboard_interrupt_after_old_rename_restores_old_tree(self):
  def interrupted(path,state):
   if state['phase']=='old-preserved': raise KeyboardInterrupt()
   dt._write_journal(path,state)
  with self.assertRaises(KeyboardInterrupt):dt.replace(self.target,self.source,write_journal=interrupted)
  self.assertTrue((self.target/'old.xml').is_file());self.assertTrue((self.target/'extra.xml').is_file());self.assertFalse((self.target/'new.xml').exists())
  self.assertFalse((self.r/'.arctic3410-recovery/skin.new').exists())
 def test_unsafe_inputs_fail_closed(self):
  with self.assertRaises(ValueError):dt.replace(self.target,self.target)
  with self.assertRaises(ValueError):dt.snapshot_protected(self.r,self.r/'backup',('../escape',))
  link=self.r/'userdata/link';link.parent.mkdir(exist_ok=True);link.symlink_to(self.r/'elsewhere')
  with self.assertRaises(ValueError):dt.snapshot_protected(self.r,self.r/'backup2',('userdata/link/x',))
  linked=self.r/'linked-target';linked.symlink_to(self.target)
  with self.assertRaises(ValueError):dt.replace(linked,self.source)
  linked_parent=self.r/'linked-parent';linked_parent.symlink_to(self.r/'addons')
  with self.assertRaises(ValueError):dt.replace(linked_parent/'skin',self.source)
 def test_existing_recovery_evidence_blocks_new_run(self):
  old=self.r/'.arctic3410-recovery/skin.old';old.mkdir(parents=True)
  with self.assertRaises(RuntimeError):dt.replace(self.target,self.source)
 def test_post_start_rollback_restores_protected_and_original_absence(self):
  settings=self.r/'userdata/settings';settings.mkdir();(settings/'value.xml').write_text('old')
  settings.chmod(0o750);missing=self.r/'userdata/created-later'
  transaction=dt.prepare(self.target,self.source,('userdata/settings','userdata/created-later'),bindings={'stage':'a'*64})
  dt.switch(transaction)
  (settings/'value.xml').write_text('changed');(settings/'new.xml').write_text('new')
  missing.mkdir();(missing/'created').write_text('created')
  recovered=dt.load(self.target)
  dt.rollback(recovered)
  self.assertEqual((settings/'value.xml').read_text(),'old');self.assertFalse((settings/'new.xml').exists())
  self.assertFalse(missing.exists());self.assertEqual(settings.stat().st_mode&0o777,0o750)
  self.assertEqual(dt.tree_hash(self.target),transaction['state']['old_sha256'])
 def test_acceptance_is_durable_and_not_automatically_rolled_back(self):
  transaction=dt.prepare(self.target,self.source,bindings={'evidence':'b'*64});dt.switch(transaction)
  dt.accept(transaction,'c'*64,{'proof':'d'*64});loaded=dt.load(self.target)
  self.assertEqual(loaded['state']['phase'],'accepted')
  self.assertEqual(loaded['state']['bindings']['accepted_receipt_sha256'],'c'*64)
  self.assertEqual(loaded['state']['bindings']['proof'],'d'*64)
  with self.assertRaisesRegex(RuntimeError,'accepted'):dt.rollback(loaded)
  dt.rollback(loaded,allow_accepted=True);self.assertTrue((self.target/'old.xml').is_file())
 def test_power_loss_between_candidate_rename_and_phase_write_is_recoverable(self):
  def lagging(path,state):
   if state['phase']=='candidate-installed':raise OSError('simulated power boundary')
   dt._write_journal(path,state)
  transaction=dt.prepare(self.target,self.source,write_journal=lagging)
  with self.assertRaises(OSError):dt.switch(transaction)
  self.assertTrue((self.target/'old.xml').is_file());self.assertFalse((self.target/'new.xml').exists())
  self.assertEqual(dt._read_journal(transaction['journal'])['phase'],'rolled-back')
 def test_orphan_initial_journal_temporary_is_quarantined_before_new_copy(self):
  recovery=self.r/'.arctic3410-recovery';recovery.mkdir()
  temporary=recovery/'skin.journal.json.tmp';temporary.write_bytes(b'partial-initial-write');temporary.chmod(0o600)
  transaction=dt.prepare(self.target,self.source)
  self.assertEqual(transaction['state']['phase'],'prepared');self.assertFalse(temporary.exists())
  evidence=list((recovery/'interrupted-journals').glob('*.partial'));self.assertEqual(len(evidence),1)
  dt.rollback(transaction);self.assertTrue((self.target/'old.xml').is_file())
 def test_recovery_replays_exact_physically_restored_layout_after_lagging_journal(self):
  def lagged(path,state):
   if state['phase']=='rolled-back':
    temporary=path.with_name(path.name+'.tmp');temporary.write_bytes(dt._canonical(state));temporary.chmod(0o600);raise OSError('cut after restore')
   dt._write_journal(path,state)
  transaction=dt.prepare(self.target,self.source,write_journal=lagged);dt.switch(transaction)
  with self.assertRaises(OSError):dt.rollback(transaction)
  self.assertEqual(dt.tree_hash(self.target),transaction['state']['old_sha256'])
  self.assertTrue(transaction['failed'].is_dir());self.assertFalse(transaction['old'].exists())
  recovered=dt.load(self.target,allow_temporary=True);dt.rollback(recovered)
  self.assertEqual(dt._read_journal(recovered['journal'])['phase'],'rolled-back')
  self.assertEqual(dt.tree_hash(self.target),recovered['state']['old_sha256'])
 def test_initial_journal_precedes_copy_and_copy_failure_is_honestly_recovered(self):
  with patch.object(dt.shutil,'copytree',side_effect=OSError('power boundary')):
   with self.assertRaises(OSError):dt.prepare(self.target,self.source)
  journal=self.r/'.arctic3410-recovery/skin.journal.json'
  self.assertEqual(dt._read_journal(journal)['phase'],'rolled-back')
  self.assertTrue((self.target/'old.xml').is_file());self.assertFalse((self.r/'.arctic3410-recovery/skin.new').exists())
 def test_interrupted_journal_temporary_is_quarantined_before_rollback(self):
  def interrupted(path,state):
   if state['phase']=='old-preserved':
    temporary=path.with_name(path.name+'.tmp');temporary.write_bytes(dt._canonical(state));temporary.chmod(0o600);raise OSError('cut')
   dt._write_journal(path,state)
  transaction=dt.prepare(self.target,self.source,write_journal=interrupted)
  with self.assertRaises(OSError):dt.switch(transaction)
  evidence=list((transaction['root']/'interrupted-journals').glob('*.partial'))
  self.assertEqual(len(evidence),1);self.assertFalse(transaction['journal'].with_name(transaction['journal'].name+'.tmp').exists())
  self.assertEqual(dt._read_journal(transaction['journal'])['phase'],'rolled-back')
 def test_protected_change_after_snapshot_blocks_switch_and_restores(self):
  transaction=dt.prepare(self.target,self.source,('userdata/guisettings.xml',))
  (self.r/'userdata/guisettings.xml').write_text('raced')
  with self.assertRaisesRegex(RuntimeError,'protected rollback verification'):
   dt.switch(transaction)
  self.assertEqual((self.r/'userdata/guisettings.xml').read_text(),'keep')
  self.assertTrue((self.target/'old.xml').is_file());self.assertFalse((self.target/'new.xml').exists())
if __name__=='__main__':unittest.main()
