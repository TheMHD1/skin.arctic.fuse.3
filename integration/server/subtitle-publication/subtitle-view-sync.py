#!/usr/bin/env python3
"""Fast per-item subtitle view update; never creates/bypasses a video entry."""
import importlib.util
import os
from pathlib import Path
import uuid


def sync(video, canonical_root='/data/media', view_root='/data/media/compatibility/jellyfin-view'):
    spec=importlib.util.spec_from_file_location('subtitle_filter',Path(__file__).with_name('subtitle-view-filter.py'))
    policy=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    video=Path(video)
    root=Path(canonical_root)
    relative=video.relative_to(root)
    if not relative.parts or relative.parts[0] not in ('shows','movies'):
        raise ValueError('not a canonical movie/show')
    target_video=Path(view_root)/relative
    if not target_video.is_file():
        return {'ready':False,'reason':'video compatibility entry pending','linked':0,'removed':0}
    marker=video.with_suffix('.subengine.json')
    data=policy.verified_marker(marker)
    if not data:
        return {'ready':False,'reason':'no current verified manifest','linked':0,'removed':0}
    linked=removed=0
    for track in data['roles'].values():
        source=Path(track['path'])
        if source.suffix!='.srt':
            raise ValueError('non-subtitle role')
        destination=Path(view_root)/source.relative_to(root)
        if destination.exists() and destination.stat().st_ino==source.stat().st_ino and destination.stat().st_dev==source.stat().st_dev:
            continue
        temporary=destination.parent/('.subtitle-view-'+uuid.uuid4().hex)
        try:
            os.link(source,temporary)
            if policy.digest(temporary)!=track['hash']:
                raise RuntimeError('subtitle changed while linking view')
            os.replace(temporary,destination)
            linked+=1
        finally:
            if temporary.exists():temporary.unlink()
    hidden=policy.hidden_sources(marker)
    retired=policy.retired_sources(marker)
    for name,expected in {**hidden,**retired}.items():
        destination=Path(view_root)/Path(name).relative_to(root)
        if destination.exists() and policy.digest(destination)==expected:
            destination.unlink()
            removed+=1
    fd=os.open(target_video.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'ready':True,'linked':linked,'removed':removed}
