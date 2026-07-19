import unittest

from analysis.ebw_track_a_v34_heldout_best_of_n_no_repair import aggregate_decision


class TestEbwTrackABestOfNNoRepair(unittest.TestCase):
    def test_aggregate_decision_prioritizes_safety(self):
        self.assertEqual(aggregate_decision(["abstain_no_valid", "commit_live"]), "commit_live")
        self.assertEqual(aggregate_decision(["commit_live", "unsafe_unique_wrong"]), "unsafe_unique_wrong")
        self.assertEqual(aggregate_decision(["abstain_no_valid", "ambiguous_both_valid"]), "ambiguous_both_valid")


if __name__ == "__main__":
    unittest.main()