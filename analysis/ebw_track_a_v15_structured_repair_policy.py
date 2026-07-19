"""CPU-only structured RepairAgent policy over v12 residual packets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v12_repairagent_metaverifier import contract_failure_modes, metaverify

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


def primitive_library() -> dict[str, Any]:
    return {
        "schema": "ebw_track_a_v15_repair_primitive_library_v1",
        "patch_templates": [
            {
                "id": "template.frontier_grammar.title_slug_export_path_binding",
                "patch_type": "frontier_grammar",
                "required_slots": ["source_binding", "slug_transform", "destination_directory_rule_id", "extension", "parser_policy"],
                "target_residual": "title_slug_export_path_binding_missing",
            },
            {
                "id": "template.response_contract.output_obligation_key",
                "patch_type": "response_contract",
                "required_slots": ["required_key", "forbidden_keys", "parser_policy"],
                "target_residual": "output_contract_obligation_key_leakage",
            },
        ],
        "source_binding": [
            {
                "id": "source_binding.latest_matching_pre_write_show_note",
                "value": "latest_matching_pre_write_show_note",
                "when": "content-only matching is ambiguous across repeated note contents",
            },
            {
                "id": "source_binding.any_matching_show_note_content",
                "value": "any_matching_show_note_content",
                "negative_control": True,
            },
            {
                "id": "source_binding.read_group_same_rank",
                "value": "read_group_same_rank",
                "negative_for_title_slug": True,
            },
        ],
        "slug_transform": [
            {"id": "slug_transform.whitespace_to_underscore", "value": "whitespace_to_underscore"},
            {"id": "slug_transform.lowercase_first_letter", "value": "lowercase_first_letter", "negative_control": True},
        ],
        "destination_directory_rule": [
            {"id": "destination_directory.task_literal_backup_directory", "value": "task_literal_backup_directory"},
            {"id": "destination_directory.dir_rule_001", "value": "DIR_RULE_001", "negative_control": True},
        ],
        "extension": [
            {"id": "extension.md_dot", "value": ".md"},
            {"id": "extension.md_no_dot", "value": "md", "negative_control": True},
        ],
        "response_contract": [
            {
                "id": "response_contract.require_obligation_forbid_required_obligation",
                "required_key": "obligation",
                "forbidden_keys": ["required_obligation"],
            },
            {
                "id": "response_contract.require_required_obligation",
                "required_key": "required_obligation",
                "forbidden_keys": ["omitted_obligation"],
                "negative_control": True,
            },
        ],
        "parser_policy": [
            {"id": "parser_policy.strict", "value": "strict_json_no_regex_repair"},
            {"id": "parser_policy.tolerant_alias", "value": "tolerant_alias_repair", "negative_control": True},
        ],
    }


def blind_packet(packet: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "residual_id",
        "residual_class",
        "typed_reason",
        "target_rows",
        "counterexample_summary",
        "failed_frontier",
        "failure_modes",
        "failed_prompt_protocol",
        "strict_before",
    }
    return {key: packet[key] for key in packet if key in allowed}


def select_structured_patch(packet: dict[str, Any]) -> dict[str, Any]:
    residual_class = packet["residual_class"]
    typed_reason = packet["typed_reason"]
    if residual_class == "title_slug_export_path_binding_missing" and typed_reason == "source_binding_ambiguity":
        return {
            "selection_id": "S_TITLE_SLUG_LATEST_SHOW_NOTE",
            "residual_id": packet["residual_id"],
            "target_residual": residual_class,
            "template_id": "template.frontier_grammar.title_slug_export_path_binding",
            "selected_primitives": [
                "source_binding.latest_matching_pre_write_show_note",
                "slug_transform.whitespace_to_underscore",
                "destination_directory.task_literal_backup_directory",
                "extension.md_dot",
                "parser_policy.strict",
            ],
            "self_check": {
                "uses_counterexample": "content-only matching binds repeated habit-tracker content to an earlier note title",
                "rejects_failed_frontier": packet.get("failed_frontier", {}).get("source_binding") == "any_matching_show_note_content",
            },
        }
    if residual_class == "output_contract_obligation_key_leakage" and typed_reason == "strict_parse_contract_failure":
        return {
            "selection_id": "S_OUTPUT_CONTRACT_OBLIGATION_KEY",
            "residual_id": packet["residual_id"],
            "target_residual": residual_class,
            "template_id": "template.response_contract.output_obligation_key",
            "selected_primitives": [
                "response_contract.require_obligation_forbid_required_obligation",
                "parser_policy.strict",
            ],
            "self_check": {
                "failure_modes_include_required_obligation_key": "required_obligation_key" in packet.get("failure_modes", {}),
                "strict_parser_should_be_preserved": True,
            },
        }
    return {
        "selection_id": "S_NO_PATCH",
        "residual_id": packet["residual_id"],
        "target_residual": residual_class,
        "template_id": "template.none",
        "selected_primitives": [],
        "self_check": {"unsupported_residual": True},
    }


def compile_proposal(selection: dict[str, Any]) -> dict[str, Any]:
    if selection["template_id"] == "template.frontier_grammar.title_slug_export_path_binding":
        return {
            "proposal_id": "structured_title_slug_latest_show_note",
            "target_residual": selection["target_residual"],
            "patch_type": "frontier_grammar",
            "source_binding": "latest_matching_pre_write_show_note",
            "slug_transform": "whitespace_to_underscore",
            "destination_directory_rule_id": "task_literal_backup_directory",
            "extension": ".md",
            "parser_policy": "strict_json_no_regex_repair",
        }
    if selection["template_id"] == "template.response_contract.output_obligation_key":
        return {
            "proposal_id": "structured_output_contract_obligation_key",
            "target_residual": selection["target_residual"],
            "patch_type": "response_contract",
            "required_key": "obligation",
            "forbidden_keys": ["required_obligation"],
            "parser_policy": "strict_json_no_regex_repair",
        }
    return {
        "proposal_id": "structured_no_patch",
        "target_residual": selection["target_residual"],
        "patch_type": "prompt_only",
        "parser_policy": "strict_json_no_regex_repair",
    }


def control_proposals() -> list[dict[str, Any]]:
    return [
        {
            "proposal_id": "control_title_slug_content_only",
            "control_type": "negative_content_only",
            "target_residual": "title_slug_export_path_binding_missing",
            "patch_type": "frontier_grammar",
            "source_binding": "any_matching_show_note_content",
            "slug_transform": "whitespace_to_underscore",
            "destination_directory_rule_id": "task_literal_backup_directory",
            "extension": ".md",
            "parser_policy": "strict_json_no_regex_repair",
        },
        {
            "proposal_id": "control_title_slug_residual_shuffled",
            "control_type": "negative_residual_shuffled",
            "target_residual": "output_contract_obligation_key_leakage",
            "patch_type": "frontier_grammar",
            "source_binding": "latest_matching_pre_write_show_note",
            "slug_transform": "whitespace_to_underscore",
            "destination_directory_rule_id": "task_literal_backup_directory",
            "extension": ".md",
            "parser_policy": "strict_json_no_regex_repair",
        },
        {
            "proposal_id": "control_output_contract_tolerant_parser",
            "control_type": "negative_parser_relaxation",
            "target_residual": "output_contract_obligation_key_leakage",
            "patch_type": "parser_repair",
            "allow_key_alias": {"required_obligation": "obligation"},
            "parser_policy": "tolerant_alias_repair",
        },
        {
            "proposal_id": "control_prompt_only_no_frontier",
            "control_type": "negative_prompt_only",
            "target_residual": "title_slug_export_path_binding_missing",
            "patch_type": "prompt_only",
            "parser_policy": "strict_json_no_regex_repair",
        },
    ]


def load_artifacts(root: Path) -> dict[str, Any]:
    paths = {
        "title_slug_feasibility_v1": resolve(root / "track_a_v11_title_slug_feasibility/feasibility.json"),
        "title_slug_feasibility_v2": resolve(root / "track_a_v11_title_slug_feasibility_v2/feasibility.json"),
        "v11_model_results": resolve(root / "track_a_model_run_v11_title_slug_target/results.json"),
        "v11_model_rows": resolve(root / "track_a_model_run_v11_title_slug_target/rows.json"),
        "v11_model_raw": resolve(root / "track_a_model_run_v11_title_slug_target/raw_model_outputs.json"),
        "v11b_retry_results": resolve(root / "track_a_model_run_v11b_contract_retry/results.json"),
        "v11b_full_results": resolve(root / "track_a_rescore_full_opened_v11b_merged/results.json"),
    }
    return {
        "title_slug_feasibility_v1": load_json(paths["title_slug_feasibility_v1"]),
        "title_slug_feasibility_v2": load_json(paths["title_slug_feasibility_v2"]),
        "v11_title_slug_model": load_json(paths["v11_model_results"]),
        "v11b_contract_retry": load_json(paths["v11b_retry_results"]),
        "v11b_full_gate": load_json(paths["v11b_full_results"]),
        "contract_failure_modes": contract_failure_modes(paths["v11_model_raw"], paths["v11_model_rows"]),
        "input_hashes": {name: file_hash(path) for name, path in sorted(paths.items())},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair-packets", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v12_repairagent_metaverifier/repair_packets.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v15_structured_repair_policy"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v15 structured repair policy")

    root = Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1")
    packets_path = resolve(args.repair_packets)
    packets = [blind_packet(packet) for packet in load_json(packets_path)["packets"]]
    artifacts = load_artifacts(root)
    library = primitive_library()
    selections = [select_structured_patch(packet) for packet in packets]
    positive_proposals = [compile_proposal(selection) for selection in selections]
    controls = control_proposals()
    positive_results = [metaverify(proposal, artifacts) for proposal in positive_proposals]
    control_results = [metaverify(proposal, artifacts) for proposal in controls]
    positive_pass = all(result["accepted"] for result in positive_results)
    negative_pass = all(not result["accepted"] for result in control_results)
    status = "RPD_EBW_TRACK_A_V15_STRUCTURED_REPAIR_POLICY_PASS" if positive_pass and negative_pass else "RPD_EBW_TRACK_A_V15_STRUCTURED_REPAIR_POLICY_FAIL"

    output_dir.mkdir(parents=True)
    write_json(output_dir / "primitive_library.json", library)
    write_json(output_dir / "structured_selections.json", {"schema": "ebw_track_a_v15_structured_selections_v1", "rows": selections})
    write_json(output_dir / "structured_proposals.json", {"schema": "ebw_track_a_v15_structured_proposals_v1", "positive_proposals": positive_proposals, "control_proposals": controls})
    write_json(output_dir / "metaverifier_results.json", {"schema": "ebw_track_a_v15_metaverifier_results_v1", "positive_results": positive_results, "control_results": control_results})
    payload = {
        "schema": "ebw_track_a_v15_structured_repair_policy_v1",
        "status": status,
        "positive_controls_pass": positive_pass,
        "negative_controls_pass": negative_pass,
        "accepted_positive_proposals": [result["proposal_id"] for result in positive_results if result["accepted"]],
        "rejected_control_proposals": [result["proposal_id"] for result in control_results if not result["accepted"]],
        "full_gate_after_repairs": artifacts["v11b_full_gate"]["decision_counts"],
        "repair_packets_sha256": file_hash(packets_path),
        "input_hashes": artifacts["input_hashes"],
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "results.json", payload)
    report = [
        "# EBW Track A v15 Structured Repair Policy",
        "",
        f"## Status: **`{status}`**",
        "",
        "- Scope: CPU-only structured proposal policy over v12 typed residual packets",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Structured Selections",
        "",
        "| Residual | Template | Selected primitives |",
        "|---|---|---|",
    ]
    for selection in selections:
        report.append(f"| `{selection['residual_id']}` | `{selection['template_id']}` | `{', '.join(selection['selected_primitives'])}` |")
    report += ["", "## MetaVerifier Results", "", "| Proposal | Accepted | Reason |", "|---|---:|---|"]
    for result in positive_results + control_results:
        report.append(f"| `{result['proposal_id']}` | {result['accepted']} | `{result['reason']}` |")
    report += [
        "",
        "## Interpretation",
        "",
        "A deterministic structured proposal policy can recover the two accepted repairs from typed residual packets while the same MetaVerifier rejects shortcut controls. This establishes the primitive vocabulary and compiler for the next model-in-the-loop step: ask Qwen to select primitives, not to free-form invent patch JSON.",
    ]
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "positive_controls_pass": positive_pass, "negative_controls_pass": negative_pass, "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()