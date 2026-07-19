import unittest

from analysis.ebw_track_a_v27_prior_effect_playlist_feasibility import prior_effect_playlist_candidate, valid_prior_effect_value


class TestEbwTrackAPriorEffectPlaylistFeasibility(unittest.TestCase):
    def test_prior_effect_playlist_candidate(self):
        row = {
            "context": {
                "candidate_action": {"api_name": "add_song_to_playlist", "target_arg": "playlist_id", "arguments": {"playlist_id": 654, "song_id": 73}},
                "prior_effects": [
                    {"effect_step_id": "effect_2", "api_name": "login", "response": {}},
                    {"effect_step_id": "effect_13", "api_name": "create_playlist", "response": {"playlist_id": 654}},
                ],
            }
        }
        candidate = prior_effect_playlist_candidate(row)
        self.assertEqual(candidate["obligation"], "prior_effect_binding")
        self.assertEqual(candidate["effect_step_id"], "effect_13")
        self.assertTrue(valid_prior_effect_value(654, candidate))
        self.assertFalse(valid_prior_effect_value(73, candidate))


if __name__ == "__main__":
    unittest.main()