"""CPU-only RepairAgent/MetaVerifier preflight over v11/v11b residual repairs."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
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


def contract_failure_modes(raw_path: Path, rows_path: Path) -> dict[str, int]:
    raw = load_json(raw_path)["rows"]
    rows = load_json(rows_path)["rows"]
    raw_by_id = {row["instance_id"]: row for row in raw}
    counts: Counter[str] = Counter()
    for result in rows:
        if result["decision"] == "commit_live":
            continue
        output = raw_by_id[result["instance_id"]]["output"]
        obj = json.loads(output)
        if "required_obligation" in obj:
            counts["required_obligation_key"] += 1
        elif "obligation" not in obj:
            counts["missing_obligation_key"] += 1
        else:
            counts["other_contract_failure"] += 1
    return dict(sorted(counts.items()))


def repair_packets(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    title_v1 = artifacts["title_slug_feasibility_v1"]
    title_v2 = artifacts["title_slug_feasibility_v2"]
    v11_model = artifacts["v11_title_slug_model"]
    v11b_retry = artifacts["v11b_contract_retry"]
    return [
        {
            "residual_id": "R_TITLE_SLUG_SOURCE_BINDING_AMBIGUITY_V11",
            "residual_class": "title_slug_export_path_binding_missing",
            "typed_reason": "source_binding_ambiguity",
            "target_rows": title_v2["target_rows"],
            "counterexample_summary": "content-only matching binds repeated habit-tracker content to an earlier note title",
            "failed_frontier": {
                "source_binding": "any_matching_show_note_content",
                "decision_counts": title_v1["decision_counts"],
                "candidate_counts": title_v1["candidate_counts"],
            },
            "accepted_frontier": {
                "source_binding": "latest_matching_pre_write_show_note",
                "transform": "whitespace_to_underscore",
                "destination_directory_rule_id": "task_literal_backup_directory",
                "extension": ".md",
                "decision_counts": title_v2["decision_counts"],
                "candidate_counts": title_v2["candidate_counts"],
            },
        },
        {
            "residual_id": "R_OUTPUT_CONTRACT_OBLIGATION_KEY_V11B",
            "residual_class": "output_contract_obligation_key_leakage",
            "typed_reason": "strict_parse_contract_failure",
            "target_rows": 5,
            "counterexample_summary": "model emitted required_obligation or omitted obligation despite semantically valid title-slug fields",
            "failure_modes": artifacts["contract_failure_modes"],
            "failed_prompt_protocol": v11_model["prompt_protocol"],
            "accepted_prompt_protocol": v11b_retry["prompt_protocol"],
            "strict_before": {"decision_counts": v11_model["decision_counts"], "parse_rate": v11_model["parse_rate"]},
            "strict_after": {"decision_counts": v11b_retry["decision_counts"], "parse_rate": v11b_retry["parse_rate"]},
        },
    ]


def proposals() -> list[dict[str, Any]]:
    return [
        {
            "proposal_id": "P_TITLE_SLUG_LATEST_SHOW_NOTE",
            "control_type": "positive",
            "target_residual": "title_slug_export_path_binding_missing",
            "patch_type": "frontier_grammar",
            "source_binding": "latest_matching_pre_write_show_note",
            "slug_transform": "whitespace_to_underscore",
            "destination_directory_rule_id": "task_literal_backup_directory",
            "extension": ".md",
            "parser_policy": "strict_json_no_regex_repair",
        },
        {
            "proposal_id": "C_TITLE_SLUG_CONTENT_ONLY",
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
            "proposal_id": "C_TITLE_SLUG_RESIDUAL_SHUFFLED",
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
            "proposal_id": "P_OUTPUT_CONTRACT_OBLIGATION_KEY",
            "control_type": "positive",
            "target_residual": "output_contract_obligation_key_leakage",
            "patch_type": "response_contract",
            "required_key": "obligation",
            "forbidden_keys": ["required_obligation"],
            "parser_policy": "strict_json_no_regex_repair",
        },
        {
            "proposal_id": "C_OUTPUT_CONTRACT_TOLERANT_PARSER",
            "control_type": "negative_parser_relaxation",
            "target_residual": "output_contract_obligation_key_leakage",
            "patch_type": "parser_repair",
            "allow_key_alias": {"required_obligation": "obligation"},
            "parser_policy": "tolerant_alias_repair",
        },
        {
            "proposal_id": "C_PROMPT_ONLY_NO_FRONTIER",
            "control_type": "negative_prompt_only",
            "target_residual": "title_slug_export_path_binding_missing",
            "patch_type": "prompt_only",
            "parser_policy": "strict_json_no_regex_repair",
        },
    ]


def metaverify(proposal: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    accepted = False
    reason = "unclassified_reject"
    target = proposal["target_residual"]
    patch_type = proposal["patch_type"]

    if patch_type == "frontier_grammar" and target == "title_slug_export_path_binding_missing":
        checks["residual_match"] = True
        checks["strict_parser_preserved"] = proposal.get("parser_policy") == "strict_json_no_regex_repair"
        checks["source_binding"] = proposal.get("source_binding")
        checks["transform_ok"] = proposal.get("slug_transform") == "whitespace_to_underscore"
        checks["directory_rule_ok"] = proposal.get("destination_directory_rule_id") == "task_literal_backup_directory"
        checks["extension_ok"] = proposal.get("extension") == ".md"
        if proposal.get("source_binding") == "latest_matching_pre_write_show_note":
            feasibility = artifacts["title_slug_feasibility_v2"]
            checks["target_rows"] = feasibility["target_rows"]
            checks["decision_counts"] = feasibility["decision_counts"]
            checks["candidate_counts"] = feasibility["candidate_counts"]
            accepted = checks["strict_parser_preserved"] and feasibility["decision_counts"] == {"commit_live": 65}
            reason = "accepted_latest_read_frontier" if accepted else "latest_read_frontier_failed_gate"
        else:
            feasibility = artifacts["title_slug_feasibility_v1"]
            checks["target_rows"] = feasibility["target_rows"]
            checks["decision_counts"] = feasibility["decision_counts"]
            checks["candidate_counts"] = feasibility["candidate_counts"]
            reason = "rejected_content_only_source_binding"
    elif patch_type == "frontier_grammar":
        checks["residual_match"] = False
        reason = "rejected_residual_family_mismatch"
    elif patch_type == "response_contract" and target == "output_contract_obligation_key_leakage":
        retry = artifacts["v11b_contract_retry"]
        checks["residual_match"] = True
        checks["strict_parser_preserved"] = proposal.get("parser_policy") == "strict_json_no_regex_repair"
        checks["required_key_ok"] = proposal.get("required_key") == "obligation"
        checks["forbidden_key_ok"] = "required_obligation" in proposal.get("forbidden_keys", [])
        checks["failure_modes"] = artifacts["contract_failure_modes"]
        checks["retry_decision_counts"] = retry["decision_counts"]
        checks["retry_parse_rate"] = retry["parse_rate"]
        accepted = (
            checks["strict_parser_preserved"]
            and checks["required_key_ok"]
            and checks["forbidden_key_ok"]
            and retry["decision_counts"] == {"commit_live": 5}
            and retry["parse_rate"] == 1.0
        )
        reason = "accepted_contract_repair" if accepted else "contract_repair_failed_gate"
    elif patch_type == "parser_repair":
        checks["strict_parser_preserved"] = False
        reason = "rejected_parser_relaxation"
    elif patch_type == "prompt_only":
        checks["has_deterministic_frontier"] = False
        reason = "rejected_prompt_only_no_frontier"
    return {"proposal_id": proposal["proposal_id"], "accepted": accepted, "reason": reason, "checks": checks, "proposal": proposal}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v12_repairagent_metaverifier"))
    parser.add_argument("--title-slug-feasibility-v1", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11_title_slug_feasibility/feasibility.json"))
    parser.add_argument("--title-slug-feasibility-v2", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11_title_slug_feasibility_v2/feasibility.json"))
    parser.add_argument("--v11-model-results", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11_title_slug_target/results.json"))
    parser.add_argument("--v11-model-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11_title_slug_target/rows.json"))
    parser.add_argument("--v11-model-raw", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11_title_slug_target/raw_model_outputs.json"))
    parser.add_argument("--v11b-retry-results", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11b_contract_retry/results.json"))
    parser.add_argument("--v11b-full-results", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v11b_merged/results.json"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v12 RepairAgent/MetaVerifier output")

    paths = {
        "title_slug_feasibility_v1": resolve(args.title_slug_feasibility_v1),
        "title_slug_feasibility_v2": resolve(args.title_slug_feasibility_v2),
        "v11_model_results": resolve(args.v11_model_results),
        "v11_model_rows": resolve(args.v11_model_rows),
        "v11_model_raw": resolve(args.v11_model_raw),
        "v11b_retry_results": resolve(args.v11b_retry_results),
        "v11b_full_results": resolve(args.v11b_full_results),
    }
    artifacts = {
        "title_slug_feasibility_v1": load_json(paths["title_slug_feasibility_v1"]),
        "title_slug_feasibility_v2": load_json(paths["title_slug_feasibility_v2"]),
        "v11_title_slug_model": load_json(paths["v11_model_results"]),
        "v11b_contract_retry": load_json(paths["v11b_retry_results"]),
        "v11b_full_gate": load_json(paths["v11b_full_results"]),
        "contract_failure_modes": contract_failure_modes(paths["v11_model_raw"], paths["v11_model_rows"]),
    }
    packets = repair_packets(artifacts)
    proposal_list = proposals()
    results = [metaverify(proposal, artifacts) for proposal in proposal_list]
    accepted = [result for result in results if result["accepted"]]
    rejected = [result for result in results if not result["accepted"]]
    status = "RPD_EBW_TRACK_A_V12_REPAIRAGENT_METAVERIFIER_COMPLETE"
    payload = {
        "schema": "ebw_track_a_v12_repairagent_metaverifier_v1",
        "status": status,
        "repair_packets": packets,
        "proposals": proposal_list,
        "metaverifier_results": results,
        "accepted_proposals": [result["proposal_id"] for result in accepted],
        "rejected_proposals": [result["proposal_id"] for result in rejected],
        "positive_controls_pass": {"accepted": len(accepted), "expected": 2, "pass": len(accepted) == 2},
        "negative_controls_pass": {"rejected": len(rejected), "expected": 4, "pass": len(rejected) == 4},
        "full_gate_after_repairs": artifacts["v11b_full_gate"]["decision_counts"],
        "input_hashes": {name: file_hash(path) for name, path in sorted(paths.items())},
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    output_dir.mkdir(parents=True)
    write_json(output_dir / "metaverifier.json", payload)
    write_json(output_dir / "repair_packets.json", {"schema": "ebw_track_a_v12_repair_packets_v1", "packets": packets})
    report = [
        "# EBW Track A v12 RepairAgent/MetaVerifier Preflight",
        "",
        f"## Status: **`{status}`**",
        "",
        "- Scope: CPU-only MetaVerifier over typed residual packets and patch proposals",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Repair Packets",
        "",
        "| Residual ID | Class | Target rows | Typed reason |",
        "|---|---|---:|---|",
    ]
    report += [f"| `{packet['residual_id']}` | `{packet['residual_class']}` | {packet['target_rows']} | `{packet['typed_reason']}` |" for packet in packets]
    report += ["", "## MetaVerifier Results", "", "| Proposal | Control | Accepted | Reason |", "|---|---|---:|---|"]
    report += [f"| `{result['proposal_id']}` | `{result['proposal']['control_type']}` | {str(result['accepted'])} | `{result['reason']}` |" for result in results]
    report += [
        "",
        "## Full Gate After Accepted Repairs",
        "",
        "| Decision | Rows |",
        "|---|---:|",
    ]
    report += [f"| `{key}` | {value} |" for key, value in sorted(artifacts["v11b_full_gate"]["decision_counts"].items())]
    report += [
        "",
        "## Interpretation",
        "",
        "This is not yet an autonomous RepairAgent result. It is the CPU-only MetaVerifier preflight: typed residual packets are explicit, accepted patches must reproduce deterministic gates, and controls reject content-only source binding, residual-family mismatch, parser relaxation, and prompt-only repair. The next step is to ask a model/agent to propose patches from the same residual packets, then run this MetaVerifier unchanged.",
    ]
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "accepted": payload["accepted_proposals"], "rejected": payload["rejected_proposals"], "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()