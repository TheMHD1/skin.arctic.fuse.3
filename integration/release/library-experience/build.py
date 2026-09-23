"""Build the Home/library-search payload from exact reviewed fork sources."""
import argparse
import hashlib
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FORK = HERE.parents[2]
SOURCES = {
    # R7 remains an exact historical recovery cohort. Newer Home/rating work
    # ships through the separate search-priority overlay.
    'home/client.py': HERE/'baseline-r7/client.py',
    'home/search.py': FORK/'integration/plugin.video.habibi.resume/search.py',
    'home/default.py': HERE/'baseline-r7/default.py',
    'home/service.py': FORK/'integration/plugin.video.habibi.resume/service.py',
    'skin/search_path.xml': FORK/'shortcuts/generator/data/setup/search_path.xml',
    'skin/searchwidgets.json': FORK/'shortcuts/skinvariables-shortcut-searchwidgets.json',
}
# Updated together with the maintained sources after focused review.
OUTPUTS = {
    'home/client.py':'ea2ebdec9f096df0ed9c1512ab9abb4d4661d90e72c3c5d8f80899330d2ceba4',
    'home/search.py':'0b04d08e0c38066b0b4cb4d5dc52b39d6626816b69991304c6d5f59128eac3f8',
    'home/default.py':'446dcf19357f7e095ca8729fa44e6ef8604b9fc4ec2bc4a7119f892d7aca2b99',
    'home/service.py':'4bd56224430ac38c9fe9a7d5aeb6123974070174403eaa6f34da1c95b21e6ffd',
    'skin/search_path.xml':'ad2c2018bb9e80b839343d975f4b939713771853b815a828845ae8e8a394007f',
    'skin/searchwidgets.json':'f718340a491415980f2344246ae49077e42493e663240bb5729257a325cf8e20',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ensure_clean():
    for path in SOURCES.values():
        subprocess.run(['git','ls-files','--error-unmatch',str(path.relative_to(FORK))],
                       cwd=FORK, check=True, stdout=subprocess.DEVNULL)
    status = subprocess.check_output(
        ['git','status','--porcelain','--untracked-files=all','--',
         *[str(path.relative_to(FORK)) for path in SOURCES.values()]],
        cwd=FORK, text=True)
    if status:
        raise RuntimeError('Reviewed library-experience sources are not committed and clean')


def build(output, check_clean=True):
    if check_clean:
        ensure_clean()
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError('Output directory must be absent or empty')
    products = {}
    for name, source in SOURCES.items():
        data = source.read_bytes()
        if sha(data) != OUTPUTS[name]:
            raise RuntimeError('Changed reviewed source: '+str(source))
        if source.suffix == '.py':
            compile(data, str(source), 'exec')
        products[name] = data
    output.mkdir(parents=True, exist_ok=True)
    for name, data in products.items():
        target = output/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (output/'SHA256SUMS').write_text(
        ''.join(OUTPUTS[name]+'  '+name+'\n' for name in sorted(OUTPUTS)))
    return products


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    build(args.output)
    for name in sorted(OUTPUTS):
        print(OUTPUTS[name], name)


if __name__ == '__main__':
    main()
