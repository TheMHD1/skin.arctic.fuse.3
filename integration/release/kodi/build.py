"""Build the reviewed Kodi payload from a clean public-fork checkout."""
import argparse
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
FORK=HERE.parents[2]
JELLYFIN_COMMIT='a1aeda1352eb49c16d8da877121ea2068a7a7508'
PATCHES=('jellyfin-2.2.0-habibi.patch','jellyfin-tls-secure-default.patch','jellyfin-native-originals.patch')
REMOTE_PATCH=FORK/'integration/patches/venom-remote-performance.patch'
REMOTE_PATCH_SHA='2c7bf2737473c7eed249c6fa3a9a637d1f19eafa0ba1ac179183a9d162f6abbb'
INPUTS={
    'native_originals.py':(FORK/'integration/jellyfin_native_originals.py','656df894c18d6d005c7d81a5ec04b3a9957a744f36ead16c6c05358309252171'),
    'search.py':(HERE/'baseline-r6/search.py','74a5b1dcb21b36ca3004179b81cf3d2f4e7894025bba85fe8a941c68d8033ee8'),
    'venom/browser.py':(FORK/'integration/plugin.video.venom.tv/browser.py','f8d1c57b08a03e3df73036c91e760214e4127ee6a697c6e83ee6f15af558b281'),
    'venom/default.py':(FORK/'integration/plugin.video.venom.tv/default.py','edbf99577e7238caad07529b8ed62665f2a5b189190b894c691941ac10c1b027'),
    'venom/shared_favorites.py':(FORK/'integration/plugin.video.venom.tv/shared_favorites.py','ab270c3806c4916b2a793b65570d650e8df06dac692e490215351e0f68e34df4'),
    'remote-venom/remote_catalogue.py':(FORK/'integration/remote-venom/remote_catalogue.py','43060f46af6ab85133c13efdc2ccc183674cac32f9a1254beb82d2c10cb3527f'),
}
OUTPUTS={
    'jellyfin/api.py':'60397069f460c2ba79a183ed8904c31ce811097ae8e4cd9cdabdc64b976be4d4',
    'jellyfin/http.py':'cc8223016710bbeaae86034428f8b35d0d7fa376a11886f017ed297530bd6005',
    'jellyfin/playutils.py':'1a786411ee85f9fe68cf994563ce83c02f9911aa86696f54b68a264462f186c9',
    'native_originals.py':INPUTS['native_originals.py'][1],
    'search.py':INPUTS['search.py'][1],
    'venom/browser.py':INPUTS['venom/browser.py'][1],
    'venom/default.py':INPUTS['venom/default.py'][1],
    'venom/shared_favorites.py':INPUTS['venom/shared_favorites.py'][1],
    'remote-venom/browser.py':'f9cb951e99f567d5c5983e563bc9cf4b1a7f12160a43187d37bc962f3e0e8467',
    'remote-venom/default.py':'1501d9dd341a25e33f07e476da1c5d822d488d277e1e71786b07071997327777',
    'remote-venom/remote_catalogue.py':INPUTS['remote-venom/remote_catalogue.py'][1],
}

def sha(data):return hashlib.sha256(data).hexdigest()
def run(*args,cwd=None):subprocess.run(args,cwd=cwd,check=True)
def pinned(name):
    path,digest=INPUTS[name];data=path.read_bytes()
    if sha(data)!=digest:raise RuntimeError('Changed reviewed fork source: '+str(path))
    return data

def prepare_jellyfin(work,supplied=None):
    source=work/'jellyfin-kodi'
    if supplied:
        supplied=Path(supplied).resolve()
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=supplied,text=True).strip()
        if commit!=JELLYFIN_COMMIT:raise RuntimeError('Supplied Jellyfin checkout is not the reviewed commit')
        status=subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=supplied,text=True)
        if status:raise RuntimeError('Supplied Jellyfin checkout is not clean')
        # Export only the reviewed committed object; ignored local files never
        # enter the build even when the supplied checkout considers them clean.
        run('git','clone','-q','--no-local',str(supplied),str(source))
        run('git','checkout','-q','--detach',JELLYFIN_COMMIT,cwd=source)
    else:
        run('git','init','-q',str(source))
        run('git','fetch','-q','--depth=1','https://github.com/jellyfin/jellyfin-kodi.git',JELLYFIN_COMMIT,cwd=source)
        run('git','checkout','-q','--detach','FETCH_HEAD',cwd=source)
    for name in PATCHES:
        patch=FORK/'integration/patches'/name
        run('git','apply','--check',str(patch),cwd=source)
        run('git','apply',str(patch),cwd=source)
    native=pinned('native_originals.py')
    (source/'jellyfin_kodi/helper/native_originals.py').write_bytes(native)
    return source

def build(output,jellyfin_source=None):
    output=Path(output).resolve()
    if output.exists() and any(output.iterdir()):raise RuntimeError('Output directory must be absent or empty')
    with tempfile.TemporaryDirectory(prefix='habibi-release-build-') as temp:
        work=Path(temp);jf=prepare_jellyfin(work,jellyfin_source)
        products={
            'jellyfin/api.py':(jf/'jellyfin_kodi/helper/api.py').read_bytes(),
            'jellyfin/http.py':(jf/'jellyfin_kodi/jellyfin/http.py').read_bytes(),
            'jellyfin/playutils.py':(jf/'jellyfin_kodi/helper/playutils.py').read_bytes(),
            **{name:pinned(name) for name in INPUTS},
        }
        if sha(REMOTE_PATCH.read_bytes())!=REMOTE_PATCH_SHA:raise RuntimeError('Changed reviewed remote overlay')
        remote=work/'remote';remote.mkdir()
        for name in ('browser.py','default.py'):(remote/name).write_bytes(products['venom/'+name])
        run('git','apply','--check',str(REMOTE_PATCH),cwd=remote);run('git','apply',str(REMOTE_PATCH),cwd=remote)
        for name in ('browser.py','default.py'):products['remote-venom/'+name]=(remote/name).read_bytes()
        for name,data in products.items():
            if sha(data)!=OUTPUTS[name]:raise RuntimeError('Unexpected built payload: '+name)
            compile(data,name,'exec')
        output.mkdir(parents=True,exist_ok=True)
        for name,data in products.items():
            target=output/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        manifest='\n'.join(OUTPUTS[name]+'  '+name for name in sorted(OUTPUTS))+'\n'
        (output/'SHA256SUMS').write_text(manifest)
    return products

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--jellyfin-source',help='clean checkout at the pinned commit; otherwise fetch it')
    args=parser.parse_args();products=build(args.output,args.jellyfin_source)
    for name in sorted(products):print(OUTPUTS[name],name)
if __name__=='__main__':main()
