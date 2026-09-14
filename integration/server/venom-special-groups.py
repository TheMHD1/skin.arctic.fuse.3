"""Persistent MBC/Syria selections and honest resolution-based companion lists."""
import re

SPECIAL = [('ar-mbc', 'MBC & related · MBC وقنوات مرتبطة', r'^\s*\|AR\|\s*MBC\b'),
           ('ar-syria', 'سوريا · Syrian channels', r'^\s*\|AR\|\s*SYRIA\b')]

def is_hdr(channel):
    if type(channel.get('decoded_hdr')) is bool:return channel['decoded_hdr']
    return bool(re.search(r'\b(?:HDR(?:10\+?)?|HLG|DOLBY[ ._-]*VISION|DV)\b',channel['name'],re.I))

def priority(channel):
    height=channel.get('decoded_height')
    if not isinstance(height,int):
        height=4320 if re.search(r'\b8K\b',channel['name'],re.I) else 2160 if re.search(r'\b(?:4K|UHD)\b',channel['name'],re.I) else 1080 if re.search(r'\b(?:FHD|HDF|1080P)\b',channel['name'],re.I) else 720 if re.search(r'\b(?:HD|720P)\b',channel['name'],re.I) else 0
    hdr=is_hdr(channel)
    return (0 if hdr and height>=2160 else 1 if hdr else 2, -height)

def extend(manifest, catalogue, working, geometry, candidates=False):
    categories={str(c['category_id']):c['category_name'] for c in catalogue['categories']}
    groups=[g for g in manifest['groups'] if not g.get('derived_quality')]
    existing={str(c['stream_id']) for g in groups for c in g['channels']}
    for key,name,pattern in SPECIAL:
        previous=next((g for g in groups if g['id']==key),None)
        rows={str(c['stream_id']):c for c in (previous or {}).get('channels',[])}
        for c in catalogue['channels']:
            cid=str(c['stream_id'])
            if re.search(pattern,categories.get(str(c['category_id']),''),re.I) and (candidates or cid in working or cid in existing):
                rows[cid]={**c,**geometry.get(cid,{})}
        group={'id':key,'name':name,'channels':list(rows.values())}
        groups=[g for g in groups if g['id']!=key]
        if group['channels']:groups.append(group)
    if not candidates:
        groups=[{**g,'channels':sorted([{**{k:v for k,v in c.items() if not k.startswith('decoded_')},**geometry.get(str(c['stream_id']),{})} for c in g['channels']],key=priority)} for g in groups]
        derived=[]
        for g in groups:
            # Pixel dimensions, not a provider's marketing label, establish quality.
            verified=[c for c in g['channels'] if geometry.get(str(c['stream_id']),{}).get('decoded_height',0)>1080]
            hd=[c for c in g['channels'] if is_hdr(c) or (geometry[str(c['stream_id'])]['decoded_height']>=720 if str(c['stream_id']) in geometry else bool(re.search(r'(?<!\w)(?:[468]K|UHD|FHD|HDF|HD|720P|1080[PI]|1440P|2160P|4320P)(?!\w)',c['name'],re.I)))]
            for suffix,label,rows in [('above-fhd','>1080p verified · دقة مثبتة',verified),('hd-plus','HD & above · HD وأعلى',hd)]:
                if rows:derived.append({'id':g['id']+'-'+suffix,'name':g['name']+' · '+label,'derived_quality':suffix,'channels':rows})
        # Keep each companion beside its main category in the browse menu.
        paired=[]
        for g in groups:
            paired.append(g)
            paired.extend(d for d in derived if d['id'] in (g['id']+'-above-fhd',g['id']+'-hd-plus'))
        groups=paired
    return {**manifest,'groups':groups,'unique_channels':len({str(c['stream_id']) for g in groups for c in g['channels']})}
