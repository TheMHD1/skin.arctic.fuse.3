"""Generic UX repairs after the paired AM9 layer, without changing transport."""
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
BROWSER='addons/plugin.video.venom.tv/browser.py'
SERVICE='addons/plugin.video.habibi.resume/service.py'
SELECTOR='addons/plugin.video.habibi.resume/search_selection.py'
BEFORE={
    'local': {BROWSER:'2f8aedfb7c71e8f5baa85af649b60cfad9d5cbcbd86dd8f915ed157221f17979',
              SERVICE:'4bd56224430ac38c9fe9a7d5aeb6123974070174403eaa6f34da1c95b21e6ffd'},
    'remote': {BROWSER:'6e0f3939ab89cdd1f9d85c167416d08d1b9a15846e3aad7f1619bca7398f7498',
               SERVICE:'4bd56224430ac38c9fe9a7d5aeb6123974070174403eaa6f34da1c95b21e6ffd'},
}

def replace(source,old,new):
    if source.count(old)!=1:raise ValueError('Unreviewed UX source anchor')
    return source.replace(old,new)

def browser(source):
    source=replace(source,'    def process(self):\n        try:call=self.jobs.get_nowait()',
        '''    def process(self):
        # Home can hide WindowXML without invoking close/onAction. Do not leave
        # a hidden owner polling forever and rejecting every later launch.
        # Native PVR fullscreen and temporary modal dialogs retain their window.
        if (xbmc.getCondVisibility('Window.IsActive(home)')
                and not xbmc.getCondVisibility('Player.HasMedia')
                and not xbmc.getCondVisibility('System.HasActiveModalDialog')):
            self.close()
            if self.closed:return
        try:call=self.jobs.get_nowait()''')
    source=harden_close(source)
    return remote_handoff(source) if 'REMOTE_NATIVE=' in source else source

def remote_handoff(source):
    # The local native-PVR path already waits for Stop before opening another
    # channel. Remote plugin resolution also needs to release the old player
    # before asking Jellyfin/provider to open a replacement live stream.
    source=replace(source,"    def open_channel_now(self,playback):\n        rpc('Player.Open'",
                   "    def open_channel_now(self,playback):\n        if REMOTE_NATIVE:self.close()\n        rpc('Player.Open'")
    source=replace(source,'    def begin_channel_playback(self,playback,selection=None,now=None):',
        '''    def begin_remote_channel_playback(self,playback,selection=None,now=None):
        self.cancel_live_handoff('replaced')
        self.cancel_network('remote playback')
        videos=[p for p in rpc('Player.GetActivePlayers',{}) if p.get('type')=='video']
        if not videos:
            self.open_channel_now(playback);return False
        if (len(videos)!=1 or type(videos[0].get('playerid')) is not int):
            raise RuntimeError('Ambiguous active player; no replacement opened')
        playerid=videos[0]['playerid']
        rpc('Player.Stop',{'playerid':playerid})
        now=time.monotonic() if now is None else now
        self.live_handoff={'playerid':playerid,'playback':dict(playback),'selection':selection,
                           'deadline':now+LIVE_HANDOFF_TIMEOUT_SECONDS,'next_poll':now}
        self.getControl(940).setLabel('Stopping current channel before switching…')
        return True

    def begin_channel_playback(self,playback,selection=None,now=None):''')
    source=replace(source,"                    self.cancel_network('remote playback')\n                    self.close()\n                    rpc('Player.Open',{'item':channel_playback_item(target,[])})\n                    xbmc.executebuiltin('ActivateWindow(fullscreenvideo)')",
                   "                    self.begin_remote_channel_playback(channel_playback_item(target,[]),selection)")
    compile(source,'remote-ordered-handoff','exec')
    return source

def harden_close(source):
    # An update popup can prevent onInit entirely. The activation deadline must
    # still release its owner without assuming initialized fields exist.
    source=replace(source,'        if self.closed:return\n        self.cancel_live_handoff',
                   "        if getattr(self,'closed',False):return\n        self.cancel_live_handoff")
    source=replace(source,'        self.request_generation+=1;self.request_apply=None;self.network_busy=False\n        self.critical_apply',
                   "        self.request_generation=getattr(self,'request_generation',0)+1;self.request_apply=None;self.network_busy=False\n        self.critical_apply")
    source=replace(source,"    if not home.getProperty('Venom.Browser.Open'):",
                   "    if not home.getProperty('Venom.Browser.Open') and not xbmc.getCondVisibility('System.HasActiveModalDialog'):")
    compile(source,'venom-ux-browser','exec')
    return source

def transform(name,data,cohort):
    if hashlib.sha256(data).hexdigest()!=BEFORE[cohort][name]:
        raise ValueError('Unreviewed UX cohort/source')
    source=data.decode()
    if name==BROWSER:source=browser(source)
    elif name==SERVICE:
        source=replace(source,'    refresh_clock = RefreshClock()\n',
                       '    refresh_clock = RefreshClock()\n    from search_selection import SearchSelection\n    search_selection = SearchSelection()\n')
        source=replace(source,'        now = time.monotonic()\n',
                       '        now = time.monotonic()\n        search_selection.poll(now)\n')
        if source.count('System.HasModalDialog')!=2:raise ValueError('Unreviewed Home modal guards')
        source=source.replace('System.HasModalDialog','System.HasActiveModalDialog')
    else:raise ValueError('Unsupported UX source')
    compile(source,name,'exec')
    return source.encode()
