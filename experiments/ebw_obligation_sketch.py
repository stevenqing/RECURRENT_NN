"""Track A obligation-sketch parser and barrier helpers for Evidence-Bound Writes."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

TRACK_A_PATTERNS = {
    "derived_path_binding",
    "literal_intent_binding",
    "prior_effect_binding",
    "ordered_role_binding",
    "path_pair_transform_binding",
    "title_slug_export_path_binding",
    "directory_basename_archive_path_binding",
}

TYPED_REASONS = {
    "missing_read",
    "missing_prior_effect",
    "role_mismatch",
    "binding_mismatch",
    "competing_valid",
    "parse_error",
}

DERIVATIONS = {"basename", "join"}
PATH_PAIR_TRANSFORMS = {"date_prefix_basename_into_directory"}
TITLE_SLUG_TRANSFORMS = {"whitespace_to_underscore"}
TITLE_SLUG_EXTENSIONS = {".md"}
ARCHIVE_BASENAME_TRANSFORMS = {"directory_basename"}
ARCHIVE_EXTENSIONS = {".zip", ".tar"}

REQUIRED_KEYS: dict[str, set[str]] = {
    "derived_path_binding": {"obligation", "source_read_id", "source_path_field", "derivation", "target_arg"},
    "literal_intent_binding": {"obligation", "user_span", "target_arg"},
    "prior_effect_binding": {"obligation", "effect_step_id", "effect_field", "target_arg"},
    "ordered_role_binding": {"obligation", "order_source_read_id", "order_field", "index_expr", "target_arg"},
    "path_pair_transform_binding": {"obligation", "source_read_id", "source_path_field", "date_read_id", "date_field", "destination_directory_rule_id", "transform", "target_arg"},
    "title_slug_export_path_binding": {"obligation", "source_read_id", "title_field", "content_field", "destination_directory_rule_id", "slug_transform", "extension", "target_arg"},
    "directory_basename_archive_path_binding": {"obligation", "source_read_id", "source_directory_field", "destination_template_rule_id", "basename_transform", "extension", "target_arg"},
}


@dataclass(frozen=True)
class ParseOutcome:
    ok: bool
    sketch: dict[str, Any] | None
    typed_reason: str | None
    message: str | None = None


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _reference_id(value: Any) -> bool:
    return isinstance(value, int) or _nonempty_string(value)


def _validate_user_span(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {"start", "end"}:
        return False
    start, end = value["start"], value["end"]
    return isinstance(start, int) and isinstance(end, int) and 0 <= start < end


def parse_track_a_sketch(raw: str | Mapping[str, Any]) -> ParseOutcome:
    """Strictly parse a Track A sketch.

    This intentionally performs no regex extraction or schema repair. Non-JSON text,
    extra keys, missing keys, and malformed bindings fail closed with parse_error.
    """
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            return ParseOutcome(False, None, "parse_error", f"json_decode: {error.msg}")
    elif isinstance(raw, Mapping):
        value = dict(raw)
    else:
        return ParseOutcome(False, None, "parse_error", "sketch must be JSON object")

    if not isinstance(value, dict):
        return ParseOutcome(False, None, "parse_error", "sketch must be JSON object")
    obligation = value.get("obligation")
    if obligation not in TRACK_A_PATTERNS:
        return ParseOutcome(False, None, "parse_error", "unknown obligation")
    required = REQUIRED_KEYS[obligation]
    if set(value) != required:
        return ParseOutcome(False, None, "parse_error", "keys must exactly match obligation schema")
    if not _nonempty_string(value["target_arg"]):
        return ParseOutcome(False, None, "parse_error", "target_arg must be nonempty string")

    if obligation == "derived_path_binding":
        if not _reference_id(value["source_read_id"]):
            return ParseOutcome(False, None, "parse_error", "source_read_id must be reference id")
        if not _nonempty_string(value["source_path_field"]):
            return ParseOutcome(False, None, "parse_error", "source_path_field must be string")
        if value["derivation"] not in DERIVATIONS:
            return ParseOutcome(False, None, "parse_error", "invalid derivation")
    elif obligation == "literal_intent_binding":
        if not _validate_user_span(value["user_span"]):
            return ParseOutcome(False, None, "parse_error", "invalid user_span")
    elif obligation == "prior_effect_binding":
        if not _reference_id(value["effect_step_id"]):
            return ParseOutcome(False, None, "parse_error", "effect_step_id must be reference id")
        if not _nonempty_string(value["effect_field"]):
            return ParseOutcome(False, None, "parse_error", "effect_field must be string")
    elif obligation == "ordered_role_binding":
        if not _reference_id(value["order_source_read_id"]):
            return ParseOutcome(False, None, "parse_error", "order_source_read_id must be reference id")
        if not _nonempty_string(value["order_field"]):
            return ParseOutcome(False, None, "parse_error", "order_field must be string")
        if value["index_expr"] != "same_rank":
            return ParseOutcome(False, None, "parse_error", "index_expr must be same_rank")
    elif obligation == "path_pair_transform_binding":
        if not _reference_id(value["source_read_id"]):
            return ParseOutcome(False, None, "parse_error", "source_read_id must be reference id")
        if not _nonempty_string(value["source_path_field"]):
            return ParseOutcome(False, None, "parse_error", "source_path_field must be string")
        if not _reference_id(value["date_read_id"]):
            return ParseOutcome(False, None, "parse_error", "date_read_id must be reference id")
        if not _nonempty_string(value["date_field"]):
            return ParseOutcome(False, None, "parse_error", "date_field must be string")
        if not _nonempty_string(value["destination_directory_rule_id"]):
            return ParseOutcome(False, None, "parse_error", "destination_directory_rule_id must be string")
        if value["transform"] not in PATH_PAIR_TRANSFORMS:
            return ParseOutcome(False, None, "parse_error", "invalid path-pair transform")
    elif obligation == "title_slug_export_path_binding":
        if not _reference_id(value["source_read_id"]):
            return ParseOutcome(False, None, "parse_error", "source_read_id must be reference id")
        if not _nonempty_string(value["title_field"]):
            return ParseOutcome(False, None, "parse_error", "title_field must be string")
        if not _nonempty_string(value["content_field"]):
            return ParseOutcome(False, None, "parse_error", "content_field must be string")
        if not _nonempty_string(value["destination_directory_rule_id"]):
            return ParseOutcome(False, None, "parse_error", "destination_directory_rule_id must be string")
        if value["slug_transform"] not in TITLE_SLUG_TRANSFORMS:
            return ParseOutcome(False, None, "parse_error", "invalid title slug transform")
        if value["extension"] not in TITLE_SLUG_EXTENSIONS:
            return ParseOutcome(False, None, "parse_error", "invalid title slug extension")
    elif obligation == "directory_basename_archive_path_binding":
        if not _reference_id(value["source_read_id"]):
            return ParseOutcome(False, None, "parse_error", "source_read_id must be reference id")
        if not _nonempty_string(value["source_directory_field"]):
            return ParseOutcome(False, None, "parse_error", "source_directory_field must be string")
        if not _nonempty_string(value["destination_template_rule_id"]):
            return ParseOutcome(False, None, "parse_error", "destination_template_rule_id must be string")
        if value["basename_transform"] not in ARCHIVE_BASENAME_TRANSFORMS:
            return ParseOutcome(False, None, "parse_error", "invalid archive basename transform")
        if value["extension"] not in ARCHIVE_EXTENSIONS:
            return ParseOutcome(False, None, "parse_error", "invalid archive extension")
    return ParseOutcome(True, value, None, None)


def barrier_unique_validity(verifier_results: Mapping[str, bool]) -> dict[str, Any]:
    """Apply the EBW unique-validity commit rule to candidate verifier results."""
    valid = [candidate_id for candidate_id, ok in verifier_results.items() if ok]
    if len(valid) == 1:
        return {"decision": "commit", "candidate_id": valid[0], "typed_reason": None}
    if len(valid) > 1:
        return {"decision": "recur", "candidate_id": None, "typed_reason": "competing_valid"}
    return {"decision": "recur", "candidate_id": None, "typed_reason": "binding_mismatch"}


def repair_prompt_payload(typed_reason: str, failing_element_id: str) -> dict[str, str]:
    if typed_reason not in TYPED_REASONS:
        raise ValueError("unknown typed reason")
    if not _nonempty_string(failing_element_id):
        raise ValueError("failing_element_id must be nonempty")
    return {"typed_reason": typed_reason, "failing_element_id": failing_element_id}