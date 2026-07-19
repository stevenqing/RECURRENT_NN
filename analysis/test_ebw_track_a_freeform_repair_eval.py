import unittest

from analysis.ebw_track_a_v35_heldout_freeform_repair_eval import parse_freeform_patch


class TestEbwTrackAFreeformRepairEval(unittest.TestCase):
    def test_parse_freeform_literal_patch(self):
        proposal = {
            "proposal_id": "p",
            "target_residual": "literal_export_path_binding_missing",
            "patch_type": "frontier_candidate",
            "span_source": "quoted_task_path_exact",
            "target_arg": "file_path",
            "parser_policy": "strict_json_no_regex_repair",
        }
        self.assertTrue(parse_freeform_patch(proposal).ok)

    def test_reject_extra_keys(self):
        proposal = {
            "proposal_id": "p",
            "target_residual": "literal_export_path_binding_missing",
            "patch_type": "frontier_candidate",
            "span_source": "quoted_task_path_exact",
            "target_arg": "file_path",
            "parser_policy": "strict_json_no_regex_repair",
            "extra": "x",
        }
        self.assertFalse(parse_freeform_patch(proposal).ok)


if __name__ == "__main__":
    unittest.main()