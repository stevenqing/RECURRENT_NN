"""Reasoning Gym official-harness bounded-register search-decision pilot."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from statistics import mean
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_fallible_1d_rerun import _read_json, _write_checkpoint
from experiments.rung1_separator_llm_inloop import DEFAULT_OPENAI_BASE_URL, DEFAULT_OPENAI_MODEL


RESULTS_DIR = REPO_ROOT / "results/rung1_reasoning_gym_bounded_register"
RESULTS_PATH = RESULTS_DIR / "results.json"
SCHEMA_VERSION = "rung1_reasoning_gym_bounded_register_v0"
STATUS_COMPLETE = "RUNG1_REASONING_GYM_BOUNDED_REGISTER_COMPLETE"
STATUS_PREFLIGHT_FAIL = "RUNG1_REASONING_GYM_BOUNDED_REGISTER_PREFLIGHT_FAIL"
R_VALUES = (0, 2, 4, 8, 16, 32)
TARGET_SOURCES = ("llm", "oracle", "random")
BRANCH_SCHEMA = {"type": "object", "properties": {"color": {"type": "integer"}, "reason": {"type": "string"}}, "required": ["color"]}
BACKTRACK_SCHEMA = {"type": "object", "properties": {"entry_index": {"type": "integer"}, "reason": {"type": "string"}}, "required": ["entry_index"]}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _ensure_reasoning_gym(repo_path: str | None) -> Any:
    if repo_path:
        candidate = Path(repo_path)
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    fallback = Path("/tmp/reasoning_benchmarks/reasoning-gym")
    if fallback.exists() and str(fallback) not in sys.path:
        sys.path.insert(0, str(fallback))
    import reasoning_gym

    return reasoning_gym


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
    usage = decoded.get("usage", {}) or {}
    return {
        "text": text,
        "parsed": parsed,
        "finish_reason": choice.get("finish_reason"),
        "output_tokens": int(usage.get("completion_tokens") or 0),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }


def _openai_text_call(base_url: str, model: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": max_tokens}
    request = Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=3600) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"OpenAI-compatible request failed: {exc}") from exc
    choice = decoded.get("choices", [{}])[0]
    usage = decoded.get("usage", {}) or {}
    return {
        "text": choice.get("message", {}).get("content", ""),
        "finish_reason": choice.get("finish_reason"),
        "output_tokens": int(usage.get("completion_tokens") or 0),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }


def _graph_color_view(entry: dict[str, Any], order_mode: str) -> dict[str, Any]:
    puzzle = entry["metadata"]["puzzle"]
    vertices = [int(vertex) for vertex in puzzle["vertices"]]
    edges = [tuple(map(int, edge)) for edge in puzzle["edges"]]
    adjacency = {vertex: set() for vertex in vertices}
    for left, right in edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    if order_mode == "degree_desc":
        order = sorted(vertices, key=lambda vertex: (-len(adjacency[vertex]), vertex))
    else:
        order = list(vertices)
    return {"vertices": vertices, "edges": edges, "adjacency": adjacency, "order": order, "num_colors": int(puzzle["num_colors"]), "color_options": [int(color) for color in puzzle["color_options"]]}


def _official_answer(assignment: dict[int, int]) -> str:
    return json.dumps({str(vertex): int(color) for vertex, color in sorted(assignment.items())}, sort_keys=True)


def _official_score(dataset: Any, entry: dict[str, Any], assignment: dict[int, int]) -> float:
    return float(dataset.score_answer(_official_answer(assignment), entry))


def _current_domain(view: dict[str, Any], vertex: int, assignment: dict[int, int], tried_colors: dict[int, set[int]]) -> list[int]:
    if vertex in assignment:
        return [assignment[vertex]]
    blocked = {assignment[neighbor] for neighbor in view["adjacency"][vertex] if neighbor in assignment}
    return [color for color in view["color_options"] if color not in blocked and color not in tried_colors[vertex]]


def _deadend_nogood(view: dict[str, Any], vertex: int, assignment: dict[int, int], position: dict[int, int]) -> set[int]:
    nogood = []
    for color in view["color_options"]:
        blockers = [neighbor for neighbor in view["adjacency"][vertex] if assignment.get(neighbor) == color]
        if blockers:
            nogood.append(min(blockers, key=lambda item: position[item]))
    return set(nogood)


def _clean_trace(entry: dict[str, Any], order_mode: str, node_cap: int, dataset: Any) -> dict[str, Any]:
    view = _graph_color_view(entry, order_mode)
    position = {vertex: index for index, vertex in enumerate(view["order"])}
    assignment: dict[int, int] = {}
    tried_colors: dict[int, set[int]] = defaultdict(set)
    register: list[dict[str, Any]] = []
    cursor = 0
    steps = 0
    retractions = 0
    max_register_len = 0
    while True:
        if steps >= node_cap:
            return {"status": "NODE_CAP", "solved": False, "official_score": 0.0, "steps": steps, "total_retractions": retractions, "max_register_len": max_register_len}
        if cursor >= len(view["order"]):
            score = _official_score(dataset, entry, assignment)
            return {"status": "SOLVED" if score >= 1.0 else "OFFICIAL_SCORE_FAIL", "solved": score >= 1.0, "official_score": score, "steps": steps, "total_retractions": retractions, "max_register_len": max_register_len}
        vertex = view["order"][cursor]
        domain = _current_domain(view, vertex, assignment, tried_colors)
        steps += 1
        if domain:
            color = domain[0]
            tried_colors[vertex].add(color)
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor})
            max_register_len = max(max_register_len, len(register))
            cursor += 1
            continue
        if not register:
            return {"status": "NO_RECOVERY_TARGET", "solved": False, "official_score": 0.0, "steps": steps, "total_retractions": retractions, "max_register_len": max_register_len}
        nogood = _deadend_nogood(view, vertex, assignment, position)
        target_vertex = max(nogood, key=lambda item: position[item]) if nogood else register[-1]["vertex"]
        target_index = max((index for index, item in enumerate(register) if item["vertex"] == target_vertex), default=len(register) - 1)
        popped = register[target_index:]
        retractions += len(popped)
        for item in popped:
            assignment.pop(int(item["vertex"]), None)
        for item in popped[1:]:
            tried_colors[int(item["vertex"])] = set()
        tried_colors[vertex] = set()
        cursor = int(register[target_index]["order_index"])
        register = register[:target_index]


def _make_dataset(args: argparse.Namespace) -> Any:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    if args.dataset != "graph_color":
        raise NotImplementedError("This first official-harness runner supports graph_color. Zebra CSP encoding is the next slice.")
    return reasoning_gym.create_dataset(
        "graph_color",
        size=args.scan_limit,
        seed=args.seed,
        num_colors=args.num_colors,
        min_num_vertices=args.num_vertices,
        max_num_vertices=args.num_vertices,
        edge_probability=args.edge_probability,
    )


def _select_entries(dataset: Any, args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    selected = []
    traces = []
    for index in range(args.scan_limit):
        entry = dataset[index]
        trace = _clean_trace(entry, args.order_mode, args.node_cap, dataset)
        trace_row = {"source_index": index, "source_dataset": entry["metadata"].get("source_dataset"), "difficulty": entry["metadata"].get("difficulty"), **trace}
        traces.append(trace_row)
        if trace.get("solved") and int(trace.get("total_retractions", 0)) >= args.min_backtracks:
            selected.append({"entry": entry, "source_index": index, "trace": trace})
        if len(selected) >= args.n_instances:
            break
    max_steps = max((int(row["trace"]["steps"]) for row in selected), default=0)
    return selected, traces, {"dataset": args.dataset, "scan_limit": args.scan_limit, "selected_instances": len(selected), "min_backtracks": args.min_backtracks, "max_clean_steps": max_steps, "call_cap_floor": max(1, int(1.5 * max_steps + 0.999)), "order_mode": args.order_mode, "official_scoring": "dataset.score_answer(answer, entry)"}


def _branch_prompt(entry: dict[str, Any], vertex: int, domain: list[int], assigned_neighbors: list[dict[str, int]]) -> str:
    return "\n".join([
        "Reasoning Gym graph_color bounded-register search decision. Return JSON only.",
        "Choose one color from remaining_domain for current_variable.",
        "The symbolic search code owns state, propagation, conflict detection, and final score_answer validation.",
        "Use only this bounded local view.",
        "Schema: {\"color\": int, \"reason\": str}",
        f"source_index={entry['metadata'].get('source_index')}; current_variable={vertex}",
        f"remaining_domain={domain}",
        f"assigned_neighbors={assigned_neighbors}",
    ])


def _backtrack_prompt(entry: dict[str, Any], conflict_vertex: int, blockers: list[int], register_view: list[dict[str, Any]]) -> str:
    return "\n".join([
        "Reasoning Gym graph_color bounded-register backtrack decision. Return JSON only.",
        "Pick which bounded register entry to retract by entry_index.",
        "The symbolic search code will undo that entry and all newer entries, then continue search.",
        "Use only this bounded register view.",
        "Schema: {\"entry_index\": int, \"reason\": str}",
        f"source_index={entry['metadata'].get('source_index')}; conflict_variable={conflict_vertex}; conflict_blockers={blockers}",
        f"bounded_register={register_view}",
    ])


def _entry_for_register(entry: dict[str, Any], index: int) -> dict[str, Any]:
    return {"entry_index": index, "variable": int(entry["vertex"]), "value": int(entry["color"])}


def _choose_random_index(row_id: str, r_value: int, step: int, view_len: int) -> int:
    if view_len <= 0:
        return -1
    return min(view_len - 1, int(_unit(row_id, "rg_random_backtrack", r_value, step) * view_len))


def _run_one_shot(dataset: Any, entry: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if args.no_llm:
        possible = entry["metadata"].get("possible_answer")
        answer = json.dumps(possible, sort_keys=True) if possible is not None else str(entry.get("answer", ""))
        return {"answer": answer, "official_score": float(dataset.score_answer(answer, entry)), "llm_calls": 0, "output_tokens": 0, "prompt_tokens": 0, "total_tokens": 0, "mode": "oracle_no_llm", "source": SOURCE, "provenance": "rg_one_shot_baseline_v0"}
    prompt = entry["question"]
    if args.one_shot_cot:
        prompt += "\nThink privately if needed, then provide the final answer in the requested format."
    generation = _openai_text_call(args.openai_base_url, args.openai_model, prompt, args.one_shot_max_tokens)
    text = generation["text"]
    score = float(dataset.score_answer(text, entry))
    return {
        "answer": text,
        "official_score": score,
        "llm_calls": 1,
        "output_tokens": generation.get("output_tokens", 0),
        "prompt_tokens": generation.get("prompt_tokens", 0),
        "total_tokens": generation.get("total_tokens", 0),
        "finish_reason": generation.get("finish_reason"),
        "mode": "one_shot_cot" if args.one_shot_cot else "one_shot",
        "source": SOURCE,
        "provenance": "rg_one_shot_baseline_v0",
    }


def _run_episode(dataset: Any, selected: dict[str, Any], r_value: int, target_source: str, args: argparse.Namespace) -> dict[str, Any]:
    entry = selected["entry"]
    row_id = f"rg_{args.dataset}_{selected['source_index']}"
    view = _graph_color_view(entry, args.order_mode)
    position = {vertex: index for index, vertex in enumerate(view["order"])}
    assignment: dict[int, int] = {}
    tried_colors: dict[int, set[int]] = defaultdict(set)
    register: list[dict[str, Any]] = []
    cursor = 0
    decision_calls = 0
    llm_calls = 0
    branch_calls = 0
    backtrack_calls = 0
    branch_correct = 0
    backtrack_correct = 0
    parseable_decisions = 0
    valid_decisions = 0
    prompt_chars = []
    register_view_lens = []
    assigned_neighbor_lens = []
    output_tokens = 0
    prompt_tokens = 0
    total_tokens = 0
    retractions = 0
    nodes_visited = 0
    while True:
        if decision_calls >= args.call_cap:
            status = "CALL_CAP"
            official_score = 0.0
            solved = False
            break
        if cursor >= len(view["order"]):
            official_score = _official_score(dataset, entry, assignment)
            status = "SOLVED" if official_score >= 1.0 else "OFFICIAL_SCORE_FAIL"
            solved = official_score >= 1.0
            break
        vertex = view["order"][cursor]
        domain = _current_domain(view, vertex, assignment, tried_colors)
        if domain:
            assigned_neighbors = [{"neighbor": neighbor, "color": assignment[neighbor]} for neighbor in sorted(view["adjacency"][vertex]) if neighbor in assignment]
            assigned_neighbor_lens.append(len(assigned_neighbors))
            oracle_color = domain[0]
            if args.no_llm:
                color = oracle_color
                generation = {"output_tokens": 0}
            else:
                prompt = _branch_prompt(entry, vertex, domain, assigned_neighbors)
                prompt_chars.append(len(prompt))
                generation = _openai_json_call(args.openai_base_url, args.openai_model, prompt, args.max_new_tokens, BRANCH_SCHEMA)
                try:
                    color = int(generation["parsed"].get("color"))
                    parseable_decisions += 1
                except (TypeError, ValueError):
                    color = oracle_color
                if color not in domain:
                    color = oracle_color
                else:
                    valid_decisions += 1
                llm_calls += 1
            decision_calls += 1
            branch_calls += 1
            output_tokens += int(generation.get("output_tokens", 0))
            prompt_tokens += int(generation.get("prompt_tokens", 0))
            total_tokens += int(generation.get("total_tokens", 0))
            branch_correct += int(color == oracle_color)
            tried_colors[vertex].add(color)
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor})
            nodes_visited += 1
            cursor += 1
            continue
        if r_value == 0:
            status = "FORWARD_DEAD_END"
            official_score = 0.0
            solved = False
            break
        if not register:
            status = "NO_RECOVERY_TARGET"
            official_score = 0.0
            solved = False
            break
        nogood = _deadend_nogood(view, vertex, assignment, position)
        blockers = sorted(nogood)
        oracle_vertex = max(nogood, key=lambda item: position[item]) if nogood else register[-1]["vertex"]
        oracle_abs = max((idx for idx, item in enumerate(register) if item["vertex"] == oracle_vertex), default=len(register) - 1)
        view_start = max(0, len(register) - r_value)
        bounded_view = [_entry_for_register(item, index - view_start) for index, item in enumerate(register[view_start:])]
        register_view_lens.append(len(bounded_view))
        oracle_view = oracle_abs - view_start
        if not (0 <= oracle_view < len(bounded_view)):
            status = "NO_RECOVERY_TARGET"
            official_score = 0.0
            solved = False
            break
        if target_source == "oracle" or (target_source == "llm" and args.no_llm):
            chosen_view = oracle_view
            generation = {"output_tokens": 0}
        elif target_source == "random":
            chosen_view = _choose_random_index(row_id, r_value, decision_calls, len(bounded_view))
            generation = {"output_tokens": 0}
        else:
            prompt = _backtrack_prompt(entry, vertex, blockers, bounded_view)
            prompt_chars.append(len(prompt))
            generation = _openai_json_call(args.openai_base_url, args.openai_model, prompt, args.max_new_tokens, BACKTRACK_SCHEMA)
            try:
                chosen_view = int(generation["parsed"].get("entry_index"))
                parseable_decisions += 1
            except (TypeError, ValueError):
                chosen_view = oracle_view
            if not (0 <= chosen_view < len(bounded_view)):
                chosen_view = oracle_view
            else:
                valid_decisions += 1
            llm_calls += 1
        decision_calls += 1
        backtrack_calls += 1
        output_tokens += int(generation.get("output_tokens", 0))
        prompt_tokens += int(generation.get("prompt_tokens", 0))
        total_tokens += int(generation.get("total_tokens", 0))
        backtrack_correct += int(chosen_view == oracle_view)
        target_abs = view_start + chosen_view
        popped = register[target_abs:]
        retractions += len(popped)
        for item in popped:
            assignment.pop(int(item["vertex"]), None)
        for item in popped[1:]:
            tried_colors[int(item["vertex"])] = set()
        tried_colors[vertex] = set()
        cursor = int(register[target_abs]["order_index"])
        register = register[:target_abs]
    return {
        "source_index": int(selected["source_index"]),
        "source_dataset": entry["metadata"].get("source_dataset"),
        "R": int(r_value),
        "target_source": target_source,
        "status": status,
        "official_score": official_score,
        "solved": solved,
        "decision_calls": decision_calls,
        "llm_calls": llm_calls,
        "branch_calls": branch_calls,
        "backtrack_calls": backtrack_calls,
        "parseable_decisions": parseable_decisions,
        "valid_decisions": valid_decisions,
        "parseable_rate": parseable_decisions / max(1, llm_calls),
        "valid_decision_rate": valid_decisions / max(1, llm_calls),
        "nodes_visited": nodes_visited,
        "total_retractions": retractions,
        "output_tokens": output_tokens,
        "prompt_tokens": prompt_tokens,
        "total_tokens": total_tokens,
        "branch_accuracy_vs_oracle": branch_correct / max(1, branch_calls),
        "backtrack_accuracy_vs_oracle": backtrack_correct / max(1, backtrack_calls),
        "max_prompt_chars": max(prompt_chars or [0]),
        "mean_prompt_chars": mean(prompt_chars) if prompt_chars else 0,
        "bounded_view_prompt_chars": prompt_chars,
        "max_register_view_len": max(register_view_lens or [0]),
        "max_assigned_neighbors_in_prompt": max(assigned_neighbor_lens or [0]),
        "answer": _official_answer(assignment) if solved else None,
        "source": SOURCE,
        "provenance": "rg_bounded_register_episode_v0",
    }


def _checkpoint_path(args: argparse.Namespace) -> Path:
    path = args.checkpoint_path if args.checkpoint_path.is_absolute() else REPO_ROOT / args.checkpoint_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _run_r_values(args: argparse.Namespace) -> list[int]:
    if isinstance(args.r_values, str):
        return [int(item) for item in args.r_values.split(",") if item.strip()]
    return list(args.r_values)


def _target_sources_for_r(r_value: int, args: argparse.Namespace) -> list[str]:
    if r_value == 0:
        return ["llm"]
    if args.claim4_r > 0 and r_value != args.claim4_r:
        return ["llm"]
    return list(TARGET_SOURCES)


def _run_all(dataset: Any, selected: list[dict[str, Any]], args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    checkpoint = _checkpoint_path(args)
    completed = _read_json(checkpoint) if args.resume and checkpoint.exists() else []
    completed_keys = {(row.get("kind", "episode"), int(row["source_index"]), int(row.get("R", -1)), row.get("target_source", "")) for row in completed}
    tasks = []
    one_shot_rows = [row for row in completed if row.get("kind") == "one_shot"]
    episode_rows = [row for row in completed if row.get("kind", "episode") == "episode"]
    for item in selected:
        if ("one_shot", int(item["source_index"]), -1, "") not in completed_keys:
            tasks.append(("one_shot", item, None, None))
        for r_value in _run_r_values(args):
            for target_source in _target_sources_for_r(r_value, args):
                if ("episode", int(item["source_index"]), int(r_value), target_source) not in completed_keys:
                    tasks.append(("episode", item, r_value, target_source))
    if args.no_llm:
        rows = list(completed)
        for kind, item, r_value, target_source in tasks:
            if kind == "one_shot":
                row = _run_one_shot(dataset, item["entry"], args) | {"kind": "one_shot", "source_index": int(item["source_index"])}
                one_shot_rows.append(row)
            else:
                row = _run_episode(dataset, item, int(r_value), str(target_source), args) | {"kind": "episode"}
                episode_rows.append(row)
            rows.append(row)
        _write_checkpoint(checkpoint, rows)
        return one_shot_rows, episode_rows
    rows = list(completed)
    with ThreadPoolExecutor(max_workers=max(1, min(args.batch_size, len(tasks)))) as pool:
        futures = {}
        for kind, item, r_value, target_source in tasks:
            if kind == "one_shot":
                futures[pool.submit(_run_one_shot, dataset, item["entry"], args)] = (kind, item, r_value, target_source)
            else:
                futures[pool.submit(_run_episode, dataset, item, int(r_value), str(target_source), args)] = (kind, item, r_value, target_source)
        for future in as_completed(futures):
            kind, item, r_value, target_source = futures[future]
            row = future.result()
            if kind == "one_shot":
                row |= {"kind": "one_shot", "source_index": int(item["source_index"])}
                one_shot_rows.append(row)
            else:
                row |= {"kind": "episode"}
                episode_rows.append(row)
            rows.append(row)
            _write_checkpoint(checkpoint, rows)
    return one_shot_rows, episode_rows


def _slope(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    xbar = mean(xs)
    ybar = mean(ys)
    den = sum((x - xbar) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / den


def _summarize(one_shot_rows: list[dict[str, Any]], episode_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    solve_by_r = []
    baseline = {"n": len(one_shot_rows), "solve_rate": mean([float(row.get("official_score", 0.0) >= 1.0) for row in one_shot_rows]) if one_shot_rows else None, "mean_official_score": mean([float(row.get("official_score", 0.0)) for row in one_shot_rows]) if one_shot_rows else None, "source": SOURCE, "provenance": "rg_one_shot_summary_v0"}
    for r_value in sorted({int(row["R"]) for row in episode_rows if row.get("target_source") == "llm"}):
        subset = [row for row in episode_rows if int(row["R"]) == r_value and row["target_source"] == "llm"]
        solve_by_r.append({"R": r_value, "target_source": "llm", "n": len(subset), "solve_rate": mean([float(row["official_score"] >= 1.0) for row in subset]) if subset else 0.0, "mean_official_score": mean([float(row["official_score"]) for row in subset]) if subset else None, "mean_decision_calls_solved": mean([row["decision_calls"] for row in subset if row["official_score"] >= 1.0]) if any(row["official_score"] >= 1.0 for row in subset) else None, "status_counts": dict(Counter(row["status"] for row in subset)), "source": SOURCE, "provenance": "rg_bounded_register_solve_by_R_v0"})
    for r_value in sorted({int(row["R"]) for row in episode_rows if int(row.get("R", 0)) > 0}):
        for target_source in TARGET_SOURCES:
            subset = [row for row in episode_rows if int(row["R"]) == r_value and row["target_source"] == target_source]
            solve_by_r.append({"R": r_value, "target_source": target_source, "n": len(subset), "solve_rate": mean([float(row["official_score"] >= 1.0) for row in subset]) if subset else 0.0, "mean_official_score": mean([float(row["official_score"]) for row in subset]) if subset else None, "status_counts": dict(Counter(row["status"] for row in subset)), "source": SOURCE, "provenance": "rg_bounded_register_target_source_v0"})
    return solve_by_r, baseline


def run(args: argparse.Namespace) -> dict[str, Any]:
    dataset = _make_dataset(args)
    selected, traces, preflight = _select_entries(dataset, args)
    status = STATUS_COMPLETE if len(selected) >= args.n_instances else STATUS_PREFLIGHT_FAIL
    args.call_cap = args.call_cap if args.call_cap > 0 else int(preflight["call_cap_floor"])
    if args.call_cap < int(preflight["call_cap_floor"]):
        status = STATUS_PREFLIGHT_FAIL
    r_values = _run_r_values(args)
    per_instance_episode_count = sum(len(_target_sources_for_r(r_value, args)) for r_value in r_values)
    budget = {"dataset": args.dataset, "n_instances": len(selected), "scan_limit": args.scan_limit, "R_values": r_values, "claim4_r": args.claim4_r, "target_sources": list(TARGET_SOURCES), "call_cap": args.call_cap, "call_cap_floor": preflight["call_cap_floor"], "max_llm_calls_upper_bound": len(selected) * per_instance_episode_count * args.call_cap + len(selected), "batch_size": args.batch_size, "source": SOURCE, "provenance": "rg_bounded_register_budget_v0"}
    one_shot_rows: list[dict[str, Any]] = []
    episode_rows: list[dict[str, Any]] = []
    if status != STATUS_PREFLIGHT_FAIL:
        one_shot_rows, episode_rows = _run_all(dataset, selected, args)
    solve_by_r, one_shot_baseline = _summarize(one_shot_rows, episode_rows)
    r0 = next((row for row in solve_by_r if row["R"] == 0 and row["target_source"] == "llm"), {})
    reversible = [row for row in solve_by_r if row["target_source"] == "llm" and row["R"] > 0]
    best_rev = max(reversible, key=lambda row: row["solve_rate"], default={"solve_rate": 0.0, "R": None})
    claim1_delta = float(best_rev.get("solve_rate", 0.0)) - float(r0.get("solve_rate", 0.0))
    xs = [math.log2(float(row["R"])) for row in reversible if row["R"]]
    ys = [float(row["solve_rate"]) for row in reversible if row["R"]]
    claim2_slope = _slope(xs, ys)
    prompt_slope = _slope([float(row["decision_calls"]) for row in episode_rows if row["target_source"] == "llm"], [float(row["max_prompt_chars"]) for row in episode_rows if row["target_source"] == "llm"])
    register_view_ok = all(int(row.get("max_register_view_len", 0)) <= int(row.get("R", 0)) for row in episode_rows if int(row.get("R", 0)) > 0)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "generated_at": _now(),
        "dataset_config": {"dataset": args.dataset, "seed": args.seed, "num_vertices": args.num_vertices, "num_colors": args.num_colors, "edge_probability": args.edge_probability, "order_mode": args.order_mode, "official_instance_source": "reasoning_gym.create_dataset", "official_scoring": "dataset.score_answer(answer, entry)", "source": SOURCE, "provenance": "rg_bounded_register_dataset_config_v0"},
        "preflight": preflight,
        "budget_ledger": [budget],
        "one_shot_baseline": one_shot_baseline,
        "one_shot_rows": one_shot_rows,
        "episode_rows": episode_rows,
        "solve_by_R": solve_by_r,
        "claim1_verdict": {"reversible_beats_forward": claim1_delta > 0, "forward_R0_solve_rate": r0.get("solve_rate"), "best_reversible_R": best_rev.get("R"), "best_reversible_solve_rate": best_rev.get("solve_rate"), "delta": claim1_delta, "kill_if_false": "reversible_not_beating_forward_fails_claim1", "source": SOURCE, "provenance": "rg_bounded_register_claim1_v0"},
        "claim2_verdict": {"solve_rate_slope_vs_log2_R": claim2_slope, "scales_with_R": claim2_slope is not None and claim2_slope > 0, "kill_if_false": "no_R_scaling_fails_claim2", "source": SOURCE, "provenance": "rg_bounded_register_claim2_v0"},
        "claim4_llm": [{"R": r_value, "llm_solve_rate": next((row["solve_rate"] for row in solve_by_r if row["R"] == r_value and row["target_source"] == "llm"), None), "oracle_solve_rate": next((row["solve_rate"] for row in solve_by_r if row["R"] == r_value and row["target_source"] == "oracle"), None), "random_solve_rate": next((row["solve_rate"] for row in solve_by_r if row["R"] == r_value and row["target_source"] == "random"), None), "kill_if_llm_near_random": "LLM target selection cap if llm approximates random", "source": SOURCE, "provenance": "rg_bounded_register_claim4_v0"} for r_value in r_values if r_value > 0],
        "bounded_view_verification": {"bounded_view_verified": register_view_ok, "max_prompt_chars": max([row["max_prompt_chars"] for row in episode_rows], default=0), "prompt_size_slope_vs_decision_calls_diagnostic": prompt_slope, "max_register_view_len": max([row.get("max_register_view_len", 0) for row in episode_rows], default=0), "max_assigned_neighbors_in_prompt": max([row.get("max_assigned_neighbors_in_prompt", 0) for row in episode_rows], default=0), "view_contract": "current frontier plus local assigned neighbors plus register view of size <= R; final scoring delegated to Reasoning Gym score_answer", "source": SOURCE, "provenance": "rg_bounded_view_verification_v1"},
        "guards": {"call_cap_floor_respected": args.call_cap >= int(preflight["call_cap_floor"]), "instances_require_backtracking": len(selected) >= args.n_instances and all(int(item["trace"].get("total_retractions", 0)) >= args.min_backtracks for item in selected), "official_score_only_for_solve_validation": True, "zebra_status": "not_in_this_first_runner; graph_color first per addendum", "agentsnet_status": "deferred_until_single_agent_reasoning_gym_lands", "source": SOURCE, "provenance": "rg_bounded_register_guards_v0"},
        "source": SOURCE,
        "provenance": "rung1_reasoning_gym_bounded_register_v0",
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the bounded-register search-decision paradigm on official Reasoning Gym graph_color instances.")
    parser.add_argument("--output", type=Path, default=RESULTS_PATH)
    parser.add_argument("--checkpoint-path", type=Path, default=RESULTS_DIR / "checkpoint_rows.json")
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--dataset", default="graph_color", choices=["graph_color"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scan-limit", type=int, default=200)
    parser.add_argument("--n-instances", type=int, default=4)
    parser.add_argument("--min-backtracks", type=int, default=4)
    parser.add_argument("--node-cap", type=int, default=1000)
    parser.add_argument("--num-vertices", type=int, default=16)
    parser.add_argument("--num-colors", type=int, default=4)
    parser.add_argument("--edge-probability", type=float, default=0.22)
    parser.add_argument("--order-mode", default="degree_desc", choices=["degree_desc", "natural"])
    parser.add_argument("--call-cap", type=int, default=0)
    parser.add_argument("--r-values", default="0,2,4,8,16")
    parser.add_argument("--claim4-r", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--one-shot-max-tokens", type=int, default=4096)
    parser.add_argument("--one-shot-cot", action="store_true")
    parser.add_argument("--openai-base-url", default=DEFAULT_OPENAI_BASE_URL)
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.set_defaults(resume=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
