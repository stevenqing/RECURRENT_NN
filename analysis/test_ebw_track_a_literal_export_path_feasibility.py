import unittest

from analysis.ebw_track_a_v23_literal_export_path_feasibility import literal_export_path_candidate, quoted_spans, valid_literal_export_path


class TestEbwTrackALiteralExportPathFeasibility(unittest.TestCase):
    def test_quoted_spans_extracts_path_and_headers(self):
        spans = quoted_spans('Export into "~/backups/spotify.csv" with headers "Title" and "Artists".')
        self.assertEqual([span["text"] for span in spans], ["~/backups/spotify.csv", "Title", "Artists"])

    def test_literal_export_path_candidate_matches_exact_path(self):
        row = {
            "context": {
                "task_text": 'Export into "~/backups/spotify.csv" with headers "Title" and "Artists".',
                "candidate_action": {"api_name": "create_file", "target_arg": "file_path", "arguments": {"file_path": "~/backups/spotify.csv"}},
            }
        }
        candidate = literal_export_path_candidate(row)
        self.assertEqual(candidate["obligation"], "literal_intent_binding")
        self.assertTrue(valid_literal_export_path("~/backups/spotify.csv", candidate))
        self.assertFalse(valid_literal_export_path("~/wrong/spotify.csv", candidate))


if __name__ == "__main__":
    unittest.main()