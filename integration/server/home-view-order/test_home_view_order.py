import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location('tool', pathlib.Path(__file__).with_name('home_view_order.py'))
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)

class OrderTests(unittest.TestCase):
    def test_priority_unknown_tail_and_old_hidden_preserved(self):
        views = [
            {'Id':'x', 'Name':'Other', 'CollectionType':'books'}, {'Id':'s', 'Name':'Shows', 'CollectionType':'tvshows'},
            {'Id':'v', 'Name':'Venom Movies', 'CollectionType':'movies'}, {'Id':'m', 'Name':'Movies', 'CollectionType':'movies'},
            {'Id':'a', 'Name':'Shoko Anime', 'CollectionType':'tvshows'}, {'Id':'l', 'Name':'Live', 'CollectionType':'livetv'}]
        self.assertEqual(tool.desired_order(views, ['hidden', 'x', 's']), ['m','s','l','v','a','hidden','x'])
    def test_preserves_prior_unknown_permutation_without_exclusion(self):
        self.assertEqual(tool.desired_order([{'Id':'m','Name':'Movies','CollectionType':'movies'}], ['gone','m','also-gone']), ['m','gone','also-gone'])
    def test_casefold_user_selection(self):
        users = [{'Name':'Ali','Id':'1'}]
        self.assertEqual(tool.select_users(users, ['aLI'], False), users)

if __name__ == '__main__': unittest.main()
