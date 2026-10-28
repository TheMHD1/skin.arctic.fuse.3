"""Guarded per-device Arctic 3.4.10 installer; defaults to a no-write plan."""
from __future__ import annotations
import argparse, hashlib, json, importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

import dependencies
import lifecycle
import directory_transaction

RELEASE='arctic-3.4.10-paired.1'
SKIN='addons/skin.arctic.fuse.3'
PROTECTED=('userdata/addon_data/skin.arctic.fuse.3','userdata/addon_data/script.skinvariables',
           'userdata/addon_data/plugin.video.themoviedb.helper','userdata/guisettings.xml')

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def version(path): return ET.fromstring(path.read_bytes()).get('version')

def canonical_parent_plan(storage_root, profile):
    source=Path(__file__).resolve().parents[1]/'library-transactions/install.py'
    spec=importlib.util.spec_from_file_location('arctic_parent_guard',source)
    parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
    result=parent.plan(Path(storage_root),profile)
    if not result.expected: raise RuntimeError('parent cohort preflight produced no evidence')
    return result

def plan(storage_root, stage, profile, parent_guard=canonical_parent_plan):
    storage_root,stage=Path(storage_root).resolve(),Path(stage).resolve()
    parent=parent_guard(storage_root,profile)  # validates every recorded source before skin work
    root=storage_root/'.kodi'
    if not parent.expected: raise ValueError('missing canonical parent evidence')
    skin=root/SKIN; receipt=root/'addons/plugin.video.habibi.resume/verified-build.json'
    if not skin.is_dir() or version(skin/'addon.xml')!='3.3.1': raise ValueError('unreviewed current Arctic cohort')
    record=json.loads((stage/'stage.json').read_text())
    if record.get('schema') != 3: raise ValueError('unreviewed candidate stage schema')
    if directory_transaction.tree_hash(skin)!=record.get('source_skin_sha256') or sha(receipt)!=record.get('source_resume_receipt_sha256'):
        raise ValueError('staged source/receipt drift')
    if version(root/'addons/script.skinvariables/addon.xml')!='2.2.10':
        raise ValueError('dependency drift: script.skinvariables')
    tmdb_binding=dependencies.require_reviewed_binding(record.get('tmdbhelper'))
    dependencies.review_live_tmdb(root/'addons'/dependencies.TMDB_ID,tmdb_binding)
    candidate=stage/'candidate'/SKIN
    if (not candidate.is_dir() or version(candidate/'addon.xml')!='3.4.10' or
            directory_transaction.tree_hash(candidate)!=record.get('candidate_skin_sha256')): raise ValueError('invalid staged candidate')
    return {skin:candidate}

def apply_candidate(storage_root, stage, profile, hostname_reader=None, mac_reader=None, run=None, switch=directory_transaction.replace, parent_guard=canonical_parent_plan):
    """Injectable integration seam; CLI deliberately does not expose it yet."""
    storage_root=Path(storage_root).resolve();root=storage_root/'.kodi'
    hostname_reader=hostname_reader or (lambda: lifecycle.appliance_hostname(storage_root))
    mac_reader=mac_reader or lifecycle.appliance_mac
    lifecycle.identity(root,profile,hostname_reader(),mac_reader())
    changes=plan(storage_root,stage,profile,parent_guard)
    target,source=next(iter(changes.items()))
    kwargs={'protected':PROTECTED}
    # Re-run the full manifest/profile guard after Kodi is stopped: no source
    # file can change between planning and the directory switch unnoticed.
    def mutate():
        # Rebuild the complete candidate plan after stop.  This repeats parent
        # manifest validation *and* stage/source-tree/dependency checks; a
        # changed file, profile or candidate can never reuse the pre-stop plan.
        refreshed=plan(storage_root,stage,profile,parent_guard)
        lifecycle.identity(root,profile,hostname_reader(),mac_reader())
        refreshed_target,refreshed_source=next(iter(refreshed.items()))
        if (refreshed_target,refreshed_source)!=(target,source):
            raise RuntimeError('candidate changed while Kodi was being stopped')
        return switch(refreshed_target,refreshed_source,**kwargs)
    if run is None: return lifecycle.with_stopped_kodi(mutate)
    return lifecycle.with_stopped_kodi(mutate,run=run)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--storage-root',type=Path,default=Path('/storage'));p.add_argument('--stage',type=Path,required=True);p.add_argument('--profile',type=Path,required=True);p.add_argument('--apply',action='store_true');p.add_argument('--idle-confirmation',type=Path)
    a=p.parse_args(); profile=json.loads(a.profile.read_text()); changes=plan(a.storage_root,a.stage,profile); print(json.dumps({'release':RELEASE,'cohort':profile['cohort'],'changes':[str(x.relative_to(a.storage_root)) for x in changes],'mode':'apply' if a.apply else 'plan'}))
    if a.apply:
        raise SystemExit('apply is disabled: compose the reviewed paired transaction/idle-RPC framework before enabling deployment')
