"""Additive repairs after the reviewed remote originals/search-priority cohort.

Do not modify historical release pins or install the legacy repository skin.
"""
import hashlib
import xml.etree.ElementTree as ET

BEFORE = {
    'addons/plugin.video.venom.tv/browser.py': 'f9cb951e99f567d5c5983e563bc9cf4b1a7f12160a43187d37bc962f3e0e8467',
    'addons/plugin.video.kodiseerr/jellyfin_bridge.py': '2e522b3ad837874d130584174c5a5ed1836c74cc07e85fd945fd75729a98587b',
    'addons/skin.arctic.fuse.3/1080i/Includes_Objects.xml': '8c214f38a01d2c0dfcba797b543c0437f1ea292385b42706002fcb2155071846',
    'addons/skin.arctic.fuse.3/1080i/Includes_Layouts.xml': '80e41db0843dd82c75c8e5faf186ae79cd4453a243685d0f695c7be5966e6cb9',
}
RATING = ('[!String.IsEmpty(ListItem.Property(Habibi.Rating.IMDb))'
          ' | !String.IsEmpty(ListItem.Rating(imdb))'
          ' | !String.IsEmpty(ListItem.Rating(tmdb))'
          ' | !String.IsEmpty(ListItem.Property(Habibi.Rating.Community))'
          ' | !String.IsEmpty(ListItem.Rating)]')


def replace(data, old, new, count=1):
    if data.count(old) != count:
        raise ValueError('Unexpected source anchor')
    return data.replace(old, new)


def browser(data):
    # Keep focus on a real button while the initial category list is empty.
    data = replace(data, '        self.jobs.put(self.load_categories)\n        self.setFocusId(910)',
                   '        self.jobs.put(self.load_categories)\n        self.setFocusId(901)')
    # Each deliberate category selection carries a focus request. Apply only
    # when the asynchronous results have populated the grid, never before.
    data = replace(data, '        self.load_entries();self.setFocusId(920)\n\n    def entry_snapshot',
                   '        self.focus_grid_when_ready=True\n        self.load_entries()\n\n    def entry_snapshot')
    data = replace(data, "                'native_offset':getattr(self,'native_offset',0)}",
                   "                'focus_grid_when_ready':getattr(self,'focus_grid_when_ready',False),\n"
                   "                'native_offset':getattr(self,'native_offset',0)}")
    data = replace(data, '        self.render()\n\n        if snapshot.get(\'restore_grid_position\')',
                   "        self.render()\n        if snapshot.get('focus_grid_when_ready'):\n"
                   "            self.focus_grid_when_ready=False\n"
                   "            if self.visible_entries and self.getFocusId() in (910,920):\n"
                   "                self.setFocusId(920)\n\n        if snapshot.get('restore_grid_position')")
    # Back while loading cancels the queued grid, including its focus request.
    data = replace(data, "            else:self.close()\n        elif action.getId()",
                   "            elif getattr(self,'network_busy',False) and self.category is not None:\n"
                   "                self.cancel_network('navigation back while loading')\n"
                   "                self.focus_grid_when_ready=False\n"
                   "            else:self.close()\n        elif action.getId()")
    data = replace(data, "        self.open_pending=None\n        self.page=0;self.query='';self.stack=[];self.scope=None;self.category=None;self.selected_category_index=0",
                   "        self.open_pending=None\n        self.focus_grid_when_ready=False\n"
                   "        self.page=0;self.query='';self.stack=[];self.scope=None;self.category=None;self.selected_category_index=0")
    return playback_lifecycle(data)


def playback_lifecycle(data):
    # Activating fullscreen hides a WindowXML without invoking our close()
    # handler. Retire the remote browser before handing off; its main loop then
    # releases the singleton even if playback fails or Stop returns to Home.
    data=replace(data,"                    self.cancel_network('remote playback')\n                    rpc('Player.Open'",
                 "                    self.cancel_network('remote playback')\n                    self.close()\n                    rpc('Player.Open'")
    return replace(data,"            else:\n                xbmc.Player().play('plugin://plugin.video.jellyfin/?mode=play&id='+p['id'])",
                   "            else:\n                if REMOTE_NATIVE:self.close()\n                xbmc.Player().play('plugin://plugin.video.jellyfin/?mode=play&id='+p['id'])")


def bridge(data):
    start = data.index('def library_index():')
    end = data.index('\ndef route(item):', start)
    return data[:start] + '''def library_index():
    """Index only this account's owned roots, with finite request/time limits.

    Provider libraries must not become the default Discover playback choice.
    A partial/outage result is usable but never cached as a complete index.
    """
    import hashlib
    sys.path.insert(0,xbmcvfs.translatePath('special://home/addons/plugin.video.habibi.resume'))
    from client import Client
    auth=Path(xbmcvfs.translatePath('special://profile/addon_data/plugin.video.jellyfin/data.json'))
    server=json.loads(auth.read_text())['Servers'][0]
    scope_path=Path(xbmcvfs.translatePath('special://profile/addon_data/plugin.video.habibi.resume/home-library-scopes.json'))
    scopes=json.loads(scope_path.read_text()) if scope_path.exists() else {}
    client=Client(server,scopes)
    home=xbmcgui.Window(10000)
    revision=home.getProperty('Habibi.Home.Refresh')
    # Invalidate on login, permission/config change or server change. Never
    # store the access token itself in a global GUI property.
    identity=hashlib.sha256(json.dumps([server['address'],server['UserId'],
        server['AccessToken'],scopes],sort_keys=True).encode()).hexdigest()
    roots=[(kind,parent) for kind in ('movies','shows') for parent in client.scope_ids(kind)]
    raw=home.getProperty('Habibi.Discover.OwnedIndex.v2')
    try:
        saved=json.loads(raw)
        if (saved['identity']==identity and saved['roots']==[list(row) for row in roots]
                and saved['revision']==revision and 0<=time.time()-saved['time']<60):
            return saved['items']
    except (ValueError,KeyError,TypeError):pass
    index={};requests=0;deadline=time.monotonic()+8;complete=True
    for kind,parent in roots:
        start=0
        while True:
            if requests>=8 or time.monotonic()>=deadline:
                complete=False;break
            requests+=1
            page=client.request('Users/'+client.user+'/Items',
                timeout=max(.1,min(2,deadline-time.monotonic())),ParentId=parent,
                Recursive='true',IncludeItemTypes='Movie' if kind=='movies' else 'Series',
                Fields='ProviderIds',Limit=500,StartIndex=start,
                EnableTotalRecordCount='false',SortBy='SortName',SortOrder='Ascending')['Items']
            for item in page:
                ids={k.lower():str(v) for k,v in item.get('ProviderIds',{}).items() if v}
                if ids.get('tmdb') and item.get('Type') in ('Movie','Series'):
                    key=('movie' if item['Type']=='Movie' else 'tv')+':'+ids['tmdb']
                    index.setdefault(key,{k:item[k] for k in ('Id','Name','Type','ProviderIds','UserData') if k in item})
            if len(page)<500:break
            start+=len(page)
    if complete:
        home.setProperty('Habibi.Discover.OwnedIndex.v2',json.dumps({
            'time':time.time(),'revision':revision,'identity':identity,'roots':roots,'items':index}))
    return index
''' + data[end:]


def transform(name, data):
    if hashlib.sha256(data).hexdigest() != BEFORE[name]:
        raise ValueError('Unreviewed source: '+name)
    source=data.decode()
    if name.endswith('/browser.py'):
        source=browser(source)
    elif name.endswith('/jellyfin_bridge.py'):
        source=bridge(source)
    else:
        source=replace(source,'!String.IsEmpty($VAR[Label_Poster_Rating])',RATING)
    if name.endswith('.py'):
        compile(source,name,'exec')
    else:
        ET.fromstring(source)
    return source.encode()
