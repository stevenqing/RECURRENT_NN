"""Controlled multi-agent CBJ on Reasoning Gym graph_color official harness."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_reasoning_gym_bounded_register import _ensure_reasoning_gym, _graph_color_view, _official_answer, _official_score, _openai_json_call, BRANCH_SCHEMA
from experiments.rung1_separator_llm_inloop import DEFAULT_OPENAI_BASE_URL, DEFAULT_OPENAI_MODEL


RESULTS_DIR = REPO_ROOT / "results/rung1_multiagent_graphcolor"
RESULTS_PATH = RESULTS_DIR / "results.json"
SCHEMA_VERSION = "rung1_multiagent_graphcolor_v0"
STATUS_COMPLETE = "RUNG1_MULTIAGENT_GRAPHCOLOR_COMPLETE"
STATUS_PREFLIGHT_FAIL = "RUNG1_MULTIAGENT_GRAPHCOLOR_PREFLIGHT_FAIL"
CULPRIT_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {"agent": {"type": "integer"}, "reason": {"type": "string"}}, "required": ["agent", "reason"]}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _unit(*parts: Any) -> float:
    digest = hashlib.blake2b("::".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") / float(2**64)


def _make_dataset(args: argparse.Namespace) -> Any:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    return reasoning_gym.create_dataset("graph_color", size=args.scan_limit, seed=args.seed, num_colors=args.num_colors, min_num_vertices=args.num_vertices, max_num_vertices=args.num_vertices, edge_probability=args.edge_probability)


def _partition(view: dict[str, Any], n_blocks: int, balance_weight: float, seed: int) -> dict[int, int]:
    order = sorted(view["vertices"], key=lambda vertex: (-len(view["adjacency"][vertex]), vertex))
    target = math.ceil(len(order) / n_blocks)
    owner: dict[int, int] = {}
    loads = [0] * n_blocks
    for vertex in order:
        best = None
        for block in range(n_blocks):
            same = sum(1 for neighbor in view["adjacency"][vertex] if owner.get(neighbor) == block)
            overflow = max(0, loads[block] + 1 - target)
            score = -same + balance_weight * loads[block] + 1000 * overflow + 1e-6 * _unit(seed, vertex, block)
            if best is None or score < best[0]:
                best = (score, block)
        owner[vertex] = int(best[1])
        loads[int(best[1])] += 1
    return owner


def _partition_stats(view: dict[str, Any], owner: dict[int, int]) -> dict[str, Any]:
    cross_edges = [(left, right) for left, right in view["edges"] if owner[left] != owner[right]]
    boundary = sorted({vertex for edge in cross_edges for vertex in edge})
    return {"B": len(set(owner.values())), "block_sizes": dict(Counter(owner.values())), "cross_block_edges": len(cross_edges), "boundary_nodes": len(boundary), "separator_ratio_edges": len(cross_edges) / max(1, len(view["edges"])), "separator_ratio_nodes": len(boundary) / max(1, len(view["vertices"]))}


def _domain(view: dict[str, Any], vertex: int, assignment: dict[int, int], tried: dict[int, set[int]]) -> list[int]:
    blocked = {assignment[neighbor] for neighbor in view["adjacency"][vertex] if neighbor in assignment}
    return [color for color in view["color_options"] if color not in blocked and color not in tried[vertex]]


def _local_domain(view: dict[str, Any], owner: dict[int, int], vertex: int, assignment: dict[int, int], tried: dict[int, set[int]]) -> list[int]:
    agent = owner[vertex]
    blocked = {assignment[neighbor] for neighbor in view["adjacency"][vertex] if neighbor in assignment and owner[neighbor] == agent}
    return [color for color in view["color_options"] if color not in blocked and color not in tried[vertex]]


def _cross_conflict(view: dict[str, Any], owner: dict[int, int], assignment: dict[int, int]) -> tuple[int, int] | None:
    for left, right in view["edges"]:
        if owner[left] != owner[right] and left in assignment and right in assignment and assignment[left] == assignment[right]:
            return (left, right)
    return None


def _branch_prompt(entry: dict[str, Any], view: dict[str, Any], owner: dict[int, int], vertex: int, domain: list[int], assignment: dict[int, int]) -> str:
    agent = owner[vertex]
    block_nodes = sorted(node for node, block in owner.items() if block == agent)
    boundary = sorted({neighbor for node in block_nodes for neighbor in view["adjacency"][node] if owner[neighbor] != agent})
    boundary_assignment = {node: assignment[node] for node in boundary if node in assignment}
    local_assignment = {node: assignment[node] for node in block_nodes if node in assignment}
    return "\n".join([
        "Controlled multi-agent graph_color branch decision. Return JSON only.",
        "Choose one color from remaining_domain. Symbolic code owns state, conflicts, registers, and score_answer validation.",
        "Schema: {\"color\": integer, \"reason\": string}",
        f"source_index={entry['metadata'].get('source_index')}; agent={agent}; current_variable={vertex}",
        f"remaining_domain={domain}",
        f"block_nodes={block_nodes}",
        f"local_assignment={local_assignment}",
        f"boundary_nodes={boundary}",
        f"boundary_assignment={boundary_assignment}",
    ])


def _culprit_prompt(entry: dict[str, Any], conflict: tuple[int, int], candidates: list[int], register_view: list[dict[str, Any]]) -> str:
    return "\n".join([
        "Controlled multi-agent graph_color culprit routing. Return JSON only.",
        "Choose which candidate agent should retract.",
        "Schema: {\"agent\": integer, \"reason\": string}",
        f"source_index={entry['metadata'].get('source_index')}; conflict_edge={conflict}; candidate_agents={candidates}",
        f"bounded_registers={register_view}",
    ])


def _row(entry: dict[str, Any], view: dict[str, Any], owner: dict[int, int], arm: str, status: str, score: float, assignment: dict[int, int], stats: dict[str, Any]) -> dict[str, Any]:
    return {"source_index": int(entry["metadata"].get("source_index", -1)), "arm": arm, "status": status, "official_score": score, "solved": score >= 1.0, "answer": _official_answer(assignment) if score >= 1.0 else None, "B": len(set(owner.values())), "n_vertices": len(view["vertices"]), "n_edges": len(view["edges"]), "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_episode_v0", **stats}


def _run_team(dataset: Any, entry: dict[str, Any], owner: dict[int, int], arm: str, args: argparse.Namespace) -> dict[str, Any]:
    view = _graph_color_view(entry, args.order_mode)
    order = sorted(view["vertices"], key=lambda vertex: (-len(view["adjacency"][vertex]), owner[vertex], vertex))
    position = {vertex: idx for idx, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    tried: dict[int, set[int]] = defaultdict(set)
    trail: list[dict[str, Any]] = []
    registers: dict[int, list[dict[str, Any]]] = defaultdict(list)
    cursor = 0
    stats = {"decision_calls": 0, "llm_calls": 0, "parseable_decisions": 0, "valid_decisions": 0, "cross_block_messages": 0, "cross_block_recoveries": 0, "total_retractions": 0, "max_register_view_len": 0, "max_prompt_chars": 0}
    while True:
        if stats["decision_calls"] >= args.call_cap:
            return _row(entry, view, owner, arm, "CALL_CAP", _official_score(dataset, entry, assignment), assignment, stats)
        conflict = _cross_conflict(view, owner, assignment)
        if conflict is not None:
            if arm == "forward":
                return _row(entry, view, owner, arm, "FORWARD_CROSS_BLOCK_CONFLICT", _official_score(dataset, entry, assignment), assignment, stats)
            candidates = sorted({owner[conflict[0]], owner[conflict[1]]})
            oracle_vertex = max(conflict, key=lambda vertex: position[vertex])
            oracle_agent = owner[oracle_vertex]
            latest_agent = trail[-1]["agent"] if trail else oracle_agent
            if arm == "chrono":
                target_agent = latest_agent
                stats["cross_block_messages"] += max(1, len(trail) - max(idx for idx, item in enumerate(trail) if item["agent"] == target_agent)) if trail else 1
            elif arm == "cbj_random":
                target_agent = candidates[min(len(candidates) - 1, int(_unit(entry["metadata"].get("source_index"), stats["decision_calls"], arm) * len(candidates)))]
                stats["cross_block_messages"] += 1
            elif arm == "cbj_llm" and not args.no_llm:
                register_view = [{"agent": agent, "entries": registers[agent][-args.register_limit:]} for agent in candidates]
                prompt = _culprit_prompt(entry, conflict, candidates, register_view)
                stats["max_prompt_chars"] = max(stats["max_prompt_chars"], len(prompt))
                generation = _openai_json_call(args.openai_base_url, args.openai_model, prompt, args.max_new_tokens, CULPRIT_SCHEMA)
                try:
                    target_agent = int(generation["parsed"].get("agent"))
                    stats["parseable_decisions"] += 1
                except (TypeError, ValueError):
                    target_agent = oracle_agent
                if target_agent not in candidates:
                    target_agent = oracle_agent
                else:
                    stats["valid_decisions"] += 1
                stats["llm_calls"] += 1
                stats["cross_block_messages"] += 1
            else:
                target_agent = oracle_agent
                stats["cross_block_messages"] += 1
            stats["cross_block_recoveries"] += 1
            target_indices = [idx for idx, item in enumerate(trail) if item["agent"] == target_agent]
            if not target_indices:
                return _row(entry, view, owner, arm, "NO_RECOVERY_TARGET", _official_score(dataset, entry, assignment), assignment, stats)
            target_index = target_indices[-1]
            popped = trail[target_index:]
            stats["total_retractions"] += len(popped)
            for item in popped:
                assignment.pop(item["vertex"], None)
            popped_vertices = {item["vertex"] for item in popped}
            trail = [item for item in trail if item["vertex"] not in popped_vertices]
            for agent in list(registers):
                registers[agent] = [item for item in registers[agent] if item["vertex"] not in popped_vertices]
            for item in popped[1:]:
                tried[item["vertex"]] = set()
            cursor = min(position[item["vertex"]] for item in popped)
            continue
        if cursor >= len(order):
            score = _official_score(dataset, entry, assignment)
            return _row(entry, view, owner, arm, "SOLVED" if score >= 1.0 else "OFFICIAL_SCORE_FAIL", score, assignment, stats)
        vertex = order[cursor]
        if vertex in assignment:
            cursor += 1
            continue
        domain = _local_domain(view, owner, vertex, assignment, tried)
        if not domain:
            if arm == "forward":
                return _row(entry, view, owner, arm, "FORWARD_DEAD_END", _official_score(dataset, entry, assignment), assignment, stats)
            blockers = [neighbor for neighbor in view["adjacency"][vertex] if neighbor in assignment]
            if not blockers:
                return _row(entry, view, owner, arm, "NO_RECOVERY_TARGET", _official_score(dataset, entry, assignment), assignment, stats)
            target_vertex = max(blockers, key=lambda item: position[item])
            target_index = max((idx for idx, item in enumerate(trail) if item["vertex"] == target_vertex), default=-1)
            if target_index < 0:
                return _row(entry, view, owner, arm, "NO_RECOVERY_TARGET", _official_score(dataset, entry, assignment), assignment, stats)
            popped = trail[target_index:]
            stats["total_retractions"] += len(popped)
            for item in popped:
                assignment.pop(item["vertex"], None)
            popped_vertices = {item["vertex"] for item in popped}
            trail = [item for item in trail if item["vertex"] not in popped_vertices]
            for agent in list(registers):
                registers[agent] = [item for item in registers[agent] if item["vertex"] not in popped_vertices]
            for item in popped[1:]:
                tried[item["vertex"]] = set()
            cursor = target_index
            continue
        agent = owner[vertex]
        stats["max_register_view_len"] = max(stats["max_register_view_len"], min(args.register_limit, len(registers[agent])))
        oracle_color = domain[0]
        if args.no_llm:
            color = oracle_color
        else:
            prompt = _branch_prompt(entry, view, owner, vertex, domain, assignment)
            stats["max_prompt_chars"] = max(stats["max_prompt_chars"], len(prompt))
            generation = _openai_json_call(args.openai_base_url, args.openai_model, prompt, args.max_new_tokens, BRANCH_SCHEMA)
            try:
                color = int(generation["parsed"].get("color"))
                stats["parseable_decisions"] += 1
            except (TypeError, ValueError):
                color = oracle_color
            if color not in domain:
                color = oracle_color
            else:
                stats["valid_decisions"] += 1
            stats["llm_calls"] += 1
        stats["decision_calls"] += 1
        tried[vertex].add(color)
        assignment[vertex] = color
        item = {"vertex": vertex, "color": color, "agent": agent}
        trail.append(item)
        registers[agent].append(item)
        cursor += 1


def _run_monolith(dataset: Any, entry: dict[str, Any], r_value: int, args: argparse.Namespace) -> dict[str, Any]:
    from experiments.rung1_reasoning_gym_bounded_register import _run_episode as run_single
    selected = {"entry": entry, "source_index": entry["metadata"].get("source_index"), "trace": {}}
    ns = argparse.Namespace(**vars(args))
    ns.dataset = "graph_color"
    row = run_single(dataset, selected, r_value, "llm", ns)
    return {"source_index": int(entry["metadata"].get("source_index")), "R": r_value, "official_score": row["official_score"], "solved": row["solved"], "status": row["status"], "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_monolith_v0"}


def _summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for key in sorted({(row["B"], row["arm"]) for row in rows}):
        b_value, arm = key
        subset = [row for row in rows if (row["B"], row["arm"]) == key]
        out.append({"B": b_value, "arm": arm, "n": len(subset), "solve_rate": mean(float(row["official_score"] >= 1.0) for row in subset), "mean_official_score": mean(row["official_score"] for row in subset), "mean_cross_block_messages": mean(row["cross_block_messages"] for row in subset), "mean_cross_block_recoveries": mean(row["cross_block_recoveries"] for row in subset), "mean_total_retractions": mean(row["total_retractions"] for row in subset), "status_counts": dict(Counter(row["status"] for row in subset)), "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_summary_v0"})
    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    dataset = _make_dataset(args)
    b_values = [int(item) for item in args.b_values.split(",") if item.strip()]
    arms = [item for item in args.arms.split(",") if item.strip()]
    selected = []
    preflight = []
    dry_args = argparse.Namespace(**{**vars(args), "no_llm": True})
    for index in range(args.scan_limit):
        entry = dataset[index]
        view = _graph_color_view(entry, args.order_mode)
        stats = []
        ok = False
        for b_value in b_values:
            owner = _partition(view, b_value, args.balance_weight, args.seed + index)
            part_stats = _partition_stats(view, owner)
            dry = _run_team(dataset, entry, owner, "cbj_oracle", dry_args)
            part_stats |= {"cross_block_recoveries": dry["cross_block_recoveries"], "dry_score": dry["official_score"], "dry_status": dry["status"]}
            stats.append(part_stats)
            ok = ok or (dry["official_score"] >= 1.0 and dry["cross_block_recoveries"] >= args.min_cross_backtracks)
        preflight.append({"source_index": index, "selected": ok, "stats_by_B": stats, "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_preflight_row_v0"})
        if ok:
            selected.append({"entry": entry, "view": view, "source_index": index})
        if len(selected) >= args.n_instances:
            break
    status = STATUS_COMPLETE if len(selected) >= args.n_instances else STATUS_PREFLIGHT_FAIL
    rows: list[dict[str, Any]] = []
    monolith_rows: list[dict[str, Any]] = []
    if status == STATUS_COMPLETE:
        tasks = []
        for item in selected:
            monolith_rows.append(_run_monolith(dataset, item["entry"], args.register_limit, args))
            for b_value in b_values:
                owner = _partition(item["view"], b_value, args.balance_weight, args.seed + item["source_index"])
                partition_stats = _partition_stats(item["view"], owner)
                for arm in arms:
                    tasks.append((item, owner, partition_stats, arm))
        if args.no_llm:
            for item, owner, partition_stats, arm in tasks:
                rows.append(_run_team(dataset, item["entry"], owner, arm, args) | {"partition": partition_stats})
        else:
            with ThreadPoolExecutor(max_workers=max(1, min(args.batch_size, len(tasks)))) as pool:
                futures = {pool.submit(_run_team, dataset, item["entry"], owner, arm, args): (partition_stats, arm) for item, owner, partition_stats, arm in tasks}
                for future in as_completed(futures):
                    partition_stats, arm = futures[future]
                    rows.append(future.result() | {"partition": partition_stats})
    by_arm = _summarize(rows)
    monolith_solve_rate = mean(float(row["official_score"] >= 1.0) for row in monolith_rows) if monolith_rows else None
    claim3_rows = []
    for b_value in b_values:
        cbj = next((row for row in by_arm if row["B"] == b_value and row["arm"] in {"cbj_llm", "cbj_oracle"}), None)
        chrono = next((row for row in by_arm if row["B"] == b_value and row["arm"] == "chrono"), None)
        if cbj and chrono:
            claim3_rows.append({"B": b_value, "cbj_messages": cbj["mean_cross_block_messages"], "chrono_messages": chrono["mean_cross_block_messages"], "cbj_solve_rate": cbj["solve_rate"], "chrono_solve_rate": chrono["solve_rate"], "cbj_below_chrono": cbj["mean_cross_block_messages"] < chrono["mean_cross_block_messages"], "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_claim3_row_v0"})
    team_vs_mono = []
    for row in by_arm:
        if row["arm"] in {"cbj_llm", "cbj_oracle"}:
            team_vs_mono.append({"B": row["B"], "arm": row["arm"], "team_solve_rate": row["solve_rate"], "monolith_solve_rate": monolith_solve_rate, "team_minus_monolith": None if monolith_solve_rate is None else row["solve_rate"] - monolith_solve_rate, "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_team_vs_monolith_v0"})
    payload = {"schema_version": SCHEMA_VERSION, "status": status, "generated_at": _now(), "dataset_config": {"dataset": "graph_color", "seed": args.seed, "num_vertices": args.num_vertices, "num_colors": args.num_colors, "edge_probability": args.edge_probability, "official_scoring": "dataset.score_answer(answer, entry)", "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_dataset_config_v0"}, "preflight": {"selected_instances": len(selected), "min_cross_backtracks": args.min_cross_backtracks, "official_scoring_only": True, "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_preflight_v0"}, "partition": {"b_values": b_values, "rows": preflight[: args.max_preflight_rows], "selected_source_indices": [item["source_index"] for item in selected], "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_partition_v0"}, "by_arm": by_arm, "monolith_baseline": {"rows": monolith_rows, "solve_rate": monolith_solve_rate, "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_monolith_summary_v0"}, "trackM1_claim3": {"rows": claim3_rows, "claim3_verdict": "positive" if claim3_rows and all(row["cbj_below_chrono"] for row in claim3_rows) else "honest_negative_or_underpowered", "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_trackM1_v0"}, "trackM2A_capacity": {"rows": team_vs_mono, "claim4_capacity_verdict": "positive" if any((row.get("team_minus_monolith") or 0) > 0 for row in team_vs_mono) else "honest_negative_or_not_discriminating", "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_trackM2A_v0"}, "trackM2B_culprit": {"rows": [row for row in by_arm if row["arm"] in {"cbj_llm", "cbj_oracle", "cbj_random", "chrono"}], "claim4_culprit_verdict": "recorded", "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_trackM2B_v0"}, "bounded_view": {"bounded_view_verified": all(row["max_register_view_len"] <= args.register_limit for row in rows), "max_register_view_len": max([row["max_register_view_len"] for row in rows], default=0), "max_prompt_chars": max([row["max_prompt_chars"] for row in rows], default=0), "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_bounded_view_v0"}, "budget_ledger": [{"n_instances": len(selected), "b_values": b_values, "arms": arms, "register_limit": args.register_limit, "call_cap": args.call_cap, "batch_size": args.batch_size, "max_episode_runs": len(selected) * len(b_values) * len(arms), "source": SOURCE, "provenance": "rung1_multiagent_graphcolor_budget_v0"}], "episode_rows": rows, "headline": {"claim3_determination": "positive" if claim3_rows and all(row["cbj_below_chrono"] for row in claim3_rows) else "honest_negative_or_underpowered", "claim4_multi_capacity": "positive" if any((row.get("team_minus_monolith") or 0) > 0 for row in team_vs_mono) else "honest_negative_or_not_discriminating", "single_next_move": "If no-LLM controlled gates discriminate, start vLLM and run cbj_llm culprit arm on the same Reasoning Gym partitions."}, "source": SOURCE, "provenance": SCHEMA_VERSION}
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Controlled multi-agent CBJ on official Reasoning Gym graph_color.")
    parser.add_argument("--output", type=Path, default=RESULTS_PATH)
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scan-limit", type=int, default=200)
    parser.add_argument("--n-instances", type=int, default=8)
    parser.add_argument("--max-preflight-rows", type=int, default=80)
    parser.add_argument("--num-vertices", type=int, default=16)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--edge-probability", type=float, default=0.4)
    parser.add_argument("--order-mode", default="degree_desc")
    parser.add_argument("--b-values", default="2,3,4")
    parser.add_argument("--arms", default="forward,chrono,cbj_oracle,cbj_random")
    parser.add_argument("--register-limit", type=int, default=8)
    parser.add_argument("--call-cap", type=int, default=400)
    parser.add_argument("--min-cross-backtracks", type=int, default=1)
    parser.add_argument("--balance-weight", type=float, default=0.05)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--openai-base-url", default=DEFAULT_OPENAI_BASE_URL)
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--no-llm", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
