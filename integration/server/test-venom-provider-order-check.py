import runpy
from pathlib import Path
import unittest

verify=runpy.run_path(str(Path(__file__).with_name('venom-provider-order-check.py')))['verify']

class ProviderOrderTests(unittest.TestCase):
    def test_provider_order_is_not_alphabetical(self):
        groups=[{'id':'fav'}]
        rows=[{'id':'collection-fav','name':'Favourites','channelCount':3},
              {'id':'z','name':'Zebra','channelCount':1},{'id':'a','name':'Alpha','channelCount':2}]
        self.assertEqual(verify(rows,groups,['Zebra','Alpha'])['known_ordered'],2)
        with self.assertRaises(ValueError):verify([rows[0],rows[2],rows[1]],groups,['Zebra','Alpha'])
        with self.assertRaises(ValueError):verify([{**rows[0],'channelCount':0},*rows[1:]],groups,['Zebra','Alpha'])
        with self.assertRaises(ValueError):verify(rows[1:],groups,['Zebra','Alpha'])

if __name__=='__main__':unittest.main()
