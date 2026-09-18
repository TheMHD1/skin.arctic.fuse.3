"""Check the current 2.2 catch-up patch separately from the legacy 2.1 suite."""
import shutil,subprocess,sys,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='kodi22-catchup-') as temp:
    root=Path(temp);source=root/'source'
    def run(*args,cwd=None):subprocess.run(args,cwd=cwd,check=True)
    run('git','init','-q',str(source))
    run('git','fetch','-q','--depth=1','https://github.com/jellyfin/jellyfin-kodi.git','a1aeda1352eb49c16d8da877121ea2068a7a7508',cwd=source)
    run('git','checkout','-q','--detach','FETCH_HEAD',cwd=source)
    run('git','apply',str(here/'patches/jellyfin-2.2.0-habibi.patch'),cwd=source)
    shutil.copy2(source/'jellyfin_kodi/library.py',root/'venom-jellyfin-library.py')
    shutil.copy2(source/'jellyfin_kodi/jellyfin/api.py',root/'venom-jellyfin-api.py')
    shutil.copy2(here/'verify-sync-catchup.py',root/'verify-sync-catchup.py')
    run(sys.executable,str(root/'verify-sync-catchup.py'))
    run(sys.executable,'-m','compileall','-q',str(source/'jellyfin_kodi'))
run(sys.executable,str(here/'test-venom-browser.py'))
print('PASS: clean 2.2 patch, catch-up contract, browser routing and syntax')
