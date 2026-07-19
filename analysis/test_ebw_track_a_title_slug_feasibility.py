import unittest

from analysis.ebw_track_a_v11_title_slug_feasibility import find_show_note_evidence, parse_export_rule, slug_title


class TestEbwTrackATitleSlugFeasibility(unittest.TestCase):
    def test_slug_title_replaces_whitespace_runs(self):
        self.assertEqual(slug_title(" Habit  Tracking Log "), "Habit_Tracking_Log")

    def test_parse_export_rule(self):
        rule = parse_export_rule(
            'Export all my Simple Note notes to "~/backups/simple_note/" directory in my file system. '
            'The files should be named according to the note title, replacing white space with "_", '
            'and the extension should be ".md".'
        )
        self.assertIsNotNone(rule)
        self.assertEqual(rule["destination_directory"], "~/backups/simple_note")
        self.assertEqual(rule["extension"], ".md")
        self.assertEqual(rule["slug_transform"], "whitespace_to_underscore")

    def test_find_show_note_evidence_uses_latest_matching_content(self):
        context = {
            "pre_write_reads": [
                {"read_id": "read_1", "response": {"title": "Older", "content": "same"}},
                {"read_id": "read_2", "response": {"title": "Newer", "content": "same"}},
            ]
        }
        evidence = find_show_note_evidence(context, "same")
        self.assertEqual(evidence["source_read_id"], "read_2")


if __name__ == "__main__":
    unittest.main()