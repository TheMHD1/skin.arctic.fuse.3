"""Permission-scoped Jellyfin title search, independent of Kodi's local sync.

Normalize punctuation/diacritics locally so 'spider man', 'Spider-Man' and
'spiderman' agree. Query only Movie/Series summaries, then hydrate one page.
No persisted catalogue or cross-user cache; current server permissions apply.
Joined-token fallback is deliberately bounded candidate discovery, not an
exhaustive punctuation-normalized catalogue scan.
"""
import unicodedata


FALLBACK_PAGE_SIZE = 100
MAX_FALLBACK_CANDIDATES = 500


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


def search(client, query, kind='Movie', start=0, page_size=30, scope=None):
    if kind not in ('Movie', 'Series'):
        raise ValueError('Unsupported search kind')
    if not words(query):
        return []
    if len(query) > 200:
        raise ValueError('Search is too long')
    scope = scope or ('movies' if kind == 'Movie' else 'shows')
    allowed = {'movies':'Movie', 'shows':'Series',
               'venom_movies':'Movie', 'venom_shows':'Series'}
    if allowed.get(scope) != kind:
        raise ValueError('Unsupported search scope')
    parents = client.scope_ids(scope)
    if not parents:
        return []
    found = {}
    fallback_candidates = 0
    query_words = words(query)
    compact_query = ''.join(query_words)
    joined_fallback = len(query_words) == 1 and len(compact_query) >= 5
    for parent in parents:
        # Jellyfin's SearchTerm keeps large provider libraries bounded. Try the
        # literal, spaced and joined spellings so punctuation-insensitive local
        # matching still handles Spider-Man / spider man / spiderman.
        terms = []
        seen_terms = set()
        for term in (query.strip(), ' '.join(words(query)), ''.join(words(query))):
            key = term.casefold()
            if key not in seen_terms:
                seen_terms.add(key)
                terms.append(term)
        from client import valid_id
        parent = valid_id(parent)
        parent_matched = False
        for term in terms:
            offset = 0
            while True:
                params = dict(Recursive='true', IncludeItemTypes=kind, IsMissing='false',
                              Fields='OriginalTitle', EnableImages='false',
                              EnableUserData='false', EnableTotalRecordCount='false',
                              SearchTerm=term, SortBy='SortName', SortOrder='Ascending',
                              Limit=500, StartIndex=offset)
                params['ParentId'] = parent
                rows = client.get('Users/'+client.user+'/Items', **params)['Items']
                for item in rows:
                    if matches(query, item.get('Name')) or matches(query, item.get('OriginalTitle')):
                        found[item['Id']] = item
                        parent_matched = True
                offset += len(rows)
                if len(rows) < 500:
                    break
                if offset >= 10000:
                    # Never silently present a truncated search as complete.
                    raise RuntimeError('Search result set is too large')
        if joined_fallback and not parent_matched:
            # A joined spelling such as SpiderMan may produce no Jellyfin
            # candidates for the literal term. Seed a bounded candidate set with
            # specific four-character anchors first. Only widen to three when the
            # whole four-character tier found no full normalized match.
            used_anchors = set(seen_terms)
            tiers = ((compact_query[:4], compact_query[-4:]),
                     (compact_query[:3], compact_query[-3:]))
            for tier in tiers:
                tier_matched = False
                for anchor in tier:
                    if anchor in used_anchors:
                        continue
                    used_anchors.add(anchor)
                    offset = 0
                    while True:
                        # Permit a one-row proof that the strict cap would be
                        # exceeded; never silently truncate a broad fallback.
                        limit = min(FALLBACK_PAGE_SIZE,
                                    MAX_FALLBACK_CANDIDATES - fallback_candidates + 1)
                        params = dict(Recursive='true', IncludeItemTypes=kind,
                                      IsMissing='false', Fields='OriginalTitle',
                                      EnableImages='false', EnableUserData='false',
                                      EnableTotalRecordCount='false', SearchTerm=anchor,
                                      SortBy='SortName', SortOrder='Ascending',
                                      Limit=limit, StartIndex=offset, ParentId=parent)
                        rows = client.get('Users/'+client.user+'/Items', **params)['Items']
                        fallback_candidates += len(rows)
                        if fallback_candidates > MAX_FALLBACK_CANDIDATES:
                            raise RuntimeError('Search too broad; try spaces between words')
                        for item in rows:
                            if (matches(query, item.get('Name'))
                                    or matches(query, item.get('OriginalTitle'))):
                                found[item['Id']] = item
                                tier_matched = True
                        offset += len(rows)
                        if len(rows) < limit:
                            break
                    if tier_matched:
                        break
                if tier_matched:
                    break
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
