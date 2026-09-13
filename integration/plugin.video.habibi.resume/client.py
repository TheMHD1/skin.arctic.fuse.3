"""Small Jellyfin 12 client, shared by the Home listing and its tests."""
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FIELDS = 'Overview,DateCreated,Path,ProviderIds'
LABELS = {'resume':'Continue Watching', 'nextup':'Next Up', 'movies':'Latest Movies',
          'episodes':'Latest Episodes', 'shows':'Latest Shows', 'favorites':'Favorites', 'series':'Episodes', 'toprated':'Top Rated Movies'}

def valid_id(value):
    if not re.fullmatch(r'[0-9a-fA-F]{32}', value or ''):
        raise ValueError('Invalid item ID')
    return value

class Client:
    def __init__(self, server):
        self.server = server
        self.base = server['address'].rstrip('/')
        self.user = server['UserId']

    def request(self, path, method='GET', **params):
        header = 'MediaBrowser Client="Habibi Home", Device="Kodi", DeviceId="habibi-home", Version="1.1", Token="'+self.server['AccessToken']+'"'
        req = Request(self.base+'/'+path+'?'+urlencode(params), headers={'Authorization':header}, method=method)
        with urlopen(req, timeout=10) as response:
            return json.load(response)

    def get(self, path, **params):
        return self.request(path, **params)

    def set_favorite(self, item_id, enabled):
        return self.request('Users/'+self.user+'/FavoriteItems/'+valid_id(item_id),
                            method='POST' if enabled else 'DELETE')

    def listing(self, mode, series=None, start=0):
        params = dict(Limit=30, StartIndex=max(0,int(start)), Fields=FIELDS, EnableTotalRecordCount='false')
        if mode == 'shows':
            # This server ignores DateLastMediaAdded as a SortBy value. Fetch the
            # series summaries in pages and sort that explicit timestamp ourselves.
            items=[]
            while True:
                page=self.get('Users/'+self.user+'/Items', Recursive='true', IncludeItemTypes='Series',
                              Fields=FIELDS+',DateLastMediaAdded', Limit=500, StartIndex=len(items))['Items']
                items.extend(page)
                if len(page)<500: break
            items.sort(key=lambda x:(x.get('Name','').casefold(),x['Id']))
            items.sort(key=lambda x:x.get('DateLastMediaAdded') or x.get('DateCreated') or '',reverse=True)
            return items[start:start+30]
        if mode == 'resume':
            return self.get('Users/'+self.user+'/Items/Resume', MediaTypes='Video', **params)['Items']
        if mode == 'nextup':
            return self.get('Shows/NextUp', UserId=self.user, EnableResumable='false', EnableRewatching='false', **params)['Items']
        if mode == 'series':
            params.update(Limit=100, StartIndex=max(0,int(start)))
            return self.get('Shows/'+valid_id(series)+'/Episodes', UserId=self.user, IsMissing='false', **params)['Items']
        if mode not in ('movies', 'episodes', 'favorites', 'toprated'):
            raise ValueError('Unknown list')
        params.update(Recursive='true', IsMissing='false', IncludeItemTypes={'movies':'Movie','episodes':'Episode','toprated':'Movie','favorites':'Movie,Series,Episode'}[mode])
        if mode == 'favorites':
            params.update(Filters='IsFavorite', SortBy='SortName', SortOrder='Ascending')
        elif mode == 'toprated':
            params.update(SortBy='CommunityRating,SortName', SortOrder='Descending')
        else:
            params.update(SortBy='DateCreated,SortName', SortOrder='Descending')
        return self.get('Users/'+self.user+'/Items', **params)['Items']

    def following(self, item_id):
        current = self.get('Users/'+self.user+'/Items/'+valid_id(item_id))
        series = valid_id(current.get('SeriesId'))
        items = self.get('Shows/'+series+'/Episodes', UserId=self.user, AdjacentTo=item_id, IsMissing='false')['Items']
        for i, item in enumerate(items):
            if item['Id'] == item_id:
                return items[i+1] if i+1 < len(items) else None
        return None

def play_path(item_id, server_id):
    # This companion reads Servers[0], which Jellyfin for Kodi initializes as
    # the default client. Its server GUID is NOT a client-registry key.
    return 'plugin://plugin.video.jellyfin/?'+urlencode({'mode':'play','id':valid_id(item_id)})
