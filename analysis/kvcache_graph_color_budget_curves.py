"""Build graph_color matched-budget curves from A/C graph_color search rows."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any

from analysis.kvcache_graph_color_search import _write_json
from experiments.rung1_distributed_graph_coloring import SOURCE


SCHEMA_VERSION = "kvcache_graph_color_budget_curves_v0"
STATUS_COMPLETE = "KVCACHE_GRAPH_COLOR_BUDGET_CURVES_COMPLETE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wilson(successes: int, n: int, z: float = 1.959963984540054) -> dict[str, float | None]:
    if n <= 0:
        return {"rate": None, "ci_low": None, "ci_high": None}
    phat = successes / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return {"rate": phat, "ci_low": max(0.0, center - half), "ci_high": min(1.0, center + half)}


def _budget_grid(anchor: int, scales: str) -> list[int]:
    return sorted({max(1, int(round(float(scale.strip()) * int(anchor)))) for scale in scales.split(",") if scale.strip()})


def _method(row: dict[str, Any]) -> str:
    base = str(row.get("base_arm") or "")
    if base == "A_cache":
        return "A_cache"
    if base == "C_incontext":
        return "C_incontext"
    arm = str(row.get("arm") or "")
    if arm.startswith("A_cache"):
        return "A_cache"
    if arm.startswith("C_incontext"):
        return "C_incontext"
    raise ValueError(f"unknown method for row arm={arm} base={base}")


def _select_bstar(rows: list[dict[str, Any]]) -> dict[str, Any]:
    c_rows = [row for row in rows if _method(row) == "C_incontext"]
    thresholds = sorted(int(row["total_tokens"]) for row in c_rows if row.get("solved"))
    n = len(c_rows)
    candidates = []
    for budget in thresholds:
        solve = sum(int(row.get("solved") and int(row["total_tokens"]) <= budget) for row in c_rows) / n if n else 0.0
        candidates.append({"budget_B": budget, "C_solve_rate": solve})
        if 0.4 <= solve <= 0.6:
            return {"budget_B": budget, "C_solve_rate": solve, "selection_rule_status": "MIDBAND_FOUND", "source": SOURCE, "provenance": "kvcache_graph_color_budget_bstar_v0"}
    selected = min(candidates, key=lambda row: abs(float(row["C_solve_rate"]) - 0.5)) if candidates else {"budget_B": 1, "C_solve_rate": 0.0}
    return selected | {"selection_rule_status": "MIDBAND_NOT_FOUND_NEAREST", "source": SOURCE, "provenance": "kvcache_graph_color_budget_bstar_v0"}


def _depth_at_budget(row: dict[str, Any], budget: int) -> tuple[int, int]:
    # context_rows are exact C per-step billings for C_incontext. For A_cache the
    # graph_color row stores exact total_tokens but not event-token prefix costs;
    # if A does not finish under budget, report the deepest context row whose
    # observed cache length is below budget as an auditable lower bound.
    method = _method(row)
    if int(row.get("total_tokens", 0)) <= int(budget):
        return int(row.get("trace_max_register_len", 0) or max((int(item.get("depth", 0)) for item in row.get("context_rows", [])), default=0)), len(row.get("context_rows", []))
    cumulative = 0
    depth = 0
    steps = 0
    for item in row.get("context_rows", []):
        cost = int(item.get("context_tokens", 0))
        if method == "C_incontext":
            cumulative += cost
        else:
            cumulative = max(cumulative, cost)
        if cumulative > int(budget):
            break
        depth = max(depth, int(item.get("depth", 0)))
        steps += 1
    return depth, steps


def build(args: argparse.Namespace) -> dict[str, Any]:
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rows = data.get("rows", [])
    if not rows:
        raise ValueError("input has no rows")
    bstar = _select_bstar(rows)
    grid = _budget_grid(int(bstar["budget_B"]), args.budget_scales)
    budget_rows = []
    for row in rows:
        method = _method(row)
        for budget in grid:
            solved = bool(row.get("solved") and int(row.get("total_tokens", 0)) <= int(budget))
            depth, steps = _depth_at_budget(row, int(budget))
            budget_rows.append({
                "task": "graph_color",
                "variant": args.variant,
                "policy": str(row.get("branch_policy") or "oracle_search"),
                "method": method,
                "source_index": int(row["source_index"]),
                "budget_B": int(budget),
                "solved": solved,
                "tokens_used": int(row.get("total_tokens", 0)) if solved else min(int(row.get("total_tokens", 0)), int(budget)),
                "full_trace_tokens": int(row.get("total_tokens", 0)),
                "depth_reached": depth,
                "steps_reached": steps,
                "status_at_budget": "SOLVED" if solved else "BUDGET_EXHAUSTED",
                "source": SOURCE,
                "provenance": "kvcache_graph_color_budget_row_v0",
            })
    curve = []
    for key in sorted({(row["method"], int(row["budget_B"])) for row in budget_rows}):
        method, budget = key
        subset = [row for row in budget_rows if row["method"] == method and int(row["budget_B"]) == budget]
        successes = sum(int(row["solved"]) for row in subset)
        ci = _wilson(successes, len(subset))
        curve.append({
            "task": "graph_color",
            "variant": args.variant,
            "policy": args.policy,
            "method": method,
            "budget_B": budget,
            "n": len(subset),
            "solve_count": successes,
            "solve_rate": ci["rate"],
            "solve_ci_low": ci["ci_low"],
            "solve_ci_high": ci["ci_high"],
            "mean_tokens_used": mean(float(row["tokens_used"]) for row in subset),
            "mean_depth_reached": mean(float(row["depth_reached"]) for row in subset),
            "mean_steps_reached": mean(float(row["steps_reached"]) for row in subset),
            "status_counts": dict(Counter(row["status_at_budget"] for row in subset)),
            "source": SOURCE,
            "provenance": "kvcache_graph_color_budget_curve_v0",
        })
    gaps = []
    for budget in grid:
        a = next(row for row in curve if row["method"] == "A_cache" and int(row["budget_B"]) == int(budget))
        c = next(row for row in curve if row["method"] == "C_incontext" and int(row["budget_B"]) == int(budget))
        gap = float(a["solve_rate"] or 0.0) - float(c["solve_rate"] or 0.0)
        gaps.append({
            "task": "graph_color",
            "variant": args.variant,
            "policy": args.policy,
            "budget_B": int(budget),
            "A_solve_rate": a["solve_rate"],
            "C_solve_rate": c["solve_rate"],
            "A_minus_C": gap,
            "gap_ci_low_conservative": float(a["solve_ci_low"] or 0.0) - float(c["solve_ci_high"] or 0.0),
            "gap_ci_high_conservative": float(a["solve_ci_high"] or 0.0) - float(c["solve_ci_low"] or 0.0),
            "promotion_midband_pass": bool(gap >= 0.10 and (float(a["solve_ci_low"] or 0.0) - float(c["solve_ci_high"] or 0.0)) > 0.0),
            "source": SOURCE,
            "provenance": "kvcache_graph_color_budget_gap_v0",
        })
    shape = {
        "task": "graph_color",
        "variant": args.variant,
        "policy": args.policy,
        "A_dominates_grid": all(float(row["A_minus_C"]) >= -1e-9 for row in gaps),
        "min_gap": min(float(row["A_minus_C"]) for row in gaps),
        "max_gap": max(float(row["A_minus_C"]) for row in gaps),
        "promotion_points": sum(int(row["promotion_midband_pass"]) for row in gaps),
        "source": SOURCE,
        "provenance": "kvcache_graph_color_budget_shape_v0",
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "input": str(args.input),
        "variant": args.variant,
        "policy": args.policy,
        "bstar": bstar,
        "budget_grid": grid,
        "curve_summary": curve,
        "gap_summary": gaps,
        "shape_summary": shape,
        "budget_rows": budget_rows,
        "source": SOURCE,
        "provenance": "kvcache_graph_color_budget_curves_v0",
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build graph_color budget curves from A/C rows.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", default="symbolic_cbj")
    parser.add_argument("--policy", default="oracle_search")
    parser.add_argument("--budget-scales", default="0.25,0.5,1,2,4")
    payload = build(parser.parse_args())
    print(json.dumps({"path": str(parser.parse_args().output), "status": payload["status"], "B_star": payload["bstar"]["budget_B"]}, sort_keys=True))


if __name__ == "__main__":
    main()
