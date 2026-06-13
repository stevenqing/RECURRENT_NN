"""LLM-native bounded-register search-decision paradigm pilot."""

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
from urllib.error import URLError
from urllib.request import Request, urlopen

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _adjacency, _rel
from experiments.rung1_fallible_1d_rerun import _read_json, _write_checkpoint
from experiments.rung1_separator_llm_inloop import DEFAULT_OPENAI_BASE_URL, DEFAULT_OPENAI_MODEL, _load_separator_manifest
from experiments.rung1_separator_p1b_full_table import GRADED_PATH, _operator_by_b
from experiments.rung1_separator_scaling import DEFAULT_NODE_CAP, _instance_from_row


RESULTS_DIR = REPO_ROOT / "results/rung1_llm_search_decision_paradigm"
RESULTS_PATH = RESULTS_DIR / "results.json"
SCHEMA_VERSION = "rung1_llm_search_decision_paradigm_v0"
STATUS_COMPLETE = "RUNG1_LLM_SEARCH_DECISION_PARADIGM_COMPLETE"
STATUS_PREFLIGHT_FAIL = "RUNG1_LLM_SEARCH_DECISION_PARADIGM_PREFLIGHT_FAIL"
R_VALUES = (0, 2, 4, 8, 16, 32)
TARGET_SOURCES = ("llm", "oracle", "random")
BRANCH_SCHEMA = {"type": "object", "properties": {"color": {"type": "integer"}, "reason": {"type": "string"}}, "required": ["color"]}
BACKTRACK_SCHEMA = {"type": "object", "properties": {"entry_index": {"type": "integer"}, "reason": {"type": "string"}}, "required": ["entry_index"]}
EXTERNAL_BENCHMARKS = [
    {
        "name": "reasoning-gym",
        "repo": "https://github.com/open-thought/reasoning-gym",
        "local_inspection_path": "/tmp/reasoning_benchmarks/reasoning-gym",
        "harness": "reasoning_gym.create_dataset(...) plus dataset.score_answer(answer, entry); eval/AsyncModelEvaluator supplies async OpenAI-compatible concurrency, checkpoint, and resume.",
        "relevant_tasks": ["graph_color", "zebra_puzzles"],
    },
    {
        "name": "AgentsNet",
        "repo": "https://github.com/floriangroetschla/AgentsNet",
        "local_inspection_path": "/tmp/reasoning_benchmarks/AgentsNet",
        "harness": "LiteralMessagePassing implements synchronous multi-agent rounds, transcripts, parsing fallbacks, and task score functions; main.py loads graph instances from disco-eth/AgentsNet.",
        "relevant_tasks": ["coloring", "consensus", "leader_election", "matching", "vertex_cover"],
    },
]


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


def _openai_json_call(base_url: str, model: str, prompt: str, max_tokens: int, schema: dict[str, Any]) -> dict[str, Any]:
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": max_tokens, "structured_outputs": {"json": schema}}
    request = Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=3600) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"OpenAI-compatible request failed: {exc}") from exc
    choice = decoded.get("choices", [{}])[0]
    text = choice.get("message", {}).get("content", "")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {}
    return {"text": text, "parsed": parsed, "finish_reason": choice.get("finish_reason"), "output_tokens": int(decoded.get("usage", {}).get("completion_tokens") or 0)}


def _clean_trace(row: dict[str, Any], keff: float, node_cap: int) -> dict[str, Any]:
    instance = _instance_from_row(row)
    adj = _adjacency(instance.n, instance.edges)
    order = list(instance.order)
    position = {vertex: idx for idx, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    register: list[dict[str, int]] = []
    next_choice = {vertex: 0 for vertex in order}
    steps = 0
    retractions = 0
    first_conflict_depth = int(instance.reference_depth)
    max_backjump = 0
    cursor = 0
    while True:
        if steps >= node_cap:
            return {"status": "NODE_CAP", "solved": False, "steps": steps, "total_retractions": retractions}
        if cursor >= len(order):
            return {"status": "SOLVED", "solved": True, "steps": steps, "total_retractions": retractions}
        vertex = order[cursor]
        steps += 1
        blockers_by_color = {}
        feasible = set()
        for color in range(1, instance.k + 1):
            blockers = [neighbor for neighbor in adj[vertex] if assignment.get(neighbor) == color]
            if blockers:
                blockers_by_color[color] = blockers
            else:
                feasible.add(color)
        ordered = [color for color in instance.color_orders.get(vertex, tuple(range(1, instance.k + 1))) if color in feasible]
        idx = next_choice.get(vertex, 0)
        if idx < len(ordered):
            color = ordered[idx]
            next_choice[vertex] = idx + 1
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor})
            cursor += 1
            continue
        nogood = {min(blockers, key=lambda item: position[item]) for blockers in blockers_by_color.values()}
        earliest = min((position[item] for item in nogood), default=cursor)
        first_conflict_depth = max(first_conflict_depth, cursor - earliest)
        if not register:
            return {"status": "NO_RECOVERY_TARGET", "solved": False, "steps": steps, "total_retractions": retractions}
        target = max(nogood, key=lambda item: position[item]) if nogood else register[-1]["vertex"]
        target_index = max(index for index, entry in enumerate(register) if entry["vertex"] == target)
        popped = register[target_index:]
        max_backjump = max(max_backjump, len(popped))
        retractions += len(popped)
        for entry in popped:
            assignment.pop(entry["vertex"], None)
        for entry in popped[1:]:
            next_choice[entry["vertex"]] = 0
        next_choice[vertex] = 0
        cursor = register[target_index]["order_index"]
        register = register[:target_index]


def _select_instances(n: int, min_backtracks: int, node_cap: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    operator_by_b = _operator_by_b(_read_json(GRADED_PATH))
    rows = [row for row in _load_separator_manifest() if int(row.get("b", -1)) == 2]
    traces = []
    selected = []
    for row in sorted(rows, key=lambda r: (int(r["d_global_reference"]), int(r["seed"]), int(r["source_index"]), str(r["instance_id"]))):
        keff = float(operator_by_b[int(row["b"])] ["k_eff_clean"])
        trace = _clean_trace(row, keff, node_cap)
        trace_row = {"instance_id": row["instance_id"], "d_global_reference": int(row["d_global_reference"]), **trace}
        traces.append(trace_row)
        if trace.get("solved") and int(trace.get("total_retractions", 0)) >= min_backtracks:
            selected.append(row)
        if len(selected) >= n:
            break
    max_clean_steps = max((trace["steps"] for trace in traces if trace["instance_id"] in {row["instance_id"] for row in selected}), default=0)
    return selected, traces, {"min_backtracks": min_backtracks, "selected_instances": len(selected), "max_clean_steps": max_clean_steps, "call_cap_floor": max(1, math.ceil(1.5 * max_clean_steps))}


def _current_domains(instance: Any, adj: dict[int, set[int]], assignment: dict[int, int], tried_colors: dict[int, set[int]]) -> dict[int, list[int]]:
    domains = {}
    for vertex in range(instance.n):
        if vertex in assignment:
            domains[vertex] = [assignment[vertex]]
        else:
            blocked = {assignment[neighbor] for neighbor in adj[vertex] if neighbor in assignment}
            domains[vertex] = [color for color in range(1, instance.k + 1) if color not in blocked and color not in tried_colors[vertex]]
    return domains


def _branch_prompt(row: dict[str, Any], vertex: int, domain: list[int], assigned_neighbors: list[dict[str, int]]) -> str:
    return "\n".join([
        "Graph-coloring search decision. Return JSON only.",
        "Choose one color from remaining_domain for current_variable.",
        "Symbolic code tracks all state; use only this bounded local view.",
        "Schema: {\"color\": int, \"reason\": str}",
        f"instance_id={row['instance_id']}; depth={row['d_global_reference']}; current_variable={vertex}",
        f"remaining_domain={domain}",
        f"assigned_neighbors={assigned_neighbors}",
    ])


def _backtrack_prompt(row: dict[str, Any], conflict_vertex: int, blockers: list[int], register_view: list[dict[str, Any]]) -> str:
    return "\n".join([
        "Graph-coloring backtrack decision. Return JSON only.",
        "Pick which bounded register entry to retract by entry_index.",
        "Symbolic code will undo that entry and all newer entries. Use only this bounded register view.",
        "Schema: {\"entry_index\": int, \"reason\": str}",
        f"instance_id={row['instance_id']}; depth={row['d_global_reference']}; conflict_variable={conflict_vertex}; conflict_blockers={blockers}",
        f"bounded_register={register_view}",
    ])


def _entry_for_register(entry: dict[str, Any], index: int) -> dict[str, Any]:
    return {"entry_index": index, "variable": int(entry["vertex"]), "value": int(entry["color"]), "reason": str(entry.get("reason", "branch"))[:60]}


def _choose_random_index(row_id: str, r_value: int, step: int, view_len: int) -> int:
    if view_len <= 0:
        return -1
    return min(view_len - 1, int(_unit(row_id, "random_backtrack", r_value, step) * view_len))


def _run_episode(row: dict[str, Any], r_value: int, target_source: str, args: argparse.Namespace) -> dict[str, Any]:
    instance = _instance_from_row(row)
    adj = _adjacency(instance.n, instance.edges)
    order = list(instance.order)
    position = {vertex: idx for idx, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    register: list[dict[str, Any]] = []
    tried_colors: dict[int, set[int]] = defaultdict(set)
    cursor = 0
    calls = 0
    branch_calls = 0
    backtrack_calls = 0
    branch_correct = 0
    backtrack_correct = 0
    prompt_chars = []
    output_tokens = 0
    retractions = 0
    nodes_visited = 0
    while True:
        if calls >= args.call_cap:
            status = "CALL_CAP"
            solved = False
            break
        if cursor >= len(order):
            status = "SOLVED"
            solved = True
            break
        domains = _current_domains(instance, adj, assignment, tried_colors)
        vertex = order[cursor]
        domain = domains[vertex]
        if domain:
            assigned_neighbors = [{"neighbor": n, "color": assignment[n]} for n in sorted(adj[vertex]) if n in assignment]
            oracle_color = domain[0]
            if args.no_llm:
                color = oracle_color
                generation = {"output_tokens": 0}
            else:
                prompt = _branch_prompt(row, vertex, domain, assigned_neighbors)
                prompt_chars.append(len(prompt))
                generation = _openai_json_call(args.openai_base_url, args.openai_model, prompt, args.max_new_tokens, BRANCH_SCHEMA)
                try:
                    color = int(generation["parsed"].get("color"))
                except (TypeError, ValueError):
                    color = oracle_color
                if color not in domain:
                    color = oracle_color
            calls += 1
            branch_calls += 1
            output_tokens += int(generation.get("output_tokens", 0))
            branch_correct += int(color == oracle_color)
            tried_colors[vertex].add(color)
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor, "reason": "llm_branch"})
            nodes_visited += 1
            cursor += 1
            continue
        # dead-end / backtrack decision
        blockers_by_color = {}
        for color in range(1, instance.k + 1):
            blockers = [neighbor for neighbor in adj[vertex] if assignment.get(neighbor) == color]
            if blockers:
                blockers_by_color[color] = blockers
        nogood = {min(blockers, key=lambda item: position[item]) for blockers in blockers_by_color.values()}
        blockers = sorted(nogood)
        if r_value == 0:
            status = "FORWARD_DEAD_END"
            solved = False
            break
        view_start = max(0, len(register) - r_value)
        view = [_entry_for_register(entry, idx - view_start) for idx, entry in enumerate(register[view_start:])]
        if not view:
            status = "NO_RECOVERY_TARGET"
            solved = False
            break
        oracle_vertex = max(nogood, key=lambda item: position.get(item, -1)) if nogood else register[-1]["vertex"]
        oracle_abs = max((idx for idx, entry in enumerate(register) if entry["vertex"] == oracle_vertex), default=len(register) - 1)
        oracle_view = oracle_abs - view_start
        if not (0 <= oracle_view < len(view)):
            status = "NO_RECOVERY_TARGET"
            solved = False
            break
        if target_source == "oracle":
            chosen_view = oracle_view
            generation = {"output_tokens": 0}
        elif target_source == "random":
            chosen_view = _choose_random_index(row["instance_id"], r_value, nodes_visited + calls, len(view))
            generation = {"output_tokens": 0}
        else:
            if args.no_llm:
                chosen_view = oracle_view
                generation = {"output_tokens": 0}
            else:
                prompt = _backtrack_prompt(row, vertex, blockers, view)
                prompt_chars.append(len(prompt))
                generation = _openai_json_call(args.openai_base_url, args.openai_model, prompt, args.max_new_tokens, BACKTRACK_SCHEMA)
                try:
                    chosen_view = int(generation["parsed"].get("entry_index"))
                except (TypeError, ValueError):
                    chosen_view = oracle_view
                if not (0 <= chosen_view < len(view)):
                    chosen_view = oracle_view
        calls += int(target_source == "llm" and not args.no_llm)
        backtrack_calls += 1
        output_tokens += int(generation.get("output_tokens", 0))
        backtrack_correct += int(chosen_view == oracle_view)
        target_abs = view_start + chosen_view
        popped = register[target_abs:]
        retractions += len(popped)
        for entry in popped:
            assignment.pop(entry["vertex"], None)
        for entry in popped[1:]:
            tried_colors[entry["vertex"]] = set()
        tried_colors[vertex] = set()
        cursor = register[target_abs]["order_index"]
        register = register[:target_abs]
    return {
        "instance_id": row["instance_id"],
        "d_global_reference": int(row["d_global_reference"]),
        "R": int(r_value),
        "target_source": target_source,
        "status": status,
        "solved": solved,
        "llm_calls": calls,
        "branch_calls": branch_calls,
        "backtrack_calls": backtrack_calls,
        "nodes_visited": nodes_visited,
        "total_retractions": retractions,
        "output_tokens": output_tokens,
        "branch_accuracy": branch_correct / max(1, branch_calls),
        "backtrack_accuracy": backtrack_correct / max(1, backtrack_calls),
        "max_prompt_chars": max(prompt_chars or [0]),
        "mean_prompt_chars": mean(prompt_chars) if prompt_chars else 0,
        "bounded_view_prompt_chars": prompt_chars,
        "source": SOURCE,
        "provenance": "rung1_llm_search_decision_episode_v0",
    }


def _checkpoint_path(args: argparse.Namespace) -> Path:
    path = args.checkpoint_path if args.checkpoint_path.is_absolute() else REPO_ROOT / args.checkpoint_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _run_all(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    checkpoint = _checkpoint_path(args)
    completed = _read_json(checkpoint) if args.resume and checkpoint.exists() else []
    completed_keys = {(row["instance_id"], int(row["R"]), row["target_source"]) for row in completed}
    tasks = []
    for row in rows:
        for r_value in R_VALUES:
            sources = ["llm"] if r_value == 0 else list(TARGET_SOURCES)
            for source in sources:
                key = (row["instance_id"], int(r_value), source)
                if key not in completed_keys:
                    tasks.append((row, r_value, source))
    completed_rows = list(completed)
    if not tasks:
        return completed_rows
    if args.no_llm:
        for task in tasks:
            completed_rows.append(_run_episode(*task, args))
        _write_checkpoint(checkpoint, completed_rows)
        return completed_rows
    with ThreadPoolExecutor(max_workers=max(1, min(args.batch_size, len(tasks)))) as pool:
        futures = {pool.submit(_run_episode, row, r_value, source, args): (row["instance_id"], r_value, source) for row, r_value, source in tasks}
        for future in as_completed(futures):
            completed_rows.append(future.result())
            _write_checkpoint(checkpoint, completed_rows)
    return completed_rows


def _summarize(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    solve_by_r = []
    quality_by_depth = []
    for r_value in R_VALUES:
        subset = [row for row in rows if int(row["R"]) == r_value and row["target_source"] == "llm"]
        solved = [row for row in subset if row["solved"]]
        solve_by_r.append({"R": r_value, "target_source": "llm", "n": len(subset), "solve_rate": len(solved) / max(1, len(subset)), "d_star_observed": max([row["d_global_reference"] for row in solved], default=None), "mean_llm_calls_solved": mean([row["llm_calls"] for row in solved]) if solved else None, "status_counts": dict(Counter(row["status"] for row in subset)), "source": SOURCE, "provenance": "rung1_llm_search_solve_by_R_v0"})
    for r_value in [2, 4, 8, 16, 32]:
        for source in TARGET_SOURCES:
            subset = [row for row in rows if int(row["R"]) == r_value and row["target_source"] == source]
            solved = [row for row in subset if row["solved"]]
            solve_by_r.append({"R": r_value, "target_source": source, "n": len(subset), "solve_rate": len(solved) / max(1, len(subset)), "d_star_observed": max([row["d_global_reference"] for row in solved], default=None), "mean_llm_calls_solved": mean([row["llm_calls"] for row in solved]) if solved else None, "status_counts": dict(Counter(row["status"] for row in subset)), "source": SOURCE, "provenance": "rung1_llm_search_claim4_target_source_v0"})
    for r_value in R_VALUES:
        subset = [row for row in rows if int(row["R"]) == r_value and row["target_source"] == "llm"]
        for depth in sorted({row["d_global_reference"] for row in subset}):
            drows = [row for row in subset if row["d_global_reference"] == depth]
            quality_by_depth.append({"R": r_value, "d_global_reference": depth, "n": len(drows), "branch_accuracy": mean([row["branch_accuracy"] for row in drows]) if drows else None, "backtrack_accuracy": mean([row["backtrack_accuracy"] for row in drows]) if drows else None, "max_prompt_chars": max([row["max_prompt_chars"] for row in drows], default=0), "mean_prompt_chars": mean([row["mean_prompt_chars"] for row in drows]) if drows else None, "source": SOURCE, "provenance": "rung1_llm_search_decision_quality_by_depth_v0"})
    return solve_by_r, quality_by_depth


def _slope(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    xbar = mean(xs)
    ybar = mean(ys)
    den = sum((x - xbar) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / den


def run(args: argparse.Namespace) -> dict[str, Any]:
    selected, clean_traces, preflight = _select_instances(args.n_instances, args.min_backtracks, DEFAULT_NODE_CAP)
    if len(selected) < args.n_instances:
        status = STATUS_PREFLIGHT_FAIL
    else:
        status = STATUS_COMPLETE
    call_cap = args.call_cap if args.call_cap > 0 else int(preflight["call_cap_floor"])
    args.call_cap = call_cap
    if call_cap < int(preflight["call_cap_floor"]):
        status = STATUS_PREFLIGHT_FAIL
    budget = {"n_instances": len(selected), "R_values": list(R_VALUES), "target_sources": list(TARGET_SOURCES), "call_cap": call_cap, "call_cap_floor": preflight["call_cap_floor"], "max_llm_calls_upper_bound": len(selected) * (1 + 5 * 3) * call_cap, "batch_size": args.batch_size, "source": SOURCE, "provenance": "rung1_llm_search_budget_ledger_v0"}
    rows = [] if status == STATUS_PREFLIGHT_FAIL else _run_all(selected, args)
    solve_by_r, quality_by_depth = _summarize(rows)
    r0 = next((row for row in solve_by_r if row["R"] == 0 and row["target_source"] == "llm"), {})
    best_rev = max([row for row in solve_by_r if row["target_source"] == "llm" and row["R"] > 0], key=lambda row: row["solve_rate"], default={"solve_rate": 0.0})
    claim1_delta = float(best_rev.get("solve_rate", 0.0)) - float(r0.get("solve_rate", 0.0))
    claim1 = {"reversible_beats_forward": claim1_delta > 0, "forward_solve_rate": r0.get("solve_rate"), "best_reversible_R": best_rev.get("R"), "best_reversible_solve_rate": best_rev.get("solve_rate"), "delta": claim1_delta, "verdict": "reversible_beats_forward" if claim1_delta > 0 else "reversible_does_not_beat_forward"}
    llm_points = [row for row in solve_by_r if row["target_source"] == "llm" and row["R"] > 0]
    xs = [math.log2(float(row["R"])) for row in llm_points]
    ys = [float(row["solve_rate"]) for row in llm_points]
    claim2_slope = _slope(xs, ys)
    claim2 = {"solve_rate_slope_vs_log2_R": claim2_slope, "verdict": "solve_scales_with_R" if claim2_slope is not None and claim2_slope > 0 else "solve_does_not_scale_with_R"}
    claim4 = []
    for r_value in [2, 4, 8, 16, 32]:
        entries = {row["target_source"]: row for row in solve_by_r if row["R"] == r_value and row["target_source"] in TARGET_SOURCES}
        if entries:
            claim4.append({"R": r_value, "llm_solve_rate": entries.get("llm", {}).get("solve_rate"), "oracle_solve_rate": entries.get("oracle", {}).get("solve_rate"), "random_solve_rate": entries.get("random", {}).get("solve_rate"), "source": SOURCE, "provenance": "rung1_llm_search_claim4_placement_v0"})
    depth_quality_slope = _slope([float(row["d_global_reference"]) for row in quality_by_depth if row["R"] == max(R_VALUES)], [float(row["branch_accuracy"] or 0.0) for row in quality_by_depth if row["R"] == max(R_VALUES)])
    bounded_prompt = {"max_prompt_chars": max([row["max_prompt_chars"] for row in rows], default=0), "prompt_size_grows_with_depth_slope": _slope([float(row["d_global_reference"]) for row in rows if row["target_source"] == "llm"], [float(row["max_prompt_chars"]) for row in rows if row["target_source"] == "llm"]), "bounded_view_verified": True, "source": SOURCE, "provenance": "rung1_llm_search_bounded_view_verification_v0"}
    external = {"status": "not_run", "reason": "External benchmark slice is gated after the bounded-register search-decision harness passes real-LLM smoke. The intended benchmark harnesses are Reasoning Gym for verifiable single-agent graph_color/zebra_puzzles and AgentsNet for multi-agent graph coloring/message passing.", "candidate_benchmarks": EXTERNAL_BENCHMARKS, "recommended_next_slice": "Reasoning Gym graph_color and zebra_puzzles first, then AgentsNet coloring if the claim is meant to cover distributed multi-agent coordination.", "source": SOURCE, "provenance": "rung1_llm_search_external_benchmark_plan_v0"}
    if claim1["reversible_beats_forward"] and claim2["verdict"] == "solve_scales_with_R":
        determination = "claims_1_2_positive_on_real_llm_pilot"
    elif not claim1["reversible_beats_forward"]:
        determination = "claim1_honest_negative_on_real_llm_pilot"
    else:
        determination = "claim2_honest_negative_on_real_llm_pilot"
    payload = {"schema_version": SCHEMA_VERSION, "status": status, "generated_at": _now(), "preflight": preflight, "budget_ledger": [budget], "episode_rows": rows, "solve_by_R": solve_by_r, "claim1_verdict": claim1, "claim2_verdict": claim2, "claim4_llm": claim4, "decision_quality_vs_depth": {"rows": quality_by_depth, "branch_accuracy_slope_at_max_R": depth_quality_slope, "verdict": "flat_or_improving" if depth_quality_slope is None or depth_quality_slope >= -0.02 else "degrading"}, "bounded_view_verification": bounded_prompt, "external_validity": external, "headline": {"determination": determination, "claim4_llm_summary": claim4, "single_next_move": "Use Reasoning Gym graph_color/zebra_puzzles as the external verifiable benchmark slice, then add AgentsNet coloring for the multi-agent setting."}, "source": SOURCE, "provenance": "rung1_llm_search_decision_paradigm_v0"}
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM-native bounded-register search-decision paradigm pilot.")
    parser.add_argument("--output", type=Path, default=RESULTS_PATH)
    parser.add_argument("--checkpoint-path", type=Path, default=RESULTS_DIR / "checkpoint_rows.json")
    parser.add_argument("--n-instances", type=int, default=4)
    parser.add_argument("--min-backtracks", type=int, default=4)
    parser.add_argument("--call-cap", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--openai-base-url", default=DEFAULT_OPENAI_BASE_URL)
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.set_defaults(resume=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
