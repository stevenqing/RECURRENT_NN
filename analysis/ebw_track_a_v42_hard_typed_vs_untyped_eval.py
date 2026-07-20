"""Evaluate hard typed vs untyped RepairAgent selections for ordered-note residuals."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v33_heldout_ttc_eval import candidate_for, proposal_slots_ok, row_with_candidate, sketch_from_candidate, verify_candidate
from analysis.ebw_track_a_v29_frontier_closure_repair_policy import compile_selection, primitive_library
from analysis.ebw_track_a_v29_frontier_selection_eval import parse_selection

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


def evaluate_condition(condition: str, prompt_manifest: dict[str, Any], raw_outputs: dict[str, Any], base_manifest: dict[str, Any], baseline_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    library = primitive_library()
    prompt_row = prompt_manifest["rows"][0]
    raw_row = raw_outputs["rows"][0]
    parsed = parse_selection(raw_row["output"], library)
    proposal = None
    compile_error = None
    target_rows = []
    target_decisions: Counter[str] = Counter()
    base_by_id = {row["instance_id"]: row for row in base_manifest["rows"]}
    noncommit = [base_by_id[row["instance_id"]] for row in baseline_rows if row["decision"] != "commit_live"]
    if not parsed.ok or parsed.selection is None:
        result = {"accepted": False, "reason": "parse_error", "checks": {"message": parsed.message}, "proposal_id": None}
    else:
        proposal, compile_error = compile_selection(parsed.selection, prompt_row["residual_class"], library)
        if proposal is None:
            result = {"accepted": False, "reason": "compile_error", "checks": {"message": compile_error}, "proposal_id": None}
        elif not proposal_slots_ok(proposal, prompt_row["residual_class"]):
            result = {"accepted": False, "reason": "metaverifier_reject_wrong_slots", "checks": {"proposal": proposal}, "proposal_id": proposal["proposal_id"], "proposal": proposal}
        else:
            for row in noncommit:
                candidate = candidate_for(row, prompt_row["residual_class"])
                if candidate is None:
                    decision = "abstain_no_valid"
                    verifier_results = {}
                else:
                    decision, verifier_results = verify_candidate(row, prompt_row["residual_class"], candidate)
                target_decisions[decision] += 1
                target_rows.append({"instance_id": row["instance_id"], "task_id": row["task_id"], "decision": decision, "candidate": candidate, "verifier_results": verifier_results})
            accepted = target_decisions == {"commit_live": len(noncommit)}
            result = {"accepted": accepted, "reason": "accepted_hard_frontier" if accepted else "hard_frontier_failed_gate", "checks": {"target_decision_counts": dict(sorted(target_decisions.items())), "target_rows": len(noncommit)}, "proposal_id": proposal["proposal_id"], "proposal": proposal}
    eval_row = {"condition": condition, "residual_id": raw_row["residual_id"], "residual_class": prompt_row["residual_class"], "parse_ok": parsed.ok, "selection": parsed.selection, "compiled_proposal": proposal, "compile_error": compile_error, "target_rows": target_rows, "metaverifier_result": result}
    return eval_row, noncommit, target_rows


def build_merged(condition: str, eval_row: dict[str, Any], base_manifest: dict[str, Any], base_raw: dict[str, Any], residual_class: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    base_raw_by_id = {row["instance_id"]: row for row in base_raw["rows"]}
    accepted_ids = {row["instance_id"]: row["candidate"] for row in eval_row["target_rows"] if eval_row["metaverifier_result"]["accepted"] and row.get("candidate") is not None}
    prompt_rows = []
    raw_rows = []
    counts: Counter[str] = Counter()
    for row in base_manifest["rows"]:
        if row["instance_id"] in accepted_ids:
            candidate = accepted_ids[row["instance_id"]]
            prompt_rows.append(row_with_candidate(row, candidate, residual_class))
            raw_rows.append({"instance_id": row["instance_id"], "output": json.dumps(sketch_from_candidate(candidate, residual_class), indent=2, sort_keys=True), "parse_ok": True, "prompt_mode": f"deterministic_{condition}_hard_ttc_v42"})
            counts[f"v42_{condition}_repair"] += 1
        else:
            prompt_rows.append(row)
            raw_rows.append(base_raw_by_id[row["instance_id"]])
            counts["v41_base"] += 1
    return prompt_rows, raw_rows, dict(sorted(counts.items()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--typed-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v42_hard_typed_vs_untyped_prompt_manifests/typed_prompt_manifest.json"))
    parser.add_argument("--untyped-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v42_hard_typed_vs_untyped_prompt_manifests/untyped_prompt_manifest.json"))
    parser.add_argument("--typed-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v42_hard_typed_selection/raw_model_outputs.json"))
    parser.add_argument("--untyped-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v42_hard_untyped_selection/raw_model_outputs.json"))
    parser.add_argument("--base-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v41_hard_target_prompt_manifest/prompt_manifest.json"))
    parser.add_argument("--base-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v41_hard_target_no_repair/raw_model_outputs.json"))
    parser.add_argument("--baseline-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v41_hard_target_no_repair/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v42_hard_typed_vs_untyped"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v42 hard typed/untyped eval")

    typed_manifest_path = resolve(args.typed_prompt_manifest)
    untyped_manifest_path = resolve(args.untyped_prompt_manifest)
    typed_raw_path = resolve(args.typed_raw_outputs)
    untyped_raw_path = resolve(args.untyped_raw_outputs)
    base_manifest_path = resolve(args.base_prompt_manifest)
    base_raw_path = resolve(args.base_raw_outputs)
    baseline_rows_path = resolve(args.baseline_rows)
    typed_manifest = load_json(typed_manifest_path)
    untyped_manifest = load_json(untyped_manifest_path)
    typed_raw = load_json(typed_raw_path)
    untyped_raw = load_json(untyped_raw_path)
    base_manifest = load_json(base_manifest_path)
    base_raw = load_json(base_raw_path)
    baseline_rows = load_json(baseline_rows_path)["rows"]
    typed_eval, _noncommit, _typed_targets = evaluate_condition("typed", typed_manifest, typed_raw, base_manifest, baseline_rows)
    untyped_eval, _noncommit, _untyped_targets = evaluate_condition("untyped", untyped_manifest, untyped_raw, base_manifest, baseline_rows)
    residual_class = typed_manifest["rows"][0]["residual_class"]
    output_dir.mkdir(parents=True)
    rows_path = output_dir / "rows.json"
    write_json(rows_path, {"schema": "ebw_track_a_v42_hard_typed_vs_untyped_eval_rows_v1", "rows": [typed_eval, untyped_eval]})
    for condition, eval_row in [("typed", typed_eval), ("untyped", untyped_eval)]:
        prompt_rows, raw_rows, source_counts = build_merged(condition, eval_row, base_manifest, base_raw, residual_class)
        write_json(output_dir / f"{condition}_merged_prompt_manifest.json", {**base_manifest, "status": f"RPD_EBW_TRACK_A_V42_HARD_{condition.upper()}_MERGED_PROMPT_READY", "prompt_protocol": f"mixed_v41_hard_{condition}_v42", "rows": prompt_rows, "source_counts": source_counts})
        write_json(output_dir / f"{condition}_merged_raw_outputs.json", {"schema": f"ebw_track_a_v42_hard_{condition}_merged_raw_outputs_v1", "status": f"RPD_EBW_TRACK_A_V42_HARD_{condition.upper()}_MERGED_RAW_READY", "rows": raw_rows, "source_counts": source_counts, "sealed_variations_opened": True})
    payload = {
        "schema": "ebw_track_a_v42_hard_typed_vs_untyped_eval_v1",
        "status": "RPD_EBW_TRACK_A_V42_HARD_TYPED_VS_UNTYPED_EVAL_COMPLETE",
        "typed_accepted": typed_eval["metaverifier_result"]["accepted"],
        "untyped_accepted": untyped_eval["metaverifier_result"]["accepted"],
        "typed_reason": typed_eval["metaverifier_result"]["reason"],
        "untyped_reason": untyped_eval["metaverifier_result"]["reason"],
        "target_rows": typed_eval["metaverifier_result"]["checks"].get("target_rows") or untyped_eval["metaverifier_result"]["checks"].get("target_rows"),
        "rows_sha256": file_hash(rows_path),
        "typed_prompt_manifest_sha256": file_hash(typed_manifest_path),
        "untyped_prompt_manifest_sha256": file_hash(untyped_manifest_path),
        "typed_raw_outputs_sha256": file_hash(typed_raw_path),
        "untyped_raw_outputs_sha256": file_hash(untyped_raw_path),
        "baseline_rows_sha256": file_hash(baseline_rows_path),
        "claim_boundary": "Exploratory hard pass-subset only; v39 hard held-out protocol was blocked.",
        "sealed_variations_opened": True,
    }
    write_json(output_dir / "results.json", payload)
    report = [
        "# EBW Track A v42 Hard Typed vs Untyped Eval",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        "- Claim boundary: exploratory hard pass-subset only; v39 hard held-out protocol was blocked.",
        f"- Target rows: {payload['target_rows']}",
        "",
        "| Condition | Accepted | Reason | Selection |",
        "|---|---:|---|---|",
    ]
    for row in [typed_eval, untyped_eval]:
        selection = row["selection"]
        report.append(f"| `{row['condition']}` | {row['metaverifier_result']['accepted']} | `{row['metaverifier_result']['reason']}` | `{selection}` |")
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "typed_accepted": payload["typed_accepted"], "untyped_accepted": payload["untyped_accepted"], "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()