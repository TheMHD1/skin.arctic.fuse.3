import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('identity_naming', Path(__file__).with_name('identity-naming.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class IdentityNamingTests(unittest.TestCase):
    def test_only_future_folder_field_changes(self):
        for app, (field, value, _) in mod.POLICY.items():
            before = {field: 'old', 'id': 1, 'renameEpisodes': True, 'custom': {'untouched': 1}}
            after = mod.desired(app, before)
            self.assertEqual(after[field], value)
            self.assertEqual(before[field], 'old')
            self.assertEqual({k:v for k,v in after.items() if k != field},
                             {k:v for k,v in before.items() if k != field})

    def test_provider_tokens_are_native_not_title_guesses(self):
        self.assertIn('[tvdbid-{TvdbId}]', mod.POLICY['sonarr'][1])
        self.assertIn('[tmdbid-{TmdbId}]', mod.POLICY['radarr'][1])
        self.assertIn('TitleYear', mod.POLICY['sonarr'][1])
        self.assertIn('Release Year', mod.POLICY['radarr'][1])

if __name__ == '__main__':
    unittest.main()
