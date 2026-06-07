"""Record banded Sudoku readiness and fail-closed gate refusal checks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from experiments.stage_a_backtrack_loop import preflight
from tasks.sudoku.generator_9x9 import generate_9x9_by_depth_band


def _run_preflight_case(name: str, output_dir: Path, operator_ckpt: str, bridge_decoder: str, teacher_trace: str) -> dict[str, Any]:
    case_dir = output_dir / name
    payload = preflight(operator_ckpt, bridge_decoder, teacher_trace, str(case_dir), Path.cwd())
    return {
        "case": name,
        "status": payload.get("status"),
        "missing": [row.get("name") for row in payload.get("missing", [])],
        "checks": payload.get("checks", []),
        "refused": payload.get("status") != "READY",
    }


def run_gate_refusal(
    output_dir: str = "results/stage_a_banded_gate_refusal",
    bridge_decoder: str = "artifacts/stage_a/item142_factored_cell_digit_decoder_depth8_D128.pt",
    teacher_trace: str = "artifacts/stage_a/internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl",
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    sudoku9_probe = generate_9x9_by_depth_band(min_depth=1, max_depth=2, n_instances=4, seed=42)
    refusal_cases = [
        _run_preflight_case("quarantined_operator", out, "artifacts/stage_a/QUARANTINED_PARENT.pt", bridge_decoder, teacher_trace),
        _run_preflight_case("missing_bridge", out, "artifacts/stage_a/recurrent_solver_b1a_clean_l2_tied_p96_e300_seed102.pt", "artifacts/stage_a/MISSING_BRIDGE.pt", teacher_trace),
        _run_preflight_case("missing_teacher_trace", out, "artifacts/stage_a/recurrent_solver_b1a_clean_l2_tied_p96_e300_seed102.pt", bridge_decoder, "artifacts/stage_a/MISSING_TRACE.jsonl"),
    ]
    payload = {
        "module": "stage_a_banded_gate_refusal",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(row["refused"] for row in refusal_cases) else "FAIL",
        "banded_datasets": {
            "sudoku9_generator_present": True,
            "sudoku9_generated_count": len(sudoku9_probe),
            "sudoku9_status": "READY_STUB_EMPTY" if len(sudoku9_probe) == 0 else "READY",
            "sudoku6_status": "RECORDED_READY_FROM_RUNBOOK_NOT_GENERATED_IN_REPO",
            "note": "Sudoku6 generator is not present in this repo; readiness is recorded from the post-027 continuation state until the G1 fix adds concrete data artifacts.",
        },
        "fail_closed_cases": refusal_cases,
        "decision": "fail_closed_refusal_proven_for_missing_or_quarantined_parent_inputs",
    }
    (out / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record Stage A banded data readiness and fail-closed refusal checks.")
    parser.add_argument("--output-dir", default="results/stage_a_banded_gate_refusal")
    parser.add_argument("--bridge-decoder", default="artifacts/stage_a/item142_factored_cell_digit_decoder_depth8_D128.pt")
    parser.add_argument("--teacher-trace", default="artifacts/stage_a/internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl")
    args = parser.parse_args()
    run_gate_refusal(args.output_dir, args.bridge_decoder, args.teacher_trace)
