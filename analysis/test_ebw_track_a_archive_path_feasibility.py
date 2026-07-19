import unittest

from analysis.ebw_track_a_v17_archive_path_feasibility import parse_archive_rule, same_user_path


class TestEbwTrackAArchivePathFeasibility(unittest.TestCase):
    def test_parse_archive_rule(self):
        rule = parse_archive_rule(
            'Compress them and save them in "~/photographs/vacations/<vacation_spot>.zip" '
            'for each vacation spot.'
        )
        self.assertIsNotNone(rule)
        self.assertEqual(rule["destination_directory"], "~/photographs/vacations")
        self.assertEqual(rule["extension"], ".zip")

    def test_same_user_path_matches_home_and_tilde(self):
        self.assertTrue(same_user_path("/home/sandra/photographs/vacations/bali/", "~/photographs/vacations/bali"))
        self.assertFalse(same_user_path("/home/sandra/photographs/vacations/miami/", "~/photographs/vacations/bali"))


if __name__ == "__main__":
    unittest.main()