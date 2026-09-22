"""Reproduce tests against pinned upstream sources; never touches a live Kodi."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
SOURCE_LAYOUT_TESTS=('test-search-default.py',)
def run(*args, cwd=None):subprocess.run(args,cwd=cwd,check=True)
def fetch(url,commit,path):
    run('git','init','-q',str(path))
    # KodiSeerr has CRLF sources; match the patch-generation normalization.
    run('git','config','core.autocrlf','input',cwd=path)
    run('git','fetch','-q','--depth=1',url,commit,cwd=path)
    run('git','checkout','-q','--detach','FETCH_HEAD',cwd=path)

ET.parse(ROOT/'shortcuts/generator/data/setup/widgets_row.xml')
ET.parse(HERE/'plugin.video.habibi.resume/addon.xml')
for name in ('Custom_1107_LiveTV.xml','Includes_Home.xml','Includes_LiveTV.xml'):
    ET.parse(ROOT/'1080i'/name)
with tempfile.TemporaryDirectory(prefix='arctic-integration-test-') as tmp:
    work=Path(tmp)
    shutil.copytree(HERE/'plugin.video.habibi.resume',work/'plugin.video.habibi.resume')
    shutil.copytree(HERE/'plugin.video.venom.tv',work/'plugin.video.venom.tv')
    shutil.copytree(HERE/'remote-venom',work/'remote-venom')
    # Regression fixtures inspect the maintained 2.2 patch as well as the legacy
    # upstream checkout. Include them in the isolated test tree.
    shutil.copytree(HERE/'patches',work/'patches')
    shutil.copy2(HERE/'ugoos-osd-seek.py',work/'ugoos-osd-seek.py')
    shutil.copy2(HERE/'jellyfin_native_originals.py',work/'jellyfin_native_originals.py')
    for test in HERE.glob('test-*.py'):
        if test.name not in SOURCE_LAYOUT_TESTS:shutil.copy2(test,work/test.name)
    kodi=work/'kodiseerr-upstream'
    fetch('https://github.com/yocksers/KodiSeerr.git','8d23b6c14473f747080719884cd998fa98a17fc6',kodi)
    jf=work/'jellyfin-upstream'
    fetch('https://github.com/jellyfin/jellyfin-kodi.git','00c33dba4658ceeaefb37ed7f1d1037e5c98feb1',jf)
    for folder,patch in ((kodi,'kodiseerr.patch'),(jf,'jellyfin-kodi.patch'),(jf,'jellyfin-iptv-update-filter.patch'),(jf,'jellyfin-sync-performance.patch')):
        run('git','apply','--check',str(HERE/'patches'/patch),cwd=folder)
        run('git','apply',str(HERE/'patches'/patch),cwd=folder)
    shutil.copy2(jf/'jellyfin_kodi/player.py',work/'ugoos-jellyfin-player.py')
    shutil.copy2(jf/'jellyfin_kodi/helper/utils.py',work/'ugoos-jellyfin-utils.py')
    shutil.copy2(jf/'jellyfin_kodi/library.py',work/'venom-jellyfin-library.py')
    shutil.copy2(jf/'jellyfin_kodi/downloader.py',work/'venom-jellyfin-downloader.py')
    for test in sorted(work.glob('test-*.py')):run(sys.executable,str(test))
    run(sys.executable,'-m','compileall','-q',str(work/'plugin.video.habibi.resume'),str(work/'plugin.video.venom.tv'),str(kodi/'plugin.video.kodiseerr'))
# The skin source/hash regression requires the actual source-tree layout,
# not a flat temporary fixture that changes Path(__file__).parents[1]. It is
# independent of Git history and also works in a source archive.
for name in SOURCE_LAYOUT_TESTS:run(sys.executable,str(HERE/name),cwd=ROOT)
run(sys.executable,str(HERE/'check-venom-package.py'))
print('PASS: skin XML, clean patch application, integration regressions and compile checks')
