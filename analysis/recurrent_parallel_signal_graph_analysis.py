"""Frozen analysis for independent recurrent graph signal-noise confirmation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from analysis.recurrent_parallel_signal_graph_run import verify_lock
from analysis.recurrent_parallel_signal_noise import _favored, _lookup, _summary
from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.recurrent_parallel_core import run_noisy_recurrent_correction


FAILURE_PENALTY = 5000


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render(payload: dict[str, Any]) -> str:
    lines = [
        "# Recurrent Parallel Signal-Noise Graph Confirmation",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Independent graph instances: 200 (50/diameter)",
        "- T=32; six eta values; three signal policies; 3,600 rows",
        "- GPU/LLM use: none",
        "- Cross-substrate claim: No",
        "",
        "## Frozen gates",
        "",
        "| Gate | Result |",
        "|---|---:|",
    ]
    for key, value in payload["gates"].items():
        lines.append(f"| `{key}` | **{'PASS' if value else 'FAIL'}** |")
    lines.extend([
        "",
        "## Confirmed boundary",
        "",
        "| Diameter | First crossing $\eta^*$ | Exact solve at eta=0.10 | Soft2 solve at eta=0.10 | Exact solve at eta=0.20 | Soft2 solve at eta=0.20 |",
        "|---:|---:|---:|---:|---:|---:|",
    ])
    for diameter in (2, 4, 8, 16):
        crossing = payload["eta_star"][str(diameter)]
        row10 = next(row for row in payload["phase_table"] if row["partition_diameter"] == diameter and row["eta_fp"] == 0.1)
        row20 = next(row for row in payload["phase_table"] if row["partition_diameter"] == diameter and row["eta_fp"] == 0.2)
        lines.append(f"| {diameter} | {crossing:.2f} | {row10['exact_solve']:.3f} | {row10['soft_solve']:.3f} | {row20['exact_solve']:.3f} | {row20['soft_solve']:.3f} |")
    lines.extend([
        "",
        "## Pooled hazard",
        "",
        "| Eta | Exact solve | Soft2 solve | Exact over-corrections | Soft2 over-corrections | Exact work | Soft2 work |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in payload["pooled_hazard"]:
        lines.append(f"| {row['eta_fp']:.2f} | {row['exact_solve']:.3f} | {row['soft_solve']:.3f} | {row['exact_over']:.2f} | {row['soft_over']:.2f} | {row['exact_work']:.1f} | {row['soft_work']:.1f} |")
    lines.extend([
        "",
        "## Integrity",
        "",
        f"- Lock checks: `{sum(payload['lock_checks'].values())}/{len(payload['lock_checks'])}`.",
        f"- Replay rows/mismatches: `{payload['integrity']['replay_rows']}/{payload['integrity']['replay_mismatches']}`.",
        f"- Eta=0 false positives/over-corrections: `{payload['integrity']['eta0_false_positives']}/{payload['integrity']['eta0_over_corrections']}`.",
        "",
        "## Claim boundary",
        "",
        "A pass independently confirms the diameter-sensitive recurrent signal hazard on the graph substrate. It does not establish SAT replication, a real-Qwen anchor, learned state, measured parallel speedup, or a broad paper claim.",
        "",
        "## Artifacts",
        "",
        "- [Raw results](raw_results.json)",
        "- [Analysis JSON](analysis.json)",
        "- [Frozen manifest](../recurrent_parallel_signal_graph_manifest/GENERATION.md)",
        "- [Confirmation contract](../../specs/recurrent_parallel_signal_graph_confirmation_v1.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze independent recurrent graph signal confirmation.")
    parser.add_argument("--raw", type=Path, default=Path("results/recurrent_parallel_signal_graph_confirmation/raw_results.json"))
    parser.add_argument("--execution-lock", type=Path, default=Path("specs/recurrent_parallel_signal_graph_execution_lock_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_signal_graph_confirmation"))
    args = parser.parse_args()
    raw_path = _resolve(args.raw)
    lock_path = _resolve(args.execution_lock)
    lock, lock_checks = verify_lock(lock_path)
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if raw.get("input_hashes") != {key: item["sha256"] for key, item in lock["files"].items()}:
        raise ValueError("raw hashes differ from graph signal lock")
    rows = list(raw.get("rows", []))
    summary = _summary(rows, FAILURE_PENALTY)
    manifest = list(json.loads(_resolve(lock["files"]["confirmatory_manifest"]["path"]).read_text(encoding="utf-8"))["rows"])
    instance_index = {str(row["instance_id"]): row for row in manifest}
    replay_targets = [row for row in rows if row["system"] == "R_exact" and row["eta_fp"] == 0.1][:8]
    replay_mismatches = 0
    for expected in replay_targets:
        replay = run_noisy_recurrent_correction(instance_index[expected["instance_id"]], system="R_exact", eta_fp=0.1, round_cap=32, noise_seed=20260712)
        replay_mismatches += int(replay != expected)
    eta0_exact = [row for row in rows if row["system"] == "R_exact" and row["eta_fp"] == 0.0]
    integrity = {
        "replay_rows": len(replay_targets),
        "replay_mismatches": replay_mismatches,
        "eta0_false_positives": sum(int(row["false_positives"]) for row in eta0_exact),
        "eta0_over_corrections": sum(int(row["over_corrections"]) for row in eta0_exact),
    }
    c0 = raw.get("status") == "RPD_SIGNAL_GRAPH_RAW_COMPLETE" and all(raw["cardinality"].values()) and all(raw["semantics"].values()) and all(lock_checks.values()) and integrity["replay_rows"] >= 8 and all(value == 0 for key, value in integrity.items() if key != "replay_rows")

    etas = [0.0, 0.01, 0.02, 0.05, 0.1, 0.2]
    eta_star = {}
    phase_table = []
    for diameter in (2, 4, 8, 16):
        crossing = None
        for eta in etas[1:]:
            exact = _lookup(summary, diameter, 32, eta, "R_exact")
            soft = _lookup(summary, diameter, 32, eta, "R_soft2")
            if _favored(soft, exact):
                crossing = eta
                break
        eta_star[str(diameter)] = crossing
        for eta in etas:
            exact = _lookup(summary, diameter, 32, eta, "R_exact")
            soft = _lookup(summary, diameter, 32, eta, "R_soft2")
            commit = _lookup(summary, diameter, 32, eta, "R_commit")
            phase_table.append({"partition_diameter": diameter, "eta_fp": eta, "exact_solve": exact["solve_rate"], "soft_solve": soft["solve_rate"], "commit_solve": commit["solve_rate"], "exact_work": exact["mean_penalized_work"], "soft_work": soft["mean_penalized_work"], "exact_over": exact["mean_over_corrections"], "soft_over": soft["mean_over_corrections"]})

    c1 = all(_lookup(summary, diameter, 32, 0.0, "R_exact")["solve_rate"] >= 0.95 and _lookup(summary, diameter, 32, 0.0, "R_soft2")["solve_rate"] >= 0.95 and _lookup(summary, diameter, 32, 0.0, "R_exact")["solve_rate"] - _lookup(summary, diameter, 32, 0.0, "R_commit")["solve_rate"] >= 0.80 for diameter in (2, 4, 8, 16))
    c2 = eta_star["16"] is not None and eta_star["8"] is not None and eta_star["2"] is not None and eta_star["16"] <= 0.05 and eta_star["2"] >= 0.05 and eta_star["16"] <= eta_star["8"] <= eta_star["2"] and _lookup(summary, 2, 32, 0.1, "R_exact")["solve_rate"] - _lookup(summary, 16, 32, 0.1, "R_exact")["solve_rate"] >= 0.20
    c3 = all(_lookup(summary, diameter, 32, eta, "R_soft2")["solve_rate"] >= 0.90 for diameter in (2, 4, 8, 16) for eta in etas)

    pooled_hazard = []
    exact_over = []
    for eta in etas:
        exact_rows = [row for row in rows if row["system"] == "R_exact" and row["eta_fp"] == eta]
        soft_rows = [row for row in rows if row["system"] == "R_soft2" and row["eta_fp"] == eta]
        def penalized(items: list[dict[str, Any]]) -> float:
            return mean(float(row["aggregate_work"] if row["solved"] else max(int(row["aggregate_work"]), FAILURE_PENALTY)) for row in items)
        item = {"eta_fp": eta, "exact_solve": mean(float(row["solved"]) for row in exact_rows), "soft_solve": mean(float(row["solved"]) for row in soft_rows), "exact_over": mean(float(row["over_corrections"]) for row in exact_rows), "soft_over": mean(float(row["over_corrections"]) for row in soft_rows), "exact_work": penalized(exact_rows), "soft_work": penalized(soft_rows)}
        pooled_hazard.append(item)
        exact_over.append(item["exact_over"])
    high = [row for row in pooled_hazard if row["eta_fp"] >= 0.05]
    c3 = c3 and mean(row["soft_solve"] for row in high) >= mean(row["exact_solve"] for row in high) and mean(row["soft_over"] for row in high) < mean(row["exact_over"] for row in high)
    c4 = all(left <= right + 1e-12 for left, right in zip(exact_over, exact_over[1:])) and pooled_hazard[-1]["exact_solve"] < pooled_hazard[0]["exact_solve"]
    c5 = pooled_hazard[0]["exact_work"] < pooled_hazard[0]["soft_work"] and all(next(row for row in pooled_hazard if row["eta_fp"] == eta)["soft_work"] < next(row for row in pooled_hazard if row["eta_fp"] == eta)["exact_work"] for eta in (0.1, 0.2)) and all(_lookup(summary, diameter, 32, 0.1, "R_soft2")["mean_penalized_work"] < _lookup(summary, diameter, 32, 0.1, "R_exact")["mean_penalized_work"] for diameter in (8, 16))
    gates = {"C0_integrity": c0, "C1_perfect_signal": c1, "C2_diameter_boundary": c2, "C3_two_hit_robustness": c3, "C4_hazard_monotonicity": c4, "C5_expected_work_crossing": c5}
    if not c0:
        status = "RPD_SIGNAL_GRAPH_PROTOCOL_FAIL"
    elif all(gates.values()):
        status = "RPD_SIGNAL_GRAPH_CONFIRMATION_PASS"
    elif c0 and c1 and c3 and c4 and c5:
        status = "RPD_SIGNAL_GRAPH_NO_DIAMETER_CONFIRMATION"
    else:
        status = "RPD_SIGNAL_GRAPH_CONFIRMATION_FAIL"

    payload = {"schema": "recurrent_parallel_signal_graph_analysis_v1", "status": status, "headline_eligible": False, "qwen_authorized": False, "cross_substrate_claim": False, "raw_results_sha256": _sha256(raw_path), "execution_lock_sha256": _sha256(lock_path), "lock_checks": lock_checks, "integrity": integrity, "gates": gates, "eta_star": eta_star, "phase_table": phase_table, "pooled_hazard": pooled_hazard, "summary": summary, "honesty": {"independent_graph_pool": True, "sat_replication_missing": True, "real_anchor_missing": True, "no_gpu_or_llm": True}}
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "analysis.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "RESULTS.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({"status": status, "report": str((output_dir / "RESULTS.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()
