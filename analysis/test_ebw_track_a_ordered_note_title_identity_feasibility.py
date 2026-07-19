import unittest

from analysis.ebw_track_a_v25_ordered_note_title_identity_feasibility import ordered_note_title_identity_candidate, valid_ordered_note_id


class TestEbwTrackAOrderedNoteTitleIdentityFeasibility(unittest.TestCase):
    def test_ordered_note_title_identity_candidate(self):
        row = {
            "context": {
                "task_text": 'Mark "Seeing the Northern Lights" in my Bucket List Simple Note as done.',
                "candidate_action": {"api_name": "update_note", "target_arg": "note_id", "arguments": {"note_id": 2099}},
                "pre_write_reads": [
                    {"read_id": "read_4", "response": {"note_id": 2099, "title": "My Bucket List", "content": "[ ] Seeing the Northern Lights"}}
                ],
            }
        }
        candidate = ordered_note_title_identity_candidate(row)
        self.assertEqual(candidate["obligation"], "ordered_note_title_identity_binding")
        self.assertTrue(valid_ordered_note_id(2099, candidate))
        self.assertFalse(valid_ordered_note_id(2100, candidate))


if __name__ == "__main__":
    unittest.main()