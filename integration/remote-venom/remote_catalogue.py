"""Remote Venom catalogue through the signed-in Jellyfin user, never the gateway.

Instances belong to one worker request/account. No disk or cross-user cache.
"""
import re

PAGE_SIZE = 160
GENRE_PAGE_SIZE = 500
MAX_GENRES = 10000


def item_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{32}', value):
        raise ValueError('Invalid Jellyfin catalogue identity')
    return value


def media_type(kind):
    if kind not in ('movie', 'series'):
        raise ValueError('Unsupported remote catalogue kind')
    return 'Movie' if kind == 'movie' else 'Series'


class RemoteCatalogue:
    def __init__(self, shared):
        self.shared = shared
        self.parents = {}

    def request(self, path, cancelled=None, **params):
        if cancelled and cancelled():
            raise RuntimeError('Remote catalogue request cancelled')
        result = self.shared.request(path, cancelled=cancelled, **params)
        if cancelled and cancelled():
            raise RuntimeError('Remote catalogue request cancelled')
        return result

    def parent(self, kind, cancelled=None):
        media_type(kind)
        if kind not in self.parents:
            name = 'Venom Movies' if kind == 'movie' else 'Venom Series'
            views = self.request('Users/' + self.shared.user + '/Views', cancelled)['Items']
            matches = [row for row in views if row.get('Name') == name]
            if len(matches) != 1:
                raise RuntimeError('Venom library is not uniquely authorized')
            self.parents[kind] = item_id(matches[0]['Id'])
        return self.parents[kind]

    def categories(self, kind, cancelled=None):
        parent = self.parent(kind, cancelled)
        categories = {}
        for offset in range(0, MAX_GENRES + 1, GENRE_PAGE_SIZE):
            rows = self.request('Genres', cancelled, UserId=self.shared.user,
                                ParentId=parent, Recursive='true',
                                IncludeItemTypes=media_type(kind),
                                StartIndex=offset, Limit=GENRE_PAGE_SIZE,
                                SortBy='SortName', SortOrder='Ascending')['Items']
            if len(rows) > GENRE_PAGE_SIZE or (offset >= MAX_GENRES and rows):
                raise RuntimeError('Remote category response exceeds safe limit')
            for row in rows:
                name = row.get('Name') or ''
                if name.startswith('Venom: ') and name[7:].strip():
                    categories[name] = name[7:].strip()
            if len(rows) < GENRE_PAGE_SIZE:
                return [('All titles', 'all')] + [(label, name) for name, label in categories.items()]
        raise RuntimeError('Remote category response exceeds safe limit')

    def page(self, kind, category, offset=0, search='', recent=False, cancelled=None):
        wanted_type = media_type(kind)
        if type(offset) is not int or offset < 0 or offset % PAGE_SIZE:
            raise ValueError('Invalid remote catalogue offset')
        if not isinstance(search, str) or len(search) > 200:
            raise ValueError('Invalid remote catalogue search')
        if not isinstance(category, str) or (category != 'all' and not category.startswith('Venom: ')):
            raise ValueError('Invalid remote catalogue category')
        params = dict(ParentId=self.parent(kind, cancelled), Recursive='true',
                      IncludeItemTypes=wanted_type, StartIndex=offset,
                      Limit=PAGE_SIZE, SortBy='DateCreated,SortName' if recent else 'SortName',
                      SortOrder='Descending' if recent else 'Ascending',
                      Fields='Overview', EnableTotalRecordCount='true')
        if category != 'all':
            params['Genres'] = category
        if search:
            params['SearchTerm'] = search
        data = self.request('Users/' + self.shared.user + '/Items', cancelled, **params)
        rows = data['Items']
        total = data['TotalRecordCount']
        if len(rows) > PAGE_SIZE or type(total) is not int or total < 0:
            raise ValueError('Invalid remote catalogue page')
        entries = []
        for row in rows:
            ident = item_id(row['Id'])
            if row.get('Type') != wanted_type:
                raise ValueError('Unexpected remote catalogue media type')
            art = (self.shared.base + '/Items/' + ident + '/Images/Primary?maxWidth=320&quality=85'
                   if row.get('ImageTags', {}).get('Primary') else '')
            entries.append(dict(label=row['Name'], params={'mode': 'shared', 'kind': kind,
                                'id': ident, 'type': wanted_type}, art=art, folder=kind == 'series',
                                plot=row.get('Overview', ''), media='movie' if kind == 'movie' else 'tvshow',
                                metadata={}))
        if offset:
            entries.insert(0, dict(label='Previous titles', params={'mode': 'nativepage',
                                  'offset': max(0, offset-PAGE_SIZE)}, folder=True, metadata={}))
        if rows and offset + len(rows) < total:
            entries.append(dict(label='More titles…', params={'mode': 'nativepage',
                                'offset': offset+PAGE_SIZE}, folder=True, metadata={}))
        return entries
