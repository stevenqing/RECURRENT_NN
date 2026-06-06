"""Merge Stage A latent backtracking shard outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _summarize_cells(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not cells:
        return []
    groups = sorted({(cell.get("stack"), cell.get("D"), cell.get("grid")) for cell in cells})
    summary = []
    for stack, D, grid in groups:
        subset = [cell for cell in cells if (cell.get("stack"), cell.get("D"), cell.get("grid")) == (stack, D, grid)]
        depths = [cell.get("max_solve_depth") for cell in subset if isinstance(cell.get("max_solve_depth"), (int, float))]
        summary.append({
            "grid": grid,
            "stack": stack,
            "D": D,
            "n": len(subset),
            "gate_pass_rate": mean([1.0 if cell.get("gate_pass") else 0.0 for cell in subset]) if subset else None,
            "mean_max_solve_depth": mean(depths) if depths else None,
            "std_max_solve_depth": pstdev(depths) if len(depths) > 1 else 0.0 if depths else None,
        })
    return summary


def merge(input_dir: str = "results/stage_a_backtrack") -> dict[str, Any]:
    root = Path(input_dir)
    shard_paths = sorted(root.glob("shard_*/results.json"))
    shards = [_load_json(path) | {"path": str(path)} for path in shard_paths]
    cell_paths = sorted(root.glob("shard_*/cell_*/results.json"))
    cells = [_load_json(path) | {"path": str(path)} for path in cell_paths]
    statuses = sorted({shard.get("status", "UNKNOWN") for shard in shards})
    preflight_failures = [shard for shard in shards if shard.get("status") == "PRECHECK_FAILED"]
    payload = {
        "module": "stage_a_backtrack_merge",
        "input_dir": input_dir,
        "n_shards": len(shards),
        "n_cells": len(cells),
        "statuses": statuses,
        "preflight_failed": bool(preflight_failures),
        "shards": shards,
        "summary": _summarize_cells(cells),
    }
    (root / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "curves.json").write_text(json.dumps({"cells": cells, "summary": payload["summary"]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"results": str(root / "results.json"), "curves": str(root / "curves.json"), "n_shards": len(shards), "n_cells": len(cells), "statuses": statuses}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge Stage A latent backtracking results.")
    parser.add_argument("--input-dir", default="results/stage_a_backtrack")
    args = parser.parse_args()
    print(json.dumps(merge(args.input_dir), indent=2, sort_keys=True))