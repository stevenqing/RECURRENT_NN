import unittest

from analysis.ebw_track_a_v41_hard_target_manifest import TARGETS


class TestEbwTrackAHardTargetManifest(unittest.TestCase):
    def test_targets_include_three_hard_classes(self):
        self.assertEqual(len(set(TARGETS.values())), 3)
        self.assertIn(("move_file", "source_file_path"), TARGETS)


if __name__ == "__main__":
    unittest.main()