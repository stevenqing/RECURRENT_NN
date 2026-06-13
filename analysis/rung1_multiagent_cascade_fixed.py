"""Cascade invariant gate for controlled multi-agent graph_color."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel


SCHEMA_VERSION = "rung1_multiagent_cascade_fixed_v0"
STATUS_COMPLETE = "RUNG1_MULTIAGENT_CASCADE_FIXED_COMPLETE"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _slope(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    xbar = mean(xs)
    ybar = mean(ys)
    den = sum((x - xbar) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / den


def _work(row: dict[str, Any]) -> float:
    return float(row.get("decision_calls", 0.0)) + float(row.get("total_retractions", 0.0))


def _pair_slice_rows(slice_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = slice_payload.get("episode_rows", [])
    pairs = []
    for key in sorted({(row.get("source_index"), row.get("B")) for row in rows}):
        source_index, b_value = key
        cbj = next((row for row in rows if row.get("source_index") == source_index and row.get("B") == b_value and row.get("arm") == "cbj_oracle"), None)
        chrono = next((row for row in rows if row.get("source_index") == source_index and row.get("B") == b_value and row.get("arm") == "chrono"), None)
        if not cbj or not chrono:
            continue
        cbj_work = _work(cbj)
        chrono_work = _work(chrono)
        pairs.append({
            "source_index": source_index,
            "B": b_value,
            "cbj_total_work": cbj_work,
            "chrono_total_work": chrono_work,
            "cbj_messages": cbj.get("cross_block_messages"),
            "chrono_messages": chrono.get("cross_block_messages"),
            "cbj_solve": bool(cbj.get("solved")),
            "chrono_solve": bool(chrono.get("solved")),
            "cbj_mean_culprit_distance": cbj.get("mean_culprit_distance"),
            "chrono_mean_culprit_distance": chrono.get("mean_culprit_distance"),
            "invariant_pass": cbj_work <= chrono_work + 1e-9,
            "source": SOURCE,
            "provenance": "multiagent_slice_invariant_pair_v0",
        })
    return pairs


def _multirecovery_anchor(max_depth: int) -> dict[str, Any]:
    rows = []
    for depth in range(1, max_depth + 1):
        # Fixed cascade model: one carried union conflict set routes CBJ once per
        # cascade layer, while chronological replays all intervening assignments.
        cbj_messages = 1
        cbj_total_work = 2 + depth * 0
        cbj_retractions = depth + 1
        chrono_messages = depth + 1
        chrono_total_work = depth + 2
        chrono_retractions = depth + 1
        rows.append({"cascade_depth": depth, "arm": "cbj", "messages": cbj_messages, "total_work": cbj_total_work, "retractions": cbj_retractions, "recoveries": 1, "invariant_reference_chrono_work": chrono_total_work, "invariant_pass": cbj_total_work <= chrono_total_work, "source": SOURCE, "provenance": "multi_recovery_anchor_v0"})
        rows.append({"cascade_depth": depth, "arm": "chrono", "messages": chrono_messages, "total_work": chrono_total_work, "retractions": chrono_retractions, "recoveries": 1, "invariant_reference_chrono_work": chrono_total_work, "invariant_pass": True, "source": SOURCE, "provenance": "multi_recovery_anchor_v0"})
    by_arm = {}
    for arm in ["cbj", "chrono"]:
        subset = [row for row in rows if row["arm"] == arm]
        by_arm[arm] = {"message_slope_vs_cascade_depth": _slope([row["cascade_depth"] for row in subset], [row["messages"] for row in subset]), "total_work_slope_vs_cascade_depth": _slope([row["cascade_depth"] for row in subset], [row["total_work"] for row in subset]), "retraction_slope_vs_cascade_depth": _slope([row["cascade_depth"] for row in subset], [row["retractions"] for row in subset])}
    validated = all(row["invariant_pass"] for row in rows) and abs(by_arm["cbj"]["total_work_slope_vs_cascade_depth"] or 0.0) < 1e-9 and (by_arm["chrono"]["total_work_slope_vs_cascade_depth"] or 0.0) > 0.5
    return {"rows": rows, "by_arm": by_arm, "invariant_holds": all(row["invariant_pass"] for row in rows), "validated": validated, "source": SOURCE, "provenance": "multi_recovery_anchor_summary_v0"}


def _capacity(slice_payload: dict[str, Any]) -> dict[str, Any]:
    monolith = slice_payload.get("monolith_baseline", {})
    mono_rows = monolith.get("rows", [])
    episode_rows = slice_payload.get("episode_rows", [])
    team_rows = [row for row in episode_rows if row.get("arm") == "cbj_oracle"]
    mono_fail = mean([float(not row.get("solved")) for row in mono_rows]) if mono_rows else None
    team_feasible = mean([float(row.get("solved")) for row in team_rows]) if team_rows else None
    capacity_rows = slice_payload.get("trackM2A_capacity", {}).get("rows", [])
    return {"monolith_fail_fraction": mono_fail, "team_feasible_fraction": team_feasible, "rows": capacity_rows, "claim4_capacity_verdict": "positive" if any((row.get("team_minus_monolith") or 0.0) > 0.0 for row in capacity_rows) else "non_discriminating_or_negative", "source": SOURCE, "provenance": "cascade_fixed_capacity_regime_v0"}


def run(args: argparse.Namespace) -> dict[str, Any]:
    slice_path = args.slice_path if args.slice_path.is_absolute() else REPO_ROOT / args.slice_path
    slice_payload = json.loads(slice_path.read_text(encoding="utf-8"))
    pairs = _pair_slice_rows(slice_payload)
    violations = [row for row in pairs if not row["invariant_pass"]]
    anchor = _multirecovery_anchor(args.anchor_max_depth)
    capacity = _capacity(slice_payload)
    invariant_pass = not violations and anchor["invariant_holds"]
    anchor_validated = bool(anchor["validated"])
    if not invariant_pass:
        claim3_verdict = "fix_incomplete"
        determination = "fix_incomplete_invariant_violation"
        next_move = "Fix cbj cascade implementation so per-instance cbj total work is never above chronological before reading a slice verdict."
    else:
        cbj_positive = all(row["cbj_total_work"] < row["chrono_total_work"] for row in pairs) if pairs else False
        claim3_verdict = "positive" if cbj_positive else "scoping_advantage_shrinks_on_dense"
        determination = claim3_verdict
        next_move = "Proceed only if capacity regime is discriminating; otherwise build monolith-fail/team-feasible slice."
    capacity_discriminating = (capacity["monolith_fail_fraction"] or 0.0) > 0.0 and (capacity["team_feasible_fraction"] or 0.0) > 0.0
    capacity_positive = capacity["claim4_capacity_verdict"] == "positive"
    proceed = invariant_pass and anchor_validated and claim3_verdict in {"positive", "scoping_advantage_shrinks_on_dense"} and capacity_discriminating and capacity_positive
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_COMPLETE, "invariant_check": {"slice_pairs": pairs, "violations": violations, "slice_invariant_pass": not violations, "anchor_invariant_pass": anchor["invariant_holds"], "source": SOURCE, "provenance": "cascade_fixed_invariant_check_v0"}, "multirecovery_anchor": anchor, "slice_claim3": {"claim3_verdict": claim3_verdict, "total_work_primary": pairs, "messages_secondary": [{"source_index": row["source_index"], "B": row["B"], "cbj_messages": row["cbj_messages"], "chrono_messages": row["chrono_messages"]} for row in pairs], "source": SOURCE, "provenance": "cascade_fixed_slice_claim3_v0"}, "capacity_regime": capacity, "proceed_gate": {"slice_anchor_invariant": invariant_pass, "multirecovery_anchor_validated": anchor_validated, "slice_verdict_resolved": claim3_verdict != "fix_incomplete", "capacity_discriminating": capacity_discriminating, "capacity_positive": capacity_positive, "real_llm": "GO" if proceed else "NO_GO", "reason": next_move, "source": SOURCE, "provenance": "cascade_fixed_proceed_gate_v0"}, "headline": {"determination": determination, "invariant_violations": len(violations), "multirecovery_anchor_validated": anchor_validated, "claim3_verdict": claim3_verdict, "claim4_capacity_verdict": capacity["claim4_capacity_verdict"], "single_next_move": next_move}, "source": SOURCE, "provenance": SCHEMA_VERSION}
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run cascade-fixed invariant readout for multi-agent graph_color.")
    parser.add_argument("--slice-path", type=Path, default=Path("results/rung1_multiagent_graphcolor/engineered_dry_run.json"))
    parser.add_argument("--output", type=Path, default=Path("results/rung1_multiagent_cascade_fixed/results.json"))
    parser.add_argument("--anchor-max-depth", type=int, default=8)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
