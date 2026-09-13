"""Reproduce tests against pinned upstream sources; never touches a live Kodi."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
def run(*args, cwd=None):subprocess.run(args,cwd=cwd,check=True)
def fetch(url,commit,path):
    run('git','init','-q',str(path))
    run('git','fetch','-q','--depth=1',url,commit,cwd=path)
    run('git','checkout','-q','--detach','FETCH_HEAD',cwd=path)

ET.parse(ROOT/'shortcuts/generator/data/setup/widgets_row.xml')
ET.parse(HERE/'plugin.video.habibi.resume/addon.xml')
with tempfile.TemporaryDirectory(prefix='arctic-integration-test-') as tmp:
    work=Path(tmp)
    shutil.copytree(HERE/'plugin.video.habibi.resume',work/'plugin.video.habibi.resume')
    for test in HERE.glob('test-*.py'):shutil.copy2(test,work/test.name)
    kodi=work/'kodiseerr-upstream'
    fetch('https://github.com/yocksers/KodiSeerr.git','8d23b6c14473f747080719884cd998fa98a17fc6',kodi)
    jf=work/'jellyfin-upstream'
    fetch('https://github.com/jellyfin/jellyfin-kodi.git','00c33dba4658ceeaefb37ed7f1d1037e5c98feb1',jf)
    for folder,patch in ((kodi,'kodiseerr.patch'),(jf,'jellyfin-kodi.patch')):
        run('git','apply','--check',str(HERE/'patches'/patch),cwd=folder)
        run('git','apply',str(HERE/'patches'/patch),cwd=folder)
    shutil.copy2(jf/'jellyfin_kodi/player.py',work/'ugoos-jellyfin-player.py')
    for test in sorted(work.glob('test-*.py')):run(sys.executable,str(test))
    run(sys.executable,'-m','compileall','-q',str(work/'plugin.video.habibi.resume'),str(kodi/'plugin.video.kodiseerr'))
print('PASS: skin XML, clean patch application, integration regressions and compile checks')
