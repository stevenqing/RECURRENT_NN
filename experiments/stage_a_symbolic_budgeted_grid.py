"""Subprocess-budgeted Track A symbolic grid launcher.

This wrapper exists because Track A rot-register cells can spend long stretches in
small PyTorch cleanup/reconstruction calls. Python-level timers cannot reliably
interrupt those inner calls, but subprocess timeouts can fail-close one cell
without losing the rest of the grid.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.stage_a_symbolic_oracle import OPERATOR, SOURCE, TRACK, build_eval_tasks, build_track_a_grid, statelessness_ci, write_report


def _text_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _timeout_cell(cell: Any, n_tasks: int, task_family: str, timeout_seconds: float, path: Path) -> dict[str, Any]:
    return {
        "cell_index": cell.cell_index,
        "cell_name": cell.name,
        "track": TRACK,
        "operator": OPERATOR,
        "source": SOURCE,
        "arm": cell.arm,
        "D": cell.D,
        "seed": cell.seed,
        "spill": cell.spill,
        "arbiter": cell.arbiter,
        "task_family": task_family,
        "n_episodes": 0,
        "solve_rate": 0.0,
        "solved": 0,
        "depths": [],
        "max_solve_depth": 0,
        "applied_reverts": 0,
        "revert_success": False,
        "mean_nodes": 0.0,
        "peak_depth": 0,
        "peak_register_bytes": 0,
        "overflow_entries": 0,
        "decode_failures": 0,
        "timeout_count": n_tasks,
        "status": "CELL_TIMEOUT",
        "timeout_seconds": timeout_seconds,
        "path": str(path),
    }


def _run_one_cell(
    cell: Any,
    root: Path,
    logs: Path,
    n_tasks: int,
    task_family: str,
    n_instances: int,
    min_depth: int,
    max_depth: int,
    seed: int,
    max_nodes: int,
    per_cell_timeout: float,
    device: str,
    torch_threads: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cell_dir = root / f"cell_{cell.cell_index:03d}"
    cell_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs / f"cell_{cell.cell_index:03d}.stdout"
    stderr_path = logs / f"cell_{cell.cell_index:03d}.stderr"
    result_path = cell_dir / "results.json"
    cmd = [
        sys.executable,
        "-m",
        "experiments.stage_a_symbolic_oracle",
        "--output-dir",
        str(cell_dir),
        "--task-family",
        task_family,
        "--n-instances",
        str(n_instances),
        "--min-depth",
        str(min_depth),
        "--max-depth",
        str(max_depth),
        "--seed",
        str(seed),
        "--max-nodes",
        str(max_nodes),
        "--device",
        device,
        "--torch-threads",
        str(torch_threads),
        "--cell-index",
        str(cell.cell_index),
    ]
    try:
        completed = subprocess.run(cmd, text=True, capture_output=True, timeout=per_cell_timeout, check=False)
        stdout_path.write_text(_text_output(completed.stdout), encoding="utf-8")
        stderr_path.write_text(_text_output(completed.stderr), encoding="utf-8")
        if completed.returncode == 0 and result_path.exists():
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            cell_rows = payload.get("cells", [])
            if cell_rows:
                status = "CELL_RECORDED"
                rows = cell_rows
            else:
                status = "CELL_EMPTY_FAIL_CLOSED"
                rows = [_timeout_cell(cell, n_tasks, task_family, per_cell_timeout, result_path)]
        else:
            status = "CELL_SUBPROCESS_FAILED_CLOSED"
            rows = [_timeout_cell(cell, n_tasks, task_family, per_cell_timeout, result_path)]
        run = {"cell_index": cell.cell_index, "cell_name": cell.name, "status": status, "returncode": completed.returncode, "stdout": str(stdout_path), "stderr": str(stderr_path), "result_path": str(result_path), "command": cmd}
        return rows, run
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(_text_output(exc.stdout), encoding="utf-8")
        stderr_path.write_text(_text_output(exc.stderr), encoding="utf-8")
        rows = [_timeout_cell(cell, n_tasks, task_family, per_cell_timeout, result_path)]
        run = {"cell_index": cell.cell_index, "cell_name": cell.name, "status": "CELL_TIMEOUT_FAIL_CLOSED", "returncode": None, "stdout": str(stdout_path), "stderr": str(stderr_path), "result_path": str(result_path), "command": cmd}
        return rows, run


def run_budgeted_grid(
    output_dir: str = "results/stage_a_symbolic_budgeted",
    task_family: str = "sudoku6",
    n_instances: int = 8,
    min_depth: int = 1,
    max_depth: int = 4,
    seed: int = 2,
    max_nodes: int = 64,
    per_cell_timeout: float = 12.0,
    device: str = "cpu",
    torch_threads: int = 1,
    workers: int = 1,
    cell_indices: set[int] | None = None,
) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    tasks = build_eval_tasks(task_family, n_instances, seed, min_depth, max_depth)
    grid = build_track_a_grid(task_family)
    if cell_indices is not None:
        grid = [cell for cell in grid if cell.cell_index in cell_indices]
    stateless = statelessness_ci(output_dir)
    cells: list[dict[str, Any]] = []
    cell_runs: list[dict[str, Any]] = []
    max_workers = max(1, min(workers, len(grid) or 1))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_one_cell,
                cell,
                root,
                logs,
                len(tasks),
                task_family,
                n_instances,
                min_depth,
                max_depth,
                seed,
                max_nodes,
                per_cell_timeout,
                device,
                torch_threads,
            ): cell
            for cell in grid
        }
        for future in concurrent.futures.as_completed(futures):
            rows, run = future.result()
            cells.extend(rows)
            cell_runs.append(run)
    cells.sort(key=lambda row: int(row.get("cell_index", -1)))
    cell_runs.sort(key=lambda row: int(row.get("cell_index", -1)))
    result = {
        "module": "stage_a_symbolic_budgeted_grid",
        "status": "TRACK_A_SYMBOLIC_BUDGETED_GRID_COMPLETE",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "track": TRACK,
        "operator": OPERATOR,
        "source": SOURCE,
        "oracle_contract": {
            "stateless": True,
            "fresh_object_per_call": True,
            "allowed_input_keys": ["givens", "assignments"],
            "branch_policy": "MRV on current node only",
            "dead_end_source": "symbolic oracle CONTRADICTION on current node only",
            "reconstruct_after_revert": "arm trail pop -> remaining decisions/snapshot -> re-render -> fresh oracle call",
            "ci_status": stateless["status"],
            "ci_artifact": str(root / "oracle_statelessness_ci.json"),
        },
        "task_family": task_family,
        "n_tasks": len(tasks),
        "task_depth_histogram": {str(depth): sum(1 for task in tasks if task.dpll_backtrack_depth == depth) for depth in sorted({task.dpll_backtrack_depth for task in tasks})},
        "n_cells": len(cells),
        "requested_cells": len(grid),
        "per_cell_timeout": per_cell_timeout,
        "workers": max_workers,
        "torch_threads": torch_threads,
        "device": device,
        "cells": cells,
        "cell_runs": cell_runs,
        "grid": [asdict(cell) | {"name": cell.name} for cell in grid],
        "honesty": {
            "does_not_establish": "Subprocess timeouts are fail-closed evidence rows, not solves. Timed-out rot cells require narrower shards or optimized register decode before they can support L4 claims.",
        },
    }
    (root / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = write_report(output_dir, result)
    result["report"] = report
    (root / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _parse_indices(values: list[int] | None) -> set[int] | None:
    if not values:
        return None
    return set(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Track A symbolic cells with subprocess-level timeouts.")
    parser.add_argument("--output-dir", default="results/stage_a_symbolic_budgeted")
    parser.add_argument("--task-family", choices=["sudoku6", "sudoku9"], default="sudoku6")
    parser.add_argument("--n-instances", type=int, default=8)
    parser.add_argument("--min-depth", type=int, default=1)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--max-nodes", type=int, default=64)
    parser.add_argument("--per-cell-timeout", type=float, default=12.0)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--torch-threads", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--cell-index", type=int, action="append", default=[])
    args = parser.parse_args()
    payload = run_budgeted_grid(
        output_dir=args.output_dir,
        task_family=args.task_family,
        n_instances=args.n_instances,
        min_depth=args.min_depth,
        max_depth=args.max_depth,
        seed=args.seed,
        max_nodes=args.max_nodes,
        per_cell_timeout=args.per_cell_timeout,
        device=args.device,
        torch_threads=args.torch_threads,
        workers=args.workers,
        cell_indices=_parse_indices(args.cell_index),
    )
    print(json.dumps({"status": payload["status"], "n_cells": payload["n_cells"], "timeouts": sum(cell.get("timeout_count", 0) for cell in payload["cells"])}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
