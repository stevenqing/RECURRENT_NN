import unittest

from analysis.ebw_track_a_v40_hard_pass_subset_instance_preflight import instance_id


class TestEbwTrackAHardPassSubsetPreflight(unittest.TestCase):
    def test_instance_id_is_scoped(self):
        self.assertNotEqual(instance_id("t", 1, "x"), instance_id("t", 2, "x"))
        self.assertEqual(instance_id("t", 1, "x"), instance_id("t", 1, "x"))


if __name__ == "__main__":
    unittest.main()