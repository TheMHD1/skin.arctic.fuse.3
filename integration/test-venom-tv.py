"""Offline checks for catalogue navigation and live-TV seek isolation."""
import io,json,runpy,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parent

class DummyItem:
    def __init__(self,*args,**kw):self.label=kw.get('label')
    def getVideoInfoTag(self):return self
    def __getattr__(self,name):return lambda *a,**k:None

class VenomTests(unittest.TestCase):
    def load(self,query,data):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        base=Path(tmp.name);config=base/'pvr.xml'
        config.write_text('<settings><setting id="m3uUrl">http://localhost:9191/get.php?username=test&amp;password=test</setting></settings>')
        rows=[];end=[]
        modules={
            'xbmc':types.SimpleNamespace(log=lambda *a:None,LOGWARNING=2,LOGERROR=3,getSkinDir=lambda:'skin.arctic.fuse.3',getCondVisibility=lambda x:False),
            'xbmcgui':types.SimpleNamespace(ListItem=DummyItem,Dialog=lambda:types.SimpleNamespace(notification=lambda *a:None),NOTIFICATION_ERROR=3),
            'xbmcplugin':types.SimpleNamespace(addDirectoryItem=lambda h,u,i,f:rows.append((u,i.label,f)),setContent=lambda *a:None,endOfDirectory=lambda *a,**k:end.append(k),setResolvedUrl=lambda *a:None),
            'xbmcvfs':types.SimpleNamespace(translatePath=lambda p:str(config) if p.endswith('.xml') else str(base/'cache'))}
        with patch.dict(sys.modules,modules),patch.object(sys,'argv',['plugin://plugin.video.venom.tv/','1',query]),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(data).encode())):
            result=runpy.run_path(str(ROOT/'plugin.video.venom.tv/default.py'),run_name='__main__')
        return result,rows,end
    def test_categories(self):
        _,rows,_=self.load('?mode=categories&kind=movie',[{'category_name':'أفلام','category_id':'7'}])
        self.assertEqual(rows[3][1],'أفلام');self.assertTrue(rows[3][2])
        self.assertIn('category=all',rows[0][0])
    def test_pagination(self):
        _,rows,_=self.load('?mode=items&kind=movie&category=7',[{'stream_id':i,'name':str(i)} for i in range(120)])
        self.assertEqual(len(rows),103);self.assertIn('start=100',rows[-1][0]);self.assertFalse(rows[2][2])
    def test_order_search_and_recent(self):
        mod,_,_=self.load('?mode=root',[])
        data=[{'name':'Zulu','added':'bad'},{'name':'Alpha','added':'5'},{'name':'عربي','added':'10'}]
        self.assertEqual(mod['ordered'](data)[0]['name'],'Alpha')
        self.assertEqual(mod['ordered'](data,'ALP')[0]['name'],'Alpha')
        self.assertEqual(mod['ordered'](data,order='recent')[0]['name'],'عربي')
    def test_previous_page_retains_filter(self):
        _,rows,_=self.load('?mode=items&kind=movie&category=7&start=100&q=film&order=recent',[{'stream_id':i,'name':'film '+str(i),'rating':'bad'} for i in range(120)])
        self.assertEqual(rows[0][1],'Previous page')
        self.assertIn('q=film',rows[0][0]);self.assertIn('order=recent',rows[0][0])
        self.assertEqual(len(rows),21)
    def test_arabic_search_ignores_diacritics(self):
        mod,_,_=self.load('?mode=root',[])
        data=[{'name':'أَفْلام عَـرَبِيّة'},{'name':'English film'}]
        self.assertEqual(len(mod['ordered'](data,'افلام عربية')),1)
    def test_featured_has_only_thirty_titles(self):
        _,rows,_=self.load('?mode=featured&kind=movie',[{'stream_id':i,'name':'film '+str(i),'added':str(i)} for i in range(50)])
        self.assertEqual(len(rows),30)
        self.assertEqual(rows[0][1],'film 49')
        self.assertTrue(all(not row[2] for row in rows))
    def test_featured_index_is_small_and_recent(self):
        mod,_,_=self.load('?mode=root',[])
        import time
        data=[{'stream_id':i,'name':'title '+str(i),'added':str(i)} for i in range(100)]
        mod['remember_category_art']('get_vod_streams',data,time.time())
        cached=mod['featured_rows']('movie')
        self.assertEqual(len(cached),30)
        self.assertEqual(cached[0]['stream_id'],99)
    def test_reject_path_ids(self):
        mod,_,_=self.load('?mode=root',[])
        with self.assertRaises(ValueError):mod['ident']('../7')
    def test_favorite_roundtrip(self):
        mod,_,_=self.load('?mode=root',[])
        state=mod['venom_state']
        with tempfile.TemporaryDirectory() as root:
            entry={'label':'عربي','params':{'mode':'seasons','kind':'series','id':'2'}}
            self.assertTrue(state.toggle_favorite(root,'key',entry))
            self.assertEqual(state.read(root)['favorites']['key'],entry)
            self.assertFalse(state.toggle_favorite(root,'key',entry))
            self.assertEqual(state.read(root)['favorites'],{})
    def test_invalid_state_is_preserved(self):
        mod,_,_=self.load('?mode=root',[])
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'library.json';p.write_text('broken')
            with self.assertRaises(ValueError):mod['venom_state'].toggle_favorite(root,'x',{})
            self.assertEqual(p.read_text(),'broken')
    def test_live_seek_untouched(self):
        with patch.dict(sys.modules,{'xbmc':types.SimpleNamespace()}):
            seek=ROOT/'arctic-fuse-fork/integration/ugoos-osd-seek.py'
            if not seek.exists():seek=ROOT/'ugoos-osd-seek.py'
            mod=runpy.run_path(str(seek))
        action=mod['action_for']
        self.assertEqual(action(True,True,True,True,'left'),'Seek(-30)')
        self.assertEqual(action(True,True,True,True,'right',is_live=True),'Action(Right)')

if __name__=='__main__':unittest.main()
