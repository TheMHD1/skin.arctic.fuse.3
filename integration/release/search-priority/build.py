"""Build the reviewed search-priority and card-rating payload."""
import argparse
import hashlib
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FORK = HERE.parents[2]
SOURCES = {
    'home/client.py':FORK/'integration/plugin.video.habibi.resume/client.py',
    'home/default.py':FORK/'integration/plugin.video.habibi.resume/default.py',
    'skin/search_selector.xml':FORK/'shortcuts/generator/data/base/search_selector.xml',
    'skin/search_selector_venom.xml':FORK/'shortcuts/generator/data/base/search_selector_venom.xml',
    'skin/search_selector_wall.xml':FORK/'shortcuts/generator/data/base/search_selector_wall.xml',
    'skin/search_selector_wall_venom.xml':FORK/'shortcuts/generator/data/base/search_selector_wall_venom.xml',
    'skin/skinvariables-generator.json':FORK/'shortcuts/skinvariables-generator.json',
}
OUTPUTS = {
    'home/client.py':'c742d7e46fb75c7b61ae68c94a9bfb781c18c0435bef722e870913d20712b6ca',
    'home/default.py':'987a6724a3cd1028ccbc840ef9623063145ad3bb8647d98f25a34475febd7b67',
    'skin/search_selector.xml':'6b07d840134d1a1e061e95b9f57b9f251b45fa0ad3ce71a1f1ebb904b5808951',
    'skin/search_selector_venom.xml':'9b86efcc50ddab37cedd169544cd4f9f9e051ff08c01e0e5da0bf5267da20c5a',
    'skin/search_selector_wall.xml':'0aa29ec928ee784413de1bd97b98c6ac3d5c0fcc91ad19a6389dedd4ab6fe4e1',
    'skin/search_selector_wall_venom.xml':'eaea2f719f5e0dd5f250e7997e865a565c748b49402979cbc82f2434467ed2dc',
    'skin/skinvariables-generator.json':'ad0414884854b24394c9d1e240722308b1b1d8b37d7011df7f6115a76ba2f7e2',
}


def sha(data): return hashlib.sha256(data).hexdigest()


def ensure_clean():
    names=[str(path.relative_to(FORK)) for path in SOURCES.values()]
    for name in names:
        subprocess.run(['git','ls-files','--error-unmatch',name],cwd=FORK,check=True,
                       stdout=subprocess.DEVNULL)
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--',*names],
                               cwd=FORK,text=True):
        raise RuntimeError('Reviewed search-priority sources are not committed and clean')


def build(output, check_clean=True):
    if check_clean: ensure_clean()
    output=Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError('Output directory must be absent or empty')
    output.mkdir(parents=True,exist_ok=True)
    for name,source in SOURCES.items():
        data=source.read_bytes()
        if sha(data)!=OUTPUTS[name]: raise RuntimeError('Changed reviewed source: '+str(source))
        if name.endswith('.py'): compile(data,str(source),'exec')
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    (output/'SHA256SUMS').write_text(''.join(OUTPUTS[name]+'  '+name+'\n' for name in sorted(OUTPUTS)))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    build(args.output)
    for name in sorted(OUTPUTS):print(OUTPUTS[name],name)


if __name__=='__main__':main()
