import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;spec=importlib.util.spec_from_file_location('life',HERE/'lifecycle.py');life=importlib.util.module_from_spec(spec);spec.loader.exec_module(life)
class T(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.r=Path(self.t.name);p=self.r/'userdata/addon_data/plugin.video.jellyfin';p.mkdir(parents=True);(p/'data.json').write_text(json.dumps({'Servers':[{'UserId':'u','address':'https://j'}]}));self.profile={'cohort':'remote','hostname':'h','wlan_mac':'aa','jellyfin_user_id':'u','jellyfin_address':'https://j','skin_before_sha256':'x','receipt_sha256':'y'}
 def test_idle_rejects_audio_video(self):
  with patch.object(life,'rpc',return_value=[{'type':'audio'}]):self.assertRaises(RuntimeError,life.idle)
  with patch.object(life,'rpc',return_value=[]):life.idle()
 def test_identity_fail_closed(self):
  life.identity(self.r,self.profile,'h','aa')
  with self.assertRaises(RuntimeError):life.identity(self.r,self.profile,'bad','aa')
  with self.assertRaises(RuntimeError):life.identity(self.r,self.profile,'h','bb')
  self.profile['jellyfin_user_id']='bad'
  with self.assertRaises(RuntimeError):life.identity(self.r,self.profile,'h','aa')
 def test_appliance_readers_use_storage_and_sysfs_files(self):
  storage=self.r/'storage';(storage/'.cache').mkdir(parents=True);(storage/'.cache/hostname').write_text('h\n')
  mac=self.r/'wlan0';mac.write_text('AA:BB\n')
  self.assertEqual(life.appliance_hostname(storage),'h');self.assertEqual(life.appliance_mac(mac),'aa:bb')
 def test_rpc_rejects_malformed_wrongid_and_error_and_accepts_fragments(self):
  class Sock:
   def __init__(self,chunks):self.chunks=list(chunks);self.sent=[]
   def __enter__(self):return self
   def __exit__(self,*_):return False
   def settimeout(self,_):pass
   def sendall(self,payload):self.sent.append(payload)
   def recv(self,_):return self.chunks.pop(0) if self.chunks else b''
  def invoke(chunks):
   with patch.object(life.socket,'create_connection',return_value=Sock(chunks)):return life.rpc('JSONRPC.Ping')
  self.assertEqual(invoke([b'{"jsonrpc":"2.0",',b'"id":1,"result":"pong"}']),'pong')
  for chunks in ([b'not json',b''],[b'{"id":2,"result":"pong"}'],[b'{"id":1,"error":{}}']):
   with self.assertRaises(RuntimeError):invoke(chunks)
 def test_rpc_serializes_optional_params(self):
  sock=type('Sock',(),{
   '__enter__':lambda self:self,'__exit__':lambda self,*_:False,
   'settimeout':lambda self,_:None,'sent':[],
   'sendall':lambda self,payload:self.sent.append(payload),
   'recv':lambda self,_:b'{"jsonrpc":"2.0","id":1,"result":"OK"}'
  })()
  with patch.object(life.socket,'create_connection',return_value=sock):
   self.assertEqual(life.rpc('Addons.SetAddonEnabled',{'addonid':'skin.arctic.fuse.3','enabled':True}),'OK')
  self.assertEqual(json.loads(sock.sent[0])['params'],{'addonid':'skin.arctic.fuse.3','enabled':True})
 def test_stop_start_is_after_idle(self):
  calls=[]
  with patch.object(life,'idle',side_effect=lambda:calls.append('idle')):
   life.stop_start(lambda args,**_:calls.append(args))
  self.assertEqual(calls,['idle',['systemctl','stop','kodi'],['systemctl','start','kodi']])
 def test_mutation_runs_only_after_stop_and_restarts_on_failure(self):
  calls=[]
  with patch.object(life,'idle',side_effect=lambda:calls.append('idle')):
   with self.assertRaises(ValueError):life.with_stopped_kodi(lambda:(calls.append('mutate'),(_ for _ in ()).throw(ValueError()))[-1],lambda a,**_:calls.append(a))
  self.assertEqual(calls,['idle',['systemctl','stop','kodi'],'mutate',['systemctl','start','kodi']])
 def test_stop_error_still_attempts_start(self):
  calls=[]
  def run(args,**_):
   calls.append(args)
   if args[1]=='stop': raise RuntimeError('stop uncertain')
  with patch.object(life,'idle',lambda:None):
   with self.assertRaises(RuntimeError):life.with_stopped_kodi(lambda:None,run)
  self.assertEqual(calls,[['systemctl','stop','kodi'],['systemctl','start','kodi']])
 def test_restart_is_withheld_when_owned_unit_cleanup_is_unproven(self):
  calls=[]
  with patch.object(life,'idle',lambda:None):
   with self.assertRaisesRegex(RuntimeError,'restart withheld'):
    life.with_stopped_kodi(lambda:None,lambda args,**_:calls.append(args),restart_permitted=lambda:False)
  self.assertEqual(calls,[['systemctl','stop','kodi']])
 def test_cleanup_error_is_not_masked_by_restart_guard(self):
  calls=[]
  def mutate(): raise RuntimeError('owned unit remains')
  with patch.object(life,'idle',lambda:None):
   with self.assertRaisesRegex(RuntimeError,'owned unit remains'):
    life.with_stopped_kodi(mutate,lambda args,**_:calls.append(args),restart_permitted=lambda:False)
  self.assertEqual(calls,[['systemctl','stop','kodi']])
if __name__=='__main__':unittest.main()
