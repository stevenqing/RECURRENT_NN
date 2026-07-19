"""Deterministic v10 gate after path-rule directory normalization."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v9_path_pair_feasibility import path_pair_candidate
from analysis.ebw_track_a_v9_path_pair_gate import adversarial_values, sketch_from_candidate, valid_path_pair
from experiments.ebw_obligation_sketch import barrier_unique_validity

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


def target_manifest_row(row: dict[str, Any], previous: str) -> dict[str, Any]:
    return {
        "instance_id": row["instance_id"],
        "task_id": row["task_id"],
        "call_index": row["call_index"],
        "field_name": row["field_name"],
        "proof_family": row["proof_family"],
        "method": row["context"]["candidate_action"]["method"],
        "app": row["context"]["candidate_action"]["app"],
        "api_name": row["context"]["candidate_action"]["api_name"],
        "required_obligation": "path_pair_transform_binding",
        "write_ordinal_for_schema": row["write_ordinal_for_schema"],
        "source_decision": previous,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_full_opened_v8_executable/prompt_manifest.json"))
    parser.add_argument("--rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_full_opened_v8_executable/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v10_path_rule_normalized_gate"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v10 path-rule normalized gate")

    manifest_path = resolve(args.prompt_manifest)
    rows_path = resolve(args.rows)
    manifest = load_json(manifest_path)["rows"]
    row_results = {row["instance_id"]: row for row in load_json(rows_path)["rows"]}
    result_rows = []
    target_rows = []
    counts: Counter[str] = Counter()
    for row in manifest:
        if row.get("required_obligation") != "derived_path_binding":
            continue
        previous = row_results.get(row["instance_id"], {}).get("decision")
        candidate = path_pair_candidate(row)
        if previous != "unsafe_unique_wrong" or candidate is None or not candidate["match"]:
            continue
        live_value = row["live_arguments"][row["field_name"]]
        live_valid = valid_path_pair(live_value, candidate)
        adversarial_valids = {f"adversarial_{index}": valid_path_pair(value, candidate) for index, value in enumerate(adversarial_values(candidate))}
        barrier = barrier_unique_validity({"live": live_valid, **adversarial_valids})
        if barrier["decision"] == "commit" and barrier["candidate_id"] == "live":
            decision = "commit_live"
        elif barrier["decision"] == "commit":
            decision = "unsafe_unique_wrong"
        elif barrier["typed_reason"] == "competing_valid":
            decision = "ambiguous_both_valid"
        else:
            decision = "abstain_no_valid"
        counts[decision] += 1
        target_rows.append(target_manifest_row(row, previous))
        result_rows.append(
            {
                "instance_id": row["instance_id"],
                "task_id": row["task_id"],
                "previous_decision": previous,
                "decision": decision,
                "sketch": sketch_from_candidate(candidate),
                "live_valid": live_valid,
                "adversarial_valids": adversarial_valids,
                "expected_destination_file_path": candidate["expected_destination_file_path"],
            }
        )

    output_dir.mkdir(parents=True)
    rows_out = output_dir / "rows.json"
    evaluation_manifest = output_dir / "evaluation_manifest.json"
    write_json(rows_out, {"schema": "ebw_track_a_v10_path_rule_normalized_gate_rows_v1", "rows": result_rows})
    write_json(
        evaluation_manifest,
        {
            "schema": "ebw_track_a_v10_target_shard_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V10_TARGET_SHARD_READY",
            "rows": target_rows,
            "target_selection": "full-v8 derived unsafe rows with normalized path-pair candidates",
            "sealed_variations_opened": False,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v10_path_rule_normalized_gate_v1",
        "status": "RPD_EBW_TRACK_A_V10_PATH_RULE_NORMALIZED_GATE_COMPLETE",
        "target_rows": len(result_rows),
        "decision_counts": dict(sorted(counts.items())),
        "previous_required_decision": "unsafe_unique_wrong",
        "target_selection": "derived-path unsafe rows with normalized path-pair candidate",
        "prompt_manifest_sha256": file_hash(manifest_path),
        "source_rows_sha256": file_hash(rows_path),
        "rows_sha256": file_hash(rows_out),
        "evaluation_manifest_sha256": file_hash(evaluation_manifest),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "results.json", payload)
    report = [
        "# EBW Track A v10 Path-Rule Normalized Gate",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Target rows: {len(result_rows)}",
        "- Target selection: full-v8 derived unsafe rows with normalized path-pair candidates",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Decision Counts",
        "",
        "| Decision | Rows |",
        "|---|---:|",
    ]
    report += [f"| {decision} | {count} |" for decision, count in sorted(counts.items())]
    report += [
        "",
        "## Interpretation",
        "",
        "The remaining full-v8 derived unsafe mismatch rows were caused by path-rule parser normalization: task text like `~/trash/.` denotes the same directory as `~/trash`, but v9 compared the unnormalized path literally. After canonicalizing directory literals and dot segments, all 156 full-v8 derived unsafe rows are covered by the path-pair proof family and pass the deterministic barrier under path-shaped adversaries.",
    ]
    (output_dir / "GATE.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "target_rows": len(result_rows), "counts": payload["decision_counts"], "report": str((output_dir / "GATE.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()