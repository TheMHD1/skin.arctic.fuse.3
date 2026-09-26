"""Verify managed subtitle publication in Jellyfin; refresh only the exact item."""
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path


def normalized(data):
    text = data.decode('utf-8-sig').replace('\r\n', '\n').strip()
    return [re.sub(r'\s+', ' ', b[b.index('-->')-13:].strip())
            for b in re.split(r'\n\s*\n', text) if '-->' in b]


class TracksPending(RuntimeError):
    """Files are valid but Jellyfin has not published this revision yet."""


def synchronize(video, root, url, token, log=print, request=None, sleep=time.sleep, item_id=None,
                poll_attempts=6, refresh=True):
    root = Path(root)
    key = hashlib.sha256(os.path.realpath(video).encode()).hexdigest()
    state = root / 'four-track-state' / (key + '.json')
    if not state.exists():
        return  # Legacy two-track processing has no managed manifest.
    manifest = json.loads(state.read_text())
    if manifest.get('status') != 'complete':
        raise RuntimeError('Subtitle publication is not complete')
    roles = manifest['roles']
    if not roles or not {'en_asr', 'ar_asr'}.issubset(roles):
        raise RuntimeError('Missing managed subtitle roles')
    expected = {}
    for role, track in roles.items():
        data = Path(track['path']).read_bytes()
        if hashlib.md5(data).hexdigest() != track['hash']:
            raise RuntimeError('Published subtitle changed before Jellyfin verification')
        expected[role] = normalized(data)
        if not expected[role]:
            raise RuntimeError('Empty published subtitle')

    def http(path, method='GET'):
        req = urllib.request.Request(url.rstrip('/') + path,
            data=b'' if method == 'POST' else None, method=method,
            headers={'Authorization': 'MediaBrowser Token="' + token + '"'})
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()

    request = request or http
    # Fields=Path avoids expensive full-library MediaStreams serialization.
    # Exact full path prevents localized titles or duplicate basenames misrouting.
    matches = []
    start = 0
    while item_id is None:
        page = json.loads(request('/Items?Recursive=true&IncludeItemTypes=Episode,Movie'
            '&Fields=Path&Limit=500&StartIndex=' + str(start)))
        items = page['Items']
        matches.extend(i for i in items if i.get('Path') == video)
        start += len(items)
        if not items or start >= page['TotalRecordCount']:
            break
        if start >= 100000:
            raise RuntimeError('Jellyfin lookup exceeded bounded item limit')
    if item_id is None and len(matches) != 1:
        raise RuntimeError('Expected exactly one Jellyfin item for media path')
    item_id = urllib.parse.quote(item_id or matches[0]['Id'], safe='')

    def verified():
        result = json.loads(request('/Items?Ids=' + item_id + '&Fields=Path,MediaStreams,MediaSources'))
        if len(result['Items']) != 1:
            return False
        item = result['Items'][0]
        if item.get('Path') != video or not item.get('MediaSources'):
            return False
        streams = [s for s in item.get('MediaStreams', [])
                   if s.get('Type') == 'Subtitle' and s.get('IsExternal')]
        default_role = 'en_download' if 'en_download' in roles else 'en_asr'
        for role, track in roles.items():
            found = [s for s in streams if s.get('Path') == track['path']]
            if len(found) != 1:
                return False
            stream = found[0]
            if bool(stream.get('IsDefault')) != (role == default_role):
                return False
            title = Path(track['path']).name[len(Path(video).stem)+1:]
            title = re.sub(r'\.(en|ar)(\.default)?\.srt$', '', title)
            if stream.get('Title') != title:
                return False
            source = urllib.parse.quote(item['MediaSources'][0]['Id'], safe='')
            served = request('/Videos/' + item_id + '/' + source + '/Subtitles/'
                             + str(stream['Index']) + '/Stream.srt')
            if normalized(served) != expected[role]:
                return False
        return True

    if verified():
        log('Jellyfin managed tracks already verified')
        return
    if refresh:
        request('/Items/' + item_id + '/Refresh?MetadataRefreshMode=Default'
            '&ImageRefreshMode=None&ReplaceAllMetadata=false&ReplaceAllImages=false'
            '&RegenerateTrickplay=false', 'POST')
    for attempt in range(poll_attempts):
        sleep(5)
        if verified():
            log('Jellyfin managed tracks verified after scoped refresh')
            return
    raise TracksPending('Jellyfin managed tracks still stale after scoped refresh; retry required')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('video')
    parser.add_argument('--root', default='/data/config/bazarr/scripts')
    args = parser.parse_args()
    config = (Path(args.root) / 'post-sub.sh').read_text()
    url = re.search(r'JELLYFIN_URL="([^"]+)"', config).group(1)
    token = re.search(r'JELLYFIN_KEY="([^"]+)"', config).group(1)
    synchronize(args.video, args.root, url, token)
