"""Build a reviewable Arctic Fuse 3.4.10 managed overlay, never deploy it."""
import argparse, hashlib, json, shutil, subprocess, tempfile
from pathlib import Path
import overlay

HERE=Path(__file__).resolve().parent
def sha(data): return hashlib.sha256(data).hexdigest()
def checked_source(source):
    source=Path(source).resolve()
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()!=overlay.UPSTREAM_COMMIT: raise RuntimeError('not pinned Arctic 3.4.10 source')
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=source,text=True): raise RuntimeError('skin source is not clean')
    if 'version="3.4.10"' not in (source/'addon.xml').read_text(): raise RuntimeError('unexpected skin manifest')
    return source
def build(source, output):
    source=checked_source(source); output=Path(output).resolve()
    if output.exists() and any(output.iterdir()): raise RuntimeError('output must be absent or empty')
    with tempfile.TemporaryDirectory(prefix='arctic-3410-') as tmp:
        tmp=Path(tmp); baseline=tmp/'baseline'; candidate=tmp/'candidate'; shutil.copytree(source,baseline,ignore=shutil.ignore_patterns('.git')); shutil.copytree(baseline,candidate)
        # A disposable repository makes a portable patch with skin-relative
        # paths, rather than no-index's baseline/ and candidate/ prefixes.
        for args in (['git','init','-q'], ['git','config','user.name','AM9 staged builder'],
                     ['git','config','user.email','noreply@localhost'], ['git','add','-A'],
                     ['git','commit','-q','-m','upstream Arctic Fuse 3.4.10']):
            subprocess.run(args,cwd=candidate,check=True)
        overlay.transform(candidate); changed=[]
        for path in sorted(candidate.rglob('*')):
            if not path.is_file() or '.git' in path.relative_to(candidate).parts:
                continue
            relative=path.relative_to(candidate); previous=baseline/relative
            if not previous.exists() or path.read_bytes()!=previous.read_bytes():
                changed.append(relative)
        output.mkdir(parents=True,exist_ok=True); skin=output/'skin'
        for relative in changed:
            target=skin/relative; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes((candidate/relative).read_bytes())
        sums={str(p):sha((candidate/p).read_bytes()) for p in changed}; (output/'SHA256SUMS.json').write_text(json.dumps(sums,indent=2,sort_keys=True)+'\n')
        # Intent-to-add includes the four new selector templates in the patch
        # without staging any changed bytes in this disposable repository.
        subprocess.run(['git','add','-N','.'],cwd=candidate,check=True)
        result=subprocess.run(['git','diff','--binary','HEAD'],cwd=candidate,stdout=subprocess.PIPE,check=False)
        if result.returncode: raise RuntimeError('git diff failed')
        (output/'arctic-3.4.10-habibi.patch').write_bytes(result.stdout)
    return changed
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args();print('\n'.join(map(str,build(a.source,a.output))))
