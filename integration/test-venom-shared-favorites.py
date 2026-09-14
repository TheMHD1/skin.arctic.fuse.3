import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).parent/'plugin.video.venom.tv/shared_favorites.py'
spec=importlib.util.spec_from_file_location('shared',path);shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)

class Tests(unittest.TestCase):
    def client(self):return shared.SharedFavorites({'address':'http://localhost','UserId':'user-a','AccessToken':'test-token'})
    def movie(self):return {'label':'Same title','params':{'mode':'play','kind':'movie','id':'7'},'metadata':{}}
    def test_exact_managed_path_not_title(self):
        client=self.client();e=self.movie()
        right={'Id':'a'*32,'Name':'Same title','Path':'/config/venom-catalogue/movies/Movie 7/movie.strm','Type':'Movie'}
        wrong={**right,'Id':'b'*32,'Path':'/media/movies/Same title/movie.mkv'}
        client.request=lambda *args,**kwargs:{'Items':[wrong,right]}
        self.assertEqual(client.resolve(e)['Id'],'a'*32)
        self.assertNotEqual(shared.item_identity(wrong),shared.identity(e))
    def test_duplicate_exact_match_fails_closed(self):
        client=self.client();item={'Id':'a'*32,'Path':'/config/venom-catalogue/movies/Movie 7/movie.strm'}
        client.request=lambda *args,**kwargs:{'Items':[item,{**item,'Id':'b'*32}]}
        with self.assertRaises(LookupError):client.resolve(self.movie())
    def test_channel_requires_number_and_name(self):
        client=self.client();e={'label':'BBC','params':{'mode':'channel','kind':'live','id':'999'},'metadata':{'channelnumber':8}}
        rows=[{'Id':'a'*32,'Type':'TvChannel','Name':'BBC','ChannelNumber':'8'}, {'Id':'b'*32,'Type':'TvChannel','Name':'BBC','ChannelNumber':'9'}]
        client.request=lambda *args,**kwargs:{'Items':rows}
        self.assertEqual(client.resolve(e)['Id'],'a'*32)
        e['label']='BBC HD'
        with self.assertRaises(LookupError):client.resolve(e)
    def test_server_mutation_and_confirmation(self):
        client=self.client();calls=[];state={'IsFavorite':False};item={'Id':'a'*32,'UserData':state}
        client.resolve=lambda e:item
        def request(path,method='GET',**params):
            calls.append((path,method))
            if method=='POST':state['IsFavorite']=True
            if method=='DELETE':state['IsFavorite']=False
            return item
        client.request=request
        self.assertTrue(client.set(self.movie(),True));self.assertTrue(state['IsFavorite'])
        self.assertFalse(client.set(self.movie(),False));self.assertFalse(state['IsFavorite'])
        self.assertIn(('Users/user-a/FavoriteItems/'+'a'*32,'POST'),calls)
        self.assertIn(('Users/user-a/FavoriteItems/'+'a'*32,'DELETE'),calls)
    def test_missing_index_never_writes(self):
        client=self.client();calls=[]
        def request(path,method='GET',**params):calls.append(method);return {'Items':[]}
        client.request=request
        with self.assertRaises(LookupError):client.set(self.movie(),True)
        self.assertEqual(calls,['GET'])
    def test_shared_list_includes_channels_and_managed_media(self):
        client=self.client();queries=[]
        def request(path,**params):
            queries.append((path,params))
            return {'Items':[{'Id':'a'*32,'Name':'BBC','Type':'TvChannel','Number':'8'}, {'Id':'b'*32,'Name':'Movie','Type':'Movie','Path':'/config/venom-catalogue/movies/Movie 7/movie.strm'}]}
        client.request=request
        self.assertEqual(len(client.entries()),2)
        self.assertIn('channel:8:BBC',client.keys());self.assertIn('movie:7',client.keys())
        self.assertEqual(queries[0][0],'Users/user-a/Items')
        self.assertEqual(queries[0][1]['Filters'],'IsFavorite')
        self.assertIn('TvChannel',queries[0][1]['IncludeItemTypes'])
    def test_episode_identity_exact(self):
        item={'Id':'x','Path':'/config/venom-catalogue/series/Series 9/Season 02/S02E003.strm'}
        self.assertEqual(shared.item_identity(item),'episode:9:2:3')
        self.assertNotEqual(shared.item_identity({'Id':'x','Path':'/other/Series 9/Season 02/S02E003.strm'}),'episode:9:2:3')

if __name__=='__main__':unittest.main()
