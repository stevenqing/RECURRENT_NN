"""Structured RepairAgent policy for v21-v28 deterministic frontier closure."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def repair_packets(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "residual_id": "R_SOURCE_PATH_IDENTITY_V21",
            "residual_class": "source_path_identity_binding_missing",
            "typed_reason": "source_path_identity_frontier_missing",
            "target_rows": artifacts["v21_source_path"]["target_rows"],
            "counterexample_summary": "destination path-pair proof cannot justify move_file.source_file_path; the source argument must be exactly bound to immutable pre-write response.path evidence",
            "failed_frontier": {"proof_family": "derived_path_binding", "binding": "destination_path_transform"},
            "accepted_frontier": {"proof_family": "source_path_identity_binding", "source_binding": "pre_write_response_path_exact", "identity_transform": "exact_path", "full_gate_after_repair": artifacts["v22_full"]["decision_counts"]},
        },
        {
            "residual_id": "R_LITERAL_EXPORT_PATH_V23",
            "residual_class": "literal_export_path_binding_missing",
            "typed_reason": "literal_task_path_span_frontier_missing",
            "target_rows": artifacts["v23_literal"]["target_rows"],
            "counterexample_summary": "Spotify CSV create_file.file_path is quoted in the task text; header-string quotes and mutated paths must not bind",
            "failed_frontier": {"proof_family": "derived_path_binding", "binding": "generic_path_derivation"},
            "accepted_frontier": {"proof_family": "literal_intent_binding", "span_source": "quoted_task_path_exact", "target_arg": "file_path", "full_gate_after_repair": artifacts["v24_full"]["decision_counts"]},
        },
        {
            "residual_id": "R_ORDERED_NOTE_TITLE_IDENTITY_V25",
            "residual_class": "ordered_note_title_identity_binding_abstain",
            "typed_reason": "ordered_note_title_content_identity_frontier_missing",
            "target_rows": artifacts["v25_note"]["target_rows"],
            "counterexample_summary": "Bucket List update_note.note_id cannot be recovered by same-rank role binding; show_note.note_id must match a Bucket List title and contain the quoted task item",
            "failed_frontier": {"proof_family": "ordered_role_binding", "binding": "same_rank_role"},
            "accepted_frontier": {"proof_family": "ordered_note_title_identity_binding", "source_binding": "show_note_response_note_id", "role_constraint": "bucket_list_title", "content_binding": "quoted_task_item_in_prewrite_content", "full_gate_after_repair": artifacts["v26_full"]["decision_counts"]},
        },
        {
            "residual_id": "R_PRIOR_EFFECT_PLAYLIST_V27",
            "residual_class": "prior_effect_playlist_id_binding_abstain",
            "typed_reason": "prior_effect_playlist_frontier_missing",
            "target_rows": artifacts["v27_prior"]["target_rows"],
            "counterexample_summary": "every add_song_to_playlist.playlist_id should bind to the earlier create_playlist.response.playlist_id prior effect; song IDs and adjacent IDs must fail",
            "failed_frontier": {"proof_family": "prior_effect_binding", "binding": "unconstrained_prior_effect_field"},
            "accepted_frontier": {"proof_family": "prior_effect_binding", "effect_binding": "create_playlist_response_playlist_id", "effect_field": "playlist_id", "full_gate_after_repair": artifacts["v28_full"]["decision_counts"]},
        },
    ]


def primitive_library() -> dict[str, Any]:
    return {
        "schema": "ebw_track_a_v29_frontier_closure_primitive_library_v1",
        "patch_templates": [
            {"id": "template.frontier_grammar.source_path_identity_binding", "patch_type": "frontier_grammar", "target_residual": "source_path_identity_binding_missing", "required_slots": ["source_binding", "identity_transform", "parser_policy"]},
            {"id": "template.frontier_candidate.literal_export_path_binding", "patch_type": "frontier_candidate", "target_residual": "literal_export_path_binding_missing", "required_slots": ["span_source", "target_arg", "parser_policy"]},
            {"id": "template.frontier_grammar.ordered_note_title_identity_binding", "patch_type": "frontier_grammar", "target_residual": "ordered_note_title_identity_binding_abstain", "required_slots": ["source_binding", "role_constraint", "content_binding", "parser_policy"]},
            {"id": "template.frontier_candidate.prior_effect_playlist_binding", "patch_type": "frontier_candidate", "target_residual": "prior_effect_playlist_id_binding_abstain", "required_slots": ["effect_binding", "effect_field", "parser_policy"]},
        ],
        "source_binding": [
            {"id": "source_binding.pre_write_response_path_exact", "value": "pre_write_response_path_exact"},
            {"id": "source_binding.destination_path_pair_transform", "value": "destination_path_pair_transform", "negative_control": True},
            {"id": "source_binding.show_note_response_note_id", "value": "show_note_response_note_id"},
            {"id": "source_binding.search_notes_same_rank", "value": "search_notes_same_rank", "negative_control": True},
        ],
        "identity_transform": [
            {"id": "identity_transform.exact_path", "value": "exact_path"},
            {"id": "identity_transform.tilde_equivalent", "value": "tilde_equivalent", "negative_control": True},
        ],
        "span_source": [
            {"id": "span_source.quoted_task_path_exact", "value": "quoted_task_path_exact"},
            {"id": "span_source.any_quoted_task_string", "value": "any_quoted_task_string", "negative_control": True},
        ],
        "target_arg": [
            {"id": "target_arg.file_path", "value": "file_path"},
            {"id": "target_arg.content", "value": "content", "negative_control": True},
        ],
        "role_constraint": [
            {"id": "role_constraint.bucket_list_title", "value": "bucket_list_title"},
            {"id": "role_constraint.any_note_title", "value": "any_note_title", "negative_control": True},
        ],
        "content_binding": [
            {"id": "content_binding.quoted_task_item_in_prewrite_content", "value": "quoted_task_item_in_prewrite_content"},
            {"id": "content_binding.output_content_contains_item", "value": "output_content_contains_item", "negative_control": True},
        ],
        "effect_binding": [
            {"id": "effect_binding.create_playlist_response_playlist_id", "value": "create_playlist_response_playlist_id"},
            {"id": "effect_binding.latest_add_song_to_playlist_response", "value": "latest_add_song_to_playlist_response", "negative_control": True},
        ],
        "effect_field": [
            {"id": "effect_field.playlist_id", "value": "playlist_id"},
            {"id": "effect_field.song_id", "value": "song_id", "negative_control": True},
        ],
        "parser_policy": [
            {"id": "parser_policy.strict", "value": "strict_json_no_regex_repair"},
            {"id": "parser_policy.tolerant_alias", "value": "tolerant_alias_repair", "negative_control": True},
        ],
    }


EXPECTED_SELECTIONS = {
    "R_SOURCE_PATH_IDENTITY_V21": {
        "template_id": "template.frontier_grammar.source_path_identity_binding",
        "selected_primitives": ["source_binding.pre_write_response_path_exact", "identity_transform.exact_path", "parser_policy.strict"],
    },
    "R_LITERAL_EXPORT_PATH_V23": {
        "template_id": "template.frontier_candidate.literal_export_path_binding",
        "selected_primitives": ["span_source.quoted_task_path_exact", "target_arg.file_path", "parser_policy.strict"],
    },
    "R_ORDERED_NOTE_TITLE_IDENTITY_V25": {
        "template_id": "template.frontier_grammar.ordered_note_title_identity_binding",
        "selected_primitives": ["source_binding.show_note_response_note_id", "role_constraint.bucket_list_title", "content_binding.quoted_task_item_in_prewrite_content", "parser_policy.strict"],
    },
    "R_PRIOR_EFFECT_PLAYLIST_V27": {
        "template_id": "template.frontier_candidate.prior_effect_playlist_binding",
        "selected_primitives": ["effect_binding.create_playlist_response_playlist_id", "effect_field.playlist_id", "parser_policy.strict"],
    },
}


def select_structured_patch(packet: dict[str, Any]) -> dict[str, Any]:
    expected = EXPECTED_SELECTIONS[packet["residual_id"]]
    return {"selection_id": "S_" + packet["residual_id"], "residual_id": packet["residual_id"], "target_residual": packet["residual_class"], **expected}


def primitive_value_map(library: dict[str, Any]) -> dict[str, tuple[str, Any]]:
    output: dict[str, tuple[str, Any]] = {}
    for group, values in library.items():
        if group in {"schema", "patch_templates"}:
            continue
        for item in values:
            output[item["id"]] = (group, item["value"])
    return output


def template_by_id(library: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {template["id"]: template for template in library["patch_templates"]}


def compile_selection(selection: dict[str, Any], residual_class: str, library: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str | None]:
    library = library or primitive_library()
    templates = template_by_id(library)
    primitive_values = primitive_value_map(library)
    template = templates.get(selection["template_id"])
    if template is None:
        return None, "unknown_template"
    if template["target_residual"] != residual_class:
        return None, "template_residual_mismatch"
    slots: dict[str, Any] = {}
    for primitive_id in selection["selected_primitives"]:
        if primitive_id not in primitive_values:
            return None, "unknown_primitive:" + primitive_id
        key, value = primitive_values[primitive_id]
        slots[key] = value
    missing = [slot for slot in template["required_slots"] if slot not in slots]
    if missing:
        return None, "missing_slots:" + ",".join(missing)
    return {
        "proposal_id": "compiled_" + selection["residual_id"],
        "target_residual": residual_class,
        "template_id": selection["template_id"],
        "patch_type": template["patch_type"],
        **slots,
    }, None


def metaverify_frontier_closure(proposal: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    target = proposal["target_residual"]
    checks = {"strict_parser_preserved": proposal.get("parser_policy") == "strict_json_no_regex_repair"}
    accepted = False
    reason = "unclassified_reject"
    if not checks["strict_parser_preserved"]:
        reason = "rejected_parser_relaxation"
    elif target == "source_path_identity_binding_missing":
        checks.update({"source_binding_ok": proposal.get("source_binding") == "pre_write_response_path_exact", "identity_transform_ok": proposal.get("identity_transform") == "exact_path", "feasibility_counts": artifacts["v21_source_path"]["decision_counts"], "full_gate": artifacts["v22_full"]["decision_counts"]})
        accepted = checks["source_binding_ok"] and checks["identity_transform_ok"] and checks["feasibility_counts"] == {"commit_live": 5}
        reason = "accepted_source_path_identity_frontier" if accepted else "rejected_source_path_identity_frontier"
    elif target == "literal_export_path_binding_missing":
        checks.update({"span_source_ok": proposal.get("span_source") == "quoted_task_path_exact", "target_arg_ok": proposal.get("target_arg") == "file_path", "feasibility_counts": artifacts["v23_literal"]["decision_counts"], "full_gate": artifacts["v24_full"]["decision_counts"]})
        accepted = checks["span_source_ok"] and checks["target_arg_ok"] and checks["feasibility_counts"] == {"commit_live": 2}
        reason = "accepted_literal_export_path_frontier" if accepted else "rejected_literal_export_path_frontier"
    elif target == "ordered_note_title_identity_binding_abstain":
        checks.update({"source_binding_ok": proposal.get("source_binding") == "show_note_response_note_id", "role_constraint_ok": proposal.get("role_constraint") == "bucket_list_title", "content_binding_ok": proposal.get("content_binding") == "quoted_task_item_in_prewrite_content", "feasibility_counts": artifacts["v25_note"]["decision_counts"], "full_gate": artifacts["v26_full"]["decision_counts"]})
        accepted = checks["source_binding_ok"] and checks["role_constraint_ok"] and checks["content_binding_ok"] and checks["feasibility_counts"] == {"commit_live": 2}
        reason = "accepted_ordered_note_title_identity_frontier" if accepted else "rejected_ordered_note_title_identity_frontier"
    elif target == "prior_effect_playlist_id_binding_abstain":
        checks.update({"effect_binding_ok": proposal.get("effect_binding") == "create_playlist_response_playlist_id", "effect_field_ok": proposal.get("effect_field") == "playlist_id", "feasibility_counts": artifacts["v27_prior"]["decision_counts"], "full_gate": artifacts["v28_full"]["decision_counts"]})
        accepted = checks["effect_binding_ok"] and checks["effect_field_ok"] and checks["feasibility_counts"] == {"commit_live": 7} and artifacts["v28_full"]["decision_counts"] == {"commit_live": 847}
        reason = "accepted_prior_effect_playlist_frontier" if accepted else "rejected_prior_effect_playlist_frontier"
    else:
        reason = "rejected_residual_family_mismatch"
    return {"proposal_id": proposal["proposal_id"], "accepted": accepted, "reason": reason, "checks": checks, "proposal": proposal}


def load_artifacts(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    paths = {
        "v21_source_path": resolve(root / "track_a_v21_source_path_identity_feasibility/feasibility.json"),
        "v22_full": resolve(root / "track_a_rescore_full_opened_v22_source_identity_merged/results.json"),
        "v23_literal": resolve(root / "track_a_v23_literal_export_path_feasibility/feasibility.json"),
        "v24_full": resolve(root / "track_a_rescore_full_opened_v24_literal_export_merged/results.json"),
        "v25_note": resolve(root / "track_a_v25_ordered_note_title_identity_feasibility/feasibility.json"),
        "v26_full": resolve(root / "track_a_rescore_full_opened_v26_ordered_note_merged/results.json"),
        "v27_prior": resolve(root / "track_a_v27_prior_effect_playlist_feasibility/feasibility.json"),
        "v28_full": resolve(root / "track_a_rescore_full_opened_v28_prior_effect_merged/results.json"),
    }
    return {key: load_json(path) for key, path in paths.items()}, {key: file_hash(path) for key, path in sorted(paths.items())}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29_frontier_closure_repair_policy"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v29 frontier closure repair policy")

    root = Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1")
    artifacts, input_hashes = load_artifacts(root)
    packets = repair_packets(artifacts)
    library = primitive_library()
    selections = [select_structured_patch(packet) for packet in packets]
    compiled = []
    results = []
    for packet, selection in zip(packets, selections):
        proposal, error = compile_selection(selection, packet["residual_class"], library)
        if proposal is None:
            compiled.append({"selection": selection, "compile_error": error})
            results.append({"proposal_id": None, "accepted": False, "reason": "compile_error", "checks": {"message": error}, "proposal": None})
        else:
            compiled.append(proposal)
            results.append(metaverify_frontier_closure(proposal, artifacts))
    status = "RPD_EBW_TRACK_A_V29_FRONTIER_CLOSURE_REPAIR_POLICY_PASS" if all(result["accepted"] for result in results) else "RPD_EBW_TRACK_A_V29_FRONTIER_CLOSURE_REPAIR_POLICY_FAIL"

    output_dir.mkdir(parents=True)
    write_json(output_dir / "repair_packets.json", {"schema": "ebw_track_a_v29_frontier_closure_repair_packets_v1", "packets": packets})
    write_json(output_dir / "primitive_library.json", library)
    write_json(output_dir / "structured_selections.json", {"schema": "ebw_track_a_v29_frontier_closure_structured_selections_v1", "rows": selections})
    write_json(output_dir / "compiled_proposals.json", {"schema": "ebw_track_a_v29_frontier_closure_compiled_proposals_v1", "rows": compiled})
    write_json(output_dir / "metaverifier_results.json", {"schema": "ebw_track_a_v29_frontier_closure_metaverifier_results_v1", "rows": results})
    payload = {
        "schema": "ebw_track_a_v29_frontier_closure_repair_policy_v1",
        "status": status,
        "processed": len(packets),
        "accepted_count": sum(1 for result in results if result["accepted"]),
        "accepted_proposals": [result["proposal_id"] for result in results if result["accepted"]],
        "v28_full_gate": artifacts["v28_full"]["decision_counts"],
        "input_hashes": input_hashes,
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "results.json", payload)
    report = [
        "# EBW Track A v29 Frontier Closure Repair Policy",
        "",
        f"## Status: **`{status}`**",
        "",
        "- Scope: CPU-only structured RepairAgent policy for v21-v28 deterministic residual closure",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Structured Selections",
        "",
        "| Residual | Template | Selected primitives | Accepted | Reason |",
        "|---|---|---|---:|---|",
    ]
    for selection, result in zip(selections, results):
        report.append(f"| `{selection['residual_id']}` | `{selection['template_id']}` | `{', '.join(selection['selected_primitives'])}` | {result['accepted']} | `{result['reason']}` |")
    report += [
        "",
        "## Interpretation",
        "",
        "The v21-v28 deterministic closure can be represented as four typed residual packets, a primitive library, deterministic compilation, and a MetaVerifier. This establishes the target for the GPU model-in-the-loop experiment: Qwen should select primitive IDs only; it should not emit free-form patch JSON.",
    ]
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "processed": len(packets), "accepted_count": payload["accepted_count"], "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()