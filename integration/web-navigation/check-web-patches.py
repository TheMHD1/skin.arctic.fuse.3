#!/usr/bin/env python3
"""Verify pinned clean Web/Enhanced patch application without touching live services."""
import argparse
from pathlib import Path
import subprocess
import tempfile

INTEGRATION = Path(__file__).resolve().parents[1]
WEB_PIN = 'fae41f33eb7cd636a9ef68984adb82bb247a6e1b'
ENHANCED_PIN = 'daf5b10c09d017941e29a79a0a45d0ab31c34abc'

def run(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True)

def prepare(destination, repository, pin, patches):
    run('git', 'init', '-q', str(destination))
    run('git', 'fetch', '-q', '--depth=1', repository, pin, cwd=destination)
    run('git', 'checkout', '-q', '--detach', 'FETCH_HEAD', cwd=destination)
    for patch in patches:
        run('git', 'apply', '--check', str(patch), cwd=destination)
        run('git', 'apply', str(patch), cwd=destination)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web-source', default='https://github.com/jellyfin/jellyfin-web.git')
    parser.add_argument('--enhanced-source', default='https://github.com/n00bcodr/Jellyfin-Enhanced.git')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='habibi-web-check-') as temp:
        root = Path(temp)
        prepare(root / 'web', args.web_source, WEB_PIN, [
            INTEGRATION / 'web-navigation/search-jellyfin-web-12.1.patch',
            INTEGRATION / 'web-home-library/jellyfin-web-12.1-owned-home.patch',
        ])
        prepare(root / 'enhanced', args.enhanced_source, ENHANCED_PIN, [
            INTEGRATION / 'patches/jellyfin-enhanced-12.7-tabs.patch',
            INTEGRATION / 'patches/jellyfin-enhanced-12.7-search-priority.patch',
        ])
        run('node', str(INTEGRATION / 'web-navigation/test-search-priority.cjs'), str(root / 'enhanced'))
        for relative in ('src/components/homesections/sections/ownedLibrary.ts',
                         'src/apps/legacy/features/search/components/SearchResultsRow.tsx'):
            assert (root / 'web' / relative).is_file()
    print('PASS: pinned clean Web/Home/Enhanced patch stack and search placement')

if __name__ == '__main__':
    main()
