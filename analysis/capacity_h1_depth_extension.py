"""Non-shallow operator restore checks on bounded SAT and Sudoku nodes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from experiments.capacity.common import env_payload, instantiate_operator, resolve_device
from experiments.capacity.gate import operator_restore_gate


def _sudoku_solution() -> dict[tuple[int, int], int]:
    return {(row, col): ((row * 3 + row // 3 + col) % 9) + 1 for row in range(9) for col in range(9)}


def _conditions() -> list[dict[str, Any]]:
    rows = []
    for depth in (64, 128, 256):
        rows.append({
            "task_type": "general_sat",
            "depth": depth,
            "givens": {"n_vars": 256, "clauses": []},
            "partial": {index: (index % 2) for index in range(1, depth + 1)},
        })
    sudoku = _sudoku_solution()
    ordered = sorted(sudoku)
    for depth in (64, 81):
        rows.append({
            "task_type": "sudoku_9x9",
            "depth": depth,
            "givens": {},
            "partial": {cell: sudoku[cell] for cell in ordered[:depth]},
        })
    return rows


def run(model: str, device: str, dtype: str) -> dict[str, Any]:
    operator = instantiate_operator(model, resolve_device(device), dtype, load_model=True)
    rows = []
    for condition in _conditions():
        step = operator.forward_step(condition["task_type"], condition["givens"], condition["partial"])
        if step.past_key_values is None or step.logits is None:
            raise RuntimeError("operator did not expose cache/logits for depth extension")
        restored_state = {
            "past_key_values": step.past_key_values,
            "feed_token_id": int(step.logits.argmax(dim=-1)[0].item()),
        }
        gate = operator_restore_gate(
            operator,
            {"task_type": condition["task_type"]},
            condition["givens"],
            condition["partial"],
            restored_state,
        )
        rows.append({
            "task_type": condition["task_type"],
            "depth": int(condition["depth"]),
            "measurement_scope": "bounded_current_node_cache_restore",
            **gate,
        })
        print(json.dumps({"task_type": condition["task_type"], "depth": condition["depth"], "decision_agreement": gate["decision_agreement"], "within_noise_floor": gate["within_noise_floor"]}), flush=True)
    return {
        "schema": "operator_restore_depth_extension_v5",
        "model": model,
        "dtype": dtype,
        "env": env_payload(dtype),
        "rows": rows,
        "pass": all(float(row["decision_agreement"]) == 1.0 and bool(row["within_noise_floor"]) for row in rows),
        "scope_note": "Tests restored cache behavior at deep bounded current nodes; these are not generated backtracking traces.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SAT/Sudoku non-shallow operator restore checks.")
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32")
    parser.add_argument("--out", default="results/capacity/H1_operator_depth_extension_qwen3_fp32.json")
    args = parser.parse_args()
    payload = run(args.model, args.device, args.dtype)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(out), "pass": payload["pass"]}), flush=True)


if __name__ == "__main__":
    main()
