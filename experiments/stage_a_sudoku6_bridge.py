"""Sudoku6 bridge G1 diagnostic and fail-closed placeholder.

The current repository does not contain the Sudoku6 bridge trainer yet. This
entrypoint records the blocker explicitly and defines the result schema that the
future G1 fix must turn green.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def _trace_stats(path: Path, max_lines: int = 256) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    action_counts: Counter[str] = Counter()
    max_depth = 0
    lines = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if lines >= max_lines:
                break
            lines += 1
            row = json.loads(line)
            max_depth = max(max_depth, int(row.get("max_backtrack_depth", 0)))
            for step in row.get("steps", []):
                action_counts[str(step.get("action"))] += 1
    return {"path": str(path), "exists": True, "sampled_tasks": lines, "sampled_max_backtrack_depth": max_depth, "sampled_action_counts": dict(action_counts)}


def run_diagnosis(
    output_dir: str = "results/stage_a_sudoku6_bridge",
    teacher_trace: str = "artifacts/stage_a/internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl",
    mode: str = "diagnose",
    seed: int = 102,
    device: str = "cpu",
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    trace = _trace_stats(Path(teacher_trace))
    training_curve_summary = {
        "initial_loss": None,
        "final_loss": None,
        "moved": False,
        "provenance": "measured: no Sudoku6 bridge trainer artifact exists in this repo yet",
    }
    single_step_by_depth = [
        {
            "depth_into_solution": 1,
            "n_states": 0,
            "forced_precision": None,
            "forced_recall": None,
            "provenance": "measured: no Sudoku6 diagnostic states available",
        },
        {
            "depth_into_solution": 2,
            "n_states": 0,
            "forced_precision": None,
            "forced_recall": None,
            "provenance": "measured: no Sudoku6 diagnostic states available",
        },
    ]
    stick_histogram = {
        "no_commit": 0,
        "wrong_commit": 0,
        "criterion_never_met": 1,
        "missing_bridge_trainer": 1,
        "missing_sudoku6_dataset_generator": 1,
        "parent_adapter_not_integrated": 1,
    }
    encoding_byte_diff = {
        "identical": None,
        "diff_bytes": None,
        "status": "NOT_COMPUTED_NO_SUDOKU6_ENCODING_ARTIFACT",
        "provenance": "measured: encoding artifacts absent",
    }
    decision_branch = {
        "branch": "objective_wiring",
        "deciding_numbers": {
            "n_single_step_states": sum(row["n_states"] for row in single_step_by_depth),
            "criterion_never_met": stick_histogram["criterion_never_met"],
            "G1": 0.0,
        },
        "reason": "Diagnosis cannot reach budget-vs-criterion arbitration because the Sudoku6 trainer/data generator and parent adapter integration are absent; fix wiring/data first.",
    }
    payload = {
        "module": "stage_a_sudoku6_bridge",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "seed": seed,
        "device": device,
        "status": "BLOCKED_G1_ZERO",
        "G1": 0.0,
        "single_step_forced_accuracy": 0.0,
        "training_curve_summary": training_curve_summary,
        "single_step_forced_precision_recall_by_depth": single_step_by_depth,
        "iterative_stick_reason_histogram": stick_histogram,
        "train_eval_encoding_byte_diff": encoding_byte_diff,
        "encoding_byte_diff_status": encoding_byte_diff["status"],
        "decision_branch": decision_branch,
        "teacher_trace_probe": trace,
        "reverts_nonzero_on_L4": False,
        "forward_floor_on_L4": False,
        "gates": {
            "G1_depth1_bridge": "FAIL",
            "G2_depth_frontier": "NOT_RUN",
            "L4_reverts_nonzero": "FAIL_NOT_RUN",
            "L4_forward_floor": "FAIL_NOT_RUN"
        },
        "next_action": "Implement Task A diagnosis and Task B deep-supervision bridge trainer from specs/g1_fix_spec.md.",
    }
    (out / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record the current Sudoku6 bridge G1 blocker.")
    parser.add_argument("--mode", choices=["diagnose", "train"], default="diagnose")
    parser.add_argument("--output-dir", default="results/stage_a_sudoku6_bridge")
    parser.add_argument("--teacher-trace", default="artifacts/stage_a/internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl")
    parser.add_argument("--seed", type=int, default=102)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    run_diagnosis(args.output_dir, args.teacher_trace, args.mode, args.seed, args.device)
