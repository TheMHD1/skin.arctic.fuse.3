#!/usr/bin/env python3
"""Hide raw provider inputs only while their verified named replacements exist."""
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def verified_marker(marker):
    try:
        data = json.loads(Path(marker).read_text())
        if data.get('status') != 'complete':
            return {}
        video = Path(data['video'])
        stem = video.with_suffix('')
        if Path(str(stem) + '.subengine.json') != Path(marker):
            return {}
        roles = data['roles']
        if set(roles) not in ({'en_asr','ar_asr'}, {'en_asr','ar_asr','en_download','ar_download'}):
            return {}
        for track in roles.values():
            path = Path(track['path'])
            if path.parent != video.parent or not path.name.startswith(stem.name + '.'):
                return {}
            if digest(path) != track['hash']:
                return {}
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def hidden_sources(marker):
    try:
        data = verified_marker(marker)
        if not data:
            return {}
        stem = Path(data['video']).with_suffix('')
        hidden = {}
        for path, expected in data.get('hidden_sources', {}).items():
            # Only the raw English provider input may be suppressed. Never allow
            # a corrupt marker to hide a video, Arabic original or unrelated file.
            if path != str(stem) + '.en.srt' or not expected or digest(path) != expected:
                return {}
            hidden[path] = expected
        return hidden
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def retired_sources(marker):
    """Allow immediate removal of stale view links only with a verified archive."""
    try:
        data = verified_marker(marker)
        if not data:
            return {}
        video = Path(data['video'])
        stem = video.with_suffix('')
        retired = {}
        for name, expected in data.get('retire', {}).items():
            path = Path(name)
            if path.parent != video.parent or not path.name.startswith(stem.name+'.') or path.suffix != '.srt':
                continue
            if path.exists():
                continue  # A provider recreated this path: preserve it.
            archive = name + '.retired-subengine-' + expected + '.bak'
            if digest(archive) == expected:
                retired[name] = expected
        return retired
    except (OSError, ValueError, KeyError, TypeError):
        return {}
