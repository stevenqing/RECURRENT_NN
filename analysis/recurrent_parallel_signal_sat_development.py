"""Development gate for recurrent signal noise on long-diameter partitioned SAT."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.recurrent_parallel_sat_core import run_noisy_sat_recurrence
from experiments.signal.long_diameter_sat import clause_hash, generate_long_diameter_sat, initial_parent_child_mismatches, local_pair_extendability, public_instance, verify_sat


CONTRACT_SCHEMA = "recurrent_parallel_signal_sat_development_contract_v1"


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summaries(rows: list[dict[str, Any]], penalty: int) -> list[dict[str, Any]]:
    output = []
    for diameter, eta, system in sorted({(int(row["partition_diameter"]), float(row["eta_fp"]), str(row["system"])) for row in rows}):
        subset = [row for row in rows if int(row["partition_diameter"]) == diameter and row["eta_fp"] == eta and row["system"] == system]
        output.append({"partition_diameter": diameter, "eta_fp": eta, "system": system, "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "mean_penalized_work": mean(float(row["aggregate_work"] if row["solved"] else max(int(row["aggregate_work"]), int(penalty))) for row in subset), "mean_over_corrections": mean(float(row["over_corrections"]) for row in subset), "mean_queries": mean(float(row["detector_queries"]) for row in subset), "mean_rounds": mean(float(row["rounds_executed"]) for row in subset), "mean_final_violations": mean(float(row["final_cross_violations"]) for row in subset), "status_counts": dict(Counter(str(row["status"]) for row in subset))})
    return output


def _lookup(summary: list[dict[str, Any]], diameter: int, eta: float, system: str) -> dict[str, Any]:
    return next(row for row in summary if row["partition_diameter"] == int(diameter) and abs(row["eta_fp"] - float(eta)) < 1e-12 and row["system"] == system)


def _favored(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left["solve_rate"] > right["solve_rate"] or (left["solve_rate"] == right["solve_rate"] and left["mean_penalized_work"] < right["mean_penalized_work"])


def _render(payload: dict[str, Any]) -> str:
    lines = [
        "# Recurrent Parallel Signal-Noise SAT Development",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Instances: 32 (8/diameter)",
        "- Long-diameter partitioned 3-SAT, 264 clauses/instance",
        "- T=32; six eta values; three policies; 576 rows",
        "- GPU/LLM use: none",
        "- Headline eligible: No",
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
        "## Preliminary SAT boundary",
        "",
        "| Diameter | Eta* | Exact solve eta=.10 | Soft solve eta=.10 | Exact solve eta=.20 | Soft solve eta=.20 |",
        "|---:|---:|---:|---:|---:|---:|",
    ])
    for diameter in (2, 4, 8, 16):
        r10 = next(row for row in payload["phase_table"] if row["partition_diameter"] == diameter and row["eta_fp"] == 0.1)
        r20 = next(row for row in payload["phase_table"] if row["partition_diameter"] == diameter and row["eta_fp"] == 0.2)
        crossing = payload["eta_star"][str(diameter)]
        lines.append(f"| {diameter} | {'none' if crossing is None else f'{crossing:.2f}'} | {r10['exact_solve']:.3f} | {r10['soft_solve']:.3f} | {r20['exact_solve']:.3f} | {r20['soft_solve']:.3f} |")
    lines.extend([
        "",
        "## Environment audit",
        "",
        f"- Fixed clauses local/cross/total: `{payload['environment']['local_clauses']}/{payload['environment']['cross_clauses']}/{payload['environment']['total_clauses']}`.",
        f"- Initial parent-child mismatch range: `{payload['environment']['mismatch_range']}`.",
        f"- Local pair extendability failures: `{payload['environment']['extendability_failures']}`.",
        "",
        "## Honesty boundary",
        "",
        "This is a small exposed development substrate whose cross-partition clauses are equality gadgets. It tests semantic replication of recurrent signal hazard in SAT form, not a broad natural-SAT claim. Independent zero-overlap confirmation remains required.",
        "",
        "## Artifacts",
        "",
        "- [Results JSON](results.json)",
        "- [Development manifest](instance_manifest.json)",
        "- [Frozen SAT development contract](../../specs/recurrent_parallel_signal_sat_development_v1.md)",
        "- [Graph confirmation](../recurrent_parallel_signal_graph_confirmation/CLOSEOUT.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run long-diameter SAT recurrent signal development.")
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_signal_sat_development_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_signal_sat_development"))
    args = parser.parse_args()
    contract_path = _resolve(args.contract)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("status") != "FROZEN_BEFORE_SAT_OUTCOMES":
        raise ValueError("SAT signal development contract is not frozen")
    graph_gate = json.loads(_resolve(contract["graph_prerequisite"]).read_text(encoding="utf-8"))
    if graph_gate.get("status") != "RPD_SIGNAL_GRAPH_CONFIRMATION_PASS":
        raise ValueError("SAT development blocked by graph confirmation")
    substrate = contract["substrate"]
    execution = contract["execution"]

    full_instances = []
    rows_public = []
    environment_rows = []
    for diameter in map(int, substrate["diameters"]):
        for candidate_index in range(int(substrate["instances_per_diameter"])):
            full = generate_long_diameter_sat(base_seed=int(substrate["base_seed"]), candidate_index=candidate_index, diameter=diameter, local_clauses_per_partition=int(substrate["local_clauses_per_partition"]), split="development")
            planted = {int(key): int(value) for key, value in full["planted_assignment"].items()}
            public = public_instance(full)
            public["clause_sha256"] = clause_hash(public)
            extendability = local_pair_extendability(public)
            mismatch = initial_parent_child_mismatches(public)
            full_instances.append(full)
            rows_public.append(public)
            environment_rows.append({"instance_id": public["instance_id"], "partition_diameter": diameter, "planted_valid": verify_sat(full, planted), "extendable": all(extendability.values()), "initial_mismatches": mismatch})

    environment = {
        "instances": len(rows_public),
        "diameter_counts": dict(Counter(int(row["partition_diameter"]) for row in rows_public)),
        "total_clauses": int(rows_public[0]["n_clauses"]),
        "local_clauses": int(rows_public[0]["n_local_clauses"]),
        "cross_clauses": int(rows_public[0]["n_cross_clauses"]),
        "mismatch_range": [min(row["initial_mismatches"] for row in environment_rows), max(row["initial_mismatches"] for row in environment_rows)],
        "extendability_failures": sum(int(not row["extendable"]) for row in environment_rows),
        "checks": {
            "complete_32": len(rows_public) == 32,
            "unique_ids": len({row["instance_id"] for row in rows_public}) == 32,
            "unique_hashes": len({row["clause_sha256"] for row in rows_public}) == 32,
            "fixed_clause_counts": len({(row["n_clauses"], row["n_local_clauses"], row["n_cross_clauses"]) for row in rows_public}) == 1,
            "planted_valid": all(row["planted_valid"] for row in environment_rows),
            "planted_removed": all("planted_assignment" not in row for row in rows_public),
            "extendable": all(row["extendable"] for row in environment_rows),
            "engaged": all(row["initial_mismatches"] >= 8 for row in environment_rows),
        },
    }

    rows = []
    for index, instance in enumerate(rows_public):
        for eta in map(float, execution["eta_fp"]):
            for system in map(str, execution["systems"]):
                rows.append(run_noisy_sat_recurrence(instance, system=system, eta_fp=eta, eta_fn=float(execution["eta_fn"]), round_cap=int(execution["round_cap"]), noise_seed=int(execution["noise_seed"])))
        if (index + 1) % 4 == 0:
            print(json.dumps({"event": "sat_signal_dev_progress", "instances_completed": index + 1}), flush=True)

    replay_targets = [row for row in rows if row["system"] == "R_exact" and row["eta_fp"] == 0.1][:8]
    index = {row["instance_id"]: row for row in rows_public}
    replay_mismatches = sum(int(run_noisy_sat_recurrence(index[row["instance_id"]], system="R_exact", eta_fp=0.1, round_cap=32, noise_seed=int(execution["noise_seed"])) != row) for row in replay_targets)
    semantics = {
        "replay_rows": len(replay_targets),
        "replay_mismatches": replay_mismatches,
        "same_round_reads": sum(int(row["same_round_cross_agent_reads"]) for row in rows),
        "invalid_message_age_rows": sum(int(row["messages_delivered"] > 0 and row["maximum_message_age"] != 1) for row in rows),
        "invalid_local_candidates": sum(int(not row["local_candidates_valid"]) for row in rows),
        "official_score_failures": sum(int(row["solved"] and not row["official_verification"]) for row in rows),
        "planted_usage_rows": sum(int(row["planted_assignment_used"]) for row in rows),
    }
    summary = _summaries(rows, int(execution["failure_penalty"]))
    etas = list(map(float, execution["eta_fp"]))
    eta_star = {}
    crossing_count = 0
    phase_table = []
    for diameter in map(int, substrate["diameters"]):
        crossing = None
        for eta in etas[1:]:
            if _favored(_lookup(summary, diameter, eta, "R_soft2"), _lookup(summary, diameter, eta, "R_exact")):
                crossing = eta
                break
        eta_star[str(diameter)] = crossing
        crossing_count += int(crossing is not None)
        for eta in etas:
            exact = _lookup(summary, diameter, eta, "R_exact")
            soft = _lookup(summary, diameter, eta, "R_soft2")
            commit = _lookup(summary, diameter, eta, "R_commit")
            phase_table.append({"partition_diameter": diameter, "eta_fp": eta, "exact_solve": exact["solve_rate"], "soft_solve": soft["solve_rate"], "commit_solve": commit["solve_rate"], "exact_work": exact["mean_penalized_work"], "soft_work": soft["mean_penalized_work"], "exact_over": exact["mean_over_corrections"], "soft_over": soft["mean_over_corrections"]})

    d0 = all(environment["checks"].values()) and semantics["replay_rows"] >= 8 and all(value == 0 for key, value in semantics.items() if key != "replay_rows")
    d1 = all(_lookup(summary, diameter, 0.0, "R_exact")["solve_rate"] >= 0.95 and _lookup(summary, diameter, 0.0, "R_soft2")["solve_rate"] >= 0.95 and _lookup(summary, diameter, 0.0, "R_exact")["mean_over_corrections"] == 0 and _lookup(summary, diameter, 0.0, "R_exact")["solve_rate"] - _lookup(summary, diameter, 0.0, "R_commit")["solve_rate"] >= 0.80 and _lookup(summary, diameter, 0.0, "R_exact")["mean_penalized_work"] < _lookup(summary, diameter, 0.0, "R_soft2")["mean_penalized_work"] for diameter in map(int, substrate["diameters"]))
    d2 = crossing_count >= 3
    pooled_exact = []
    for eta in etas:
        subset = [row for row in rows if row["system"] == "R_exact" and row["eta_fp"] == eta]
        pooled_exact.append({"eta": eta, "solve": mean(float(row["solved"]) for row in subset), "over": mean(float(row["over_corrections"]) for row in subset)})
    d3 = all(left["over"] <= right["over"] + 1e-12 for left, right in zip(pooled_exact, pooled_exact[1:])) and pooled_exact[-1]["solve"] < pooled_exact[0]["solve"]
    high_exact = [row for row in rows if row["system"] == "R_exact" and row["eta_fp"] >= 0.05]
    high_soft = [row for row in rows if row["system"] == "R_soft2" and row["eta_fp"] >= 0.05]
    soft_eta20_groups = sum(int(_lookup(summary, diameter, 0.2, "R_soft2")["solve_rate"] >= 0.90) for diameter in map(int, substrate["diameters"]))
    d4 = mean(float(row["solved"]) for row in high_soft) >= mean(float(row["solved"]) for row in high_exact) and mean(float(row["over_corrections"]) for row in high_soft) < mean(float(row["over_corrections"]) for row in high_exact) and soft_eta20_groups >= 3
    d5 = eta_star["16"] is not None and eta_star["2"] is not None and eta_star["16"] <= eta_star["2"] and _lookup(summary, 16, 0.1, "R_exact")["solve_rate"] <= _lookup(summary, 2, 0.1, "R_exact")["solve_rate"]
    gates = {"D0_environment_semantics": d0, "D1_perfect_signal_asset": d1, "D2_asset_liability_crossing": d2, "D3_recurrent_hazard": d3, "D4_two_hit_robustness": d4, "D5_diameter_direction": d5}
    if not d0:
        status = "RPD_SIGNAL_SAT_DEV_PROTOCOL_FAIL"
    elif all(gates.values()):
        status = "RPD_SIGNAL_SAT_DEV_GO_CONFIRMATION"
    elif d0 and d1 and d2 and d3 and d4:
        status = "RPD_SIGNAL_SAT_DEV_NO_DIAMETER"
    else:
        status = "RPD_SIGNAL_SAT_DEV_NO_GO"

    payload = {"schema": "recurrent_parallel_signal_sat_development_results_v1", "status": status, "headline_eligible": False, "qwen_authorized": False, "independent_confirmation_authorized": status == "RPD_SIGNAL_SAT_DEV_GO_CONFIRMATION", "contract_sha256": _sha256(contract_path), "graph_gate_sha256": _sha256(_resolve(contract["graph_prerequisite"])), "implementation_sha256": _sha256(REPO_ROOT / "experiments/recurrent_parallel_sat_core.py"), "generator_sha256": _sha256(REPO_ROOT / "experiments/signal/long_diameter_sat.py"), "analysis_sha256": _sha256(Path(__file__)), "environment": environment, "semantics": semantics, "gates": gates, "eta_star": eta_star, "phase_table": phase_table, "summary": summary, "rows": rows, "honesty": {"development_only": True, "synthetic_sat_equality_gadgets": True, "no_gpu_or_llm": True, "cross_substrate_claim": False}}
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "instance_manifest.json").write_text(json.dumps({"schema": "recurrent_parallel_signal_sat_development_manifest_v1", "status": "SAT_DEVELOPMENT_MANIFEST_COMPLETE", "rows": rows_public}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "DEVELOPMENT.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({"status": status, "independent_confirmation_authorized": payload["independent_confirmation_authorized"], "rows": len(rows), "report": str((output_dir / "DEVELOPMENT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()
