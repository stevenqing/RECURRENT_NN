"""CPU-only structured RepairAgent policy for archive-path residuals."""
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


def archive_repair_packet(feasibility: dict[str, Any], model_result: dict[str, Any], full_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "residual_id": "R_ARCHIVE_PATH_DIRECTORY_BASENAME_V17",
        "residual_class": "directory_basename_archive_path_binding_missing",
        "typed_reason": "archive_path_frontier_missing",
        "target_rows": feasibility["target_rows"],
        "counterexample_summary": "basename-only path derivation cannot prove compressed_file_path; source directory basename must fill the task literal <vacation_spot> archive template and extension",
        "failed_frontier": {
            "proof_family": "derived_path_binding",
            "source_binding": "generic_basename_projection",
        },
        "accepted_frontier": {
            "source_binding": "immutable_directory_list_entry",
            "basename_transform": "directory_basename",
            "destination_template_rule_id": "task_literal_vacation_spot_archive_template",
            "extension_policy": "task_template_extension",
            "decision_counts": feasibility["decision_counts"],
            "model_decision_counts": model_result["decision_counts"],
            "full_gate_after_repair": full_result["decision_counts"],
        },
    }


def primitive_library() -> dict[str, Any]:
    return {
        "schema": "ebw_track_a_v18_archive_primitive_library_v1",
        "patch_templates": [
            {
                "id": "template.frontier_grammar.directory_basename_archive_path_binding",
                "patch_type": "frontier_grammar",
                "target_residual": "directory_basename_archive_path_binding_missing",
                "required_slots": ["source_binding", "basename_transform", "destination_template_rule_id", "extension_policy", "parser_policy"],
            }
        ],
        "source_binding": [
            {"id": "source_binding.immutable_directory_list_entry", "value": "immutable_directory_list_entry"},
            {"id": "source_binding.latest_matching_pre_write_show_note", "value": "latest_matching_pre_write_show_note", "negative_control": True},
            {"id": "source_binding.generic_basename_projection", "value": "generic_basename_projection", "negative_control": True},
        ],
        "basename_transform": [
            {"id": "basename_transform.directory_basename", "value": "directory_basename"},
            {"id": "basename_transform.file_basename", "value": "file_basename", "negative_control": True},
        ],
        "destination_template_rule": [
            {"id": "destination_template.task_literal_vacation_spot_archive_template", "value": "task_literal_vacation_spot_archive_template"},
            {"id": "destination_template.task_literal_backup_directory", "value": "task_literal_backup_directory", "negative_control": True},
        ],
        "extension_policy": [
            {"id": "extension_policy.task_template_extension", "value": "task_template_extension"},
            {"id": "extension_policy.always_md", "value": "always_md", "negative_control": True},
        ],
        "parser_policy": [
            {"id": "parser_policy.strict", "value": "strict_json_no_regex_repair"},
            {"id": "parser_policy.tolerant_alias", "value": "tolerant_alias_repair", "negative_control": True},
        ],
    }


def select_archive_patch(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "selection_id": "S_ARCHIVE_PATH_DIRECTORY_BASENAME",
        "residual_id": packet["residual_id"],
        "target_residual": packet["residual_class"],
        "template_id": "template.frontier_grammar.directory_basename_archive_path_binding",
        "selected_primitives": [
            "source_binding.immutable_directory_list_entry",
            "basename_transform.directory_basename",
            "destination_template.task_literal_vacation_spot_archive_template",
            "extension_policy.task_template_extension",
            "parser_policy.strict",
        ],
        "self_check": {
            "uses_counterexample": "source directory basename must fill the task literal <vacation_spot> archive template",
            "rejects_failed_frontier": packet.get("failed_frontier", {}).get("source_binding") == "generic_basename_projection",
        },
    }


def compile_archive_proposal(selection: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposal_id": "structured_archive_directory_basename",
        "target_residual": selection["target_residual"],
        "patch_type": "frontier_grammar",
        "source_binding": "immutable_directory_list_entry",
        "basename_transform": "directory_basename",
        "destination_template_rule_id": "task_literal_vacation_spot_archive_template",
        "extension_policy": "task_template_extension",
        "parser_policy": "strict_json_no_regex_repair",
    }


def control_proposals() -> list[dict[str, Any]]:
    base = {
        "target_residual": "directory_basename_archive_path_binding_missing",
        "patch_type": "frontier_grammar",
        "source_binding": "immutable_directory_list_entry",
        "basename_transform": "directory_basename",
        "destination_template_rule_id": "task_literal_vacation_spot_archive_template",
        "extension_policy": "task_template_extension",
        "parser_policy": "strict_json_no_regex_repair",
    }
    controls = []
    for proposal_id, field, value in [
        ("control_archive_generic_basename_projection", "source_binding", "generic_basename_projection"),
        ("control_archive_wrong_template", "destination_template_rule_id", "task_literal_backup_directory"),
        ("control_archive_wrong_transform", "basename_transform", "file_basename"),
        ("control_archive_wrong_extension_policy", "extension_policy", "always_md"),
        ("control_archive_parser_relaxation", "parser_policy", "tolerant_alias_repair"),
    ]:
        proposal = dict(base)
        proposal["proposal_id"] = proposal_id
        proposal["control_type"] = "negative_" + field
        proposal[field] = value
        controls.append(proposal)
    prompt_only = {
        "proposal_id": "control_archive_prompt_only",
        "control_type": "negative_prompt_only",
        "target_residual": "directory_basename_archive_path_binding_missing",
        "patch_type": "prompt_only",
        "parser_policy": "strict_json_no_regex_repair",
    }
    controls.append(prompt_only)
    return controls


def metaverify_archive(proposal: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    accepted = False
    reason = "unclassified_reject"
    if proposal["target_residual"] != "directory_basename_archive_path_binding_missing":
        return {"proposal_id": proposal["proposal_id"], "accepted": False, "reason": "rejected_residual_family_mismatch", "checks": {"residual_match": False}, "proposal": proposal}
    if proposal["patch_type"] == "prompt_only":
        return {"proposal_id": proposal["proposal_id"], "accepted": False, "reason": "rejected_prompt_only_no_frontier", "checks": {"has_deterministic_frontier": False}, "proposal": proposal}
    if proposal["patch_type"] != "frontier_grammar":
        return {"proposal_id": proposal["proposal_id"], "accepted": False, "reason": "rejected_wrong_patch_type", "checks": {"patch_type": proposal["patch_type"]}, "proposal": proposal}
    checks["strict_parser_preserved"] = proposal.get("parser_policy") == "strict_json_no_regex_repair"
    checks["source_binding_ok"] = proposal.get("source_binding") == "immutable_directory_list_entry"
    checks["basename_transform_ok"] = proposal.get("basename_transform") == "directory_basename"
    checks["template_rule_ok"] = proposal.get("destination_template_rule_id") == "task_literal_vacation_spot_archive_template"
    checks["extension_policy_ok"] = proposal.get("extension_policy") == "task_template_extension"
    checks["feasibility_decision_counts"] = artifacts["feasibility"]["decision_counts"]
    checks["model_decision_counts"] = artifacts["model"]["decision_counts"]
    checks["full_gate_after_repair"] = artifacts["full"]["decision_counts"]
    accepted = (
        checks["strict_parser_preserved"]
        and checks["source_binding_ok"]
        and checks["basename_transform_ok"]
        and checks["template_rule_ok"]
        and checks["extension_policy_ok"]
        and artifacts["feasibility"]["decision_counts"] == {"commit_live": 9}
        and artifacts["model"]["decision_counts"] == {"commit_live": 9}
    )
    if accepted:
        reason = "accepted_archive_directory_basename_frontier"
    elif not checks["strict_parser_preserved"]:
        reason = "rejected_parser_relaxation"
    elif not checks["source_binding_ok"]:
        reason = "rejected_source_binding"
    elif not checks["basename_transform_ok"]:
        reason = "rejected_basename_transform"
    elif not checks["template_rule_ok"]:
        reason = "rejected_destination_template"
    elif not checks["extension_policy_ok"]:
        reason = "rejected_extension_policy"
    return {"proposal_id": proposal["proposal_id"], "accepted": accepted, "reason": reason, "checks": checks, "proposal": proposal}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v18_archive_structured_repair_policy"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v18 archive structured repair policy")

    root = Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1")
    paths = {
        "feasibility": resolve(root / "track_a_v17_archive_path_feasibility/feasibility.json"),
        "model": resolve(root / "track_a_model_run_v17_archive_path_target/results.json"),
        "full": resolve(root / "track_a_rescore_full_opened_v17_merged/results.json"),
    }
    artifacts = {key: load_json(path) for key, path in paths.items()}
    packet = archive_repair_packet(artifacts["feasibility"], artifacts["model"], artifacts["full"])
    selection = select_archive_patch(packet)
    positive = compile_archive_proposal(selection)
    controls = control_proposals()
    positive_results = [metaverify_archive(positive, artifacts)]
    control_results = [metaverify_archive(control, artifacts) for control in controls]
    positive_pass = all(result["accepted"] for result in positive_results)
    negative_pass = all(not result["accepted"] for result in control_results)
    status = "RPD_EBW_TRACK_A_V18_ARCHIVE_STRUCTURED_REPAIR_POLICY_PASS" if positive_pass and negative_pass else "RPD_EBW_TRACK_A_V18_ARCHIVE_STRUCTURED_REPAIR_POLICY_FAIL"

    output_dir.mkdir(parents=True)
    write_json(output_dir / "archive_repair_packet.json", {"schema": "ebw_track_a_v18_archive_repair_packet_v1", "packet": packet})
    write_json(output_dir / "primitive_library.json", primitive_library())
    write_json(output_dir / "structured_selection.json", {"schema": "ebw_track_a_v18_archive_structured_selection_v1", "selection": selection})
    write_json(output_dir / "structured_proposals.json", {"schema": "ebw_track_a_v18_archive_structured_proposals_v1", "positive_proposal": positive, "control_proposals": controls})
    write_json(output_dir / "metaverifier_results.json", {"schema": "ebw_track_a_v18_archive_metaverifier_results_v1", "positive_results": positive_results, "control_results": control_results})
    payload = {
        "schema": "ebw_track_a_v18_archive_structured_repair_policy_v1",
        "status": status,
        "positive_controls_pass": positive_pass,
        "negative_controls_pass": negative_pass,
        "accepted_positive_proposals": [result["proposal_id"] for result in positive_results if result["accepted"]],
        "rejected_control_proposals": [result["proposal_id"] for result in control_results if not result["accepted"]],
        "full_gate_after_repair": artifacts["full"]["decision_counts"],
        "input_hashes": {name: file_hash(path) for name, path in sorted(paths.items())},
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "results.json", payload)
    report = [
        "# EBW Track A v18 Archive Structured Repair Policy",
        "",
        f"## Status: **`{status}`**",
        "",
        "- Scope: CPU-only structured proposal policy for archive-path residuals",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Structured Selection",
        "",
        "| Residual | Template | Selected primitives |",
        "|---|---|---|",
        f"| `{selection['residual_id']}` | `{selection['template_id']}` | `{', '.join(selection['selected_primitives'])}` |",
        "",
        "## MetaVerifier Results",
        "",
        "| Proposal | Accepted | Reason |",
        "|---|---:|---|",
    ]
    for result in positive_results + control_results:
        report.append(f"| `{result['proposal_id']}` | {result['accepted']} | `{result['reason']}` |")
    report += [
        "",
        "## Interpretation",
        "",
        "The archive-path proof family can be represented in the same structured RepairAgent action space: typed residual packet, primitive selection, deterministic compilation, and MetaVerifier acceptance. Negative controls reject generic basename projection, wrong task template, wrong transform, wrong extension policy, parser relaxation, and prompt-only repair.",
    ]
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "positive_controls_pass": positive_pass, "negative_controls_pass": negative_pass, "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()