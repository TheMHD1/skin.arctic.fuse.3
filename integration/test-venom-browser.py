"""Offline regression checks for grid paging, remote actions and sync filtering."""
import ast
import importlib.util
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).parent

class Control:
    def __init__(self):self.items=[];self.position=0;self.label=''
    def reset(self):self.items=[];self.position=0
    def addItems(self,items):self.items.extend(items)
    def getSelectedPosition(self):return self.position
    def selectItem(self,index):self.position=index
    def setLabel(self,label):self.label=label

class Item:
    def __init__(self,label=''):self.label=label;self.properties={}
    def setArt(self,art):self.art=art
    def setProperty(self,key,value):self.properties[key]=value

class Window:
    def __init__(self):self.controls={};self.focus=910;self.kind='live';self.recent=False;self.shared=None;self.shared_keys=set()
    def getControl(self,id):return self.controls.setdefault(id,Control())
    def setFocusId(self,id):self.focus=id
    def getFocusId(self):return self.focus

class Tests(unittest.TestCase):
    def test_channel_display_cleanup_preserves_identity_and_other_titles(self):
        mod=self.load();clean=mod['channel_display_name']
        self.assertEqual(clean('9328 CA TSN1 FHD'),'TSN1 FHD')
        self.assertEqual(clean('5849 VIP UK: SKY SPORTS 1 4K'),'SKY SPORTS 1 4K')
        for name in ['24 NEWS HD','MBC 1 HD','360 العربية','BBC UK NEWS']:
            self.assertEqual(clean(name),name)
        b=mod['Browser']();b.page=0;b.query='';b.category_name='Favourites'
        live=mod['entry']('9328 CA TSN1 FHD',{'kind':'live','mode':'channel','id':'7'})
        movie=mod['entry']('VIP UK Story',{'kind':'movie','id':'8'})
        b.entries=[live,movie];b.render()
        # User confirmed Kodi names already work; don't add a second cosmetic
        # rename layer while deploying the missing category navigation.
        self.assertEqual([i.label for i in b.getControl(920).items],['9328 CA TSN1 FHD','VIP UK Story'])
        self.assertEqual(live['label'],'9328 CA TSN1 FHD')
        self.assertEqual(live['params']['id'],'7')
    def test_curated_groups_pinned_provider_rank_preserved(self):
        choices=self.load()['live_group_choices'](
            [{'label':'Tunisia','channelgroupid':1},{'label':'Arabic News','channelgroupid':2}],
            [{'id':'collection-news','name':'أخبار'},{'id':'category-a','name':'Arabic News'},{'id':'category-t','name':'Tunisia'}])
        self.assertEqual(choices,[('أخبار','jf:collection-news'),('All channels','alltv'),('Arabic News','jf:category-a'),('Tunisia','jf:category-t')])
    def test_provider_groups_do_not_require_pvr_import(self):
        mod=self.load()
        self.assertEqual(mod['live_group_choices']([],[{'id':'category-a','name':'Arabic News'}]),[('All channels','alltv'),('Arabic News','jf:category-a')])
    def test_curated_entries_use_existing_shared_channel_playback(self):
        mod=self.load();b=mod['Browser']();b.kind='live';b.category='jf:collection-news'
        b.shared=types.SimpleNamespace(request=lambda *a,**k:{'Items':[{'Name':'News','Id':'native','ChannelNumber':'10'}],'TotalRecordCount':1})
        row=b.fetch_entries()[0]
        self.assertEqual(row['params'],{'mode':'shared','kind':'live','id':'native','type':'TvChannel'})
    def load(self):
        cat=types.SimpleNamespace(ROOT='unused',search_text=lambda x:str(x).casefold(),favorite_key=lambda x:str(x),venom_state=types.SimpleNamespace(read=lambda p:{'favorites':{}}))
        modules={'default':cat,'xbmc':types.SimpleNamespace(log=lambda *a:None,LOGINFO=1,LOGERROR=3),'xbmcgui':types.SimpleNamespace(WindowXML=Window,ListItem=Item)}
        with patch.dict(sys.modules,modules):
            result=runpy.run_path(str(ROOT/'plugin.video.venom.tv/browser.py'))
        return result
    def test_page_bounded_and_clamped(self):
        mod=self.load();b=mod['Browser']();b.kind='live';b.page=999;b.query='';b.category_name='All'
        b.source_entries=lambda:[mod['entry']('Channel '+str(i),{'kind':'live','id':str(i)}) for i in range(165)]
        b.load_entries();self.assertEqual(b.page,2);self.assertEqual(len(b.getControl(920).items),5)
        b.page=0;b.render();self.assertEqual(len(b.getControl(920).items),80)
    def test_search_and_empty_results(self):
        mod=self.load();b=mod['Browser']();b.page=0;b.query='arabic';b.category_name='All'
        b.source_entries=lambda:[mod['entry']('Arabic News',{}),mod['entry']('Sport',{})]
        b.load_entries();self.assertEqual(len(b.entries),1)
        b.query='missing';b.load_entries();self.assertEqual(b.entries,[])
    def test_arabic_preserved_emoji_removed(self):
        clean=self.load()['clean_label']
        self.assertEqual(clean('⚽  العربية \ufe0f'),'العربية')
    def test_grid_star_uses_server_favourite_identity(self):
        mod=self.load();b=mod['Browser']();b.page=0;b.query='';b.category_name='Movies'
        b.entries=[mod['entry']('Movie',{'mode':'play','kind':'movie','id':'7'})]
        b.shared=types.SimpleNamespace(keys=lambda:(_ for _ in ()).throw(AssertionError('render contacted server')))
        b.shared_keys={'movie:7'}
        b.render();self.assertEqual(b.getControl(920).items[0].properties['venom.favorite'],'true')
        b.shared_keys=set()
        b.render();self.assertEqual(b.getControl(920).items[0].properties['venom.favorite'],'false')
    def test_category_cache_reuses_search_source(self):
        from collections import OrderedDict
        mod=self.load();b=mod['Browser']();b.kind='movie';b.category='all';b.scope=None;b.source_cache=OrderedDict()
        calls=[]
        b.fetch_entries=lambda:(calls.append(True) or [mod['entry']('A',{})])
        self.assertEqual(b.source_entries(),b.source_entries());self.assertEqual(len(calls),1)
        b.category='new';b.source_entries();self.assertEqual(len(calls),2)
    def test_shared_series_not_truncated_at_500(self):
        mod=self.load();b=mod['Browser']();b.kind='series';b.scope={'jf_series':'s'};b.closed=False
        offsets=[]
        def request(path,**params):
            offsets.append(params['StartIndex'])
            return {'Items':[{'Name':'Episode','Id':str(i)} for i in range(500 if params['StartIndex']==0 else 1)]}
        b.shared=types.SimpleNamespace(user='u',request=request)
        self.assertEqual(len(b.fetch_entries()),501);self.assertEqual(offsets,[0,500])
    def test_exclusion_boundaries_and_whitelist(self):
        source=ast.parse((ROOT/'venom-jellyfin-library.py').read_text())
        function=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='excluded_stream_item')
        namespace={};exec(compile(ast.Module(body=[function],type_ignores=[]),'test','exec'),namespace)
        excluded=namespace['excluded_stream_item'];policy={'Whitelist':[],'ExcludedLibraryPaths':{'/config/venom/series':'iptv'}}
        self.assertTrue(excluded({'Type':'Season','Path':'/config/venom/series/show/season'},policy))
        self.assertFalse(excluded({'Path':'/config/venom/series-other/show'},policy))
        self.assertFalse(excluded({'Path':'/media/shows/a'},policy))
        self.assertFalse(excluded({},policy))
        policy['Whitelist']=['Mixed:iptv'];self.assertFalse(excluded({'Path':'/config/venom/series/show'},policy))
    def test_xml_navigation_ids_exist(self):
        import xml.etree.ElementTree as ET
        root=ET.parse(ROOT/'plugin.video.venom.tv/resources/skins/Default/1080i/VenomBrowser.xml').getroot()
        ids=[e.get('id') for e in root.iter('control') if e.get('id')]
        self.assertEqual(len(ids),len(set(ids)))
        for control in root.iter('control'):
            for tag in ('onleft','onright','onup','ondown'):
                action=control.findtext(tag)
                if action and action.isdigit():self.assertIn(action,ids)

if __name__=='__main__':unittest.main()
