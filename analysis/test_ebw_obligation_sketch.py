import unittest

from experiments.ebw_obligation_sketch import barrier_unique_validity, parse_track_a_sketch, repair_prompt_payload


class TestEbwObligationSketch(unittest.TestCase):
    def test_parse_valid_track_a_patterns(self):
        examples = [
            {"obligation": "derived_path_binding", "source_read_id": "r1", "source_path_field": "source_file_path", "derivation": "basename", "target_arg": "destination_file_path"},
            {"obligation": "literal_intent_binding", "user_span": {"start": 10, "end": 15}, "target_arg": "message"},
            {"obligation": "prior_effect_binding", "effect_step_id": "w3", "effect_field": "playlist_id", "target_arg": "playlist_id"},
            {"obligation": "ordered_role_binding", "order_source_read_id": "r5", "order_field": "song_id", "index_expr": "same_rank", "target_arg": "song_id"},
            {"obligation": "path_pair_transform_binding", "source_read_id": "r1", "source_path_field": "response.path", "date_read_id": "r1", "date_field": "response.created_at", "destination_directory_rule_id": "current_year_2023_else_trash", "transform": "date_prefix_basename_into_directory", "target_arg": "destination_file_path"},
            {"obligation": "title_slug_export_path_binding", "source_read_id": "r7", "title_field": "response.title", "content_field": "response.content", "destination_directory_rule_id": "task_literal_backup_directory", "slug_transform": "whitespace_to_underscore", "extension": ".md", "target_arg": "file_path"},
            {"obligation": "directory_basename_archive_path_binding", "source_read_id": "r9", "source_directory_field": "response.2", "destination_template_rule_id": "task_literal_vacation_spot_archive_template", "basename_transform": "directory_basename", "extension": ".zip", "target_arg": "compressed_file_path"},
            {"obligation": "source_path_identity_binding", "source_read_id": "r11", "source_path_field": "response.path", "identity_transform": "exact_path", "target_arg": "source_file_path"},
            {"obligation": "ordered_note_title_identity_binding", "source_read_id": "r12", "note_id_field": "response.note_id", "title_field": "response.title", "content_field": "response.content", "task_item_span": {"start": 5, "end": 20}, "target_arg": "note_id"},
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
        self.assertFalse(parse_track_a_sketch({"obligation": "path_pair_transform_binding", "source_read_id": "r1", "source_path_field": "response.path", "date_read_id": "r1", "date_field": "response.created_at", "destination_directory_rule_id": "rule", "transform": "basename", "target_arg": "x"}).ok)
        self.assertFalse(parse_track_a_sketch({"obligation": "title_slug_export_path_binding", "source_read_id": "r1", "title_field": "response.title", "content_field": "response.content", "destination_directory_rule_id": "task_literal_backup_directory", "slug_transform": "lowercase", "extension": ".md", "target_arg": "file_path"}).ok)
        self.assertFalse(parse_track_a_sketch({"obligation": "title_slug_export_path_binding", "source_read_id": "r1", "title_field": "response.title", "content_field": "response.content", "destination_directory_rule_id": "task_literal_backup_directory", "slug_transform": "whitespace_to_underscore", "extension": ".txt", "target_arg": "file_path"}).ok)
        self.assertFalse(parse_track_a_sketch({"obligation": "directory_basename_archive_path_binding", "source_read_id": "r1", "source_directory_field": "response.0", "destination_template_rule_id": "task_literal_vacation_spot_archive_template", "basename_transform": "parent_directory", "extension": ".zip", "target_arg": "compressed_file_path"}).ok)
        self.assertFalse(parse_track_a_sketch({"obligation": "directory_basename_archive_path_binding", "source_read_id": "r1", "source_directory_field": "response.0", "destination_template_rule_id": "task_literal_vacation_spot_archive_template", "basename_transform": "directory_basename", "extension": ".rar", "target_arg": "compressed_file_path"}).ok)
        self.assertFalse(parse_track_a_sketch({"obligation": "source_path_identity_binding", "source_read_id": "r1", "source_path_field": "response.path", "identity_transform": "tilde_equivalent", "target_arg": "source_file_path"}).ok)
        self.assertFalse(parse_track_a_sketch({"obligation": "ordered_note_title_identity_binding", "source_read_id": "r1", "note_id_field": "response.note_id", "title_field": "response.title", "content_field": "response.content", "task_item_span": {"start": 4, "end": 4}, "target_arg": "note_id"}).ok)

    def test_barrier_unique_validity(self):
        self.assertEqual(barrier_unique_validity({"A": True, "B": False}), {"decision": "commit", "candidate_id": "A", "typed_reason": None})
        self.assertEqual(barrier_unique_validity({"A": True, "B": True}), {"decision": "recur", "candidate_id": None, "typed_reason": "competing_valid"})
        self.assertEqual(barrier_unique_validity({"A": False, "B": False}), {"decision": "recur", "candidate_id": None, "typed_reason": "binding_mismatch"})

    def test_repair_payload_is_typed_reason_only(self):
        self.assertEqual(repair_prompt_payload("missing_read", "read_id"), {"typed_reason": "missing_read", "failing_element_id": "read_id"})


if __name__ == "__main__":
    unittest.main()