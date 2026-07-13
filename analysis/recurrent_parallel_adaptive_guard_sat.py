"""Evaluate exposure-calibrated k-hit recurrent verification on exposed SAT data."""

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
from experiments.recurrent_parallel_sat_core import run_noisy_sat_recurrence


CONTRACT_SCHEMA = "recurrent_parallel_adaptive_guard_sat_contract_v1"


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hits(eta: float, diameter: int, p0: float) -> int:
    if float(eta) == 0.0:
        return 1
    exposure = 16 * (int(diameter) + 1)
    return max(1, math.ceil(math.log(1.0 - float(p0) ** (1.0 / exposure)) / math.log(float(eta))))


def _summary(rows: list[dict[str, Any]], penalty: int) -> list[dict[str, Any]]:
    output = []
    for diameter, eta in sorted({(int(row["partition_diameter"]), float(row["eta_fp"])) for row in rows}):
        subset = [row for row in rows if int(row["partition_diameter"]) == diameter and row["eta_fp"] == eta]
        output.append({"partition_diameter": diameter, "eta_fp": eta, "confirmation_hits": int(subset[0]["confirmation_hits"]), "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "mean_penalized_work": mean(float(row["aggregate_work"] if row["solved"] else max(int(row["aggregate_work"]), int(penalty))) for row in subset), "mean_work": mean(float(row["aggregate_work"]) for row in subset), "mean_queries": mean(float(row["detector_queries"]) for row in subset), "mean_over_corrections": mean(float(row["over_corrections"]) for row in subset), "mean_rounds": mean(float(row["rounds_executed"]) for row in subset), "status_counts": dict(Counter(str(row["status"]) for row in subset))})
    return output


def _lookup(summary: list[dict[str, Any]], diameter: int, eta: float) -> dict[str, Any]:
    return next(row for row in summary if row["partition_diameter"] == int(diameter) and abs(row["eta_fp"] - float(eta)) < 1e-12)


def _parent_lookup(rows: list[dict[str, Any]], instance_id: str, system: str, eta: float) -> dict[str, Any]:
    return next(row for row in rows if row["instance_id"] == instance_id and row["system"] == system and abs(row["eta_fp"] - float(eta)) < 1e-12)


def _render(payload: dict[str, Any]) -> str:
    lines = [
        "# Exposure-Calibrated Recurrent Verification — SAT Development",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Policy: minimum k satisfying $(1-\eta^k)^{16(\delta+1)}\ge0.95$",
        "- New adaptive rows: 192",
        "- Frozen one-hit/two-hit controls reused without rerun",
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
        "## Adaptive policy matrix",
        "",
        "| Diameter | Eta | k | Adaptive solve | Soft2 solve | Adaptive over | Soft2 over | Adaptive work | Soft2 work |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in payload["comparison"]:
        lines.append(f"| {row['partition_diameter']} | {row['eta_fp']:.2f} | {row['confirmation_hits']} | {row['adaptive_solve']:.3f} | {row['soft_solve']:.3f} | {row['adaptive_over']:.2f} | {row['soft_over']:.2f} | {row['adaptive_work']:.1f} | {row['soft_work']:.1f} |")
    lines.extend([
        "",
        "## Integrity",
        "",
        f"- Schedule mismatches: `{payload['integrity']['schedule_mismatches']}`.",
        f"- Replay rows/mismatches: `{payload['integrity']['replay_rows']}/{payload['integrity']['replay_mismatches']}`.",
        f"- Eta=0 control mismatches: `{payload['integrity']['eta0_control_mismatches']}`.",
        f"- Same-round/message/local/official/planted violations: `{payload['integrity']['protocol_violations']}`.",
        "",
        "## Interpretation",
        "",
    ])
    if payload["status"] == "RPD_ADAPTIVE_GUARD_SAT_DEV_GO_CONFIRMATION":
        lines.append("The outcome-independent exposure-calibrated guard repairs the frozen SAT two-hit failures and has charged Pareto value. A new zero-overlap SAT confirmation is authorized.")
    elif payload["status"] == "RPD_ADAPTIVE_GUARD_ROBUST_NO_VALUE":
        lines.append("The adaptive guard is robust but does not improve the failed cells after charging verification. Do not confirm it as a resource contribution.")
    elif payload["status"] == "RPD_ADAPTIVE_GUARD_SAT_NO_GO":
        lines.append("Exposure calibration does not restore robust SAT solve. Close the adaptive-guard line.")
    else:
        lines.append("Policy or protocol integrity failed; no interpretation is allowed.")
    lines.extend([
        "",
        "## Honesty boundary",
        "",
        "This policy was frozen after observing the fixed-two-hit failure but before adaptive outcomes. The source instances are exposed development data. Only a new zero-overlap confirmation can support a SAT or cross-substrate claim.",
        "",
        "## Artifacts",
        "",
        "- [Results JSON](results.json)",
        "- [Frozen adaptive contract](../../specs/recurrent_parallel_adaptive_guard_sat_v1.md)",
        "- [Parent SAT no-go](../recurrent_parallel_signal_sat_development/CLOSEOUT.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run exposure-calibrated SAT recurrent guard development.")
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_adaptive_guard_sat_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_adaptive_guard_sat"))
    args = parser.parse_args()
    contract_path = _resolve(args.contract)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("status") != "FROZEN_BEFORE_ADAPTIVE_OUTCOMES":
        raise ValueError("adaptive SAT contract is not frozen")
    parent_path = _resolve(contract["parent_results"])
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    if parent.get("status") != "RPD_SIGNAL_SAT_DEV_NO_GO":
        raise ValueError("adaptive SAT expects the frozen parent no-go")
    manifest_path = _resolve(contract["source_manifest"])
    instances = list(json.loads(manifest_path.read_text(encoding="utf-8"))["rows"])
    p0 = float(contract["p0"])
    etas = list(map(float, contract["eta_fp"]))

    computed_schedule = {str(diameter): {str(eta): _hits(eta, diameter, p0) for eta in etas} for diameter in (2, 4, 8, 16)}
    frozen_schedule = {str(diameter): {str(float(eta)): int(value) for eta, value in schedule.items()} for diameter, schedule in contract["schedule"].items()}
    schedule_mismatches = sum(int(computed_schedule[diameter][eta] != frozen_schedule[diameter][eta]) for diameter in computed_schedule for eta in computed_schedule[diameter])

    rows = []
    for index, instance in enumerate(instances):
        diameter = int(instance["partition_diameter"])
        for eta in etas:
            rows.append(run_noisy_sat_recurrence(instance, system="R_adaptive", eta_fp=eta, round_cap=int(contract["round_cap"]), noise_seed=int(contract["noise_seed"]), confirmation_hits=_hits(eta, diameter, p0)))
        if (index + 1) % 4 == 0:
            print(json.dumps({"event": "adaptive_sat_progress", "instances_completed": index + 1}), flush=True)

    replay_targets = [row for row in rows if row["eta_fp"] == 0.2][:8]
    instance_index = {row["instance_id"]: row for row in instances}
    replay_mismatches = sum(int(run_noisy_sat_recurrence(instance_index[row["instance_id"]], system="R_adaptive", eta_fp=0.2, round_cap=32, noise_seed=int(contract["noise_seed"]), confirmation_hits=_hits(0.2, int(row["partition_diameter"]), p0)) != row) for row in replay_targets)
    parent_rows = list(parent["rows"])
    eta0_mismatches = 0
    for row in [item for item in rows if item["eta_fp"] == 0.0]:
        control = _parent_lookup(parent_rows, row["instance_id"], "R_exact", 0.0)
        fields = ("solved", "rounds_executed", "candidate_corrections", "over_corrections", "aggregate_work", "final_cross_violations")
        eta0_mismatches += int(any(row[field] != control[field] for field in fields))
    protocol_violations = sum(int(row["same_round_cross_agent_reads"] != 0 or (row["messages_delivered"] > 0 and row["maximum_message_age"] != 1) or not row["local_candidates_valid"] or (row["solved"] and not row["official_verification"]) or row["planted_assignment_used"]) for row in rows)
    integrity = {"schedule_mismatches": schedule_mismatches, "replay_rows": len(replay_targets), "replay_mismatches": replay_mismatches, "eta0_control_mismatches": eta0_mismatches, "protocol_violations": protocol_violations}
    a0 = integrity["replay_rows"] >= 8 and all(value == 0 for key, value in integrity.items() if key != "replay_rows")

    summary = _summary(rows, int(contract["failure_penalty"]))
    parent_summary = list(parent["summary"])
    comparison = []
    for diameter in (2, 4, 8, 16):
        for eta in etas:
            adaptive = _lookup(summary, diameter, eta)
            soft = next(row for row in parent_summary if row["partition_diameter"] == diameter and row["eta_fp"] == eta and row["system"] == "R_soft2")
            comparison.append({"partition_diameter": diameter, "eta_fp": eta, "confirmation_hits": adaptive["confirmation_hits"], "adaptive_solve": adaptive["solve_rate"], "soft_solve": soft["solve_rate"], "adaptive_over": adaptive["mean_over_corrections"], "soft_over": soft["mean_over_corrections"], "adaptive_work": adaptive["mean_penalized_work"], "soft_work": soft["mean_penalized_work"]})
    a1 = all(row["adaptive_solve"] >= 0.90 for row in comparison)
    row8 = next(row for row in comparison if row["partition_diameter"] == 8 and row["eta_fp"] == 0.2)
    row16 = next(row for row in comparison if row["partition_diameter"] == 16 and row["eta_fp"] == 0.2)
    a2 = row8["adaptive_solve"] - row8["soft_solve"] >= 0.10 and row16["adaptive_solve"] - row16["soft_solve"] >= 0.50
    a3 = all(row["adaptive_over"] <= row["soft_over"] + 1e-12 for row in comparison) and row16["adaptive_over"] <= 1.0
    a4 = eta0_mismatches == 0
    a5 = all(row["adaptive_solve"] > row["soft_solve"] and row["adaptive_work"] < row["soft_work"] for row in (row8, row16))
    gates = {"A0_policy_integrity": a0, "A1_robust_solve": a1, "A2_failed_cell_repair": a2, "A3_hazard_control": a3, "A4_perfect_signal_equivalence": a4, "A5_charged_pareto_value": a5}
    if not a0:
        status = "RPD_ADAPTIVE_GUARD_PROTOCOL_FAIL"
    elif all(gates.values()):
        status = "RPD_ADAPTIVE_GUARD_SAT_DEV_GO_CONFIRMATION"
    elif a0 and a1 and a4:
        status = "RPD_ADAPTIVE_GUARD_ROBUST_NO_VALUE"
    else:
        status = "RPD_ADAPTIVE_GUARD_SAT_NO_GO"

    payload = {"schema": "recurrent_parallel_adaptive_guard_sat_results_v1", "status": status, "headline_eligible": False, "qwen_authorized": False, "independent_confirmation_authorized": status == "RPD_ADAPTIVE_GUARD_SAT_DEV_GO_CONFIRMATION", "contract_sha256": _sha256(contract_path), "parent_results_sha256": _sha256(parent_path), "manifest_sha256": _sha256(manifest_path), "implementation_sha256": _sha256(REPO_ROOT / "experiments/recurrent_parallel_sat_core.py"), "analysis_sha256": _sha256(Path(__file__)), "computed_schedule": computed_schedule, "integrity": integrity, "gates": gates, "comparison": comparison, "summary": summary, "rows": rows, "honesty": {"formula_frozen_before_adaptive_outcomes": True, "source_pool_exposed": True, "no_gpu_or_llm": True, "no_cross_substrate_claim": True}}
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "SUMMARY.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({"status": status, "independent_confirmation_authorized": payload["independent_confirmation_authorized"], "rows": len(rows), "report": str((output_dir / "SUMMARY.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()
