"""Guarded live ARC budget trial. No VM changes, swapoff, pool changes or reboot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

GIB=1024**3

def configured(source,maximum,minimum):
    if minimum<=0 or maximum<minimum:raise ValueError('Invalid ARC budget')
    # Replace precisely one existing setting each, preserving every other knob.
    result=source
    for key,value in [('zfs_arc_max',maximum),('zfs_arc_min',minimum)]:
        pattern=rf'(?<!\S){key}=\d+(?=\s|$)'
        if len(re.findall(pattern,result))!=1:raise ValueError('Ambiguous ARC configuration')
        result=re.sub(pattern,key+'='+str(value),result)
    return result

def apply(parameters,maximum,minimum):
    old={key:int((parameters/key).read_text()) for key in ('zfs_arc_max','zfs_arc_min')}
    # Lower minimum first; raise maximum first. Never transiently min > max.
    changes=[('zfs_arc_min',minimum),('zfs_arc_max',maximum)] if maximum<old['zfs_arc_max'] else [('zfs_arc_max',maximum),('zfs_arc_min',minimum)]
    done=[]
    try:
        for key,value in changes:
            (parameters/key).write_text(str(value));done.append(key)
        if any(int((parameters/k).read_text())!=v for k,v in changes):raise RuntimeError('ARC readback mismatch')
    except BaseException:
        for key in reversed(done):(parameters/key).write_text(str(old[key]))
        raise
    return old

def persist(path,before,after,refresh):
    """Change two reviewed module settings; refresh only the running initramfs."""
    if path.is_symlink() or path.read_bytes()!=before:raise ValueError('Persistent ARC config drift')
    mode=path.stat().st_mode&0o777
    def write(data):
        fd,name=tempfile.mkstemp(prefix=path.name+'.performance-',dir=path.parent)
        temporary=Path(name)
        try:
            with os.fdopen(fd,'wb') as f:
                f.write(data);f.flush();os.fsync(f.fileno())
            temporary.chmod(mode);os.replace(temporary,path)
        finally:temporary.unlink(missing_ok=True)
    try:
        write(after)
        refresh()
        if path.read_bytes()!=after:raise RuntimeError('Persistent ARC readback mismatch')
    except BaseException as failure:
        write(before)
        try:refresh()
        except Exception as recovery:raise RuntimeError('ARC initramfs recovery failed; use private journal') from recovery
        raise failure

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--max-gib',type=int,required=True);p.add_argument('--min-gib',type=int,required=True)
    p.add_argument('--config',type=Path,default=Path('/etc/modprobe.d/zfs.conf'))
    p.add_argument('--expected-config-sha256',required=True)
    p.add_argument('--expected-max-gib',type=int,required=True);p.add_argument('--expected-min-gib',type=int,required=True)
    p.add_argument('--journal',type=Path,required=True);p.add_argument('--apply',action='store_true')
    p.add_argument('--persist',action='store_true',help='also preserve the budget across the next normal boot; no reboot')
    a=p.parse_args();raw=a.config.read_bytes()
    if a.persist and not a.apply:raise SystemExit('--persist requires --apply after a live trial')
    if a.config.is_symlink() or hashlib.sha256(raw).hexdigest()!=a.expected_config_sha256:raise SystemExit('ARC config drift')
    maximum=a.max_gib*GIB;minimum=a.min_gib*GIB
    total=int(re.search(r'^MemTotal:\s+(\d+)',Path('/proc/meminfo').read_text(),re.M)[1])*1024
    if not 0<minimum<=maximum<=total//4:raise SystemExit('Unsafe ARC budget')
    params=Path('/sys/module/zfs/parameters')
    before={key:int((params/key).read_text()) for key in ('zfs_arc_max','zfs_arc_min')}
    if before!={'zfs_arc_max':a.expected_max_gib*GIB,'zfs_arc_min':a.expected_min_gib*GIB}:raise SystemExit('ARC live policy drift')
    proposed=configured(raw.decode(),maximum,minimum)
    print(json.dumps({'mode':'persist' if a.persist else ('live-trial' if a.apply else 'plan'),'before':before,'after':{'zfs_arc_max':maximum,'zfs_arc_min':minimum},'persistent_config_requested':a.persist}))
    if a.apply:
        # Exclusive private journal first: preserve the live and full disk policy.
        with a.journal.open('x') as f:
            a.journal.chmod(0o600)
            json.dump({'before':before,'config':raw.decode(),'proposed_config':proposed,'config_sha256':a.expected_config_sha256,'persist':a.persist,'kernel':os.uname().release},f,indent=2)
        apply(params,maximum,minimum)
        if a.persist:
            def refresh():subprocess.run(['update-initramfs','-u','-k',os.uname().release],check=True,timeout=600)
            persist(a.config,raw,proposed.encode(),refresh)
        print(json.dumps({'live_readback':'passed','persistent_config_changed':a.persist,'reboot':False}))
