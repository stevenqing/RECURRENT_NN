import unittest

from analysis.ebw_track_a_v42_hard_typed_vs_untyped_prompt_manifests import typed_packet, untyped_packet


class TestEbwTrackAHardTypedVsUntyped(unittest.TestCase):
    def test_typed_and_untyped_packets_differ(self):
        rows = [{"instance_id": "i", "decision": "abstain_no_valid", "parse_ok": True}]
        prompt_rows = {"i": {"task_id": "t", "field_name": "note_id", "required_obligation": "ordered_role_binding", "context": {"candidate_action": {"api_name": "update_note"}}}}
        typed = typed_packet(rows)
        untyped = untyped_packet(rows, prompt_rows)
        self.assertIn("residual_class", typed)
        self.assertNotIn("residual_class", untyped)
        self.assertIn("api_name_counts", untyped)


if __name__ == "__main__":
    unittest.main()