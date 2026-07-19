import unittest

from analysis.ebw_track_a_v21_source_path_identity_feasibility import find_source_path_evidence, source_path_identity_candidate, valid_source_path


class TestEbwTrackASourcePathIdentityFeasibility(unittest.TestCase):
    def test_find_source_path_evidence_uses_latest_exact_path(self):
        context = {
            "pre_write_reads": [
                {"read_id": "read_1", "response": {"path": "/home/cody/downloads/a.pdf", "created_at": "2023-01-01T00:00:00"}},
                {"read_id": "read_2", "response": {"path": "/home/cody/downloads/b.pdf", "created_at": "2023-01-02T00:00:00"}},
                {"read_id": "read_3", "response": {"path": "/home/cody/downloads/a.pdf", "created_at": "2023-01-03T00:00:00"}},
            ]
        }
        evidence = find_source_path_evidence(context, "/home/cody/downloads/a.pdf")
        self.assertEqual(evidence["source_read_id"], "read_3")
        self.assertEqual(evidence["source_path_field"], "response.path")

    def test_source_path_identity_candidate_is_strict(self):
        row = {
            "context": {
                "candidate_action": {
                    "api_name": "move_file",
                    "target_arg": "source_file_path",
                    "arguments": {"source_file_path": "/home/cody/downloads/a.pdf", "destination_file_path": "~/downloads/2023-01-01_a.pdf"},
                },
                "pre_write_reads": [{"read_id": "read_1", "response": {"path": "/home/cody/downloads/a.pdf"}}],
            }
        }
        candidate = source_path_identity_candidate(row)
        self.assertEqual(candidate["obligation"], "source_path_identity_binding")
        self.assertTrue(valid_source_path("/home/cody/downloads/a.pdf", candidate))
        self.assertFalse(valid_source_path("~/downloads/a.pdf", candidate))
        self.assertFalse(valid_source_path("/home/cody/downloads/b.pdf", candidate))


if __name__ == "__main__":
    unittest.main()