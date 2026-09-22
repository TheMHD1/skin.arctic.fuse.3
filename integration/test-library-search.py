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
            def get(self,path,**params):
                self.calls.append((path,params))
                if 'Ids' in params:
                    return {'Items':[{'Id':key,'Name':'Spider-Man','Type':'Movie'} for key in reversed(params['Ids'].split(','))]}
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
                    def get(self,path,**params):
                        self.calls.append((path,params))
                        return {'Items':[item]}
                fake=Fake()
                self.assertEqual(search(fake,query,kind),[item])
                self.assertEqual(len(fake.calls),2)
                self.assertTrue(all(p=='Users/current-user/Items' for p,_ in fake.calls))
                self.assertEqual(fake.calls[0][1]['IncludeItemTypes'],kind)
                self.assertEqual(fake.calls[0][1]['ParentId'],('1' if kind=='Movie' else '2')*32)
                self.assertEqual(fake.calls[1][1]['Ids'],item['Id'])

    def test_default_plugin_routes_use_server_search_not_local_or_discover(self):
        import client
        entry=Path(__file__).resolve().parent/'plugin.video.habibi.resume/default.py'
        for mode, kind, title in [('searchmovies','Movie','Dune'),
                                  ('searchshows','Series','Breaking Bad'),
                                  ('searchshows','Series','رَمَضَان كريم')]:
            with self.subTest(mode=mode,title=title):
                item={'Id':'a'*32,'Name':title,'Type':kind}
                server={'address':'https://example.test','UserId':'test-user',
                        'AccessToken':'fixture-not-a-real-token','Id':'b'*32}
                calls=[]
                class FakeClient(client.Client):
                    def get(self,path,**params):
                        calls.append((path,params))
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
                        return io.StringIO(json.dumps({'movies':['1'*32],'shows':['2'*32]}))
                    raise AssertionError('Unexpected file access: '+str(path))
                argv=['plugin://plugin.video.habibi.resume/','7','?'+urlencode({'mode':mode,'query':title})]
                with mock.patch.dict(sys.modules,modules), mock.patch.object(client,'Client',FakeClient), \
                        mock.patch('builtins.open',side_effect=fixture_open), mock.patch.object(sys,'argv',argv):
                    runpy.run_path(str(entry),run_name='__main__')
                modules['xbmcplugin'].endOfDirectory.assert_called_once_with(7,cacheToDisc=False)
                self.assertEqual(len(calls),2)
                self.assertTrue(all(path=='Users/test-user/Items' for path,_ in calls))
                self.assertEqual(calls[0][1]['IncludeItemTypes'],kind)
                rows=modules['xbmcplugin'].addDirectoryItems.call_args.args[1]
                self.assertEqual(len(rows),1)
                target=urlsplit(rows[0][0])
                self.assertEqual(target.netloc,'plugin.video.habibi.resume' if kind=='Series' else 'plugin.video.jellyfin')
                self.assertEqual(parse_qs(target.query)['series' if kind=='Series' else 'id'],[item['Id']])
                modules['xbmc'].executebuiltin.assert_not_called()

    def test_skin_paths(self):
        import xml.etree.ElementTree as ET
        path=Path(__file__).resolve().parent.parent/'shortcuts/generator/data/setup/search_path.xml'
        if not path.exists():self.skipTest('not in fork checkout')
        root=ET.parse(path).getroot()
        for kind in ('Movies','TvShows'):
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
        for kind,mode in [('Movies','searchmovies'),('TvShows','searchshows')]:
            prefix=html.unescape(rules['{item_path}==DefaultSearch-'+kind])
            query='Spider-Man & رَمَضَان + Dune'
            url=prefix+urlencode({'query':query}).split('=',1)[1]
            self.assertEqual(parse_qs(urlsplit(url).query),{'mode':[mode],'query':[query]})
        for kind in ('TMDBMovies','TMDBShows'):
            target=html.unescape(rules['{item_path}==DefaultSearch-'+kind])
            self.assertEqual(urlsplit(target).netloc,'plugin.video.themoviedb.helper')
            self.assertEqual(parse_qs(urlsplit(target).query)['info'],['search'])

if __name__=='__main__':unittest.main()
