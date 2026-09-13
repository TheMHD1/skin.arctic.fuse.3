"""Read-only update guard. Never applies old patches to newly updated addons."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

def check(root, manifest):
    problems=[]
    for addon,expected in manifest.get('versions',{}).items():
        try:
            actual=ET.parse(Path(root)/'addons'/addon/'addon.xml').getroot().get('version')
            if actual!=expected:problems.append(addon+' version '+str(actual)+' (verified '+expected+')')
        except (OSError,ET.ParseError):problems.append(addon+' manifest unavailable')
    for relative,expected in manifest['files'].items():
        path=Path(root)/relative
        if not path.is_file():problems.append(relative+' (missing)')
        elif hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            problems.append(relative+' (changed since verified build)')
    return problems

def startup_check():
    import xbmc,xbmcgui,xbmcvfs
    root=Path(xbmcvfs.translatePath('special://home'))
    manifest=json.loads((Path(__file__).parent/'verified-build.json').read_text())
    problems=check(root,manifest)
    profile=Path(xbmcvfs.translatePath('special://profile/addon_data/plugin.video.habibi.resume'))
    profile.mkdir(parents=True,exist_ok=True)
    (profile/'compatibility-report.json').write_text(json.dumps({'verified_versions':manifest['versions'],'problems':problems},indent=2))
    if problems:
        xbmc.log('Habibi compatibility check: '+ '; '.join(problems),xbmc.LOGWARNING)
        xbmcgui.Dialog().notification('Jellyfin integration needs review','An update changed a verified custom fix. See compatibility report.',time=8000)
    else:xbmc.log('Habibi compatibility check: all verified fixes intact',xbmc.LOGINFO)
