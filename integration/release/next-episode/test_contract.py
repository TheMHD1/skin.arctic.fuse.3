"""Offline contract checks for the guarded Episode -> Up Next source path."""
import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
FORK = HERE.parents[2]
KODI = FORK / "integration/release/kodi"
PATCH = FORK / "integration/patches/jellyfin-2.2.0-habibi.patch"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = load("next_episode_builder", KODI / "build.py")
load("transaction", KODI / "transaction.py")
installer = load("next_episode_installer", KODI / "install.py")


class NextEpisodeContractTests(unittest.TestCase):
    def test_patch_has_early_episode_handoff_and_safe_terminal_cases(self):
        patch = PATCH.read_text()
        self.assertIn('if item.get("Type") == "Episode" and not self.up_next:', patch)
        self.assertIn("self.up_next = bool(self.next_up())", patch)
        self.assertIn('LOG.warning("No next up episode.")', patch)
        self.assertIn('LOG.warning("Current episode absent from adjacent episode response")', patch)
        # A final episode is complete, whereas a malformed adjacent response is
        # retryable.  That distinction prevents final-episode loops.
        terminal = patch.index('LOG.warning("No next up episode.")')
        malformed = patch.index('LOG.warning("Current episode absent from adjacent episode response")')
        self.assertIn('+                    return True', patch[terminal:terminal + 180])
        self.assertIn('+            return False', patch[malformed:malformed + 150])

    def test_player_is_built_and_installed_as_the_reviewed_member(self):
        self.assertEqual(builder.OUTPUTS["jellyfin/player.py"], installer.PLAYER_OUT)
        self.assertEqual(installer.PAYLOAD_HASHES["jellyfin/player.py"], installer.PLAYER_OUT)
        target = "addons/plugin.video.jellyfin/jellyfin_kodi/player.py"
        self.assertEqual(installer.TOUCHED_OUTPUT[target], installer.PLAYER_OUT)
        self.assertEqual(installer.TOUCHED[target], {installer.PLAYER_BASE, installer.PLAYER_OUT})

    def test_pinned_player_hash_is_literal_sha256(self):
        self.assertEqual(len(installer.PLAYER_BASE), 64)
        self.assertEqual(len(installer.PLAYER_OUT), 64)
        self.assertNotEqual(installer.PLAYER_BASE, installer.PLAYER_OUT)
        for digest in (installer.PLAYER_BASE, installer.PLAYER_OUT):
            int(digest, 16)


if __name__ == "__main__":
    unittest.main()
