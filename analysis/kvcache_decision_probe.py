"""Probe clean-vs-polluted graph_color decision accuracy under direct Transformers."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

import torch

from analysis.kvcache_graph_color_search import _load_model, _read_json, _write_json
from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE
from experiments.rung1_reasoning_gym_bounded_register import (
    _clean_trace,
    _current_domain,
    _deadend_nogood,
    _ensure_reasoning_gym,
    _entry_for_register,
    _graph_color_view,
)


SCHEMA_VERSION = "kvcache_decision_probe_v0"
STATUS_COMPLETE = "KVCACHE_DECISION_PROBE_COMPLETE"
STATUS_PREFLIGHT_FAIL = "KVCACHE_DECISION_PROBE_PREFLIGHT_FAIL"
STATUS_POINTS_COMPLETE = "KVCACHE_DECISION_PROBE_POINTS_COMPLETE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha1(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=12).hexdigest()


def _parse_ints(text: str) -> list[int]:
    return [int(item.strip()) for item in text.split(",") if item.strip()]


def _parse_bins(text: str) -> list[dict[str, Any]]:
    bins: list[dict[str, Any]] = []
    for chunk in text.split(","):
        if not chunk.strip():
            continue
        label, vertices, edge = chunk.split(":")
        bins.append({"label": label, "num_vertices": int(vertices), "edge_probability": float(edge)})
    return bins


def _make_dataset(args: argparse.Namespace, bin_spec: dict[str, Any]) -> Any:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    return reasoning_gym.create_dataset(
        "graph_color",
        size=args.scan_limit,
        seed=args.seed,
        num_colors=args.num_colors,
        min_num_vertices=int(bin_spec["num_vertices"]),
        max_num_vertices=int(bin_spec["num_vertices"]),
        edge_probability=float(bin_spec["edge_probability"]),
    )


def _live_path(register: list[dict[str, Any]]) -> str:
    if not register:
        return "LIVE_PATH empty"
    lines = ["LIVE_PATH"]
    for item in register:
        lines.append(f"BRANCH vertex={int(item['vertex'])} color={int(item['color'])} order_index={int(item['order_index'])}")
    return "\n".join(lines)


def _dead_history(dead_events: list[str], n_dead: int) -> str:
    if n_dead <= 0:
        return ""
    selected = dead_events[-n_dead:]
    lines = [f"RETRACTED_DEAD_BRANCH_HISTORY n={len(selected)}"]
    lines.extend(selected)
    return "\n".join(lines)


def _collect_points_for_entry(entry: dict[str, Any], source_index: int, trace: dict[str, Any], bin_spec: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    view = _graph_color_view(entry, args.order_mode)
    position = {vertex: index for index, vertex in enumerate(view["order"])}
    assignment: dict[int, int] = {}
    tried: dict[int, set[int]] = defaultdict(set)
    register: list[dict[str, Any]] = []
    dead_events: list[str] = []
    points: list[dict[str, Any]] = []
    cursor = 0
    step = 0
    while step < args.node_cap:
        if cursor >= len(view["order"]):
            break
        vertex = view["order"][cursor]
        domain = _current_domain(view, vertex, assignment, tried)
        step += 1
        if domain:
            neighbors = [{"neighbor": neighbor, "color": assignment[neighbor]} for neighbor in sorted(view["adjacency"][vertex]) if neighbor in assignment]
            oracle_color = int(domain[0])
            points.append({
                "kind": "branch",
                "difficulty_bin": bin_spec["label"],
                "num_vertices": int(bin_spec["num_vertices"]),
                "edge_probability": float(bin_spec["edge_probability"]),
                "source_index": int(source_index),
                "step": int(step),
                "trace_total_retractions": int(trace.get("total_retractions", 0)),
                "trace_steps": int(trace.get("steps", 0)),
                "problem": entry.get("question", ""),
                "live_register": [dict(item) for item in register],
                "dead_events": list(dead_events),
                "current_vertex": int(vertex),
                "domain": [int(color) for color in domain],
                "assigned_neighbors": neighbors,
                "already_tried_values": sorted(int(color) for color in tried[vertex]),
                "oracle_value": oracle_color,
            })
            tried[vertex].add(oracle_color)
            assignment[vertex] = oracle_color
            register.append({"vertex": int(vertex), "color": oracle_color, "order_index": int(cursor)})
            cursor += 1
            continue
        if not register:
            break
        nogood = _deadend_nogood(view, vertex, assignment, position)
        oracle_vertex = max(nogood, key=lambda item: position[item]) if nogood else int(register[-1]["vertex"])
        oracle_abs = max((index for index, item in enumerate(register) if int(item["vertex"]) == int(oracle_vertex)), default=len(register) - 1)
        start = max(0, len(register) - args.register_window)
        bounded = [_entry_for_register(item, index - start) for index, item in enumerate(register[start:])]
        oracle_view = oracle_abs - start
        if 0 <= oracle_view < len(bounded):
            points.append({
                "kind": "backtrack",
                "difficulty_bin": bin_spec["label"],
                "num_vertices": int(bin_spec["num_vertices"]),
                "edge_probability": float(bin_spec["edge_probability"]),
                "source_index": int(source_index),
                "step": int(step),
                "trace_total_retractions": int(trace.get("total_retractions", 0)),
                "trace_steps": int(trace.get("steps", 0)),
                "problem": entry.get("question", ""),
                "live_register": [dict(item) for item in register],
                "dead_events": list(dead_events),
                "conflict_vertex": int(vertex),
                "conflict_blockers": sorted(int(item) for item in nogood),
                "bounded_register": bounded,
                "oracle_value": int(oracle_view),
            })
        popped = register[oracle_abs:]
        for item in popped:
            assignment.pop(int(item["vertex"]), None)
        for item in popped[1:]:
            tried[int(item["vertex"])] = set()
        tried[vertex] = set()
        dead_events.extend(
            f"RETRACTED_BRANCH vertex={int(item['vertex'])} color={int(item['color'])} order_index={int(item['order_index'])} conflict_vertex={int(vertex)} blockers={sorted(int(blocker) for blocker in nogood)}"
            for item in popped
        )
        cursor = int(register[oracle_abs]["order_index"])
        del register[oracle_abs:]
    return points


def _collect_points(args: argparse.Namespace, bins: list[dict[str, Any]], n_values: list[int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    all_points: list[dict[str, Any]] = []
    preflight_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    for bin_spec in bins:
        print(json.dumps({"phase": "collect_start_bin", "difficulty_bin": bin_spec["label"], "scan_limit": args.scan_limit}), flush=True)
        dataset = _make_dataset(args, bin_spec)
        bin_points: list[dict[str, Any]] = []
        selected = 0
        for source_index in range(args.scan_limit):
            entry = dataset[source_index]
            entry.setdefault("metadata", {})["source_index"] = source_index
            trace = _clean_trace(entry, args.order_mode, args.node_cap, dataset)
            row = {"difficulty_bin": bin_spec["label"], "source_index": source_index, **trace}
            row["selected"] = bool(trace.get("solved") and int(trace.get("total_retractions", 0)) >= args.min_backtracks)
            preflight_rows.append(row)
            if not row["selected"]:
                continue
            selected += 1
            bin_points.extend(_collect_points_for_entry(entry, source_index, trace, bin_spec, args))
            if selected % max(1, args.progress_every_selected) == 0:
                print(json.dumps(_collect_progress(bin_spec, source_index, selected, bin_points, n_values, args.n_per_kind_level)), flush=True)
            if selected >= args.max_selected_instances:
                print(json.dumps({"phase": "collect_stop_max_selected", "difficulty_bin": bin_spec["label"], "selected": selected, "source_index": source_index}), flush=True)
                break
            if _has_coverage(bin_points, n_values, args.n_per_kind_level):
                progress = _collect_progress(bin_spec, source_index, selected, bin_points, n_values, args.n_per_kind_level)
                progress["phase"] = "collect_stop_coverage"
                print(json.dumps(progress), flush=True)
                break
            if args.progress_every_scan > 0 and (source_index + 1) % args.progress_every_scan == 0:
                print(json.dumps(_collect_progress(bin_spec, source_index, selected, bin_points, n_values, args.n_per_kind_level)), flush=True)
        all_points.extend(bin_points)
        for kind in ["branch", "backtrack"]:
            for n_dead in n_values:
                eligible = sum(1 for point in bin_points if point["kind"] == kind and len(point["dead_events"]) >= n_dead)
                coverage_rows.append({"difficulty_bin": bin_spec["label"], "kind": kind, "N": n_dead, "eligible_points": eligible, "required_points": args.n_per_kind_level})
    return all_points, preflight_rows, coverage_rows


def _collect_progress(bin_spec: dict[str, Any], source_index: int, selected: int, points: list[dict[str, Any]], n_values: list[int], target: int) -> dict[str, Any]:
    branch_points = sum(1 for point in points if point["kind"] == "branch")
    backtrack_points = sum(1 for point in points if point["kind"] == "backtrack")
    min_by_kind: dict[str, int] = {}
    for kind in ["branch", "backtrack"]:
        eligibles = [sum(1 for point in points if point["kind"] == kind and len(point["dead_events"]) >= n_dead) for n_dead in n_values]
        min_by_kind[kind] = min(eligibles) if eligibles else 0
    return {
        "phase": "collect_progress",
        "difficulty_bin": bin_spec["label"],
        "source_index": int(source_index),
        "selected": int(selected),
        "branch_points": branch_points,
        "backtrack_points": backtrack_points,
        "min_eligible_per_N": min_by_kind,
        "target_per_kind_N": int(target),
    }


def _load_or_collect_points(args: argparse.Namespace, bins: list[dict[str, Any]], n_values: list[int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], bool]:
    if args.points_path and args.points_path.exists():
        payload = _read_json(args.points_path)
        return list(payload.get("points", [])), list(payload.get("preflight_rows", [])), list(payload.get("coverage", [])), True
    points, preflight_rows, coverage_rows = _collect_points(args, bins, n_values)
    if args.points_path:
        _write_json(args.points_path, {
            "schema_version": "kvcache_decision_probe_points_v0",
            "status": STATUS_POINTS_COMPLETE,
            "generated_at": _now(),
            "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()},
            "coverage": coverage_rows,
            "preflight_rows": preflight_rows,
            "points": points,
            "source": SOURCE,
            "provenance": "kvcache_decision_probe_points_v0",
        })
    return points, preflight_rows, coverage_rows, False


def _has_coverage(points: list[dict[str, Any]], n_values: list[int], target: int) -> bool:
    for kind in ["branch", "backtrack"]:
        for n_dead in n_values:
            if sum(1 for point in points if point["kind"] == kind and len(point["dead_events"]) >= n_dead) < target:
                return False
    return True


def _sample_points(points: list[dict[str, Any]], n_values: list[int], target: int) -> list[tuple[int, dict[str, Any], int]]:
    sampled_pairs: list[tuple[dict[str, Any], int]] = []
    groups = sorted({(point["difficulty_bin"], point["kind"]) for point in points})
    for difficulty_bin, kind in groups:
        subset = [point for point in points if point["difficulty_bin"] == difficulty_bin and point["kind"] == kind]
        subset.sort(key=lambda point: (int(point["source_index"]), int(point["step"])))
        for n_dead in n_values:
            eligible = [point for point in subset if len(point["dead_events"]) >= n_dead]
            sampled_pairs.extend((point, n_dead) for point in eligible[:target])
    return [(index, point, n_dead) for index, (point, n_dead) in enumerate(sampled_pairs)]


def _prompt_for_point(point: dict[str, Any], n_dead: int) -> tuple[str, list[int], int]:
    context_parts = [
        "Graph_color decision probe. Use the live path as the current state.",
        "Return only one integer; do not explain.",
        "Problem:",
        str(point["problem"]),
        _live_path(point["live_register"]),
    ]
    dead_text = _dead_history(point["dead_events"], n_dead)
    if dead_text:
        context_parts.append(dead_text)
    if point["kind"] == "branch":
        candidates = [int(value) for value in point["domain"]]
        context_parts.extend([
            "NEXT_BRANCH_DECISION",
            f"current_variable={int(point['current_vertex'])}",
            f"remaining_domain={candidates}",
            f"assigned_neighbors={point['assigned_neighbors']}",
            f"already_tried_values={point['already_tried_values']}",
            f"valid_color_candidates={candidates}",
            "answer=",
        ])
    else:
        candidates = [int(item["entry_index"]) for item in point["bounded_register"]]
        context_parts.extend([
            "NEXT_BACKTRACK_DECISION",
            f"conflict_variable={int(point['conflict_vertex'])}",
            f"conflict_blockers={point['conflict_blockers']}",
            f"bounded_register={point['bounded_register']}",
            f"valid_entry_index_candidates={candidates}",
            "answer=",
        ])
    return "\n".join(context_parts), candidates, int(point["oracle_value"])


@torch.no_grad()
def _score_next_integer_batch(model: Any, tokenizer: Any, prompts: list[str], candidates_by_prompt: list[list[int]]) -> list[tuple[int, dict[int, float], float]]:
    encoded = tokenizer(prompts, return_tensors="pt", add_special_tokens=False, padding=True)
    ids = encoded.input_ids.to(model.device)
    attention_mask = encoded.attention_mask.to(model.device)
    out = model(input_ids=ids, attention_mask=attention_mask, use_cache=False)
    last_positions = attention_mask.sum(dim=1) - 1
    batch_indices = torch.arange(ids.shape[0], device=model.device)
    log_probs = torch.log_softmax(out.logits[batch_indices, last_positions, :], dim=-1)
    scored: list[tuple[int, dict[int, float], float]] = []
    for row_index, candidates in enumerate(candidates_by_prompt):
        scores: dict[int, float] = {}
        for candidate in candidates:
            token_scores: list[float] = []
            for form in (str(candidate), " " + str(candidate), "\n" + str(candidate)):
                token_ids = tokenizer(form, add_special_tokens=False).input_ids
                if token_ids:
                    token_scores.append(float(log_probs[row_index, int(token_ids[0])].item()))
            scores[int(candidate)] = max(token_scores) if token_scores else float("-inf")
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        predicted = int(ranked[0][0])
        margin = float(ranked[0][1] - ranked[1][1]) if len(ranked) > 1 else 0.0
        scored.append((predicted, scores, margin))
    return scored


def _checkpoint_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if str(path):
        _write_json(path, rows)


def _evaluate(points_with_n: list[tuple[int, dict[str, Any], int]], model: Any, tokenizer: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = _read_json(args.checkpoint_path) if args.resume else []
    if isinstance(rows, dict):
        rows = rows.get("rows", [])
    rows = list(rows or [])
    done = {int(row["row_index"]) for row in rows if "row_index" in row}
    pending = [(row_index, point, n_dead) for row_index, point, n_dead in points_with_n if int(row_index) not in done]
    for batch_start in range(0, len(pending), args.batch_size):
        batch = pending[batch_start: batch_start + args.batch_size]
        prompts: list[str] = []
        candidates_by_prompt: list[list[int]] = []
        oracles: list[int] = []
        prompt_tokens: list[int] = []
        for _, point, n_dead in batch:
            prompt, candidates, oracle = _prompt_for_point(point, n_dead)
            prompts.append(prompt)
            candidates_by_prompt.append(candidates)
            oracles.append(oracle)
            prompt_tokens.append(len(tokenizer(prompt, add_special_tokens=False).input_ids))
        scored = _score_next_integer_batch(model, tokenizer, prompts, candidates_by_prompt)
        for local_index, (row_index, point, n_dead) in enumerate(batch):
            predicted, scores, margin = scored[local_index]
            oracle = oracles[local_index]
            rows.append({
                "row_index": int(row_index),
                "shard_index": int(args.shard_index),
                "num_shards": int(args.num_shards),
                "difficulty_bin": point["difficulty_bin"],
                "num_vertices": point["num_vertices"],
                "edge_probability": point["edge_probability"],
                "source_index": point["source_index"],
                "step": point["step"],
                "kind": point["kind"],
                "N": int(n_dead),
                "condition": "clean" if n_dead == 0 else "polluted",
                "dead_events_available": len(point["dead_events"]),
                "context_tokens": int(prompt_tokens[local_index]),
                "prompt_sha1": _sha1(prompts[local_index]),
                "candidates": candidates_by_prompt[local_index],
                "oracle_value": oracle,
                "predicted_value": predicted,
                "correct": predicted == oracle,
                "score_margin": margin,
                "candidate_scores": {str(key): value for key, value in sorted(scores.items())},
                "source": SOURCE,
                "provenance": "kvcache_decision_probe_row_v0",
            })
        _checkpoint_rows(args.checkpoint_path, rows)
        print(json.dumps({"shard_index": args.shard_index, "evaluated_rows": len(rows), "pending_rows": max(0, len(pending) - batch_start - len(batch))}), flush=True)
    rows.sort(key=lambda row: int(row["row_index"]))
    return rows


def _summarize(rows: list[dict[str, Any]], n_values: list[int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    def accuracy(subset: list[dict[str, Any]]) -> float | None:
        return mean(float(row["correct"]) for row in subset) if subset else None

    by_N_kind: list[dict[str, Any]] = []
    groups = sorted({(row["difficulty_bin"], row["kind"], int(row["N"])) for row in rows})
    for difficulty_bin, kind, n_dead in groups:
        subset = [row for row in rows if row["difficulty_bin"] == difficulty_bin and row["kind"] == kind and int(row["N"]) == n_dead]
        by_N_kind.append({
            "difficulty_bin": difficulty_bin,
            "kind": kind,
            "N": n_dead,
            "n": len(subset),
            "accuracy_vs_oracle": accuracy(subset),
            "mean_context_tokens": mean(int(row["context_tokens"]) for row in subset),
            "mean_score_margin": mean(float(row["score_margin"]) for row in subset),
            "source": SOURCE,
            "provenance": "kvcache_decision_probe_by_N_kind_v0",
        })

    overall: list[dict[str, Any]] = []
    for kind in ["branch", "backtrack", "all"]:
        for n_dead in n_values:
            subset = [row for row in rows if int(row["N"]) == n_dead and (kind == "all" or row["kind"] == kind)]
            if not subset:
                continue
            overall.append({"kind": kind, "N": n_dead, "n": len(subset), "accuracy_vs_oracle": accuracy(subset), "mean_context_tokens": mean(int(row["context_tokens"]) for row in subset), "source": SOURCE, "provenance": "kvcache_decision_probe_overall_by_N_v0"})

    max_n = max(n_values)
    def acc_for(kind: str, n_dead: int) -> float | None:
        subset = [row for row in rows if int(row["N"]) == n_dead and (kind == "all" or row["kind"] == kind)]
        return accuracy(subset)

    branch_drop = None if acc_for("branch", 0) is None or acc_for("branch", max_n) is None else acc_for("branch", 0) - acc_for("branch", max_n)
    backtrack_drop = None if acc_for("backtrack", 0) is None or acc_for("backtrack", max_n) is None else acc_for("backtrack", 0) - acc_for("backtrack", max_n)
    overall_drop = None if acc_for("all", 0) is None or acc_for("all", max_n) is None else acc_for("all", 0) - acc_for("all", max_n)
    fork = {
        "N_max": max_n,
        "branch_accuracy_N0": acc_for("branch", 0),
        "branch_accuracy_Nmax": acc_for("branch", max_n),
        "branch_drop_N0_to_Nmax": branch_drop,
        "backtrack_accuracy_N0": acc_for("backtrack", 0),
        "backtrack_accuracy_Nmax": acc_for("backtrack", max_n),
        "backtrack_drop_N0_to_Nmax": backtrack_drop,
        "overall_accuracy_N0": acc_for("all", 0),
        "overall_accuracy_Nmax": acc_for("all", max_n),
        "overall_drop_N0_to_Nmax": overall_drop,
        "DP_1_accuracy_falls_with_N": bool(overall_drop is not None and overall_drop > 0),
        "DP_2_backtrack_falls_faster_than_branch": bool(branch_drop is not None and backtrack_drop is not None and backtrack_drop > branch_drop),
        "base_weak_at_N0_branch_below_0p5": bool(acc_for("branch", 0) is not None and acc_for("branch", 0) < 0.5),
        "base_weak_at_N0_backtrack_below_0p5": bool(acc_for("backtrack", 0) is not None and acc_for("backtrack", 0) < 0.5),
        "source": SOURCE,
        "provenance": "kvcache_decision_probe_fork_verdicts_v0",
    }
    return by_N_kind, overall, fork


def run(args: argparse.Namespace) -> dict[str, Any]:
    km3 = _read_json(args.km3_real_prompt)
    if km3.get("status") != "KVCACHE_REAL_PROMPT_KM3_PASS":
        payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_PREFLIGHT_FAIL, "reason": "KM3 real prompt gate did not pass", "km3_real_prompt": km3, "source": SOURCE, "provenance": SCHEMA_VERSION}
        _write_json(args.output, payload)
        return payload
    bins = _parse_bins(args.bins)
    n_values = _parse_ints(args.n_values)
    points, preflight_rows, coverage_rows, points_loaded_from_cache = _load_or_collect_points(args, bins, n_values)
    underfilled = [row for row in coverage_rows if int(row["eligible_points"]) < int(row["required_points"])]
    if underfilled and not args.allow_underfilled:
        payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_PREFLIGHT_FAIL, "reason": "not enough decision points for requested per-bin/kind/N coverage", "coverage": coverage_rows, "underfilled": underfilled, "preflight_rows": preflight_rows, "source": SOURCE, "provenance": SCHEMA_VERSION}
        _write_json(args.output, payload)
        return payload
    sampled_all = _sample_points(points, n_values, args.n_per_kind_level)
    if args.collect_only:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "status": STATUS_POINTS_COMPLETE,
            "generated_at": _now(),
            "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()},
            "coverage": coverage_rows,
            "preflight_summary": {"preflight_rows": len(preflight_rows), "collected_points": len(points), "sampled_rows_all_shards": len(sampled_all), "points_loaded_from_cache": points_loaded_from_cache},
            "source": SOURCE,
            "provenance": SCHEMA_VERSION,
        }
        _write_json(args.output, payload)
        return payload
    sampled = [(row_index, point, n_dead) for row_index, point, n_dead in sampled_all if int(row_index) % int(args.num_shards) == int(args.shard_index)]
    model, tokenizer = _load_model(args)
    rows = _evaluate(sampled, model, tokenizer, args)
    by_N_kind, overall_by_N, fork = _summarize(rows, n_values)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()},
        "km3_real_prompt": {"KM3_PASS": km3.get("overall_pass"), "status": km3.get("status"), "max_abs_logit_delta": km3.get("max_abs_logit_delta")},
        "coverage": coverage_rows,
        "preflight_summary": {"preflight_rows": len(preflight_rows), "collected_points": len(points), "sampled_rows_all_shards": len(sampled_all), "sampled_rows_this_shard": len(sampled), "evaluated_rows": len(rows), "points_loaded_from_cache": points_loaded_from_cache, "official_scoring_used_for_trajectory_selection": True, "scoring_mode": "batched_next_token_integer_choice"},
        "accuracy_by_N_kind": by_N_kind,
        "overall_by_N": overall_by_N,
        "fork_verdicts": fork,
        "rows": rows,
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run clean-vs-polluted graph_color decision probe.")
    parser.add_argument("--output", type=Path, default=Path("results/kvcache_decision_probe/decision_probe.json"))
    parser.add_argument("--checkpoint-path", type=Path, default=Path("results/kvcache_decision_probe/decision_probe_checkpoint.json"))
    parser.add_argument("--points-path", type=Path, default=None)
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--km3-real-prompt", type=Path, default=Path("results/kvcache_exactness/km3_real_graph_color_prompt_qwen3_fp32.json"))
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scan-limit", type=int, default=5000)
    parser.add_argument("--max-selected-instances", type=int, default=200)
    parser.add_argument("--n-per-kind-level", type=int, default=30)
    parser.add_argument("--min-backtracks", type=int, default=4)
    parser.add_argument("--node-cap", type=int, default=500)
    parser.add_argument("--register-window", type=int, default=8)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--order-mode", default="degree_desc", choices=["degree_desc", "natural"])
    parser.add_argument("--bins", default="v14_p04:14:0.4,v16_p04:16:0.4,v18_p04:18:0.4")
    parser.add_argument("--n-values", default="0,2,4,8,16,32")
    parser.add_argument("--allow-underfilled", action="store_true")
    parser.add_argument("--progress-every-scan", type=int, default=100)
    parser.add_argument("--progress-every-selected", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
