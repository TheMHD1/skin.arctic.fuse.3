"""Install the reviewed update over an exact existing Kodi source cohort.

This is not a blank-device bootstrap. A private profile supplies device identity
and native mappings; credentials, settings, databases and markers stay on-box.
"""
import argparse
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import transaction

VERSIONS={'plugin.video.habibi.resume':'1.1.0','plugin.video.jellyfin':'2.2.0+py3',
          'skin.arctic.fuse.3':'3.3.1','plugin.video.venom.tv':'1.3.1'}
VENOM_BASE={'browser.py':'9960d5abf16547daa59166dd51bd089aa025d4f46b344ec2d28d7dd0a2f27a29',
 'default.py':'a607f48feff50aca83e6897a3507a0ee6f665ee805d3b31f9e684a2402ad29ae',
 'shared_favorites.py':'8f73ab90c7a554807878567efcadc2e0f9a5eecfd2156ce227cbd4f4b2dec7af'}
VENOM_R3={'browser.py':'13561ec9556ad254c0479dd6ee67b2fa5e300b41a89eadf8b4ded14212396b81',
 'default.py':'edbf99577e7238caad07529b8ed62665f2a5b189190b894c691941ac10c1b027',
 'shared_favorites.py':'718988d6c64a7fddc8255f25e3f5a882ffab4aa0d8744d84ff07d3ae9866cd39'}
VENOM_R5={'browser.py':'e185f815009b868541e42ef0b4c057db678f705e78a8b7d5f30f55b3b214e4ff',
 'default.py':'edbf99577e7238caad07529b8ed62665f2a5b189190b894c691941ac10c1b027',
 'shared_favorites.py':'ab270c3806c4916b2a793b65570d650e8df06dac692e490215351e0f68e34df4'}
VENOM_OUT={'browser.py':'f8d1c57b08a03e3df73036c91e760214e4127ee6a697c6e83ee6f15af558b281',
 'default.py':'edbf99577e7238caad07529b8ed62665f2a5b189190b894c691941ac10c1b027',
 'shared_favorites.py':'ab270c3806c4916b2a793b65570d650e8df06dac692e490215351e0f68e34df4'}
REMOTE_BASE={'browser.py':'e85915452b7843d76db40a299cc44960c5bda7c7dd71cbddaa8eb2a4b492b532',
 'default.py':'458d6e9f6b7179213602dfb596728e411b79b4c824fd9fcdace49ee6cf53f565',
 'shared_favorites.py':VENOM_BASE['shared_favorites.py'],
 'remote_catalogue.py':'88d691ff20ffb1df9de3cbc2d3a46df26a76a55b0ea578630bcee3c4f31b6837'}
REMOTE_R3={'browser.py':'325652df90ce2ab4b7902b14c4d5525a86cf1fd81112c9827809b89c96c4b536',
 'default.py':'1501d9dd341a25e33f07e476da1c5d822d488d277e1e71786b07071997327777',
 'shared_favorites.py':VENOM_R3['shared_favorites.py'],'remote_catalogue.py':'43060f46af6ab85133c13efdc2ccc183674cac32f9a1254beb82d2c10cb3527f'}
REMOTE_R5={'browser.py':'78e04e90889c49075072a6d8cc1ad9ee2f1fce8532867ca98e750cc61c0fc3fc',
 'default.py':REMOTE_R3['default.py'],'shared_favorites.py':VENOM_R5['shared_favorites.py'],'remote_catalogue.py':REMOTE_R3['remote_catalogue.py']}
REMOTE_OUT={'browser.py':'f9cb951e99f567d5c5983e563bc9cf4b1a7f12160a43187d37bc962f3e0e8467',
 'default.py':REMOTE_R3['default.py'],'shared_favorites.py':VENOM_OUT['shared_favorites.py'],'remote_catalogue.py':REMOTE_R3['remote_catalogue.py']}
REMOTE_MARKER='4d3f886ca60726528b56a11e2271605a146d04d29c7fa63add90891011bc240b'
NATIVE_BASE={'api.py':'e625164ea9e3e86751d644b90c3ff1b6ff455558d7b8268ca03c42a83fceabc2',
             'playutils.py':'6c44e9df8e28888968455564b6496003bd3a32d2efd65bf1dd6b19c104ec817b','native_originals.py':None}
NATIVE_OUT={'api.py':'60397069f460c2ba79a183ed8904c31ce811097ae8e4cd9cdabdc64b976be4d4',
            'playutils.py':'1a786411ee85f9fe68cf994563ce83c02f9911aa86696f54b68a264462f186c9',
            'native_originals.py':'656df894c18d6d005c7d81a5ec04b3a9957a744f36ead16c6c05358309252171'}
PAYLOAD_HASHES={'search.py':'74a5b1dcb21b36ca3004179b81cf3d2f4e7894025bba85fe8a941c68d8033ee8',
 **{'venom/'+k:v for k,v in VENOM_OUT.items()},
 'jellyfin/api.py':NATIVE_OUT['api.py'],'jellyfin/playutils.py':NATIVE_OUT['playutils.py'],
 'native_originals.py':NATIVE_OUT['native_originals.py'],
 **{'remote-venom/'+k:v for k,v in REMOTE_OUT.items() if k!='shared_favorites.py'}}
TOUCHED={
 'addons/plugin.video.habibi.resume/client.py':{'53df471451ea50451cae5371a4a97239e5ea1286ff4fc8b765ab9a2330f28f0f','72f944e2b93f1bc51b449830124ddf551d9222aa002e41edc6b18ce6d2594c5b'},
 'addons/plugin.video.habibi.resume/default.py':{'f6e0ed8daac2024bf189b7d2918b39019728371cf61ab77f70391bc124566bec','4a281b6036b25e927d34e1d2f500fc6bfcd092d7eeb87a77dc6d1fc355d5c810'},
 'addons/skin.arctic.fuse.3/shortcuts/generator/data/setup/search_path.xml':{'fee6f922930de8115cac3339629a35b2d022e87dc286706eaf81a353ac984ef2','5edb7d411bd5bbbcd5d045b694355879fb023a0019c7f6baf1850ef4b056b9e5'},
 'addons/plugin.video.jellyfin/jellyfin_kodi/jellyfin/http.py':{'d3fde303945807303a4399a98ec3cf3fe40481c599152e1d2d31a0b407fa0aad','cc8223016710bbeaae86034428f8b35d0d7fa376a11886f017ed297530bd6005'},
}
TOUCHED_OUTPUT={
 'addons/plugin.video.habibi.resume/client.py':'72f944e2b93f1bc51b449830124ddf551d9222aa002e41edc6b18ce6d2594c5b',
 'addons/plugin.video.habibi.resume/default.py':'4a281b6036b25e927d34e1d2f500fc6bfcd092d7eeb87a77dc6d1fc355d5c810',
 'addons/skin.arctic.fuse.3/shortcuts/generator/data/setup/search_path.xml':'5edb7d411bd5bbbcd5d045b694355879fb023a0019c7f6baf1850ef4b056b9e5',
 'addons/plugin.video.jellyfin/jellyfin_kodi/jellyfin/http.py':'cc8223016710bbeaae86034428f8b35d0d7fa376a11886f017ed297530bd6005',
}
# One recorded remote baseline predates ownership of this generated search-path
# source in its integrity manifest.  It may cross this bridge only when the
# manifest is the separately verified remote base and these exact bytes are
# still present; the R6 transaction records the replacement immediately.
REMOTE_UNTRACKED_BASE={
 'addons/skin.arctic.fuse.3/shortcuts/generator/data/setup/search_path.xml':'fee6f922930de8115cac3339629a35b2d022e87dc286706eaf81a353ac984ef2',
 'addons/plugin.video.jellyfin/jellyfin_kodi/jellyfin/http.py':'d3fde303945807303a4399a98ec3cf3fe40481c599152e1d2d31a0b407fa0aad',
}
REMOTE_UNTRACKED_MANIFEST='258f4ce9efbe374a650a76e24aeda979c5f17a18e29654caf23a73616695c47c'
REMOTE_R6_OUTPUT={
 'addons/plugin.video.habibi.resume/client.py':'1aaf8ec5a327f6f09c10a842de36c9eabfd2d4378b54d83fe1598b481aad31cd',
 'addons/skin.arctic.fuse.3/shortcuts/generator/data/setup/search_path.xml':'d819c566ae13c982f201f2d702fc9c755672c42778e220a227be750bd173ef48',
}
SEARCH_SKIN='addons/skin.arctic.fuse.3/1080i/Includes_Search.xml'
SEARCH_BASE={'27bf4f29b0f333c867f06dd2e0ec17999a836cff7fc948a25cb97edc1333304d',
             '270a52601721c96489a244727206634443d2b07f77001e0a7cea8bae95ea2f92'}
DISCOVER=b'''                        <item>\n                            <label>$LOCALIZE[31066]$INFO[Window(Home).Property(TMDbHelper.UserDiscover.FolderPath.Name), ,]</label>\n                            <icon>special://skin/extras/icons/binoculars.png</icon>\n                            <property name="mode">discover</property>\n                            <onclick>RunPlugin(plugin://plugin.video.themoviedb.helper/?info=user_discover$INFO[Window(Home).Property(TMDbHelper.UserDiscover.Folderpath.ParamString),&amp;,])</onclick>\n                            <visible>String.IsEqual(Skin.String(HomeSwitcher.Search.Mode),Combined) + !Skin.HasSetting(Search.DisableDiscover)</visible>\n                        </item>\n'''
SEARCH=b'''                        <item>\n                            <label>$LOCALIZE[137]$VAR[Search_Label_Results]</label>\n                            <icon>special://skin/extras/icons/chart-simple.png</icon>\n                            <property name="mode">search</property>\n                            <onclick>SetFocus(3000)</onclick>\n                            <onclick>Action(Select)</onclick>\n                            <onclick>SetFocus(3003)</onclick>\n                        </item>\n'''

def sha(data):return hashlib.sha256(data).hexdigest()
def require(value,message):transaction.require(value,message)
def load_profile(path):
    data=json.loads(Path(path).read_text());required={'name','variant','hostnames','mac','jellyfin_user_id','native_paths'}
    allowed=required|{'remote_public_host'}
    require(required.issubset(data) and set(data)<=allowed,'Private profile has unknown/missing fields')
    require(data['variant'] in ('local','remote'),'Profile variant must be local or remote')
    require(isinstance(data['hostnames'],list) and data['hostnames'],'Profile needs allowed hostnames')
    require(isinstance(data['native_paths'],dict),'native_paths must be an object')
    if data['variant']=='remote':
        require(data['native_paths']=={},'Remote profile cannot carry native paths')
        host=data.get('remote_public_host')
        require(isinstance(host,str) and host==host.lower() and re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',host or '') is not None,
                'Remote profile requires a canonical public hostname')
    else:require('remote_public_host' not in data,'Local profile cannot carry a remote public hostname')
    return data

def payloads(stage):
    result={}
    for name,digest in PAYLOAD_HASHES.items():
        data=(stage/name).read_bytes();require(sha(data)==digest,'Unreviewed payload: '+name)
        compile(data,name,'exec');result[name]=data
    return result

def search_default(data):
    before=DISCOVER+SEARCH;after=SEARCH+DISCOVER
    if sha(data) in SEARCH_BASE:
        require(data.count(before)==1 and data.count(after)==0,'Search blocks are missing/duplicated')
        return data.replace(before,after,1)
    if data.count(after)==1 and data.count(before)==0:
        require(sha(data.replace(after,before,1)) in SEARCH_BASE,'Unreviewed installed search selector')
        return data
    raise RuntimeError('Unreviewed search skin source')

def settings(data):
    return {x.get('id'):(x.text or '').strip() for x in ET.fromstring(data).findall('setting') if x.get('id')}

def reviewed_untracked_remote(relative,digest,recorded,manifest_digest,remote):
    """Only the exact historical remote manifest may adopt its two unowned inputs."""
    return (remote and relative in REMOTE_UNTRACKED_BASE
            and digest==REMOTE_UNTRACKED_BASE[relative] and recorded is None
            and manifest_digest==REMOTE_UNTRACKED_MANIFEST)

def build_changes(root,stage,profile):
    expected={};changes={}
    def read(path):
        if path not in expected:expected[path]=path.read_bytes() if path.exists() else None
        return expected[path]
    manifest=root/'addons/plugin.video.habibi.resume/verified-build.json'
    require(manifest.is_file(),'Required live integrity manifest is absent')
    record=json.loads(read(manifest));require(isinstance(record.get('files'),dict) and isinstance(record.get('versions'),dict),'Bad manifest')
    for name,version in VERSIONS.items():
        addon=ET.fromstring(read(root/'addons'/name/'addon.xml'))
        require(addon.get('id')==name and addon.get('version')==version,'Unreviewed addon version: '+name)
        require(record['versions'].get(name)==version,'Manifest version mismatch: '+name)
    remote=profile['variant']=='remote'
    def verify_touched(path):
        relative=str(path.relative_to(root));digest=sha(read(path))
        require(digest in TOUCHED[relative] or (remote and REMOTE_R6_OUTPUT.get(relative)==digest),
                'Unreviewed whole-file source: '+relative)
        untracked=reviewed_untracked_remote(relative,digest,record['files'].get(relative),
                                           sha(read(manifest)),remote)
        require(record['files'].get(relative)==digest or untracked,'Source/manifest drift: '+relative)
    def replace(path,old,new):
        text=changes.get(path,read(path).decode())
        relative=str(path.relative_to(root))
        if path not in changes and sha(read(path))==TOUCHED_OUTPUT.get(relative):return
        if new in text:return
        require(text.count(old)==1,'Unreviewed source anchor: '+str(path));changes[path]=text.replace(old,new,1)
    home=root/'addons/plugin.video.habibi.resume'
    verify_touched(home/'client.py');verify_touched(home/'default.py')
    replace(home/'client.py',"'toprated':'Top Rated Movies'}","'toprated':'Top Rated Movies','searchmovies':'Library Movies','searchshows':'Library TV Shows'}")
    replace(home/'default.py',"        items = client.listing(mode, params.get('series'), start)","        is_search = mode in ('searchmovies', 'searchshows')\n        query = params.get('query', '')\n        if is_search:\n            from search import search\n            items = search(client, query, 'Movie' if mode == 'searchmovies' else 'Series', start)\n        else:\n            items = client.listing(mode, params.get('series'), start)")
    replace(home/'default.py',"            if mode != 'series':","            if mode != 'series' and not is_search:")
    replace(home/'default.py',"            more_params = {'mode':mode,'start':start+page_size}","            more_params = {'mode':mode,'start':start+page_size}\n            if is_search:more_params['query']=query")
    bundle=payloads(stage);target=home/'search.py';require(read(target) in (None,bundle['search.py']),'Different search helper exists')
    target_record=record['files'].get(str(target.relative_to(root)))
    if read(target) is None:require(target_record is None,'Absent search helper has active manifest hash')
    else:require(target_record==sha(read(target)),'Search helper/manifest drift')
    changes[target]=bundle['search.py']
    template=root/'addons/skin.arctic.fuse.3/shortcuts/generator/data/setup/search_path.xml';verify_touched(template);text=read(template).decode()
    for rules in ('widget_path','widget_path_end'):
        match=re.search(r'(<rules name="'+rules+r'">)(.*?)(</rules>)',text,re.S);require(match,'Missing search template rule');block=match[2]
        for kind,mode in (('Movies','searchmovies'),('TvShows','searchshows')):
            value='plugin://plugin.video.habibi.resume/?mode='+mode+'&amp;amp;query=' if rules=='widget_path' else ''
            block,count=re.subn(r'(<condition>\{item_path\}==DefaultSearch-'+kind+r'</condition>\s*<value>).*?(</value>)',lambda m:m[1]+value+m[2],block,flags=re.S);require(count==1,'Ambiguous search rule')
        text=text[:match.start(2)]+block+text[match.end(2):]
    ET.fromstring(text);changes[template]=text.encode()
    http=root/'addons/plugin.video.jellyfin/jellyfin_kodi/jellyfin/http.py';verify_touched(http)
    replace(http,'        data["verify"] = data.get("verify") or self.config.data.get("auth.ssl", False)','        if data.get("verify") is None:\n            data["verify"] = self.config.data.get("auth.ssl")\n        if data["verify"] is None:\n            data["verify"] = True')
    skin=root/SEARCH_SKIN;skin_source=read(skin);skin_output=search_default(skin_source)
    recorded_skin=record['files'].get(SEARCH_SKIN)
    if skin_output==skin_source:require(recorded_skin==sha(skin_source),'Search skin/manifest drift')
    else:require(recorded_skin in (None,sha(skin_source)),'Search skin baseline/manifest drift')
    changes[skin]=skin_output
    venom=root/'addons/plugin.video.venom.tv';marker=root/'userdata/addon_data/plugin.video.venom.tv/remote-native.json'
    require((read(marker) is not None and sha(read(marker))==REMOTE_MARKER) if remote else read(marker) is None,'Remote marker/profile mismatch')
    cohorts=(REMOTE_BASE,REMOTE_R3,REMOTE_R5,REMOTE_OUT) if remote else (VENOM_BASE,VENOM_R3,VENOM_R5,VENOM_OUT)
    names=cohorts[0];current={n:sha(read(venom/n)) if read(venom/n) is not None else None for n in names};require(current in cohorts,'Unreviewed Venom cohort')
    for name,digest in current.items():
        rel='addons/plugin.video.venom.tv/'+name;require(record['files'].get(rel)==digest,'Venom manifest drift: '+name)
        prefix='remote-venom/' if remote and name!='shared_favorites.py' else 'venom/'
        replacement=bundle[prefix+name]
        if read(venom/name)!=replacement:changes[venom/name]=replacement
    jfdata=root/'userdata/addon_data/plugin.video.jellyfin';values=settings(read(jfdata/'settings.xml'))
    require(values.get('playFromStream')=='true' and values.get('playFromTranscode')=='false','Unreviewed playback settings')
    if remote:require(values.get('useDirectPaths')=='0','Remote profile must stay add-on mode')
    else:
        require(values.get('useDirectPaths')=='1','Local profile requires Native mode')
        require(json.loads(read(jfdata/'data.json'))['Servers'][0].get('paths',{})==profile['native_paths'],'Native path mappings differ')
        helper=root/'addons/plugin.video.jellyfin/jellyfin_kodi/helper';paths={n:helper/n for n in NATIVE_BASE}
        current_native={n:sha(read(p)) if read(p) is not None else None for n,p in paths.items()};require(current_native in (NATIVE_BASE,NATIVE_OUT),'Unreviewed native cohort')
        for name,path in paths.items():
            recorded=record['files'].get(str(path.relative_to(root)))
            if current_native==NATIVE_OUT:require(recorded==current_native[name],'Native manifest drift: '+name)
            elif current_native[name] is None:require(recorded is None,'Absent native helper has manifest hash')
            elif recorded is not None:require(recorded==current_native[name],'Native baseline manifest drift: '+name)
            replacement=bundle[name if name=='native_originals.py' else 'jellyfin/'+name]
            if read(path)!=replacement:changes[path]=replacement
    # Never use the repository's historical sample manifest as device truth.
    for path,content in changes.items():record['files'][str(path.relative_to(root))]=sha(content if isinstance(content,bytes) else content.encode())
    changes={p:(c if isinstance(c,bytes) else c.encode()) for p,c in changes.items()};changes[manifest]=(json.dumps(record,indent=2)+'\n').encode()
    return transaction.Plan({p:c for p,c in changes.items() if read(p)!=c},expected)

def live_plan(root,stage,profile,hostname_path,mac_path):
    account=root/'userdata/addon_data/plugin.video.jellyfin/data.json';identity={p:p.read_bytes() for p in (hostname_path,mac_path,account)}
    hostname=identity[hostname_path].decode().strip();mac=identity[mac_path].decode().strip().lower();servers=json.loads(identity[account])['Servers']
    require(hostname in profile['hostnames'],'Hostname not allowed by private profile');require(mac==profile['mac'].lower(),'Hardware identity mismatch')
    require(servers and servers[0].get('UserId')==profile['jellyfin_user_id'],'Jellyfin identity mismatch')
    plan=build_changes(root,stage,profile)
    for path,data in identity.items():require(path not in plan.expected or plan.expected[path]==data,'Identity changed during planning');plan.expected[path]=data
    return plan

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--profile',required=True);parser.add_argument('--payload',required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    profile=load_profile(args.profile);root=Path('/storage/.kodi');plan=live_plan(root,Path(args.payload),profile,Path('/storage/.cache/hostname'),Path('/sys/class/net/wlan0/address'))
    if not args.apply:
        print('PLAN_ONLY',len(plan),'replacement(s)')
        for path in sorted(plan,key=lambda value:str(value)):print(path.relative_to(root))
        print('No files changed; rerun with --apply after review and idle confirmation.')
        return
    backup=Path('/storage/upgrade-staging')/('combined-before-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
    if transaction.deploy(root,plan,backup):print('Applied reviewed cohort; rollback:',backup)
    else:print('Reviewed cohort already installed; Kodi not restarted')
if __name__=='__main__':main()
