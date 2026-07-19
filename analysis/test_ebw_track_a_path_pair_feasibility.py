import unittest

from analysis.ebw_track_a_v9_path_pair_feasibility import norm_path, parse_path_rule


class TestEbwTrackAPathPairFeasibility(unittest.TestCase):
    def test_parse_path_rule_strips_sentence_punctuation(self):
        rule = parse_path_rule(
            'In my file system, add the prefix "YYYY-MM-DD_" to all file names in the ~/downloads/ directory, '
            'based on their creation dates, and then move all files not from this year to ~/trash/.'
        )
        self.assertIsNotNone(rule)
        self.assertEqual(rule["source_directory_hint"], "~/downloads")
        self.assertEqual(rule["trash_directory"], "~/trash")

    def test_norm_path_collapses_dot_segments(self):
        self.assertEqual(norm_path("~/trash/./2021-07-06_file.pdf"), "~/trash/2021-07-06_file.pdf")


if __name__ == "__main__":
    unittest.main()