"""Run and analyze recurrent correction under injected rollback-signal noise."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.recurrent_parallel_core import SIGNAL_SYSTEMS, run_noisy_recurrent_correction


CONTRACT_SCHEMA = "recurrent_parallel_signal_noise_contract_v1"


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summary(rows: list[dict[str, Any]], failure_penalty: int) -> list[dict[str, Any]]:
    output = []
    cells = sorted({(int(row["partition_diameter"]), int(row["round_cap"]), float(row["eta_fp"]), str(row["system"])) for row in rows})
    for diameter, rounds, eta, system in cells:
        subset = [row for row in rows if int(row["partition_diameter"]) == diameter and int(row["round_cap"]) == rounds and float(row["eta_fp"]) == eta and row["system"] == system]
        penalized = [float(row["aggregate_work"] if row["solved"] else max(int(row["aggregate_work"]), int(failure_penalty))) for row in subset]
        output.append({
            "partition_diameter": diameter,
            "round_cap": rounds,
            "eta_fp": eta,
            "system": system,
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_penalized_work": mean(penalized),
            "mean_work": mean(float(row["aggregate_work"]) for row in subset),
            "mean_rounds": mean(float(row["rounds_executed"]) for row in subset),
            "mean_detector_queries": mean(float(row["detector_queries"]) for row in subset),
            "mean_over_corrections": mean(float(row["over_corrections"]) for row in subset),
            "mean_true_corrections": mean(float(row["true_corrections_executed"]) for row in subset),
            "mean_final_conflicts": mean(float(row["final_cross_conflicts"]) for row in subset),
            "status_counts": dict(Counter(str(row["status"]) for row in subset)),
        })
    return output


def _lookup(summary: list[dict[str, Any]], diameter: int, rounds: int, eta: float, system: str) -> dict[str, Any]:
    return next(row for row in summary if row["partition_diameter"] == int(diameter) and row["round_cap"] == int(rounds) and abs(row["eta_fp"] - float(eta)) < 1e-12 and row["system"] == system)


def _favored(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left["solve_rate"] > right["solve_rate"] or (
        left["solve_rate"] == right["solve_rate"]
        and left["mean_penalized_work"] < right["mean_penalized_work"]
    )


def _render(payload: dict[str, Any]) -> str:
    lines = [
        "# Recurrent Parallel Signal-Noise Sweep",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Evidence tier: exposed-pool recurrent noise development",
        "- Systems: one-hit exact correction, two-hit correction, ignore/commit",
        "- Noise: deterministic false-positive correction signal",
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
        "## T=32 asset↔liability matrix",
        "",
        "| Diameter | Eta | Exact solve | Soft2 solve | Commit solve | Exact work | Soft2 work | Exact over-corrections | Soft2 over-corrections |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in payload["T32_matrix"]:
        lines.append(
            f"| {row['partition_diameter']} | {row['eta_fp']:.2f} | {row['exact_solve']:.3f} | {row['soft_solve']:.3f} | "
            f"{row['commit_solve']:.3f} | {row['exact_work']:.1f} | {row['soft_work']:.1f} | "
            f"{row['exact_over']:.1f} | {row['soft_over']:.1f} |"
        )
    lines.extend([
        "",
        "## Preliminary crossing by diameter and T",
        "",
        "| Diameter | T=2 | T=4 | T=8 | T=16 | T=32 |",
        "|---:|---:|---:|---:|---:|---:|",
    ])
    for diameter, values in payload["eta_star"].items():
        lines.append(
            f"| {diameter} | " + " | ".join("none" if values[str(rounds)] is None else f"{values[str(rounds)]:.2f}" for rounds in (2, 4, 8, 16, 32)) + " |"
        )
    lines.extend([
        "",
        "## Pooled exact hazard",
        "",
        "| Eta | Solve | Mean over-corrections | Mean detector queries | Penalized work |",
        "|---:|---:|---:|---:|---:|",
    ])
    for row in payload["pooled_exact_hazard"]:
        lines.append(f"| {row['eta_fp']:.2f} | {row['solve_rate']:.3f} | {row['mean_over_corrections']:.2f} | {row['mean_detector_queries']:.1f} | {row['mean_penalized_work']:.1f} |")
    lines.extend([
        "",
        "## Semantics audit",
        "",
        f"- Replay rows/mismatches: `{payload['semantics']['replay_rows']}/{payload['semantics']['replay_mismatches']}`.",
        f"- Eta=0 matrix mismatches versus P0: `{payload['semantics']['eta0_matrix_mismatches']}`.",
        f"- Same-round reads: `{payload['semantics']['same_round_reads']}`.",
        f"- Invalid message-age rows: `{payload['semantics']['invalid_message_age_rows']}`.",
        f"- Eta=0 false positives/over-corrections: `{payload['semantics']['eta0_false_positives']}/{payload['semantics']['eta0_over_corrections']}`.",
        f"- Official-score failures: `{payload['semantics']['official_score_failures']}`.",
        "",
        "## Interpretation",
        "",
    ])
    if payload["status"] == "RPD_SIGNAL_PHASE_DIAMETER_CANDIDATE":
        lines.append("The recurrent asset↔liability crossing is measurable and shifts in the frozen diameter direction. New zero-overlap graph/SAT confirmation is authorized; Qwen remains blocked.")
    elif payload["status"] == "RPD_SIGNAL_PHASE_NO_DIAMETER_SHIFT":
        lines.append("The recurrent asset↔liability crossing is measurable, but the frozen diameter shift is not identified. Scope the result to signal hazard, not a diameter law.")
    elif payload["status"] == "RPD_SIGNAL_PHASE_NO_CROSSING":
        lines.append("Perfect-signal recurrence works, but no frozen crossing is identified. Do not escalate to confirmation or Qwen.")
    else:
        lines.append("The eta=0 recurrent harness failed equivalence or semantics checks. No scientific interpretation is allowed.")
    lines.extend([
        "",
        "## Honesty boundary",
        "",
        "This is exposed development data with symbolic correction labels and idealized parallel rounds. It does not establish an independent phase law, real-Qwen signal placement, learned state, measured GPU speedup, or a paper claim.",
        "",
        "## Artifacts",
        "",
        "- [Results JSON](results.json)",
        "- [Frozen recurrent-noise contract](../../specs/recurrent_parallel_signal_noise_v1.md)",
        "- [SPEC v7-RPD preflight](../recurrent_signal_phase_v7_preflight/CLOSEOUT.md)",
        "- [RPD P0 closeout](../recurrent_parallel_engine_p0/CLOSEOUT.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run recurrent correction signal-noise sweep.")
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_signal_noise_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_signal_noise"))
    parser.add_argument("--noise-seed", type=int, default=20260712)
    args = parser.parse_args()
    contract_path = _resolve(args.contract)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("status") != "FROZEN_BEFORE_RECURRENT_NOISE_OUTCOMES":
        raise ValueError("recurrent signal-noise contract is not frozen")
    prerequisite_payloads = [json.loads(_resolve(path).read_text(encoding="utf-8")) for path in contract["prerequisites"]]
    expected_statuses = {"V7_PREFLIGHT_PHASE_IDENTIFIABLE", "RPD_MESSAGE_RECURRENCE_ONLY", "RPD_FIXED_B_INTERIOR_OPTIMUM_CANDIDATE"}
    if {payload.get("status") for payload in prerequisite_payloads} != expected_statuses:
        raise ValueError("recurrent signal-noise prerequisites failed")
    p0 = next(payload for payload in prerequisite_payloads if payload.get("status") == "RPD_MESSAGE_RECURRENCE_ONLY")
    manifest_path = _resolve(contract["source_manifest"])
    instances = list(json.loads(manifest_path.read_text(encoding="utf-8"))["rows"])
    systems = list(map(str, contract["systems"]))
    etas = list(map(float, contract["eta_fp"]))
    budgets = list(map(int, contract["round_budgets"]))
    if tuple(systems) != SIGNAL_SYSTEMS:
        raise ValueError("signal systems differ from implementation")

    rows = []
    for index, instance in enumerate(instances):
        for rounds in budgets:
            for eta in etas:
                for system in systems:
                    rows.append(run_noisy_recurrent_correction(instance, system=system, eta_fp=eta, eta_fn=float(contract["eta_fn"]), round_cap=rounds, noise_seed=int(args.noise_seed)))
        if (index + 1) % 4 == 0:
            print(json.dumps({"event": "recurrent_noise_progress", "instances_completed": index + 1}), flush=True)

    replay_targets = [row for row in rows if row["system"] == "R_exact" and row["eta_fp"] == 0.1 and row["round_cap"] == 32][:8]
    instance_index = {str(row["instance_id"]): row for row in instances}
    replay_mismatches = 0
    for expected in replay_targets:
        replay = run_noisy_recurrent_correction(instance_index[expected["instance_id"]], system="R_exact", eta_fp=0.1, round_cap=32, noise_seed=int(args.noise_seed))
        replay_mismatches += int(replay != expected)

    summary = _summary(rows, int(contract["failure_penalty"]))
    eta0_mismatches = 0
    for diameter in (2, 4, 8, 16):
        for rounds in budgets:
            observed = _lookup(summary, diameter, rounds, 0.0, "R_exact")["solve_rate"]
            expected = float(p0["recurrent_matrix"][str(diameter)][str(rounds)])
            eta0_mismatches += int(abs(observed - expected) > 1e-12)
    eta0_exact_rows = [row for row in rows if row["system"] == "R_exact" and float(row["eta_fp"]) == 0.0]
    semantics = {
        "replay_rows": len(replay_targets),
        "replay_mismatches": replay_mismatches,
        "eta0_matrix_mismatches": eta0_mismatches,
        "same_round_reads": sum(int(row["same_round_cross_agent_reads"]) for row in rows),
        "invalid_message_age_rows": sum(int(row["messages_delivered"] > 0 and int(row["maximum_message_age"]) != 1) for row in rows),
        "eta0_false_positives": sum(int(row["false_positives"]) for row in eta0_exact_rows),
        "eta0_over_corrections": sum(int(row["over_corrections"]) for row in eta0_exact_rows),
        "invalid_local_candidates": sum(int(not row["local_candidates_valid"]) for row in rows),
        "official_score_failures": sum(int(row["solved"] and not row["official_verification"]) for row in rows),
        "planted_usage_rows": sum(int(row["planted_assignment_used"]) for row in rows),
    }
    n0 = semantics["replay_rows"] >= 8 and all(value == 0 for key, value in semantics.items() if key != "replay_rows")

    eta_star: dict[str, dict[str, float | None]] = {}
    crossing_groups = 0
    low_exact_groups = 0
    for diameter in (2, 4, 8, 16):
        eta_star[str(diameter)] = {}
        for rounds in budgets:
            exact0 = _lookup(summary, diameter, rounds, 0.0, "R_exact")
            soft0 = _lookup(summary, diameter, rounds, 0.0, "R_soft2")
            low_exact = exact0["solve_rate"] >= soft0["solve_rate"] and exact0["mean_penalized_work"] < soft0["mean_penalized_work"]
            low_exact_groups += int(low_exact)
            crossing = None
            for eta in etas[1:]:
                exact = _lookup(summary, diameter, rounds, eta, "R_exact")
                soft = _lookup(summary, diameter, rounds, eta, "R_soft2")
                if _favored(soft, exact):
                    crossing = eta
                    break
            eta_star[str(diameter)][str(rounds)] = crossing
            crossing_groups += int(low_exact and crossing is not None)
    n1 = low_exact_groups > 0 and crossing_groups >= 3

    pooled_exact_hazard = []
    over_by_eta = []
    for eta in etas:
        subset = [row for row in rows if row["system"] == "R_exact" and float(row["eta_fp"]) == eta]
        penalized = [float(row["aggregate_work"] if row["solved"] else max(int(row["aggregate_work"]), int(contract["failure_penalty"]))) for row in subset]
        item = {
            "eta_fp": eta,
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_over_corrections": mean(float(row["over_corrections"]) for row in subset),
            "mean_detector_queries": mean(float(row["detector_queries"]) for row in subset),
            "mean_penalized_work": mean(penalized),
        }
        pooled_exact_hazard.append(item)
        over_by_eta.append(item["mean_over_corrections"])
    over_monotonic = all(left <= right + 1e-12 for left, right in zip(over_by_eta, over_by_eta[1:]))
    eta0_solve = pooled_exact_hazard[0]["solve_rate"]
    eta20_solve = next(row["solve_rate"] for row in pooled_exact_hazard if abs(row["eta_fp"] - 0.2) < 1e-12)
    exposure_delta2 = _lookup(summary, 2, 32, 0.0, "R_exact")["mean_detector_queries"]
    exposure_delta16 = _lookup(summary, 16, 32, 0.0, "R_exact")["mean_detector_queries"]
    n2 = over_monotonic and eta20_solve <= eta0_solve and exposure_delta16 > exposure_delta2

    eta_star2 = eta_star["2"]["32"]
    eta_star16 = eta_star["16"]["32"]
    common_direction = any(
        _lookup(summary, 16, 32, eta, "R_exact")["solve_rate"] <= _lookup(summary, 2, 32, eta, "R_exact")["solve_rate"]
        for eta in etas[1:]
    )
    n3 = eta_star2 is not None and eta_star16 is not None and eta_star16 <= eta_star2 and common_direction

    high_exact = [row for row in rows if row["system"] == "R_exact" and float(row["eta_fp"]) >= 0.05]
    high_soft = [row for row in rows if row["system"] == "R_soft2" and float(row["eta_fp"]) >= 0.05]
    n4 = (
        mean(float(row["solved"]) for row in high_soft) >= mean(float(row["solved"]) for row in high_exact)
        and mean(float(row["over_corrections"]) for row in high_soft) < mean(float(row["over_corrections"]) for row in high_exact)
        and sum(int(row["detector_queries"]) for row in high_soft) > 0
    )
    exact_commit_pool = [row for row in rows if int(row["partition_diameter"]) >= 4 and int(row["round_cap"]) == 32 and float(row["eta_fp"]) == 0.0]
    exact_solve = mean(float(row["solved"]) for row in exact_commit_pool if row["system"] == "R_exact")
    commit_solve = mean(float(row["solved"]) for row in exact_commit_pool if row["system"] == "R_commit")
    n5 = exact_solve - commit_solve >= 0.15
    gates = {
        "N0_perfect_signal_recurrence": n0,
        "N1_asset_liability_identifiable": n1,
        "N2_recurrent_hazard_accumulation": n2,
        "N3_diameter_sensitive_boundary": n3,
        "N4_two_hit_robustness": n4,
        "N5_correction_necessity": n5,
    }
    if not n0:
        status = "RPD_SIGNAL_PHASE_HARNESS_FAIL"
    elif all(gates.values()):
        status = "RPD_SIGNAL_PHASE_DIAMETER_CANDIDATE"
    elif n0 and n1 and n2 and n4 and n5:
        status = "RPD_SIGNAL_PHASE_NO_DIAMETER_SHIFT"
    else:
        status = "RPD_SIGNAL_PHASE_NO_CROSSING"

    t32_matrix = []
    for diameter in (2, 4, 8, 16):
        for eta in etas:
            exact = _lookup(summary, diameter, 32, eta, "R_exact")
            soft = _lookup(summary, diameter, 32, eta, "R_soft2")
            commit = _lookup(summary, diameter, 32, eta, "R_commit")
            t32_matrix.append({
                "partition_diameter": diameter,
                "eta_fp": eta,
                "exact_solve": exact["solve_rate"],
                "soft_solve": soft["solve_rate"],
                "commit_solve": commit["solve_rate"],
                "exact_work": exact["mean_penalized_work"],
                "soft_work": soft["mean_penalized_work"],
                "exact_over": exact["mean_over_corrections"],
                "soft_over": soft["mean_over_corrections"],
            })
    payload = {
        "schema": "recurrent_parallel_signal_noise_results_v1",
        "status": status,
        "headline_eligible": False,
        "qwen_authorized": False,
        "independent_confirmation_authorized": status == "RPD_SIGNAL_PHASE_DIAMETER_CANDIDATE",
        "contract_sha256": _sha256(contract_path),
        "manifest_sha256": _sha256(manifest_path),
        "implementation_sha256": _sha256(REPO_ROOT / "experiments/recurrent_parallel_core.py"),
        "analysis_sha256": _sha256(Path(__file__)),
        "gates": gates,
        "semantics": semantics,
        "eta_star": eta_star,
        "pooled_exact_hazard": pooled_exact_hazard,
        "T32_matrix": t32_matrix,
        "summary": summary,
        "rows": rows,
        "honesty": {
            "development_only": True,
            "symbolic_correction_truth": True,
            "idealized_parallel_rounds": True,
            "no_gpu_or_llm": True,
            "no_independent_claim": True,
        },
    }
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "SUMMARY.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": status,
        "independent_confirmation_authorized": payload["independent_confirmation_authorized"],
        "rows": len(rows),
        "report": str((output_dir / "SUMMARY.md").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
