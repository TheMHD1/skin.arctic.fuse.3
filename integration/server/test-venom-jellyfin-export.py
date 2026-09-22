import runpy
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
from unittest.mock import patch

M=runpy.run_path(str(Path(__file__).with_name('venom-jellyfin-export.py')))

class ExportTests(unittest.TestCase):
    def test_multiple_provider_categories(self):
        names=M['category_names']({'category_id':'1','category_ids':[1,'2','3']},{'1':'Drama','2':'رمضان'})
        self.assertEqual(names,['Drama','رمضان'])
        root=ET.fromstring(M['nfo']('tvshow',{'name':'Show'},names))
        self.assertEqual([x.text for x in root.findall('genre')],['Venom: Drama','Venom: رمضان'])
        self.assertEqual(M['category_names']({'category_ids':2},{'2':'Action'}),['Action'])
    def test_safe_nfo_and_categories(self):
        raw=M['nfo']('movie',{'name':'أفلام & <Film>\x00','rating':'bad','year':'2026','genre':'Drama, Action'},'Arabic')
        root=ET.fromstring(raw)
        self.assertEqual(root.findtext('title'),'أفلام & <Film>')
        self.assertEqual([x.text for x in root.findall('genre')],['Drama','Action','Venom: Arabic'])
        self.assertIsNone(root.find('rating'))
    def test_atomic_noop(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'movie.nfo'
            self.assertTrue(M['atomic'](path,b'one'))
            stamp=path.stat().st_mtime_ns
            self.assertFalse(M['atomic'](path,b'one'))
            self.assertEqual(stamp,path.stat().st_mtime_ns)
            self.assertTrue(M['atomic'](path,b'two'))
            self.assertEqual(path.read_bytes(),b'two')
    def test_dirty_generation_only_changes_with_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'catalogue';config=Path(folder)/'config'
            with patch.dict(M['atomic'].__globals__,ROOT=root,CONFIG=config,DIRTY_MARKED=set()):
                path=root/'movies'/'Movie 1'/'movie.nfo'
                M['atomic'](path,b'one');marker=config/'refresh-dirty-movies';first=marker.read_text()
                M['atomic'](path,b'two');self.assertEqual(marker.read_text(),first)
                M['atomic'].__globals__['DIRTY_MARKED'].clear()
                self.assertFalse(M['atomic'](path,b'two'));self.assertEqual(marker.read_text(),first)
                M['atomic'](path,b'three');self.assertNotEqual(marker.read_text(),first)
    def test_stream_route_validation(self):
        auth={'username':'user','password':'a/b'}
        self.assertIn('/movie/user/a%2Fb/12.mp4',M['stream_url'](auth,'movie',12,'mp4'))
        with self.assertRaises(ValueError):M['stream_url'](auth,'movie','../12','mp4')
        with self.assertRaises(ValueError):M['stream_url'](auth,'movie',12,'mp4\nhttp://other')
    def test_episode_numbers(self):
        root=ET.fromstring(M['nfo']('episodedetails',{'title':'episode'},season=0,episode=12))
        self.assertEqual(root.findtext('season'),'0');self.assertEqual(root.findtext('episode'),'12')

if __name__=='__main__':unittest.main()
