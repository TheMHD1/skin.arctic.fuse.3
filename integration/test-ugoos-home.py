import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'plugin.video.habibi.resume'))
from client import Client, valid_id, play_path
client=Client({'address':'http://test','UserId':'u','AccessToken':'unused'})
calls=[]
client.get=lambda path,**params: calls.append((path,params)) or {'Items':[]}
for mode in ('resume','nextup','movies','episodes','favorites'):
    assert client.listing(mode)==[]
assert calls[0][0]=='Users/u/Items/Resume'
assert calls[1][1]['EnableResumable']=='false'
assert calls[2][1]['IncludeItemTypes']=='Movie'
assert calls[3][1]['IncludeItemTypes']=='Episode'
assert calls[4][1]['Filters']=='IsFavorite'
assert all(x[1]['Limit']==30 for x in calls)
assert client.listing('shows')==[]
assert calls[-1][1]['IncludeItemTypes']=='Series'
assert 'DateLastMediaAdded' in calls[-1][1]['Fields']
client.get=lambda *a,**k:{'Items':[{'Id':'1','Name':'Old show new episode','DateLastMediaAdded':'2026-09-13'}, {'Id':'2','Name':'Newer show older episode','DateLastMediaAdded':'2026-09-01'}]}
assert [x['Id'] for x in client.listing('shows')]==['1','2']
for bad in ('','abc','../path','a'*31,'a'*33):
    try: valid_id(bad)
    except ValueError: pass
    else: raise AssertionError(bad)
assert play_path('a'*32,'server').startswith('plugin://plugin.video.jellyfin/')
assert 'server=' not in play_path('a'*32,'server-guid')
responses=[{'SeriesId':'b'*32},{'Items':[{'Id':'c'*32},{'Id':'a'*32},{'Id':'d'*32}]}]
client.get=lambda *a,**k:responses.pop(0)
assert client.following('a'*32)['Id']=='d'*32
responses=[{'SeriesId':'b'*32},{'Items':[{'Id':'a'*32}]}]
assert client.following('a'*32) is None
print('PASS: five endpoint contracts, limits, ID guards, playback delegation, following/last episode')
requests=[]
client.request=lambda path,**params: requests.append((path,params)) or {}
client.set_favorite('a'*32,True)
client.set_favorite('a'*32,False)
assert requests==[('Users/u/FavoriteItems/'+'a'*32,{'method':'POST'}),('Users/u/FavoriteItems/'+'a'*32,{'method':'DELETE'})]
print('PASS: favorite add/remove endpoints and methods')

scoped=Client({'address':'http://test','UserId':'u','AccessToken':'unused'},scopes={'movies':['a'*32,'b'*32]})
calls=[]
def scope_get(path,**params):
    calls.append(params)
    return {'Items':[{'Id':params['ParentId'],'Name':'title','DateCreated':'2026-09-13' if params['ParentId']=='b'*32 else '2026-01-01'}]}
scoped.get=scope_get
assert [x['Id'] for x in scoped.listing('movies')]==['b'*32,'a'*32]
assert {x['ParentId'] for x in calls}=={'a'*32,'b'*32}
calls.clear()
scoped.get=lambda path,**params:calls.append(params) or {'Items':[]}
scoped.listing('resume')
assert 'ParentId' not in calls[0]
print('PASS: Home library scopes merge dates and preserve server-wide resume')
