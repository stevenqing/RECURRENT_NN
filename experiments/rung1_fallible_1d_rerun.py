"""Decisive fallible 1D rerun batch.

Emits ``rung1_fallible_1d_rerun_v0``.  The hard preflight gate is enforced before
real LLM launch: ``call_cap`` must be strictly greater than ``max(register D)``.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from statistics import mean
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _adjacency, _rel
from experiments.rung1_separator_item062_execution import _competence_episodes
from experiments.rung1_separator_llm_inloop import (
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    InLoopEpisode,
    _advance_without_generation,
    _apply_generation,
    _generate_prompts,
    _initial_domains,
    _load_separator_manifest,
    _live_domain,
    _prompt_for_inloop_episode,
    _row_for_episode,
)
from experiments.rung1_separator_p1b_full_table import GRADED_PATH, _operator_by_b
from experiments.rung1_separator_p1b_full_table_controlled_v1 import _interpolate_dstar
from experiments.rung1_separator_p1c_truncation_pilot import OPERATOR_VERSION_V2, _prompt_for_operator
from experiments.rung1_separator_scaling import DEFAULT_NODE_CAP, _instance_from_row


RESULTS_DIR = REPO_ROOT / "results/rung1_fallible_1d_rerun"
RESULTS_PATH = RESULTS_DIR / "results.json"
SCHEMA_VERSION = "rung1_fallible_1d_rerun_v0"
STATUS_COMPLETE = "RUNG1_FALLIBLE_1D_RERUN_COMPLETE"
STATUS_PREFLIGHT_FAIL = "RUNG1_FALLIBLE_1D_RERUN_PREFLIGHT_FAIL"
PIECE1_D = (12, 16, 24, 32)
PIECE1_DEPTHS = (4, 5, 6, 7, 9, 10)
PIECE3_B = (4, 8, 12)
PIECE3_D = (40, 50, 64, 80, 100)
PIECE3_DEPTHS = (4, 5, 6, 7, 9, 10, 12)
FUNCTIONAL_GATE_THRESHOLD = 0.20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _checkpoint_dir(args: argparse.Namespace) -> Path:
    path = args.checkpoint_dir if args.checkpoint_dir.is_absolute() else REPO_ROOT / args.checkpoint_dir
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_checkpoint(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_checkpoint(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return _read_json(path)


def _episode_key(ep: InLoopEpisode) -> str:
    return f"D{int(ep.register_capacity_D)}::{ep.row['instance_id']}"


def _domains_to_json(domains: dict[int, set[int]]) -> dict[str, list[int]]:
    return {str(int(vertex)): sorted(int(color) for color in colors) for vertex, colors in domains.items()}


def _domains_from_json(domains: dict[str, list[int]]) -> dict[int, set[int]]:
    return {int(vertex): {int(color) for color in colors} for vertex, colors in domains.items()}


def _register_to_json(register: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for entry in register:
        item = dict(entry)
        item["vertex"] = int(item["vertex"])
        item["color"] = int(item["color"])
        item["order_index"] = int(item["order_index"])
        item["domains_before"] = _domains_to_json(item["domains_before"])
        out.append(item)
    return out


def _register_from_json(register: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for entry in register:
        item = dict(entry)
        item["vertex"] = int(item["vertex"])
        item["color"] = int(item["color"])
        item["order_index"] = int(item["order_index"])
        item["domains_before"] = _domains_from_json(item["domains_before"])
        out.append(item)
    return out


def _episode_to_json(ep: InLoopEpisode) -> dict[str, Any]:
    return {
        "key": _episode_key(ep),
        "row": ep.row,
        "arm": ep.arm,
        "register_capacity_D": int(ep.register_capacity_D),
        "adjacency": {str(int(vertex)): sorted(int(item) for item in neighbors) for vertex, neighbors in ep.adjacency.items()},
        "order": [int(vertex) for vertex in ep.order],
        "domains": _domains_to_json(ep.domains),
        "assignment": {str(int(vertex)): int(color) for vertex, color in ep.assignment.items()},
        "cursor": int(ep.cursor),
        "calls": int(ep.calls),
        "status": ep.status,
        "solved": bool(ep.solved),
        "call_cap_hit": bool(ep.call_cap_hit),
        "register": _register_to_json(ep.register),
        "tried_colors": {str(int(vertex)): sorted(int(color) for color in colors) for vertex, colors in ep.tried_colors.items()},
        "generation_counts": dict(ep.generation_counts),
        "operator_error_counts": dict(ep.operator_error_counts),
        "step_rows": ep.step_rows,
        "first_conflict_depth": ep.first_conflict_depth,
        "max_backjump_distance": int(ep.max_backjump_distance),
        "total_retractions": int(ep.total_retractions),
    }


def _episode_from_json(payload: dict[str, Any]) -> InLoopEpisode:
    ep = InLoopEpisode(
        row=payload["row"],
        arm=payload["arm"],
        register_capacity_D=int(payload["register_capacity_D"]),
        adjacency={int(vertex): {int(item) for item in neighbors} for vertex, neighbors in payload["adjacency"].items()},
        order=[int(vertex) for vertex in payload["order"]],
        domains=_domains_from_json(payload["domains"]),
    )
    ep.assignment = {int(vertex): int(color) for vertex, color in payload.get("assignment", {}).items()}
    ep.cursor = int(payload.get("cursor", 0))
    ep.calls = int(payload.get("calls", 0))
    ep.status = str(payload.get("status", "RUNNING"))
    ep.solved = bool(payload.get("solved", False))
    ep.call_cap_hit = bool(payload.get("call_cap_hit", False))
    ep.register = _register_from_json(payload.get("register", []))
    ep.tried_colors = defaultdict(set, {int(vertex): {int(color) for color in colors} for vertex, colors in payload.get("tried_colors", {}).items()})
    ep.generation_counts = Counter(payload.get("generation_counts", {}))
    ep.operator_error_counts = Counter(payload.get("operator_error_counts", {}))
    ep.step_rows = list(payload.get("step_rows", []))
    ep.first_conflict_depth = payload.get("first_conflict_depth")
    ep.max_backjump_distance = int(payload.get("max_backjump_distance", 0))
    ep.total_retractions = int(payload.get("total_retractions", 0))
    return ep


def _save_piece1_checkpoint(path: Path, episodes: list[InLoopEpisode]) -> None:
    counts = dict(Counter(ep.status for ep in episodes))
    payload = {"schema_version": "rung1_piece1_episode_checkpoint_v0", "updated_at": _now(), "status_counts": counts, "episodes": [_episode_to_json(ep) for ep in episodes]}
    _write_checkpoint(path, payload)


def _load_piece1_checkpoint(path: Path, episodes: list[InLoopEpisode], resume: bool) -> list[InLoopEpisode]:
    if not resume or not path.exists():
        return episodes
    payload = _read_checkpoint(path, {})
    saved = {row["key"]: _episode_from_json(row) for row in payload.get("episodes", [])}
    return [saved.get(_episode_key(ep), ep) for ep in episodes]


def _run_episodes_checkpointed(episodes: list[InLoopEpisode], args: argparse.Namespace, call_cap: int, max_new_tokens: int, keff_hat: float, checkpoint_path: Path) -> list[InLoopEpisode]:
    if not checkpoint_path.exists():
        _save_piece1_checkpoint(checkpoint_path, episodes)
    while True:
        changed = False
        for ep in episodes:
            changed = _advance_without_generation(ep, call_cap, keff_hat) or changed
        active = [ep for ep in episodes if ep.status == "RUNNING" and _live_domain(ep, ep.order[ep.cursor])]
        if changed:
            _save_piece1_checkpoint(checkpoint_path, episodes)
        if not active:
            _save_piece1_checkpoint(checkpoint_path, episodes)
            return episodes
        batch = active[:args.batch_size]
        prompts = [_prompt_for_inloop_episode(ep, "explicit_domains") for ep in batch]
        generations = _generate_prompts(prompts, "openai", None, None, max_new_tokens, args.openai_base_url, args.openai_model, True)
        for ep, generation in zip(batch, generations):
            _apply_generation(ep, generation, keff_hat)
        _save_piece1_checkpoint(checkpoint_path, episodes)


def _group(rows: list[dict[str, Any]], *keys: str) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row[key] for key in keys)].append(row)
    return grouped


def _ols_slope(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    xbar = mean(xs)
    ybar = mean(ys)
    den = sum((x - xbar) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - xbar) * (y - ybar) for x, y in points) / den


def _select_manifest(b_values: tuple[int, ...], depths: tuple[int, ...], n_per_cell: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in _load_separator_manifest():
        b_value = int(row.get("b", -1))
        depth = int(row.get("d_global_reference", -1))
        if b_value in b_values and depth in depths:
            grouped[(b_value, depth)].append(row)
    selected = []
    for key in sorted(grouped):
        rows = sorted(grouped[key], key=lambda row: (int(row["seed"]), int(row["source_index"]), str(row["instance_id"])))
        selected.extend(rows[:n_per_cell])
    return selected


def _trace_clean(row: dict[str, Any], register_d: int, keff: float, node_cap: int) -> dict[str, Any]:
    instance = _instance_from_row(row)
    adj = _adjacency(instance.n, instance.edges)
    order = list(instance.order)
    pos = {vertex: index for index, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    register: list[dict[str, int]] = []
    next_choice = {vertex: 0 for vertex in order}
    steps = 0
    retractions = 0
    first_conflict_depth = int(instance.reference_depth)
    max_backjump = 0
    cursor = 0

    def depth_component() -> int:
        return max(1, first_conflict_depth, max_backjump)

    def occupancy() -> int:
        return math.ceil(depth_component() * math.log(max(keff, 1.0001)))

    while True:
        peak = occupancy()
        if steps >= node_cap:
            return _clean_row(row, register_d, keff, "NODE_CAP", False, steps, retractions, peak, None)
        if cursor >= len(order):
            if peak >= register_d:
                return _clean_row(row, register_d, keff, "OVERFLOW_FAIL", False, steps, retractions, peak, depth_component())
            return _clean_row(row, register_d, keff, "SOLVED", True, steps, retractions, peak, None)
        vertex = order[cursor]
        steps += 1
        blockers_by_color: dict[int, list[int]] = {}
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
        nogood = {min(blockers, key=lambda item: pos[item]) for blockers in blockers_by_color.values()}
        earliest = min((pos[item] for item in nogood), default=cursor)
        first_conflict_depth = max(first_conflict_depth, cursor - earliest)
        peak = occupancy()
        if peak >= register_d:
            return _clean_row(row, register_d, keff, "OVERFLOW_FAIL", False, steps, retractions, peak, depth_component())
        if not register:
            return _clean_row(row, register_d, keff, "NO_RECOVERY_TARGET", False, steps, retractions, peak, None)
        target = max(nogood, key=lambda item: pos[item]) if nogood else register[-1]["vertex"]
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


def _clean_row(row: dict[str, Any], register_d: int, keff: float, status: str, solved: bool, steps: int, retractions: int, peak: int, overflow_depth: int | None) -> dict[str, Any]:
    return {
        "instance_id": row["instance_id"],
        "cell_id": row.get("cell_id"),
        "b": int(row["b"]),
        "d_global_reference": int(row["d_global_reference"]),
        "register_capacity_D": int(register_d),
        "k_eff": float(keff),
        "status": status,
        "solved": bool(solved),
        "steps": int(steps),
        "total_retractions": int(retractions),
        "peak_register_occupancy_proxy": int(peak),
        "overflowed": status == "OVERFLOW_FAIL",
        "overflow_depth": overflow_depth,
        "source": SOURCE,
        "provenance": "rung1_fallible_1d_clean_trace_fixed_overflow_depth_v0",
    }


def _cell_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (register_d, depth, b_value), subset in sorted(_group(rows, "register_capacity_D", "d_global_reference", "b").items()):
        overflow_depths = [row["overflow_depth"] for row in subset if row.get("overflow_depth") is not None]
        out.append({
            "register_capacity_D": int(register_d),
            "d_global_reference": int(depth),
            "b": int(b_value),
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "overflow_rate": mean(float(row["overflowed"]) for row in subset),
            "mean_overflow_depth": mean(overflow_depths) if overflow_depths else None,
            "status_counts": dict(Counter(row["status"] for row in subset)),
            "source": SOURCE,
            "provenance": "rung1_fallible_1d_cell_summary_v0",
        })
    return out


def _clean_piece(rows: list[dict[str, Any]], d_values: tuple[int, ...], operator_by_b: dict[int, dict[str, Any]], node_cap: int, label: str) -> dict[str, Any]:
    instance_rows = []
    for row in rows:
        keff = float(operator_by_b[int(row["b"])]["k_eff_clean"])
        for register_d in d_values:
            instance_rows.append(_trace_clean(row, register_d, keff, node_cap))
    cells = _cell_summary(instance_rows)
    points = [(float(row["register_capacity_D"]), float(row["mean_overflow_depth"])) for row in cells if int(row["b"]) == 2 and row.get("mean_overflow_depth") is not None]
    return {"label": label, "status": "COMPLETE", "instance_rows": instance_rows, "cell_summary": cells, "overflow_depth_vs_D_slope": _ols_slope(points)}


def _run_piece1_fallible(args: argparse.Namespace, rows: list[dict[str, Any]], operator_by_b: dict[int, dict[str, Any]]) -> dict[str, Any]:
    max_d = max(PIECE1_D)
    max_calls = len(rows) * len(PIECE1_D) * args.piece1_call_cap
    budget = {"piece": "piece1", "n_instances": len(rows), "D_values": list(PIECE1_D), "call_cap": args.piece1_call_cap, "max_D": max_d, "max_llm_calls": max_calls, "max_budget_calls": args.max_budget_calls, "call_cap_gt_max_D": args.piece1_call_cap > max_d, "cost_ok": max_calls <= args.max_budget_calls}
    if not budget["call_cap_gt_max_D"]:
        return {"status": "KILLED_PREFLIGHT_CALL_CAP_LE_MAX_D", "budget_ledger": budget, "instance_rows": [], "step_rows": [], "cell_summary": []}
    if not budget["cost_ok"]:
        return {"status": "SKIPPED_BUDGET", "budget_ledger": budget, "instance_rows": [], "step_rows": [], "cell_summary": []}
    if args.no_llm:
        return {"status": "SKIPPED_NO_LLM_FLAG", "budget_ledger": budget, "instance_rows": [], "step_rows": [], "cell_summary": []}
    keff_hat = float(operator_by_b[2]["graded_keff_inflated"])
    episodes = []
    for register_d in PIECE1_D:
        for row in rows:
            episodes.append(InLoopEpisode(row=row, arm="cbj_bounded", register_capacity_D=int(register_d), adjacency=_adjacency(int(row["n_vertices"]), tuple(tuple(edge) for edge in row["edges"])), order=[int(vertex) for vertex in row["order"]], domains=_initial_domains(row)))
    checkpoint_path = _checkpoint_dir(args) / "piece1_episodes.json"
    episodes = _load_piece1_checkpoint(checkpoint_path, episodes, args.resume)
    episodes = _run_episodes_checkpointed(episodes, args, args.piece1_call_cap, args.max_new_tokens, keff_hat, checkpoint_path)
    instance_rows = []
    for ep in episodes:
        row = _row_for_episode(ep)
        depth_component = max(1, int(ep.first_conflict_depth or 0), int(ep.max_backjump_distance or 0), int(ep.cursor), len(ep.register))
        row.update({"overflow_depth": depth_component if ep.status == "OVERFLOW_FAIL" else None, "k_eff_used": keff_hat})
        instance_rows.append(row)
    return {"status": "COMPLETE", "budget_ledger": budget, "instance_rows": instance_rows, "step_rows": [step for ep in episodes for step in ep.step_rows], "cell_summary": _fallible_cell_summary(instance_rows)}


def _fallible_cell_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (register_d, depth), subset in sorted(_group(rows, "register_capacity_D", "d_global_reference").items()):
        overflows = [row["overflow_depth"] for row in subset if row.get("overflow_depth") is not None]
        out.append({"register_capacity_D": int(register_d), "d_global_reference": int(depth), "b": 2, "n": len(subset), "solve_rate": mean(float(row.get("solved_valid", False)) for row in subset), "call_cap_rate": mean(float(row.get("call_cap_hit", False)) for row in subset), "overflow_rate": mean(float(row.get("status") == "OVERFLOW_FAIL") for row in subset), "mean_overflow_depth": mean(overflows) if overflows else None, "status_counts": dict(Counter(row["status"] for row in subset)), "source": SOURCE, "provenance": "rung1_fallible_1d_fallible_cell_summary_v0"})
    return out


def _first_json(text: str) -> dict[str, Any]:
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    for start in [m.start() for m in re.finditer(r"\{", text)]:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start:index + 1])
                    except json.JSONDecodeError:
                        break
                    return parsed if isinstance(parsed, dict) else {}
    return {}


def _openai_call(base_url: str, model: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": max_tokens}
    request = Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=3600) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"OpenAI-compatible P1c request failed: {exc}") from exc
    choice = decoded.get("choices", [{}])[0]
    usage = decoded.get("usage", {})
    return {"text": choice.get("message", {}).get("content", ""), "finish_reason": "length" if choice.get("finish_reason") == "length" else "stop", "output_tokens": int(usage.get("completion_tokens") or 0)}


def _p1c_row_from_generation(idx: int, episode: dict[str, Any], generation: dict[str, Any]) -> dict[str, Any]:
    parsed = _first_json(generation["text"])
    pred_conflict = bool(parsed.get("conflict_detected"))
    try:
        culprit = None if parsed.get("culprit") is None else int(parsed.get("culprit"))
    except (TypeError, ValueError):
        culprit = None
    oracle_conflict = bool(episode["oracle_conflict"])
    oracle_culprits = {int(value) for value in episode["oracle_culprits"]}
    return {"episode_index": idx, "instance_id": episode["row"].get("instance_id"), "episode_type": episode.get("episode_type"), "oracle_conflict": oracle_conflict, "oracle_culprits": sorted(oracle_culprits), "predicted_conflict": pred_conflict, "predicted_culprit": culprit, "culprit_correct": bool(oracle_conflict and culprit in oracle_culprits), "parsable": bool(parsed), "finish_reason": generation["finish_reason"], "output_tokens": generation["output_tokens"], "source": SOURCE, "provenance": "rung1_fallible_1d_p1c_scale_row_v0"}


def _run_p1c(args: argparse.Namespace, remaining_budget: int) -> dict[str, Any]:
    rows = [row for row in _load_separator_manifest() if int(row.get("b", -1)) == 12]
    rows = sorted(rows, key=lambda row: (int(row["d_global_reference"]), int(row["seed"]), int(row["source_index"])))[:args.p1c_instances]
    episodes = _competence_episodes(rows)
    n_run = min(args.p1c_target_episodes, len(episodes), remaining_budget)
    budget = {"piece": "piece4", "target_episodes": args.p1c_target_episodes, "available_episodes": len(episodes), "n_episodes": n_run, "call_cap": 1, "max_llm_calls": n_run, "remaining_budget_after_piece1": remaining_budget, "cost_ok": n_run > 0}
    if not budget["cost_ok"]:
        return {"status": "SKIPPED_BUDGET", "budget_ledger": budget, "rows": [], "summary": {}}
    if args.no_llm or args.no_p1c:
        return {"status": "SKIPPED_NO_LLM_FLAG", "budget_ledger": budget, "rows": [], "summary": {}}
    selected = episodes[:n_run]
    checkpoint_path = _checkpoint_dir(args) / "piece4_p1c_rows.json"
    completed_rows = _read_checkpoint(checkpoint_path, []) if args.resume else []
    completed_by_idx = {int(row["episode_index"]): row for row in completed_rows}
    pending = [(idx, episode) for idx, episode in enumerate(selected) if idx not in completed_by_idx]
    if pending:
        with ThreadPoolExecutor(max_workers=max(1, min(args.batch_size, len(pending)))) as pool:
            future_to_episode = {pool.submit(_openai_call, args.openai_base_url, args.openai_model, _prompt_for_operator(episode, OPERATOR_VERSION_V2), args.p1c_max_tokens): (idx, episode) for idx, episode in pending}
            for future in as_completed(future_to_episode):
                idx, episode = future_to_episode[future]
                completed_by_idx[idx] = _p1c_row_from_generation(idx, episode, future.result())
                _write_checkpoint(checkpoint_path, [completed_by_idx[key] for key in sorted(completed_by_idx)])
    out = [completed_by_idx[key] for key in sorted(completed_by_idx) if key < n_run]
    return {"status": "COMPLETE", "budget_ledger": budget, "rows": out, "summary": _p1c_summary(out)}


def _p1c_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(1 for row in rows if row["oracle_conflict"] and row["predicted_conflict"])
    fp = sum(1 for row in rows if not row["oracle_conflict"] and row["predicted_conflict"])
    fn = sum(1 for row in rows if row["oracle_conflict"] and not row["predicted_conflict"])
    true_conflicts = sum(1 for row in rows if row["oracle_conflict"])
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    culprit_accuracy = sum(1 for row in rows if row["culprit_correct"]) / max(1, true_conflicts)
    return {"n_episodes": len(rows), "n_true_conflicts": true_conflicts, "n_true_nonconflicts": sum(1 for row in rows if not row["oracle_conflict"]), "conflict_precision": precision, "conflict_recall": recall, "culprit_accuracy": culprit_accuracy, "functional_gate_threshold": FUNCTIONAL_GATE_THRESHOLD, "functional_gate_pass": min(precision, recall, culprit_accuracy) >= FUNCTIONAL_GATE_THRESHOLD, "positive_or_negative": "positive_scaled" if min(precision, recall, culprit_accuracy) >= FUNCTIONAL_GATE_THRESHOLD else "negative_scaled", "source": SOURCE, "provenance": "rung1_fallible_1d_p1c_scale_summary_v0"}


def _dstar_slope(cell_rows: list[dict[str, Any]], b_value: int) -> dict[str, Any]:
    points = []
    dstar_rows = []
    for register_d in sorted({int(row["register_capacity_D"]) for row in cell_rows if int(row["b"]) == b_value}):
        rates = [(int(row["d_global_reference"]), float(row["solve_rate"])) for row in cell_rows if int(row["b"]) == b_value and int(row["register_capacity_D"]) == register_d]
        dstar = _interpolate_dstar(rates)
        dstar_rows.append({"register_capacity_D": register_d, "b": b_value, **dstar})
        if dstar.get("dstar_observed") is not None:
            points.append((float(register_d), float(dstar["dstar_observed"])))
    return {"b": b_value, "clean_dstar_vs_D_slope": _ols_slope(points), "n_uncensored": len(points), "dstar_rows": dstar_rows}


def _piece1_verdict(clean: dict[str, Any], fallible: dict[str, Any]) -> str:
    if fallible.get("status") != "COMPLETE":
        return "still_call_cap_dominated"
    counts = Counter(row["status"] for row in fallible.get("instance_rows", []))
    if counts.get("CALL_CAP", 0) > counts.get("OVERFLOW_FAIL", 0) + counts.get("SOLVED", 0):
        return "still_call_cap_dominated"
    clean_depths = [row["mean_overflow_depth"] for row in clean.get("cell_summary", []) if row.get("mean_overflow_depth") is not None]
    fall_depths = [row["mean_overflow_depth"] for row in fallible.get("cell_summary", []) if row.get("mean_overflow_depth") is not None]
    if clean_depths and fall_depths and mean(fall_depths) < mean(clean_depths) - 1.0:
        return "fallibility_compresses_dstar_keff_inflation"
    return "register_binds_no_distinct_fallibility_effect"


def run(args: argparse.Namespace) -> dict[str, Any]:
    operator_by_b = _operator_by_b(_read_json(GRADED_PATH))
    piece1_rows = _select_manifest((2,), PIECE1_DEPTHS, args.piece1_n_per_depth)
    piece1_clean = _clean_piece(piece1_rows, PIECE1_D, operator_by_b, args.node_cap, "piece1_clean_fixed_overflow_depth")
    piece1_fallible = _run_piece1_fallible(args, piece1_rows, operator_by_b)
    piece1_spent = int(piece1_fallible.get("budget_ledger", {}).get("max_llm_calls", 0)) if piece1_fallible.get("status") == "COMPLETE" else 0
    piece3_rows = _select_manifest(PIECE3_B, PIECE3_DEPTHS, args.piece3_n_per_cell)
    piece3_clean = _clean_piece(piece3_rows, PIECE3_D, operator_by_b, args.node_cap, "piece3_large_b_clean_extended_D")
    piece3_slopes = [_dstar_slope(piece3_clean["cell_summary"], b) for b in PIECE3_B]
    piece3_verdict = "inconclusive_still_censored" if any(row["n_uncensored"] < 2 for row in piece3_slopes) else ("structural_separator_limited" if all(abs(row["clean_dstar_vs_D_slope"] or 0.0) < 0.05 for row in piece3_slopes) else "fallibility_capped")
    piece4 = _run_p1c(args, max(0, args.max_budget_calls - piece1_spent))
    piece1_verdict = _piece1_verdict(piece1_clean, piece1_fallible)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_PREFLIGHT_FAIL if piece1_fallible.get("status") == "KILLED_PREFLIGHT_CALL_CAP_LE_MAX_D" else STATUS_COMPLETE,
        "generated_at": _now(),
        "headline": {"piece1_verdict": piece1_verdict, "determination": "not_yet_reachable" if piece1_verdict == "still_call_cap_dominated" else "positive_or_weaker_positive", "single_next_move": "Raise call_cap or shrink harder until Piece 1 is not CALL_CAP dominated." if piece1_verdict == "still_call_cap_dominated" else "Use reachable fallible curve before decoupling corner."},
        "budget_ledger": [piece1_fallible.get("budget_ledger"), piece4.get("budget_ledger")],
        "piece1": {"piece1_verdict": piece1_verdict, "clean": piece1_clean, "fallible": piece1_fallible},
        "piece2": {"corrected_overflow_depth_definition": "trail depth at first step register occupancy reaches cap D; never emits 0 for real overflow", "rederived_clean_slope": piece1_clean.get("overflow_depth_vs_D_slope"), "rederived_fallible_slope": _ols_slope([(float(row["register_capacity_D"]), float(row["mean_overflow_depth"])) for row in piece1_fallible.get("cell_summary", []) if row.get("mean_overflow_depth") is not None]), "clean_scaling_gate": "supported" if piece1_clean.get("overflow_depth_vs_D_slope") is not None and piece1_clean["overflow_depth_vs_D_slope"] > 0.2 else "not_established"},
        "piece3": {"piece3_verdict": piece3_verdict, "clean_large_b_dstar_slopes": piece3_slopes, "clean": piece3_clean},
        "piece4": {"status": piece4.get("status"), "scaled_p1c_competence": piece4.get("summary"), "rows": piece4.get("rows", [])},
        "guards": ["call_cap > max register D hard preflight", "No fallible capacity-law positive until Piece 1 fixed-cap lands", "Track 4 inconclusive until large-b D uncensored", "P1c competence provisional until scaled run"],
        "source": SOURCE,
        "provenance": "rung1_fallible_1d_rerun_v0",
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fallible 1D rerun batch.")
    parser.add_argument("--output", type=Path, default=RESULTS_PATH)
    parser.add_argument("--max-budget-calls", type=int, default=2200)
    parser.add_argument("--piece1-n-per-depth", type=int, default=1)
    parser.add_argument("--piece1-call-cap", type=int, default=40)
    parser.add_argument("--piece3-n-per-cell", type=int, default=2)
    parser.add_argument("--node-cap", type=int, default=DEFAULT_NODE_CAP)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--checkpoint-dir", type=Path, default=RESULTS_DIR / "checkpoints")
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.set_defaults(resume=True)
    parser.add_argument("--openai-base-url", default=DEFAULT_OPENAI_BASE_URL)
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--p1c-target-episodes", type=int, default=3000)
    parser.add_argument("--p1c-instances", type=int, default=800)
    parser.add_argument("--p1c-max-tokens", type=int, default=4500)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--no-p1c", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
