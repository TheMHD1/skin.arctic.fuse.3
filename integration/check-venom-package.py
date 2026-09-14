"""Offline checks for the standalone Venom source package, not all skin patches."""
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
addon=ROOT/'plugin.video.venom.tv'
manifest=ET.parse(addon/'addon.xml').getroot()
assert manifest.attrib['id']=='plugin.video.venom.tv'
required=['default.py','browser.py','shared_favorites.py','venom_state.py']
with tempfile.TemporaryDirectory(prefix='venom-package-check-') as tmp:
    for name in required:
        py_compile.compile(str(addon/name),cfile=str(Path(tmp)/(name+'c')),doraise=True)
layout=ET.parse(addon/'resources/skins/Default/1080i/VenomBrowser.xml').getroot()
ids=[c.get('id') for c in layout.iter('control') if c.get('id')]
assert len(ids)==len(set(ids))
for control in layout.iter('control'):
    for direction in ('onleft','onright','onup','ondown'):
        target=control.findtext(direction)
        if target and target.isdigit():assert target in ids,(direction,target)
for relative in ['test-venom-shared-favorites.py','server/test-venom-channel-health-policy.py',
                 'server/test-venom-provider-missing-check.py','server/test-venom-hide-plan.py',
                 'server/test-venom-hide-worker.py']:
    subprocess.run([sys.executable,str(ROOT/relative)],check=True)
print('PASS: add-on syntax/XML, shared favourites and server evidence/visibility tests')
print('Scope: no Kodi runtime, playback, skin patch application or native Moonfin verification')
