"""Harvest and optionally evaluate real-Qwen multi-agent branch/route decisions.

The default mode is offline and deterministic: replay symbolic team-CBJ traces
from the frozen 2x2 preflight manifest and write bounded prompts plus reference
decisions. ``--evaluate`` calls an existing OpenAI-compatible endpoint. Invalid
or unparsable model outputs fail closed; there is no oracle fallback.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT, _adjacency
from experiments.rung1_reasoning_gym_bounded_register import _openai_json_call


SCHEMA_VERSION = "multiagent_real_qwen_decision_gate_v1"
PROMPT_CONTRACT = "multiagent_branch_route_compact_deepest_v2"
STATUS_HARVEST = "MULTIAGENT_REAL_QWEN_DECISION_HARVEST_COMPLETE"
STATUS_PASS = "MULTIAGENT_REAL_QWEN_DECISION_GATE_PASS"
STATUS_FAIL = "MULTIAGENT_REAL_QWEN_DECISION_GATE_FAIL"
BRANCH_SCHEMA = {
    "type": "object",
    "properties": {"color": {"type": "integer"}, "reason": {"type": "string"}},
    "required": ["color"],
}
ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "agent": {"type": "integer"},
        "entry_index": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["agent", "entry_index"],
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        shown = str(path.relative_to(REPO_ROOT))
    except ValueError:
        shown = str(path)
    print(json.dumps({"path": shown, "status": payload.get("status")}), flush=True)


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _register_view(register: list[dict[str, int]], r_value: int) -> tuple[int, list[dict[str, int]]]:
    start = max(0, len(register) - int(r_value))
    return start, [
        {
            "entry_index": index,
            "variable": int(item["vertex"]),
            "value": int(item["color"]),
            "order_index": int(item["order_index"]),
        }
        for index, item in enumerate(register[start:])
    ]


def _branch_prompt(
    row: dict[str, Any],
    vertex: int,
    agent: int,
    domain: list[int],
    assignment: dict[int, int],
    adjacency: list[set[int]],
    partitions: list[int],
    register_view: list[dict[str, int]],
) -> str:
    block_nodes = [node for node, owner in enumerate(partitions) if int(owner) == int(agent)]
    boundary_nodes = sorted({
        neighbor
        for node in block_nodes
        for neighbor in adjacency[node]
        if int(partitions[neighbor]) != int(agent)
    })
    local_assignment = {str(node): int(assignment[node]) for node in block_nodes if node in assignment}
    boundary_assignment = {str(node): int(assignment[node]) for node in boundary_nodes if node in assignment}
    return "\n".join([
        "Bounded multi-agent graph-color branch decision. Return JSON only.",
        "Choose one color from remaining_domain for current_variable.",
        "Use only the block-local state, boundary commitments, and bounded register below.",
        'Return exactly compact JSON: {"color": int}. Omit explanation.',
        f"cell={row['cell']}; instance_id={row['instance_id']}; agent={agent}; current_variable={vertex}",
        f"remaining_domain={json.dumps(domain)}",
        f"block_nodes={json.dumps(block_nodes)}",
        f"local_assignment={json.dumps(local_assignment, sort_keys=True)}",
        f"boundary_assignment={json.dumps(boundary_assignment, sort_keys=True)}",
        f"bounded_register={json.dumps(register_view, sort_keys=True)}",
    ])


def _route_prompt(
    row: dict[str, Any],
    vertex: int,
    agent: int,
    blockers: list[int],
    valid_targets: list[dict[str, int]],
    windows: dict[int, list[dict[str, int]]],
) -> str:
    return "\n".join([
        "Bounded multi-agent graph-color cross-block recovery decision. Return JSON only.",
        "Choose exactly one pair from valid_targets. Do not output a vertex id as entry_index.",
        "Conflict-directed rule: choose the valid target with the largest order_index (the deepest/latest culprit).",
        'Return exactly compact JSON: {"agent": int, "entry_index": int}. Omit explanation.',
        f"cell={row['cell']}; instance_id={row['instance_id']}; current_agent={agent}; conflict_variable={vertex}",
        f"conflict_blockers={json.dumps(blockers)}",
        f"registers_by_agent={json.dumps({str(key): value for key, value in sorted(windows.items())}, sort_keys=True)}",
        f"valid_targets={json.dumps(valid_targets, sort_keys=True)}",
    ])


def _harvest_trace(row: dict[str, Any], r_value: int, node_cap: int) -> list[dict[str, Any]]:
    n = int(row["n_vertices"])
    k = int(row["k"])
    edges = [tuple(map(int, edge)) for edge in row["edges"]]
    partitions = [int(value) for value in row["partitions"]]
    order = [int(value) for value in row["order"]]
    position = {vertex: index for index, vertex in enumerate(order)}
    adjacency = _adjacency(n, edges)
    assignment: dict[int, int] = {}
    next_choice = {vertex: 0 for vertex in order}
    conflict_sets: dict[int, set[int]] = {vertex: set() for vertex in order}
    trail: list[dict[str, int]] = []
    registers: dict[int, list[dict[str, int]]] = defaultdict(list)
    events: list[dict[str, Any]] = []
    cursor = 0
    steps = 0

    while steps < int(node_cap):
        if cursor >= len(order):
            return events
        vertex = order[cursor]
        if vertex in assignment:
            cursor += 1
            continue
        blocked_colors: dict[int, set[int]] = {}
        valid_colors: list[int] = []
        for color in range(1, k + 1):
            blockers = {neighbor for neighbor in adjacency[vertex] if assignment.get(neighbor) == color}
            if blockers:
                blocked_colors[color] = blockers
            else:
                valid_colors.append(color)
        steps += 1
        if next_choice[vertex] < len(valid_colors):
            remaining = valid_colors[next_choice[vertex]:]
            reference_color = remaining[0]
            agent = partitions[vertex]
            _start, bounded = _register_view(registers[agent], int(r_value))
            prompt = _branch_prompt(row, vertex, agent, remaining, assignment, adjacency, partitions, bounded)
            events.append({
                "event": "branch",
                "cell": str(row["cell"]),
                "capacity": str(row["capacity"]),
                "coupling": str(row["coupling"]),
                "instance_id": str(row["instance_id"]),
                "step": steps,
                "agent": int(agent),
                "vertex": int(vertex),
                "valid_colors": [int(value) for value in remaining],
                "reference_color": int(reference_color),
                "prompt": prompt,
                "prompt_sha256": _prompt_hash(prompt),
            })
            next_choice[vertex] += 1
            assignment[vertex] = int(reference_color)
            item = {"vertex": int(vertex), "color": int(reference_color), "agent": int(agent), "order_index": int(cursor)}
            trail.append(item)
            registers[agent].append(item)
            cursor += 1
            continue

        blockers = set().union(*blocked_colors.values()) if blocked_colors else set()
        blockers = {item for item in blockers if item in assignment and position[item] < cursor}
        next_choice[vertex] = 0
        if not blockers or not trail:
            return events
        windows: dict[int, list[dict[str, int]]] = {}
        window_starts: dict[int, int] = {}
        for agent in sorted(set(partitions)):
            start, bounded = _register_view(registers[agent], int(r_value))
            window_starts[agent] = start
            windows[agent] = bounded
        valid_targets: list[dict[str, int]] = []
        for blocker in sorted(blockers):
            agent = partitions[blocker]
            register = registers[agent]
            absolute_index = max((index for index, item in enumerate(register) if item["vertex"] == blocker), default=-1)
            entry_index = absolute_index - window_starts[agent]
            if 0 <= entry_index < len(windows[agent]):
                valid_targets.append({
                    "agent": int(agent),
                    "entry_index": int(entry_index),
                    "variable": int(blocker),
                    "order_index": int(position[blocker]),
                })
        reference_vertex = max(blockers, key=lambda item: position[item])
        reference_target = next((target for target in valid_targets if target["variable"] == reference_vertex), None)
        if reference_target is None:
            return events
        agent = partitions[vertex]
        prompt = _route_prompt(row, vertex, agent, sorted(blockers), valid_targets, windows)
        events.append({
            "event": "route",
            "cell": str(row["cell"]),
            "capacity": str(row["capacity"]),
            "coupling": str(row["coupling"]),
            "instance_id": str(row["instance_id"]),
            "step": steps,
            "agent": int(agent),
            "vertex": int(vertex),
            "blockers": sorted(map(int, blockers)),
            "valid_targets": valid_targets,
            "reference_target": reference_target,
            "prompt": prompt,
            "prompt_sha256": _prompt_hash(prompt),
        })
        conflict_sets[reference_vertex].update(blocker for blocker in blockers if blocker != reference_vertex)
        target_trail_index = max(index for index, item in enumerate(trail) if item["vertex"] == reference_vertex)
        popped = trail[target_trail_index:]
        popped_vertices = {item["vertex"] for item in popped}
        for item in popped:
            assignment.pop(item["vertex"], None)
        trail = trail[:target_trail_index]
        for register_agent in list(registers):
            registers[register_agent] = [item for item in registers[register_agent] if item["vertex"] not in popped_vertices]
        for item in popped[1:]:
            next_choice[item["vertex"]] = 0
            conflict_sets[item["vertex"]].clear()
        conflict_sets[vertex].clear()
        cursor = popped[0]["order_index"]
    return events


def _select_samples(manifest: list[dict[str, Any]], per_cell_event: int, r_value: int, node_cap: int) -> list[dict[str, Any]]:
    pools: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(manifest, key=lambda item: (str(item["cell"]), str(item["instance_id"]))):
        for event in _harvest_trace(row, int(r_value), int(node_cap)):
            pools[(str(row["cell"]), str(event["event"]))].append(event)
    selected: list[dict[str, Any]] = []
    for cell in ("under_low", "under_high", "over_low", "over_high"):
        for event in ("branch", "route"):
            candidates = pools[(cell, event)]
            if event == "branch":
                chosen: list[dict[str, Any]] = []
                used_instances: set[str] = set()
                target_sizes = [2] * (int(per_cell_event) // 2) + [3] * (int(per_cell_event) - int(per_cell_event) // 2)
                for domain_size in target_sizes:
                    candidate = next(
                        (
                            row
                            for row in sorted(candidates, key=lambda item: (str(item["instance_id"]), int(item["step"])))
                            if len(row["valid_colors"]) == domain_size
                            and str(row["instance_id"]) not in used_instances
                        ),
                        None,
                    )
                    if candidate is not None:
                        chosen.append(candidate)
                        used_instances.add(str(candidate["instance_id"]))
                if len(chosen) < int(per_cell_event):
                    priority = {2: 0, 3: 1, 1: 2, 4: 3}
                    for candidate in sorted(
                        candidates,
                        key=lambda item: (
                            priority.get(len(item["valid_colors"]), 9),
                            str(item["instance_id"]),
                            int(item["step"]),
                        ),
                    ):
                        if str(candidate["instance_id"]) in used_instances:
                            continue
                        chosen.append(candidate)
                        used_instances.add(str(candidate["instance_id"]))
                        if len(chosen) >= int(per_cell_event):
                            break
                selected.extend(chosen[: int(per_cell_event)])
                continue
            # Spread samples across instances before taking later events from the same trace.
            by_instance: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in candidates:
                by_instance[str(row["instance_id"])].append(row)
            round_index = 0
            while len([row for row in selected if row["cell"] == cell and row["event"] == event]) < int(per_cell_event):
                added = False
                for instance_id in sorted(by_instance):
                    rows = by_instance[instance_id]
                    if round_index < len(rows):
                        selected.append(rows[round_index])
                        added = True
                        if len([row for row in selected if row["cell"] == cell and row["event"] == event]) >= int(per_cell_event):
                            break
                if not added:
                    break
                round_index += 1
    for index, row in enumerate(selected):
        row["sample_id"] = f"decision_{index:04d}_{row['cell']}_{row['event']}"
    return selected


def _evaluate_one(row: dict[str, Any], base_url: str, model: str, max_tokens: int) -> dict[str, Any]:
    schema = BRANCH_SCHEMA if row["event"] == "branch" else ROUTE_SCHEMA
    generation = _openai_json_call(base_url, model, row["prompt"], int(max_tokens), schema)
    parsed = generation.get("parsed") or {}
    parseable = False
    valid = False
    exact = False
    prediction: dict[str, int] | None = None
    if row["event"] == "branch":
        try:
            color = int(parsed.get("color"))
            parseable = True
            valid = color in {int(value) for value in row["valid_colors"]}
            exact = valid and color == int(row["reference_color"])
            prediction = {"color": color}
        except (TypeError, ValueError):
            pass
    else:
        try:
            agent = int(parsed.get("agent"))
            entry_index = int(parsed.get("entry_index"))
            parseable = True
            prediction = {"agent": agent, "entry_index": entry_index}
            valid = any(
                int(target["agent"]) == agent and int(target["entry_index"]) == entry_index
                for target in row["valid_targets"]
            )
            exact = valid and agent == int(row["reference_target"]["agent"]) and entry_index == int(row["reference_target"]["entry_index"])
        except (TypeError, ValueError):
            pass
    return {
        "sample_id": row["sample_id"],
        "cell": row["cell"],
        "event": row["event"],
        "base_url": base_url,
        "parseable": parseable,
        "valid": valid,
        "exact": exact,
        "prediction": prediction,
        "model_text": str(generation.get("text", ""))[-1024:],
        "finish_reason": generation.get("finish_reason"),
        "prompt_tokens": int(generation.get("prompt_tokens", 0)),
        "output_tokens": int(generation.get("output_tokens", 0)),
        "total_tokens": int(generation.get("total_tokens", 0)),
        "oracle_fallback_used": False,
    }


def _summarize_evaluations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for cell, event in sorted({(row["cell"], row["event"]) for row in rows}):
        subset = [row for row in rows if row["cell"] == cell and row["event"] == event]
        output.append({
            "cell": cell,
            "event": event,
            "n": len(subset),
            "parse_rate": mean(float(row["parseable"]) for row in subset),
            "valid_rate": mean(float(row["valid"]) for row in subset),
            "exact_rate": mean(float(row["exact"]) for row in subset),
            "mean_prompt_tokens": mean(float(row["prompt_tokens"]) for row in subset),
            "mean_output_tokens": mean(float(row["output_tokens"]) for row in subset),
            "mean_total_tokens": mean(float(row["total_tokens"]) for row in subset),
            "finish_reason_counts": dict(Counter(str(row["finish_reason"]) for row in subset)),
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest or evaluate real-Qwen multi-agent decision gates.")
    parser.add_argument("--manifest", type=Path, default=Path("results/multiagent_core_2x2_preflight/instance_manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("results/multiagent_real_qwen_decision_gate/harvest.json"))
    parser.add_argument("--samples-per-cell-event", type=int, default=8)
    parser.add_argument("--register", type=int, default=8)
    parser.add_argument("--node-cap", type=int, default=20000)
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--base-urls", default="")
    parser.add_argument("--model", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    manifest_payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest = list(manifest_payload.get("rows", []))
    samples = _select_samples(manifest, int(args.samples_per_cell_event), int(args.register), int(args.node_cap))
    expected = 4 * 2 * int(args.samples_per_cell_event)
    harvest_complete = len(samples) == expected
    payload: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "prompt_contract": PROMPT_CONTRACT,
        "status": STATUS_HARVEST,
        "mode": "offline_harvest",
        "source_manifest": str(args.manifest),
        "config": vars(args) | {"manifest": str(args.manifest), "output": str(args.output)},
        "expected_samples": expected,
        "harvested_samples": len(samples),
        "harvest_complete": harvest_complete,
        "samples": samples,
        "headline_eligible": False,
        "honesty": {
            "no_oracle_fallback": True,
            "does_not_establish": "Offline harvest establishes no model decision quality. Evaluation establishes only bounded decision parse/valid/exact rates, not end-to-end solve rate.",
        },
    }
    if args.evaluate:
        base_urls = [item.strip() for item in args.base_urls.split(",") if item.strip()] or [args.base_url]
        evaluations: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as executor:
            futures = {
                executor.submit(
                    _evaluate_one,
                    row,
                    base_urls[index % len(base_urls)],
                    args.model,
                    args.max_tokens,
                ): row["sample_id"]
                for index, row in enumerate(samples)
            }
            for future in as_completed(futures):
                evaluations.append(future.result())
        evaluations.sort(key=lambda row: row["sample_id"])
        summary = _summarize_evaluations(evaluations)
        branch_rows = [row for row in evaluations if row["event"] == "branch"]
        route_rows = [row for row in evaluations if row["event"] == "route"]
        gates = {
            "harvest_complete": harvest_complete,
            "branch_parse_rate_ge_0_95": mean(float(row["parseable"]) for row in branch_rows) >= 0.95 if branch_rows else False,
            "branch_valid_rate_ge_0_90": mean(float(row["valid"]) for row in branch_rows) >= 0.90 if branch_rows else False,
            "route_parse_rate_ge_0_95": mean(float(row["parseable"]) for row in route_rows) >= 0.95 if route_rows else False,
            "route_valid_rate_ge_0_90": mean(float(row["valid"]) for row in route_rows) >= 0.90 if route_rows else False,
            "no_oracle_fallback": all(not row["oracle_fallback_used"] for row in evaluations),
        }
        gates["go_end_to_end_dev"] = all(gates.values())
        payload.update({
            "status": STATUS_PASS if gates["go_end_to_end_dev"] else STATUS_FAIL,
            "mode": "real_qwen_decision_evaluation",
            "base_urls": base_urls,
            "evaluations": evaluations,
            "summary": summary,
            "gates": gates,
        })
    output = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    _write_json(output, payload)


if __name__ == "__main__":
    main()
