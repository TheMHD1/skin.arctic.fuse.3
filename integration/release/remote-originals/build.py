"""Rebase only the optional native gate onto the exact remote HTTP cohort."""
import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
INTEGRATION = HERE.parents[1]
BASE = '006794f85b35b4f9ef0b8749dfe3d9fdca54e348a541cc4599704ed8dba51b5f'
NATIVE = '656df894c18d6d005c7d81a5ec04b3a9957a744f36ead16c6c05358309252171'
JELLYFIN_COMMIT = 'a1aeda1352eb49c16d8da877121ea2068a7a7508'
PRE_REMOTE = '6c44e9df8e28888968455564b6496003bd3a32d2efd65bf1dd6b19c104ec817b'
IMPORT = 'from . import translate, settings, window, dialog, api, LazyLogger\n'
ANCHOR = '''        if (
            (source.get("Protocol") == "Http" and not settings("playFromStream.bool"))'''
BRANCH = '''        native_path = remote_original_path(self.item, source, self.info["ForceTranscode"])
        if native_path:
            LOG.info("--[ verified remote native original ]")
            self.info["Method"] = "DirectPlay"
            self.info["Path"] = native_path

        elif (
            (source.get("Protocol") == "Http" and not settings("playFromStream.bool"))'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def patch_playutils(data):
    if sha(data) != BASE:
        raise ValueError('Unreviewed remote playback source; rebase, do not force')
    text = data.decode()
    if text.count(IMPORT) != 1 or text.count(ANCHOR) != 1:
        raise ValueError('Ambiguous remote playback anchors')
    text = text.replace(IMPORT, IMPORT+'from .remote_native.kodi_adapter import remote_original_path\n', 1)
    text = text.replace(ANCHOR, BRANCH, 1)
    compile(text, 'playutils.py', 'exec')
    return text.encode()


def clean_remote_base():
    """Recreate the historical remote HTTP input from pinned public source."""
    with tempfile.TemporaryDirectory(prefix='remote-native-build-') as directory:
        work = Path(directory)
        def run(*args):
            subprocess.run(args, cwd=work, check=True)
        run('git', 'init', '-q')
        run('git', 'fetch', '-q', '--depth=1', 'https://github.com/jellyfin/jellyfin-kodi.git', JELLYFIN_COMMIT)
        run('git', 'checkout', '-q', '--detach', 'FETCH_HEAD')
        for name in ('jellyfin-2.2.0-habibi.patch', 'jellyfin-tls-secure-default.patch'):
            patch = INTEGRATION/'patches'/name
            run('git', 'apply', '--check', str(patch))
            run('git', 'apply', str(patch))
        data = (work/'jellyfin_kodi/helper/playutils.py').read_bytes()
        if sha(data) != PRE_REMOTE:
            raise ValueError('Clean upstream did not reproduce the reviewed pre-remote source')
        old = '            source.get("Protocol") == "Http"\n'
        new = '            (source.get("Protocol") == "Http" and not settings("playFromStream.bool"))\n'
        if data.decode().count(old) != 1:
            raise ValueError('Unreviewed remote HTTP compatibility anchor')
        data = data.decode().replace(old, new, 1).encode()
        if sha(data) != BASE:
            raise ValueError('Remote HTTP baseline does not match the actual reviewed appliance')
        return data


def build(source, output):
    source_bytes = source.read_bytes() if source else clean_remote_base()
    output.mkdir(parents=True, exist_ok=False)
    files = {'playutils.py': patch_playutils(source_bytes)}
    native = (INTEGRATION/'jellyfin_native_originals.py').read_bytes()
    if sha(native) != NATIVE:
        raise ValueError('Unreviewed shared native mapper')
    files['native_originals.py'] = native
    for name in ('__init__.py', 'kodi_adapter.py', 'gate.py', 'manifest.py'):
        files['remote_native/'+name] = (INTEGRATION/'remote-native-originals'/name).read_bytes()
    for name, payload in files.items():
        compile(payload, name, 'exec')
        target = output/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    record = {'schema': 1, 'input_playutils': BASE,
              'files': {name: sha(payload) for name, payload in files.items()}}
    (output/'payload.json').write_text(json.dumps(record, indent=2)+'\n')
    print('Built exact remote-original gate payload:', len(files), 'files')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, help='Optional exact reviewed source; otherwise rebuild from pinned public upstream')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.input, args.output)
