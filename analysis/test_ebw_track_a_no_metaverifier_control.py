import unittest

from analysis.ebw_track_a_v36_heldout_no_metaverifier_control import negative_control_selections


class TestEbwTrackANoMetaVerifierControl(unittest.TestCase):
    def test_negative_controls_include_bad_slots(self):
        controls = negative_control_selections("R")
        primitive_sets = [set(control["selection"]["selected_primitives"]) for control in controls]
        self.assertIn("span_source.any_quoted_task_string", set.union(*primitive_sets))
        self.assertIn("parser_policy.tolerant_alias", set.union(*primitive_sets))


if __name__ == "__main__":
    unittest.main()