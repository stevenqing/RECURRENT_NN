"""P1a Qwen recovery baseline sweep for the Rung-1 separator PO experiment."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
from statistics import mean, median
from typing import Any

from tqdm.auto import tqdm

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _adjacency, _rel
from experiments.rung1_separator_llm_po_forward_gate import (
    DEFAULT_MAX_NEW_TOKENS,
    MODEL_ID,
    P1A_PROMPT_CONTRACT,
    QWEN35_DOWNLOAD_PATH,
    SEPARATOR_RESULTS_PATH,
    _generate_batch,
    _load_model,
    _parse_generation,
)


RESULTS_ROOT = REPO_ROOT / "results/rung1_separator_llm_po"
RESULTS_PATH = RESULTS_ROOT / "p1a_recovery_baseline.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_061_rung1_separator_p1a_recovery_baseline.json"
SCHEMA_VERSION = "rung1_separator_llm_po_p1a_recovery_baseline_v1"
ITEM_NUMBER = "061"
STATUS_PASS = "RUNG1_SEPARATOR_LLM_PO_P1A_RECOVERY_BASELINE_PASS"
STATUS_FAIL = "RUNG1_SEPARATOR_LLM_PO_P1A_RECOVERY_BASELINE_FAIL"
STATUS_SHARD = "SHARD_COMPLETE"
ARMS = ("cbj_bounded_team_qwen_p1a", "chronological_rollback_team_qwen_p1a", "forward_markov_team_qwen_p1a")
RECOVERY_MODE = {
    "cbj_bounded_team_qwen_p1a": "cbj_bounded",
    "chronological_rollback_team_qwen_p1a": "chronological_rollback",
    "forward_markov_team_qwen_p1a": "forward_markov",
}
REQUESTED_TO_CANONICAL_CELLS = {
    "corner_local_heavy": "corner_local_heavy",
    "dg_m2_dl5_b2": "dg_m2_dl5",
    "dg_m4_dl5_b2": "dg_m4_dl5",
    "dg_m6_dl5_b2": "dg_m6_dl5",
    "b_b12_mid_dglobal": "b_b12_db2",
}
COMM_BUDGET_SWEEP = [64, 128, 192, 256, 384, 512, 768, 1024]
DEFAULT_N_PER_CELL = 24
DEFAULT_N_SEEDS = 2
DEFAULT_CALL_CAP = 200
DEFAULT_BATCH_SIZE_PER_GPU = 2
TRUNCATION_RATE_THRESHOLD = 0.10
RHO_TOLERANCE = 0.05
SYMBOLIC_CHRONO_DGLOBAL_BETA = 41.4


@dataclass
class Episode:
    row: dict[str, Any]
    arm: str
    adjacency: dict[int, set[int]]
    order: list[int]
    assignment: dict[int, int] = field(default_factory=dict)
    cursor: int = 0
    calls: int = 0
    status: str = "RUNNING"
    solved: bool = False
    trace: list[dict[str, Any]] = field(default_factory=list)
    register: list[dict[str, int]] = field(default_factory=list)
    tried_colors: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    generation_counts: Counter[str] = field(default_factory=Counter)
    operator_error_counts: Counter[str] = field(default_factory=Counter)
    distinct_attempts_by_vertex: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    live_domain_sizes: list[int] = field(default_factory=list)
    total_retractions: int = 0
    commit_messages: int = 0
    nogood_messages: int = 0
    comm_tokens: int = 0
    peak_register_entries: int = 0
    peak_shared_channel: int = 0
    first_conflict_depth: int | None = None
    backjump_distances: list[int] = field(default_factory=list)
    call_cap_hit: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _instance_position(episode: Episode) -> dict[int, int]:
    return {vertex: index for index, vertex in enumerate(episode.order)}


def _feasible_colors(episode: Episode, vertex: int) -> list[int]:
    tried = episode.tried_colors[vertex]
    feasible = []
    for color in range(1, int(episode.row["k"]) + 1):
        if color in tried:
            continue
        if all(episode.assignment.get(neighbor) != color for neighbor in episode.adjacency[vertex]):
            feasible.append(color)
    return feasible


def _prompt(episode: Episode) -> str:
    row = episode.row
    vertex = episode.order[episode.cursor]
    block = int(row["partitions"][vertex])
    feasible_colors = _feasible_colors(episode, vertex)
    own_vertices = [idx for idx, part in enumerate(row["partitions"]) if int(part) == block]
    own_set = set(own_vertices)
    boundary_edges = [edge for edge in row["edges"] if (int(edge[0]) in own_set) ^ (int(edge[1]) in own_set)]
    visible_assignment = {}
    for assigned_vertex, color in episode.assignment.items():
        if assigned_vertex in own_set or any(assigned_vertex in {int(edge[0]), int(edge[1])} and vertex in {int(edge[0]), int(edge[1])} for edge in boundary_edges):
            visible_assignment[assigned_vertex] = color
    return "\n".join([
        "P1a branch-only value-ordering operator.",
        "Symbolic guards already computed the live domain. Choose exactly one listed color.",
        "Do not reason, explain, restate the task, use markdown, or add extra keys.",
        "Return exactly one compact JSON object: {\"color\": <one value from feasible_colors>}.",
        f"current_vertex={vertex}; agent_block={block}; k={row['k']}",
        f"feasible_colors={feasible_colors}",
        f"own_block_vertices={own_vertices}",
        f"incident_boundary_edges={boundary_edges}",
        f"visible_assignment={dict(sorted(visible_assignment.items()))}",
    ])


def _blockers_by_color(episode: Episode, vertex: int) -> dict[int, list[int]]:
    blockers: dict[int, list[int]] = {}
    for color in range(1, int(episode.row["k"]) + 1):
        color_blockers = [neighbor for neighbor in episode.adjacency[vertex] if neighbor in episode.assignment and episode.assignment[neighbor] == color]
        if color_blockers or color in episode.tried_colors[vertex]:
            blockers[color] = color_blockers
    return blockers


def _shared_channel_load(episode: Episode, vertex: int, nogood: set[int] | None = None) -> int:
    block = int(episode.row["partitions"][vertex])
    visible_boundary_commitments = sum(1 for neighbor in episode.adjacency[vertex] if neighbor in episode.assignment and int(episode.row["partitions"][neighbor]) != block)
    return max(visible_boundary_commitments, len(nogood or set()))


def _nogood(episode: Episode, vertex: int, blockers_by_color: dict[int, list[int]]) -> set[int]:
    position = _instance_position(episode)
    boundary_blockers = []
    vertex_block = int(episode.row["partitions"][vertex])
    for blockers in blockers_by_color.values():
        candidates = [item for item in blockers if int(episode.row["partitions"][item]) != vertex_block]
        if candidates:
            boundary_blockers.append(min(candidates, key=lambda item: position[item]))
        elif blockers:
            boundary_blockers.append(min(blockers, key=lambda item: position[item]))
    return set(boundary_blockers)


def _fallback_color(episode: Episode, vertex: int, feasible: list[int], parsed_color: int | None) -> tuple[int, str | None]:
    if parsed_color in feasible:
        return int(parsed_color), None
    if parsed_color is not None:
        episode.operator_error_counts["value_misselection"] += 1
        episode.distinct_attempts_by_vertex[vertex].add(int(parsed_color))
        return int(feasible[0]), "value_misselection"
    episode.operator_error_counts["format_failure"] += 1
    return int(feasible[0]), "format_failure"


def _assign(episode: Episode, generation: dict[str, Any]) -> None:
    vertex = episode.order[episode.cursor]
    feasible = _feasible_colors(episode, vertex)
    parsed = _parse_generation(generation, int(episode.row["k"]))
    episode.calls += 1
    episode.generation_counts[parsed["generation_state"]] += 1
    episode.live_domain_sizes.append(len(feasible))
    chosen, repair = _fallback_color(episode, vertex, feasible, parsed["color"])
    if parsed["generation_state"] in {"format_failure", "truncated_no_answer", "parsable_invalid"} and repair is None:
        episode.operator_error_counts["format_failure"] += 1
    episode.tried_colors[vertex].add(chosen)
    episode.distinct_attempts_by_vertex[vertex].add(chosen)
    episode.assignment[vertex] = chosen
    episode.register.append({"vertex": vertex, "color": chosen, "order_index": episode.cursor, "agent": int(episode.row["partitions"][vertex])})
    episode.peak_register_entries = max(episode.peak_register_entries, len(episode.register))
    episode.peak_shared_channel = max(episode.peak_shared_channel, _shared_channel_load(episode, vertex))
    episode.commit_messages += 1
    episode.comm_tokens += 4
    episode.trace.append({
        "vertex": vertex,
        "chosen_color": chosen,
        "llm_color": parsed["color"],
        "feasible_colors": feasible,
        "generation_state": parsed["generation_state"],
        "finish_reason": generation["finish_reason"],
        "output_tokens": generation["output_tokens"],
        "operator_repair": repair,
        "arm": episode.arm,
    })
    episode.cursor += 1
    if episode.cursor >= len(episode.order):
        episode.status = "SOLVED"
        episode.solved = True


def _recover_or_stop(episode: Episode) -> None:
    vertex = episode.order[episode.cursor]
    blockers = _blockers_by_color(episode, vertex)
    nogood = _nogood(episode, vertex, blockers)
    position = _instance_position(episode)
    if episode.first_conflict_depth is None:
        earliest = min((position[item] for item in nogood), default=episode.cursor)
        episode.first_conflict_depth = episode.cursor - earliest
    episode.nogood_messages += 1
    episode.comm_tokens += 2 + 2 * len(nogood)
    episode.peak_shared_channel = max(episode.peak_shared_channel, _shared_channel_load(episode, vertex, nogood))
    mode = RECOVERY_MODE[episode.arm]
    if mode == "forward_markov":
        episode.status = "FORWARD_DEAD_END"
        return
    if not episode.register:
        episode.status = "NO_RECOVERY_TARGET"
        return
    if mode == "chronological_rollback" or not nogood:
        target_index = len(episode.register) - 1
    else:
        target_vertex = max(nogood, key=lambda item: position[item])
        target_index = max(index for index, entry in enumerate(episode.register) if entry["vertex"] == target_vertex)
    popped = episode.register[target_index:]
    distance = len(popped)
    episode.backjump_distances.append(distance)
    episode.total_retractions += distance
    episode.comm_tokens += 2 * distance
    for entry in popped:
        episode.assignment.pop(int(entry["vertex"]), None)
    for entry in popped[1:]:
        episode.tried_colors.pop(int(entry["vertex"]), None)
    episode.tried_colors.pop(vertex, None)
    episode.cursor = int(episode.register[target_index]["order_index"])
    episode.register = episode.register[:target_index]


def _step_episode(episode: Episode, generation: dict[str, Any] | None = None) -> None:
    if episode.status != "RUNNING":
        return
    if episode.calls >= DEFAULT_CALL_CAP:
        episode.status = "CALL_CAP"
        episode.call_cap_hit = True
        return
    vertex = episode.order[episode.cursor]
    feasible = _feasible_colors(episode, vertex)
    if not feasible:
        _recover_or_stop(episode)
        return
    if generation is None:
        raise RuntimeError("generation required for non-empty live domain")
    _assign(episode, generation)


def _active_needing_generation(episodes: list[Episode]) -> list[Episode]:
    active = []
    for episode in episodes:
        while episode.status == "RUNNING" and not _feasible_colors(episode, episode.order[episode.cursor]):
            _step_episode(episode)
        if episode.status == "RUNNING":
            active.append(episode)
    return active


def _select_manifest(n_per_cell: int, n_seeds: int) -> list[dict[str, Any]]:
    data = _read_json(SEPARATOR_RESULTS_PATH)
    acceptance = data.get("acceptance", {})
    if data.get("schema_version") != "rung1_separator_scaling_symbolic_v0_2_3" or not acceptance.get("overall_pass") or not acceptance.get("fairness_corner_clean"):
        raise RuntimeError("symbolic separator v0.2.3 fairness gate is not passed")
    by_cell: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data["instance_manifest"]:
        by_cell[str(row["cell_id"])].append(row)
    selected: list[dict[str, Any]] = []
    per_seed = max(1, n_per_cell // max(n_seeds, 1))
    for requested, canonical in REQUESTED_TO_CANONICAL_CELLS.items():
        rows = sorted(by_cell[canonical], key=lambda row: (int(row["seed"]), int(row["source_index"]), str(row["instance_id"])))
        seeds = sorted({int(row["seed"]) for row in rows})[:n_seeds]
        cell_rows: list[dict[str, Any]] = []
        for seed in seeds:
            cell_rows.extend([dict(row, requested_cell_id=requested, canonical_cell_id=canonical) for row in rows if int(row["seed"]) == seed][:per_seed])
        if len(cell_rows) < n_per_cell:
            seen = {row["instance_id"] for row in cell_rows}
            cell_rows.extend([dict(row, requested_cell_id=requested, canonical_cell_id=canonical) for row in rows if row["instance_id"] not in seen][: n_per_cell - len(cell_rows)])
        selected.extend(cell_rows[:n_per_cell])
    return selected


def _episode_row(episode: Episode, model_source: str, shard_index: int, num_shards: int, n_per_cell: int, n_seeds: int, batch_size: int, max_new_tokens: int) -> dict[str, Any]:
    generation_total = sum(episode.generation_counts.values()) or 1
    decision_count = max(1, len(episode.live_domain_sizes))
    clean = mean(episode.live_domain_sizes) if episode.live_domain_sizes else float(episode.row.get("mean_live_domain_at_decision") or 1.0)
    attempts = sum(len(values) for values in episode.distinct_attempts_by_vertex.values())
    extra_attempts_per_decision = max(0.0, (attempts - decision_count) / decision_count)
    inflated = clean + extra_attempts_per_decision
    finish_counts = Counter(item["finish_reason"] for item in episode.trace)
    return {
        "instance_id": episode.row["instance_id"],
        "requested_cell_id": episode.row["requested_cell_id"],
        "cell_id": episode.row["canonical_cell_id"],
        "sweep": episode.row["sweep"],
        "d_global_reference": episode.row["d_global_reference"],
        "b": episode.row["b"],
        "d_boundary": episode.row["d_boundary"],
        "d_local": episode.row["d_local"],
        "m_blocks": episode.row["m_blocks"],
        "local_contribution": episode.row["local_contribution"],
        "seed": episode.row["seed"],
        "rung": "P1a_recovery_baseline",
        "arm": episode.arm,
        "solved": episode.solved,
        "status": episode.status,
        "llm_calls": episode.calls,
        "call_cap": DEFAULT_CALL_CAP,
        "call_cap_hit": episode.call_cap_hit,
        "steps_to_solve_or_cap": len(episode.trace),
        "comm_tokens": episode.comm_tokens if episode.solved else None,
        "comm_tokens_observed": episode.comm_tokens,
        "total_retractions": episode.total_retractions,
        "peak_register_entries": episode.peak_register_entries,
        "peak_shared_channel": episode.peak_shared_channel,
        "commit_messages": episode.commit_messages,
        "nogood_messages": episode.nogood_messages,
        "first_conflict_depth": episode.first_conflict_depth or 0,
        "mean_backjump_distance": mean(episode.backjump_distances) if episode.backjump_distances else 0.0,
        "finish_reason": finish_counts.most_common(1)[0][0] if finish_counts else None,
        "finish_reason_length_count": finish_counts["length"],
        "output_tokens": sum(int(item["output_tokens"]) for item in episode.trace),
        "thinking_tokens": 0,
        "generation_truncated_no_answer": episode.generation_counts["truncated_no_answer"],
        "generation_parsable_invalid": episode.generation_counts["parsable_invalid"],
        "generation_valid": episode.generation_counts["valid"],
        "generation_format_failure": episode.generation_counts["format_failure"],
        "false_pos_deadend": 0,
        "false_neg_missed_conflict": 0,
        "value_misselection": episode.operator_error_counts["value_misselection"],
        "format_failure": episode.operator_error_counts["format_failure"],
        "frac_valid_generation": episode.generation_counts["valid"] / generation_total,
        "k_eff_clean": clean,
        "k_eff_inflated": inflated,
        "rho": inflated / max(clean, 1e-9),
        "oracle_read_only_parallel": True,
        "oracle_visible_to_llm_loop": False,
        "frozen_symbolic_components": ["register", "recovery_routing", "boundary_message_protocol", "symbolic_guard_for_P1a"],
        "po_visibility": "own block, incident boundary edges, and messaged boundary-neighbor colors only",
        "model_id": MODEL_ID,
        "model_source": model_source,
        "temperature": 0,
        "max_new_tokens": max_new_tokens,
        "n_per_cell": n_per_cell,
        "n_seeds": n_seeds,
        "batch_size_per_gpu": batch_size,
        "prompt_contract": P1A_PROMPT_CONTRACT,
        "thinking_disabled": True,
        "shard_index": shard_index,
        "num_shards": num_shards,
        "source": SOURCE,
        "provenance": "qwen35_p1a_recovery_baseline_instance_v0",
    }


def run_shard(shard_index: int, num_shards: int, output_dir: Path, n_per_cell: int, n_seeds: int, batch_size: int, max_new_tokens: int, device: str, dtype: str) -> dict[str, Any]:
    manifest = _select_manifest(n_per_cell, n_seeds)
    expanded = [(row, arm) for row in manifest for arm in ARMS]
    shard_items = [item for index, item in enumerate(expanded) if index % num_shards == shard_index]
    model, tokenizer, model_source = _load_model(device, dtype)
    episodes = [Episode(row=row, arm=arm, adjacency=_adjacency(int(row["n_vertices"]), tuple(tuple(edge) for edge in row["edges"])), order=[int(v) for v in row["order"]]) for row, arm in shard_items]
    active = _active_needing_generation(episodes)
    with tqdm(total=len(episodes), desc=f"p1a recovery shard {shard_index}", unit="arm", dynamic_ncols=True) as progress:
        completed = 0
        while active:
            batch = active[:batch_size]
            generations = _generate_batch(model, tokenizer, [_prompt(episode) for episode in batch], max_new_tokens)
            for episode, generation in zip(batch, generations):
                before = episode.status
                _step_episode(episode, generation)
                if episode.status != "RUNNING" and before == "RUNNING":
                    completed += 1
                    progress.update(1)
            active = _active_needing_generation(episodes)
            for episode in episodes:
                if episode.status == "RUNNING" and episode.calls >= DEFAULT_CALL_CAP:
                    episode.status = "CALL_CAP"
                    episode.call_cap_hit = True
                    completed += 1
                    progress.update(1)
            active = [episode for episode in active if episode.status == "RUNNING"]
    rows = [_episode_row(episode, model_source, shard_index, num_shards, n_per_cell, n_seeds, batch_size, max_new_tokens) for episode in episodes]
    payload = {"schema_version": SCHEMA_VERSION, "generated_at": _now(), "status": STATUS_SHARD, "shard_index": shard_index, "num_shards": num_shards, "instance_arm_metrics": rows, "source": SOURCE}
    _write_json(output_dir / f"shard_{shard_index:02d}.json", payload)
    return payload


def _groups(rows: list[dict[str, Any]], *keys: str) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    out: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        out[tuple(row[key] for key in keys)].append(row)
    return out


def _arm_cell_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (arm, requested_cell), subset in sorted(_groups(rows, "arm", "requested_cell_id").items()):
        solved = [row for row in subset if row["solved"]]
        out.append({
            "arm": arm,
            "requested_cell_id": requested_cell,
            "cell_id": subset[0]["cell_id"],
            "d_global_reference": subset[0]["d_global_reference"],
            "b": subset[0]["b"],
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_comm_tokens_to_solve": mean(float(row["comm_tokens"]) for row in solved) if solved else None,
            "median_comm_tokens_to_solve": median([float(row["comm_tokens"]) for row in solved]) if solved else None,
            "mean_llm_calls": mean(float(row["llm_calls"]) for row in subset),
            "call_cap_rate": mean(float(row["call_cap_hit"]) for row in subset),
            "truncation_rate": mean(float(row["finish_reason_length_count"] > 0 or row["generation_truncated_no_answer"] > 0) for row in subset),
            "source": SOURCE,
            "provenance": "qwen35_p1a_recovery_arm_cell_summary_v0",
        })
    return out


def _budget_at_95(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (arm, requested_cell), subset in sorted(_groups(rows, "arm", "requested_cell_id").items()):
        budget_rates = {}
        for budget in COMM_BUDGET_SWEEP:
            budget_rates[str(budget)] = mean(float(row["solved"] and row.get("comm_tokens") is not None and float(row["comm_tokens"]) <= budget) for row in subset)
        solved_comm = sorted(float(row["comm_tokens"]) for row in subset if row["solved"] and row.get("comm_tokens") is not None)
        threshold = next((budget for budget in COMM_BUDGET_SWEEP if budget_rates[str(budget)] >= 0.95), None)
        p95_comm = solved_comm[min(len(solved_comm) - 1, math.ceil(0.95 * len(solved_comm)) - 1)] if solved_comm else None
        out.append({
            "arm": arm,
            "requested_cell_id": requested_cell,
            "cell_id": subset[0]["cell_id"],
            "budget_at_95_solve": threshold,
            "max_budget": max(COMM_BUDGET_SWEEP),
            "max_budget_solve_rate": budget_rates[str(max(COMM_BUDGET_SWEEP))],
            "posterior_p95_comm_to_solve": p95_comm,
            "budget_solve_rates": budget_rates,
            "n": len(subset),
            "source": SOURCE,
            "provenance": "qwen35_p1a_recovery_budget95_offline_v0",
        })
    return out


def _operator_error_breakdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (arm, requested_cell), subset in sorted(_groups(rows, "arm", "requested_cell_id").items()):
        out.append({
            "arm": arm,
            "requested_cell_id": requested_cell,
            "cell_id": subset[0]["cell_id"],
            "n": len(subset),
            "false_pos_deadend_rate": mean(float(row["false_pos_deadend"] > 0) for row in subset),
            "false_neg_missed_conflict_rate": mean(float(row["false_neg_missed_conflict"] > 0) for row in subset),
            "value_misselection_rate": mean(float(row["value_misselection"] > 0) for row in subset),
            "format_failure_rate": mean(float(row["format_failure"] > 0) for row in subset),
            "frac_truncated_no_answer": mean(float(row["generation_truncated_no_answer"] > 0) for row in subset),
            "frac_finish_reason_length": mean(float(row["finish_reason_length_count"] > 0) for row in subset),
            "frac_parsable_invalid": mean(float(row["generation_parsable_invalid"] > 0) for row in subset),
            "frac_valid": mean(float(row["generation_valid"] > 0) for row in subset),
            "source": SOURCE,
            "provenance": "qwen35_p1a_recovery_operator_error_breakdown_v0",
        })
    return out


def _keff_inflation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (arm, requested_cell), subset in sorted(_groups(rows, "arm", "requested_cell_id").items()):
        out.append({
            "arm": arm,
            "requested_cell_id": requested_cell,
            "cell_id": subset[0]["cell_id"],
            "k_eff_clean": mean(float(row["k_eff_clean"]) for row in subset),
            "k_eff_inflated": mean(float(row["k_eff_inflated"]) for row in subset),
            "rho": mean(float(row["rho"]) for row in subset),
            "n": len(subset),
            "source": SOURCE,
            "provenance": "qwen35_p1a_recovery_keff_inflation_v0",
        })
    return out


def _invert(matrix: list[list[float]]) -> list[list[float]]:
    n = len(matrix)
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        denom = aug[col][col]
        if abs(denom) < 1e-12:
            raise ValueError("singular matrix")
        aug[col] = [value / denom for value in aug[col]]
        for row in range(n):
            if row != col:
                factor = aug[row][col]
                aug[row] = [value - factor * base for value, base in zip(aug[row], aug[col])]
    return [row[n:] for row in aug]


def _ols_beta_ci(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fit_rows = [row for row in rows if row["arm"] in {"cbj_bounded_team_qwen_p1a", "chronological_rollback_team_qwen_p1a"} and row["solved"] and row.get("comm_tokens") is not None]
    if len(fit_rows) < 8:
        return {"fit_ok": False, "reason": "too_few_solved_rows", "n": len(fit_rows)}
    x = []
    y = []
    for row in fit_rows:
        dplusb = float(row["d_global_reference"] + row["b"])
        chrono = 1.0 if row["arm"] == "chronological_rollback_team_qwen_p1a" else 0.0
        x.append([1.0, dplusb, chrono, chrono * dplusb])
        y.append(float(row["comm_tokens"]))
    xtx = [[sum(a[i] * a[j] for a in x) for j in range(4)] for i in range(4)]
    inv = _invert(xtx)
    xty = [sum(a[i] * b for a, b in zip(x, y)) for i in range(4)]
    beta = [sum(inv[i][j] * xty[j] for j in range(4)) for i in range(4)]
    residuals = [obs - sum(coef * value for coef, value in zip(beta, row)) for obs, row in zip(y, x)]
    dof = max(1, len(y) - 4)
    sigma2 = sum(value * value for value in residuals) / dof
    se = [math.sqrt(max(0.0, sigma2 * inv[i][i])) for i in range(4)]
    chrono_beta = beta[3]
    chrono_se = se[3]
    return {
        "fit_ok": True,
        "n": len(fit_rows),
        "formula": "comm_tokens ~ 1 + (d_global+b) + chronological + chronological:(d_global+b)",
        "arm_chrono_x_d_global_beta": chrono_beta,
        "arm_chrono_x_d_global_ci95_low": chrono_beta - 1.96 * chrono_se,
        "arm_chrono_x_d_global_ci95_high": chrono_beta + 1.96 * chrono_se,
        "symbolic_reference_beta": SYMBOLIC_CHRONO_DGLOBAL_BETA,
        "beta_minus_symbolic_reference": chrono_beta - SYMBOLIC_CHRONO_DGLOBAL_BETA,
        "decoupling_survives_component": chrono_beta > 0 and chrono_beta + 1.96 * chrono_se > 0,
        "source": SOURCE,
        "provenance": "qwen35_p1a_recovery_decoupling_ols_v0",
    }


def _ols_fit(x: list[list[float]], y: list[float], names: list[str]) -> dict[str, Any]:
    n_params = len(names)
    xtx = [[sum(row[i] * row[j] for row in x) for j in range(n_params)] for i in range(n_params)]
    inv = _invert(xtx)
    xty = [sum(row[i] * value for row, value in zip(x, y)) for i in range(n_params)]
    beta = [sum(inv[i][j] * xty[j] for j in range(n_params)) for i in range(n_params)]
    residuals = [value - sum(coef * feature for coef, feature in zip(beta, row)) for value, row in zip(y, x)]
    dof = max(1, len(y) - n_params)
    sigma2 = sum(value * value for value in residuals) / dof
    covariance = [[sigma2 * inv[i][j] for j in range(n_params)] for i in range(n_params)]
    coefficients = {}
    for index, name in enumerate(names):
        se = math.sqrt(max(0.0, covariance[index][index]))
        coefficients[name] = {
            "beta": beta[index],
            "se": se,
            "ci95_low": beta[index] - 1.96 * se,
            "ci95_high": beta[index] + 1.96 * se,
        }
    return {"n": len(y), "dof": dof, "names": names, "beta": beta, "covariance": covariance, "coefficients": coefficients}


def _combine_terms(fit: dict[str, Any], weights: dict[str, float]) -> dict[str, float]:
    names = fit["names"]
    vector = [float(weights.get(name, 0.0)) for name in names]
    beta = sum(weight * value for weight, value in zip(vector, fit["beta"]))
    variance = 0.0
    for i, left in enumerate(vector):
        for j, right in enumerate(vector):
            variance += left * right * fit["covariance"][i][j]
    se = math.sqrt(max(0.0, variance))
    return {"beta": beta, "se": se, "ci95_low": beta - 1.96 * se, "ci95_high": beta + 1.96 * se}


def _arm_feature_fit(rows: list[dict[str, Any]], target: str) -> dict[str, Any]:
    fit_rows = [row for row in rows if row["arm"] in {"cbj_bounded_team_qwen_p1a", "chronological_rollback_team_qwen_p1a"}]
    names = ["intercept", "d_global", "b", "chronological", "chronological_x_d_global", "chronological_x_b"]
    x = []
    y = []
    for row in fit_rows:
        d_global = float(row["d_global_reference"])
        b_value = float(row["b"])
        chronological = 1.0 if row["arm"] == "chronological_rollback_team_qwen_p1a" else 0.0
        x.append([1.0, d_global, b_value, chronological, chronological * d_global, chronological * b_value])
        y.append(float(row[target]))
    fit = _ols_fit(x, y, names)
    fit["formula"] = f"{target} ~ 1 + d_global + b + chronological + chronological:d_global + chronological:b"
    fit["target"] = target
    fit["cbj_d_global"] = fit["coefficients"]["d_global"]
    fit["chronological_incremental_d_global"] = fit["coefficients"]["chronological_x_d_global"]
    fit["chronological_d_global"] = _combine_terms(fit, {"d_global": 1.0, "chronological_x_d_global": 1.0})
    return fit


def _fit_summary_row(fit: dict[str, Any], target_label: str, pass_rule: str, passed: bool, provenance: str) -> dict[str, Any]:
    cbj = fit["cbj_d_global"]
    chrono = fit["chronological_d_global"]
    interaction = fit["chronological_incremental_d_global"]
    return {
        "target": target_label,
        "formula": fit["formula"],
        "n": fit["n"],
        "cbj_d_global_beta": cbj["beta"],
        "cbj_d_global_ci95_low": cbj["ci95_low"],
        "cbj_d_global_ci95_high": cbj["ci95_high"],
        "chronological_d_global_beta": chrono["beta"],
        "chronological_d_global_ci95_low": chrono["ci95_low"],
        "chronological_d_global_ci95_high": chrono["ci95_high"],
        "chronological_minus_cbj_d_global_beta": interaction["beta"],
        "chronological_minus_cbj_d_global_ci95_low": interaction["ci95_low"],
        "chronological_minus_cbj_d_global_ci95_high": interaction["ci95_high"],
        "pass_rule": pass_rule,
        "pass": passed,
        "source": SOURCE,
        "provenance": provenance,
    }


def _solve_gap_by_cell(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    by_cell = _groups([row for row in rows if row["arm"] in {"cbj_bounded_team_qwen_p1a", "chronological_rollback_team_qwen_p1a"}], "requested_cell_id")
    for (requested_cell,), subset in sorted(by_cell.items()):
        by_arm = _groups(subset, "arm")
        cbj = by_arm[("cbj_bounded_team_qwen_p1a",)]
        chrono = by_arm[("chronological_rollback_team_qwen_p1a",)]
        cbj_solve = mean(float(row["solved"]) for row in cbj)
        chrono_solve = mean(float(row["solved"]) for row in chrono)
        out.append({
            "requested_cell_id": requested_cell,
            "cell_id": subset[0]["cell_id"],
            "d_global_reference": subset[0]["d_global_reference"],
            "b": subset[0]["b"],
            "n_per_arm": len(cbj),
            "cbj_solve_rate": cbj_solve,
            "chronological_solve_rate": chrono_solve,
            "solve_rate_gap_cbj_minus_chronological": cbj_solve - chrono_solve,
            "cbj_call_cap_rate": mean(float(row["call_cap_hit"]) for row in cbj),
            "chronological_call_cap_rate": mean(float(row["call_cap_hit"]) for row in chrono),
            "source": SOURCE,
            "provenance": "qwen35_p1a_recovery_solve_gap_by_cell_v1",
        })
    return out


def _calls_censoring_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (arm, requested_cell), subset in sorted(_groups(rows, "arm", "requested_cell_id").items()):
        calls = sorted(float(row["llm_calls"]) for row in subset)
        out.append({
            "arm": arm,
            "requested_cell_id": requested_cell,
            "cell_id": subset[0]["cell_id"],
            "d_global_reference": subset[0]["d_global_reference"],
            "b": subset[0]["b"],
            "n": len(subset),
            "median_capped_llm_calls": median(calls),
            "mean_capped_llm_calls": mean(calls),
            "right_censored_call_cap_rate": mean(float(row["call_cap_hit"]) for row in subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "call_cap": subset[0]["call_cap"],
            "censoring_policy": "call_cap_hit means calls_to_solve >= call_cap; capped llm_calls are lower bounds, not missing values",
            "source": SOURCE,
            "provenance": "qwen35_p1a_recovery_calls_censoring_summary_v1",
        })
    return out


def _cap_robust_decoupling(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    legacy = _decoupling_survival(rows)
    calls_fit = _arm_feature_fit(rows, "llm_calls")
    cap_fit = _arm_feature_fit(rows, "call_cap_hit")
    solve_fit = _arm_feature_fit(rows, "solved")
    calls_interaction = calls_fit["chronological_incremental_d_global"]
    cap_interaction = cap_fit["chronological_incremental_d_global"]
    solve_interaction = solve_fit["chronological_incremental_d_global"]
    calls_rows = [
        _fit_summary_row(calls_fit, "capped_llm_calls_lower_bound", "chronological-minus-CBJ d_global interaction has positive 95% lower bound even with cap-hit rows retained as lower-bound censored observations", calls_interaction["ci95_low"] > 0.0, "qwen35_p1a_recovery_censored_calls_lower_bound_ols_v1"),
        _fit_summary_row(cap_fit, "call_cap_hit", "chronological-minus-CBJ d_global interaction has positive 95% lower bound for right-censoring probability", cap_interaction["ci95_low"] > 0.0, "qwen35_p1a_recovery_call_cap_hit_lpm_v1"),
    ]
    solve_rows = [_fit_summary_row(solve_fit, "solved", "chronological-minus-CBJ d_global interaction has negative 95% upper bound on the uncensored solve indicator", solve_interaction["ci95_high"] < 0.0, "qwen35_p1a_recovery_solve_rate_lpm_v1")]
    cbj = [row for row in rows if row["arm"] == "cbj_bounded_team_qwen_p1a"]
    chrono = [row for row in rows if row["arm"] == "chronological_rollback_team_qwen_p1a"]
    cbj_call_cap = mean(float(row["call_cap_hit"]) for row in cbj)
    chrono_call_cap = mean(float(row["call_cap_hit"]) for row in chrono)
    cbj_solve = mean(float(row["solved"]) for row in cbj)
    chrono_solve = mean(float(row["solved"]) for row in chrono)
    cap_robust_pass = all(row["pass"] for row in calls_rows + solve_rows) and chrono_call_cap > cbj_call_cap
    decoupling_rows = [{
        "fit_ok": True,
        "decoupling_survives": cap_robust_pass,
        "cap_robust_decoupling_survives": cap_robust_pass,
        "legacy_v0_comm_solved_only_decoupling_survives": bool(legacy and legacy[0].get("decoupling_survives")),
        "legacy_v0_right_censoring_note": "v0 comm_tokens regression used solved rows only, so call-cap rows were right-censored out of the fit and are not used as the v1 landing criterion",
        "cbj_solve_rate": cbj_solve,
        "chronological_solve_rate": chrono_solve,
        "cbj_call_cap_rate": cbj_call_cap,
        "chronological_call_cap_rate": chrono_call_cap,
        "call_cap_rate_gap_chronological_minus_cbj": chrono_call_cap - cbj_call_cap,
        "capped_calls_chronological_minus_cbj_d_global_beta": calls_interaction["beta"],
        "capped_calls_chronological_minus_cbj_d_global_ci95_low": calls_interaction["ci95_low"],
        "capped_calls_chronological_minus_cbj_d_global_ci95_high": calls_interaction["ci95_high"],
        "call_cap_hit_chronological_minus_cbj_d_global_beta": cap_interaction["beta"],
        "call_cap_hit_chronological_minus_cbj_d_global_ci95_low": cap_interaction["ci95_low"],
        "call_cap_hit_chronological_minus_cbj_d_global_ci95_high": cap_interaction["ci95_high"],
        "solved_chronological_minus_cbj_d_global_beta": solve_interaction["beta"],
        "solved_chronological_minus_cbj_d_global_ci95_low": solve_interaction["ci95_low"],
        "solved_chronological_minus_cbj_d_global_ci95_high": solve_interaction["ci95_high"],
        "source": SOURCE,
        "provenance": "qwen35_p1a_recovery_cap_robust_decoupling_v1",
    }]
    return decoupling_rows, calls_rows, solve_rows, legacy


def _decoupling_survival(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fit = _ols_beta_ci(rows)
    cbj = [row for row in rows if row["arm"] == "cbj_bounded_team_qwen_p1a"]
    chrono = [row for row in rows if row["arm"] == "chronological_rollback_team_qwen_p1a"]
    fit.update({
        "comparison_to_symbolic_beta_41_4": f"symbolic_reference={SYMBOLIC_CHRONO_DGLOBAL_BETA}",
        "cbj_solve_rate": mean(float(row["solved"]) for row in cbj) if cbj else None,
        "chronological_solve_rate": mean(float(row["solved"]) for row in chrono) if chrono else None,
        "decoupling_survives": bool(fit.get("decoupling_survives_component")) and (mean(float(row["solved"]) for row in cbj) if cbj else 0.0) >= 0.95,
    })
    return [fit]


def _verdict(decoupling: list[dict[str, Any]], calls_interaction: list[dict[str, Any]], solve_interaction: list[dict[str, Any]], legacy_decoupling: list[dict[str, Any]], keff_rows: list[dict[str, Any]], op_rows: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    max_rho_delta = max((abs(float(row["rho"]) - 1.0) for row in keff_rows), default=1.0)
    max_trunc = max((max(float(row["frac_truncated_no_answer"]), float(row["frac_finish_reason_length"])) for row in op_rows), default=1.0)
    max_value_error = max((float(row["value_misselection_rate"]) for row in op_rows), default=1.0)
    call_cap_rate = mean(float(row["call_cap_hit"]) for row in rows) if rows else 1.0
    decoupling_ok = bool(decoupling and decoupling[0].get("decoupling_survives"))
    calls_ok = bool(calls_interaction) and all(bool(row.get("pass")) for row in calls_interaction)
    solve_ok = bool(solve_interaction) and all(bool(row.get("pass")) for row in solve_interaction)
    rho_ok = max_rho_delta <= RHO_TOLERANCE
    op_ok = max_trunc <= TRUNCATION_RATE_THRESHOLD and max_value_error <= 0.05
    landed = decoupling_ok and calls_ok and solve_ok and rho_ok and op_ok
    return [
        {"check": "cap_robust_decoupling_survives", "predicted": "right-censored calls/cap-hit and uncensored solve-rate interactions show chronological degradation with d_global relative to CBJ", "observed": str(decoupling[0] if decoupling else {}), "pass": decoupling_ok, "source": SOURCE, "provenance": "qwen35_p1a_recovery_verdict_v1"},
        {"check": "censoring_aware_calls_interaction", "predicted": "cap-hit and capped-call lower-bound chronological-minus-CBJ d_global interactions are positive", "observed": str(calls_interaction), "pass": calls_ok, "source": SOURCE, "provenance": "qwen35_p1a_recovery_verdict_v1"},
        {"check": "uncensored_solve_rate_interaction", "predicted": "uncensored solved indicator has negative chronological-minus-CBJ d_global interaction", "observed": str(solve_interaction), "pass": solve_ok, "source": SOURCE, "provenance": "qwen35_p1a_recovery_verdict_v1"},
        {"check": "legacy_v0_comm_solved_only_not_decisive", "predicted": "v0 solved-only comm regression is recorded but not used for landing because call-cap rows are right-censored", "observed": str(legacy_decoupling[0] if legacy_decoupling else {}), "pass": True, "source": SOURCE, "provenance": "qwen35_p1a_recovery_verdict_v1"},
        {"check": "rho_near_one", "predicted": f"max |rho-1| <= {RHO_TOLERANCE}", "observed": f"max_rho_delta={max_rho_delta:.6f}", "pass": rho_ok, "source": SOURCE, "provenance": "qwen35_p1a_recovery_verdict_v1"},
        {"check": "operator_clean", "predicted": "P1a terse operator has low truncation and value-misselection rates", "observed": f"max_truncation_or_length={max_trunc:.6f}; max_value_misselection={max_value_error:.6f}", "pass": op_ok, "source": SOURCE, "provenance": "qwen35_p1a_recovery_verdict_v1"},
        {"check": "call_cap_censoring_accounted", "predicted": "CALL_CAP is modeled as right-censoring evidence instead of solved-row missingness", "observed": f"call_cap_rate={call_cap_rate:.6f}", "pass": True, "source": SOURCE, "provenance": "qwen35_p1a_recovery_verdict_v1"},
        {"check": "p1a_recovery_baseline_landed", "predicted": "cap-robust decoupling, censoring-aware calls, uncensored solve-rate interaction, rho near 1, and operator clean", "observed": f"decoupling_ok={decoupling_ok}; calls_ok={calls_ok}; solve_ok={solve_ok}; rho_ok={rho_ok}; op_ok={op_ok}", "pass": landed, "p1a_recovery_baseline_landed": landed, "source": SOURCE, "provenance": "qwen35_p1a_recovery_verdict_v1"},
    ]


def _build_item(payload: dict[str, Any]) -> dict[str, Any]:
    if payload["acceptance"]["p1a_recovery_baseline_landed"]:
        next_step_routing = "P1a recovery baseline landed under the v1 cap-robust censoring-aware verdict; refresh Item060 before any P1b/P1c full-table launch."
    else:
        next_step_routing = "Do not unlock P1b/P1c. Diagnose the P1a recovery baseline failure first under the cap-robust censoring-aware v1 verdict."
    return {
        "schema_version": "log_item_contract_v1",
        "item_number": ITEM_NUMBER,
        "name": "Rung-1 P1a recovery baseline sweep",
        "status": payload["status"],
        "purpose": "Land the P1a recovery baseline itself, using the already-passed terse Qwen branch-value operator with frozen symbolic register, recovery routing, boundary messaging, and P1a symbolic guard.",
        "code_added_used": [{"path": "experiments/rung1_separator_p1a_recovery_baseline.py", "change": "Runs the full P1a recovery sweep and re-emits the baseline with cap-robust, censoring-aware v1 verdict tables from existing rows."}],
        "commands": [
            {"command": ".venv/bin/python -m experiments.rung1_separator_p1a_recovery_baseline --launch-4gpu --num-shards 4 --n-per-cell 24 --n-seeds 2 --batch-size 2 --max-new-tokens 8192", "purpose": "Run the P1a recovery body on GPUs 0-3."},
            {"command": ".venv/bin/python -m experiments.rung1_separator_p1a_recovery_baseline --merge --num-shards 4", "purpose": "Re-emit the baseline v1 verdict from existing shard JSON; no new Qwen calls."},
        ],
        "artifacts": [_rel(RESULTS_PATH), _rel(ITEM_PATH)],
        "provenance": payload["generation_config"],
        "result_tables": {
            "decoupling_survival": {"rows": payload["decoupling_survival"]},
            "keff_inflation": {"rows": payload["keff_inflation"]},
            "operator_error_breakdown": {"rows": payload["operator_error_breakdown"]},
            "arm_cell_summary": {"rows": payload["arm_cell_summary"]},
            "budget_at_95_solve": {"rows": payload["budget_at_95_solve"]},
            "call_cap_truncation_rates": {"rows": payload["call_cap_truncation_rates"]},
            "calls_censoring_summary": {"rows": payload["calls_censoring_summary"]},
            "calls_censoring_interaction": {"rows": payload["calls_censoring_interaction"]},
            "solve_gap_by_cell": {"rows": payload["solve_gap_by_cell"]},
            "solve_rate_interaction": {"rows": payload["solve_rate_interaction"]},
            "legacy_comm_solved_only_regression": {"rows": payload["legacy_comm_solved_only_regression"]},
            "verdict": {"rows": payload["verdict"]},
        },
        "honesty": {
            "does_not_establish": "This lands only the P1a recovery baseline gate under the v1 cap-robust respec. It does not run P1b/P1c bodies.",
            "oracle_policy": "Same-instance symbolic oracle/guard statistics are read-only and never visible inside the LLM prompt beyond the allowed live feasible_colors guard for P1a.",
            "rerun_policy": "v1 re-emission reuses existing shard JSON and does not make new Qwen calls.",
            "po_visibility": payload["generation_config"]["po_visibility"],
        },
        "decision": {
            "gate_outcomes": [{"gate": row["check"], "outcome": "PASS" if row["pass"] else "FAIL", "number": row["observed"]} for row in payload["verdict"]],
            "next_step_routing": next_step_routing,
            "outcome": payload["status"],
            "overall_pass": payload["acceptance"]["p1a_recovery_baseline_landed"],
        },
    }


def merge(output_dir: Path, num_shards: int) -> dict[str, Any]:
    rows = []
    shard_paths = []
    for shard_index in range(num_shards):
        path = output_dir / f"shard_{shard_index:02d}.json"
        shard_paths.append(_rel(path))
        rows.extend(_read_json(path)["instance_arm_metrics"])
    arm_cell = _arm_cell_summary(rows)
    budget = _budget_at_95(rows)
    op_rows = _operator_error_breakdown(rows)
    keff_rows = _keff_inflation(rows)
    decoupling, calls_interaction, solve_interaction, legacy_decoupling = _cap_robust_decoupling(rows)
    calls_summary = _calls_censoring_summary(rows)
    solve_gap = _solve_gap_by_cell(rows)
    verdict = _verdict(decoupling, calls_interaction, solve_interaction, legacy_decoupling, keff_rows, op_rows, rows)
    landed = bool({row["check"]: row for row in verdict}["p1a_recovery_baseline_landed"]["pass"])
    call_cap_trunc = []
    for arm, subset in sorted(_groups(rows, "arm").items()):
        call_cap_trunc.append({"arm": arm[0], "n": len(subset), "call_cap_rate": mean(float(row["call_cap_hit"]) for row in subset), "truncation_or_length_rate": mean(float(row["finish_reason_length_count"] > 0 or row["generation_truncated_no_answer"] > 0) for row in subset), "source": SOURCE, "provenance": "qwen35_p1a_recovery_callcap_truncation_v0"})
    observed_batches = sorted({int(row["batch_size_per_gpu"]) for row in rows})
    observed_n_per_cell = sorted({int(row["n_per_cell"]) for row in rows})
    observed_n_seeds = sorted({int(row["n_seeds"]) for row in rows})
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": STATUS_PASS if landed else STATUS_FAIL,
        "generation_config": {
            "model_id": MODEL_ID,
            "temperature": 0,
            "prompt_contract": P1A_PROMPT_CONTRACT,
            "thinking_disabled": True,
            "max_new_tokens": rows[0]["max_new_tokens"] if rows else DEFAULT_MAX_NEW_TOKENS,
            "n_shards": num_shards,
            "gpu_device_ids": list(range(num_shards)),
            "arms": list(ARMS),
            "requested_cells": list(REQUESTED_TO_CANONICAL_CELLS),
            "cell_alias_map": REQUESTED_TO_CANONICAL_CELLS,
            "n_per_cell_observed_values": observed_n_per_cell,
            "n_seeds_observed_values": observed_n_seeds,
            "batch_size_per_gpu_observed_values": observed_batches,
            "per_instance_llm_call_cap": DEFAULT_CALL_CAP,
            "comm_budget_sweep": COMM_BUDGET_SWEEP,
            "comm_budget_sweep_mode": "offline_posthoc_no_extra_qwen_calls",
            "po_visibility": "agent sees own block, incident boundary edges, and messaged boundary-neighbor colors only; no global graph view",
            "frozen_symbolic_components": ["register", "recovery_routing", "boundary_message_protocol", "symbolic_guard_for_P1a"],
            "parallel_oracle": "same-instance symbolic guard/oracle bookkeeping is read-only and never enters the LLM loop",
            "source": SOURCE,
            "provenance": "qwen35_p1a_recovery_baseline_config_v1",
        },
        "acceptance": {
            "p1a_recovery_baseline_landed": landed,
            "decoupling_survives": bool(decoupling[0].get("decoupling_survives")) if decoupling else False,
            "cap_robust_decoupling_survives": bool(decoupling[0].get("cap_robust_decoupling_survives")) if decoupling else False,
            "legacy_v0_comm_solved_only_decoupling_survives": bool(legacy_decoupling[0].get("decoupling_survives")) if legacy_decoupling else False,
            "censoring_aware_calls_interaction_pass": all(bool(row.get("pass")) for row in calls_interaction),
            "uncensored_solve_rate_interaction_pass": all(bool(row.get("pass")) for row in solve_interaction),
            "rho_near_one": max((abs(float(row["rho"]) - 1.0) for row in keff_rows), default=1.0) <= RHO_TOLERANCE,
            "operator_clean": all(max(float(row["frac_truncated_no_answer"]), float(row["frac_finish_reason_length"])) <= TRUNCATION_RATE_THRESHOLD and float(row["value_misselection_rate"]) <= 0.05 for row in op_rows),
        },
        "decoupling_survival": decoupling,
        "calls_censoring_summary": calls_summary,
        "calls_censoring_interaction": calls_interaction,
        "solve_gap_by_cell": solve_gap,
        "solve_rate_interaction": solve_interaction,
        "legacy_comm_solved_only_regression": legacy_decoupling,
        "keff_inflation": keff_rows,
        "operator_error_breakdown": op_rows,
        "arm_cell_summary": arm_cell,
        "budget_at_95_solve": budget,
        "call_cap_truncation_rates": call_cap_trunc,
        "instance_arm_metrics": rows,
        "shard_paths": shard_paths,
        "verdict": verdict,
    }
    _write_json(RESULTS_PATH, payload)
    _write_json(ITEM_PATH, _build_item(payload))
    return payload


def launch_4gpu(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    processes = []
    for shard_index in range(args.num_shards):
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(shard_index)
        cmd = [args.python_bin, "-u", "-m", "experiments.rung1_separator_p1a_recovery_baseline", "--shard-index", str(shard_index), "--num-shards", str(args.num_shards), "--output-dir", str(output_dir), "--n-per-cell", str(args.n_per_cell), "--n-seeds", str(args.n_seeds), "--batch-size", str(args.batch_size), "--max-new-tokens", str(args.max_new_tokens), "--device", "cuda:0", "--dtype", args.dtype]
        log_path = output_dir / f"shard_{shard_index:02d}.log"
        log_handle = log_path.open("w", encoding="utf-8")
        processes.append((shard_index, log_handle, subprocess.Popen(cmd, cwd=REPO_ROOT, env=env, stdout=log_handle, stderr=subprocess.STDOUT, text=True)))
    failed = []
    for shard_index, log_handle, process in processes:
        code = process.wait()
        log_handle.close()
        if code != 0:
            failed.append((shard_index, code, str(output_dir / f"shard_{shard_index:02d}.log")))
    if failed:
        raise SystemExit(f"failed shards: {failed}")
    merge(output_dir, args.num_shards)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-4gpu", action="store_true")
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--num-shards", type=int, default=4)
    parser.add_argument("--output-dir", default="results/rung1_separator_llm_po/p1a_recovery_baseline_shards")
    parser.add_argument("--n-per-cell", type=int, default=DEFAULT_N_PER_CELL)
    parser.add_argument("--n-seeds", type=int, default=DEFAULT_N_SEEDS)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE_PER_GPU)
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--python-bin", default=str(REPO_ROOT / ".venv/bin/python"))
    args = parser.parse_args()
    output_dir = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO_ROOT / args.output_dir
    if args.launch_4gpu:
        launch_4gpu(args)
    elif args.merge:
        merge(output_dir, args.num_shards)
    else:
        if args.shard_index is None:
            raise SystemExit("provide --shard-index or use --launch-4gpu")
        run_shard(args.shard_index, args.num_shards, output_dir, args.n_per_cell, args.n_seeds, args.batch_size, args.max_new_tokens, args.device, args.dtype)


if __name__ == "__main__":
    main()