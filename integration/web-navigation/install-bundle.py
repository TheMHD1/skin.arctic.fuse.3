#!/usr/bin/env python3
"""Install a version-matched web bundle; keep existing hashed chunks and custom scripts."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            attributes = dict(attrs)
            source = attributes.get('src', '')
            if source.startswith(('venom-', 'habibi-')) and '/' not in source:
                self.tags.append(self.get_starttag_text() + '</script>')


def install(archive, digest, web, backup, server, version):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise RuntimeError('Bundle checksum mismatch')
    with urllib.request.urlopen(server.rstrip('/') + '/System/Info/Public', timeout=10) as response:
        if json.load(response).get('Version') != version:
            raise RuntimeError('Server version mismatch')
    if not (web / 'index.html').is_file():
        raise RuntimeError('Target is not an existing bundled web tree')
    backup.mkdir(mode=0o700, parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='library-search-web-') as temporary:
        stage = Path(temporary)
        with tarfile.open(archive) as bundle:
            bundle.extractall(stage, filter='data')
        index = stage / 'index.html'
        html = index.read_text()
        if '</body>' not in html or 'main.jellyfin.bundle.js' not in html:
            raise RuntimeError('Unexpected web bundle index')
        original_index = (web / 'index.html').read_bytes()
        parser = Scripts()
        parser.feed(original_index.decode())
        preserved = ''.join(tag for tag in parser.tags if tag not in html)
        index.write_text(html.replace('</body>', preserved + '</body>'))
        if (web / 'index.html').read_bytes() != original_index:
            raise RuntimeError('Live web changed during planning')
        files = sorted((path for path in stage.rglob('*') if path.is_file()),
                       key=lambda path: (path.name == 'index.html', path.name == 'serviceworker.js', str(path)))
        manifest = []
        for source in files:
            relative = source.relative_to(stage)
            target = web / relative
            if target.is_file() and target.read_bytes() == source.read_bytes():
                continue
            existed = target.is_file()
            if existed:
                saved = backup / relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
            target.parent.mkdir(parents=True, exist_ok=True)
            pending = target.with_name(target.name + '.library-experience-new')
            if pending.exists():
                raise RuntimeError('Foreign staging file found')
            shutil.copy2(source, pending)
            os.replace(pending, target)
            manifest.append({'path': str(relative), 'existed': existed})
        (backup / 'changes.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'changed_files': len(manifest), 'preserved_custom_scripts': len(parser.tags),
                      'backup': str(backup), 'server_restart': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--web', required=True, type=Path)
    parser.add_argument('--backup', required=True, type=Path)
    parser.add_argument('--server', required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    install(args.archive, args.sha256, args.web, args.backup, args.server, args.version)
