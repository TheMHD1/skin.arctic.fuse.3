import unittest

from state_guard import probe_eligible, restoration_permitted, restoration_plan


def snapshot(played=False, count=0, position=0, date=None, resume=None, kodi_count=0):
    return {
        "server_user_data": {
            "Played": played,
            "PlayCount": count,
            "PlaybackPositionTicks": position,
            "LastPlayedDate": date,
        },
        "kodi_resume_field": resume,
        "kodi_playcount": kodi_count,
    }


class StateGuardTests(unittest.TestCase):
    def test_exact_post_test_state_can_restore_captured_baseline(self):
        before = snapshot(False, 0, date="2026-10-28T01:00:00.0000000Z")
        after = snapshot(True, 1, date="2026-10-28T01:02:00Z")
        self.assertTrue(restoration_permitted(before, after, after))
        self.assertEqual(restoration_plan(before, after, after)["server_user_data"]["Played"], False)

    def test_concurrent_server_or_local_change_blocks_restore(self):
        before = snapshot(False, 0, date="2026-10-28T01:00:00Z")
        after = snapshot(True, 1, date="test", kodi_count=1)
        self.assertFalse(restoration_permitted(before, after, snapshot(True, 1, date="user", kodi_count=1)))
        self.assertFalse(restoration_permitted(before, after, snapshot(True, 1, date="test", kodi_count=2)))

    def test_missing_baseline_never_allows_guessing(self):
        after = snapshot(True, 1)
        self.assertFalse(restoration_permitted(None, after, after))
        self.assertIsNone(restoration_plan(None, after, after))

    def test_nullable_date_is_ineligible_before_playback(self):
        self.assertFalse(probe_eligible(snapshot(False, 0, date=None)))
        self.assertTrue(probe_eligible(snapshot(False, 0, date="2026-10-28T01:00:00.1234567Z")))

    def test_equivalent_utc_precision_does_not_block_restore(self):
        before = snapshot(False, 0, date="2026-10-28T01:00:00.1234567Z")
        after = snapshot(True, 1, date="2026-10-28T01:02:00.1000000Z")
        current = snapshot(True, 1, date="2026-10-28T01:02:00.100000Z")
        self.assertTrue(restoration_permitted(before, after, current))


if __name__ == "__main__":
    unittest.main()
