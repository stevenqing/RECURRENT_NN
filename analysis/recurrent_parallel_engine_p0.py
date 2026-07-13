"""Run and analyze the frozen synchronous RPD P0 development contract."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.recurrent_parallel_core import MODES, run_recurrent_parallel


CONTRACT_SCHEMA = "recurrent_parallel_engine_p0_contract_v1"


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    cells = sorted({(int(row["partition_diameter"]), str(row["mode"]), int(row["round_cap"])) for row in rows})
    for diameter, mode, rounds in cells:
        subset = [
            row for row in rows
            if int(row["partition_diameter"]) == diameter
            and str(row["mode"]) == mode
            and int(row["round_cap"]) == rounds
        ]
        output.append({
            "partition_diameter": diameter,
            "mode": mode,
            "round_cap": rounds,
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_rounds_executed": mean(float(row["rounds_executed"]) for row in subset),
            "mean_agent_updates": mean(float(row["agent_updates"]) for row in subset),
            "mean_state_changes": mean(float(row["state_changes"]) for row in subset),
            "mean_messages_delivered": mean(float(row["messages_delivered"]) for row in subset),
            "mean_final_cross_conflicts": mean(float(row["final_cross_conflicts"]) for row in subset),
            "mean_idealized_parallel_critical_path": mean(float(row["idealized_parallel_critical_path"]) for row in subset),
            "mean_sequential_critical_path": mean(float(row["sequential_local_update_critical_path"]) for row in subset),
            "status_counts": dict(Counter(str(row["status"]) for row in subset)),
        })
    return output


def _pooled(rows: list[dict[str, Any]], mode: str, round_cap: int, min_diameter: int = 4) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if row["mode"] == mode
        and int(row["round_cap"]) == int(round_cap)
        and int(row["partition_diameter"]) >= int(min_diameter)
    ]


def _solve(rows: list[dict[str, Any]]) -> float:
    return mean(float(row["solved"]) for row in rows) if rows else 0.0


def _t90(summary: list[dict[str, Any]], diameter: int, mode: str, budgets: list[int]) -> int | None:
    for budget in sorted(budgets):
        row = next(
            item for item in summary
            if int(item["partition_diameter"]) == int(diameter)
            and item["mode"] == mode
            and int(item["round_cap"]) == int(budget)
        )
        if float(row["solve_rate"]) >= 0.90:
            return int(budget)
    return None


def _render(payload: dict[str, Any]) -> str:
    lines = [
        "# Recurrent Parallel Deliberation P0",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Evidence tier: exposed-pool symbolic recurrent semantics preflight",
        "- Agents: 17 weight-tied local update cells",
        "- Update: immutable Jacobi snapshot → parallel proposals → barrier commit → next-round messages",
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
        "## Recurrent solve by diameter and round budget",
        "",
        "| Diameter | T=1 | T=2 | T=4 | T=8 | T=16 | T=32 | T for ≥0.90 solve |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    recurrent = payload["recurrent_matrix"]
    for diameter in sorted(recurrent, key=int):
        values = recurrent[diameter]
        t90 = payload["round_depth"][diameter]
        lines.append(
            f"| {diameter} | "
            + " | ".join(f"{values[str(budget)]:.3f}" for budget in (1, 2, 4, 8, 16, 32))
            + f" | {'NA' if t90 is None else t90} |"
        )
    controls = payload["pooled_controls_T32"]
    lines.extend([
        "",
        "## Pooled $\delta\ge4$ controls at T=32",
        "",
        "| Mode | Solve | Mean rounds | Final cross conflicts | Idealized critical path | Sequential local-update path |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for mode, row in controls.items():
        lines.append(
            f"| `{mode}` | {row['solve_rate']:.3f} | {row['mean_rounds']:.2f} | "
            f"{row['mean_final_cross_conflicts']:.2f} | {row['mean_idealized_parallel_path']:.2f} | {row['mean_sequential_path']:.2f} |"
        )
    lines.extend([
        "",
        "## Semantics audit",
        "",
        f"- Deterministic replay episodes: `{payload['semantics']['replay_episodes']}`; mismatches: `{payload['semantics']['replay_mismatches']}`.",
        f"- Parallel same-round cross-agent reads: `{payload['semantics']['parallel_same_round_reads']}`.",
        f"- Invalid message-age rows: `{payload['semantics']['invalid_message_age_rows']}`.",
        f"- Invalid local-candidate rows: `{payload['semantics']['invalid_local_candidate_rows']}`.",
        f"- Solved rows failing official verification: `{payload['semantics']['official_score_failures']}`.",
        "",
        "## Interpretation",
        "",
    ])
    if payload["status"] == "RPD_P0_FULL_RECURRENCE_GO":
        lines.append("Both recurrent communication depth and persistent local state are identified. A fixed-$B=MT$ width sweep is authorized.")
    elif payload["status"] == "RPD_MESSAGE_RECURRENCE_ONLY":
        lines.append("Multi-round message propagation is necessary, but persistent local state is not separately identified at T=32. The next stage may test fixed-$B=MT$ communication depth, but cannot yet claim latent-state recurrence.")
    elif payload["status"] == "RPD_P0_NO_RECURRENCE_SIGNAL":
        lines.append("Synchronous semantics pass, but the frozen task/update rule does not identify recurrent communication value. Do not escalate to Qwen or fixed-budget claims.")
    else:
        lines.append("The synchronous engine failed its semantics audit. No scientific interpretation is allowed.")
    lines.extend([
        "",
        "## Honesty boundary",
        "",
        "P0 uses symbolic local coloring candidates and idealized round accounting. It does not establish learned latent-state reasoning, fixed-compute spatial–temporal optimality, real wall-clock parallelism, signal-noise interaction, or a Qwen result.",
        "",
        "## Artifacts",
        "",
        "- [Results JSON](results.json)",
        "- [Frozen P0 contract](../../specs/recurrent_parallel_engine_p0_v1.md)",
        "- [SPEC v7-RPD preflight](../recurrent_signal_phase_v7_preflight/CLOSEOUT.md)",
        "- [RPD strategy](../../specs/multiagent_recurrent_parallel_reasoning_v1.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run synchronous recurrent parallel P0.")
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_engine_p0_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_engine_p0"))
    args = parser.parse_args()
    contract_path = _resolve(args.contract)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("status") != "FROZEN_BEFORE_ENGINE_OUTCOMES":
        raise ValueError("RPD P0 contract is not frozen")
    manifest_path = _resolve(contract["source_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    instances = list(manifest["rows"])
    if len(instances) != 32 or any("planted_assignment" in row for row in instances):
        raise ValueError("RPD P0 source manifest invalid")
    budgets = list(map(int, contract["round_budgets"]))
    modes = list(map(str, contract["modes"]))
    if tuple(modes) != MODES:
        raise ValueError("RPD modes differ from frozen implementation")

    rows: list[dict[str, Any]] = []
    for index, instance in enumerate(instances):
        for mode in modes:
            for budget in budgets:
                rows.append(run_recurrent_parallel(instance, mode=mode, round_cap=budget, root_agent=int(contract["root_agent"])))
        if (index + 1) % 4 == 0:
            print(json.dumps({"event": "rpd_p0_progress", "instances_completed": index + 1}), flush=True)

    replay_targets = [
        row for row in rows
        if row["mode"] == "recurrent_parallel" and int(row["round_cap"]) == 32
    ][:8]
    replay_mismatches = []
    instance_index = {str(row["instance_id"]): row for row in instances}
    for expected in replay_targets:
        replay = run_recurrent_parallel(instance_index[expected["instance_id"]], mode="recurrent_parallel", round_cap=32, root_agent=int(contract["root_agent"]))
        if replay != expected:
            replay_mismatches.append(expected["instance_id"])

    parallel_modes = {"recurrent_parallel", "state_reset", "shuffled_message", "no_message"}
    parallel_rows = [row for row in rows if row["mode"] in parallel_modes]
    semantics = {
        "replay_episodes": len(replay_targets),
        "replay_mismatches": len(replay_mismatches),
        "parallel_same_round_reads": sum(int(row["same_round_cross_agent_reads"]) for row in parallel_rows),
        "invalid_message_age_rows": sum(
            int(row["messages_delivered"] > 0 and int(row["maximum_message_age"]) != 1)
            for row in parallel_rows
        ),
        "invalid_local_candidate_rows": sum(int(not row["local_candidates_valid"]) for row in rows),
        "official_score_failures": sum(int(row["solved"] and not row["official_verification"]) for row in rows),
        "planted_usage_rows": sum(int(row["planted_assignment_used"]) for row in rows),
    }
    p0 = all(value == 0 for key, value in semantics.items() if key not in {"replay_episodes"}) and semantics["replay_episodes"] >= 8

    summary = _summary(rows)
    recurrent_matrix: dict[str, dict[str, float]] = {}
    round_depth: dict[str, int | None] = {}
    for diameter in sorted({int(row["partition_diameter"]) for row in rows}):
        recurrent_matrix[str(diameter)] = {}
        for budget in budgets:
            item = next(
                row for row in summary
                if row["partition_diameter"] == diameter
                and row["mode"] == "recurrent_parallel"
                and row["round_cap"] == budget
            )
            recurrent_matrix[str(diameter)][str(budget)] = float(item["solve_rate"])
        round_depth[str(diameter)] = _t90(summary, diameter, "recurrent_parallel", budgets)

    pooled_recurrent_by_budget = {
        budget: _solve(_pooled(rows, "recurrent_parallel", budget))
        for budget in budgets
    }
    monotonic = all(
        pooled_recurrent_by_budget[left] <= pooled_recurrent_by_budget[right] + 1e-12
        for left, right in zip(budgets, budgets[1:])
    )
    finite_depths = [value for value in round_depth.values() if value is not None]
    depth_direction = len(finite_depths) >= 2 and max(finite_depths) > min(finite_depths)
    p1 = (
        pooled_recurrent_by_budget[32] - pooled_recurrent_by_budget[1] >= 0.15
        and monotonic
        and depth_direction
    )
    solve_t32 = {
        mode: _solve(_pooled(rows, mode, 32))
        for mode in modes
    }
    p2 = (
        solve_t32["recurrent_parallel"] - solve_t32["no_message"] >= 0.10
        and solve_t32["recurrent_parallel"] - solve_t32["shuffled_message"] >= 0.10
    )
    p3 = solve_t32["recurrent_parallel"] - solve_t32["state_reset"] >= 0.10
    sequential_rows = _pooled(rows, "sequential_sharded", 32)
    p4 = (
        len(sequential_rows) == len(_pooled(rows, "recurrent_parallel", 32))
        and all(row["message_semantics"] == "same_round" for row in sequential_rows)
        and all(int(row["same_round_cross_agent_reads"]) > 0 for row in sequential_rows)
    )
    gates = {
        "P0_synchronous_semantics": p0,
        "P1_recurrent_communication_depth": p1,
        "P2_message_necessity": p2,
        "P3_state_persistence": p3,
        "P4_sequential_control": p4,
    }
    if not p0:
        status = "RPD_P0_SEMANTICS_FAIL"
    elif all(gates.values()):
        status = "RPD_P0_FULL_RECURRENCE_GO"
    elif p0 and p1 and p2 and p4 and not p3:
        status = "RPD_MESSAGE_RECURRENCE_ONLY"
    else:
        status = "RPD_P0_NO_RECURRENCE_SIGNAL"

    pooled_controls = {}
    for mode in modes:
        subset = _pooled(rows, mode, 32)
        pooled_controls[mode] = {
            "solve_rate": _solve(subset),
            "mean_rounds": mean(float(row["rounds_executed"]) for row in subset),
            "mean_final_cross_conflicts": mean(float(row["final_cross_conflicts"]) for row in subset),
            "mean_idealized_parallel_path": mean(float(row["idealized_parallel_critical_path"]) for row in subset),
            "mean_sequential_path": mean(float(row["sequential_local_update_critical_path"]) for row in subset),
        }

    payload = {
        "schema": "recurrent_parallel_engine_p0_results_v1",
        "status": status,
        "headline_eligible": False,
        "qwen_authorized": False,
        "fixed_B_width_sweep_authorized": bool(p0 and p1 and p2),
        "contract": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha256(contract_path),
        "manifest": str(manifest_path.relative_to(REPO_ROOT)),
        "manifest_sha256": _sha256(manifest_path),
        "implementation_sha256": _sha256(REPO_ROOT / "experiments/recurrent_parallel_core.py"),
        "analysis_sha256": _sha256(Path(__file__)),
        "gates": gates,
        "semantics": semantics,
        "recurrent_matrix": recurrent_matrix,
        "round_depth": round_depth,
        "pooled_recurrent_by_budget": {str(key): value for key, value in pooled_recurrent_by_budget.items()},
        "pooled_controls_T32": pooled_controls,
        "summary": summary,
        "rows": rows,
        "honesty": {
            "development_only": True,
            "symbolic_candidates": True,
            "idealized_parallel_rounds_only": True,
            "no_gpu_or_llm": True,
            "does_not_establish_fixed_B_optimum": True,
            "does_not_establish_wall_clock_speedup": True,
        },
    }
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "P0.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": status,
        "fixed_B_width_sweep_authorized": payload["fixed_B_width_sweep_authorized"],
        "rows": len(rows),
        "report": str((output_dir / "P0.md").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
