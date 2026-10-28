"""Exact appliance identity and Kodi lifecycle guards for the candidate installer."""
from __future__ import annotations
import json, socket, subprocess, time
from pathlib import Path
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

def with_stopped_kodi(mutate, run=subprocess.run):
 """Run a supplied reversible transaction only after idle; always restart Kodi."""
 idle()
 stop_attempted=False
 try:
  stop_attempted=True
  run(['systemctl','stop','kodi'],check=True,timeout=45)
  return mutate()
 finally:
  if stop_attempted: run(['systemctl','start','kodi'],check=True,timeout=45)
