"""Presentation-only title cleanup. Never writes server metadata or filenames."""
import re

EXT = re.compile(r'\.(?:mkv|mp4|avi|m4v|ts|m2ts|webm)$', re.I)
QUALITY = re.compile(r'(?<!\w)(?:WEBDL|WEB[- .]?DL|WEBRip|Blu[- .]?ray|BDRip|BRRip|HDTV|Remux|(?:480|576|720|1080|2160|4320)[pi])(?=$|[\W_])', re.I)
MARKER = re.compile(r'(?<!\w)S(\d{1,3})E(\d{1,4})(?!\d)', re.I)
PLACEHOLDER = {'japanese', 'english', 'arabic', 'undetermined', 'unknown'}

def managed_episode_title(item):
    """Use only the managed 'Show - SxxExx - Title QUALITY' filename format."""
    name = EXT.sub('', (item.get('Path') or '').replace('\\','/').rsplit('/',1)[-1])
    match = re.search(r' - S(\d{1,3})E(\d{1,4}) - (.+)', name, re.I)
    if not match or (int(match[1]),int(match[2])) != (item.get('ParentIndexNumber'),item.get('IndexNumber')):
        return ''
    tail = match[3]
    quality = QUALITY.search(tail)
    if not quality:
        return ''
    return tail[:quality.start()].strip(' ._-')

def display_title(item):
    raw = (item.get('Name') or '').strip()
    series = (item.get('SeriesName') or '').strip()
    release = bool(EXT.search(raw) or QUALITY.search(raw) or MARKER.search(raw))
    junk = raw.casefold() in PLACEHOLDER or bool(re.match(r'^(?:x26[45]|bdrip\s+by)\b',raw,re.I))
    repeated = bool(series and raw.casefold().startswith(series.casefold()) and re.search(r' - \d+$',raw))
    if not (release or junk or repeated or not raw):
        return raw
    if item.get('Type') == 'Episode':
        managed = managed_episode_title(item)
        if managed:
            return managed
        # Release-style title with no reliable episode name: show episode number,
        # not an invented metadata title or release-group/language suffix.
        return 'Episode {}'.format(item.get('IndexNumber', '?'))
    text = EXT.sub('',raw)
    quality = QUALITY.search(text)
    if quality:
        text = text[:quality.start()]
    if release:
        text = text.replace('.', ' ').replace('_',' ')
        text = re.sub(r'\s*\((?:19|20)\d{2}\)\s*$', '', text)
    return re.sub(r'\s+',' ',text).strip(' ._-') or 'Untitled'

def display_label(item):
    title = display_title(item)
    if item.get('Type') != 'Episode':
        return title
    season, episode = item.get('ParentIndexNumber'), item.get('IndexNumber')
    code = 'S{:02d}E{:02d}'.format(season,episode) if isinstance(season,int) and isinstance(episode,int) else 'Episode'
    parts = [item.get('SeriesName') or '',code]
    if title != 'Episode {}'.format(episode):
        parts.append(title)
    return ' · '.join(p for p in parts if p)
