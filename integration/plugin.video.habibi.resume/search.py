"""Permission-scoped Jellyfin title search, independent of Kodi's local sync.

Normalize punctuation/diacritics locally so 'spider man', 'Spider-Man' and
'spiderman' agree. Query only Movie/Series summaries, then hydrate one page.
No persisted catalogue or cross-user cache; current server permissions apply.
"""
import unicodedata


def words(text):
    text = unicodedata.normalize('NFKD', text or '').casefold()
    return ''.join(c if c.isalnum() else ' ' for c in text
                   if not unicodedata.combining(c) and c != '\u0640').split()


def matches(query, title):
    query_words, title_words = words(query), words(title)
    if not query_words:
        return False
    # Joined matching also handles apostrophes, hyphens and compound titles.
    return (''.join(query_words) in ''.join(title_words)
            or all(any(part in word for word in title_words) for part in query_words))


def search(client, query, kind='Movie', start=0, page_size=30):
    if kind not in ('Movie', 'Series'):
        raise ValueError('Unsupported search kind')
    if not words(query):
        return []
    if len(query) > 200:
        raise ValueError('Search is too long')
    parents = client.scopes.get('movies' if kind == 'Movie' else 'shows') or [None]
    found = {}
    for parent in parents:
        offset = 0
        while True:
            params = dict(Recursive='true', IncludeItemTypes=kind, IsMissing='false',
                          Fields='OriginalTitle', EnableImages='false',
                          EnableUserData='false', EnableTotalRecordCount='false',
                          SortBy='SortName', SortOrder='Ascending', Limit=500, StartIndex=offset)
            if parent:
                from client import valid_id
                params['ParentId'] = valid_id(parent)
            rows = client.get('Users/'+client.user+'/Items', **params)['Items']
            for item in rows:
                if matches(query, item.get('Name')) or matches(query, item.get('OriginalTitle')):
                    found[item['Id']] = item
            offset += len(rows)
            if len(rows) < 500:
                break
            if offset >= 50000:
                # Never silently present a truncated search as complete.
                raise RuntimeError('Configure Home library scopes for this large catalogue')
    results = sorted(found.values(), key=lambda i: (
        ''.join(words(i.get('Name'))) != ''.join(words(query)),
        ' '.join(words(i.get('Name'))), i['Id']))
    selected = results[max(0, start):max(0, start)+page_size]
    if not selected:
        return []
    from client import FIELDS, valid_id
    details = client.get('Users/'+client.user+'/Items',
                         Ids=','.join(valid_id(i['Id']) for i in selected),
                         Fields=FIELDS+',OriginalTitle', EnableTotalRecordCount='false')['Items']
    by_id = {i['Id']: i for i in details}
    return [by_id[i['Id']] for i in selected if i['Id'] in by_id]
