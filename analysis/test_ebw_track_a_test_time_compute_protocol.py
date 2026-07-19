import unittest

from analysis.ebw_track_a_v30_test_time_compute_freeze import frozen_files


class TestEbwTrackATestTimeComputeProtocol(unittest.TestCase):
    def test_frozen_files_includes_contract_and_components(self):
        contract = {
            "frozen_components": {"parser": "experiments/ebw_obligation_sketch.py"},
            "retrospective_replay_scope": {"purpose": "not a path", "base_gate": "results/base.json"},
        }
        files = frozen_files(contract)
        self.assertIn("specs/recurrent_parallel_ebw_test_time_compute_v1.json", files)
        self.assertIn("experiments/ebw_obligation_sketch.py", files)
        self.assertIn("results/base.json", files)
        self.assertNotIn("not a path", files)


if __name__ == "__main__":
    unittest.main()