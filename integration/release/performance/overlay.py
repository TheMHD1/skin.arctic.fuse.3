"""Minimal paired optimization after the complete UX release."""
import hashlib

BROWSER='addons/plugin.video.venom.tv/browser.py'
FAVORITES='addons/plugin.video.venom.tv/shared_favorites.py'
CLIENT='addons/plugin.video.habibi.resume/client.py'
HELPER='addons/plugin.video.venom.tv/favorite_refresh.py'
BEFORE={
    'local':{BROWSER:'ad999c6bc1e920093c6dd5187a2ee089adac4fcab3f3a610bf613a868d798107'},
    'remote':{BROWSER:'f81b91f1ec47a21ef88a78517850878c014329bf04cb849f383a23e2789e6aa7'},
}
for row in BEFORE.values():
    row.update({FAVORITES:'ab270c3806c4916b2a793b65570d650e8df06dac692e490215351e0f68e34df4',
                CLIENT:'c742d7e46fb75c7b61ae68c94a9bfb781c18c0435bef722e870913d20712b6ca'})

def replace(source,old,new):
    if source.count(old)!=1:raise ValueError('Unreviewed performance source anchor')
    return source.replace(old,new)

def browser(source):
    source=replace(source,'import shared_favorites\n','import shared_favorites\nfrom favorite_refresh import FavoriteRefresh\n')
    source=replace(source,'\n        self.favorite_check=0\n',
        '\n        self.favorite_check=0\n        self.favorite_refresh=FavoriteRefresh(LatestWorker(),self.shared.server,self.apply_favorite_refresh) if self.shared else None\n')
    start=source.index('        if (self.shared and time.monotonic()-self.favorite_check>30')
    end=source.index('\n    def apply_favorite_refresh',start)
    source=source[:start]+'''        refresh=getattr(self,'favorite_refresh',None)
        if refresh:
            report=refresh.poll(blocked=self.network_busy or self.critical_busy or not self.jobs.empty())
            if report:
                name,elapsed,cancelled=report
                xbmc.log('Venom optional read: %s %.3fs%s'%(name,elapsed,' cancelled' if cancelled else ''),xbmc.LOGINFO)
'''+source[end:]
    source=replace(source,"        if hasattr(self,'network'):self.network.close()\n",
        "        if hasattr(self,'network'):self.network.close()\n        if getattr(self,'favorite_refresh',None):self.favorite_refresh.close()\n")
    source=replace(source,"        self.cancel_network('user mutation')\n",
        "        if getattr(self,'favorite_refresh',None):self.favorite_refresh.invalidate()\n        self.cancel_network('user mutation')\n")
    source=replace(source,'                self.favorite_check=0\n',
        "                self.favorite_check=0\n                if getattr(self,'favorite_refresh',None):self.favorite_refresh.invalidate()\n")
    return source

def favorites(source):
    source=replace(source,'self.cached=[];self.stamp=0;self.matches={};self.retry_after=0',
                   'self.cached=[];self.stamp=0;self.cached_summary=False;self.matches={};self.retry_after=0')
    source=replace(source,'    def favorites(self,force=False,cancelled=None):',
                   '    def favorites(self,force=False,cancelled=None,summary=False):')
    source=replace(source,'        if not force and time.monotonic()-self.stamp<15:return self.cached',
                   '        if not force and summary==self.cached_summary and time.monotonic()-self.stamp<15:return self.cached')
    source=replace(source,'            offset=0\n            while True:',
        "            params['EnableTotalRecordCount']='false'\n            if summary:params.update(EnableImages='false',EnableUserData='false')\n            offset=0\n            while True:")
    source=replace(source,'        self.cached=items;self.stamp=time.monotonic()',
                   '        self.cached=items;self.cached_summary=summary;self.stamp=time.monotonic()')
    source=replace(source,'        items=self.favorites(cancelled=cancelled)',
                   '        items=self.favorites(cancelled=cancelled,summary=True)')
    return source

def transform(name,data,cohort):
    if hashlib.sha256(data).hexdigest()!=BEFORE[cohort][name]:raise ValueError('Unreviewed performance cohort')
    source=data.decode()
    if name==BROWSER:source=browser(source)
    elif name==FAVORITES:source=favorites(source)
    elif name==CLIENT:
        source=replace(source,"            response = self.get('Users/'+self.user+'/Views')",
            "            response = self.get('Users/'+self.user+'/Views', IncludeExternalContent='false')")
    else:raise ValueError('Unsupported performance source')
    compile(source,name,'exec');return source.encode()
