"""Run and analyze the frozen compressed-message recurrent-state gate."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.recurrent_parallel_core import COMPRESSED_MODES, run_compressed_recurrence


CONTRACT_SCHEMA = "recurrent_parallel_compressed_state_contract_v1"


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for diameter, mode, budget in sorted({(int(row["partition_diameter"]), str(row["mode"]), int(row["round_cap"])) for row in rows}):
        subset = [row for row in rows if int(row["partition_diameter"]) == diameter and row["mode"] == mode and int(row["round_cap"]) == budget]
        output.append({
            "partition_diameter": diameter,
            "mode": mode,
            "round_cap": budget,
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_rounds": mean(float(row["rounds_executed"]) for row in subset),
            "mean_updates": mean(float(row["agent_updates"]) for row in subset),
            "mean_final_conflicts": mean(float(row["final_cross_conflicts"]) for row in subset),
            "mean_facts_delivered": mean(float(row["message_facts_delivered"]) for row in subset),
            "mean_full_fact_equivalent": mean(float(row["full_message_fact_equivalent"]) for row in subset),
            "mean_compression_ratio": mean(float(row["compression_ratio"]) for row in subset),
            "mean_state_changes": mean(float(row["state_changes"]) for row in subset),
            "max_cache_facts": max(int(row["max_cache_facts"]) for row in subset),
            "status_counts": dict(Counter(str(row["status"]) for row in subset)),
        })
    return output


def _lookup(summary: list[dict[str, Any]], diameter: int, mode: str, budget: int) -> dict[str, Any]:
    return next(row for row in summary if row["partition_diameter"] == int(diameter) and row["mode"] == mode and row["round_cap"] == int(budget))


def _pooled(rows: list[dict[str, Any]], mode: str, budget: int) -> list[dict[str, Any]]:
    return [row for row in rows if row["mode"] == mode and int(row["round_cap"]) == int(budget) and int(row["partition_diameter"]) >= 4]


def _solve(rows: list[dict[str, Any]]) -> float:
    return mean(float(row["solved"]) for row in rows)


def _t90(summary: list[dict[str, Any]], diameter: int, mode: str, budgets: list[int]) -> int | None:
    for budget in sorted(budgets):
        if _lookup(summary, diameter, mode, budget)["solve_rate"] >= 0.90:
            return int(budget)
    return None


def _render(payload: dict[str, Any]) -> str:
    lines = [
        "# RPD Compressed-Message State Gate",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Evidence tier: exposed-pool symbolic recurrent-state development",
        "- Message bottleneck: one boundary fact per parent→child per round",
        "- Persistent message cache: at most two keyed facts per agent",
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
        "## Pooled $\delta\ge4$ controls at T=32",
        "",
        "| Mode | Solve | Mean rounds | Final conflicts | Facts/full equivalent | Max cache facts |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for mode, row in payload["pooled_controls_T32"].items():
        lines.append(
            f"| `{mode}` | {row['solve_rate']:.3f} | {row['mean_rounds']:.2f} | {row['mean_final_conflicts']:.2f} | "
            f"{row['compression_ratio']:.3f} | {row['max_cache_facts']} |"
        )
    lines.extend([
        "",
        "## Compressed-persistent recurrence depth",
        "",
        "| Diameter | T=1 | T=2 | T=4 | T=8 | T=16 | T=32 | T for ≥0.90 solve |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for diameter, values in payload["persistent_matrix"].items():
        t90 = payload["round_depth"][diameter]
        lines.append(
            f"| {diameter} | " + " | ".join(f"{values[str(budget)]:.3f}" for budget in (1, 2, 4, 8, 16, 32)) + f" | {'NA' if t90 is None else t90} |"
        )
    lines.extend([
        "",
        "## Semantics audit",
        "",
        f"- Replay rows/mismatches: `{payload['semantics']['replay_rows']}/{payload['semantics']['replay_mismatches']}`.",
        f"- Same-round reads: `{payload['semantics']['same_round_reads']}`.",
        f"- Invalid message-age rows: `{payload['semantics']['invalid_message_age_rows']}`.",
        f"- Fragment-size violations: `{payload['semantics']['fragment_size_violations']}`.",
        f"- Compressed cache-bound violations: `{payload['semantics']['cache_bound_violations']}`.",
        f"- Hidden full-message reads: `{payload['semantics']['hidden_full_message_reads']}`.",
        f"- Official-score failures: `{payload['semantics']['official_score_failures']}`.",
        "",
        "## Interpretation",
        "",
    ])
    if payload["status"] == "RPD_COMPRESSED_STATE_NECESSITY_GO":
        lines.append("Bounded persistent message/candidate state is necessary under the frozen communication bottleneck. Lightweight recurrent-state learning is authorized.")
    elif payload["status"] == "RPD_COMPRESSED_MESSAGE_RECURRENCE_ONLY":
        lines.append("Compressed recurrent communication works, but the frozen controls do not isolate bounded message-cache memory as necessary. Keep the claim at message recurrence or redesign the partial-observation task before learning.")
    elif payload["status"] == "RPD_COMPRESSED_STATE_NO_GO":
        lines.append("The compressed persistent policy does not retain competence. Do not escalate to learned recurrent state.")
    else:
        lines.append("Compressed-message semantics failed; no scientific interpretation is allowed.")
    lines.extend([
        "",
        "## Honesty boundary",
        "",
        "The state is symbolic candidate/cache state, not a learned latent vector. The source pool is exposed development data. No fixed-actual-compute, wall-clock, GPU, Qwen, or independent-confirmation claim is made.",
        "",
        "## Artifacts",
        "",
        "- [Results JSON](results.json)",
        "- [Frozen compressed-state contract](../../specs/recurrent_parallel_compressed_state_v1.md)",
        "- [Fixed-budget closeout](../recurrent_parallel_fixed_budget/CLOSEOUT.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RPD compressed-message persistence gate.")
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_compressed_state_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_compressed_state"))
    args = parser.parse_args()
    contract_path = _resolve(args.contract)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("status") != "FROZEN_BEFORE_COMPRESSED_OUTCOMES":
        raise ValueError("compressed-state contract is not frozen")
    for path_text in contract["prerequisites"]:
        payload = json.loads(_resolve(path_text).read_text(encoding="utf-8"))
        if payload.get("status") not in {"RPD_MESSAGE_RECURRENCE_ONLY", "RPD_FIXED_B_INTERIOR_OPTIMUM_CANDIDATE"}:
            raise ValueError(f"compressed-state prerequisite failed: {path_text}")
    manifest_path = _resolve(contract["source_manifest"])
    instances = list(json.loads(manifest_path.read_text(encoding="utf-8"))["rows"])
    modes = list(map(str, contract["modes"]))
    budgets = list(map(int, contract["round_budgets"]))
    if tuple(modes) != COMPRESSED_MODES:
        raise ValueError("compressed modes differ from frozen implementation")

    rows = []
    for index, instance in enumerate(instances):
        for mode in modes:
            for budget in budgets:
                rows.append(
                    run_compressed_recurrence(
                        instance,
                        mode=mode,
                        round_cap=budget,
                        cache_capacity=int(contract["message_cache_capacity_facts"]),
                    )
                )
        if (index + 1) % 4 == 0:
            print(json.dumps({"event": "compressed_state_progress", "instances_completed": index + 1}), flush=True)

    replay_targets = [row for row in rows if row["mode"] == "compressed_persistent" and int(row["round_cap"]) == 32][:8]
    instance_index = {str(row["instance_id"]): row for row in instances}
    replay_mismatches = 0
    for expected in replay_targets:
        replay = run_compressed_recurrence(instance_index[expected["instance_id"]], mode="compressed_persistent", round_cap=32, cache_capacity=2)
        replay_mismatches += int(replay != expected)
    compressed_modes = {"compressed_persistent", "compressed_cache_reset", "compressed_all_reset", "compressed_shuffled"}
    compressed_rows = [row for row in rows if row["mode"] in compressed_modes]
    semantics = {
        "replay_rows": len(replay_targets),
        "replay_mismatches": replay_mismatches,
        "same_round_reads": sum(int(row["same_round_cross_agent_reads"]) for row in rows),
        "invalid_message_age_rows": sum(int(row["message_facts_delivered"] > 0 and int(row["maximum_message_age"]) != 1) for row in rows),
        "fragment_size_violations": sum(int(row["fragment_size_violations"]) for row in compressed_rows),
        "cache_bound_violations": sum(int(row["max_cache_facts"] > int(contract["message_cache_capacity_facts"])) for row in compressed_rows),
        "hidden_full_message_reads": sum(int(row["hidden_full_message_reads"]) for row in compressed_rows),
        "invalid_local_candidates": sum(int(not row["local_candidates_valid"]) for row in rows),
        "official_score_failures": sum(int(row["solved"] and not row["official_verification"]) for row in rows),
        "planted_usage_rows": sum(int(row["planted_assignment_used"]) for row in rows),
    }
    s0 = semantics["replay_rows"] >= 8 and all(value == 0 for key, value in semantics.items() if key != "replay_rows")
    summary = _summary(rows)
    controls = {}
    for mode in modes:
        subset = _pooled(rows, mode, 32)
        controls[mode] = {
            "solve_rate": _solve(subset),
            "mean_rounds": mean(float(row["rounds_executed"]) for row in subset),
            "mean_final_conflicts": mean(float(row["final_cross_conflicts"]) for row in subset),
            "compression_ratio": mean(float(row["compression_ratio"]) for row in subset),
            "max_cache_facts": max(int(row["max_cache_facts"]) for row in subset),
        }
    s1 = (
        controls["compressed_persistent"]["solve_rate"] >= 0.90
        and controls["compressed_persistent"]["solve_rate"] >= controls["full_message"]["solve_rate"] - 0.10
        and controls["compressed_persistent"]["compression_ratio"] <= 0.60
    )
    diameter_directions = 0
    for diameter in (4, 8, 16):
        persistent = _lookup(summary, diameter, "compressed_persistent", 32)
        reset = _lookup(summary, diameter, "compressed_cache_reset", 32)
        diameter_directions += int(persistent["solve_rate"] > reset["solve_rate"])
    s2 = (
        controls["compressed_persistent"]["solve_rate"] - controls["compressed_cache_reset"]["solve_rate"] >= 0.15
        and controls["compressed_persistent"]["mean_final_conflicts"] < controls["compressed_cache_reset"]["mean_final_conflicts"]
        and diameter_directions >= 2
    )
    s3 = controls["compressed_persistent"]["solve_rate"] - controls["compressed_all_reset"]["solve_rate"] >= 0.15
    s4 = (
        controls["compressed_persistent"]["solve_rate"] - controls["compressed_shuffled"]["solve_rate"] >= 0.15
        and controls["compressed_persistent"]["solve_rate"] - controls["no_message"]["solve_rate"] >= 0.15
    )
    persistent_by_budget = {budget: _solve(_pooled(rows, "compressed_persistent", budget)) for budget in budgets}
    monotonic = all(persistent_by_budget[left] <= persistent_by_budget[right] + 1e-12 for left, right in zip(budgets, budgets[1:]))
    round_depth = {str(diameter): _t90(summary, diameter, "compressed_persistent", budgets) for diameter in (2, 4, 8, 16)}
    low_depths = [round_depth[str(diameter)] for diameter in (2, 4) if round_depth[str(diameter)] is not None]
    high_depths = [round_depth[str(diameter)] for diameter in (8, 16) if round_depth[str(diameter)] is not None]
    depth_direction = bool(low_depths and high_depths and max(high_depths) >= min(low_depths))
    s5 = monotonic and depth_direction
    gates = {
        "S0_semantics_memory_bound": s0,
        "S1_compressed_persistent_competence": s1,
        "S2_message_cache_necessity": s2,
        "S3_full_state_necessity": s3,
        "S4_correct_message_necessity": s4,
        "S5_recurrence_depth": s5,
    }
    if not s0:
        status = "RPD_COMPRESSED_STATE_SEMANTICS_FAIL"
    elif all(gates.values()):
        status = "RPD_COMPRESSED_STATE_NECESSITY_GO"
    elif s0 and s1 and s4 and s5:
        status = "RPD_COMPRESSED_MESSAGE_RECURRENCE_ONLY"
    else:
        status = "RPD_COMPRESSED_STATE_NO_GO"

    persistent_matrix = {
        str(diameter): {
            str(budget): float(_lookup(summary, diameter, "compressed_persistent", budget)["solve_rate"])
            for budget in budgets
        }
        for diameter in (2, 4, 8, 16)
    }
    payload = {
        "schema": "recurrent_parallel_compressed_state_results_v1",
        "status": status,
        "headline_eligible": False,
        "qwen_authorized": False,
        "learned_state_authorized": status == "RPD_COMPRESSED_STATE_NECESSITY_GO",
        "contract_sha256": _sha256(contract_path),
        "manifest_sha256": _sha256(manifest_path),
        "implementation_sha256": _sha256(REPO_ROOT / "experiments/recurrent_parallel_core.py"),
        "analysis_sha256": _sha256(Path(__file__)),
        "gates": gates,
        "semantics": semantics,
        "pooled_controls_T32": controls,
        "persistent_matrix": persistent_matrix,
        "round_depth": round_depth,
        "summary": summary,
        "rows": rows,
        "honesty": {
            "development_only": True,
            "symbolic_state_not_learned": True,
            "no_gpu_or_llm": True,
            "no_independent_confirmation": True,
        },
    }
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "SUMMARY.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": status,
        "learned_state_authorized": payload["learned_state_authorized"],
        "rows": len(rows),
        "report": str((output_dir / "SUMMARY.md").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
