import importlib.util,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('install',HERE/'install.py')
install=importlib.util.module_from_spec(spec);spec.loader.exec_module(install)

class T(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
  self.storage=Path(self.t.name)/'storage';self.r=self.storage/'.kodi';self.r.mkdir(parents=True)
  self.s=Path(self.t.name)/'stage';(self.s/'candidate/addons/skin.arctic.fuse.3').mkdir(parents=True)
  for p,v in [('addons/skin.arctic.fuse.3/addon.xml','3.3.1'),('addons/script.skinvariables/addon.xml','2.2.10'),('addons/plugin.video.themoviedb.helper/addon.xml','6.19.1')]:
   x=self.r/p;x.parent.mkdir(parents=True,exist_ok=True);x.write_text(f'<addon version="{v}"/>')
  (self.s/'candidate/addons/skin.arctic.fuse.3/addon.xml').write_text('<addon version="3.4.10"/>')
  q=self.r/'addons/plugin.video.habibi.resume/verified-build.json';q.parent.mkdir(parents=True,exist_ok=True);q.write_text('{}')
  data=self.r/'userdata/addon_data/plugin.video.jellyfin/data.json';data.parent.mkdir(parents=True,exist_ok=True);data.write_text('{"Servers":[{"UserId":"u","address":"http://j"}]}')
  self.p={'cohort':'local','hostname':'fixture','wlan_mac':'aa','jellyfin_user_id':'u','jellyfin_address':'http://j','canonical_extra':'preserved'}
  self.write_stage();self.guard_calls=[]
 def write_stage(self):
  record={'schema':2,'source_skin_sha256':install.directory_transaction.tree_hash(self.r/'addons/skin.arctic.fuse.3'),
          'source_resume_receipt_sha256':install.sha(self.r/'addons/plugin.video.habibi.resume/verified-build.json'),
          'candidate_skin_sha256':install.directory_transaction.tree_hash(self.s/'candidate/addons/skin.arctic.fuse.3')}
  (self.s/'stage.json').write_text(json.dumps(record))
 def guard(self,root,profile):
  self.guard_calls.append((Path(root),dict(profile)));self.assertEqual(profile,self.p)
  return SimpleNamespace(expected={Path(root)/'.kodi/addons/skin.arctic.fuse.3/addon.xml':b'whole-parent-manifest-checked'})
 def test_plan_and_drift_guard(self):
  self.assertEqual(len(install.plan(self.storage,self.s,self.p,self.guard)),1);self.assertEqual(len(self.guard_calls),1)
  self.r.joinpath('addons/skin.arctic.fuse.3/addon.xml').write_text('<addon version="3.3.1">drift</addon>')
  with self.assertRaises(ValueError):install.plan(self.storage,self.s,self.p,self.guard)
 def test_integrated_switch_preserves_settings_and_removes_old(self):
  oldskin=self.r/'addons/skin.arctic.fuse.3';(oldskin/'old.xml').write_text('old')
  protected=self.r/'userdata/guisettings.xml';protected.parent.mkdir(parents=True,exist_ok=True);protected.write_text('<settings/>');before=install.sha(protected)
  (self.s/'candidate/addons/skin.arctic.fuse.3/new.xml').write_text('new');self.write_stage();calls=[]
  with patch.object(install.lifecycle,'idle',lambda:calls.append('idle')):
   install.apply_candidate(self.storage,self.s,self.p,lambda:'fixture',lambda:'aa',run=lambda a,**_:calls.append(a),parent_guard=self.guard)
  self.assertEqual(calls,['idle',['systemctl','stop','kodi'],['systemctl','start','kodi']]);self.assertEqual(len(self.guard_calls),2)
  self.assertFalse((oldskin/'old.xml').exists());self.assertTrue((oldskin/'new.xml').is_file());self.assertEqual(before,install.sha(protected))
 def test_active_or_identity_drift_never_stops_or_mutates(self):
  calls=[]
  with patch.object(install.lifecycle,'identity',side_effect=RuntimeError('drift')):
   with self.assertRaises(RuntimeError):install.apply_candidate(self.storage,self.s,self.p,lambda:'fixture',lambda:'aa',run=lambda a,**_:calls.append(a),parent_guard=self.guard)
  self.assertEqual(calls,[])
 def test_post_stop_stage_drift_restarts_without_switch(self):
  calls=[]
  def idle_then_drift():
   calls.append('idle');(self.s/'candidate/addons/skin.arctic.fuse.3/addon.xml').write_text('<addon version="3.4.10">drift</addon>')
  with patch.object(install.lifecycle,'idle',idle_then_drift):
   with self.assertRaises(ValueError):install.apply_candidate(self.storage,self.s,self.p,lambda:'fixture',lambda:'aa',run=lambda a,**_:calls.append(a),parent_guard=self.guard)
  self.assertEqual(calls,['idle',['systemctl','stop','kodi'],['systemctl','start','kodi']])
 def test_failed_switch_starts_kodi_and_restores_full_old_tree(self):
  oldskin=self.r/'addons/skin.arctic.fuse.3';(oldskin/'old.xml').write_text('old');oldhash=install.directory_transaction.tree_hash(oldskin)
  protected=self.r/'userdata/guisettings.xml';protected.parent.mkdir(parents=True,exist_ok=True);protected.write_text('<settings/>');saved=install.sha(protected);calls=[]
  self.write_stage()
  def bad(path):
   if Path(path).name=='skin.arctic.fuse.3': raise RuntimeError('forced verify failure')
   return install.directory_transaction.tree_hash(path)
  with patch.object(install.lifecycle,'idle',lambda:None):
   with self.assertRaises(RuntimeError):install.apply_candidate(self.storage,self.s,self.p,lambda:'fixture',lambda:'aa',run=lambda a,**_:calls.append(a),switch=lambda *a,**k:install.directory_transaction.replace(*a,verify=bad,**k),parent_guard=self.guard)
  self.assertEqual(calls,[['systemctl','stop','kodi'],['systemctl','start','kodi']]);self.assertEqual(oldhash,install.directory_transaction.tree_hash(oldskin));self.assertEqual(saved,install.sha(protected))

if __name__=='__main__':unittest.main()
