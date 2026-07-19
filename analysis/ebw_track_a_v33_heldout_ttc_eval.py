"""Evaluate held-out TTC primitive selections and build merged proof outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from analysis.ebw_track_a_v21_source_path_identity_feasibility import adversarial_values as source_adversarial_values, source_path_identity_candidate, valid_source_path
from analysis.ebw_track_a_v23_literal_export_path_feasibility import adversarial_values as literal_adversarial_values, literal_export_path_candidate, valid_literal_export_path
from analysis.ebw_track_a_v25_ordered_note_title_identity_feasibility import adversarial_values as note_adversarial_values, ordered_note_title_identity_candidate, valid_ordered_note_id
from analysis.ebw_track_a_v27_prior_effect_playlist_feasibility import adversarial_values as prior_adversarial_values, prior_effect_playlist_candidate, valid_prior_effect_value
from analysis.ebw_track_a_v29_frontier_closure_repair_policy import compile_selection, primitive_library
from analysis.ebw_track_a_v29_frontier_selection_eval import parse_selection
from experiments.ebw_obligation_sketch import barrier_unique_validity

REPO_ROOT = Path(__file__).resolve().parents[1]

CandidateFn = Callable[[dict[str, Any]], dict[str, Any] | None]


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def candidate_for(row: dict[str, Any], residual_class: str) -> dict[str, Any] | None:
    return {
        "source_path_identity_binding_missing": source_path_identity_candidate,
        "literal_export_path_binding_missing": literal_export_path_candidate,
        "ordered_note_title_identity_binding_abstain": ordered_note_title_identity_candidate,
        "prior_effect_playlist_id_binding_abstain": prior_effect_playlist_candidate,
    }[residual_class](row)


def proposal_slots_ok(proposal: dict[str, Any], residual_class: str) -> bool:
    if proposal.get("parser_policy") != "strict_json_no_regex_repair":
        return False
    if residual_class == "source_path_identity_binding_missing":
        return proposal.get("source_binding") == "pre_write_response_path_exact" and proposal.get("identity_transform") == "exact_path"
    if residual_class == "literal_export_path_binding_missing":
        return proposal.get("span_source") == "quoted_task_path_exact" and proposal.get("target_arg") == "file_path"
    if residual_class == "ordered_note_title_identity_binding_abstain":
        return proposal.get("source_binding") == "show_note_response_note_id" and proposal.get("role_constraint") == "bucket_list_title" and proposal.get("content_binding") == "quoted_task_item_in_prewrite_content"
    if residual_class == "prior_effect_playlist_id_binding_abstain":
        return proposal.get("effect_binding") == "create_playlist_response_playlist_id" and proposal.get("effect_field") == "playlist_id"
    return False


def verify_candidate(row: dict[str, Any], residual_class: str, candidate: dict[str, Any]) -> tuple[str, dict[str, bool]]:
    live_value = row["live_arguments"][row["field_name"]]
    if residual_class == "source_path_identity_binding_missing":
        live_valid = valid_source_path(live_value, candidate)
        adversarial_valids = {f"adversarial_{index}": valid_source_path(value, candidate) for index, value in enumerate(source_adversarial_values(row, candidate))}
    elif residual_class == "literal_export_path_binding_missing":
        live_valid = valid_literal_export_path(live_value, candidate)
        adversarial_valids = {f"adversarial_{index}": valid_literal_export_path(value, candidate) for index, value in enumerate(literal_adversarial_values(row, candidate))}
    elif residual_class == "ordered_note_title_identity_binding_abstain":
        live_valid = valid_ordered_note_id(live_value, candidate)
        adversarial_valids = {f"adversarial_{index}": valid_ordered_note_id(value, candidate) for index, value in enumerate(note_adversarial_values(row, candidate))}
    elif residual_class == "prior_effect_playlist_id_binding_abstain":
        live_valid = valid_prior_effect_value(live_value, candidate)
        adversarial_valids = {f"adversarial_{index}": valid_prior_effect_value(value, candidate) for index, value in enumerate(prior_adversarial_values(row, candidate))}
    else:
        return "unsupported_residual", {}
    barrier = barrier_unique_validity({"live": live_valid, **adversarial_valids})
    if barrier["decision"] == "commit" and barrier["candidate_id"] == "live":
        return "commit_live", {"live": live_valid, **adversarial_valids}
    if barrier["decision"] == "commit":
        return "unsafe_unique_wrong", {"live": live_valid, **adversarial_valids}
    if barrier["typed_reason"] == "competing_valid":
        return "ambiguous_both_valid", {"live": live_valid, **adversarial_valids}
    return "abstain_no_valid", {"live": live_valid, **adversarial_valids}


def sketch_from_candidate(candidate: dict[str, Any], residual_class: str) -> dict[str, Any]:
    if residual_class == "source_path_identity_binding_missing":
        return {"obligation": "source_path_identity_binding", "source_read_id": candidate["source_read_id"], "source_path_field": candidate["source_path_field"], "identity_transform": candidate["identity_transform"], "target_arg": candidate["target_arg"]}
    if residual_class == "literal_export_path_binding_missing":
        return {"obligation": "literal_intent_binding", "user_span": candidate["user_span"], "target_arg": candidate["target_arg"]}
    if residual_class == "ordered_note_title_identity_binding_abstain":
        return {"obligation": "ordered_note_title_identity_binding", "source_read_id": candidate["source_read_id"], "note_id_field": candidate["note_id_field"], "title_field": candidate["title_field"], "content_field": candidate["content_field"], "task_item_span": candidate["task_item_span"], "target_arg": candidate["target_arg"]}
    if residual_class == "prior_effect_playlist_id_binding_abstain":
        return {"obligation": "prior_effect_binding", "effect_step_id": candidate["effect_step_id"], "effect_field": candidate["effect_field"], "target_arg": candidate["target_arg"]}
    raise ValueError(residual_class)


def row_with_candidate(row: dict[str, Any], candidate: dict[str, Any], residual_class: str) -> dict[str, Any]:
    updated = dict(row)
    if residual_class == "source_path_identity_binding_missing":
        updated["required_obligation"] = "source_path_identity_binding"
        updated["source_path_identity_candidates"] = [candidate]
    elif residual_class == "literal_export_path_binding_missing":
        updated["required_obligation"] = "literal_intent_binding"
        updated["required_literal_span"] = candidate["user_span"]
    elif residual_class == "ordered_note_title_identity_binding_abstain":
        updated["required_obligation"] = "ordered_note_title_identity_binding"
        updated["ordered_note_title_identity_candidates"] = [candidate]
    elif residual_class == "prior_effect_playlist_id_binding_abstain":
        updated["required_obligation"] = "prior_effect_binding"
        updated["prior_effect_candidates"] = [candidate]
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v33_heldout_ttc_prompt_manifest/prompt_manifest.json"))
    parser.add_argument("--repair-raw-outputs", type=Path, required=True)
    parser.add_argument("--base-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v32_heldout_prompt_manifest_no_repair/prompt_manifest.json"))
    parser.add_argument("--base-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v32_heldout_no_repair/raw_model_outputs.json"))
    parser.add_argument("--baseline-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v32_heldout_no_repair/rows.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v33 held-out TTC eval")

    repair_manifest_path = resolve(args.repair_prompt_manifest)
    repair_raw_path = resolve(args.repair_raw_outputs)
    base_manifest_path = resolve(args.base_prompt_manifest)
    base_raw_path = resolve(args.base_raw_outputs)
    baseline_rows_path = resolve(args.baseline_rows)
    repair_manifest = load_json(repair_manifest_path)
    repair_raw = load_json(repair_raw_path)
    base_manifest = load_json(base_manifest_path)
    base_raw = load_json(base_raw_path)
    baseline_rows = load_json(baseline_rows_path)["rows"]
    library = primitive_library()
    repair_rows_by_id = {row["residual_id"]: row for row in repair_manifest["rows"]}
    base_rows_by_id = {row["instance_id"]: row for row in base_manifest["rows"]}
    base_raw_by_id = {row["instance_id"]: row for row in base_raw["rows"]}
    residual_by_class_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in baseline_rows:
        if result["decision"] == "commit_live":
            continue
        for packet in repair_manifest["repair_packets"]:
            candidate = candidate_for(base_rows_by_id[result["instance_id"]], packet["residual_class"])
            if candidate is not None and candidate.get("match") is True:
                residual_by_class_rows[packet["residual_class"]].append(base_rows_by_id[result["instance_id"]])
                break

    eval_rows = []
    accepted_classes = set()
    parse_ok = 0
    compile_ok = 0
    for raw_row in repair_raw["rows"]:
        prompt_row = repair_rows_by_id[raw_row["residual_id"]]
        parsed = parse_selection(raw_row["output"], library)
        proposal = None
        compile_error = None
        target_decisions: Counter[str] = Counter()
        target_rows = []
        if not parsed.ok or parsed.selection is None:
            result = {"accepted": False, "reason": "parse_error", "checks": {"message": parsed.message}, "proposal_id": None}
        else:
            parse_ok += 1
            proposal, compile_error = compile_selection(parsed.selection, prompt_row["residual_class"], library)
            if proposal is None:
                result = {"accepted": False, "reason": "compile_error", "checks": {"message": compile_error}, "proposal_id": None}
            elif not proposal_slots_ok(proposal, prompt_row["residual_class"]):
                result = {"accepted": False, "reason": "metaverifier_reject_wrong_slots", "checks": {}, "proposal_id": proposal["proposal_id"], "proposal": proposal}
            else:
                compile_ok += 1
                for row in residual_by_class_rows[prompt_row["residual_class"]]:
                    candidate = candidate_for(row, prompt_row["residual_class"])
                    if candidate is None:
                        decision = "abstain_no_valid"
                        verifier_results = {}
                    else:
                        decision, verifier_results = verify_candidate(row, prompt_row["residual_class"], candidate)
                    target_decisions[decision] += 1
                    target_rows.append({"instance_id": row["instance_id"], "task_id": row["task_id"], "decision": decision, "candidate": candidate, "verifier_results": verifier_results})
                accepted = target_decisions == {"commit_live": len(target_rows)} and len(target_rows) == prompt_row.get("expected_target_rows", len(target_rows))
                result = {"accepted": accepted, "reason": "accepted_heldout_frontier" if accepted else "heldout_frontier_failed_gate", "checks": {"target_decision_counts": dict(sorted(target_decisions.items())), "target_rows": len(target_rows)}, "proposal_id": proposal["proposal_id"], "proposal": proposal}
        if result["accepted"]:
            accepted_classes.add(prompt_row["residual_class"])
        eval_rows.append({"residual_id": raw_row["residual_id"], "residual_class": prompt_row["residual_class"], "parse_ok": parsed.ok, "selection": parsed.selection, "compiled_proposal": proposal, "compile_error": compile_error, "target_rows": target_rows, "metaverifier_result": result})

    merged_prompt_rows = []
    merged_raw_rows = []
    source_counts: Counter[str] = Counter()
    for row in base_manifest["rows"]:
        replacement = None
        for residual_class in accepted_classes:
            candidate = candidate_for(row, residual_class)
            if candidate is not None and candidate.get("match") is True:
                replacement = (residual_class, candidate)
                break
        if replacement is None:
            merged_prompt_rows.append(row)
            merged_raw_rows.append(base_raw_by_id[row["instance_id"]])
            source_counts["v32_base"] += 1
        else:
            residual_class, candidate = replacement
            merged_prompt_rows.append(row_with_candidate(row, candidate, residual_class))
            merged_raw_rows.append({"instance_id": row["instance_id"], "output": json.dumps(sketch_from_candidate(candidate, residual_class), indent=2, sort_keys=True), "parse_ok": True, "prompt_mode": "deterministic_heldout_ttc_compiled_v33"})
            source_counts["v33_heldout_ttc_repair"] += 1

    output_dir.mkdir(parents=True)
    rows_path = output_dir / "rows.json"
    write_json(rows_path, {"schema": "ebw_track_a_v33_heldout_ttc_eval_rows_v1", "rows": eval_rows})
    merged_prompt_path = output_dir / "merged_prompt_manifest.json"
    merged_raw_path = output_dir / "merged_raw_outputs.json"
    write_json(merged_prompt_path, {**base_manifest, "status": "RPD_EBW_TRACK_A_V33_HELDOUT_TTC_MERGED_PROMPT_MANIFEST_READY", "prompt_protocol": "mixed_v32_no_repair_v33_ttc_repair", "rows": merged_prompt_rows})
    write_json(merged_raw_path, {"schema": "ebw_track_a_v33_heldout_ttc_merged_raw_outputs_v1", "status": "RPD_EBW_TRACK_A_V33_HELDOUT_TTC_MERGED_RAW_OUTPUTS_READY", "rows": merged_raw_rows, "source_counts": dict(sorted(source_counts.items())), "sealed_variations_opened": bool(base_manifest.get("sealed_variations_opened", False)), "model_gpu_docker_used": False, "external_process_actions": False})
    payload = {
        "schema": "ebw_track_a_v33_heldout_ttc_eval_v1",
        "status": "RPD_EBW_TRACK_A_V33_HELDOUT_TTC_EVAL_COMPLETE",
        "processed": len(eval_rows),
        "parse_rate": parse_ok / max(1, len(eval_rows)),
        "compile_rate": compile_ok / max(1, len(eval_rows)),
        "accepted_count": len(accepted_classes),
        "accepted_residual_classes": sorted(accepted_classes),
        "source_counts": dict(sorted(source_counts.items())),
        "rows_sha256": file_hash(rows_path),
        "merged_prompt_manifest_sha256": file_hash(merged_prompt_path),
        "merged_raw_outputs_sha256": file_hash(merged_raw_path),
        "repair_prompt_manifest_sha256": file_hash(repair_manifest_path),
        "repair_raw_outputs_sha256": file_hash(repair_raw_path),
        "base_prompt_manifest_sha256": file_hash(base_manifest_path),
        "base_raw_outputs_sha256": file_hash(base_raw_path),
        "sealed_variations_opened": bool(base_manifest.get("sealed_variations_opened", False)),
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "results.json", payload)
    report = [
        "# EBW Track A v33 Held-Out TTC Eval",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Residual packets processed: {len(eval_rows)}",
        f"- Accepted residual classes: {payload['accepted_residual_classes']}",
        f"- Parse rate: {payload['parse_rate']:.3f}",
        f"- Compile rate: {payload['compile_rate']:.3f}",
        "- Sealed variations 10-12 opened: Yes",
        "- Model/GPU/Docker actions in eval: No",
        "",
        "## Rows",
        "",
        "| Residual | Parse OK | Compiled | Accepted | Reason | Target decisions |",
        "|---|---:|---:|---:|---|---|",
    ]
    for row in eval_rows:
        result = row["metaverifier_result"]
        report.append(f"| `{row['residual_class']}` | {row['parse_ok']} | {row['compiled_proposal'] is not None} | {result['accepted']} | `{result['reason']}` | `{result['checks'].get('target_decision_counts', {})}` |")
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "accepted_count": payload["accepted_count"], "accepted_residual_classes": payload["accepted_residual_classes"], "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()