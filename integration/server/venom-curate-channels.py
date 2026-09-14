#!/usr/bin/env python3
"""Build a bounded bilingual starter selection, retaining quality fallbacks.

Selection is editorial, not an invented audience-ranking statistic. Does not
probe streams, change channel records, or mark user favourites by itself.
"""
import json
import argparse
import sqlite3
import time
from pathlib import Path
import re
import unicodedata
import runpy
from collections import OrderedDict

RULES=[
 ('ar-news','أخبار عربية · Arabic news',30,r'\|AR\|',r'JAZEERA|JAZIRA|ARABIYA|ARABIA|HADATH|MAYADEEN|MAYADIN|ALGHAD|AL GHAD|ASHARQ|AL SHARQ|SKY.*NEWS|BBC.*AR|FRANCE.*24|DW.*AR|TRT.*AR|الجزيرة|العربية|الحدث|الميادين'),
 ('ar-general','عربي منوع · Arabic favourites',36,r'\|AR\|',r'\bMBC\b|ROYA|LBC|MTV|AL JADEED|JADEED|DUBAI|ABU.?DHABI|SAMA|SYRIA|AL MAMLAKA|ALMAMLAKA|NBN|DMC|\bCBC\b|\bON\b|رؤيا|الجديد|دبي|سوريا'),
 ('ar-movies','أفلام ومسلسلات عربية · Arabic movies & drama',36,r'\|AR\|',r'ROTANA.*(CINEMA|AFLAM|CLASSIC|DRAMA|COMEDY)|ART.*(AFLAM|CINEMA|HEKAYAT)|MBC.*(DRAMA|MASER|MASR)|DMC.*DRAMA|CBC.*DRAMA|روتانا|سينما|دراما'),
 ('ar-kids','أطفال عربي · Arabic kids',24,r'\|AR\|',r'SPACETOON|MAJED|MAJID|BARAEM|JEEM|TOYOR|KARAMEESH|CARTOON.*AR|MBC.*(3|TOON)|NICKELODEON|NICK JR|NICK TOONS|MARAH|HODHOD|سبيس|براعم|ماجد'),
 ('ar-sport','رياضة عربية · Arabic sports',42,r'\|SP\|',r'BEIN.*SPORT|BEIN.*([468]\s*K|GLOBAL)|KASS|THMANY|THMANYAH|ALTHMANY|SSC|ABU.?DHABI|DUBAI|SHARJAH|ثمانية|الكأس'),
 ('en-canada','كندا · Canada favourites',30,r'\|CA\|',r'CBC|CTV|GLOBAL|CITY|CP.?24|TVO|CHCH|APTN'),
 ('en-news','أخبار إنجليزي · English news',24,r'\|(UK|US|CA)\|',r'BBC.*NEWS|BBC.*WORLD|CNN|SKY NEWS|AL.?JAZEERA|BLOOMBERG|CTV.*NEWS|CBC.*NEWS|CP.?24|EURONEWS|NBC.*NEWS|CBS.*NEWS|ABC.*NEWS|FOX NEWS'),
 ('en-kids','أطفال إنجليزي · English kids',24,r'\|(UK|US|CA)\|',r'CBEEBIES|CBBC|DISNEY|CARTOON|NICK|TREEHOUSE|YTV|PBS.*KIDS|BOOMERANG'),
 ('en-movies','أفلام ومنوع إنجليزي · English movies & entertainment',30,r'\|(UK|US|CA)\|',r'HBO|AMC|FX\b|FILM.?4|SKY.*CINEMA|CRAVE|MOVIETIME|SHOWCASE|PARAMOUNT|COMEDY|DISCOVERY|NATIONAL GEO|NAT GEO'),
 ('en-sport','رياضة إنجليزي · English sports',36,r'\|(UK|US|CA)\|',r'\bTSN\b|SPORTSNET|SKY.*SPORT|TNT.*SPORT|BT.*SPORT|ESPN|EUROSPORT|NBC.*SPORT|FOX.*SPORT|GOLF CHANNEL')
]

def normalized(value):return unicodedata.normalize('NFKC',value).upper()

def high_quality_label(name):
    return bool(re.search(r'\b(?:[4-9]\s*K|UHD|1440P|2160P|2880P|4320P|HDR(?:10\+?)?|HLG|DOLBY[ ._-]*VISION|DV)\b',normalized(name)))

def quality_rank(channel):
    """Fresh decoded geometry wins; labels are only the unmeasured fallback."""
    height=channel.get('decoded_height')
    width=channel.get('decoded_width')
    if isinstance(height,int) and isinstance(width,int) and 16<=height<=16384 and 16<=width<=16384:
        return 0 if height>=4320 else 1 if height>=2160 else 2 if height>=1080 else 3 if height>=720 else 4
    name=normalized(channel['name'])
    for rank,pattern in enumerate((r'\b(?:8K|4320P)\b',r'\b(?:4K|UHD|2160P)\b',r'\b(?:FHD|HDF|1080[PI])\b',r'\b(?:HD|720P)\b')):
        if re.search(pattern,name):return rank
    return 4

def order_channels(channels):
    # Best alternative of each channel first; duplicate backups form lower rows.
    families=OrderedDict()
    for channel in channels:families.setdefault(family(channel['name']),[]).append(channel)
    for members in families.values():members.sort(key=quality_rank)
    ordered=[]
    for variant in range(max((len(m) for m in families.values()),default=0)):
        tier=[members[variant] for members in families.values() if variant<len(members)]
        ordered.extend(sorted(tier,key=quality_rank))
    return ordered

def family(name):
    name=normalized(name)
    name=re.sub(r'^\s*\d{3,6}\s+(?=(?:VIP\s+)?(?:CA|UK|US|AR|NW)\b)','',name)
    name=re.sub(r'^(?:(?:VIP|CA|UK|US|AR|NW)\b[\s:|.-]*)+','',name).strip()
    name=re.sub(r'^\s*(?:[A-Z]{2,4})\s*[:.|-]\s*','',name)
    name=re.sub(r'\b(?:[468]K|UHD|FHD|HDF|HD|SD|1080P|720P|VIP)\b',' ',name)
    return re.sub(r'[^\w]+',' ',name).strip()

def build(catalogue,category_limit=None):
    categories={str(c['category_id']):c['category_name'] for c in catalogue['categories']}
    selected=set();groups=[]
    # Specialized categories precede general matching, so kids/drama do not
    # disappear into the much broader MBC/Arabic general group.
    rules=sorted(enumerate(RULES),key=lambda pair:pair[1][0]=='ar-general')
    results={}
    for index,(key,label,limit,group_pattern,name_pattern) in rules:
        if category_limit is not None:limit=category_limit
        families=OrderedDict()
        candidates=catalogue['channels']
        if key.startswith('en-'):
            # Canada first for the household; UK and US remain represented.
            candidates=sorted(candidates,key=lambda c:0 if '|CA|' in categories.get(str(c['category_id']),'') else 1)
        if key=='ar-general':
            candidates=sorted(candidates,key=lambda c:0 if 'MBC' in categories.get(str(c['category_id']),'') else 1)
        for channel in candidates:
            name=normalized(channel['name']);group=categories.get(str(channel['category_id']),'')
            if str(channel['stream_id']) in selected or not re.search(group_pattern,group,re.I):continue
            mashhad=key=='ar-news' and bool(re.search(r'\b(?:AL\s*)?MASHHAD\b',name))
            if key=='ar-news' and not mashhad and not re.search(r'\|AR\|\s*(NEWS|JAZEERA)',group,re.I):continue
            if key=='ar-news' and re.search(r'ENGLISH|DOCUMENT|EN\b|FR\b',name):continue
            if key=='en-kids' and re.search(r'\(FR\)|FRANCE|LA CHAINE',name+' '+group,re.I):continue
            if key=='ar-sport' and re.search(r'\b(?:ENGLISH|EN|FR|FRANSA|USA)\b',name):continue
            if key=='ar-general' and not re.search(r'\|AR\|\s*(MBC|SYRIA|LEBANON|EGYPT|SAUDI|IRAQ|JORDAN|ROYA|PALESTINE|EMARAT|QATAR|KUWIT)',group,re.I):continue
            if key=='ar-general' and 'MBC' in group.upper() and not re.search(r'\bMBC[ .:]+(?:[1245]\b|IRAQ\b|ACTION\b|MAX\b|BOLLYWOOD\b|VARIETY\b)',name):continue
            match_name=re.sub(r'\bTSN(?=\d)','TSN ',name)
            if (not mashhad and not re.search(name_pattern,match_name,re.I)) or name.lstrip().startswith('#'):continue
            if re.search(r'\b(?:ADULT|XXX|PORN)\b',name+' '+group,re.I):continue
            families.setdefault(family(name),[]).append(channel)
        chosen=[]
        for members in families.values():members.sort(key=quality_rank)
        for variant in range(3):
            for members in families.values():
                if variant<len(members) and len(chosen)<limit:
                    channel=members[variant];chosen.append(channel);selected.add(str(channel['stream_id']))
        # Stage every matching high-quality alternative, even beyond the starter
        # cap or three-backup limit. Publication still requires decoded playback.
        if category_limit is not None:
            chosen_ids={str(c['stream_id']) for c in chosen}
            for members in families.values():
                for channel in members:
                    cid=str(channel['stream_id'])
                    if high_quality_label(channel['name']) and cid not in chosen_ids:
                        chosen.append(channel);chosen_ids.add(cid);selected.add(cid)
        results[index]={'id':key,'name':label,'channels':order_channels(chosen)}
    groups=[results[i] for i in range(len(RULES))]
    return {'version':1,'selection_basis':'editorial mainstream starter selection; not measured popularity','groups':groups,'unique_channels':len(selected)}

def approved_additions(existing,candidates,working_ids,geometry=None):
    """Retain existing identities; only add candidates with fresh decoder success."""
    groups=[];seen=set()
    for group in existing['groups']:
        rows=list(group['channels']);ids={str(c['stream_id']) for c in rows}
        candidate=next((g for g in candidates['groups'] if g['id']==group['id']),None)
        for channel in (candidate or {}).get('channels',[]):
            cid=str(channel['stream_id'])
            if cid in working_ids and cid not in ids:
                rows.append(channel);ids.add(cid)
        measured=[]
        for channel in rows:
            # Never retain a stale measurement copied from a previous manifest.
            clean={k:v for k,v in channel.items() if k not in ('decoded_width','decoded_height')}
            clean.update((geometry or {}).get(str(channel['stream_id']),{}))
            measured.append(clean)
        groups.append({**group,'channels':order_channels(measured)})
        seen.update(ids)
    return {**existing,'groups':groups,'unique_channels':len(seen),
            'addition_policy':'latest decoder result working within seven days; existing channels retained',
            'quality_basis':'fresh decoded resolution when available; provider label fallback; backups below primaries'}

def fresh_geometry(rows,now):
    geometry={}
    for cid,stamp,status,payload in rows:
        if status!='working' or not 0<=now-stamp<=7*86400:continue
        try:
            record=json.loads(payload)
            width,height=record.get('decoded_width'),record.get('decoded_height')
            if type(width) is int and type(height) is int and 16<=width<=16384 and 16<=height<=16384:
                geometry[str(cid)]={'decoded_width':width,'decoded_height':height}
                if type(record.get('decoded_hdr')) is bool:
                    geometry[str(cid)].update(decoded_hdr=record['decoded_hdr'],decoded_transfer=record.get('decoded_transfer'))
        except (TypeError,ValueError,AttributeError):continue
    return geometry

def repeatedly_unavailable(rows,now):
    """Two separated capacity-available failures; a newer success restores it."""
    histories={}
    for cid,stamp,status,payload in rows:
        if not 0<=now-stamp<=7*86400:continue
        histories.setdefault(str(cid),[]).append((stamp,status,payload))
    blocked={}
    for cid,history in histories.items():
        history.sort(reverse=True,key=lambda x:x[0])
        failures=[]
        for stamp,status,payload in history:
            if status=='working':break
            try:record=json.loads(payload)
            except (ValueError,TypeError):continue
            if status=='inconclusive_playback' and record.get('capacity_available') is True:
                failures.append(stamp)
        if len(failures)>=2 and max(failures)-min(failures)>=1800:
            blocked[cid]={'reason':'repeated_unavailable_not_permanent_failure','failures':len(failures),'latest_failure':max(failures)}
    return blocked

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--candidates',action='store_true',help='Stage expanded candidates without publishing or favouriting them')
    parser.add_argument('--approve-tested',action='store_true',help='Merge only fresh successful candidates into the existing selection')
    args=parser.parse_args()
    if args.candidates and args.approve_tested:parser.error('Choose one mode')
    root=Path('/data/config/iptv-venom')
    if args.approve_tested:
        with sqlite3.connect('file:'+str(root/'channel-health.sqlite3')+'?mode=ro',uri=True) as db:
            rows=db.execute('select channel_id,time,result,record from observations where id in (select max(id) from observations group by channel_id)').fetchall()
            history=db.execute('select channel_id,time,result,record from observations where time>=?',(time.time()-7*86400,)).fetchall()
        now=time.time()
        working={cid for cid,stamp,status,_ in rows if status=='working' and 0<=now-stamp<=7*86400}
        result=approved_additions(json.loads((root/'curated-channels.json').read_text()),json.loads((root/'curated-candidates.json').read_text()),working,fresh_geometry(rows,now))
    else:
        result=build(json.loads((root/'live-catalogue-redacted.json').read_text()),120 if args.candidates else None)
    if args.approve_tested or args.candidates:
        extend=runpy.run_path(str(root/'venom-special-groups.py'))['extend']
        result=extend(result,json.loads((root/'live-catalogue-redacted.json').read_text()),working if args.approve_tested else set(),fresh_geometry(rows,now) if args.approve_tested else {},args.candidates)
    if args.approve_tested:
        blocked=repeatedly_unavailable(history,now)
        removed={str(c['stream_id']):c['name'] for g in result['groups'] for c in g['channels'] if str(c['stream_id']) in blocked}
        result['groups']=[{**g,'channels':[c for c in g['channels'] if str(c['stream_id']) not in blocked]} for g in result['groups']]
        result['groups']=[g for g in result['groups'] if g['channels']]
        result['unique_channels']=len({str(c['stream_id']) for g in result['groups'] for c in g['channels']})
        report=root/'unavailable-channel-exclusions.json';tmp=report.with_suffix('.tmp')
        tmp.write_text(json.dumps({'updated':now,'excluded':blocked,'removed_this_pass':removed},ensure_ascii=False,indent=2));tmp.chmod(0o600);tmp.replace(report)
    if args.approve_tested:
        rank=runpy.run_path(str(root/'venom-measured-ranking.py'))['apply']
        result,ratings=rank(result,json.loads((root/'channel-quality-audit.json').read_text()))
        report=root/'channel-measured-ratings.json';tmp=report.with_suffix('.tmp')
        tmp.write_text(json.dumps({'updated':time.time(),'channels':ratings},ensure_ascii=False,indent=2));tmp.chmod(0o600);tmp.replace(report)
    target=root/('curated-candidates.json' if args.candidates else 'curated-channels.json');temporary=target.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2));temporary.chmod(0o600);temporary.replace(target)
    print(json.dumps({'unique_channels':result['unique_channels'],'groups':[{ 'name':g['name'],'count':len(g['channels']),'sample':[c['name'] for c in g['channels'][:5]]} for g in result['groups']]},ensure_ascii=False))

if __name__=='__main__':main()
