"""Exact appliance identity and Kodi lifecycle guards for the candidate installer."""
from __future__ import annotations
import hashlib, json, os, socket, subprocess, sys, time
from pathlib import Path
import xml.etree.ElementTree as ET

LIVE_PROOF_SCHEMA=1
LIVE_PROOF_SCRIPT='arctic3410-live-skin-proof.py'
LIVE_PROOF_PREFIX='arctic3410-live-skin-proof-'
def rpc(method, params=None):
 with socket.create_connection(('127.0.0.1',9090),3) as s:
  request={'jsonrpc':'2.0','id':1,'method':method}
  if params is not None: request['params']=params
  s.settimeout(3);s.sendall(json.dumps(request).encode()); data=b'';end=time.monotonic()+4
  while len(data)<65536:
   left=end-time.monotonic()
   if left<=0: raise RuntimeError('Kodi RPC timeout')
   s.settimeout(left);chunk=s.recv(8192)
   if not chunk: raise RuntimeError('Kodi RPC closed')
   data+=chunk
   try:r=json.loads(data)
   except (ValueError,UnicodeDecodeError):continue
   if r.get('id')!=1 or 'result' not in r or 'error' in r: raise RuntimeError('Kodi RPC failure')
   return r['result']
  raise RuntimeError('Kodi RPC response too large')
def idle():
 if rpc('Player.GetActivePlayers')!=[]: raise RuntimeError('Kodi active audio/video playback')
def ready(timeout=45,rpc_func=rpc,clock=time.monotonic,sleeper=time.sleep):
 deadline=clock()+timeout;last=None
 while clock()<deadline:
  try:
   if rpc_func('JSONRPC.Ping')=='pong':return
   last=RuntimeError('Kodi returned an unexpected readiness result')
  except (OSError,RuntimeError) as exc:last=exc
  sleeper(.25)
 raise RuntimeError('Kodi did not become ready after startup') from last
def appliance_hostname(storage_root=Path('/storage')):
 """Read the appliance identity from the mounted CoreELEC storage, not argv."""
 return (Path(storage_root)/'.cache/hostname').read_text().strip()

def appliance_mac(path=Path('/sys/class/net/wlan0/address')):
 return Path(path).read_text().strip().lower()

def identity(root, profile, hostname, mac):
 # The canonical parent guard owns the complete paired-profile schema.  This
 # second check deliberately requires only the fields it consumes, so it does
 # not silently reject legitimate future canonical profile fields.
 required={'cohort','hostname','wlan_mac','jellyfin_user_id','jellyfin_address'}
 if not required.issubset(profile) or profile['cohort'] not in {'local','remote'}: raise ValueError('invalid profile')
 if hostname!=profile['hostname'] or mac.lower()!=profile['wlan_mac'].lower(): raise RuntimeError('wrong appliance identity')
 data=json.loads((Path(root)/'userdata/addon_data/plugin.video.jellyfin/data.json').read_text())['Servers'][0]
 if data.get('UserId')!=profile['jellyfin_user_id'] or (data.get('address') or data.get('Address'))!=profile['jellyfin_address']: raise RuntimeError('wrong Jellyfin identity')
def stop_start(run=subprocess.run):
 idle(); run(['systemctl','stop','kodi'],check=True,timeout=45); run(['systemctl','start','kodi'],check=True,timeout=45)

def wait_stopped(status_reader=None,timeout=15,clock=time.monotonic,sleeper=time.sleep):
 if status_reader is None:
  def status_reader():
   result=subprocess.run(['systemctl','show','kodi','--property=ActiveState,SubState,MainPID',
                          '--value'],check=True,timeout=5,capture_output=True,text=True)
   values=result.stdout.splitlines();return tuple(values)
 deadline=clock()+timeout;last=None
 while clock()<deadline:
  try:
   active,sub,pid=status_reader()
   if active=='inactive' and sub=='dead' and pid=='0':return
   last=(active,sub,pid)
  except (OSError,subprocess.SubprocessError,ValueError) as exc:last=exc
  sleeper(.25)
 raise RuntimeError('Kodi unit did not become inactive/dead with no main PID: '+repr(last))

def _live_proof_paths(proof_root,nonce):
 if not isinstance(nonce,str) or len(nonce)!=64 or any(ch not in '0123456789abcdef' for ch in nonce):
  raise ValueError('invalid live-skin proof nonce')
 root=Path(proof_root).resolve();return root/LIVE_PROOF_SCRIPT,root/(LIVE_PROOF_PREFIX+nonce+'.json')

def write_live_skin_proof_script(proof_root,nonce,reuse=False):
 root=Path(proof_root)
 if not root.is_absolute() or root.is_symlink() or not root.is_dir():raise ValueError('unsafe live proof root')
 script,receipt=_live_proof_paths(root,nonce)
 payload={'schema':LIVE_PROOF_SCHEMA,'nonce':nonce,'receipt':str(receipt)}
 source="""import json,os,xml.etree.ElementTree as ET\nimport xbmcvfs\npayload={payload}\nskin=xbmcvfs.translatePath('special://skin')\naddon=os.path.join(skin,'addon.xml')\nroot=ET.parse(addon).getroot()\nvalue={{'schema':payload['schema'],'nonce':payload['nonce'],'skin':skin,'addon_id':root.get('id'),'version':root.get('version')}}\ntemporary=payload['receipt']+'.tmp'\ndescriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)\ntry:\n with os.fdopen(descriptor,'w',encoding='utf-8') as handle:\n  json.dump(value,handle,sort_keys=True,separators=(',',':'));handle.flush();os.fsync(handle.fileno())\n os.replace(temporary,payload['receipt'])\nfinally:\n try:os.unlink(temporary)\n except FileNotFoundError:pass\n""".format(payload=repr(payload))
 if reuse and script.exists():
  info=script.stat(follow_symlinks=False)
  if (script.is_symlink() or not script.is_file() or info.st_nlink!=1 or info.st_uid!=os.geteuid()
      or info.st_mode&0o777!=0o600 or script.read_text(encoding='utf-8')!=source):
   raise ValueError('existing live proof script differs from reviewed source')
  return script,receipt
 if script.exists() or receipt.exists():raise ValueError('live proof paths must be new')
 descriptor=os.open(script,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(descriptor,'w',encoding='utf-8') as handle:
  handle.write(source);handle.flush();os.fsync(handle.fileno())
 return script,receipt

def validate_live_skin_proof(proof_root,nonce,expected_skin,version='3.4.10'):
 script,receipt=_live_proof_paths(proof_root,nonce)
 info=receipt.stat(follow_symlinks=False) if receipt.exists() else None
 if (info is None or receipt.is_symlink() or not receipt.is_file() or info.st_size>4096
     or info.st_nlink!=1 or info.st_uid!=os.geteuid() or info.st_mode&0o077):
  raise RuntimeError('live-skin proof receipt is missing or unsafe')
 try:value=json.loads(receipt.read_text())
 except (OSError,UnicodeDecodeError,json.JSONDecodeError) as exc:raise RuntimeError('invalid live-skin proof') from exc
 if set(value)!={'schema','nonce','skin','addon_id','version'} or value.get('schema')!=LIVE_PROOF_SCHEMA or value.get('nonce')!=nonce:
  raise RuntimeError('live-skin proof schema/nonce mismatch')
 expected=Path(expected_skin).resolve()
 if Path(value.get('skin','')).resolve()!=expected or value.get('addon_id')!='skin.arctic.fuse.3' or value.get('version')!=version:
  raise RuntimeError('Kodi did not load the reviewed live skin')
 addon=expected/'addon.xml'
 if addon.is_symlink() or not addon.is_file() or ET.fromstring(addon.read_bytes()).get('version')!=version:
  raise RuntimeError('live skin manifest drift')
 return value

def reset_live_skin_proof_receipt(proof_root,nonce):
 script,receipt=_live_proof_paths(proof_root,nonce);temporary=receipt.with_name(receipt.name+'.tmp')
 write_live_skin_proof_script(proof_root,nonce,reuse=True)
 if temporary.exists():raise RuntimeError('stale live-skin proof temporary blocks a fresh proof')
 if receipt.exists():
  info=receipt.stat(follow_symlinks=False)
  if (receipt.is_symlink() or not receipt.is_file() or info.st_nlink!=1
      or info.st_uid!=os.geteuid() or info.st_mode&0o077 or info.st_size>4096):
   raise RuntimeError('unsafe prior live-skin proof receipt')
  receipt.unlink()
  descriptor=os.open(receipt.parent,os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(descriptor)
  finally:os.close(descriptor)
 return script,receipt

def recover_live_skin_proof_receipt(proof_root,nonce):
 script,receipt=_live_proof_paths(proof_root,nonce);temporary=receipt.with_name(receipt.name+'.tmp')
 write_live_skin_proof_script(proof_root,nonce,reuse=True)
 if temporary.exists() or temporary.is_symlink():
  if temporary.is_symlink() or not temporary.is_file():raise RuntimeError('unsafe interrupted proof temporary')
  info=temporary.stat(follow_symlinks=False)
  if info.st_nlink!=1 or info.st_uid!=os.geteuid() or info.st_mode&0o077 or info.st_size>4096:
   raise RuntimeError('unsafe interrupted proof temporary metadata')
  payload=temporary.read_bytes();evidence=Path(proof_root)/'interrupted-proof-writes'
  evidence.mkdir(mode=0o700,exist_ok=True)
  destination=evidence/(hashlib.sha256(payload).hexdigest()+'.json.partial')
  if destination.exists():
   if destination.is_symlink() or not destination.is_file() or destination.read_bytes()!=payload:
    raise RuntimeError('interrupted proof evidence collision')
   temporary.unlink()
  else:os.replace(temporary,destination)
  for directory in (evidence,Path(proof_root)):
   descriptor=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
   try:os.fsync(descriptor)
   finally:os.close(descriptor)
 return reset_live_skin_proof_receipt(proof_root,nonce)

def wait_live_skin_proof(proof_root,nonce,expected_skin,version='3.4.10',timeout=10,clock=time.monotonic,sleeper=time.sleep):
 deadline=clock()+timeout;last=None
 while clock()<deadline:
  try:return validate_live_skin_proof(proof_root,nonce,expected_skin,version)
  except RuntimeError as exc:last=exc
  sleeper(.1)
 raise RuntimeError('Kodi did not produce an accepted live-skin proof') from last

def with_stopped_kodi(mutate, run=subprocess.run, restart_permitted=None):
 """Run a reversible transaction after idle and restart only when it is safe.

 ``restart_permitted`` is intentionally an opt-in guard for transactions that
 launch a second, private Kodi process. If that process cannot be proved gone,
 starting normal Kodi could race it for JSON-RPC port 9090. In that exceptional
 case leave normal Kodi stopped and retain the original cleanup failure instead
 of masking it with a second bind failure.
 """
 idle()
 stop_attempted=False
 try:
  stop_attempted=True
  run(['systemctl','stop','kodi'],check=True,timeout=45)
  return mutate()
 finally:
  if stop_attempted:
   permitted = restart_permitted is None or restart_permitted()
   if permitted:
    run(['systemctl','start','kodi'],check=True,timeout=45)
   elif sys.exc_info()[0] is None:
    raise RuntimeError('normal Kodi restart withheld: owned isolated unit was not confirmed stopped')
