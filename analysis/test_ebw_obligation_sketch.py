import unittest

from experiments.ebw_obligation_sketch import barrier_unique_validity, parse_track_a_sketch, repair_prompt_payload


class TestEbwObligationSketch(unittest.TestCase):
    def test_parse_valid_track_a_patterns(self):
        examples = [
            {"obligation": "derived_path_binding", "source_read_id": "r1", "source_path_field": "source_file_path", "derivation": "basename", "target_arg": "destination_file_path"},
            {"obligation": "literal_intent_binding", "user_span": {"start": 10, "end": 15}, "target_arg": "message"},
            {"obligation": "prior_effect_binding", "effect_step_id": "w3", "effect_field": "playlist_id", "target_arg": "playlist_id"},
            {"obligation": "ordered_role_binding", "order_source_read_id": "r5", "order_field": "song_id", "index_expr": "same_rank", "target_arg": "song_id"},
        ]
        for example in examples:
            outcome = parse_track_a_sketch(example)
            self.assertTrue(outcome.ok, outcome)

    def test_parser_rejects_non_json_and_extra_keys(self):
        self.assertFalse(parse_track_a_sketch('prefix {"obligation":"literal_intent_binding"}').ok)
        outcome = parse_track_a_sketch({"obligation": "literal_intent_binding", "user_span": {"start": 1, "end": 2}, "target_arg": "message", "extra": "x"})
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.typed_reason, "parse_error")

    def test_parser_rejects_bad_bindings(self):
        self.assertFalse(parse_track_a_sketch({"obligation": "derived_path_binding", "source_read_id": "r1", "source_path_field": "p", "derivation": "parent", "target_arg": "x"}).ok)
        self.assertFalse(parse_track_a_sketch({"obligation": "literal_intent_binding", "user_span": {"start": 2, "end": 2}, "target_arg": "x"}).ok)
        self.assertFalse(parse_track_a_sketch({"obligation": "ordered_role_binding", "order_source_read_id": "r1", "order_field": "song_id", "index_expr": "first", "target_arg": "song_id"}).ok)

    def test_barrier_unique_validity(self):
        self.assertEqual(barrier_unique_validity({"A": True, "B": False}), {"decision": "commit", "candidate_id": "A", "typed_reason": None})
        self.assertEqual(barrier_unique_validity({"A": True, "B": True}), {"decision": "recur", "candidate_id": None, "typed_reason": "competing_valid"})
        self.assertEqual(barrier_unique_validity({"A": False, "B": False}), {"decision": "recur", "candidate_id": None, "typed_reason": "binding_mismatch"})

    def test_repair_payload_is_typed_reason_only(self):
        self.assertEqual(repair_prompt_payload("missing_read", "read_id"), {"typed_reason": "missing_read", "failing_element_id": "read_id"})


if __name__ == "__main__":
    unittest.main()