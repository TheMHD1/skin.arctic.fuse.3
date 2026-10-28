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
  for p,v in [('addons/skin.arctic.fuse.3/addon.xml','3.3.1'),('addons/script.skinvariables/addon.xml','2.2.10')]:
   x=self.r/p;x.parent.mkdir(parents=True,exist_ok=True);x.write_text(f'<addon version="{v}"/>')
  self.tmdb=self.r/'addons'/install.dependencies.TMDB_ID;self.tmdb.mkdir(parents=True)
  requirements=''.join(f'<import addon="{k}" version="{v}"/>' for k,v in install.dependencies.TMDB_REQUIREMENTS.items())
  (self.tmdb/'addon.xml').write_text(f'<addon id="{install.dependencies.TMDB_ID}" version="{install.dependencies.TMDB_VERSION}"><requires>{requirements}</requires></addon>')
  (self.tmdb/'resources').mkdir();(self.tmdb/'resources/main.py').write_text('reviewed')
  entries={str(p.relative_to(self.tmdb)):p.read_bytes() for p in self.tmdb.rglob('*') if p.is_file()}
  payload=install.dependencies._payload_hash(entries)
  payload_patch=patch.object(install.dependencies,'TMDB_PAYLOAD_SHA256',payload);payload_patch.start();self.addCleanup(payload_patch.stop)
  count_patch=patch.object(install.dependencies,'TMDB_PAYLOAD_FILE_COUNT',len(entries));count_patch.start();self.addCleanup(count_patch.stop)
  (self.s/'candidate/addons/skin.arctic.fuse.3/addon.xml').write_text('<addon version="3.4.10"/>')
  q=self.r/'addons/plugin.video.habibi.resume/verified-build.json';q.parent.mkdir(parents=True,exist_ok=True);q.write_text('{}')
  data=self.r/'userdata/addon_data/plugin.video.jellyfin/data.json';data.parent.mkdir(parents=True,exist_ok=True);data.write_text('{"Servers":[{"UserId":"u","address":"http://j"}]}')
  self.p={'cohort':'local','hostname':'fixture','wlan_mac':'aa','jellyfin_user_id':'u','jellyfin_address':'http://j','canonical_extra':'preserved'}
  self.write_stage();self.guard_calls=[]
 def write_stage(self):
  record={'schema':3,'tmdbhelper':install.dependencies.reviewed_binding(),
          'source_skin_sha256':install.directory_transaction.tree_hash(self.r/'addons/skin.arctic.fuse.3'),
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
 def test_old_schema_binding_drift_and_same_version_payload_drift_fail_closed(self):
  record=json.loads((self.s/'stage.json').read_text());record['schema']=2;(self.s/'stage.json').write_text(json.dumps(record))
  with self.assertRaisesRegex(ValueError,'schema'):install.plan(self.storage,self.s,self.p,self.guard)
  self.write_stage();record=json.loads((self.s/'stage.json').read_text());record['tmdbhelper']['commit']='0'*40;(self.s/'stage.json').write_text(json.dumps(record))
  with self.assertRaisesRegex(ValueError,'provenance'):install.plan(self.storage,self.s,self.p,self.guard)
  self.write_stage();(self.tmdb/'resources/main.py').write_text('same-version-different-code')
  with self.assertRaisesRegex(ValueError,'payload differs'):install.plan(self.storage,self.s,self.p,self.guard)
 def test_tmdb_payload_drift_after_idle_is_caught_before_switch_and_kodi_restarts(self):
  calls=[]
  def idle_then_drift():
   calls.append('idle');(self.tmdb/'resources/main.py').write_text('drift-after-first-plan')
  with patch.object(install.lifecycle,'idle',idle_then_drift):
   with self.assertRaisesRegex(ValueError,'payload differs'):
    install.apply_candidate(self.storage,self.s,self.p,lambda:'fixture',lambda:'aa',run=lambda a,**_:calls.append(a),parent_guard=self.guard)
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
