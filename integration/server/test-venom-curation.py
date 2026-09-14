import runpy
from pathlib import Path
import unittest
import json

m=runpy.run_path(str(Path(__file__).with_name('venom-curate-channels.py')))
s=runpy.run_path(str(Path(__file__).with_name('venom-seed-favourites.py')))

class CurationTests(unittest.TestCase):
    def test_high_quality_variants_not_excluded_or_capped(self):
        names=['BEIN SPORTS 1 '+q for q in ['HD','FHD','4K','6K','8K','HDR','HLG']]+['BEIN 8K Match Today']
        source={'categories':[dict(category_id=1,category_name='|SP| BEIN SPORTS VIP')],
                'channels':[dict(stream_id=i,category_id=1,name=n) for i,n in enumerate(names)]}
        group=next(g for g in m['build'](source,category_limit=1)['groups'] if g['id']=='ar-sport')
        self.assertTrue(set(names[2:]).issubset({c['name'] for c in group['channels']}))
        self.assertEqual(len(group['channels']),len({c['stream_id'] for c in group['channels']}))
    def test_decoded_quality_overrides_misleading_label(self):
        rows=[{'stream_id':1,'name':'TSN 4K','decoded_width':1920,'decoded_height':1080},
              {'stream_id':2,'name':'TSN HD','decoded_width':3840,'decoded_height':2160}]
        self.assertEqual([r['stream_id'] for r in m['order_channels'](rows)],[2,1])
        self.assertEqual(m['quality_rank']({'name':'TSN 4K'}),1)
    def test_stale_failed_or_invalid_geometry_not_used(self):
        payload=json.dumps({'decoded_width':3840,'decoded_height':2160})
        now=1000000
        rows=[('ok',now,'working',payload),('old',now-8*86400,'working',payload),
              ('failed',now,'inconclusive_playback',payload),('bad',now,'working','broken')]
        self.assertEqual(set(m['fresh_geometry'](rows,now)),{'ok'})
        old={'groups':[{'id':'x','channels':[{'stream_id':1,'name':'TSN HD','decoded_width':3840,'decoded_height':2160}]}]}
        result=m['approved_additions'](old,{'groups':[]},set())
        self.assertNotIn('decoded_height',result['groups'][0]['channels'][0])
    def test_managed_override_tracks_provider_but_preserves_user_edits(self):
        plan=runpy.run_path(str(Path(__file__).with_name('venom-channel-names.py')))['planned_override']
        self.assertEqual(plan('UK: BBC HD',None,None),'BBC HD')
        self.assertIsNone(plan('BBC HD',None,None))
        self.assertEqual(plan('BBC NEWS HD','BBC HD',{'applied':'BBC HD'}),'BBC NEWS HD')
        self.assertEqual(plan('UK: BBC HD','My BBC',{'applied':'BBC HD'}),'My BBC')
        self.assertEqual(plan('UK: BBC HD','Manual',None),'Manual')
    def test_cleaned_name_resolution_preserves_number_and_rejects_collision(self):
        groups=[dict(id='sports',name='Sports',channels=[dict(name='9328 CA TSN1 FHD',num=42,stream_id=123)])]
        channel=dict(Name='TSN1 FHD',ChannelNumber='42',Id='unchanged')
        self.assertEqual(s['resolve'](groups,[channel])[0]['channels'][0]['id'],'unchanged')
        with self.assertRaises(ValueError):s['resolve'](groups,[channel,channel])
        with self.assertRaises(ValueError):s['resolve'](groups,[{**channel,'ChannelNumber':'43'}])
    def test_conservative_channel_names(self):
        policy=runpy.run_path(str(Path(__file__).with_name('venom-channel-names.py')))
        for source, expected in policy['REVIEWED'].items():
            self.assertEqual(policy['clean_name'](source), expected)
            self.assertEqual(policy['clean_name'](expected), expected)
        for source,expected in [('KD : KARAMEESH','KARAMEESH'),('748 KD : KARAMEESH','KARAMEESH'),('KD : MBC 3','MBC 3'),('KD TV','KD TV'),('KD :','KD :')]:
            self.assertEqual(s['clean_name'](source),expected)
            self.assertEqual(s['clean_name'](expected),expected)
        for source,expected in [('9328 CA TSN1 FHD','TSN1 FHD'),('5849 VIP UK Sky Sports UHD','Sky Sports UHD'),('MBC 1 HD','MBC 1 HD'),('24 NEWS','24 NEWS'),('قناة العربية HD','قناة العربية HD'),('CA','CA')]:
            self.assertEqual(s['clean_name'](source),expected)
            self.assertEqual(s['clean_name'](expected),expected)
    def test_favourite_verification_rejects_missing_or_unset_items(self):
        s['verify_favourites'](['new'],[{'Id':'new','UserData':{'IsFavorite':True}}])
        for items in [[],[{'Id':'new','UserData':{'IsFavorite':False}}],[{'Id':'other','UserData':{'IsFavorite':True}}]]:
            with self.assertRaises(RuntimeError):s['verify_favourites'](['new'],items)
    def test_quality_and_backup_order(self):
        rows=[{'name':n} for n in ['TSN HD','ESPN HD','TSN 4K','ESPN FHD','TSN FHD']]
        self.assertEqual([c['name'] for c in m['order_channels'](rows)],['TSN 4K','ESPN FHD','TSN FHD','ESPN HD','TSN HD'])

    def test_additions_require_success_and_preserve_existing(self):
        old={'groups':[{'id':'x','channels':[{'stream_id':1,'name':'TSN HD'}]}]}
        candidates={'groups':[{'id':'x','channels':[{'stream_id':2,'name':'TSN 4K'},{'stream_id':3,'name':'ESPN 4K'}]}]}
        result=m['approved_additions'](old,candidates,{'2'})
        self.assertEqual([c['stream_id'] for c in result['groups'][0]['channels']],[2,1])
        self.assertEqual(result['unique_channels'],2)

    def catalogue(self):
        groups=['|AR| NEWS الأخبار','|AR| MBC HD','|AR| SHAHID','|CA| CANAD','|AR| KIDS','|SP| BEIN SPORTS']
        names=[(0,'ALJAZEERA 4K'),(0,'ALJAZEERA HD'),(0,'ALJAZEERA ENGLISH'),(0,'ALJAZEERA DOCUMENTARY'),(1,'MBC 1 HD'),(2,'Attack on Titan'),(3,'Disney La Chaine (FR)'),(4,'MBC 3 HD'),(5,'BEIN SPORTS 1 FHD'),(5,'BEIN SPORTS 1 HD')]
        return {'categories':[dict(category_id=i,category_name=n) for i,n in enumerate(groups)],'channels':[dict(stream_id=i,category_id=g,name=n,num=i+1) for i,(g,n) in enumerate(names)]}
    def test_correct_groups_and_fallbacks(self):
        result=m['build'](self.catalogue());groups={g['id']:g for g in result['groups']}
        self.assertEqual([c['name'] for c in groups['ar-news']['channels']],['ALJAZEERA 4K','ALJAZEERA HD'])
        self.assertEqual([c['name'] for c in groups['ar-general']['channels']],['MBC 1 HD'])
        self.assertEqual([c['name'] for c in groups['ar-kids']['channels']],['MBC 3 HD'])
        self.assertEqual(len(groups['ar-sport']['channels']),2)
        self.assertEqual(groups['en-kids']['channels'],[])
        ids=[c['stream_id'] for g in result['groups'] for c in g['channels']]
        self.assertEqual(len(ids),len(set(ids)))
    def test_id_resolution_requires_exact_name_and_number(self):
        groups=[dict(id='news',name='News',channels=[dict(name='Al Jazeera',num=10,stream_id=123)])]
        channel=dict(Name='Al Jazeera',ChannelNumber='10',Id='native')
        self.assertEqual(s['resolve'](groups,[channel])[0]['channels'][0]['id'],'native')
        with self.assertRaises(ValueError):s['resolve'](groups,[channel,channel])
        with self.assertRaises(ValueError):s['resolve'](groups,[{**channel,'ChannelNumber':'11'}])

if __name__=='__main__':unittest.main()
