"""Minimal DTO reads retain exact identity and full favourite-page artwork."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock,patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import install

def favorites():
    source=HERE.parents[1]/'plugin.video.venom.tv/shared_favorites.py'
    mod=types.ModuleType('performance_favorites')
    exec(install.overlay.transform(install.overlay.FAVORITES,source.read_bytes(),'local'),mod.__dict__)
    return mod

class Tests(unittest.TestCase):
    def test_keys_skip_images_userdata_and_totals_but_retain_identity_fields(self):
        mod=favorites();client=mod.SharedFavorites({'address':'https://example.invalid','UserId':'own-user'})
        client.request=Mock(return_value={'Items':[{'Id':'a'*32,'Type':'TvChannel','Name':'Test HD','ChannelNumber':'42'}]})
        self.assertEqual(client.keys(),{'jf:'+'a'*32,'channel:42:Test HD'})
        path=client.request.call_args.args[0];query=client.request.call_args.kwargs
        self.assertEqual(path,'Users/own-user/Items');self.assertEqual(query['Filters'],'IsFavorite')
        self.assertEqual(query['Fields'],'Path,ChannelInfo')
        for key in ('EnableImages','EnableUserData','EnableTotalRecordCount'):self.assertEqual(query[key],'false')

    def test_summary_cache_never_replaces_full_page_artwork(self):
        client=favorites().SharedFavorites({'address':'https://example.invalid','UserId':'own-user'})
        client.request=Mock(side_effect=[{'Items':[{'Id':'a'*32,'Type':'Movie','Name':'Film'}]},
            {'Items':[{'Id':'a'*32,'Type':'Movie','Name':'Film','ImageTags':{'Primary':'art'}}]}])
        client.keys();rows=client.entries();self.assertIn('/Images/Primary',rows[0]['art'])
        query=client.request.call_args.kwargs
        self.assertNotIn('EnableImages',query);self.assertNotIn('EnableUserData',query)
        self.assertFalse(client.cached_summary)

    def test_summary_paging_and_cancel_remain_bounded(self):
        client=favorites().SharedFavorites({'address':'https://example.invalid','UserId':'own-user'})
        client.request=Mock(return_value={'Items':[{'Id':'a'*32,'Type':'Movie'}]*500})
        with self.assertRaisesRegex(RuntimeError,'safe browser limit'):client.keys()
        self.assertEqual(client.request.call_count,20)
        client.request.reset_mock()
        with self.assertRaisesRegex(RuntimeError,'cancelled'):client.keys(cancelled=lambda:True)
        client.request.assert_not_called()

    def test_only_library_scope_view_call_changes_not_permission_or_sorting_logic(self):
        import ast
        source=HERE.parents[1]/'plugin.video.habibi.resume/client.py'
        before=source.read_text();after=install.overlay.transform(install.overlay.CLIENT,source.read_bytes(),'remote').decode()
        def classes(s):return {n.name:n for n in ast.parse(s).body if isinstance(n,ast.ClassDef)}
        left,right=classes(before),classes(after)
        self.assertEqual(left.keys(),right.keys())
        changes=[]
        for name in left:
            a={n.name:n for n in left[name].body if isinstance(n,ast.FunctionDef)}
            b={n.name:n for n in right[name].body if isinstance(n,ast.FunctionDef)}
            for method in a:
                if ast.dump(a[method])!=ast.dump(b[method]):changes.append(method)
        self.assertEqual(changes,['_views'])
        self.assertIn("IncludeExternalContent='false'",after)

if __name__=='__main__':unittest.main()
