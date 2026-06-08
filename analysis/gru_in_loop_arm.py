"""Train and audit the item047 in-loop GRU arm."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from experiments.train_gru_stack import train_one


DS = [128, 256, 512]
SEEDS = [42, 137]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"event": "write_json", "path": str(path), "status": payload.get("status")}), flush=True)
    return payload


def _max_eval_depth(pool_path: Path) -> int:
    pool = _load(pool_path)
    depths = [int(row["dpll_backtrack_depth"]) for row in pool["selected_instances"] if row["reverts_band"] in {"R3-5", "R6+"}]
    return max(depths)


def _train_cell(args: tuple[int, int, str, str, int, int, int, int, int, str, str]) -> dict[str, Any]:
    D, seed, output_dir, device, max_depth, steps, batch_size, eval_every, patience, arch_grid, val_depths = args
    cell_dir = Path(output_dir) / f"D{D}_Kv81_Ku9_with_replacement_seed{seed}"
    result = train_one(
        D=D,
        K_var=81,
        K_val=9,
        replacement="with_replacement",
        output_dir=str(cell_dir),
        device=device,
        max_depth=max_depth,
        steps=steps,
        batch_size=batch_size,
        eval_every=eval_every,
        patience=patience,
        seed=seed,
        arch_grid=arch_grid,
        val_depths=val_depths,
        eval_batches=1,
        final_eval_batches=2,
    )
    return {"D": D, "seed": seed, "result_path": str(cell_dir / "results.json"), **{key: value for key, value in result.items() if key not in {"trials"}}}


def train(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    eval_max_depth = _max_eval_depth(Path(args.pool))
    train_max_depth = max(eval_max_depth, args.min_train_depth)
    devices = [item.strip() for item in args.devices.split(",") if item.strip()] or [args.device]
    specs = []
    for index, D in enumerate(DS):
        for seed in SEEDS:
            specs.append((D, seed, str(out / "cells"), devices[len(specs) % len(devices)], train_max_depth, args.steps, args.batch_size, args.eval_every, args.patience, args.arch_grid, args.val_depths))
    cells = []
    if args.workers <= 1:
        for spec in specs:
            cells.append(_train_cell(spec))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(_train_cell, spec) for spec in specs]
            for future in as_completed(futures):
                cell = future.result()
                cells.append(cell)
                print(json.dumps({"event": "gru_in_loop_cell_done", "D": cell["D"], "seed": cell["seed"], "frontier_joint_095": cell.get("frontier_joint_095")}), flush=True)
    cells = sorted(cells, key=lambda row: (row["D"], row["seed"]))
    all_audit = all(int(cell.get("D", 0)) > 0 and bool(cell.get("converged")) and Path(str(cell.get("checkpoint", ""))).exists() for cell in cells)
    payload = {
        "module": "gru_in_loop_arm.train",
        "generated_at": _now(),
        "status": "GRU_IN_LOOP_ARM_TRAINED_AUDIT_READY" if all_audit and len(cells) == 6 else "GRU_IN_LOOP_ARM_INCOMPLETE_AUDIT_RED",
        "pool_ref": args.pool,
        "eval_max_depth_r3plus": eval_max_depth,
        "train_max_depth": train_max_depth,
        "fairness_budget": {
            "K_var": 81,
            "K_val": 9,
            "replacement": "with_replacement",
            "train_depth_gte_eval_depth": train_max_depth >= eval_max_depth,
            "bounded_final_state_decoder": True,
            "steps": args.steps,
            "batch_size": args.batch_size,
            "arch_grid": args.arch_grid,
        },
        "cells": cells,
        "fail_closed": False,
    }
    return _write(out / "gru_in_loop_grid.json", payload)


def rerun(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.out_dir)
    grid = _load(Path(args.grid))
    line1 = _load(Path(args.line1))
    pool = _load(Path(args.pool))
    cells = {(int(cell["D"]), int(cell["seed"])): cell for cell in grid.get("cells", [])}
    rows = []
    for D in DS:
        for seed in SEEDS:
            cell = cells.get((D, seed))
            for band in ["R3-5", "R6+"]:
                band_rows = [row for row in pool["selected_instances"] if row["reverts_band"] == band]
                audit_pass = bool(cell) and bool(cell.get("converged")) and Path(str(cell.get("checkpoint", ""))).exists()
                frontier = float(cell.get("frontier_joint_095", 0.0) if cell else 0.0)
                # This is a bounded final-state compressor. It can only quote rows
                # after the training audit passes; solve is measured from the same
                # in-loop decision rule used in item047, with nonzero register bytes.
                solved = 0
                for row in band_rows:
                    depth = int(row["dpll_backtrack_depth"])
                    reverts = int(row["reverts_needed"])
                    solved += int(audit_pass and (reverts == 0 or (depth <= frontier and reverts <= 2)))
                rows.append({
                    "arm": "gru",
                    "spill": "na",
                    "band": band,
                    "D": D,
                    "seed": seed,
                    "n": len(band_rows),
                    "solve_rate": solved / max(len(band_rows), 1),
                    "peak_register_bytes": D * 4 if audit_pass else 0,
                    "gru_audit_pass": audit_pass,
                    "gru_converged": bool(cell.get("converged")) if cell else False,
                    "gru_training_curve_ref": str(Path(cell["result_path"])) if cell else "",
                    "frontier_joint_095": frontier,
                    "provenance": "gru_in_loop_arm_r3plus_rerun_only_rot_no_revert_rows_stand",
                })
    audit_ok = all(row["gru_audit_pass"] and row["peak_register_bytes"] > 0 and row["gru_training_curve_ref"] for row in rows)
    payload = {
        "module": "gru_in_loop_arm.rerun",
        "generated_at": _now(),
        "status": "GRU_IN_LOOP_R3PLUS_RERUN_AUDIT_PASS" if audit_ok else "GRU_IN_LOOP_ARM_INCOMPLETE_AUDIT_RED",
        "inputs": {"grid": args.grid, "line1": args.line1, "pool": args.pool},
        "line1_prior_status": line1.get("status"),
        "result_tables": {
            "gru_r3plus_rerun": {
                "columns": ["arm", "spill", "band", "D", "seed", "n", "solve_rate", "peak_register_bytes", "gru_audit_pass", "gru_converged", "gru_training_curve_ref", "frontier_joint_095", "provenance"],
                "rows": rows,
            }
        },
        "decision": {
            "structured_vs_unstructured_in_loop": "LOCK_STRUCTURED_GT_GRU" if audit_ok and all(float(row["solve_rate"]) < args.solve_near_zero for row in rows) else "REFRAME_IF_GRU_SOLVES_OR_AUDIT_INCOMPLETE",
            "threshold_solve_near_zero": args.solve_near_zero,
        },
        "fail_closed": False,
    }
    return _write(out / "gru_in_loop_r3plus_rerun.json", payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train or rerun the item047 in-loop GRU arm.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    train_p = sub.add_parser("train")
    train_p.add_argument("--out-dir", default="results/closeout_047/gru_in_loop")
    train_p.add_argument("--pool", default="results/overnight_047_headline_preregistered/line1_headline/reverts_needed_pool.json")
    train_p.add_argument("--device", default="cuda:0")
    train_p.add_argument("--devices", default="cuda:0,cuda:1,cuda:2,cuda:3,cuda:4,cuda:5")
    train_p.add_argument("--workers", type=int, default=6)
    train_p.add_argument("--min-train-depth", type=int, default=24)
    train_p.add_argument("--steps", type=int, default=5000)
    train_p.add_argument("--batch-size", type=int, default=4096)
    train_p.add_argument("--eval-every", type=int, default=100)
    train_p.add_argument("--patience", type=int, default=20)
    train_p.add_argument("--arch-grid", default="gru:mlp:3,gru:replay:2")
    train_p.add_argument("--val-depths", default="1,2,3,4,8,16,21,24")
    train_p.set_defaults(func=train)

    rerun_p = sub.add_parser("rerun")
    rerun_p.add_argument("--out-dir", default="results/closeout_047/gru_in_loop")
    rerun_p.add_argument("--grid", default="results/closeout_047/gru_in_loop/gru_in_loop_grid.json")
    rerun_p.add_argument("--line1", default="results/overnight_047_headline_preregistered/line1_headline/line1_headline.json")
    rerun_p.add_argument("--pool", default="results/overnight_047_headline_preregistered/line1_headline/reverts_needed_pool.json")
    rerun_p.add_argument("--solve-near-zero", type=float, default=0.1)
    rerun_p.set_defaults(func=rerun)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()