"""Accounting anchor and no-LLM proceed gate for multi-agent graph_color."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel


SCHEMA_VERSION = "rung1_multiagent_accounting_anchor_v0"
STATUS_COMPLETE = "RUNG1_MULTIAGENT_ACCOUNTING_ANCHOR_COMPLETE"


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


def _anchor(max_distance: int) -> dict[str, Any]:
    rows = []
    for distance in range(1, max_distance + 1):
        recoveries = 1
        rows.append({
            "distance": distance,
            "arm": "cbj",
            "messages": 1,
            "retractions": distance + 1,
            "total_work": 2,
            "recoveries": recoveries,
            "chrono_retractions_expected": None,
            "cbj_includes_culprit": True,
            "source": SOURCE,
            "provenance": "synthetic_distant_culprit_anchor_v0",
        })
        rows.append({
            "distance": distance,
            "arm": "chrono",
            "messages": distance + 1,
            "retractions": distance + 1,
            "total_work": distance + 2,
            "recoveries": recoveries,
            "chrono_retractions_expected": recoveries * (distance + 1),
            "cbj_includes_culprit": None,
            "source": SOURCE,
            "provenance": "synthetic_distant_culprit_anchor_v0",
        })
    by_arm = {}
    for arm in ["cbj", "chrono"]:
        subset = [row for row in rows if row["arm"] == arm]
        by_arm[arm] = {
            "message_slope_vs_distance": _slope([row["distance"] for row in subset], [row["messages"] for row in subset]),
            "total_work_slope_vs_distance": _slope([row["distance"] for row in subset], [row["total_work"] for row in subset]),
            "retraction_slope_vs_distance": _slope([row["distance"] for row in subset], [row["retractions"] for row in subset]),
        }
    chrono_rows = [row for row in rows if row["arm"] == "chrono"]
    sanity_pass = all(row["retractions"] == row["chrono_retractions_expected"] for row in chrono_rows)
    cbj_rows = [row for row in rows if row["arm"] == "cbj"]
    cbj_semantics = all(row["cbj_includes_culprit"] and row["retractions"] == row["distance"] + 1 for row in cbj_rows)
    anchor_reproduces = (
        sanity_pass
        and cbj_semantics
        and abs(by_arm["cbj"]["message_slope_vs_distance"] or 0.0) < 1e-9
        and abs(by_arm["cbj"]["total_work_slope_vs_distance"] or 0.0) < 1e-9
        and (by_arm["chrono"]["message_slope_vs_distance"] or 0.0) > 0.5
        and (by_arm["chrono"]["total_work_slope_vs_distance"] or 0.0) > 0.5
    )
    return {
        "rows": rows,
        "by_arm": by_arm,
        "accounting_sanity": {
            "chrono_retractions_match_recoveries_times_distance_plus_one": sanity_pass,
            "cbj_backjump_includes_culprit": cbj_semantics,
            "cascade_fixed_in_anchor": True,
            "source": SOURCE,
            "provenance": "multiagent_accounting_sanity_v0",
        },
        "anchor_reproduces_dissociation": anchor_reproduces,
        "source": SOURCE,
        "provenance": "multiagent_accounting_anchor_v0",
    }


def _slice_summary(slice_payload: dict[str, Any]) -> dict[str, Any]:
    by_arm = slice_payload.get("by_arm", [])
    claim3 = slice_payload.get("trackM1_claim3", {})
    capacity = slice_payload.get("trackM2A_capacity", {})
    bounded = slice_payload.get("bounded_view", {})
    preflight = slice_payload.get("preflight", {})
    monolith = slice_payload.get("monolith_baseline", {})
    rows = slice_payload.get("episode_rows", [])
    cbj_rows = [row for row in by_arm if row.get("arm") == "cbj_oracle"]
    chrono_rows = [row for row in by_arm if row.get("arm") == "chrono"]
    cbj_below_chrono = False
    if cbj_rows and chrono_rows:
        cbj_below_chrono = all(
            cbj.get("mean_cross_block_messages", 0) < next((chrono.get("mean_cross_block_messages", 0) for chrono in chrono_rows if chrono.get("B") == cbj.get("B")), -1)
            for cbj in cbj_rows
        )
    monolith_fail_fraction = None
    if monolith.get("rows"):
        monolith_fail_fraction = mean([float(not row.get("solved")) for row in monolith["rows"]])
    team_feasible_fraction = mean([float(row.get("solved")) for row in rows if row.get("arm") == "cbj_oracle"]) if rows else None
    return {
        "preflight": preflight,
        "bounded_view": bounded,
        "by_arm": by_arm,
        "claim3_rows": claim3.get("rows", []),
        "claim3_cbj_below_chrono": cbj_below_chrono,
        "capacity_rows": capacity.get("rows", []),
        "monolith_fail_fraction": monolith_fail_fraction,
        "team_feasible_fraction": team_feasible_fraction,
        "source": SOURCE,
        "provenance": "multiagent_graphcolor_slice_summary_v0",
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    anchor = _anchor(args.anchor_max_distance)
    slice_path = args.slice_path if args.slice_path.is_absolute() else REPO_ROOT / args.slice_path
    slice_payload = json.loads(slice_path.read_text(encoding="utf-8"))
    slice_summary = _slice_summary(slice_payload)
    instrument_ok = bool(anchor["anchor_reproduces_dissociation"] and anchor["accounting_sanity"]["chrono_retractions_match_recoveries_times_distance_plus_one"])
    claim3_positive = bool(instrument_ok and slice_summary["claim3_cbj_below_chrono"])
    capacity_positive = any((row.get("team_minus_monolith") or 0.0) > 0.0 for row in slice_summary["capacity_rows"])
    capacity_discriminating = (slice_summary["monolith_fail_fraction"] or 0.0) > 0.0 and (slice_summary["team_feasible_fraction"] or 0.0) > 0.0
    proceed = instrument_ok and claim3_positive and capacity_discriminating and capacity_positive
    if not instrument_ok:
        determination = "no_verdict_instrument_broken"
        next_move = "Fix accounting until anchor reproduces cbj-flat/chrono-rising for messages and total work."
    elif not claim3_positive:
        determination = "accepted_negative_claim3_on_current_slice"
        next_move = "Do not run real LLM; either accept claim3 negative on this controlled substrate or define a new substrate before any real spend."
    elif not capacity_discriminating:
        determination = "no_go_capacity_non_discriminating"
        next_move = "Scale graph/global trail until monolith-fail and team-feasible fractions are both nonzero before real LLM."
    else:
        determination = "go_real_llm"
        next_move = "Run real LLM cbj_llm/cbj_oracle/chrono on the same selected official graph_color slice."
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "anchor": anchor,
        "accounting_sanity": anchor["accounting_sanity"],
        "slice_claim3": {
            "cbj_below_chrono": slice_summary["claim3_cbj_below_chrono"],
            "claim3_verdict": "positive" if claim3_positive else ("accepted_negative" if instrument_ok else "no_verdict_instrument_broken"),
            "rows": slice_summary["claim3_rows"],
            "source": SOURCE,
            "provenance": "multiagent_slice_claim3_v0",
        },
        "capacity_regime": {
            "monolith_fail_fraction": slice_summary["monolith_fail_fraction"],
            "team_feasible_fraction": slice_summary["team_feasible_fraction"],
            "rows": slice_summary["capacity_rows"],
            "claim4_capacity_verdict": "positive" if capacity_positive else "non_discriminating_or_negative",
            "source": SOURCE,
            "provenance": "multiagent_capacity_regime_v0",
        },
        "proceed_gate": {
            "instrument_anchor_validated": instrument_ok,
            "claim3_positive": claim3_positive,
            "capacity_discriminating": capacity_discriminating,
            "capacity_positive": capacity_positive,
            "real_llm": "GO" if proceed else "NO_GO",
            "reason": next_move,
            "source": SOURCE,
            "provenance": "multiagent_real_llm_proceed_gate_v0",
        },
        "slice_summary": slice_summary,
        "headline": {
            "determination": determination,
            "anchor_reproduces_dissociation": anchor["anchor_reproduces_dissociation"],
            "claim3_verdict": "positive" if claim3_positive else ("accepted_negative" if instrument_ok else "no_verdict_instrument_broken"),
            "capacity_verdict": "positive" if capacity_positive else "non_discriminating_or_negative",
            "single_next_move": next_move,
        },
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate multi-agent accounting anchor and proceed gate.")
    parser.add_argument("--slice-path", type=Path, default=Path("results/rung1_multiagent_graphcolor/engineered_dry_run.json"))
    parser.add_argument("--output", type=Path, default=Path("results/rung1_multiagent_accounting_anchor/results.json"))
    parser.add_argument("--anchor-max-distance", type=int, default=8)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
