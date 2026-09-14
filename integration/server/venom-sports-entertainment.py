"""Full catalogue classification for bilingual sports and English entertainment."""
import re
import unicodedata

SPORTS=[
 ('sport-ufc','UFC & MMA · الفنون القتالية',r'\bUFC\b|\bMMA\b|FIGHT PASS|FIGTH PASS|\bPFL\b|BELLATOR|ONE CHAMPIONSHIP'),
 ('sport-boxing','Boxing & kickboxing · الملاكمة',r'BOXING|KICKBOX|FIGHT\s*BOX|FIGHT NETWORK|ملاكمة'),
 ('sport-wrestling','Wrestling · المصارعة',r'\bWWE\b|\bAEW\b|WRESTL|مصارعة'),
 ('sport-rugby','Rugby · الرغبي',r'RUGBY|رغبي'),
 ('sport-gridiron','American & Canadian football · NFL / CFL',r'\bNFL\b|\bCFL\b|RED\s*ZONE|GRIDIRON|\bTSN\s*[1-5]?\b'),
 ('sport-cricket','Cricket · الكريكيت',r'CRICKET|WILLOW|كريكيت'),
 ('sport-baseball','Baseball · البيسبول',r'\bMLB\b|BASEBALL|STRIKE\s*ZONE'),
 ('sport-basketball','Basketball · كرة السلة',r'\bNBA\b|\bWNBA\b|BASKETBALL|السلة'),
 ('sport-hockey','Ice hockey · هوكي الجليد',r'\bNHL\b|HOCKEY|هوكي'),
 ('sport-golf','Golf · الغولف',r'GOLF|غولف|جولف'),
 ('sport-tennis','Tennis · التنس',r'TENNIS|التنس'),
 ('sport-motorsport','Motorsport / F1 · سباقات السيارات',r'\bF1\b|FORMULA|MOTORSPORT|MOTOR SPORT|MOTOR TREND|MOTORTREND|MOTOGP|NASCAR|FOX SPORTS RACING'),
 ('sport-racing','Horse racing · سباق الخيل',r'RACING|HORSE|\bYAS\b|الخيل'),
 ('sport-football-ar','Football · كرة القدم بالعربية',None),
 ('sport-football-en','Football / Soccer · English',None),
]
FOREIGN=r'(?:^|[\s|\[\]:])(?:PT|IT|DE|FR|ES|NL|PL|DK|SE|NO|TR|SR|EXYU|EX-YU|CRO|BG|RUS)(?:[\s|\]\]:]|$)|LATINO|LATIN\b|DEPORTES|ESPA[NÑ]OL|FRAN[CÇ]AIS'
SPORT_NAME=r'SPORT|\bTSN\b|SPORTSNET|\bESPN\b|EUROSPORT|\bBEIN\b|\bUFC\b|\bWWE\b|FIGHT|BOXING|CRICKET|GOLF|TENNIS|\bNBA\b|\bNFL\b|\bNHL\b|\bMLB\b|RUGBY|RACING|\bF1\b|WILLOW|MOTOR|PPV EVENT|FORMULA'
AR_SPORT_CATEGORY=r'BEIN SPORTS|ARABIC SPORTS|SOLO SPORTS|THMANY|ALTHMANY|SHASHA SPORT|SHAHID SPORT|ALWAN SPORTS|STC SPORTS|SPORT KASS|STARZPLAY|ALRABIAA|AL FAJER'
ENTERTAINMENT=r'\bHBO\b|CINEMAX|(?:ACTION|OUTER|THRILLER|MORE|5 STAR)\s*MAX|SHOWTIME|\bSTARZ\b|\bEPIX\b|\bMGM\b|MOVIE|CINEMA|FILM\s*4|\bFX\b|\bFXX\b|\bFXM\b|\bAMC\b|HALLMARK|LIFETIME|CRAVE|SHOWCASE|PARAMOUNT|COMEDY|SYFY|SCI.?FI|SUNDANCE|\bIFC\b|FREEFORM|\bTBS\b|\bTNT\b|USA NETWORK|TV LAND|SKY (?:ONE|1|ATLANTIC|WITNESS|COMEDY|MAX)|\bBRAVO\b|\bA&E\b|\bTLC\b|\bHGTV\b|E!|STAR WORLD|SONY|MOVIEPLEX|RETROPLEX|\bFOX\b'

def norm(s):return unicodedata.normalize('NFKC',s).upper()

def language(name,category):
    n=norm(name);cat=norm(category)
    if re.search(FOREIGN,n.replace('*',' ')):return None
    if re.search(r'\bENGLISH\b|\bEN\b|\[UK\]|\|UK\||\bUSA[: ]|\bUS[: ]',n):return 'en'
    if re.search(r'\|(UK|US|CA)\|',cat) and not re.search(r'FRANCE|ASIA',cat):return 'en'
    if re.search(r'\|AR\|',cat):return 'ar'
    if re.search(AR_SPORT_CATEGORY,cat):return 'ar'
    if 'DSTV' in cat and re.search(r'SUPERSPORT|ESPN|WWE',n):return 'en'
    if '|AF|' in cat and re.search(r'^DS:\s*(?:SS\b|SUPERSPORT\b|ESPN)',n) and 'MAXIMO' not in n:return 'en'
    # The international sports bin has mixed languages. Only explicit known
    # English network variants or language markers are admitted from it.
    if 'INTERNATIONAL SPORTS' in cat and re.search(r'\bNBA\b|\bNFL\b|\bESPN\b|PREMIER SPORTS|EIR SPORT|MOTORSPORT',n):return 'en'
    return None

def classify(channel,category):
    n=norm(channel['name']);cat=norm(category)
    if not n.strip() or n.lstrip().startswith(('#','•','★')) or re.search(r'\bXXX\b|\bADULT\b|\bPORN\b',n+' '+cat):return []
    lang=language(n,cat);result=[]
    if lang:
        sport=bool(re.search(SPORT_NAME,n) or re.search(AR_SPORT_CATEGORY,cat) or re.search(r'FOOTBALL|SOCCER|\bMUTV\b|\bLFCTV\b|CELTIC|RANGERS|LIVERPOOL|ARSENAL|CHELSEA',n) or ('FOX SPORT & FOX' not in cat and re.search(r'SPORT|PPV EVENTS|NATIONAL LEAGUE|USA TENNIS|NBA NFL NHL MLB',cat)))
        if sport:
            result.append('ar-sport')
            for key,label,pattern in SPORTS:
                if pattern and re.search(pattern,n):
                    if key=='sport-racing' and re.search(r'MOTOR|FOX SPORTS RACING',n):continue
                    result.append(key)
            football=re.search(r'FOOTBALL|SOCCER|PREMIER LEAGUE|PREMIER SPORTS|\bEPL\b|\bMLS\b|LALIGA|LA LIGA|CHAMPIONS LEAGUE|LIVERPOOL|MANCHESTER|CHELSEA|ARSENAL|\bMUTV\b|\bLFCTV\b|CELTIC|RANGERS',n)
            arabic_carrier=lang=='ar' and re.search(r'BEIN.*SPORT|KASS|THMANY|ALTHMANY|SSC|ON TIME|AD SPORT|DUBAI SPORT|SHASHA',n) and not re.search(r'NBA|NFL|BASKET|TENNIS|RACING',n)
            if (football or arabic_carrier) and not re.search(r'\bNFL\b|\bCFL\b|AMERICAN FOOTBALL',n):result.append('sport-football-'+lang)
        entertainment_category=bool(re.search(r'MOVIES TV|USA CINEMA|ENTERTAINMENT|ENTERTIMENT',cat))
        if lang=='en' and (entertainment_category or re.search(ENTERTAINMENT,n)) and not sport and not re.search(r'NEWS|WEATHER|QVC|\bHSN\b',n):result.append('en-movies')
        if lang=='ar' and re.search(r'OSN|BEIN MEDIA',cat) and re.search(r'MOVIES|HOLLYWOOD|PREMIERE|STAR WORLD|SHOWCASE|BOX OFFICE|SERIES',n) and not re.search(r'ARABI|YAHALA|AFLAM',n):result.append('en-movies')
    # Explicitly requested FOX Movies feeds exist only in regional provider
    # bins; retain region labels and do not claim measured English audio.
    if re.search(r'\bFOX MOVIES\b',n):result.append('en-movies')
    return list(dict.fromkeys(result))

def extend(manifest,catalogue,working,geometry,candidates=False):
    labels=dict((key,label) for key,label,_ in SPORTS)
    labels.update({'ar-sport':'All sports · عربي / English','en-movies':'Movies & entertainment · English'})
    groups={g['id']:{**g,'channels':list(g['channels'])} for g in manifest['groups'] if not g.get('derived_quality')}
    old_english=groups.pop('en-sport',None)
    if old_english:
        target=groups.setdefault('ar-sport',{'id':'ar-sport','name':labels['ar-sport'],'channels':[]})
        ids={str(c['stream_id']) for c in target['channels']}
        target['channels'].extend(c for c in old_english['channels'] if str(c['stream_id']) not in ids)
    existing={str(c['stream_id']) for g in groups.values() for c in g['channels']}
    categories={str(c['category_id']):c['category_name'] for c in catalogue['categories']}
    for c in catalogue['channels']:
        cid=str(c['stream_id'])
        if not candidates and cid not in working and cid not in existing:continue
        for key in classify(c,categories.get(str(c['category_id']),'')):
            target=groups.setdefault(key,{'id':key,'name':labels[key],'channels':[]})
            if not any(str(x['stream_id'])==cid for x in target['channels']):target['channels'].append({**c,**geometry.get(cid,{})})
    for key,label in labels.items():
        if key in groups:groups[key]['name']=label
    ordered=[]
    for key,g in groups.items():
        if key.startswith('sport-'):continue
        ordered.append(g)
        if key=='ar-sport':ordered.extend(groups[k] for k,_,_ in SPORTS if k in groups and groups[k]['channels'])
    return {**manifest,'groups':ordered,'unique_channels':len({str(c['stream_id']) for g in ordered for c in g['channels']})}
