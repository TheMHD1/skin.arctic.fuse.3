import unittest

from upnext_policy import AUTOPLAY_POLICY, UPNEXT_COMMIT, UPNEXT_TAG, validate_policy


def settings_xml(values):
    return "<settings>" + "".join(
        '<setting id="%s">%s</setting>' % (name, value) for name, value in values.items()
    ) + "</settings>"


class UpNextPolicyTests(unittest.TestCase):
    def test_reviewed_release_pin(self):
        self.assertEqual(UPNEXT_TAG, "v1.3.0")
        self.assertEqual(len(UPNEXT_COMMIT), 40)
        int(UPNEXT_COMMIT, 16)

    def test_autoplay_policy_accepts_exact_behavior(self):
        self.assertTrue(validate_policy(settings_xml(AUTOPLAY_POLICY).encode()))

    def test_stop_cancel_playlist_and_autoplay_regressions_fail(self):
        for name, bad in {
            "autoPlayMode": "1",
            "stopAfterClose": "true",
            "enablePlaylist": "true",
            "disableNextUp": "true",
        }.items():
            values = dict(AUTOPLAY_POLICY)
            values[name] = bad
            with self.assertRaisesRegex(ValueError, name):
                validate_policy(settings_xml(values).encode())

    def test_three_episode_still_watching_boundary_is_explicit(self):
        self.assertEqual(AUTOPLAY_POLICY["playedInARow"], "3")


if __name__ == "__main__":
    unittest.main()
