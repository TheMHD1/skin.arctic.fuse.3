"""Measured browse ranking and bounded sports sections; no audience claims."""
import re
import time
from collections import defaultdict

MAINSTREAM=r'BEIN|SKY|TNT|ESPN|TSN|SPORTSNET|SSC|TH[AM]*NY|MBC|BBC|CNN|JAZEERA|ARABIYA|HBO|SHOWTIME|CINEMAX|OSN|ROTANA|DISNEY|NICKELODEON|SPACETOON|JADEED|MTV|LBC|CBC|CTV|FOX|AL.?KASS'
NETWORKS=[('bein','beIN Sports',r'BEIN'),('sky','Sky Sports',r'SKY'),('tnt','TNT / BT Sports',r'\bTNT\b|\bBT\b'),('arabic','Arabic sports networks · شبكات عربية',r'SSC|TH[AM]*NY|KASS|AD SPORT|DUBAI|KSA|ONTIME|ON TIME|SHARJAH|RABIAA|RABIA|SHAHID|SHASHA|ALWAN|SOLO|STC'),('north-america','US & Canadian sports',r'ESPN|TSN|SPORTSNET|FOX|NBC|CBS|NBA|NFL|NHL|MLB|ROOT|MARQUEE'),('events','Event & extra feeds · أحداث إضافية',r'PPV|EVENT|DAZN|AMAZON|EXTRA'),('international','Other English / Arabic sports',r'.')]

def family(name):
    n=name.upper()
    n=re.sub(r'^(?:(?:VIP|UK|US|USA|CA|SP|AR|DS)\s*[:| ._-]*)+','',n)
    n=re.sub(r'\b(?:[4-9]\s*K|UHD|FHD|HDF|HD|SD|\d{3,4}[PI]|HDR10?|HLG)\b',' ',n)
    n=re.sub(r'\((?:BK|B|F)\)|· BACKUP.*|\s+#.*',' ',n)
    return re.sub(r'[^\w]+',' ',n).strip()

def measure(channel,record,now):
    valid=record.get('result')=='working' and 0<=now-record.get('time',0)<=7*86400
    frames=record.get('decoded_frame_variants',[]) if valid else []
    # Use the least resolution observed during a switching sample.
    height=min((f.get('height') or 0 for f in frames),default=0)
    depth=min((min(f.get('component_bit_depths') or [8]) for f in frames),default=0)
    pq=bool(frames) and all(f.get('color_transfer') in ('smpte2084','arib-std-b67') for f in frames)
    wide=bool(frames) and all(f.get('color_primaries')=='bt2020' for f in frames)
    colour=3 if pq and depth>=10 and wide else 2 if wide and depth>=10 else 1 if depth>=10 else 0
    fps=min((s.get('observed_frame_rate') or 0 for s in record.get('video_sample_statistics',[])),default=0) if valid else 0
    interlaced=any(f.get('interlaced_frame') for f in frames)
    name=channel['name'];popular=bool(re.search(MAINSTREAM,name,re.I))
    # Resolution first; colour precision and motion distinguish measured peers.
    # Unknown metadata earns no HDR bonus. Provider resolution labels earn none.
    tier=5 if height>=4320 else 4 if height>=2160 else 3 if height>=1440 else 2 if height>=1080 else 1 if height>=720 else 0
    key=(0 if frames else 1,-tier,-colour,-(1 if fps>=45 and not interlaced else 0),-int(popular),-height,family(name),str(channel['stream_id']))
    return key,{'height':height or None,'bit_depth':depth or None,'hdr':'supported_10bit_signal' if colour==3 else 'signalled_8bit_unverified' if pq else 'not_confirmed','colour_tier':colour,'fps':fps or None,'editorial_mainstream':popular,'basis':'measured resolution, colour, motion; editorial recognition; not audience statistics'}

def apply(manifest,audit,now=None):
    now=time.time() if now is None else now
    records=audit.get('channels',{});ratings={};keys={}
    groups=[{**g,'channels':list(g['channels'])} for g in manifest['groups'] if not g.get('measured_sports_section')]
    # Some old display names retain foreign-region markers even when the
    # gateway's current source name has been cleaned. Reject explicit markers.
    foreign=r'^(?:VIP\s+)?(?:IT|PT|SR|FR|ES|DE|NL|TR)\s*[:|]|\bFRANSA\b|ESPA[NÑ]OL|\bLATIN\b'
    for g in groups:g['channels']=[c for c in g['channels'] if not re.search(foreign,c['name'],re.I)]
    for g in groups:
        for c in g['channels']:
            cid=str(c['stream_id']);keys[cid],ratings[cid]=measure(c,records.get(cid,{}),now)
        g['channels'].sort(key=lambda c:keys[str(c['stream_id'])])
    sports=next((g for g in groups if g['id']=='ar-sport'),None)
    if sports:
        retained={str(c['stream_id']):c for g in manifest['groups'] if g.get('measured_sports_section') for c in g['channels'] if not re.search(foreign,c['name'],re.I)}
        retained.update({str(c['stream_id']):c for c in sports['channels']})
        for cid,c in retained.items():keys[cid],ratings[cid]=measure(c,records.get(cid,{}),now)
        pool=sorted(retained.values(),key=lambda c:keys[str(c['stream_id'])]);buckets=defaultdict(list);non_sports=[]
        for c in pool:
            n=c['name'].upper()
            if re.search(r'MOVIES|\bKIDS\b|\bDRAMA\b|\bSERIES\b',n):
                non_sports.append(c);continue
            for key,label,pattern in NETWORKS:
                if re.search(pattern,n):buckets[key].append(c);break
        bad={str(c['stream_id']) for c in non_sports}
        patterns=[('sport-rugby','Rugby · الرغبي',r'RUGBY'),('sport-tennis','Tennis · التنس',r'TENNIS'),('sport-golf','Golf · الغولف',r'GOLF'),('sport-motorsport','Motorsport / F1 · سباقات السيارات',r'\bF1\b|FORMULA|MOTOGP|NASCAR|MOTORSPORT'),('sport-cricket','Cricket · الكريكيت',r'CRICKET|WILLOW'),('sport-darts','Darts & snooker · دارتس وسنوكر',r'DARTS|SNOOKER'),('sport-cycling','Cycling · الدراجات',r'CYCLING|VELO'),('sport-football-en','Football / Soccer · English',r'\bSS\s+(?:PL|LA LIGA)|SKY\s*SPORTS?\s+PREMIER')]
        for gid,label,pattern in patterns:
            matched=[c for c in pool if str(c['stream_id']) not in bad and re.search(pattern,c['name'],re.I)]
            if not matched:continue
            target=next((g for g in groups if g['id']==gid),None)
            if target is None:target={'id':gid,'name':label,'channels':[]};groups.append(target)
            combined={str(c['stream_id']):c for c in target['channels']+matched}
            target['channels']=sorted(combined.values(),key=lambda c:keys[str(c['stream_id'])])
        for gid,label,pattern in [('sport-baseball','Baseball · البيسبول',r'DODGERS|YANKEES|\bMETS\b|RED SOX|MLB'),('sport-basketball','Basketball · كرة السلة',r'LAKERS|CELTICS|\bNBA\b|WNBA'),('sport-football-en','Football / Soccer · English',r'\bSS\s+LA\s*LIGA')]:
            target=next((g for g in groups if g['id']==gid),None)
            matched=[c for c in pool if re.search(pattern,c['name'],re.I)]
            if matched:
                if target is None:target={'id':gid,'name':label,'channels':[]};groups.append(target)
                combined={str(c['stream_id']):c for c in target['channels']+matched}
                target['channels']=sorted(combined.values(),key=lambda c:keys[str(c['stream_id'])])
        for g in groups:
            if g['id'].startswith('sport-'):g['channels']=[c for c in g['channels'] if str(c['stream_id']) not in bad]
        # Keep previously approved non-sports feeds accessible without assuming
        # their language from an ambiguous mixed-provider category.
        extras=[]
        if non_sports:extras.append({'id':'mixed-provider-entertainment','name':'Provider entertainment · منوعات','channels':non_sports,'measured_sports_section':True})
        seen=set();picks=[]
        for c in pool:
            if str(c['stream_id']) in bad or re.search(r'PPV|EVENT',c['name'],re.I):continue
            f=family(c['name'])
            if f not in seen:seen.add(f);picks.append(c)
            if len(picks)>=48:break
        sports.update(name='Sports picks · مختارات رياضية',channels=picks)
        for key,label,pattern in NETWORKS:
            rows=buckets[key]
            for start in range(0,len(rows),100):
                page=start//100+1
                extras.append({'id':'sports-network-'+key+'-'+str(page),'name':label+(' · '+str(page) if len(rows)>100 else ''),'channels':rows[start:start+100],'measured_sports_section':True})
        pos=next(i for i,g in enumerate(groups) if g['id']=='ar-sport')
        groups[pos+1:pos+1]=extras
    groups=[g for g in groups if g['channels']]
    return {**manifest,'groups':groups,'unique_channels':len({str(c['stream_id']) for g in groups for c in g['channels']}),'quality_basis':'measured quality first; editorial recognition within quality peers; provider claims do not determine rank'},ratings
