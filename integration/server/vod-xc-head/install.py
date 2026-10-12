"""Guarded, persistent XC HEAD overlay for the reviewed single-service Compose."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import yaml
from build import SOURCE_SHA256, transform

IMAGE = 'ghcr.io/dispatcharr/dispatcharr:0.31.0@sha256:f81924fa3dbfeb463b3908be7e086bf58aacbd2ba56062bfb555ee3a471acf8f'
TARGET = '/app/apps/proxy/vod_proxy/views.py'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True)
    parser.add_argument('--compose',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    assert os.geteuid()==0 and socket.gethostname()==args.host,'Exact private root host required'
    assert args.compose.is_file() and not args.compose.is_symlink()
    before=args.compose.read_bytes();data=yaml.safe_load(before)
    assert set(data['services'])=={'dispatcharr'}
    service=data['services']['dispatcharr'];assert service['image']==IMAGE,'Review new image before rebase'
    source=subprocess.check_output(['docker','exec','dispatcharr','cat',TARGET])
    output=transform(source)
    assert all(TARGET not in str(v) for v in service['volumes']),'Existing VOD overlay requires review'
    overlay=args.compose.parent/'patches/vod-xc-head-031.py'
    assert overlay.parent.is_dir() and not overlay.exists()
    # Insert one mount using an existing unique sibling anchor. Preserve every
    # byte of unrelated Compose config rather than reserializing secrets/YAML.
    lines=before.decode().splitlines(keepends=True)
    positions=[i for i,line in enumerate(lines) if '/app/apps/proxy/live_proxy/output/ts/generator.py:ro' in line]
    assert len(positions)==1
    index=positions[0];indent=lines[index][:len(lines[index])-len(lines[index].lstrip())]
    mount=str(overlay)+':'+TARGET+':ro'
    lines.insert(index+1,indent+'- '+mount+'\n')
    candidate=''.join(lines).encode()
    expected=yaml.safe_load(candidate)
    wanted=yaml.safe_load(before);wanted['services']['dispatcharr']['volumes'].append(mount)
    assert expected==wanted,'Unexpected Compose change'
    print('Plan: one guarded read-only VOD module mount; recreate Dispatcharr only')
    if not args.apply:return
    backup=args.compose.parent/'backup'/('vod-xc-head-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
    backup.mkdir(mode=0o700,parents=True)
    (backup/'compose.before.yml').write_bytes(before);(backup/'compose.before.yml').chmod(0o600)
    (backup/'views.before.py').write_bytes(source)
    with overlay.open('xb') as target:target.write(output)
    overlay.chmod(0o644)
    args.compose.write_bytes(candidate)
    try:
        subprocess.run(['docker','compose','-f',str(args.compose),'config','-q'],check=True)
        subprocess.run(['docker','compose','-f',str(args.compose),'up','-d','--no-deps','--force-recreate','dispatcharr'],check=True)
        installed=subprocess.check_output(['docker','exec','dispatcharr','cat',TARGET])
        assert installed==output,'In-container mounted bytes mismatch'
    except BaseException:
        args.compose.write_bytes(before)
        subprocess.run(['docker','compose','-f',str(args.compose),'up','-d','--no-deps','--force-recreate','dispatcharr'],check=True)
        raise
    print('Mounted source verified SHA256='+hashlib.sha256(output).hexdigest())
    print('Private rollback backup: '+str(backup))


if __name__=='__main__':main()
