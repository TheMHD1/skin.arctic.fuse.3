"""Small Jellyfin 12 client, shared by the Home listing and its tests."""
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FIELDS = 'Overview,DateCreated,Path,ProviderIds'
PAGE_SIZE = 30
MAX_LATEST = 500
LABELS = {'resume':'Continue Watching', 'nextup':'Next Up', 'movies':'Latest Movies',
          'episodes':'Latest Episodes', 'shows':'Latest Shows', 'favorites':'Favorites',
          'series':'Episodes', 'toprated':'Top Rated Movies',
          'searchmovies':'Movies', 'searchshows':'Shows',
          'searchvenommovies':'Venom Movies — Not HD',
          'searchvenomshows':'Venom Shows — Not HD'}

VENOM_NAMES = {'venom_movies':{'venom movies'},
               'venom_shows':{'venom series', 'venom shows'}}
NONMEDIA_VIEWS = {'collections', 'playlists', 'live tv', 'music', 'photos',
                  'home videos', 'books', 'audiobooks'}
SCOPE_TYPES = {
    'movies': {'movies', 'mixed'},
    'shows': {'tvshows', 'mixed'},
    'venom_movies': {'movies'},
    'venom_shows': {'tvshows'},
}


def valid_id(value):
    if not re.fullmatch(r'[0-9a-fA-F]{32}', value or ''):
        raise ValueError('Invalid item ID')
    return value


def _view_name(value):
    return ' '.join((value or '').casefold().split())


class Client:
    def __init__(self, server, scopes=None):
        self.server = server
        self.base = server['address'].rstrip('/')
        self.user = server['UserId']
        self.scopes = scopes if isinstance(scopes, dict) else {}
        self._authorized_views = None

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

    def _configured_scope(self, name):
        # Preserve the existing private scope format. A configured empty list is
        # deliberately empty; it must never widen back to the user root.
        aliases = {'episodes':'shows', 'toprated':'movies'}
        key = name if name in self.scopes else aliases.get(name)
        if key not in self.scopes:
            return None
        values = self.scopes[key]
        if not isinstance(values, list):
            raise ValueError('Invalid library scope')
        return list(dict.fromkeys(valid_id(value) for value in values))

    def _views(self):
        if self._authorized_views is None:
            response = self.get('Users/'+self.user+'/Views')
            rows = response.get('Items', []) if isinstance(response, dict) else []
            self._authorized_views = [row for row in rows if isinstance(row, dict)]
        return self._authorized_views

    def scope_ids(self, name):
        configured = self._configured_scope(name)
        base = {'episodes':'shows', 'toprated':'movies'}.get(name, name)
        if base not in SCOPE_TYPES:
            raise ValueError('Unknown library scope')
        views = []
        for row in self._views():
            try:
                item_id = valid_id(row.get('Id'))
            except ValueError:
                continue
            collection = (row.get('CollectionType') or '').casefold()
            name_key = _view_name(row.get('Name'))
            view_type = row.get('Type')
            is_untyped_media = (not collection and view_type in ('CollectionFolder', 'UserView')
                                and name_key not in NONMEDIA_VIEWS)
            is_venom = name_key.startswith('venom ')
            if base.startswith('venom_'):
                if name_key in VENOM_NAMES[base] and collection in SCOPE_TYPES[base]:
                    views.append(item_id)
            elif not is_venom and (collection in SCOPE_TYPES[base] or is_untyped_media):
                views.append(item_id)
        views = list(dict.fromkeys(views))
        # A duplicate exact Venom view is ambiguous. Owned routes may safely use
        # all classified original roots, but provider routes must fail closed.
        if base.startswith('venom_') and len(views) != 1:
            return []
        if configured is not None:
            # Private preferences may narrow the authorized/classified roots,
            # never add a provider root to an owned route (or vice versa).
            allowed = set(views)
            return [item_id for item_id in configured if item_id in allowed]
        return views

    def _items_page(self, mode, start, limit, parent=None):
        params = dict(Limit=limit, StartIndex=max(0, int(start)), Fields=FIELDS,
                      EnableTotalRecordCount='false', Recursive='true', IsMissing='false')
        if parent:
            params['ParentId'] = valid_id(parent)
        params['IncludeItemTypes'] = {
            'movies':'Movie', 'episodes':'Episode', 'toprated':'Movie'
        }[mode]
        if mode == 'toprated':
            params.update(SortBy='CommunityRating,SortName', SortOrder='Descending')
        else:
            params.update(SortBy='DateCreated,SortName', SortOrder='Descending')
        return self.get('Users/'+self.user+'/Items', **params)['Items']

    def _latest_shows(self, parent, count):
        # Jellyfin's grouped Latest query orders by the latest Episode.DateCreated
        # without scanning every Series. It can return an Episode, Season or
        # Series representative, so resolve every row back to a stable Series card.
        if count > MAX_LATEST:
            raise ValueError('Latest Shows page is too deep')
        latest = self.get('Items/Latest', UserId=self.user, ParentId=valid_id(parent),
                          IncludeItemTypes='Episode', GroupItems='true', Limit=count,
                          Fields=FIELDS+',DateLastMediaAdded')
        wanted = []
        dates = {}
        for item in latest if isinstance(latest, list) else []:
            series_id = item.get('Id') if item.get('Type') == 'Series' else item.get('SeriesId')
            try:
                series_id = valid_id(series_id)
            except ValueError:
                continue
            if series_id not in dates:
                wanted.append(series_id)
            dates[series_id] = max(dates.get(series_id, ''),
                                   item.get('DateLastMediaAdded') or item.get('DateCreated') or '')
        if not wanted:
            return []
        rows = self.get('Users/'+self.user+'/Items', Ids=','.join(wanted),
                        IncludeItemTypes='Series', Fields=FIELDS+',DateLastMediaAdded',
                        EnableTotalRecordCount='false')['Items']
        by_id = {row.get('Id'):row for row in rows if row.get('Type') == 'Series'}
        result = []
        for item_id in wanted:
            if item_id in by_id:
                row = by_id[item_id]
                row['_LatestDate'] = dates[item_id]
                result.append(row)
        return result

    @staticmethod
    def _sort_rows(mode, rows):
        rows.sort(key=lambda item:(item.get('Name','').casefold(), item.get('Id','')))
        if mode == 'toprated':
            rows.sort(key=lambda item:item.get('CommunityRating') or 0, reverse=True)
        elif mode == 'shows':
            rows.sort(key=lambda item:item.get('_LatestDate') or '', reverse=True)
        else:
            rows.sort(key=lambda item:item.get('DateCreated') or '', reverse=True)
        return rows

    def _scoped_listing(self, mode, start):
        parents = self.scope_ids(mode)
        if not parents:
            return []
        needed = max(0, int(start)) + PAGE_SIZE
        items = {}
        for parent in parents:
            if mode == 'shows':
                pages = self._latest_shows(parent, needed)
            else:
                pages = []
                for offset in range(0, needed, PAGE_SIZE):
                    size = min(PAGE_SIZE, needed-offset)
                    page = self._items_page(mode, offset, size, parent)
                    pages.extend(page)
                    if len(page) < size:
                        break
            for item in pages:
                item_id = item.get('Id')
                if item_id not in items or ((item.get('_LatestDate') or '') >
                                            (items[item_id].get('_LatestDate') or '')):
                    items[item_id] = item
        rows = self._sort_rows(mode, list(items.values()))
        return rows[start:start+PAGE_SIZE]

    def listing(self, mode, series=None, start=0):
        start = max(0, int(start))
        if mode in ('movies', 'shows', 'episodes', 'toprated'):
            return self._scoped_listing(mode, start)
        params = dict(Limit=PAGE_SIZE, StartIndex=start, Fields=FIELDS,
                      EnableTotalRecordCount='false')
        if mode == 'resume':
            # These endpoints already carry the server's authoritative per-user
            # activity rank. Re-sorting by item creation would corrupt that order.
            return self.get('Users/'+self.user+'/Items/Resume', MediaTypes='Video', **params)['Items']
        if mode == 'nextup':
            return self.get('Shows/NextUp', UserId=self.user, EnableResumable='false',
                            EnableRewatching='false', **params)['Items']
        if mode == 'series':
            params.update(Limit=100)
            return self.get('Shows/'+valid_id(series)+'/Episodes', UserId=self.user,
                            IsMissing='false', **params)['Items']
        if mode != 'favorites':
            raise ValueError('Unknown list')
        params.update(Recursive='true', IsMissing='false', IncludeItemTypes='Movie,Series,Episode',
                      Filters='IsFavorite', SortBy='SortName', SortOrder='Ascending')
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
