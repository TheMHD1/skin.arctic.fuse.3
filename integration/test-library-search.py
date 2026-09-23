import io, json, runpy, sys, unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlencode, urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parent/'plugin.video.habibi.resume'))
from search import matches, search

class SearchTests(unittest.TestCase):
    def test_punctuation(self):
        for query in ('spider man','Spider-Man','SPIDERMAN','spider—man'):
            self.assertTrue(matches(query,'Spider-Man: No Way Home'))
        self.assertTrue(matches('amelie','Amélie'))
        self.assertTrue(matches('رمضان','رَمَضَان'))
        self.assertFalse(matches('spider man','Superman'))
        self.assertFalse(matches('','Spider-Man'))

    def test_paginated_scope_dedupe_hydration(self):
        class Fake:
            user='own-user';scopes={'movies':['1'*32,'2'*32]}
            calls=[]
            def scope_ids(self,name):return self.scopes[name]
            def get(self,path,**params):
                self.calls.append((path,params))
                if 'Ids' in params:
                    return {'Items':[{'Id':key,'Name':'Spider-Man','Type':'Movie'} for key in reversed(params['Ids'].split(','))]}
                if params['SearchTerm'] in ('nothing','noth','hing','not','ing'):
                    return {'Items':[]}
                if params['StartIndex']==0:
                    return {'Items':[{'Id':f'{i:032x}','Name':'Unrelated'} for i in range(500)]}
                return {'Items':[{'Id':'a'*32,'Name':'Spider-Man'}, {'Id':'b'*32,'Name':'Spider-Man 2'}]}
        fake=Fake();result=search(fake,'spiderman')
        self.assertEqual([i['Id'] for i in result],['a'*32,'b'*32])
        self.assertEqual(len(fake.calls),5)
        self.assertTrue(all(p=='Users/own-user/Items' for p,_ in fake.calls))
        self.assertEqual(search(fake,'nothing'),[])

    def test_blank_does_not_fetch(self):
        class Fake: pass
        self.assertEqual(search(Fake(),'  -  '),[])

    def test_general_movie_and_series_titles(self):
        # Fixtures, not assertions that all these titles exist on a live server.
        cases = [('Movie','Dune','dune'), ('Movie','Casablanca','casablanca'),
                 ('Movie','Amélie','amelie'), ('Series','The Expanse','expanse'),
                 ('Series','Breaking Bad','breaking bad'),
                 ('Series','رَمَضَان كريم','رمضان')]
        for index, (kind, title, query) in enumerate(cases, 1):
            with self.subTest(kind=kind, query=query):
                item = {'Id':f'{index:032x}', 'Name':title, 'Type':kind}
                class Fake:
                    user='current-user'
                    scopes={'movies':['1'*32], 'shows':['2'*32]}
                    def __init__(self): self.calls=[]
                    def scope_ids(self,name):return self.scopes[name]
                    def get(self,path,**params):
                        self.calls.append((path,params))
                        return {'Items':[item]}
                fake=Fake()
                self.assertEqual(search(fake,query,kind),[item])
                self.assertGreaterEqual(len(fake.calls),2)
                self.assertTrue(all(p=='Users/current-user/Items' for p,_ in fake.calls))
                self.assertEqual(fake.calls[0][1]['IncludeItemTypes'],kind)
                self.assertEqual(fake.calls[0][1]['ParentId'],('1' if kind=='Movie' else '2')*32)
                self.assertEqual(fake.calls[-1][1]['Ids'],item['Id'])

    def test_joined_query_uses_bounded_generic_prefix_or_suffix_fallback(self):
        cases = [
            ('SpiderMan', 'spid', 'Spider-Man: No Way Home'),
            ('TheMatrix', 'trix', 'The Matrix'),
            ('NoWayHome', 'home', 'Spider-Man: No Way Home'),
        ]
        for index, (query, successful_anchor, title) in enumerate(cases, 1):
            with self.subTest(query=query):
                item = {'Id':f'{index:032x}', 'Name':title, 'Type':'Movie'}
                class Fake:
                    user='current-user'
                    def __init__(self):self.calls=[]
                    def scope_ids(self,name):return ['1'*32]
                    def get(self,path,**params):
                        self.calls.append((path,params))
                        if 'Ids' in params:
                            return {'Items':[item]}
                        return {'Items':[item] if params['SearchTerm'] == successful_anchor else []}
                fake = Fake()
                self.assertEqual(search(fake,query),[item])
                terms = [params['SearchTerm'] for _,params in fake.calls if 'SearchTerm' in params]
                self.assertIn(successful_anchor, terms)
                # Stop once a four-character anchor produced a full local match;
                # do not continue to broad three-character suffixes such as man.
                self.assertFalse(any(len(term) == 3 for term in terms))
                self.assertTrue(all(params.get('ParentId') == '1'*32
                                    for _,params in fake.calls if 'SearchTerm' in params))

    def test_joined_fallback_widens_to_three_only_after_four_tier_misses(self):
        item = {'Id':'a'*32, 'Name':'Ab-Cde', 'Type':'Movie'}
        class Fake:
            user='current-user'
            def __init__(self):self.calls=[]
            def scope_ids(self,name):return ['1'*32]
            def get(self,path,**params):
                self.calls.append(params)
                if 'Ids' in params:return {'Items':[item]}
                return {'Items':[item] if params['SearchTerm'] == 'abc' else []}
        fake=Fake()
        self.assertEqual(search(fake,'abcde'),[item])
        terms=[params['SearchTerm'] for params in fake.calls if 'SearchTerm' in params]
        self.assertEqual(terms,['abcde','abcd','bcde','abc'])

    def test_joined_fallback_fails_clearly_before_broad_catalogue_scan(self):
        class Fake:
            user='current-user'
            def __init__(self):self.calls=[]
            def scope_ids(self,name):return ['1'*32]
            def get(self,path,**params):
                self.calls.append(params)
                if params['SearchTerm'].casefold() == 'thematrix':return {'Items':[]}
                start=params['StartIndex']
                return {'Items':[{'Id':f'{start+i+1:032x}','Name':'Unrelated'}
                                 for i in range(params['Limit'])]}
        fake=Fake()
        with self.assertRaisesRegex(RuntimeError,'Search too broad; try spaces between words'):
            search(fake,'TheMatrix')
        fallback=[params for params in fake.calls if params['SearchTerm'].casefold() != 'thematrix']
        self.assertEqual(sum(len(range(params['Limit'])) for params in fallback),501)
        self.assertTrue(all(params['Limit'] <= 100 for params in fallback))
        self.assertTrue(all(params['ParentId'] == '1'*32 for params in fallback))

    def test_default_plugin_routes_use_server_search_not_local_or_discover(self):
        import client
        entry=Path(__file__).resolve().parent/'plugin.video.habibi.resume/default.py'
        for mode, kind, title, scope in [('searchmovies','Movie','Dune','1'),
                                  ('searchshows','Series','Breaking Bad','2'),
                                  ('searchshows','Series','رَمَضَان كريم','2'),
                                  ('searchvenommovies','Movie','Dune','3'),
                                  ('searchvenomshows','Series','Breaking Bad','4')]:
            with self.subTest(mode=mode,title=title):
                item={'Id':'a'*32,'Name':title,'Type':kind}
                server={'address':'https://example.test','UserId':'test-user',
                        'AccessToken':'fixture-not-a-real-token','Id':'b'*32}
                calls=[]
                class FakeClient(client.Client):
                    def get(self,path,**params):
                        calls.append((path,params))
                        if path=='Habibi/LibraryExperience/Ratings':
                            return {'items':{item['Id']:{'imdb':{'rating':8.2,'votes':1234},
                                                               'community':7.7}}}
                        if path.endswith('/Views'):
                            return {'Items':[
                                {'Id':'1'*32,'Name':'Movies','CollectionType':'movies'},
                                {'Id':'2'*32,'Name':'Shows','CollectionType':'tvshows'},
                                {'Id':'3'*32,'Name':'Venom Movies','CollectionType':'movies'},
                                {'Id':'4'*32,'Name':'Venom Series','CollectionType':'tvshows'},
                            ]}
                        return {'Items':[item]}
                    def listing(self,*args,**kwargs):
                        raise AssertionError('Library search fell through to ordinary listing')
                modules={name:mock.MagicMock() for name in ('xbmc','xbmcgui','xbmcplugin','xbmcvfs')}
                modules['xbmc'].getCondVisibility.return_value=False
                modules['xbmcvfs'].translatePath.side_effect=lambda path:path
                def fixture_open(path,*args,**kwargs):
                    if str(path).endswith('/plugin.video.jellyfin/data.json'):
                        return io.StringIO(json.dumps({'Servers':[server]}))
                    if str(path).endswith('/home-library-scopes.json'):
                        return io.StringIO(json.dumps({'movies':['1'*32],'shows':['2'*32],
                            'venom_movies':['3'*32],'venom_shows':['4'*32]}))
                    raise AssertionError('Unexpected file access: '+str(path))
                argv=['plugin://plugin.video.habibi.resume/','7','?'+urlencode({'mode':mode,'query':title})]
                with mock.patch.dict(sys.modules,modules), mock.patch.object(client,'Client',FakeClient), \
                        mock.patch('builtins.open',side_effect=fixture_open), mock.patch.object(sys,'argv',argv):
                    runpy.run_path(str(entry),run_name='__main__')
                modules['xbmcplugin'].endOfDirectory.assert_called_once_with(7,cacheToDisc=False)
                self.assertGreaterEqual(len(calls),2)
                search_calls=[call for call in calls if call[0]=='Users/test-user/Items']
                self.assertTrue(search_calls)
                self.assertEqual(search_calls[0][1]['IncludeItemTypes'],kind)
                self.assertEqual(search_calls[0][1]['ParentId'],scope*32)
                rows=modules['xbmcplugin'].addDirectoryItems.call_args.args[1]
                self.assertEqual(len(rows),1)
                target=urlsplit(rows[0][0])
                self.assertEqual(target.netloc,'plugin.video.habibi.resume' if kind=='Series' else 'plugin.video.jellyfin')
                self.assertEqual(parse_qs(target.query)['series' if kind=='Series' else 'id'],[item['Id']])
                listitem=modules['xbmcgui'].ListItem.return_value
                info=listitem.getVideoInfoTag.return_value
                info.setRating.assert_any_call(8.2,1234,'imdb',True)
                info.setRating.assert_any_call(7.7,0,'community',False)
                listitem.setProperty.assert_any_call('Habibi.Rating.IMDb','8.2')
                listitem.setProperty.assert_any_call('Habibi.Rating.Community','7.7')
                modules['xbmc'].executebuiltin.assert_not_called()

    def test_skin_paths(self):
        import xml.etree.ElementTree as ET
        path=Path(__file__).resolve().parent.parent/'shortcuts/generator/data/setup/search_path.xml'
        if not path.exists():self.skipTest('not in fork checkout')
        root=ET.parse(path).getroot()
        for kind in ('Movies','TvShows','VenomMovies','VenomShows'):
            rules={r.get('name'):next((e.findtext('value') or '' for e in r if e.findtext('condition')=='{item_path}==DefaultSearch-'+kind),'') for r in root}
            self.assertTrue(rules['widget_path'].startswith('plugin://plugin.video.habibi.resume/'))
            self.assertEqual(rules['widget_path_end'],'')

    def test_library_template_query_encoding_and_discover_separation(self):
        import html
        import xml.etree.ElementTree as ET
        path=Path(__file__).resolve().parent.parent/'shortcuts/generator/data/setup/search_path.xml'
        if not path.exists():self.skipTest('not in fork checkout')
        root=ET.parse(path).getroot()
        rules={entry.findtext('condition'):entry.findtext('value') or ''
               for group in root if group.get('name')=='widget_path' for entry in group}
        for kind,mode in [('Movies','searchmovies'),('TvShows','searchshows'),
                          ('VenomMovies','searchvenommovies'),('VenomShows','searchvenomshows')]:
            prefix=html.unescape(rules['{item_path}==DefaultSearch-'+kind])
            query='Spider-Man & رَمَضَان + Dune'
            url=prefix+urlencode({'query':query}).split('=',1)[1]
            self.assertEqual(parse_qs(urlsplit(url).query),{'mode':[mode],'query':[query]})
        for kind in ('TMDBMovies','TMDBShows'):
            target=html.unescape(rules['{item_path}==DefaultSearch-'+kind])
            self.assertEqual(urlsplit(target).netloc,'plugin.video.themoviedb.helper')
            self.assertEqual(parse_qs(urlsplit(target).query)['info'],['search'])

    def test_owned_and_venom_scopes_never_mix(self):
        class Fake:
            user='current-user'
            def __init__(self):self.calls=[]
            def scope_ids(self,name):
                return {'movies':['1'*32], 'venom_movies':['2'*32]}[name]
            def get(self,path,**params):
                self.calls.append(params)
                if 'Ids' in params:
                    return {'Items':[{'Id':params['Ids'],'Name':'Dune','Type':'Movie'}]}
                return {'Items':[{'Id':params['ParentId'],'Name':'Dune','Type':'Movie'}]}
        owned=Fake();venom=Fake()
        self.assertEqual(search(owned,'Dune',scope='movies')[0]['Id'],'1'*32)
        self.assertEqual(search(venom,'Dune',scope='venom_movies')[0]['Id'],'2'*32)
        self.assertEqual({call.get('ParentId') for call in owned.calls if 'SearchTerm' in call},{'1'*32})
        self.assertEqual({call.get('ParentId') for call in venom.calls if 'SearchTerm' in call},{'2'*32})

    def test_search_widget_sections(self):
        import json
        path=Path(__file__).resolve().parent.parent/'shortcuts/skinvariables-shortcut-searchwidgets.json'
        if not path.exists():self.skipTest('not in fork checkout')
        rows=json.loads(path.read_text())
        self.assertEqual([row['label'] for row in rows],
                         ['Movies','Shows','Venom Movies — Not HD','Venom Shows — Not HD'])
        # Discover is the skin's independent built-in selector, not another
        # library route in this generated list.

    def test_owned_discover_venom_selector_order_is_rebuild_safe(self):
        import xml.etree.ElementTree as ET
        fork=Path(__file__).resolve().parent.parent
        if not (fork/'1080i/Includes_Search.xml').exists():
            self.skipTest('not in fork checkout')
        search=ET.parse(fork/'1080i/Includes_Search.xml').getroot()
        expected=['skinvariables-searchwidgets-selector-owned','discover',
                  'skinvariables-searchwidgets-selector-venom']
        section=next(node for node in search.findall('include')
                     if node.get('name')=='Search_Switcher_Items')
        order=[]
        for node in list(section):
            if node.tag=='include' and not node.get('content'):
                order.append((node.text or '').strip())
            elif node.tag=='item' and node.findtext("property[@name='guid']")=='discover':
                order.append('discover')
        self.assertEqual(order[:3],expected)
        wall=next(node for node in search.findall('include')
                  if node.get('name')=='Search_Switcher_Wall_Items')
        wall_order=[]
        for node in list(wall):
            if node.tag=='include':wall_order.append((node.text or '').strip())
            elif node.tag=='item':wall_order.append(node.findtext("property[@name='guid']"))
        self.assertEqual(wall_order,[value.replace('searchwidgets-selector',
                                                   'searchwidgets-wall-selector')
                                     if value!='discover' else value for value in expected])
        cases={
            'search_selector.xml':('skinvariables-searchwidgets-selector-owned',
                'DefaultSearch-Movies||{item_path}==DefaultSearch-TvShows'),
            'search_selector_venom.xml':('skinvariables-searchwidgets-selector-venom',
                'DefaultSearch-VenomMovies||{item_path}==DefaultSearch-VenomShows'),
            'search_selector_wall.xml':('skinvariables-searchwidgets-wall-selector-owned',
                'DefaultSearch-Movies||{item_path}==DefaultSearch-TvShows'),
            'search_selector_wall_venom.xml':('skinvariables-searchwidgets-wall-selector-venom',
                'DefaultSearch-VenomMovies||{item_path}==DefaultSearch-VenomShows'),
        }
        base=fork/'shortcuts/generator/data/base'
        for filename,(name,guard) in cases.items():
            node=ET.parse(base/filename).getroot()
            self.assertEqual(next(value for value in node.findall('value')
                                  if value.get('name')=='includes_name').text,name)
            conditions=[value.text or '' for value in node.findall('.//condition')]
            self.assertTrue(any(guard in value for value in conditions))

    def test_poster_rating_prefers_named_sources_without_fabricating_zero(self):
        import xml.etree.ElementTree as ET
        fork=Path(__file__).resolve().parent.parent
        if not (fork/'1080i/Includes_Labels.xml').exists():
            self.skipTest('not in fork checkout')
        labels=ET.parse(fork/'1080i/Includes_Labels.xml').getroot()
        rating=next(node for node in labels.findall('variable')
                    if node.get('name')=='Label_Poster_Rating')
        values=[(node.get('condition',''),node.text or '') for node in rating.findall('value')]
        self.assertIn('Habibi.Rating.IMDb',values[0][0])
        self.assertIn('IMDb ',values[0][1])
        self.assertIn('Rating(imdb)',values[1][0])
        self.assertIn('Rating(tmdb)',values[2][0])
        self.assertIn('Property(tmdb_id)',values[3][0])
        self.assertIn('Habibi.Rating.Community',values[4][0])
        self.assertNotIn('IMDb',values[4][1])
        self.assertNotIn('0', ''.join(text for _,text in values))
        layouts=(fork/'1080i/Includes_Layouts.xml').read_text()
        self.assertIn('<include content="Object_PosterRating" />',layouts)

if __name__=='__main__':unittest.main()
