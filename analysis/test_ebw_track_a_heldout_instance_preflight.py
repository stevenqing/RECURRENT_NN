import unittest

from analysis.ebw_track_a_v31_heldout_instance_preflight import instance_id


class TestEbwTrackAHeldoutInstancePreflight(unittest.TestCase):
    def test_instance_id_is_stable_and_heldout_scoped(self):
        self.assertEqual(instance_id("task_10", 3, "file_path"), instance_id("task_10", 3, "file_path"))
        self.assertNotEqual(instance_id("task_10", 3, "file_path"), instance_id("task_10", 4, "file_path"))


if __name__ == "__main__":
    unittest.main()