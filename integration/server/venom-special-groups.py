"""Provider-label browse ordering; measured quality remains separately verified."""
import re

SPECIAL = [('ar-mbc', 'MBC & related · MBC وقنوات مرتبطة', r'^\s*\|AR\|\s*MBC\b'),
           ('ar-syria', 'سوريا · Syrian channels', r'^\s*\|AR\|\s*SYRIA\b')]

def is_hdr(channel):
    return channel.get('decoded_hdr') is True or bool(re.search(r'\b(?:HDR(?:10\+?)?|HLG|DOLBY[ ._-]*VISION|DV)\b',channel['name'],re.I))

def priority(channel):
    # User-facing order follows explicit provider labels, even if a probe saw
    # lower resolution. Measurements only fill in channels without quality labels.
    name=channel['name']
    k=re.search(r'\b([4-9])\s*K\b',name,re.I)
    pixels=re.search(r'\b(720|1080|1440|2160|2880|4320)[PI]\b',name,re.I)
    height=int(k[1])*540 if k else int(pixels[1]) if pixels else 2160 if re.search(r'\bUHD\b',name,re.I) else 1080 if re.search(r'\b(?:FHD|HDF)\b',name,re.I) else 720 if re.search(r'\bHD\b',name,re.I) else 480 if re.search(r'\bSD\b',name,re.I) else channel.get('decoded_height',0)
    if not isinstance(height,int):height=0
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
            hd=[c for c in g['channels'] if is_hdr(c) or -priority(c)[1]>=720]
            for suffix,label,rows in [('above-fhd','>1080p verified · دقة مثبتة',verified),('hd-plus','HD & above · HD وأعلى',hd)]:
                if rows:derived.append({'id':g['id']+'-'+suffix,'name':g['name']+' · '+label,'derived_quality':suffix,'channels':rows})
        # Keep each companion beside its main category in the browse menu.
        paired=[]
        for g in groups:
            paired.append(g)
            paired.extend(d for d in derived if d['id'] in (g['id']+'-above-fhd',g['id']+'-hd-plus'))
        groups=paired
    return {**manifest,'groups':groups,'unique_channels':len({str(c['stream_id']) for g in groups for c in g['channels']}),
            'quality_basis':'browse order: HDR first, then provider-labelled resolution; decoded fallback for unlabelled channels; verified companions use measurements only'}
