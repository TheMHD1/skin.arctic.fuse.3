import importlib.util,tempfile,unittest
from pathlib import Path
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
  self.assertTrue((self.r/'.arctic3410-recovery/skin.failed/new.xml').is_file())
 def test_journal_failure_after_old_rename_restores_old_tree(self):
  def broken(path,phase):
   if phase=='old-preserved': raise OSError('no space')
   dt._write_journal(path,phase)
  with self.assertRaises(OSError):dt.replace(self.target,self.source,write_journal=broken)
  self.assertTrue((self.target/'old.xml').is_file());self.assertTrue((self.target/'extra.xml').is_file());self.assertFalse((self.target/'new.xml').exists())
 def test_keyboard_interrupt_after_old_rename_restores_old_tree(self):
  def interrupted(path,phase):
   if phase=='old-preserved': raise KeyboardInterrupt()
   dt._write_journal(path,phase)
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
if __name__=='__main__':unittest.main()
