import unittest

from analysis.ebw_track_a_v38_heldout_no_typed_residual_prompt_manifest import build_untyped_packet


class TestEbwTrackANoTypedResidualPrompt(unittest.TestCase):
    def test_untyped_packet_excludes_typed_fields(self):
        baseline_rows = [{"instance_id": "i", "decision": "abstain_no_valid", "parse_ok": False}]
        prompt_rows = {
            "i": {
                "task_id": "t",
                "field_name": "file_path",
                "required_obligation": "derived_path_binding",
                "context": {"candidate_action": {"api_name": "create_file"}},
            }
        }
        packet = build_untyped_packet(baseline_rows, prompt_rows)
        self.assertNotIn("residual_class", packet)
        self.assertNotIn("typed_reason", packet)
        self.assertNotIn("failed_frontier", packet)
        self.assertEqual(packet["target_rows"], 1)


if __name__ == "__main__":
    unittest.main()