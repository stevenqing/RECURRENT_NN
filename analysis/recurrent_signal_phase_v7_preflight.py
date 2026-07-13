"""CPU environment and development phase preflight for SPEC v7-RPD."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.signal.detector import DeterministicNoisyDetector
from experiments.signal.long_diameter_graph import (
    GraphCompletionOracle,
    canonical_graph_hash,
    generate_long_diameter_graph,
    public_instance,
    reference_engagement,
    verify_coloring,
)
from experiments.signal.systems import SYSTEMS, run_system


CONTRACT_SCHEMA = "recurrent_parallel_signal_phase_v7_contract"


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _calibrate_detector(etas: list[float], n_per_label: int, seed: int) -> dict[str, Any]:
    rows = []
    checks = []
    for eta in etas:
        detector = DeterministicNoisyDetector(float(eta), 0.0, int(seed))
        fp = 0
        fn = 0
        replay_ok = True
        for index in range(int(n_per_label)):
            assignment = {index: 1, index + int(n_per_label): 2}
            first = detector.observe(instance_id="calibration_live", assignment=assignment, true_dead=False, query_index=0)
            second = detector.observe(instance_id="calibration_live", assignment=assignment, true_dead=False, query_index=0)
            replay_ok = replay_ok and first == second
            fp += int(first.observed_dead)
            dead = detector.observe(instance_id="calibration_dead", assignment=assignment, true_dead=True, query_index=0)
            fn += int(not dead.observed_dead)
        realized_fp = fp / int(n_per_label)
        realized_fn = fn / int(n_per_label)
        tolerance = 0.0 if float(eta) in {0.0, 1.0} else max(0.02, 4.0 * math.sqrt(float(eta) * (1.0 - float(eta)) / int(n_per_label)))
        passed = abs(realized_fp - float(eta)) <= tolerance + 1e-12 and realized_fn == 0.0 and replay_ok
        rows.append({
            "eta_fp": float(eta),
            "n_per_label": int(n_per_label),
            "false_positives": fp,
            "false_negatives": fn,
            "realized_fp": realized_fp,
            "realized_fn": realized_fn,
            "tolerance": tolerance,
            "deterministic_replay": replay_ok,
            "pass": passed,
        })
        checks.append(passed)
    return {"pass": all(checks), "rows": rows}


def _summaries(rows: list[dict[str, Any]], failure_penalty: int) -> list[dict[str, Any]]:
    output = []
    cells = sorted({(int(row["partition_diameter"]), float(row["eta_fp"]), str(row["system"])) for row in rows})
    for diameter, eta, system in cells:
        subset = [
            row for row in rows
            if int(row["partition_diameter"]) == diameter
            and float(row["eta_fp"]) == eta
            and str(row["system"]) == system
        ]
        penalized = [float(row["aggregate_work"] if row["solved"] else max(int(row["aggregate_work"]), int(failure_penalty))) for row in subset]
        output.append({
            "partition_diameter": diameter,
            "eta_fp": eta,
            "system": system,
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_work": mean(float(row["aggregate_work"]) for row in subset),
            "mean_penalized_work": mean(penalized),
            "mean_over_rollbacks": mean(float(row["over_rollbacks"]) for row in subset),
            "mean_true_rollbacks": mean(float(row["true_signal_rollbacks"]) for row in subset),
            "mean_restarts": mean(float(row["restarts"]) for row in subset),
            "mean_rounds": mean(float(row["recurrent_rounds"]) for row in subset),
            "status_counts": dict(Counter(str(row["status"]) for row in subset)),
        })
    return output


def _lookup(summary: list[dict[str, Any]], diameter: int, eta: float, system: str) -> dict[str, Any]:
    return next(
        row for row in summary
        if int(row["partition_diameter"]) == int(diameter)
        and abs(float(row["eta_fp"]) - float(eta)) < 1e-12
        and str(row["system"]) == str(system)
    )


def _render(payload: dict[str, Any]) -> str:
    lines = [
        "# SPEC v7-RPD CPU Preflight",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        "- Evidence tier: environment + perfect-signal + development noise probe",
        "- Headline eligible: No",
        "- GPU/LLM use: none",
        "- Substrate: fixed-density planted 3-coloring with exact partition-tree diameter",
        "",
        "## Gates",
        "",
        "| Gate | Result |",
        "|---|---:|",
    ]
    for key, value in payload["gates"].items():
        lines.append(f"| `{key}` | **{'PASS' if value else 'FAIL'}** |")
    audit = payload["environment_audit"]
    lines.extend([
        "",
        "## Environment audit",
        "",
        f"- Instances: `{audit['instances']}`; counts `{json.dumps(audit['diameter_counts'], sort_keys=True)}`.",
        f"- Fixed edge count: `{audit['edge_count']}`; local/cross: `{audit['local_edges']}/{audit['cross_edges']}`.",
        f"- Reference rollback range by diameter: `{json.dumps(audit['rollback_ranges'], sort_keys=True)}`.",
        f"- Candidate-check range by diameter: `{json.dumps(audit['candidate_check_ranges'], sort_keys=True)}`.",
        f"- Difficulty-range overlap: **{'PASS' if audit['difficulty_overlap'] else 'FAIL'}**.",
        "",
        "## Perfect-signal sanity",
        "",
        "| Diameter | Exact solve | Commit solve | Soft2 solve | Exact work | Soft2 work |",
        "|---:|---:|---:|---:|---:|---:|",
    ])
    for row in payload["perfect_signal"]:
        lines.append(
            f"| {row['partition_diameter']} | {row['R_exact_solve']:.3f} | {row['R_commit_solve']:.3f} | "
            f"{row['R_soft2_solve']:.3f} | {row['R_exact_work']:.1f} | {row['R_soft2_work']:.1f} |"
        )
    lines.extend([
        "",
        "## Development phase readout",
        "",
        "| Diameter | Preliminary crossing $\eta^*$ | Low-noise exact favored | Higher-noise soft/commit favored |",
        "|---:|---:|---:|---:|",
    ])
    for row in payload["phase_probe"]:
        crossing = "none" if row["eta_star_preliminary"] is None else f"{row['eta_star_preliminary']:.2f}"
        lines.append(
            f"| {row['partition_diameter']} | {crossing} | {'PASS' if row['low_noise_exact_favored'] else 'FAIL'} | "
            f"{'PASS' if row['higher_noise_alternative_favored'] else 'FAIL'} |"
        )
    lines.extend([
        "",
        "## Full development matrix",
        "",
        "| $\delta$ | $\eta_{fp}$ | System | Solve | Penalized work | Over-rollbacks | True rollbacks |",
        "|---:|---:|---|---:|---:|---:|---:|",
    ])
    for row in payload["summary"]:
        lines.append(
            f"| {row['partition_diameter']} | {row['eta_fp']:.2f} | `{row['system']}` | {row['solve_rate']:.3f} | "
            f"{row['mean_penalized_work']:.1f} | {row['mean_over_rollbacks']:.1f} | {row['mean_true_rollbacks']:.1f} |"
        )
    lines.extend([
        "",
        "## Honesty boundary",
        "",
        "This is a small exposed development preflight. It validates the environment, signal decoupling, exact-register audit, and whether a phase crossing is measurable. It does not establish recurrent parallelism, a final $\eta^*(\delta,T)$ law, a real-Qwen anchor, or a paper claim.",
        "",
        "## Artifacts",
        "",
        "- [Preflight JSON](preflight.json)",
        "- [Development instance manifest](instance_manifest.json)",
        "- [Frozen joint contract](../../specs/recurrent_parallel_signal_phase_v7.md)",
        "- [RPD strategy](../../specs/multiagent_recurrent_parallel_reasoning_v1.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SPEC v7-RPD CPU environment preflight.")
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_signal_phase_v7.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_signal_phase_v7_preflight"))
    parser.add_argument("--base-seed", type=int, default=710000)
    parser.add_argument("--noise-seed", type=int, default=20260712)
    parser.add_argument("--failure-penalty", type=int, default=5000)
    parser.add_argument("--max-activations", type=int, default=5000)
    parser.add_argument("--max-restarts", type=int, default=12)
    args = parser.parse_args()

    contract_path = _resolve(args.contract)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("status") != "FROZEN_BEFORE_PREFLIGHT_OUTCOMES":
        raise ValueError("SPEC v7-RPD contract is not frozen")
    substrate = contract["substrate"]
    preflight = contract["preflight"]
    diameters = list(map(int, substrate["diameters"]))
    target_per_diameter = int(preflight["instances_per_diameter_target"])
    minimum_rollbacks = int(preflight["minimum_true_rollbacks_per_instance"])
    max_candidates = int(preflight["max_generation_candidates_per_diameter"])

    accepted_full: list[dict[str, Any]] = []
    reference_rows: list[dict[str, Any]] = []
    generation_counts: dict[str, int] = {}
    for diameter in diameters:
        accepted = 0
        generated = 0
        for candidate_index in range(max_candidates):
            if accepted >= target_per_diameter:
                break
            generated += 1
            full = generate_long_diameter_graph(
                base_seed=int(args.base_seed),
                candidate_index=candidate_index,
                diameter=diameter,
                n_partitions=int(substrate["n_partitions"]),
                vertices_per_partition=int(substrate["vertices_per_partition"]),
                k=int(substrate["k"]),
                cross_edges_per_tree_edge=int(substrate["cross_variable_edges_per_tree_edge"]),
                split="development",
            )
            planted = {int(key): int(value) for key, value in full["planted_assignment"].items()}
            if not verify_coloring(full, planted):
                continue
            public = public_instance(full)
            reference = reference_engagement(public)
            if not reference.solved or int(reference.true_rollbacks) < minimum_rollbacks:
                continue
            public["graph_sha256"] = canonical_graph_hash(public)
            public["reference_true_rollbacks"] = int(reference.true_rollbacks)
            public["reference_candidate_checks"] = int(reference.candidate_checks)
            public["reference_completion_queries"] = int(reference.completion_queries)
            accepted_full.append(public)
            reference_rows.append({
                "instance_id": public["instance_id"],
                "partition_diameter": diameter,
                "true_rollbacks": int(reference.true_rollbacks),
                "candidate_checks": int(reference.candidate_checks),
                "completion_queries": int(reference.completion_queries),
            })
            accepted += 1
        generation_counts[str(diameter)] = generated

    diameter_counts = Counter(int(row["partition_diameter"]) for row in accepted_full)
    rollback_ranges = {
        str(diameter): [
            min(int(row["true_rollbacks"]) for row in reference_rows if int(row["partition_diameter"]) == diameter),
            max(int(row["true_rollbacks"]) for row in reference_rows if int(row["partition_diameter"]) == diameter),
        ]
        for diameter in diameters
    }
    check_ranges = {
        str(diameter): [
            min(int(row["candidate_checks"]) for row in reference_rows if int(row["partition_diameter"]) == diameter),
            max(int(row["candidate_checks"]) for row in reference_rows if int(row["partition_diameter"]) == diameter),
        ]
        for diameter in diameters
    }
    rollback_overlap = max(value[0] for value in rollback_ranges.values()) <= min(value[1] for value in rollback_ranges.values())
    check_overlap = max(value[0] for value in check_ranges.values()) <= min(value[1] for value in check_ranges.values())
    environment_checks = {
        "complete": all(diameter_counts[diameter] == target_per_diameter for diameter in diameters),
        "exact_diameter": all(int(row["partition_diameter"]) in diameters for row in accepted_full),
        "fixed_edge_count": len({int(row["n_edges"]) for row in accepted_full}) == 1,
        "fixed_local_cross_edges": len({(int(row["n_local_edges"]), int(row["n_cross_edges"])) for row in accepted_full}) == 1,
        "unique_ids": len({str(row["instance_id"]) for row in accepted_full}) == len(accepted_full),
        "unique_graph_hashes": len({str(row["graph_sha256"]) for row in accepted_full}) == len(accepted_full),
        "planted_removed": all("planted_assignment" not in row and bool(row["planted_assignment_removed"]) for row in accepted_full),
        "reference_solved": len(reference_rows) == len(accepted_full),
        "rollback_engaged": all(int(row["true_rollbacks"]) >= minimum_rollbacks for row in reference_rows),
        "difficulty_overlap": rollback_overlap and check_overlap,
    }
    g_env = all(environment_checks.values())
    environment_audit = {
        "pass": g_env,
        "checks": environment_checks,
        "instances": len(accepted_full),
        "diameter_counts": {str(key): value for key, value in sorted(diameter_counts.items())},
        "generation_candidates": generation_counts,
        "edge_count": int(accepted_full[0]["n_edges"]) if accepted_full else None,
        "local_edges": int(accepted_full[0]["n_local_edges"]) if accepted_full else None,
        "cross_edges": int(accepted_full[0]["n_cross_edges"]) if accepted_full else None,
        "rollback_ranges": rollback_ranges,
        "candidate_check_ranges": check_ranges,
        "difficulty_overlap": rollback_overlap and check_overlap,
    }

    calibration = _calibrate_detector(
        list(map(float, contract["signal"]["eta_fp"])),
        int(preflight["noise_calibration_states_per_label"]),
        int(args.noise_seed),
    )
    g1 = bool(calibration["pass"])

    rows: list[dict[str, Any]] = []
    if g_env and g1:
        for index, instance in enumerate(accepted_full):
            shared_oracle = GraphCompletionOracle(instance)
            for eta in map(float, contract["signal"]["eta_fp"]):
                for system in SYSTEMS:
                    row = run_system(
                        instance,
                        system=system,
                        eta_fp=eta,
                        eta_fn=float(contract["signal"]["eta_fn_primary"]),
                        noise_seed=int(args.noise_seed),
                        max_activations=int(args.max_activations),
                        max_restarts=int(args.max_restarts),
                        completion_oracle=shared_oracle,
                    )
                    rows.append(row)
            print(json.dumps({"event": "v7_preflight_progress", "instances_completed": index + 1}), flush=True)
    summary = _summaries(rows, int(args.failure_penalty)) if rows else []

    perfect_signal = []
    g0_checks = []
    for diameter in diameters:
        exact = _lookup(summary, diameter, 0.0, "R_exact") if summary else None
        commit = _lookup(summary, diameter, 0.0, "R_commit") if summary else None
        soft = _lookup(summary, diameter, 0.0, "R_soft2") if summary else None
        if not exact or not commit or not soft:
            g0_checks.append(False)
            continue
        row = {
            "partition_diameter": diameter,
            "R_exact_solve": exact["solve_rate"],
            "R_commit_solve": commit["solve_rate"],
            "R_soft2_solve": soft["solve_rate"],
            "R_exact_work": exact["mean_penalized_work"],
            "R_commit_work": commit["mean_penalized_work"],
            "R_soft2_work": soft["mean_penalized_work"],
        }
        perfect_signal.append(row)
        exact_rows = [item for item in rows if int(item["partition_diameter"]) == diameter and float(item["eta_fp"]) == 0.0 and item["system"] == "R_exact"]
        passed = (
            exact["solve_rate"] >= commit["solve_rate"]
            and exact["mean_true_rollbacks"] > 0
            and exact["mean_over_rollbacks"] == 0
            and all(float(item["register_residual_max"]) <= float(contract["register"]["push_pop_residual_tolerance"]) for item in exact_rows)
            and all(bool(item["official_verification"]) for item in exact_rows if item["solved"])
        )
        g0_checks.append(passed)
    g0 = bool(g0_checks) and all(g0_checks)

    phase_probe = []
    phase_crossings = []
    for diameter in diameters:
        exact_zero = _lookup(summary, diameter, 0.0, "R_exact") if summary else None
        soft_zero = _lookup(summary, diameter, 0.0, "R_soft2") if summary else None
        low_favored = bool(
            exact_zero and soft_zero
            and exact_zero["solve_rate"] >= soft_zero["solve_rate"]
            and exact_zero["mean_penalized_work"] <= soft_zero["mean_penalized_work"]
        )
        crossing = None
        alternative_favored = False
        for eta in sorted(float(value) for value in contract["signal"]["eta_fp"] if float(value) > 0):
            exact = _lookup(summary, diameter, eta, "R_exact") if summary else None
            alternatives = [_lookup(summary, diameter, eta, system) for system in ("R_soft2", "R_commit")] if summary else []
            if not exact:
                continue
            favored = any(
                alt["solve_rate"] > exact["solve_rate"]
                or (
                    alt["solve_rate"] == exact["solve_rate"]
                    and alt["mean_penalized_work"] < exact["mean_penalized_work"]
                )
                for alt in alternatives
            )
            if favored:
                crossing = eta
                alternative_favored = True
                break
        phase_probe.append({
            "partition_diameter": diameter,
            "low_noise_exact_favored": low_favored,
            "higher_noise_alternative_favored": alternative_favored,
            "eta_star_preliminary": crossing,
        })
        phase_crossings.append(low_favored and alternative_favored)
    g2 = bool(phase_crossings) and all(phase_crossings)

    gates = {"G_env_environment": g_env, "G0_perfect_signal": g0, "G1_signal_calibration": g1, "G2_phase_identifiable_development": g2}
    if not g_env:
        status = "V7_PREFLIGHT_ENVIRONMENT_FAIL"
    elif not g1:
        status = "V7_PREFLIGHT_SIGNAL_FAIL"
    elif not g0:
        status = "V7_PREFLIGHT_PERFECT_SIGNAL_FAIL"
    elif g2:
        status = "V7_PREFLIGHT_PHASE_IDENTIFIABLE"
    else:
        status = "V7_PREFLIGHT_NO_CROSSING_OR_UNSTABLE"

    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_payload = {
        "schema": "recurrent_signal_phase_v7_development_manifest_v1",
        "status": "DEVELOPMENT_MANIFEST_COMPLETE" if g_env else "DEVELOPMENT_MANIFEST_FAIL",
        "headline_eligible": False,
        "rows": accepted_full,
    }
    (output_dir / "instance_manifest.json").write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload = {
        "schema": "recurrent_signal_phase_v7_preflight_v1",
        "status": status,
        "headline_eligible": False,
        "contract": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha256(contract_path),
        "gates": gates,
        "environment_audit": environment_audit,
        "reference_rows": reference_rows,
        "signal_calibration": calibration,
        "perfect_signal": perfect_signal,
        "phase_probe": phase_probe,
        "summary": summary,
        "rows": rows,
        "config": {
            "base_seed": int(args.base_seed),
            "noise_seed": int(args.noise_seed),
            "failure_penalty": int(args.failure_penalty),
            "max_activations": int(args.max_activations),
            "max_restarts": int(args.max_restarts),
        },
        "honesty": {
            "development_only": True,
            "no_gpu_or_llm": True,
            "does_not_establish_recurrent_parallelism": True,
            "does_not_establish_final_phase_boundary": True,
            "planted_assignment_unavailable_to_systems": True,
        },
    }
    (output_dir / "preflight.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "PREFLIGHT.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": status,
        "instances": len(accepted_full),
        "rows": len(rows),
        "report": str((output_dir / "PREFLIGHT.md").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
