"""Build the offline worksheet from reviewed exact station names and aliases."""
import json,re,runpy
from pathlib import Path
root=Path(__file__).parent
clean=runpy.run_path(str(root/'venom-channel-names.py'))['clean_name']
key=runpy.run_path(str(root/'venom-reviewed-artwork.py'))['key']
channels=json.loads(Path('/tmp/iptv-channels.json').read_text())
logos=json.loads(Path('/tmp/iptv-logos.json').read_text())
available={l['channel']:l for l in logos if l['in_use'] and l['format'] in ('PNG','JPEG')}
def norm(s):return re.sub(r'[^A-Z0-9+]','',s.upper())
aliases={
'AR:ASHARQ':'AsharqNews.sa','AR:ALARABIA':'Alarabiya.ae','AR:ALARABIYA ALHADATH':'AlHadath.sa','AR:ALGHAD':'AlGhadTV.eg','AR:DW ARABIC':'DW.de','AR:FRANCE 24 ENG':'France24.fr','AR:FRANCE 24 AR':'France24.fr','AR:SKY NEWS':'SkyNewsArabia.ae',
'AR:ABU DHABI':'AbuDhabiTV.ae','AR:DUBAI SAMA':'SamaDubai.ae','AR:MTV':'MTVLebanon.lb','AR:JADEED':'AlJadeed.lb','AR:ON E TV':'OnE.eg','AR:ROYA':'RoyaTV.jo','AR:ROYA TV PLUS':'RoyaTV.jo','AR:CBC':'CBC.eg','AR:CBC EXTRA NEWS':'ExtraNews.eg','AR:ART HEKAYAT 1':'ARTHekayat.sa','AR:MAJED':'Majid.ae','AR:BEIN BARAEM KIDS':'Baraem.qa','AR:JEEM':'JeemTV.qa','AR:HODHOD TV':'HodHodArabicTV.ir','AR:SPACETOON':'SpacetoonArabic.ae','AR:TOYOR ALJANAH':'ToyorAlJannah.jo',
'EN:SKY NEWS':'SkyNews.uk','EN:AL JAZEERA':'AlJazeeraEnglish.qa','EN:AL JAZEERA ENGLISH':'AlJazeeraEnglish.qa','EN:ALJAZEERA NEWS':'AlJazeeraEnglish.qa','EN:BBC WORLD NEWS':'BBCNews.uk','EN:BBC ONE NEWS':'BBCNews.uk','EN:FOX NEWS':'FoxNewsChannel.us','EN:ABC NEWS':'ABCNewsLive.us','EN:CBS NEWS':'CBSNews247.us','EN:CBSN NEWS':'CBSNews247.us','EN:CBBC BBC 4':'CBBC.uk','EN:BBC 3 CBBC':'CBBC.uk','EN:BBC CBBC':'CBBC.uk','EN:BBC 4 CBEEBIES':'CBeebies.uk','EN:NICK':'Nickelodeon.uk','EN:NICK (KIDS)':'Nickelodeon.us','EN:SKY NICK':'Nickelodeon.uk','EN:SKY NICK JR':'NickJr.uk','EN:SKY NICKTOONS':'Nicktoons.uk','EN:SKY CINEMA PREMIER':'SkyCinemaPremiere.uk','EN:SKY CINEMA SELECT/OSCARS':'SkyCinemaSelect.uk','EN:AMC PLUS':'AMCPlus.us','EN:INVESTIGATION DISCOVERY ID':'InvestigationDiscovery.us','EN:DISCOVERY':'DiscoveryChannel.uk','EN:PARAMOUNT':'ParamountNetwork.uk','EN:HBO EAST':'HBO.us','EN:HBO PACIFIC':'HBO.us','EN:HBO 2 EAST':'HBO2.us','EN:HBO 2 WEST':'HBO2.us','EN:HBO LATIN':'HBOLatino.us','EN:SKYSPORT PL':'SkySportsPremierLeague.uk','EN:SKYSPORT MAIN EVENTS':'SkySportsMainEvent.uk','EN:EUROSPORTS':'Eurosport1.fr','EN:ESPN CLASSIC':'ESPNClassic.ca',
'CA:CP 24 TV':'CP24.ca','CA:CP24 TV':'CP24.ca','CA:CTV NEWS':'CTVNewsChannel.ca','CA:CTV SCI-FI':'CTVSciFiChannel.ca','CA:CTV LIFE':'CTVLifeChannel.ca'}
aliases.update({'AR:BBC ARABIC':'BBCArabic.uk','AR:TRT ARABI':'TRTArabi.tr','AR:DUBAI RACING 1':'DubaiRacing.ae','AR:ON TIME SPORT 1':'OnTimeSports.eg','AR:ON TIME SPORT 2':'OnTimeSports2.eg','AR:OSN NICKELODEON':'NickelodeonArabia.ae','AR:NICKELODEON':'NickelodeonArabia.ae','AR:OSN NICK JR':'NickJrArabia.ae','AR:CARTOON NETWORK AR':'CartoonNetworkArabic.ae','AR:MBC MASER DRAMA':'MBCMasrDrama.sa','AR:SYRIA TV':'SyriaTV.sy','EN:CBC NEWS':'CBCNewsNetwork.ca','EN:BLOOMBERG':'BloombergTV.us','EN:BLOOMBERG NEWS':'BloombergTV.us','EN:EURONEWS':'EuronewsEnglish.fr','EN:ALJAZEERA BALKANS':'AlJazeeraBalkans.ba','EN:EUROSPORT 1':'Eurosport1.fr','EN:EUROSPORT 2':'Eurosport2.fr','EN:NAT GEO':'NationalGeographic.uk','EN:NAT GEO WILD':'NationalGeographicWild.uk','EN:GOLF CHANNEL':'GolfChannel.us','EN:FX':'FX.us','EN:DISCOVERY VELOCITY':'DiscoveryVelocity.ca','EN:PLUTO TV COMEDY':'PlutoTVComedy.us','CA:CTV TORONTO':'CTV.ca'})
for city in ['',' CALGARY',' CHARLOTTE',' EDMONTON',' MONTREAL',' OTTAWA',' REGINA',' TORONTO',' VANCOUVER',' WINDSOR',' WINNIPEG']:aliases['CA:CBC'+city]='CBCTelevision.ca'
for city in [' TORONTO',' CALGARY',' EDMONTON',' HALIFAX',' VANCOUVER']:aliases['CA:GLOBAL'+city]='Global.ca'
for city in [' CALGARY',' EDMONTON',' KINGSTON',' MONTREAL',' PETERBOROUGH',' REGINA',' SASKATOON',' TORONTO',' VANCOUVER',' WINNIPEG']:aliases['CA:GLOBAL NEWS'+city]='GlobalNews.ca'
for region in ['EAST','ONTARIO','PACIFIC','WEST']:aliases['EN:SPORTSNET '+region]='Sportsnet.ca'
for i in range(1,4):aliases['AR:DUBAI SPORT '+str(i)]='DubaiSports'+str(i)+'.ae'
for i in range(1,8):
    cid='Alkass'+['','One','Two','Three','Four','Five','Six','Seven'][i]+'.qa'
    for label in ['AL KASS '+str(i),'ALKASS '+str(i),'KASS '+str(i),'BEIN ALKASS '+str(i),'AL KASS SPORTS'+str(i),'AL KASS SPORTS '+str(i),'AL KASS SPORTS'+str(i)+' LIVE EVENTS']:aliases['AR:'+label]=cid
for i in range(1,4):aliases['AR:THMANYAH '+str(i)]='Thmanyah'+str(i)+'.sa'
manifest=json.loads(Path('/tmp/curated-now.json').read_text());result=json.loads((root/'venom-reviewed-artwork.json').read_text());pending=[]
for group in manifest['groups']:
    scope='AR' if group['id'].startswith('ar-') else 'CA' if group['id']=='en-canada' else 'EN'
    for row in group['channels']:
        label=key(clean(row['name']));entry=scope+':'+label
        if entry in result:continue
        cid=aliases.get(entry)
        if not cid and label in result:continue
        if not cid:
            raw=row['name'].upper()
            countries=['CA'] if re.match(r'^(CA|CAN)\b',raw) or scope=='CA' else ['US'] if re.match(r'^USA?\b',raw) else ['IT'] if raw.startswith('IT:') else ['UK'] if scope=='EN' else ['AE','SA','QA','EG','JO','SY','LB','IQ']
            matches=[c for c in channels if c['country'] in countries and c['id'] in available and norm(c['name'])==norm(label) and len(norm(label))>2 and not re.search('[\u0600-\u06ff]',label)]
            if len(matches)==1:cid=matches[0]['id']
        if cid in available:result[entry]={'channel':cid,'url':available[cid]['url']}
        else:pending.append(entry)
print(json.dumps({'mapping':result,'pending':sorted(set(pending))},ensure_ascii=False))
