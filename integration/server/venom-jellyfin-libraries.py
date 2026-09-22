#!/usr/bin/env python3
"""Create Habibi-only IPTV libraries without exposing them during setup."""
import json
from pathlib import Path
import runpy
import urllib.parse
import sys
import shutil
import fcntl
import os

ROOT=Path('/data/config/iptv-venom')
api=runpy.run_path('/root/iptv-jellyfin-admin.py')['api']
names={'Venom Movies':('movies','/config/venom-catalogue/movies'),
       'Venom Series':('tvshows','/config/venom-catalogue/series')}

def main():
    libraries=api('/Library/VirtualFolders')
    if '--refresh' in sys.argv:
        with (ROOT/'refresh.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                print('Refresh helper already running');return
            if shutil.disk_usage('/data/config/jellyfin').free<8*1024*1024*1024:
                print('Refresh deferred: less than 8 GiB free');return
            # Jellyfin's refresh queue is serial and does not deduplicate requests.
            # Coalesce timer ticks while a library is active/queued, and publish
            # series first so a large movie import cannot repeatedly jump ahead.
            state_path=ROOT/'refresh-requested.json'
            try:requested=json.loads(state_path.read_text())
            except (FileNotFoundError,ValueError):requested={}
            for library in sorted(libraries,key=lambda item:item['Name']!='Venom Series'):
                if library['Name'] in names:
                    kind=names[library['Name']][1].rsplit('/',1)[-1]
                    marker=ROOT/('refresh-dirty-'+kind)
                    generation=marker.read_text() if marker.exists() else 'legacy-initial'
                    if requested.get(kind)==generation:
                        print('Catalogue unchanged:',library['Name']);continue
                    if library.get('RefreshStatus') in ('Active','Queued'):
                        print('Refresh already pending:',library['Name']);continue
                    api('/Items/'+library['ItemId']+'/Refresh?Recursive=true&MetadataRefreshMode=Default&ImageRefreshMode=Default',method='POST')
                    requested[kind]=generation
                    tmp=state_path.with_suffix('.tmp')
                    tmp.write_text(json.dumps(requested));os.replace(tmp,state_path)
                    print('Refresh queued:',library['Name'])
        return
    users=api('/Users')
    if sum(u['Name'].casefold()=='habibi' for u in users)!=1:raise RuntimeError('Expected one Habibi user')
    backup=ROOT/'jellyfin-policies-before-vod.json'
    if not backup.exists():
        backup.write_text(json.dumps(users,indent=2));backup.chmod(0o600)
    existing_ids=[x['ItemId'] for x in libraries if x['Name'] not in names]
    # Narrow access before creating even an empty library. Preserve prior folders.
    for user in users:
        if user['Name'].casefold()=='habibi':continue
        policy=dict(user['Policy'])
        if policy.get('EnableAllFolders'):
            blocked={x.replace('-','') for x in policy.get('BlockedMediaFolders',[])}
            policy['EnabledFolders']=[x for x in existing_ids if x.replace('-','') not in blocked]
            policy['EnableAllFolders']=False
            # Empty blocked list makes Jellyfin use the temporary allowlist.
            policy['BlockedMediaFolders']=[]
            api('/Users/'+user['Id']+'/Policy',policy,'POST')
    for name,(kind,path) in names.items():
        if any(x['Name']==name for x in libraries):continue
        available=api('/Libraries/AvailableOptions?libraryContentType='+kind+'&isNewLibrary=true')
        options={'EnableRealtimeMonitor':False,'EnableInternetProviders':False,
                 'EnableChapterImageExtraction':False,'ExtractChapterImagesDuringLibraryScan':False,
                 'EnableTrickplayImageExtraction':False,'ExtractTrickplayImagesDuringLibraryScan':False,
                 'EnableLUFSScan':False,'EnableAutomaticSeriesGrouping':False,'AutomaticallyAddToCollection':False,
                 'SaveLocalMetadata':False,'MetadataSavers':[],'AutomaticRefreshIntervalDays':0,
                 'SubtitleDownloadLanguages':[],'DisabledSubtitleFetchers':[x['Name'] for x in available.get('SubtitleFetchers',[])],
                 'DisabledMediaSegmentProviders':[x['Name'] for x in available.get('MediaSegmentProviders',[])],
                 'TypeOptions':[{'Type':t,'MetadataFetchers':[],'ImageFetchers':[],
                                 'ImageOptions':[{'Type':'Primary','Limit':1},{'Type':'Backdrop','Limit':0},{'Type':'Thumb','Limit':0}]} for t in ('Movie','Series','Season','Episode')]}
        query=urllib.parse.urlencode({'name':name,'collectionType':kind,'paths':path,'refreshLibrary':'false'})
        api('/Library/VirtualFolders?'+query,{'LibraryOptions':options},'POST')
    libraries=api('/Library/VirtualFolders')
    private=[x['ItemId'] for x in libraries if x['Name'] in names]
    if len(private)!=2:raise RuntimeError('Expected two private libraries')
    for original in users:
        user=api('/Users/'+original['Id'])
        policy=dict(user['Policy'])
        if user['Name'].casefold()=='habibi':
            if not policy.get('EnableAllFolders'):policy['EnabledFolders']=list(set(policy.get('EnabledFolders',[])+private))
        else:
            # This Jellyfin build returns BlockedMediaFolders but its policy
            # updater does not persist it. Use the supported explicit allowlist.
            policy['EnableAllFolders']=False
            policy['EnabledFolders']=[x for x in policy.get('EnabledFolders',[]) if x not in private]
        api('/Users/'+user['Id']+'/Policy',policy,'POST')
    for user in api('/Users'):
        if user['Name'].casefold()=='habibi':continue
        p=user['Policy']
        assert not p.get('EnableAllFolders')
        assert not set(private).intersection(p.get('EnabledFolders',[]))
    print('Habibi-only libraries configured:',[(x['Name'],x['ItemId']) for x in libraries if x['Name'] in names])

if __name__=='__main__':main()
