"""Bounded end-to-end P1b LLM-in-the-loop separator run.

Layer-3 controlled substrate: real Qwen calls at every visited search node, while
conflict detection, recovery routing, register accounting, and the propagation
soundness guard remain symbolic. This validates or falsifies the calibrated proxy
without folding in P1c conflict/culprit fallibility.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
from statistics import mean
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import torch

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _adjacency, _rel
from experiments.rung1_separator_llm_po_forward_gate import MODEL_ID, SEPARATOR_RESULTS_PATH, _load_model, _read_json
from experiments.rung1_separator_p1b_full_table import GRADED_PATH, _operator_by_b
from experiments.rung1_separator_p1b_truncation_pilot import (
    ANSWER_TOKEN_BUDGET_REQUESTED,
    THINKING_BUDGET_REQUESTED,
    Episode as P1bEpisode,
    _apply_guarded_prunes,
    _generate_batch,
    _initial_domains,
    _operator_prompt,
    _oracle_prunes,
    _parse_generation,
)


RESULTS_ROOT = REPO_ROOT / "results/rung1_separator_llm_inloop"
RESULTS_PATH = RESULTS_ROOT / "results.json"
SCHEMA_VERSION = "rung1_separator_llm_inloop_v0"
STATUS_PREFLIGHT = "RUNG1_SEPARATOR_LLM_INLOOP_PREFLIGHT_ONLY"
STATUS_BUDGET_STOP = "RUNG1_SEPARATOR_LLM_INLOOP_BUDGET_STOP"
STATUS_COMPLETE = "RUNG1_SEPARATOR_LLM_INLOOP_SMOKE_COMPLETE"
STATUS_CAPACITY_COMPLETE = "RUNG1_SEPARATOR_LLM_INLOOP_CAPACITY_SLICE_COMPLETE"
STATUS_FAIL = "RUNG1_SEPARATOR_LLM_INLOOP_FAIL"
OPERATOR_VERSION = "v1_1"
PROMPT_CONTRACT = "p1b_bounded_structured_domain_propagation_capped_thinking_v1_1"
CAPACITY_D_VALUES = (6, 8, 10)
CAPACITY_DEPTHS = (4, 5, 6, 7, 9, 10)
SMOKE_D_VALUES = (6,)
SMOKE_DEPTHS = (4, 5)
B_VALUE = 2
DEFAULT_N_PER_CELL = 8
DEFAULT_SMOKE_N_PER_CELL = 2
DEFAULT_CALL_CAP = 40
DEFAULT_MAX_BUDGET_CALLS = 300
DEFAULT_MAX_NEW_TOKENS = 4096
DEFAULT_BATCH_SIZE = 4
DEFAULT_OPENAI_BASE_URL = "http://127.0.0.1:8001/v1"
DEFAULT_OPENAI_MODEL = "Qwen/Qwen3.5-4B"
LOW_SOLVE_THRESHOLD = 0.50


@dataclass
class InLoopEpisode:
    row: dict[str, Any]
    arm: str
    register_capacity_D: int
    adjacency: dict[int, set[int]]
    order: list[int]
    domains: dict[int, set[int]]
    assignment: dict[int, int] = field(default_factory=dict)
    cursor: int = 0
    calls: int = 0
    status: str = "RUNNING"
    solved: bool = False
    call_cap_hit: bool = False
    register: list[dict[str, Any]] = field(default_factory=list)
    tried_colors: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    generation_counts: Counter[str] = field(default_factory=Counter)
    operator_error_counts: Counter[str] = field(default_factory=Counter)
    step_rows: list[dict[str, Any]] = field(default_factory=list)
    first_conflict_depth: int | None = None
    max_backjump_distance: int = 0
    total_retractions: int = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _group(rows: list[dict[str, Any]], *keys: str) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    out: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        out[tuple(row[key] for key in keys)].append(row)
    return out


def _load_separator_manifest() -> list[dict[str, Any]]:
    data = _read_json(SEPARATOR_RESULTS_PATH)
    if data.get("schema_version") != "rung1_separator_scaling_symbolic_v0_2_3":
        raise RuntimeError("unexpected separator schema")
    return data.get("instance_manifest", [])


def _select_capacity_manifest(depths: tuple[int, ...], n_per_cell: int) -> list[dict[str, Any]]:
    by_depth: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in _load_separator_manifest():
        if int(row.get("b", -1)) == B_VALUE and int(row.get("d_global_reference", -1)) in depths:
            by_depth[int(row["d_global_reference"])].append(row)
    selected: list[dict[str, Any]] = []
    for depth in depths:
        rows = sorted(by_depth.get(depth, []), key=lambda row: (int(row["seed"]), int(row["source_index"]), str(row["instance_id"])))
        selected.extend(rows[:n_per_cell])
    return selected


def _estimate_budget(n_instances: int, d_values: tuple[int, ...], arms: tuple[str, ...], call_cap: int) -> dict[str, Any]:
    cells = len(d_values) * len(arms)
    max_llm_calls = n_instances * cells * call_cap
    return {
        "n_base_instances": n_instances,
        "n_register_D_values": len(d_values),
        "n_arms": len(arms),
        "call_cap_per_instance": call_cap,
        "max_llm_calls": max_llm_calls,
        "thinking_budget_requested": THINKING_BUDGET_REQUESTED,
        "answer_token_budget_requested": ANSWER_TOKEN_BUDGET_REQUESTED,
        "source": SOURCE,
        "provenance": "llm_inloop_budget_preflight_v0",
    }


def _live_domain(ep: InLoopEpisode, vertex: int) -> list[int]:
    if vertex in ep.assignment:
        return []
    live = set(ep.domains[vertex])
    live -= ep.tried_colors[vertex]
    for neighbor in ep.adjacency[vertex]:
        assigned = ep.assignment.get(neighbor)
        if assigned in live:
            live.remove(assigned)
    return sorted(live)


def _p1b_prompt_episode(ep: InLoopEpisode) -> P1bEpisode:
    return P1bEpisode(
        row=ep.row,
        adjacency=ep.adjacency,
        order=ep.order,
        domains=ep.domains,
        assignment=ep.assignment,
        cursor=ep.cursor,
        calls=ep.calls,
        status=ep.status,
    )


def _position(ep: InLoopEpisode) -> dict[int, int]:
    return {vertex: index for index, vertex in enumerate(ep.order)}


def _blockers_by_color(ep: InLoopEpisode, vertex: int) -> dict[int, list[int]]:
    blockers: dict[int, list[int]] = {}
    for color in range(1, int(ep.row["k"]) + 1):
        color_blockers = [neighbor for neighbor in ep.adjacency[vertex] if ep.assignment.get(neighbor) == color]
        if color_blockers or color in ep.tried_colors[vertex]:
            blockers[color] = color_blockers
    return blockers


def _nogood(ep: InLoopEpisode, vertex: int, blockers: dict[int, list[int]]) -> set[int]:
    position = _position(ep)
    vertex_block = int(ep.row["partitions"][vertex])
    out = []
    for items in blockers.values():
        boundary = [item for item in items if int(ep.row["partitions"][item]) != vertex_block]
        if boundary:
            out.append(min(boundary, key=lambda item: position[item]))
        elif items:
            out.append(min(items, key=lambda item: position[item]))
    return set(out)


def _effective_peak(ep: InLoopEpisode, keff_hat: float) -> int:
    distance = max(int(ep.first_conflict_depth or int(ep.row["d_global_reference"])), int(ep.max_backjump_distance))
    return math.ceil(distance * math.log(max(keff_hat, 1.0001)))


def _recover(ep: InLoopEpisode, keff_hat: float) -> None:
    vertex = ep.order[ep.cursor]
    blockers = _blockers_by_color(ep, vertex)
    nogood = _nogood(ep, vertex, blockers)
    position = _position(ep)
    earliest = min((position[item] for item in nogood), default=ep.cursor)
    ep.first_conflict_depth = max(int(ep.first_conflict_depth or 0), ep.cursor - earliest)
    if _effective_peak(ep, keff_hat) > ep.register_capacity_D:
        ep.status = "OVERFLOW_FAIL"
        return
    if ep.arm == "forward_markov":
        ep.status = "FORWARD_DEAD_END"
        return
    if not ep.register:
        ep.status = "NO_RECOVERY_TARGET"
        return
    if ep.arm == "chronological_rollback" or not nogood:
        target_index = len(ep.register) - 1
    else:
        target_vertex = max(nogood, key=lambda item: position[item])
        target_index = max(index for index, entry in enumerate(ep.register) if entry["vertex"] == target_vertex)
    popped = ep.register[target_index:]
    ep.max_backjump_distance = max(ep.max_backjump_distance, len(popped))
    ep.total_retractions += len(popped)
    snapshot = ep.register[target_index]["domains_before"]
    ep.domains = {vertex_id: set(colors) for vertex_id, colors in snapshot.items()}
    for entry in popped:
        ep.assignment.pop(int(entry["vertex"]), None)
    for entry in popped[1:]:
        ep.tried_colors.pop(int(entry["vertex"]), None)
    ep.cursor = int(ep.register[target_index]["order_index"])
    ep.register = ep.register[:target_index]


def _apply_generation(ep: InLoopEpisode, generation: dict[str, Any], keff_hat: float) -> None:
    vertex = ep.order[ep.cursor]
    live = _live_domain(ep, vertex)
    parsed = _parse_generation(generation, int(ep.row["k"]), OPERATOR_VERSION)
    ep.calls += 1
    ep.generation_counts[parsed["generation_state"]] += 1
    chosen = parsed["color"]
    repair = None
    if chosen not in live:
        if chosen is None:
            ep.operator_error_counts["format_failure"] += 1
            repair = "format_failure"
        else:
            ep.operator_error_counts["value_misselection"] += 1
            repair = "value_misselection"
        chosen = live[0]
    domains_before = {key: set(value) for key, value in ep.domains.items()}
    ep.tried_colors[vertex].add(int(chosen))
    ep.assignment[vertex] = int(chosen)
    ep.domains[vertex] = {int(chosen)}
    p1b_ep = _p1b_prompt_episode(ep)
    oracle_before = set(_oracle_prunes(p1b_ep))
    prune_result = _apply_guarded_prunes(p1b_ep, parsed["prunes"])
    ep.domains = p1b_ep.domains
    accepted_set = {tuple(item) for item in prune_result["accepted_prunes"]}
    oracle_count = len(oracle_before)
    accepted_count = len(accepted_set & oracle_before)
    missed_set = oracle_before - accepted_set
    recall = accepted_count / oracle_count if oracle_count else None
    ep.register.append({"vertex": vertex, "color": int(chosen), "order_index": ep.cursor, "domains_before": domains_before})
    ep.step_rows.append({
        "instance_id": ep.row["instance_id"],
        "arm": ep.arm,
        "register_capacity_D": ep.register_capacity_D,
        "d_global_reference": int(ep.row["d_global_reference"]),
        "b": int(ep.row["b"]),
        "call_index": ep.calls,
        "cursor_before": ep.cursor,
        "vertex": vertex,
        "live_domain_size": len(live),
        "llm_color": parsed["color"],
        "chosen_color": int(chosen),
        "operator_repair": repair,
        "generation_state": parsed["generation_state"],
        "finish_reason": generation.get("finish_reason"),
        "thinking_finish_reason": generation.get("thinking_finish_reason"),
        "answer_finish_reason": generation.get("answer_finish_reason"),
        "thinking_tokens": generation.get("thinking_tokens"),
        "answer_tokens": generation.get("answer_tokens"),
        "output_tokens": generation.get("output_tokens"),
        "n_oracle_prunes": oracle_count,
        "n_accepted_prunes": accepted_count,
        "n_rejected_prunes": len(prune_result["rejected_prunes"]),
        "n_missed_prunes": len(missed_set),
        "propagation_recall": recall,
        "source": SOURCE,
        "provenance": "llm_inloop_step_v0",
    })
    if _effective_peak(ep, keff_hat) > ep.register_capacity_D:
        ep.status = "OVERFLOW_FAIL"
        return
    ep.cursor += 1
    if ep.cursor >= len(ep.order):
        ep.status = "SOLVED"
        ep.solved = True


def _run_episode(ep: InLoopEpisode, model: Any, tokenizer: Any, call_cap: int, max_new_tokens: int, keff_hat: float) -> InLoopEpisode:
    while ep.status == "RUNNING":
        if ep.calls >= call_cap:
            ep.status = "CALL_CAP"
            ep.call_cap_hit = True
            break
        vertex = ep.order[ep.cursor]
        live = _live_domain(ep, vertex)
        if not live:
            _recover(ep, keff_hat)
            continue
        prompt = _operator_prompt(_p1b_prompt_episode(ep), OPERATOR_VERSION)
        generation = _generate_batch(model, tokenizer, [prompt], max_new_tokens, OPERATOR_VERSION)[0]
        _apply_generation(ep, generation, keff_hat)
    return ep


def _openai_chat_completion(base_url: str, model_name: str, prompt: str, max_new_tokens: int) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_new_tokens,
    }
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=600) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"OpenAI-compatible backend request failed: {exc}") from exc
    choice = decoded.get("choices", [{}])[0]
    message = choice.get("message", {})
    usage = decoded.get("usage", {})
    return {
        "text": message.get("content", ""),
        "output_tokens": int(usage.get("completion_tokens") or 0),
        "thinking_tokens": None,
        "answer_tokens": int(usage.get("completion_tokens") or 0),
        "thinking_finish_reason": None,
        "answer_finish_reason": choice.get("finish_reason"),
        "finish_reason": "length" if choice.get("finish_reason") == "length" else "stop",
    }


def _generate_prompts(prompts: list[str], backend: str, model: Any, tokenizer: Any, max_new_tokens: int, openai_base_url: str, openai_model: str) -> list[dict[str, Any]]:
    if backend == "openai":
        with ThreadPoolExecutor(max_workers=max(1, len(prompts))) as pool:
            return list(pool.map(lambda prompt: _openai_chat_completion(openai_base_url, openai_model, prompt, max_new_tokens), prompts))
    return _generate_batch(model, tokenizer, prompts, max_new_tokens, OPERATOR_VERSION)


def _advance_without_generation(ep: InLoopEpisode, call_cap: int, keff_hat: float) -> bool:
    """Advance symbolic-only recovery until this episode needs an LLM call or terminates."""
    changed = False
    while ep.status == "RUNNING":
        if ep.calls >= call_cap:
            ep.status = "CALL_CAP"
            ep.call_cap_hit = True
            changed = True
            break
        vertex = ep.order[ep.cursor]
        if _live_domain(ep, vertex):
            break
        _recover(ep, keff_hat)
        changed = True
    return changed


def _run_episodes_batched(episodes: list[InLoopEpisode], backend: str, model: Any, tokenizer: Any, call_cap: int, max_new_tokens: int, keff_hat: float, batch_size: int, openai_base_url: str, openai_model: str) -> list[InLoopEpisode]:
    while True:
        for ep in episodes:
            _advance_without_generation(ep, call_cap, keff_hat)
        active = [ep for ep in episodes if ep.status == "RUNNING" and _live_domain(ep, ep.order[ep.cursor])]
        if not active:
            return episodes
        batch = active[:batch_size]
        prompts = [_operator_prompt(_p1b_prompt_episode(ep), OPERATOR_VERSION) for ep in batch]
        generations = _generate_prompts(prompts, backend, model, tokenizer, max_new_tokens, openai_base_url, openai_model)
        for ep, generation in zip(batch, generations):
            _apply_generation(ep, generation, keff_hat)


def _row_for_episode(ep: InLoopEpisode) -> dict[str, Any]:
    step_recalls = [row["propagation_recall"] for row in ep.step_rows if row["propagation_recall"] is not None]
    return {
        "instance_id": ep.row["instance_id"],
        "cell_id": ep.row["cell_id"],
        "d_global_reference": int(ep.row["d_global_reference"]),
        "b": int(ep.row["b"]),
        "register_capacity_D": ep.register_capacity_D,
        "arm": ep.arm,
        "solved_valid": bool(ep.solved),
        "status": ep.status,
        "llm_calls": ep.calls,
        "call_cap_hit": ep.call_cap_hit,
        "right_censored": ep.call_cap_hit,
        "total_retractions": ep.total_retractions,
        "mean_inloop_propagation_recall": mean(step_recalls) if step_recalls else None,
        "propagation_opportunity_steps": len(step_recalls),
        "generation_counts": dict(ep.generation_counts),
        "operator_error_counts": dict(ep.operator_error_counts),
        "source": SOURCE,
        "provenance": "llm_inloop_instance_v0",
    }


def _capacity_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for (register_D, depth), subset in sorted(_group(rows, "register_capacity_D", "d_global_reference").items()):
        out.append({
            "register_capacity_D": int(register_D),
            "d_global_bin": str(depth),
            "b_bin": str(B_VALUE),
            "n": len(subset),
            "solve_rate": mean(float(row["solved_valid"]) for row in subset),
            "call_cap_rate": mean(float(row["call_cap_hit"]) for row in subset),
            "mean_llm_calls": mean(float(row["llm_calls"]) for row in subset),
            "mean_inloop_propagation_recall": mean([float(row["mean_inloop_propagation_recall"]) for row in subset if row.get("mean_inloop_propagation_recall") is not None]) if any(row.get("mean_inloop_propagation_recall") is not None for row in subset) else None,
            "source": SOURCE,
            "provenance": "llm_inloop_capacity_cell_v0",
        })
    return out


def _build_result_payload(base_payload: dict[str, Any], rows: list[dict[str, Any]], step_rows: list[dict[str, Any]], isolated_recall: float | None, smoke: bool) -> dict[str, Any]:
    capacity = _capacity_summary(rows)
    recalls = [row["propagation_recall"] for row in step_rows if row.get("propagation_recall") is not None]
    inloop_recall = mean(recalls) if recalls else None
    status = STATUS_COMPLETE if smoke else STATUS_CAPACITY_COMPLETE
    return base_payload | {
        "status": status,
        "inloop_vs_isolated_recall": [{
            "b_bin": str(B_VALUE),
            "isolated_step1A_recall": isolated_recall,
            "inloop_recall": inloop_recall,
            "n_inloop_opportunity_steps": len(recalls),
            "delta_inloop_minus_isolated": None if inloop_recall is None or isolated_recall is None else inloop_recall - isolated_recall,
            "source": SOURCE,
            "provenance": "llm_inloop_vs_isolated_recall_v0",
        }],
        "proxy_match_by_cell": [],
        "capacity_scaling_inloop_b2": capacity,
        "decoupling_inloop_corner": [],
        "instance_arm_metrics": rows,
        "inloop_step_metrics": step_rows,
        "verdict": [
            {"check": "budget_preflight", "pass": True, "observed": f"max_llm_calls={base_payload['cost_ledger'][0]['max_llm_calls']}; threshold={base_payload['cost_ledger'][0]['max_budget_calls']}", "source": SOURCE, "provenance": "llm_inloop_verdict_v0"},
            {"check": "inloop_smoke_completed" if smoke else "inloop_capacity_slice_completed", "pass": bool(rows), "observed": f"n_instances={len(rows)}; n_steps={len(step_rows)}", "source": SOURCE, "provenance": "llm_inloop_verdict_v0"},
        ],
    }


def run(preflight_only: bool, smoke: bool, output_path: Path, n_per_cell: int, call_cap: int, max_budget_calls: int, max_new_tokens: int, device: str, batch_size: int, shard_index: int | None = None, num_shards: int = 1, backend: str = "transformers", openai_base_url: str = DEFAULT_OPENAI_BASE_URL, openai_model: str = DEFAULT_OPENAI_MODEL) -> dict[str, Any]:
    depths = SMOKE_DEPTHS if smoke else CAPACITY_DEPTHS
    d_values = SMOKE_D_VALUES if smoke else CAPACITY_D_VALUES
    arms = ("cbj_bounded",)
    manifest = _select_capacity_manifest(depths, n_per_cell)
    budget = _estimate_budget(len(manifest), d_values, arms, call_cap)
    cost_ok = int(budget["max_llm_calls"]) <= max_budget_calls
    expanded_specs = [(int(register_D), row, arm) for register_D in d_values for row in manifest for arm in arms]
    if shard_index is not None:
        expanded_specs = [spec for index, spec in enumerate(expanded_specs) if index % num_shards == shard_index]
    base_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "generation_config": {
            "model_id": MODEL_ID,
            "operator_version": OPERATOR_VERSION,
            "prompt_contract": PROMPT_CONTRACT,
            "thinking_budget_requested": THINKING_BUDGET_REQUESTED,
            "answer_token_budget_requested": ANSWER_TOKEN_BUDGET_REQUESTED,
            "b_value": B_VALUE,
            "register_capacity_D_values": list(d_values),
            "d_global_depths": list(depths),
            "n_per_cell_requested": n_per_cell,
            "call_cap_per_instance": call_cap,
            "max_new_tokens": max_new_tokens,
            "device": device,
            "batch_size": batch_size,
            "backend": backend,
            "openai_base_url": openai_base_url if backend == "openai" else None,
            "openai_model": openai_model if backend == "openai" else None,
            "smoke": smoke,
            "shard_index": shard_index,
            "num_shards": num_shards,
            "source": SOURCE,
            "provenance": "llm_inloop_config_v0",
        },
        "cost_ledger": [budget | {"max_budget_calls": max_budget_calls, "cost_ok": cost_ok, "n_shard_episode_specs": len(expanded_specs)}],
    }
    if preflight_only or not cost_ok:
        payload = base_payload | {
            "status": STATUS_PREFLIGHT if preflight_only else STATUS_BUDGET_STOP,
            "inloop_vs_isolated_recall": [],
            "proxy_match_by_cell": [],
            "capacity_scaling_inloop_b2": [],
            "decoupling_inloop_corner": [],
            "instance_arm_metrics": [],
            "inloop_step_metrics": [],
            "verdict": [{"check": "budget_preflight", "pass": cost_ok, "observed": f"max_llm_calls={budget['max_llm_calls']}; threshold={max_budget_calls}", "source": SOURCE, "provenance": "llm_inloop_verdict_v0"}],
        }
        _write_json(output_path, payload)
        return payload

    graded = _read_json(GRADED_PATH)
    operator_by_b = _operator_by_b(graded)
    keff_hat = float(operator_by_b[B_VALUE]["graded_keff_inflated"])
    isolated_recall = float(operator_by_b[B_VALUE]["prune_recall"])
    model = tokenizer = None
    if backend == "transformers":
        model, tokenizer, _ = _load_model(device, "auto")
    episodes: list[InLoopEpisode] = []
    try:
        for register_D, row, arm in expanded_specs:
            ep = InLoopEpisode(
                row=row,
                arm=arm,
                register_capacity_D=int(register_D),
                adjacency=_adjacency(int(row["n_vertices"]), tuple(tuple(edge) for edge in row["edges"])),
                order=[int(vertex) for vertex in row["order"]],
                domains=_initial_domains(row),
            )
            episodes.append(ep)
        episodes = _run_episodes_batched(episodes, backend, model, tokenizer, call_cap, max_new_tokens, keff_hat, batch_size, openai_base_url, openai_model)
    finally:
        if model is not None:
            del model
        if backend == "transformers" and torch.cuda.is_available():
            torch.cuda.empty_cache()
    rows = [_row_for_episode(ep) for ep in episodes]
    step_rows = [step for ep in episodes for step in ep.step_rows]
    payload = _build_result_payload(base_payload, rows, step_rows, isolated_recall, smoke)
    _write_json(output_path, payload)
    return payload


def _merge_shards(shard_paths: list[Path], output_path: Path) -> dict[str, Any]:
    shard_paths = [path if path.is_absolute() else REPO_ROOT / path for path in shard_paths]
    output_path = output_path if output_path.is_absolute() else REPO_ROOT / output_path
    payloads = [_read_json(path) for path in shard_paths]
    payloads = [payload for payload in payloads if payload]
    if not payloads:
        raise RuntimeError("no shard payloads to merge")
    first = payloads[0]
    rows = [row for payload in payloads for row in payload.get("instance_arm_metrics", [])]
    step_rows = [row for payload in payloads for row in payload.get("inloop_step_metrics", [])]
    isolated = None
    if first.get("inloop_vs_isolated_recall"):
        isolated = first["inloop_vs_isolated_recall"][0].get("isolated_step1A_recall")
    base = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "generation_config": first.get("generation_config", {}) | {"shard_index": None, "num_shards": len(payloads), "merged_shards": [str(path) for path in shard_paths]},
        "cost_ledger": first.get("cost_ledger", []),
        "shard_summaries": [
            {"path": _rel(path), "status": payload.get("status"), "n_instances": len(payload.get("instance_arm_metrics", [])), "n_steps": len(payload.get("inloop_step_metrics", []))}
            for path, payload in zip(shard_paths, payloads)
        ],
    }
    merged = _build_result_payload(base, rows, step_rows, isolated, bool(first.get("generation_config", {}).get("smoke")))
    _write_json(output_path, merged)
    return merged


def _launch_shards(num_shards: int, smoke: bool, output_dir: Path, n_per_cell: int, call_cap: int, max_budget_calls: int, max_new_tokens: int, batch_size: int, backend: str, openai_base_url: str, openai_model: str) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    shard_dir = output_dir / "shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    for stale in shard_dir.glob("shard_*.json"):
        stale.unlink()
    processes = []
    for shard_index in range(num_shards):
        device = f"cuda:{shard_index}"
        shard_path = shard_dir / f"shard_{shard_index:02d}.json"
        cmd = [
            sys.executable, "-u", "-m", "experiments.rung1_separator_llm_inloop",
            "--output", str(shard_path),
            "--n-per-cell", str(n_per_cell),
            "--call-cap", str(call_cap),
            "--max-budget-calls", str(max_budget_calls),
            "--max-new-tokens", str(max_new_tokens),
            "--device", device,
            "--batch-size", str(batch_size),
            "--backend", backend,
            "--openai-base-url", openai_base_url,
            "--openai-model", openai_model,
            "--shard-index", str(shard_index),
            "--num-shards", str(num_shards),
        ]
        if smoke:
            cmd.append("--smoke")
        print(json.dumps({"event": "llm_inloop_launch_shard", "shard_index": shard_index, "device": device, "cmd": cmd}), flush=True)
        processes.append(subprocess.Popen(cmd, cwd=str(REPO_ROOT)))
    failures = []
    for shard_index, process in enumerate(processes):
        return_code = process.wait()
        if return_code != 0:
            failures.append({"shard_index": shard_index, "return_code": return_code})
    if failures:
        raise RuntimeError(f"LLM in-loop shard failures: {failures}")
    shard_paths = [shard_dir / f"shard_{index:02d}.json" for index in range(num_shards)]
    return _merge_shards(shard_paths, output_dir / "results.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded P1b real LLM-in-the-loop controlled separator run.")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--output", default=str(RESULTS_PATH))
    parser.add_argument("--n-per-cell", type=int, default=DEFAULT_N_PER_CELL)
    parser.add_argument("--call-cap", type=int, default=DEFAULT_CALL_CAP)
    parser.add_argument("--max-budget-calls", type=int, default=DEFAULT_MAX_BUDGET_CALLS)
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--backend", choices=("transformers", "openai"), default="transformers")
    parser.add_argument("--openai-base-url", default=DEFAULT_OPENAI_BASE_URL)
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--shard-index", type=int, default=None)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--launch-4gpu", action="store_true")
    parser.add_argument("--output-dir", default=str(RESULTS_ROOT))
    args = parser.parse_args()
    if args.launch_4gpu:
        _launch_shards(4, args.smoke, Path(args.output_dir), args.n_per_cell, args.call_cap, args.max_budget_calls, args.max_new_tokens, args.batch_size, args.backend, args.openai_base_url, args.openai_model)
        return
    run(args.preflight_only, args.smoke, Path(args.output), args.n_per_cell, args.call_cap, args.max_budget_calls, args.max_new_tokens, args.device, args.batch_size, args.shard_index, args.num_shards, args.backend, args.openai_base_url, args.openai_model)


if __name__ == "__main__":
    main()
