import runpy
import unittest
from pathlib import Path
m=runpy.run_path(str(Path(__file__).with_name('venom-sports-entertainment.py')))
class Tests(unittest.TestCase):
    def classify(self,name,cat):return m['classify']({'name':name},cat)
    def test_combat_languages_and_spanish_exclusion(self):
        for name,cat in [('ALWAN UFC 4K','|SP| ALWAN SPORTS'),('UFC FIGHT PASS','|UK| SPORTS')]:self.assertIn('sport-ufc',self.classify(name,cat))
        self.assertEqual(self.classify('ES: GLORY Kickboxing','|SP| RAKUTEN 4K'),[])
        self.assertNotIn('sport-ufc',self.classify('QR: Muhammad Ayyub','|AR| QURAN'))
    def test_football_separation_and_multisport(self):
        self.assertIn('sport-football-ar',self.classify('BEIN SPORTS 1','|SP| BEIN SPORTS VIP'))
        self.assertIn('sport-football-en',self.classify('SKY SPORTS FOOTBALL','|UK| SPORTS'))
        self.assertNotIn('sport-football-en',self.classify('NFL NETWORK','|US| SPORTS'))
        self.assertNotIn('sport-golf',self.classify('TSN 1','|CA| CANADA SPORT'))
    def test_entertainment_and_regional_fox(self):
        for name in ['HBO HD','SHOWTIME 2','CINEMAX','FOX MOVIES']:self.assertIn('en-movies',self.classify(name,'|US| USA CINEMA'))
        self.assertNotIn('en-movies',self.classify('HBO Latin','|US| USA CINEMA'))
        self.assertIn('en-movies',self.classify('PT| FOX MOVIES HD','|PT| PORTUGAL'))
    def test_new_feeds_require_success_existing_ids_preserved(self):
        old={'groups':[{'id':'en-sport','name':'English sports','channels':[{'stream_id':1,'name':'TSN 1'}]}]}
        source={'categories':[{'category_id':2,'category_name':'|UK| SPORTS'}],'channels':[{'stream_id':2,'name':'UFC FIGHT PASS','category_id':2}]}
        result=m['extend'](old,source,set(),{})
        self.assertEqual(result['unique_channels'],1)
        self.assertFalse(any(g['id']=='en-sport' for g in result['groups']))
        staged=m['extend'](old,source,set(),{},True)
        self.assertEqual(staged['unique_channels'],2)
        approved=m['extend'](old,source,{'2'},{})
        self.assertTrue(any(g['id']=='sport-ufc' for g in approved['groups']))
if __name__=='__main__':unittest.main()
