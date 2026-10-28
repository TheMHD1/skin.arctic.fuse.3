"""Create a private, non-runnable 3.4.10 staging tree and rollback snapshot."""
from __future__ import annotations
import argparse, hashlib, json, shutil
from pathlib import Path
import xml.etree.ElementTree as ET
import build, dependencies, overlay

MARKER='.arctic-3410-staging-profile'
BACKUP=('addons/skin.arctic.fuse.3','userdata/addon_data/skin.arctic.fuse.3',
        'userdata/addon_data/script.skinvariables','userdata/addon_data/plugin.video.themoviedb.helper',
        'userdata/guisettings.xml')

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def validate_profile(root):
    root=Path(root).resolve()
    if not (root/MARKER).is_file(): raise ValueError('requires explicitly marked copied staging profile')
    addon=root/'addons/skin.arctic.fuse.3/addon.xml'
    if not addon.is_file() or ET.fromstring(addon.read_bytes()).get('version')!='3.3.1': raise ValueError('not reviewed 3.3.1 staging cohort')
    for name in BACKUP[1:3]+(BACKUP[-1],):
        if not (root/name).exists(): raise ValueError('missing protected profile input: '+name)
    return root

def stage(source, profile_root, output, tmdb_artifact):
    source=build.checked_source(source); profile_root=validate_profile(profile_root); output=Path(output).resolve()
    if output.exists() and any(output.iterdir()): raise ValueError('stage output must be empty')
    dependency=dependencies.review_tmdb_artifact(tmdb_artifact); output.mkdir(parents=True,exist_ok=True)
    rollback=output/'rollback'; saved={}
    for name in BACKUP:
        path=profile_root/name
        if not path.exists(): continue
        destination=rollback/name; destination.parent.mkdir(parents=True,exist_ok=True)
        if path.is_dir(): shutil.copytree(path,destination); saved[name]='directory'
        else: shutil.copy2(path,destination); saved[name]=digest(path)
    skin=output/'candidate/addons/skin.arctic.fuse.3'; skin.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(source,skin,ignore=shutil.ignore_patterns('.git')); overlay.transform(skin)
    result={'schema':1,'status':'staged-only-requires-real-kodi-generation',
            'upstream_commit':overlay.UPSTREAM_COMMIT,'tmdbhelper':dependency,'rollback':saved,
            'generation_command':'RunScript(script.skinvariables,action=buildtemplate,force=true,no_reload=true)'}
    (output/'stage.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--source',type=Path,required=True);p.add_argument('--profile-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--tmdb-artifact',type=Path,required=True)
    print(json.dumps(stage(**vars(p.parse_args())),indent=2,sort_keys=True))
