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
    payload = {
        "module": "stage_a_sudoku6_bridge",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "seed": seed,
        "device": device,
        "status": "BLOCKED_G1_ZERO",
        "G1": 0.0,
        "single_step_forced_accuracy": 0.0,
        "iterative_stick_reason_histogram": {
            "bridge_trainer_missing": 1,
            "sudoku6_dataset_generator_missing": 1,
            "parent_adapter_not_integrated": 1
        },
        "train_eval_encoding_byte_diff": None,
        "encoding_byte_diff_status": "NOT_COMPUTED_NO_SUDOKU6_ENCODING_ARTIFACT",
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
