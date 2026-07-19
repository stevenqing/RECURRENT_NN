import unittest

from analysis.ebw_track_a_v29_frontier_closure_repair_policy import compile_selection, metaverify_frontier_closure, primitive_library


class TestEbwTrackAFrontierClosureRepairPolicy(unittest.TestCase):
    def test_compile_source_path_selection_requires_strict_parser(self):
        selection = {
            "residual_id": "R_SOURCE_PATH_IDENTITY_V21",
            "template_id": "template.frontier_grammar.source_path_identity_binding",
            "selected_primitives": ["source_binding.pre_write_response_path_exact", "identity_transform.exact_path", "parser_policy.strict"],
        }
        proposal, error = compile_selection(selection, "source_path_identity_binding_missing", primitive_library())
        self.assertIsNone(error)
        self.assertEqual(proposal["source_binding"], "pre_write_response_path_exact")

    def test_metaverifier_rejects_parser_relaxation(self):
        proposal = {
            "proposal_id": "control",
            "target_residual": "source_path_identity_binding_missing",
            "template_id": "template.frontier_grammar.source_path_identity_binding",
            "patch_type": "frontier_grammar",
            "source_binding": "pre_write_response_path_exact",
            "identity_transform": "exact_path",
            "parser_policy": "tolerant_alias_repair",
        }
        result = metaverify_frontier_closure(proposal, {})
        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"], "rejected_parser_relaxation")


if __name__ == "__main__":
    unittest.main()