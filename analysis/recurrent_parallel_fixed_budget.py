"""Run the frozen fixed-B=M*T recurrent width/depth development sweep."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.recurrent_parallel_core import run_fixed_budget_width


CONTRACT_SCHEMA = "recurrent_parallel_fixed_budget_contract_v1"


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for budget, width in sorted({(int(row["budget_cap"]), int(row["width"])) for row in rows}):
        subset = [row for row in rows if int(row["budget_cap"]) == budget and int(row["width"]) == width]
        output.append({
            "budget": budget,
            "width": width,
            "round_cap": int(subset[0]["round_cap"]),
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_rounds": mean(float(row["rounds_executed"]) for row in subset),
            "mean_agent_calls": mean(float(row["agent_calls"]) for row in subset),
            "mean_primitive_updates": mean(float(row["primitive_updates"]) for row in subset),
            "mean_parallel_path": mean(float(row["idealized_parallel_critical_path"]) for row in subset),
            "mean_sequential_path": mean(float(row["sequential_local_update_critical_path"]) for row in subset),
            "mean_messages": mean(float(row["messages_delivered"]) for row in subset),
            "mean_final_conflicts": mean(float(row["final_cross_conflicts"]) for row in subset),
            "mean_context_variable_updates": mean(float(row["total_context_variable_updates"]) for row in subset),
            "mean_attention_proxy": mean(float(row["quadratic_attention_proxy"]) for row in subset),
            "max_context_variables": int(subset[0]["max_context_variables"]),
            "mean_context_variables": float(subset[0]["mean_context_variables"]),
            "cross_agent_edges": int(subset[0]["cross_agent_partition_edges"]),
            "agent_graph_diameter": int(subset[0]["execution_agent_graph_diameter"]),
            "group_sizes": subset[0]["group_sizes"],
        })
    return output


def _lookup(summary: list[dict[str, Any]], budget: int, width: int) -> dict[str, Any]:
    return next(row for row in summary if row["budget"] == int(budget) and row["width"] == int(width))


def _pareto(rows: list[dict[str, Any]]) -> list[int]:
    frontier = []
    for candidate in rows:
        dominated = any(
            other["solve_rate"] >= candidate["solve_rate"]
            and other["mean_parallel_path"] <= candidate["mean_parallel_path"]
            and (
                other["solve_rate"] > candidate["solve_rate"]
                or other["mean_parallel_path"] < candidate["mean_parallel_path"]
            )
            for other in rows
        )
        if not dominated:
            frontier.append(int(candidate["width"]))
    return sorted(frontier)


def _render(payload: dict[str, Any]) -> str:
    lines = [
        "# Recurrent Parallel Deliberation Fixed-Budget Sweep",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Evidence tier: exposed-pool symbolic width/depth development",
        "- Fixed configured agent-call caps: $B\in\{136,272\}$",
        "- Widths: $M\in\{1,2,4,8,17\}$; temporal caps: $T=B/M$",
        "- Each agent call updates exactly one base partition",
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
        "## Width/depth phase table",
        "",
        "| B | M | T cap | Solve | Actual rounds | Agent calls | Max local context | Agent-graph diameter | Attention proxy |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in payload["summary"]:
        lines.append(
            f"| {row['budget']} | {row['width']} | {row['round_cap']} | {row['solve_rate']:.3f} | "
            f"{row['mean_rounds']:.2f} | {row['mean_agent_calls']:.1f} | {row['max_context_variables']} | "
            f"{row['agent_graph_diameter']} | {row['mean_attention_proxy']:.1f} |"
        )
    lines.extend([
        "",
        "## Pareto readout",
        "",
        f"- B=136 solve/parallel-path frontier widths: `{payload['pareto_frontiers']['136']}`.",
        f"- B=272 solve/parallel-path frontier widths: `{payload['pareto_frontiers']['272']}`.",
        f"- Frozen B=136 best interior width: `{payload['interior_readout']['best_interior_width']}`.",
        f"- M=1 mean path: `{payload['interior_readout']['M1_parallel_path']:.2f}`; best interior path: `{payload['interior_readout']['best_interior_parallel_path']:.2f}`; M=17 path: `{payload['interior_readout']['M17_parallel_path']:.2f}`.",
        "",
        "## Accounting audit",
        "",
        f"- Replay rows/mismatches: `{payload['accounting']['replay_rows']}/{payload['accounting']['replay_mismatches']}`.",
        f"- MT mismatches: `{payload['accounting']['MT_mismatches']}`.",
        f"- Primitive/call mismatches: `{payload['accounting']['primitive_call_mismatches']}`.",
        f"- Same-round cross-agent reads: `{payload['accounting']['same_round_reads']}`.",
        f"- Invalid message-age rows: `{payload['accounting']['invalid_message_age_rows']}`.",
        f"- Context/group conservation failures: `{payload['accounting']['resource_conservation_failures']}`.",
        f"- Official-score failures: `{payload['accounting']['official_score_failures']}`.",
        "",
        "## Interpretation",
        "",
    ])
    if payload["status"] == "RPD_FIXED_B_INTERIOR_OPTIMUM_CANDIDATE":
        lines.append("An interior width lies on the frozen solve/critical-path frontier and avoids both centralized depth and maximally wide recurrence starvation. This authorizes a lightweight learned-cell replication, not a Qwen or wall-clock claim.")
    elif payload["status"] == "RPD_FIXED_B_PARETO_NO_WIDTH_FAILURE":
        lines.append("An interior Pareto point exists, but the maximally wide endpoint does not show the frozen recurrence-starvation signature. Scope the result to width/latency tradeoffs.")
    elif payload["status"] == "RPD_FIXED_B_NO_INTERIOR_VALUE":
        lines.append("The frozen sweep does not identify an interior spatial–temporal allocation benefit. Do not escalate to learned or GPU experiments.")
    else:
        lines.append("Accounting or Jacobi semantics failed. No scientific interpretation is allowed.")
    lines.extend([
        "",
        "## Honesty boundary",
        "",
        "B is a configured call cap; early stopping produces different actual calls. Local context size and a quadratic attention proxy are reported because one call at M=1 is not equal-cost to one call at M=17. The proxy is not measured transformer FLOPs or wall-clock.",
        "",
        "## Artifacts",
        "",
        "- [Results JSON](results.json)",
        "- [Frozen width contract](../../specs/recurrent_parallel_fixed_budget_v1.md)",
        "- [RPD P0 closeout](../recurrent_parallel_engine_p0/CLOSEOUT.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fixed-B recurrent width sweep.")
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_fixed_budget_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_fixed_budget"))
    args = parser.parse_args()
    contract_path = _resolve(args.contract)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("status") != "FROZEN_BEFORE_WIDTH_OUTCOMES":
        raise ValueError("fixed-budget contract is not frozen")
    prerequisite_path = _resolve(contract["prerequisite"])
    prerequisite = json.loads(prerequisite_path.read_text(encoding="utf-8"))
    if prerequisite.get("status") not in {"RPD_P0_FULL_RECURRENCE_GO", "RPD_MESSAGE_RECURRENCE_ONLY"} or not prerequisite.get("fixed_B_width_sweep_authorized"):
        raise ValueError("fixed-budget sweep blocked by RPD P0")
    manifest_path = _resolve(contract["source_manifest"])
    instances = list(json.loads(manifest_path.read_text(encoding="utf-8"))["rows"])
    widths = list(map(int, contract["widths"]))
    budgets = list(map(int, contract["budgets"]))

    rows = []
    for index, instance in enumerate(instances):
        for budget in budgets:
            for width in widths:
                rows.append(run_fixed_budget_width(instance, width=width, budget=budget))
        if (index + 1) % 4 == 0:
            print(json.dumps({"event": "fixed_budget_progress", "instances_completed": index + 1}), flush=True)

    replay_targets = rows[:10]
    instance_index = {str(row["instance_id"]): row for row in instances}
    replay_mismatches = 0
    for expected in replay_targets:
        replay = run_fixed_budget_width(instance_index[expected["instance_id"]], width=int(expected["width"]), budget=int(expected["budget_cap"]))
        replay_mismatches += int(replay != expected)

    accounting = {
        "replay_rows": len(replay_targets),
        "replay_mismatches": replay_mismatches,
        "MT_mismatches": sum(int(int(row["configured_MT"]) != int(row["budget_cap"])) for row in rows),
        "primitive_call_mismatches": sum(int(int(row["primitive_updates"]) != int(row["agent_calls"])) for row in rows),
        "same_round_reads": sum(int(row["same_round_cross_agent_reads"]) for row in rows),
        "invalid_message_age_rows": sum(int(row["messages_delivered"] > 0 and int(row["maximum_message_age"]) != 1) for row in rows),
        "resource_conservation_failures": sum(
            int(
                sum(int(value) for value in row["group_sizes"].values()) != 17
                or sum(int(value) for value in row["context_variables"].values()) != 68
                or int(row["cross_agent_partition_edges"]) + int(row["internal_partition_edges"]) != 16
                or int(row["agent_calls"]) > int(row["budget_cap"])
                or int(row["primitive_updates"]) > int(row["budget_cap"])
            )
            for row in rows
        ),
        "official_score_failures": sum(int(row["solved"] and not row["official_verification"]) for row in rows),
        "planted_usage_rows": sum(int(row["planted_assignment_used"]) for row in rows),
        "invalid_local_candidates": sum(int(not row["local_candidates_valid"]) for row in rows),
    }
    w0 = all(value == 0 for key, value in accounting.items() if key != "replay_rows") and accounting["replay_rows"] >= 10
    summary = _summary(rows)
    frontiers = {str(budget): _pareto([row for row in summary if row["budget"] == budget]) for budget in budgets}

    b136 = [_lookup(summary, 136, width) for width in widths]
    endpoint_best_solve = max(_lookup(summary, 136, 1)["solve_rate"], _lookup(summary, 136, 17)["solve_rate"])
    interior = [row for row in b136 if row["width"] in {2, 4, 8}]
    eligible = [
        row for row in interior
        if row["solve_rate"] >= endpoint_best_solve - 0.05
        and row["mean_parallel_path"] <= 0.5 * _lookup(summary, 136, 1)["mean_parallel_path"]
        and row["width"] in frontiers["136"]
    ]
    best_interior = min(eligible, key=lambda row: row["mean_parallel_path"]) if eligible else None
    w1 = bool(best_interior)
    best_interior_solve = max(row["solve_rate"] for row in interior)
    best_interior_path = min(row["mean_parallel_path"] for row in interior if row["solve_rate"] >= best_interior_solve - 0.05)
    m17 = _lookup(summary, 136, 17)
    w2 = m17["solve_rate"] <= best_interior_solve - 0.10 or m17["mean_parallel_path"] > best_interior_path
    w3 = all(_lookup(summary, 272, width)["solve_rate"] + 1e-12 >= _lookup(summary, 136, width)["solve_rate"] for width in widths)
    required_summary_fields = {
        "group_sizes", "max_context_variables", "cross_agent_edges", "agent_graph_diameter",
        "mean_agent_calls", "mean_primitive_updates", "mean_parallel_path", "mean_sequential_path",
        "mean_context_variable_updates", "mean_attention_proxy",
    }
    w4 = all(required_summary_fields.issubset(row) for row in summary) and accounting["resource_conservation_failures"] == 0
    gates = {
        "W0_accounting_semantics": w0,
        "W1_interior_pareto": w1,
        "W2_wide_recurrence_cost": w2,
        "W3_budget_scaling": w3,
        "W4_resource_transparency": w4,
    }
    if not w0:
        status = "RPD_FIXED_B_ACCOUNTING_FAIL"
    elif all(gates.values()):
        status = "RPD_FIXED_B_INTERIOR_OPTIMUM_CANDIDATE"
    elif w0 and w1 and w3 and w4:
        status = "RPD_FIXED_B_PARETO_NO_WIDTH_FAILURE"
    else:
        status = "RPD_FIXED_B_NO_INTERIOR_VALUE"

    interior_readout = {
        "best_interior_width": None if best_interior is None else int(best_interior["width"]),
        "best_interior_solve": None if best_interior is None else float(best_interior["solve_rate"]),
        "best_interior_parallel_path": float(best_interior_path),
        "M1_parallel_path": float(_lookup(summary, 136, 1)["mean_parallel_path"]),
        "M17_parallel_path": float(m17["mean_parallel_path"]),
        "M17_solve": float(m17["solve_rate"]),
    }
    payload = {
        "schema": "recurrent_parallel_fixed_budget_results_v1",
        "status": status,
        "headline_eligible": False,
        "qwen_authorized": False,
        "learned_cell_development_authorized": status in {"RPD_FIXED_B_INTERIOR_OPTIMUM_CANDIDATE", "RPD_FIXED_B_PARETO_NO_WIDTH_FAILURE"},
        "contract_sha256": _sha256(contract_path),
        "prerequisite_sha256": _sha256(prerequisite_path),
        "manifest_sha256": _sha256(manifest_path),
        "implementation_sha256": _sha256(REPO_ROOT / "experiments/recurrent_parallel_core.py"),
        "analysis_sha256": _sha256(Path(__file__)),
        "gates": gates,
        "accounting": accounting,
        "pareto_frontiers": frontiers,
        "interior_readout": interior_readout,
        "summary": summary,
        "rows": rows,
        "honesty": {
            "development_only": True,
            "budget_is_cap_not_forced_consumption": True,
            "context_attention_is_proxy_not_measured_flops": True,
            "no_gpu_or_llm": True,
            "no_wall_clock_claim": True,
            "persistent_state_not_identified_in_P0": True,
        },
    }
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "SUMMARY.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": status,
        "learned_cell_development_authorized": payload["learned_cell_development_authorized"],
        "rows": len(rows),
        "report": str((output_dir / "SUMMARY.md").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
