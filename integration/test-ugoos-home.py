import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent/'plugin.video.habibi.resume'))
from client import Client, valid_id, play_path

MOVIES='a'*32
SHOWS='b'*32
server={'address':'http://test','UserId':'u','AccessToken':'unused'}
client=Client(server, {'movies':[MOVIES], 'shows':[SHOWS]})
client._authorized_views=[{'Id':MOVIES,'Name':'Movies','CollectionType':'movies'},
                          {'Id':SHOWS,'Name':'Shows','CollectionType':'tvshows'}]
calls=[]
client.get=lambda path,**params: calls.append((path,params)) or ([] if path=='Items/Latest' else {'Items':[]})
for mode in ('resume','nextup','movies','episodes','favorites'):
    assert client.listing(mode)==[]
assert calls[0][0]=='Users/u/Items/Resume'
assert calls[1][0]=='Shows/NextUp' and calls[1][1]['EnableResumable']=='false'
assert calls[2][1]['IncludeItemTypes']=='Movie' and calls[2][1]['ParentId']==MOVIES
assert calls[3][1]['IncludeItemTypes']=='Episode' and calls[3][1]['ParentId']==SHOWS
assert calls[4][1]['Filters']=='IsFavorite' and 'ParentId' not in calls[4][1]
assert all(call[1]['Limit']==30 for call in calls[:5])

# Latest Shows uses bounded latest Episode groups, resolves mixed representatives
# to Series cards, and orders across roots by latest content rather than the
# Series' original creation date.
old_series='1'*32
new_series='2'*32
latest=Client(server, {'shows':[SHOWS]})
latest._authorized_views=[{'Id':SHOWS,'Name':'Shows','CollectionType':'tvshows'}]
latest_calls=[]
def latest_get(path,**params):
    latest_calls.append((path,params))
    if path=='Items/Latest':
        return [
            {'Id':'3'*32,'Type':'Episode','SeriesId':old_series,'DateCreated':'2026-09-22'},
            {'Id':new_series,'Type':'Series','DateLastMediaAdded':'2026-09-20'},
        ]
    return {'Items':[
        {'Id':new_series,'Name':'New show','Type':'Series','DateCreated':'2026-09-19'},
        {'Id':old_series,'Name':'Old show, new episode','Type':'Series','DateCreated':'2020-01-01'},
    ]}
latest.get=latest_get
assert [row['Id'] for row in latest.listing('shows')]==[old_series,new_series]
assert latest_calls[0][0]=='Items/Latest'
assert latest_calls[0][1]['IncludeItemTypes']=='Episode'
assert latest_calls[0][1]['GroupItems']=='true'
assert latest_calls[0][1]['Limit']==30
assert len(latest_calls)==2  # never scans every Series page

# Missing scopes are derived from the current user's authorized views. Exact
# Venom roots are excluded from owned routes and uniquely selected for Venom.
dynamic=Client(server)
views=[
    {'Id':'4'*32,'Name':'Movies','CollectionType':'movies'},
    {'Id':'5'*32,'Name':'Shows','CollectionType':'tvshows'},
    {'Id':'6'*32,'Name':'Shoko Anime','CollectionType':None,'Type':'CollectionFolder'},
    {'Id':'7'*32,'Name':' Venom   Movies ','CollectionType':'movies'},
    {'Id':'8'*32,'Name':'VENOM SERIES','CollectionType':'tvshows'},
    {'Id':'a'*32,'Name':'Playlists','CollectionType':None,'Type':'UserView'},
    {'Id':'b'*32,'Name':'Venom Sports','CollectionType':None,'Type':'CollectionFolder'},
]
view_calls=[]
dynamic.get=lambda path,**params:view_calls.append(path) or {'Items':views}
assert dynamic.scope_ids('movies')==['4'*32,'6'*32]
assert dynamic.scope_ids('shows')==['5'*32,'6'*32]
assert dynamic.scope_ids('venom_movies')==['7'*32]
assert dynamic.scope_ids('venom_shows')==['8'*32]
assert view_calls==['Users/u/Views']  # one per Client, then cached

ambiguous=Client(server)
ambiguous.get=lambda *a,**k:{'Items':[views[3],dict(views[3],Id='9'*32)]}
assert ambiguous.scope_ids('venom_movies')==[]
assert ambiguous.scope_ids('movies')==[]  # never widens to root
misconfigured=Client(server, {'movies':['7'*32]})
misconfigured.get=lambda *a,**k:{'Items':views}
assert misconfigured.scope_ids('movies')==[]  # private config cannot cross provider boundary
alias=Client(server)
alias.get=lambda *a,**k:{'Items':[{'Id':'c'*32,'Name':'Venom Shows',
                                   'CollectionType':'tvshows','Type':'CollectionFolder'}]}
assert alias.scope_ids('venom_shows')==['c'*32]

# Resume and NextUp are server-authoritative global ranks; configured library
# scopes do not inject ParentId or re-sort by media creation time.
ranked=Client(server, {'resume':[MOVIES], 'nextup':[SHOWS]})
resume_rows=[{'Id':'a','DateCreated':'2000','UserData':{'LastPlayedDate':'2026-09-22'}},
             {'Id':'b','DateCreated':'2030','UserData':{'LastPlayedDate':'2026-09-21'}}]
rank_calls=[]
def rank_get(path,**params):
    rank_calls.append((path,params))
    return {'Items':resume_rows}
ranked.get=rank_get
assert ranked.listing('resume')==resume_rows
assert ranked.listing('nextup')==resume_rows
assert all('ParentId' not in params for _,params in rank_calls)

# Multi-parent paging obtains only enough sorted rows from each parent for the
# requested global page, then globally merges and deduplicates.
paged=Client(server, {'movies':['c'*32,'d'*32]})
paged._authorized_views=[{'Id':'c'*32,'Name':'Movies 1','CollectionType':'movies'},
                         {'Id':'d'*32,'Name':'Movies 2','CollectionType':'movies'}]
page_calls=[]
def page_get(path,**params):
    page_calls.append(params)
    base=1000 if params['ParentId']=='c'*32 else 2000
    rows=[]
    for index in range(params['StartIndex'],params['StartIndex']+params['Limit']):
        rows.append({'Id':f'{base+index:032x}','Name':str(index),
                     'DateCreated':f'2026-09-{30-index%30:02d}T00:00:00Z'})
    return {'Items':rows}
paged.get=page_get
assert len(paged.listing('movies',start=30))==30
assert [(row['StartIndex'],row['Limit']) for row in page_calls]==[(0,30),(30,30),(0,30),(30,30)]

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

requests=[]
client.request=lambda path,**params: requests.append((path,params)) or {}
client.set_favorite('a'*32,True)
client.set_favorite('a'*32,False)
assert requests==[('Users/u/FavoriteItems/'+'a'*32,{'method':'POST'}),
                  ('Users/u/FavoriteItems/'+'a'*32,{'method':'DELETE'})]
print('PASS: authoritative playback rank, scoped recent merge, grouped latest shows, view isolation, paging and mutations')
