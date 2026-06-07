"""Stage A adapter wiring preflight artifact.

This does not run autonomous solving. It proves the reconstructed parent artifact
contract and register smoke path are wired enough for later G1 work.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import torch

from experiments.stage_a_backtrack_loop import build_grid, preflight, smoke


def _torch_payload_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    payload = torch.load(path, map_location="cpu", weights_only=False)
    config = payload.get("config", {}) if isinstance(payload, dict) else {}
    return {
        "path": str(path),
        "exists": True,
        "kind": payload.get("kind") if isinstance(payload, dict) else None,
        "model_class": payload.get("model_class") if isinstance(payload, dict) else None,
        "config": config,
    }


def run_adapter_wiring(
    output_dir: str = "results/stage_a_adapter_wiring",
    operator_ckpt: str = "artifacts/stage_a/recurrent_solver_b1a_clean_l2_tied_p96_e300_seed102.pt",
    bridge_decoder: str = "artifacts/stage_a/item142_factored_cell_digit_decoder_depth8_D128.pt",
    teacher_trace: str = "artifacts/stage_a/internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl",
    device: str = "cpu",
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    pre = preflight(operator_ckpt, bridge_decoder, teacher_trace, output_dir, Path.cwd())
    smoke_payload = smoke(str(out / "smoke"), operator_ckpt, bridge_decoder, teacher_trace, num_shards=1, shard_index=0, device=device)
    operator_summary = _torch_payload_summary(Path(operator_ckpt))
    bridge_summary = _torch_payload_summary(Path(bridge_decoder))
    trace_path = Path(teacher_trace)
    trace_lines = 0
    if trace_path.exists():
        with trace_path.open("r", encoding="utf-8") as handle:
            trace_lines = sum(1 for _ in handle)
    payload = {
        "module": "stage_a_adapter_wiring",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if pre.get("status") == "READY" and smoke_payload.get("status") == "SMOKE_PASS" else "FAIL",
        "autonomous_solve_status": "NOT_RUN",
        "preflight_status": pre.get("status"),
        "preflight_checks": pre.get("checks", []),
        "register_smoke_status": smoke_payload.get("status"),
        "register_checks": smoke_payload.get("register_checks", {}),
        "grid_cells": len(build_grid()),
        "operator_ckpt": operator_summary,
        "bridge_decoder": bridge_summary,
        "teacher_trace": {"path": teacher_trace, "exists": trace_path.exists(), "tasks": trace_lines},
        "decision": "adapter_contract_wired_but_autonomous_loop_not_proven",
    }
    (out / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record Stage A adapter wiring status.")
    parser.add_argument("--output-dir", default="results/stage_a_adapter_wiring")
    parser.add_argument("--operator-ckpt", default="artifacts/stage_a/recurrent_solver_b1a_clean_l2_tied_p96_e300_seed102.pt")
    parser.add_argument("--bridge-decoder", default="artifacts/stage_a/item142_factored_cell_digit_decoder_depth8_D128.pt")
    parser.add_argument("--teacher-trace", default="artifacts/stage_a/internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    run_adapter_wiring(args.output_dir, args.operator_ckpt, args.bridge_decoder, args.teacher_trace, args.device)
