"""Backjump-only LoRA data, training, and evaluation for graph_color KV-cache search."""

from __future__ import annotations

import argparse
import copy
from collections import Counter, defaultdict
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
from statistics import mean
from typing import Any, Iterable

import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel
from torch.utils.data import DataLoader, Dataset
from torch.utils.data.distributed import DistributedSampler
from transformers import AutoModelForCausalLM, AutoTokenizer

from peft import LoraConfig, PeftModel, TaskType, get_peft_model

from analysis.kvcache_decision_probe import _parse_bins, _parse_ints
from analysis.kvcache_exactness_gate import _cache_inventory, _cache_seq_length, _crop_cache, _deviation, _different_token
from analysis.kvcache_graph_color_search import _feed, _write_json
from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE
from experiments.rung1_reasoning_gym_bounded_register import (
    _clean_trace,
    _current_domain,
    _deadend_nogood,
    _ensure_reasoning_gym,
    _graph_color_view,
    _official_answer,
    _official_score,
)


SCHEMA_VERSION = "kvcache_backjump_lora_v0"
STATUS_DATA_COMPLETE = "KVCACHE_BACKJUMP_LORA_DATA_COMPLETE"
STATUS_TRAIN_COMPLETE = "KVCACHE_BACKJUMP_LORA_TRAIN_COMPLETE"
STATUS_EVAL_COMPLETE = "KVCACHE_BACKJUMP_LORA_EVAL_COMPLETE"
STATUS_PREFLIGHT_FAIL = "KVCACHE_BACKJUMP_LORA_PREFLIGHT_FAIL"
STATUS_KM3_PASS = "KVCACHE_BACKJUMP_LORA_KM3_PASS"
STATUS_KM3_FAIL = "KVCACHE_BACKJUMP_LORA_KM3_FAIL"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    path = path if path.is_absolute() else REPO_ROOT / path
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    path = path if path.is_absolute() else REPO_ROOT / path
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    print(json.dumps({"path": str(path.relative_to(REPO_ROOT)), "rows": sum(1 for _ in _read_jsonl(path))}), flush=True)


def _hash_float(text: str) -> float:
    raw = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(raw, "big") / float(2**64 - 1)


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


def _instance_id(bin_label: str, source_index: int) -> str:
    return f"{bin_label}_{source_index:04d}"


def _split_for_instance(instance_id: str, bin_label: str, args: argparse.Namespace) -> str:
    if bin_label.startswith("v18"):
        return "ood_eval"
    return "train" if _hash_float(instance_id) < args.train_fraction else "val"


def _checkpoint_rows(register: list[dict[str, Any]], start: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for local_index, item in enumerate(register[start:]):
        rows.append({
            "idx": local_index,
            "var": int(item["vertex"]),
            "color": int(item["color"]),
            "order_index": int(item["order_index"]),
        })
    return rows


def _backjump_prompt(example: dict[str, Any]) -> str:
    live_rows = [
        {"var": int(item["vertex"]), "color": int(item["color"]), "order_index": int(item["order_index"])}
        for item in example["live_register"]
    ]
    lines = [
        "Graph_color backjump target decision.",
        "Return only one entry_index integer from valid_entry_index_candidates; do not explain.",
        "Problem:",
        str(example["problem"]),
        "LIVE_PATH=" + json.dumps(live_rows, separators=(",", ":")),
        "DEAD_END",
        f"conflict_variable={int(example['conflict_vertex'])}",
        "conflict_blockers=" + json.dumps(example["conflict_blockers"], separators=(",", ":")),
        "open_checkpoints=" + json.dumps(example["open_checkpoints"], separators=(",", ":")),
        "valid_entry_index_candidates=" + json.dumps(example["candidate_indices"], separators=(",", ":")),
        "answer=",
    ]
    return "\n".join(lines)


def _conflict_analysis_prompt(entry: dict[str, Any], view: dict[str, Any], vertex: int, assignment: dict[int, int], tried: dict[int, set[int]], register: list[dict[str, Any]], open_checkpoints: list[dict[str, Any]], args: argparse.Namespace) -> str:
    register_by_vertex = {int(item["vertex"]): item for item in register}
    open_index_by_vertex = {int(item["var"]): int(item["idx"]) for item in open_checkpoints}
    assigned_neighbors: list[dict[str, Any]] = []
    for neighbor in sorted(view["adjacency"][vertex]):
        if int(neighbor) not in assignment:
            continue
        source = register_by_vertex.get(int(neighbor), {})
        assigned_neighbors.append({
            "neighbor": int(neighbor),
            "color": int(assignment[int(neighbor)]),
            "step": int(source.get("order_index", -1)),
            "open_idx": open_index_by_vertex.get(int(neighbor)),
        })
    blockers_by_color: dict[int, list[dict[str, Any]]] = {int(color): [] for color in view["color_options"]}
    for row in assigned_neighbors:
        blockers_by_color[int(row["color"])].append(row)
    blockers_by_color = {color: sorted(rows, key=lambda item: int(item["step"])) for color, rows in blockers_by_color.items()}
    assignment_rows = [
        {"var": int(item["vertex"]), "color": int(item["color"]), "step": int(item["order_index"])}
        for item in register
        if int(item["vertex"]) in assignment
    ]
    checkpoint_lines = [
        f"  {int(item['idx'])}: {int(item['var'])} = {int(item['color'])} @ step{int(item['order_index'])}"
        for item in open_checkpoints
    ]
    if args.cot_prompt_style == "per_color":
        rule = "For each color, use the first item in blockers_by_color as that color's blocker. If that first item has open_idx=null or open_idx is not in the valid target indices, write not-open for that color and do not replace it with a later duplicate. BACKJUMP is the non-null first-item blocker with the largest step. Use only valid target indices as BACKJUMP values; step numbers and vertex ids are not target indices."
    else:
        rule = "Find assigned neighbor blockers of the dead-end variable. Pick the deepest open checkpoint among those blockers."
    lines = [
        "Graph_color conflict-analysis backjump targeting.",
        "Use only the visible state below. Be terse. No markdown. No bullets.",
        f"Dead end: variable {int(vertex)} has no legal color.",
        "Color options: " + json.dumps([int(item) for item in view["color_options"]], separators=(",", ":")),
        f"Already tried colors for {int(vertex)}: " + json.dumps(sorted(int(item) for item in tried[int(vertex)]), separators=(",", ":")),
        f"Neighbors of {int(vertex)} that are currently assigned: " + json.dumps(assigned_neighbors, separators=(",", ":")),
        "blockers_by_color sorted earliest-first: " + json.dumps(blockers_by_color, separators=(",", ":")),
        "Current assignment along the live path: " + json.dumps(assignment_rows, separators=(",", ":")),
        "Open checkpoints you may backjump to (index: variable = color @ step):",
        *(checkpoint_lines or ["  <none>"]),
        "Valid target indices: " + json.dumps([int(item["idx"]) for item in open_checkpoints], separators=(",", ":")),
        "Hard constraint: the final BACKJUMP value must be one of these valid target indices exactly. Any other integer is invalid.",
        "Hard constraint: never output a step number, vertex id, color, null, or a number outside valid target indices after BACKJUMP.",
        rule,
        "Fill this exact template. Produce no other text.",
        "blocked: <color->earliest-neighbor/open_idx>",
        "conflict_set: <only per-color earliest open_idx values>",
        "deepest_open_checkpoint: <one valid target index>",
        "BACKJUMP: <one valid target index>",
        "Now fill it:",
        "blocked:",
    ]
    return "\n".join(lines) + "\n"


def _conflict_blocker_tables(view: dict[str, Any], vertex: int, assignment: dict[int, int], register: list[dict[str, Any]], open_checkpoints: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    register_by_vertex = {int(item["vertex"]): item for item in register}
    open_index_by_vertex = {int(item["var"]): int(item["idx"]) for item in open_checkpoints}
    assigned_neighbors: list[dict[str, Any]] = []
    for neighbor in sorted(view["adjacency"][vertex]):
        if int(neighbor) not in assignment:
            continue
        source = register_by_vertex.get(int(neighbor), {})
        assigned_neighbors.append({
            "neighbor": int(neighbor),
            "color": int(assignment[int(neighbor)]),
            "step": int(source.get("order_index", -1)),
            "open_idx": open_index_by_vertex.get(int(neighbor)),
        })
    blockers_by_color: dict[int, list[dict[str, Any]]] = {int(color): [] for color in view["color_options"]}
    for row in assigned_neighbors:
        blockers_by_color[int(row["color"])].append(row)
    blockers_by_color = {color: sorted(rows, key=lambda item: int(item["step"])) for color, rows in blockers_by_color.items()}
    return assigned_neighbors, blockers_by_color


def _render_gold_conflict_derivation(view: dict[str, Any], vertex: int, assignment: dict[int, int], register: list[dict[str, Any]], open_checkpoints: list[dict[str, Any]], target_idx: int) -> str:
    _, blockers_by_color = _conflict_blocker_tables(view, vertex, assignment, register, open_checkpoints)
    blocked_parts: list[str] = []
    conflict_parts: list[str] = []
    candidates: list[dict[str, Any]] = []
    for color in [int(item) for item in view["color_options"]]:
        first = blockers_by_color.get(color, [])[:1]
        if not first:
            blocked_parts.append(f"{color}->none")
            conflict_parts.append(f"{color}:none")
            continue
        row = first[0]
        open_idx = row.get("open_idx")
        idx_text = "not-open" if open_idx is None else str(int(open_idx))
        blocked_parts.append(f"{color}->{int(row['neighbor'])}/{idx_text}")
        conflict_parts.append(f"{color}:{idx_text}")
        if open_idx is not None:
            candidates.append(row)
    if candidates:
        deepest = max(candidates, key=lambda item: int(item["step"]))
        deepest_text = str(int(deepest["open_idx"]))
    else:
        deepest_text = str(int(target_idx))
    return "\n".join([
        "blocked: " + ",".join(blocked_parts),
        "conflict_set: " + ",".join(conflict_parts),
        "deepest_open_checkpoint: " + deepest_text,
        f"BACKJUMP: {int(target_idx)}",
    ])


def _branch_prompt(entry: dict[str, Any], vertex: int, domain: list[int], neighbors: list[dict[str, int]], tried: set[int]) -> str:
    return "\n".join([
        "Graph_color branch value decision.",
        "Return only one color integer from valid_color_candidates; do not explain.",
        "Problem:",
        str(entry.get("question", "")),
        f"current_variable={int(vertex)}",
        "assigned_neighbors=" + json.dumps(neighbors, separators=(",", ":")),
        "already_tried_values=" + json.dumps(sorted(int(item) for item in tried), separators=(",", ":")),
        "valid_color_candidates=" + json.dumps([int(item) for item in domain], separators=(",", ":")),
        "answer=",
    ])


def _collect_examples_for_entry(entry: dict[str, Any], source_index: int, trace: dict[str, Any], bin_spec: dict[str, Any], r_values: list[int], args: argparse.Namespace) -> list[dict[str, Any]]:
    view = _graph_color_view(entry, args.order_mode)
    position = {vertex: index for index, vertex in enumerate(view["order"])}
    assignment: dict[int, int] = {}
    tried: dict[int, set[int]] = defaultdict(set)
    register: list[dict[str, Any]] = []
    examples: list[dict[str, Any]] = []
    cursor = 0
    step = 0
    bin_label = str(bin_spec["label"])
    instance_id = _instance_id(bin_label, source_index)
    split = _split_for_instance(instance_id, bin_label, args)
    while step < args.node_cap:
        if cursor >= len(view["order"]):
            break
        vertex = view["order"][cursor]
        domain = _current_domain(view, vertex, assignment, tried)
        step += 1
        if domain:
            color = int(domain[0])
            tried[vertex].add(color)
            assignment[vertex] = color
            register.append({"vertex": int(vertex), "color": color, "order_index": int(cursor)})
            cursor += 1
            continue
        if not register:
            break
        nogood = _deadend_nogood(view, vertex, assignment, position)
        oracle_vertex = max(nogood, key=lambda item: position[item]) if nogood else int(register[-1]["vertex"])
        oracle_abs = max((index for index, item in enumerate(register) if int(item["vertex"]) == int(oracle_vertex)), default=len(register) - 1)
        for r_value in r_values:
            start = max(0, len(register) - int(r_value))
            target_idx = oracle_abs - start
            if not (0 <= target_idx < len(register[start:])):
                continue
            open_checkpoints = _checkpoint_rows(register, start)
            example = {
                "schema_version": "kvcache_backjump_example_v0",
                "example_id": f"{instance_id}_step{step:04d}_R{int(r_value)}",
                "instance_id": instance_id,
                "bin": bin_label,
                "split": split,
                "source_index": int(source_index),
                "num_vertices": int(bin_spec["num_vertices"]),
                "edge_probability": float(bin_spec["edge_probability"]),
                "R": int(r_value),
                "problem": entry.get("question", ""),
                "live_register": [dict(item) for item in register],
                "open_checkpoints": open_checkpoints,
                "candidate_indices": [int(item["idx"]) for item in open_checkpoints],
                "target_idx": int(target_idx),
                "target_var": int(register[oracle_abs]["vertex"]),
                "target_abs_depth": int(oracle_abs),
                "chrono_idx": len(open_checkpoints) - 1,
                "num_open": len(open_checkpoints),
                "chance": 1.0 / len(open_checkpoints),
                "conflict_vertex": int(vertex),
                "conflict_blockers": sorted(int(item) for item in nogood),
                "trace_total_retractions": int(trace.get("total_retractions", 0)),
                "trace_steps": int(trace.get("steps", 0)),
                "source": SOURCE,
                "provenance": "kvcache_backjump_lora_data_v0",
            }
            example["prompt"] = _backjump_prompt(example)
            example["target_text"] = " " + str(int(target_idx))
            examples.append(example)
        popped = register[oracle_abs:]
        for item in popped:
            assignment.pop(int(item["vertex"]), None)
        for item in popped[1:]:
            tried[int(item["vertex"])] = set()
        tried[vertex] = set()
        cursor = int(register[oracle_abs]["order_index"])
        del register[oracle_abs:]
    return examples


def _summarize_examples(examples: list[dict[str, Any]]) -> dict[str, Any]:
    def group_count(keys: list[str]) -> list[dict[str, Any]]:
        counter: Counter[tuple[Any, ...]] = Counter(tuple(row[key] for key in keys) for row in examples)
        return [{**{key: value for key, value in zip(keys, group)}, "n": count} for group, count in sorted(counter.items())]

    chrono_hits = [int(row["target_idx"] == row["chrono_idx"]) for row in examples]
    return {
        "n_examples": len(examples),
        "splits": group_count(["split"]),
        "by_bin_split": group_count(["bin", "split"]),
        "by_R_split": group_count(["R", "split"]),
        "by_bin_R_split": group_count(["bin", "R", "split"]),
        "cbj_equals_chrono_rate": mean(chrono_hits) if chrono_hits else None,
        "mean_chance": mean(float(row["chance"]) for row in examples) if examples else None,
        "mean_num_open": mean(int(row["num_open"]) for row in examples) if examples else None,
    }


def build_data(args: argparse.Namespace) -> dict[str, Any]:
    bins = _parse_bins(args.bins)
    r_values = _parse_ints(args.r_values)
    all_examples: list[dict[str, Any]] = []
    preflight_rows: list[dict[str, Any]] = []
    for bin_spec in bins:
        dataset = _make_dataset(args, bin_spec)
        selected = 0
        print(json.dumps({"phase": "build_data_start_bin", "bin": bin_spec["label"]}), flush=True)
        for source_index in range(args.scan_limit):
            entry = dataset[source_index]
            entry.setdefault("metadata", {})["source_index"] = source_index
            trace = _clean_trace(entry, args.order_mode, args.node_cap, dataset)
            row = {"bin": bin_spec["label"], "source_index": source_index, **trace}
            row["selected"] = bool(trace.get("solved") and int(trace.get("total_retractions", 0)) >= args.min_backtracks)
            preflight_rows.append(row)
            if not row["selected"]:
                continue
            selected += 1
            all_examples.extend(_collect_examples_for_entry(entry, source_index, trace, bin_spec, r_values, args))
            if selected % max(1, args.progress_every_selected) == 0:
                print(json.dumps({"phase": "build_data_progress", "bin": bin_spec["label"], "selected": selected, "examples": len(all_examples), "source_index": source_index}), flush=True)
            if selected >= args.max_selected_instances:
                break
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    split_rows = {
        "train": [row for row in all_examples if row["split"] == "train"],
        "val": [row for row in all_examples if row["split"] == "val"],
        "ood_eval": [row for row in all_examples if row["split"] == "ood_eval"],
    }
    _write_jsonl(output_dir / "all_examples.jsonl", all_examples)
    for split, rows in split_rows.items():
        _write_jsonl(output_dir / f"{split}.jsonl", rows)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_DATA_COMPLETE,
        "generated_at": _now(),
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()},
        "summary": _summarize_examples(all_examples),
        "preflight_rows": preflight_rows,
        "files": {split: str((output_dir / f"{split}.jsonl").relative_to(REPO_ROOT)) for split in split_rows},
        "all_examples": str((output_dir / "all_examples.jsonl").relative_to(REPO_ROOT)),
        "source": SOURCE,
        "provenance": "kvcache_backjump_lora_data_v0",
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def _collect_c2_examples_for_selected(model: Any, tokenizer: Any, selected: dict[str, Any], r_value: int, condition: str, args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entry = selected["entry"]
    view = _graph_color_view(entry, args.order_mode)
    position = {vertex: index for index, vertex in enumerate(view["order"])}
    assignment: dict[int, int] = {}
    tried: dict[int, set[int]] = defaultdict(set)
    register: list[dict[str, Any]] = []
    transcript = f"Graph_color C2 reasoning data collection condition={condition}.\nProblem:\n{entry.get('question','')}\n"
    _, cache, used = _feed(model, tokenizer, transcript, None)
    stats = Counter({"input_tokens": used, "total_tokens": used})
    rows: list[dict[str, Any]] = []
    cursor = 0
    decision_index = 0
    status = "UNKNOWN"
    while True:
        if int(stats["decision_points"]) >= args.call_cap:
            status = "CALL_CAP"
            break
        if cursor >= len(view["order"]):
            status = "SOLVED"
            break
        vertex = view["order"][cursor]
        domain = _current_domain(view, vertex, assignment, tried)
        if domain:
            neighbors = [{"neighbor": int(neighbor), "color": int(assignment[neighbor])} for neighbor in sorted(view["adjacency"][vertex]) if neighbor in assignment]
            checkpoint = _cache_seq_length(cache)
            if condition == "isolation":
                color = int(domain[0])
            else:
                prompt = "\nNEXT_BRANCH\n" + _branch_prompt(entry, int(vertex), [int(item) for item in domain], neighbors, tried[vertex])
                color, _, _, cache, branch_used = _score_prompt_candidates(model, tokenizer, prompt, [int(item) for item in domain], cache, disable_adapter=True)
                stats["input_tokens"] += branch_used
                stats["total_tokens"] += branch_used
            tried[vertex].add(int(color))
            assignment[vertex] = int(color)
            register.append({"vertex": int(vertex), "color": int(color), "order_index": int(cursor), "cache_pos": int(checkpoint)})
            event = f"\nBRANCH vertex={int(vertex)} color={int(color)} domain={list(map(int, domain))} tried={sorted(int(item) for item in tried[vertex])}\n"
            _, cache, event_used = _feed(model, tokenizer, event, cache)
            stats["input_tokens"] += event_used
            stats["total_tokens"] += event_used
            cursor += 1
            continue
        if r_value == 0 or not register:
            status = "FORWARD_DEAD_END"
            break
        nogood = _deadend_nogood(view, int(vertex), assignment, position)
        oracle_vertex = max(nogood, key=lambda item: position[item]) if nogood else int(register[-1]["vertex"])
        oracle_abs = max((index for index, item in enumerate(register) if int(item["vertex"]) == int(oracle_vertex)), default=len(register) - 1)
        start = max(0, len(register) - int(r_value))
        oracle_idx = oracle_abs - start
        if not (0 <= oracle_idx < len(register[start:])):
            status = "NO_RECOVERY_TARGET"
            break
        open_checkpoints = _checkpoint_rows(register, start)
        plain_prompt = "\nDEAD_END\n" + _conflict_analysis_prompt(entry, view, int(vertex), assignment, tried, register, open_checkpoints, args)
        train_prompt = _maybe_chat_prompt(tokenizer, plain_prompt, args)
        text, new_cache, usage = _generate_conflict_analysis(model, tokenizer, train_prompt, cache, int(args.cot_max_new_tokens))
        parsed = _parse_backjump_index(text, len(open_checkpoints))
        valid = bool(parsed.get("valid"))
        chosen_idx = int(parsed["raw_index"]) if valid else None
        exact = valid and chosen_idx == int(oracle_idx)
        gold_text = _render_gold_conflict_derivation(view, int(vertex), assignment, register, open_checkpoints, int(oracle_idx))
        target_text = text.strip() if exact and text.strip() else gold_text
        target_source = "star" if exact and text.strip() else "gold"
        instance_id = _instance_id(str(selected["bin"]), int(selected["source_index"]))
        rows.append({
            "schema_version": "kvcache_c2_reasoning_example_v0",
            "sft_task": "c2_reasoning",
            "example_id": f"{instance_id}_{condition}_R{int(r_value)}_de{decision_index:04d}",
            "instance_id": instance_id,
            "bin": str(selected["bin"]),
            "split": str(selected["split"]),
            "source_index": int(selected["source_index"]),
            "R": int(r_value),
            "condition": condition,
            "prompt": train_prompt,
            "plain_prompt": plain_prompt,
            "target_text": target_text,
            "target_source": target_source,
            "model_reasoning_text": text.strip(),
            "gold_reasoning_text": gold_text,
            "target_idx": int(oracle_idx),
            "chosen_idx": chosen_idx,
            "model_exact": bool(exact),
            "model_parseable": bool(parsed.get("parseable")),
            "model_valid": valid,
            "model_invalid_reason": parsed.get("invalid_reason"),
            "open_checkpoints": open_checkpoints,
            "candidate_indices": [int(item["idx"]) for item in open_checkpoints],
            "conflict_vertex": int(vertex),
            "conflict_blockers": sorted(int(item) for item in nogood),
            "source": SOURCE,
            "provenance": "kvcache_c2_reasoning_data_v0",
        })
        stats["decision_points"] += 1
        stats["input_tokens"] += int(usage["input_tokens"])
        stats["total_tokens"] += int(usage["total_tokens"])
        decision_index += 1
        if not valid:
            status = "INVALID_BACKJUMP_DECISION"
            break
        target_abs = start + int(chosen_idx)
        checkpoint = register[target_abs].get("cache_pos")
        if checkpoint is None:
            status = "CACHE_CHECKPOINT_MISSING"
            break
        cache, _ = _crop_cache(new_cache, int(checkpoint))
        popped = register[target_abs:]
        for item in popped:
            assignment.pop(int(item["vertex"]), None)
        for item in popped[1:]:
            tried[int(item["vertex"])] = set()
        tried[vertex] = set()
        cursor = int(register[target_abs]["order_index"])
        del register[target_abs:]
    return rows, {"status": status, "n_examples": len(rows), "decision_points": int(stats["decision_points"]), "input_tokens": int(stats["input_tokens"]), "total_tokens": int(stats["total_tokens"])}


def _summarize_c2_examples(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def group_count(keys: list[str]) -> list[dict[str, Any]]:
        counter: Counter[tuple[Any, ...]] = Counter(tuple(row.get(key) for key in keys) for row in rows)
        return [{**{key: value for key, value in zip(keys, group)}, "n": count} for group, count in sorted(counter.items())]

    return {
        "n_examples": len(rows),
        "splits": group_count(["split"]),
        "by_bin_split": group_count(["bin", "split"]),
        "by_bin_R_split": group_count(["bin", "R", "split"]),
        "by_target_source": group_count(["target_source"]),
        "by_R_target_source": group_count(["R", "target_source"]),
        "star_rate": mean(float(row.get("target_source") == "star") for row in rows) if rows else None,
        "model_exact_rate": mean(float(row.get("model_exact")) for row in rows) if rows else None,
        "model_parseable_rate": mean(float(row.get("model_parseable")) for row in rows) if rows else None,
        "model_valid_rate": mean(float(row.get("model_valid")) for row in rows) if rows else None,
    }


def _star_reasoning_indices_clean(text: str, candidates: list[int]) -> bool:
    allowed = {int(item) for item in candidates}
    if not allowed:
        return False
    checked: list[int] = []
    for raw in re.findall(r"/\s*(-?\d+)", text):
        checked.append(int(raw))
    for line in text.splitlines():
        lower = line.lower()
        if "conflict_set" in lower or "deepest_open_checkpoint" in lower or "backjump" in lower:
            checked.extend(int(raw) for raw in re.findall(r"(?<![A-Za-z_])-?\d+", line))
    return all(item in allowed for item in checked)


def repair_c2_data(args: argparse.Namespace) -> dict[str, Any]:
    input_dir = args.input_dir if args.input_dir.is_absolute() else REPO_ROOT / args.input_dir
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    rows = _read_jsonl(input_dir / "all_examples.jsonl")
    repaired: list[dict[str, Any]] = []
    repair_count = 0
    for row in rows:
        item = dict(row)
        if item.get("target_source") == "star" and not _star_reasoning_indices_clean(str(item.get("target_text", "")), [int(v) for v in item.get("candidate_indices", [])]):
            item["target_text"] = str(item.get("gold_reasoning_text", item.get("target_text", "")))
            item["target_source"] = "gold_format_repair"
            item["format_repair_reason"] = "star_reasoning_contains_out_of_range_intermediate_index"
            repair_count += 1
        repaired.append(item)
    output_dir.mkdir(parents=True, exist_ok=True)
    split_rows = {
        "train": [row for row in repaired if row["split"] == "train"],
        "val": [row for row in repaired if row["split"] == "val"],
        "ood_eval": [row for row in repaired if row["split"] == "ood_eval"],
    }
    _write_jsonl(output_dir / "all_examples.jsonl", repaired)
    for split, split_data in split_rows.items():
        _write_jsonl(output_dir / f"{split}.jsonl", split_data)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_DATA_COMPLETE,
        "generated_at": _now(),
        "config": {"input_dir": str(args.input_dir), "output_dir": str(args.output_dir)},
        "summary": {**_summarize_c2_examples(repaired), "format_repair_count": repair_count},
        "files": {split: str((output_dir / f"{split}.jsonl").relative_to(REPO_ROOT)) for split in split_rows},
        "all_examples": str((output_dir / "all_examples.jsonl").relative_to(REPO_ROOT)),
        "source": SOURCE,
        "provenance": "kvcache_c2_reasoning_data_repaired_v0",
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def collect_c2_data(args: argparse.Namespace) -> dict[str, Any]:
    model, tokenizer = _load_lora_model(args, training=False)
    bins = _parse_bins(args.bins)
    r_values = _parse_ints(args.r_values)
    conditions = [item.strip() for item in args.conditions.split(",") if item.strip()]
    state = _read_json(args.checkpoint_path) if args.resume and args.checkpoint_path.exists() else {"rows": [], "completed_tasks": []}
    if isinstance(state, list):
        rows = list(state)
        completed_tasks: set[str] = set()
    else:
        rows = list(state.get("rows", []))
        completed_tasks = set(str(item) for item in state.get("completed_tasks", []))
    preflight: list[dict[str, Any]] = []
    task_rows: list[dict[str, Any]] = []
    task_index = 0
    for bin_spec in bins:
        dataset = _make_dataset(args, bin_spec)
        selected: list[dict[str, Any]] = []
        for source_index in range(args.scan_limit):
            instance_id = _instance_id(str(bin_spec["label"]), source_index)
            split = _split_for_instance(instance_id, str(bin_spec["label"]), args)
            entry = dataset[source_index]
            entry.setdefault("metadata", {})["source_index"] = source_index
            trace = _clean_trace(entry, args.order_mode, args.node_cap, dataset)
            if trace.get("solved") and int(trace.get("total_retractions", 0)) >= args.min_backtracks:
                selected.append({"entry": entry, "source_index": source_index, "trace": trace, "bin": bin_spec["label"], "split": split})
            if len(selected) >= args.max_selected_instances:
                break
        preflight.append({"bin": bin_spec["label"], "selected": len(selected), "requested": args.max_selected_instances})
        for item in selected:
            for r_value in r_values:
                for condition in conditions:
                    current_task_index = task_index
                    task_index += 1
                    if current_task_index % int(args.num_shards) != int(args.shard_index):
                        continue
                    task_key = f"{item['bin']}:{int(item['source_index'])}:R{int(r_value)}:{condition}"
                    if task_key in completed_tasks:
                        continue
                    examples, task_meta = _collect_c2_examples_for_selected(model, tokenizer, item, int(r_value), condition, args)
                    for row in examples:
                        row["task_key"] = task_key
                        row["task_index"] = current_task_index
                        row["shard_index"] = int(args.shard_index)
                        row["num_shards"] = int(args.num_shards)
                    rows.extend(examples)
                    completed_tasks.add(task_key)
                    task_rows.append({"task_key": task_key, **task_meta})
                    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_DATA_COMPLETE, "generated_at": _now(), "rows": rows, "completed_tasks": sorted(completed_tasks), "task_rows": task_rows, "preflight": preflight, "planned_tasks_all_shards": task_index, "source": SOURCE, "provenance": "kvcache_c2_reasoning_collect_shard_v0"}
                    _write_json(args.checkpoint_path, payload)
                    print(json.dumps({"task_key": task_key, "examples": len(examples), "status": task_meta["status"], "rows": len(rows)}), flush=True)
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_DATA_COMPLETE, "generated_at": _now(), "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "rows": rows, "completed_tasks": sorted(completed_tasks), "task_rows": task_rows, "preflight": preflight, "planned_tasks_all_shards": task_index, "summary": _summarize_c2_examples(rows), "source": SOURCE, "provenance": "kvcache_c2_reasoning_collect_shard_v0"}
    _write_json(args.output, payload)
    return payload


def merge_c2_data(args: argparse.Namespace) -> dict[str, Any]:
    rows_by_id: dict[str, dict[str, Any]] = {}
    input_files: list[str] = []
    preflight: list[dict[str, Any]] = []
    completed_tasks: set[str] = set()
    for pattern in args.inputs:
        for path in sorted(Path().glob(pattern)):
            payload = _read_json(path)
            input_files.append(str(path))
            if isinstance(payload, list):
                rows = payload
            else:
                rows = payload.get("rows", [])
                preflight.extend(payload.get("preflight", []))
                completed_tasks.update(str(item) for item in payload.get("completed_tasks", []))
            for row in rows:
                rows_by_id[str(row["example_id"])] = row
    rows = [rows_by_id[key] for key in sorted(rows_by_id)]
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    split_rows = {
        "train": [row for row in rows if row["split"] == "train"],
        "val": [row for row in rows if row["split"] == "val"],
        "ood_eval": [row for row in rows if row["split"] == "ood_eval"],
    }
    _write_jsonl(output_dir / "all_examples.jsonl", rows)
    for split, split_data in split_rows.items():
        _write_jsonl(output_dir / f"{split}.jsonl", split_data)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_DATA_COMPLETE,
        "generated_at": _now(),
        "config": {"inputs": args.inputs, "output_dir": str(args.output_dir)},
        "input_files": input_files,
        "completed_tasks": sorted(completed_tasks),
        "summary": _summarize_c2_examples(rows),
        "preflight": preflight,
        "files": {split: str((output_dir / f"{split}.jsonl").relative_to(REPO_ROOT)) for split in split_rows},
        "all_examples": str((output_dir / "all_examples.jsonl").relative_to(REPO_ROOT)),
        "source": SOURCE,
        "provenance": "kvcache_c2_reasoning_data_merged_v0",
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


class BackjumpDataset(Dataset[dict[str, torch.Tensor]]):
    def __init__(self, rows: list[dict[str, Any]], tokenizer: Any, max_length: int) -> None:
        self.rows = rows
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        row = self.rows[index]
        prompt_ids = self.tokenizer(str(row["prompt"]), add_special_tokens=False).input_ids
        target_ids = self.tokenizer(str(row["target_text"]), add_special_tokens=False).input_ids
        if not target_ids:
            target_ids = self.tokenizer(str(row["target_idx"]), add_special_tokens=False).input_ids
        overflow = max(0, len(prompt_ids) + len(target_ids) - self.max_length)
        if overflow:
            prompt_ids = prompt_ids[overflow:]
        input_ids = prompt_ids + target_ids
        labels = [-100] * len(prompt_ids) + target_ids
        return {"input_ids": torch.tensor(input_ids, dtype=torch.long), "labels": torch.tensor(labels, dtype=torch.long)}


def _collate(batch: list[dict[str, torch.Tensor]], pad_token_id: int) -> dict[str, torch.Tensor]:
    max_len = max(int(item["input_ids"].shape[0]) for item in batch)
    input_ids = torch.full((len(batch), max_len), pad_token_id, dtype=torch.long)
    labels = torch.full((len(batch), max_len), -100, dtype=torch.long)
    attention_mask = torch.zeros((len(batch), max_len), dtype=torch.long)
    for index, item in enumerate(batch):
        length = int(item["input_ids"].shape[0])
        input_ids[index, :length] = item["input_ids"]
        labels[index, :length] = item["labels"]
        attention_mask[index, :length] = 1
    return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}


def _dtype(name: str, device: torch.device) -> torch.dtype:
    if name == "bf16" and device.type == "cuda":
        return torch.bfloat16
    if name == "fp16" and device.type == "cuda":
        return torch.float16
    return torch.float32


def _load_tokenizer(model_id: str) -> Any:
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    return tokenizer


def _load_base_model(args: argparse.Namespace, training: bool) -> Any:
    device = torch.device(args.device if torch.cuda.is_available() or not str(args.device).startswith("cuda") else "cpu")
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=_dtype(args.dtype, device), trust_remote_code=True).to(device)
    model.config.use_cache = not training
    return model.train() if training else model.eval()


def _distributed_state(args: argparse.Namespace) -> dict[str, Any]:
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    rank = int(os.environ.get("RANK", "0"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    distributed = world_size > 1
    if distributed:
        if torch.cuda.is_available():
            torch.cuda.set_device(local_rank)
            args.device = f"cuda:{local_rank}"
        if not dist.is_initialized():
            dist.init_process_group(backend="nccl" if torch.cuda.is_available() else "gloo")
    return {"distributed": distributed, "rank": rank, "local_rank": local_rank, "world_size": world_size, "is_main": rank == 0}


def _barrier(state: dict[str, Any]) -> None:
    if state.get("distributed") and dist.is_initialized():
        dist.barrier()


def _cleanup_distributed(state: dict[str, Any]) -> None:
    if state.get("distributed") and dist.is_initialized():
        dist.destroy_process_group()


def _unwrap_model(model: Any) -> Any:
    return model.module if isinstance(model, DistributedDataParallel) else model


def _model_device(model: Any) -> torch.device:
    return next(_unwrap_model(model).parameters()).device


def _load_lora_model(args: argparse.Namespace, training: bool) -> tuple[Any, Any]:
    tokenizer = _load_tokenizer(args.model)
    base = _load_base_model(args, training=training)
    if args.adapter_path:
        model = PeftModel.from_pretrained(base, args.adapter_path, is_trainable=training)
    elif training:
        config = LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
            target_modules=[item.strip() for item in args.target_modules.split(",") if item.strip()],
        )
        model = get_peft_model(base, config)
    else:
        model = base
    return (model.train() if training else model.eval()), tokenizer


def train(args: argparse.Namespace) -> dict[str, Any]:
    dist_state = _distributed_state(args)
    train_rows = _read_jsonl(args.train_jsonl)
    val_rows = _read_jsonl(args.val_jsonl)
    if not train_rows:
        payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_PREFLIGHT_FAIL, "reason": "no train rows", "source": SOURCE, "provenance": SCHEMA_VERSION}
        if dist_state["is_main"]:
            _write_json(args.output, payload)
        _cleanup_distributed(dist_state)
        return payload
    model, tokenizer = _load_lora_model(args, training=True)
    if dist_state["distributed"]:
        model = DistributedDataParallel(model, device_ids=[dist_state["local_rank"]], output_device=dist_state["local_rank"], find_unused_parameters=False)
    train_dataset = BackjumpDataset(train_rows, tokenizer, args.max_length)
    sampler = DistributedSampler(train_dataset, num_replicas=dist_state["world_size"], rank=dist_state["rank"], shuffle=True) if dist_state["distributed"] else None
    loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=sampler is None, sampler=sampler, collate_fn=lambda batch: _collate(batch, tokenizer.pad_token_id))
    optimizer = torch.optim.AdamW((param for param in _unwrap_model(model).parameters() if param.requires_grad), lr=args.learning_rate, weight_decay=args.weight_decay)
    history: list[dict[str, Any]] = []
    global_step = 0
    for epoch in range(args.epochs):
        if sampler is not None:
            sampler.set_epoch(epoch)
        losses: list[float] = []
        optimizer.zero_grad(set_to_none=True)
        for step, batch in enumerate(loader):
            batch = {key: value.to(_model_device(model)) for key, value in batch.items()}
            out = model(**batch)
            loss = out.loss / args.grad_accum_steps
            loss.backward()
            losses.append(float(out.loss.detach().float().cpu().item()))
            if (step + 1) % args.grad_accum_steps == 0 or (step + 1) == len(loader):
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                global_step += 1
                if dist_state["is_main"] and global_step % args.log_every == 0:
                    print(json.dumps({"epoch": epoch + 1, "global_step": global_step, "rank0_loss": losses[-1], "world_size": dist_state["world_size"]}), flush=True)
        if dist_state["is_main"]:
            _unwrap_model(model).eval()
            if args.full_sequence_val_loss or any(str(row.get("sft_task")) == "c2_reasoning" for row in val_rows[:1]):
                val_metrics = _evaluate_sft_loss(val_rows, _unwrap_model(model), tokenizer, args) if val_rows else {}
            else:
                val_metrics = evaluate_examples(val_rows[: args.max_val_examples], _unwrap_model(model), tokenizer, disable_adapter=False) if val_rows else {}
            _unwrap_model(model).train()
            history.append({"epoch": epoch + 1, "rank0_mean_train_loss": mean(losses) if losses else None, "val": val_metrics})
            print(json.dumps({"epoch": epoch + 1, "rank0_mean_train_loss": history[-1]["rank0_mean_train_loss"], "val": val_metrics, "world_size": dist_state["world_size"]}), flush=True)
        _barrier(dist_state)
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    if dist_state["is_main"]:
        output_dir.mkdir(parents=True, exist_ok=True)
        _unwrap_model(model).save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_TRAIN_COMPLETE,
        "generated_at": _now(),
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()},
        "n_train": len(train_rows),
        "n_val": len(val_rows),
        "global_steps": global_step,
        "distributed": {key: value for key, value in dist_state.items() if key != "is_main"},
        "history": history,
        "adapter_path": str(output_dir.relative_to(REPO_ROOT)),
        "source": SOURCE,
        "provenance": "kvcache_backjump_lora_train_v0",
    }
    if dist_state["is_main"]:
        _write_json(args.output, payload)
    _barrier(dist_state)
    _cleanup_distributed(dist_state)
    return payload


def _adapter_disabled(model: Any, disable: bool) -> Any:
    if disable and hasattr(model, "disable_adapter"):
        return model.disable_adapter()
    return nullcontext()


@torch.no_grad()
def _score_prompt_candidates(model: Any, tokenizer: Any, prompt: str, candidates: list[int], cache: Any | None = None, disable_adapter: bool = False) -> tuple[int, dict[int, float], float, Any, int]:
    ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(_model_device(model))
    with _adapter_disabled(model, disable_adapter):
        out = model(input_ids=ids, past_key_values=cache, use_cache=True)
    log_probs = torch.log_softmax(out.logits[:, -1, :], dim=-1)[0]
    scores: dict[int, float] = {}
    for candidate in candidates:
        token_scores: list[float] = []
        for form in (str(candidate), " " + str(candidate), "\n" + str(candidate)):
            token_ids = tokenizer(form, add_special_tokens=False).input_ids
            if token_ids:
                token_scores.append(float(log_probs[int(token_ids[0])].item()))
        scores[int(candidate)] = max(token_scores) if token_scores else float("-inf")
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    predicted = int(ranked[0][0])
    margin = float(ranked[0][1] - ranked[1][1]) if len(ranked) > 1 else 0.0
    return predicted, scores, margin, out.past_key_values, int(ids.shape[1])


def _is_conflict_analysis_policy(policy: str) -> bool:
    return policy in {"conflict_cot", "conflict_analysis", "c1_cot", "cot"}


@torch.no_grad()
def _generate_conflict_analysis(model: Any, tokenizer: Any, prompt: str, cache: Any | None, max_new_tokens: int) -> tuple[str, Any, dict[str, int]]:
    device = _model_device(model)
    ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(device)
    out = model(input_ids=ids, past_key_values=cache, use_cache=True)
    next_cache = out.past_key_values
    logits = out.logits[:, -1, :]
    generated: list[torch.Tensor] = []
    eos_ids = {token for token in [tokenizer.eos_token_id, tokenizer.pad_token_id] if token is not None}
    text = ""
    for _ in range(max_new_tokens):
        token = logits.argmax(dim=-1, keepdim=True)
        generated.append(token)
        text = tokenizer.decode(torch.cat(generated, dim=1)[0], skip_special_tokens=True)
        out = model(input_ids=token, past_key_values=next_cache, use_cache=True)
        next_cache = out.past_key_values
        logits = out.logits[:, -1, :]
        if int(token[0, 0].item()) in eos_ids:
            break
        if re.search(r"BACKJUMP\s*:\s*\d+", text, flags=re.IGNORECASE):
            break
    output_tokens = len(generated)
    return text.strip(), next_cache, {"input_tokens": int(ids.shape[1]), "output_tokens": output_tokens, "total_tokens": int(ids.shape[1]) + output_tokens}


def _parse_backjump_index(text: str, num_open: int) -> dict[str, Any]:
    matches = list(re.finditer(r"BACKJUMP\s*:\s*([+-]?\d+)", text, flags=re.IGNORECASE))
    if not matches:
        return {"parseable": False, "valid": False, "raw_index": None, "invalid_reason": "parse_fail"}
    raw_text = matches[-1].group(1)
    try:
        raw_index = int(raw_text)
    except Exception:
        return {"parseable": True, "valid": False, "raw_index": raw_text, "invalid_reason": "invalid_type"}
    if not 0 <= raw_index < int(num_open):
        return {"parseable": True, "valid": False, "raw_index": raw_index, "invalid_reason": "out_of_range"}
    return {"parseable": True, "valid": True, "raw_index": raw_index, "invalid_reason": None}


def _maybe_chat_prompt(tokenizer: Any, prompt: str, args: argparse.Namespace) -> str:
    if not bool(getattr(args, "cot_chat_template", True)) or not hasattr(tokenizer, "apply_chat_template"):
        return prompt
    messages = [
        {"role": "system", "content": "You are a terse graph-color conflict analyst. Follow the requested output format exactly."},
        {"role": "user", "content": prompt},
    ]
    try:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception:
        return prompt


@torch.no_grad()
def evaluate_examples(rows: list[dict[str, Any]], model: Any, tokenizer: Any, disable_adapter: bool) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "accuracy": None, "any_legal_rate": None, "chance": None}
    exact = 0
    legal = 0
    chance_values: list[float] = []
    for row in rows:
        prediction, _, _, _, _ = _score_prompt_candidates(model, tokenizer, row["prompt"], [int(item) for item in row["candidate_indices"]], None, disable_adapter=disable_adapter)
        target = int(row["target_idx"])
        exact += int(prediction == target)
        legal += int(prediction <= target)
        chance_values.append(float(row["chance"]))
    return {"n": len(rows), "accuracy": exact / len(rows), "any_legal_rate": legal / len(rows), "chance": mean(chance_values)}


@torch.no_grad()
def _evaluate_sft_loss(rows: list[dict[str, Any]], model: Any, tokenizer: Any, args: argparse.Namespace) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "loss": None, "perplexity": None}
    dataset = BackjumpDataset(rows[: args.max_val_examples], tokenizer, args.max_length)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, collate_fn=lambda batch: _collate(batch, tokenizer.pad_token_id))
    model.eval()
    losses: list[float] = []
    for batch in loader:
        batch = {key: value.to(_model_device(model)) for key, value in batch.items()}
        out = model(**batch)
        losses.append(float(out.loss.detach().float().item()))
    mean_loss = mean(losses) if losses else None
    perplexity = float(torch.exp(torch.tensor(mean_loss)).item()) if mean_loss is not None and mean_loss < 20 else None
    return {"n": len(dataset), "loss": mean_loss, "perplexity": perplexity}


@torch.no_grad()
def _score_prompt_candidates_batch(model: Any, tokenizer: Any, prompts: list[str], candidates_by_prompt: list[list[int]], disable_adapter: bool = False) -> list[tuple[int, dict[int, float], float]]:
    encoded = tokenizer(prompts, return_tensors="pt", add_special_tokens=False, padding=True)
    input_ids = encoded.input_ids.to(_model_device(model))
    attention_mask = encoded.attention_mask.to(_model_device(model))
    with _adapter_disabled(model, disable_adapter):
        out = model(input_ids=input_ids, attention_mask=attention_mask, use_cache=False)
    last_positions = attention_mask.sum(dim=1) - 1
    batch_indices = torch.arange(input_ids.shape[0], device=_model_device(model))
    log_probs = torch.log_softmax(out.logits[batch_indices, last_positions, :], dim=-1)
    results: list[tuple[int, dict[int, float], float]] = []
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
        results.append((predicted, scores, margin))
    return results


def _decision_eval_detail_rows(rows: list[dict[str, Any]], model: Any, tokenizer: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    existing = _read_json(args.checkpoint_path) if args.resume and args.checkpoint_path.exists() else []
    if isinstance(existing, dict):
        existing = existing.get("rows", [])
    detail_rows = list(existing or [])
    done = {int(row["row_index"]) for row in detail_rows if "row_index" in row}
    indexed = [(index, row) for index, row in enumerate(rows) if index % int(args.num_shards) == int(args.shard_index)]
    pending = [(index, row) for index, row in indexed if index not in done]
    for batch_start in range(0, len(pending), args.batch_size):
        batch = pending[batch_start: batch_start + args.batch_size]
        prompts = [str(row["prompt"]) for _, row in batch]
        candidates_by_prompt = [[int(item) for item in row["candidate_indices"]] for _, row in batch]
        frozen_scores = _score_prompt_candidates_batch(model, tokenizer, prompts, candidates_by_prompt, disable_adapter=True)
        lora_scores = _score_prompt_candidates_batch(model, tokenizer, prompts, candidates_by_prompt, disable_adapter=False)
        for local_index, (row_index, row) in enumerate(batch):
            target = int(row["target_idx"])
            chrono = int(row["chrono_idx"])
            frozen_pred, frozen_candidate_scores, frozen_margin = frozen_scores[local_index]
            lora_pred, lora_candidate_scores, lora_margin = lora_scores[local_index]
            detail_rows.append({
                "row_index": int(row_index),
                "shard_index": int(args.shard_index),
                "num_shards": int(args.num_shards),
                "example_id": row.get("example_id"),
                "instance_id": row.get("instance_id"),
                "bin": row.get("bin"),
                "split": row.get("split"),
                "R": int(row["R"]),
                "num_open": int(row["num_open"]),
                "chance": float(row["chance"]),
                "target_idx": target,
                "chrono_idx": chrono,
                "frozen_pred": int(frozen_pred),
                "lora_pred": int(lora_pred),
                "frozen_exact": int(frozen_pred == target),
                "lora_exact": int(lora_pred == target),
                "chrono_exact": int(chrono == target),
                "oracle_exact": 1,
                "frozen_any_legal": int(frozen_pred <= target),
                "lora_any_legal": int(lora_pred <= target),
                "chrono_any_legal": int(chrono <= target),
                "oracle_any_legal": 1,
                "frozen_margin": float(frozen_margin),
                "lora_margin": float(lora_margin),
                "frozen_candidate_scores": {str(key): value for key, value in sorted(frozen_candidate_scores.items())},
                "lora_candidate_scores": {str(key): value for key, value in sorted(lora_candidate_scores.items())},
                "source": SOURCE,
                "provenance": "kvcache_backjump_lora_decision_eval_row_v0",
            })
        detail_rows.sort(key=lambda item: int(item["row_index"]))
        _write_json(args.checkpoint_path, detail_rows)
        print(json.dumps({"shard_index": args.shard_index, "rows": len(detail_rows), "pending": max(0, len(pending) - batch_start - len(batch))}), flush=True)
    return detail_rows


def _summarize_decision_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    groups = sorted({(row["bin"], row["split"], int(row["R"])) for row in rows})
    for bin_label, split, r_value in groups:
        subset = [row for row in rows if row["bin"] == bin_label and row["split"] == split and int(row["R"]) == r_value]
        summary.append({
            "bin": bin_label,
            "split": split,
            "R": r_value,
            "n": len(subset),
            "frozen_accuracy": mean(float(row["frozen_exact"]) for row in subset),
            "lora_accuracy": mean(float(row["lora_exact"]) for row in subset),
            "chrono_accuracy": mean(float(row["chrono_exact"]) for row in subset),
            "oracle_accuracy": 1.0,
            "frozen_any_legal": mean(float(row["frozen_any_legal"]) for row in subset),
            "lora_any_legal": mean(float(row["lora_any_legal"]) for row in subset),
            "chrono_any_legal": mean(float(row["chrono_any_legal"]) for row in subset),
            "chance": mean(float(row["chance"]) for row in subset),
            "source": SOURCE,
            "provenance": "kvcache_backjump_lora_decision_eval_v0",
        })
    return summary


def eval_decisions(args: argparse.Namespace) -> dict[str, Any]:
    all_rows = _read_jsonl(args.examples_jsonl)
    rows = [row for index, row in enumerate(all_rows) if index % int(args.num_shards) == int(args.shard_index)]
    model, tokenizer = _load_lora_model(args, training=False)
    detail_rows = _decision_eval_detail_rows(all_rows, model, tokenizer, args)
    summary = _summarize_decision_rows(detail_rows)
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_EVAL_COMPLETE, "generated_at": _now(), "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "preflight": {"all_examples": len(all_rows), "shard_examples": len(rows), "evaluated_rows": len(detail_rows)}, "summary": summary, "rows": detail_rows, "source": SOURCE, "provenance": "kvcache_backjump_lora_decision_eval_v0"}
    _write_json(args.output, payload)
    return payload


def merge_decisions(args: argparse.Namespace) -> dict[str, Any]:
    rows_by_index: dict[int, dict[str, Any]] = {}
    input_files: list[str] = []
    for pattern in args.inputs:
        for path in sorted(Path().glob(pattern)):
            payload = _read_json(path)
            input_files.append(str(path))
            if isinstance(payload, list):
                rows = payload
            else:
                rows = payload.get("rows", [])
            for row in rows:
                rows_by_index[int(row["row_index"])] = row
    rows = [rows_by_index[key] for key in sorted(rows_by_index)]
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_EVAL_COMPLETE, "generated_at": _now(), "config": {"inputs": args.inputs}, "input_files": input_files, "summary": _summarize_decision_rows(rows), "rows": rows, "source": SOURCE, "provenance": "kvcache_backjump_lora_decision_eval_merged_v0"}
    _write_json(args.output, payload)
    return payload


def _choose_backjump(policy: str, model: Any, tokenizer: Any, prompt: str, candidates: list[int], oracle_idx: int, cache: Any, args: argparse.Namespace) -> tuple[int, Any, int, dict[str, Any]]:
    if policy == "oracle":
        return oracle_idx, cache, 0, {"parse_checked": False, "fallback": False, "fatal": False}
    if policy == "chrono":
        return max(candidates), cache, 0, {"parse_checked": False, "fallback": False, "fatal": False}
    if policy == "random":
        rng = random.Random(f"{args.seed}:{hashlib.blake2b(prompt.encode('utf-8'), digest_size=8).hexdigest()}")
        return int(candidates[rng.randrange(len(candidates))]), cache, 0, {"parse_checked": False, "fallback": False, "fatal": False}
    if _is_conflict_analysis_policy(policy):
        prompt = _maybe_chat_prompt(tokenizer, prompt, args)
        text, new_cache, usage = _generate_conflict_analysis(model, tokenizer, prompt, cache, int(args.cot_max_new_tokens))
        parsed = _parse_backjump_index(text, len(candidates))
        meta = {**parsed, **usage, "parse_checked": True, "fallback": False, "fallback_type": None, "fatal": False, "repair_attempted": False, "repair_success": False, "raw_parseable": bool(parsed.get("parseable")), "raw_valid": bool(parsed.get("valid")), "raw_text_tail": text[-512:]}
        if bool(parsed["valid"]):
            return int(parsed["raw_index"]), new_cache, int(usage["total_tokens"]), meta
        if args.cot_invalid_repair == "score":
            repair_suffix = "\nThe BACKJUMP above is invalid. Valid target indices are " + json.dumps([int(item) for item in candidates], separators=(",", ":")) + ". Return one valid line only.\nBACKJUMP:"
            repair_prediction, _, _, repair_cache, repair_used = _score_prompt_candidates(model, tokenizer, repair_suffix, candidates, new_cache, disable_adapter=False)
            meta["repair_attempted"] = True
            meta["repair_success"] = True
            meta["repair_prediction"] = int(repair_prediction)
            meta["repair_input_tokens"] = int(repair_used)
            meta["valid"] = True
            meta["invalid_reason"] = None
            meta["total_tokens"] = int(usage["total_tokens"]) + int(repair_used)
            return int(repair_prediction), repair_cache, int(meta["total_tokens"]), meta
        if args.cot_fallback == "chrono":
            meta["fallback"] = True
            meta["fallback_type"] = "chronological_latest"
            return max(candidates), new_cache, int(usage["total_tokens"]), meta
        meta["fatal"] = True
        return max(candidates), new_cache, int(usage["total_tokens"]), meta
    disable_adapter = policy == "frozen"
    prediction, _, _, new_cache, used = _score_prompt_candidates(model, tokenizer, prompt, candidates, cache, disable_adapter=disable_adapter)
    return prediction, new_cache, used, {"parse_checked": False, "fallback": False, "fatal": False}


def _run_search(model: Any, tokenizer: Any, dataset: Any, selected: dict[str, Any], r_value: int, condition: str, backjump_policy: str, args: argparse.Namespace) -> dict[str, Any]:
    entry = selected["entry"]
    view = _graph_color_view(entry, args.order_mode)
    position = {vertex: index for index, vertex in enumerate(view["order"])}
    assignment: dict[int, int] = {}
    tried: dict[int, set[int]] = defaultdict(set)
    register: list[dict[str, Any]] = []
    transcript = f"Graph_color backjump LoRA search condition={condition} backjump_policy={backjump_policy}.\nProblem:\n{entry.get('question','')}\n"
    _, cache, used = _feed(model, tokenizer, transcript, None)
    stats = Counter({"input_tokens": used, "total_tokens": used})
    cot_trace_samples: list[dict[str, Any]] = []
    cursor = 0
    while True:
        if int(stats["decision_points"]) >= args.call_cap:
            status = "CALL_CAP"
            break
        if cursor >= len(view["order"]):
            status = "SOLVED"
            break
        vertex = view["order"][cursor]
        domain = _current_domain(view, vertex, assignment, tried)
        if domain:
            neighbors = [{"neighbor": int(neighbor), "color": int(assignment[neighbor])} for neighbor in sorted(view["adjacency"][vertex]) if neighbor in assignment]
            checkpoint = _cache_seq_length(cache)
            if condition == "isolation":
                color = int(domain[0])
            else:
                prompt = "\nNEXT_BRANCH\n" + _branch_prompt(entry, vertex, [int(item) for item in domain], neighbors, tried[vertex])
                color, _, _, cache, branch_used = _score_prompt_candidates(model, tokenizer, prompt, [int(item) for item in domain], cache, disable_adapter=True)
                stats["input_tokens"] += branch_used
                stats["total_tokens"] += branch_used
                stats["branch_decisions"] += 1
                stats["branch_correct"] += int(color == int(domain[0]))
            tried[vertex].add(int(color))
            assignment[vertex] = int(color)
            register.append({"vertex": int(vertex), "color": int(color), "order_index": int(cursor), "cache_pos": int(checkpoint)})
            event = f"\nBRANCH vertex={int(vertex)} color={int(color)} domain={list(map(int, domain))} tried={sorted(int(item) for item in tried[vertex])}\n"
            _, cache, event_used = _feed(model, tokenizer, event, cache)
            stats["input_tokens"] += event_used
            stats["total_tokens"] += event_used
            cursor += 1
            continue
        if r_value == 0 or not register:
            status = "FORWARD_DEAD_END"
            break
        nogood = _deadend_nogood(view, vertex, assignment, position)
        oracle_vertex = max(nogood, key=lambda item: position[item]) if nogood else int(register[-1]["vertex"])
        oracle_abs = max((index for index, item in enumerate(register) if int(item["vertex"]) == int(oracle_vertex)), default=len(register) - 1)
        start = max(0, len(register) - int(r_value))
        oracle_idx = oracle_abs - start
        if not (0 <= oracle_idx < len(register[start:])):
            status = "NO_RECOVERY_TARGET"
            break
        open_checkpoints = _checkpoint_rows(register, start)
        example = {"problem": entry.get("question", ""), "live_register": [dict(item) for item in register], "open_checkpoints": open_checkpoints, "candidate_indices": [int(item["idx"]) for item in open_checkpoints], "target_idx": int(oracle_idx), "conflict_vertex": int(vertex), "conflict_blockers": sorted(int(item) for item in nogood)}
        if _is_conflict_analysis_policy(backjump_policy):
            prompt = "\nDEAD_END\n" + _conflict_analysis_prompt(entry, view, int(vertex), assignment, tried, register, open_checkpoints, args)
        else:
            prompt = "\nDEAD_END\n" + _backjump_prompt(example)
        chosen, cache, backjump_used, backjump_meta = _choose_backjump(backjump_policy, model, tokenizer, prompt, example["candidate_indices"], int(oracle_idx), cache, args)
        stats["input_tokens"] += int(backjump_meta.get("input_tokens", backjump_used))
        stats["total_tokens"] += backjump_used
        stats["decision_points"] += 1
        stats["backtrack_decisions"] += 1
        stats["backtrack_parse_checks"] += int(bool(backjump_meta.get("parse_checked")))
        stats["backtrack_parseable"] += int(backjump_meta.get("parseable") is True)
        stats["backtrack_valid"] += int(backjump_meta.get("valid") is True)
        stats["backtrack_fallback"] += int(bool(backjump_meta.get("fallback")))
        stats["backtrack_repair_attempted"] += int(bool(backjump_meta.get("repair_attempted")))
        stats["backtrack_repair_success"] += int(bool(backjump_meta.get("repair_success")))
        stats["cot_output_tokens"] += int(backjump_meta.get("output_tokens", 0))
        if bool(backjump_meta.get("parse_checked")) and len(cot_trace_samples) < int(args.cot_trace_samples):
            cot_trace_samples.append({
                "conflict_vertex": int(vertex),
                "oracle_idx": int(oracle_idx),
                "chosen_idx": int(chosen),
                "parseable": bool(backjump_meta.get("parseable")),
                "valid": bool(backjump_meta.get("valid")),
                "fallback": bool(backjump_meta.get("fallback")),
                "fallback_type": backjump_meta.get("fallback_type"),
                "invalid_reason": backjump_meta.get("invalid_reason"),
                "raw_index": backjump_meta.get("raw_index"),
                "raw_parseable": backjump_meta.get("raw_parseable"),
                "raw_valid": backjump_meta.get("raw_valid"),
                "repair_attempted": backjump_meta.get("repair_attempted"),
                "repair_success": backjump_meta.get("repair_success"),
                "repair_prediction": backjump_meta.get("repair_prediction"),
                "output_tokens": int(backjump_meta.get("output_tokens", 0)),
                "raw_text_tail": backjump_meta.get("raw_text_tail"),
            })
        stats["backtrack_exact"] += int(int(chosen) == int(oracle_idx))
        stats["backtrack_legal"] += int(int(chosen) <= int(oracle_idx))
        stats["chance_sum"] += 1.0 / len(open_checkpoints)
        if bool(backjump_meta.get("fatal")):
            status = "INVALID_BACKJUMP_DECISION"
            break
        target_abs = start + int(chosen)
        checkpoint = register[target_abs].get("cache_pos")
        if checkpoint is None:
            status = "CACHE_CHECKPOINT_MISSING"
            break
        cache, _ = _crop_cache(cache, int(checkpoint))
        popped = register[target_abs:]
        for item in popped:
            assignment.pop(int(item["vertex"]), None)
        for item in popped[1:]:
            tried[int(item["vertex"])] = set()
        tried[vertex] = set()
        cursor = int(register[target_abs]["order_index"])
        del register[target_abs:]
        stats["retractions"] += len(popped)
    score = _official_score(dataset, entry, assignment) if len(assignment) == len(entry["metadata"]["puzzle"]["vertices"]) else 0.0
    return {"bin": selected["bin"], "split": selected["split"], "source_index": int(selected["source_index"]), "R": int(r_value), "condition": condition, "backjump_policy": backjump_policy, "status": "SOLVED" if score >= 1.0 else status, "solved": score >= 1.0, "official_score": score, "backtrack_decisions": int(stats["backtrack_decisions"]), "backtrack_exact": int(stats["backtrack_exact"]), "backtrack_legal": int(stats["backtrack_legal"]), "backtrack_parse_checks": int(stats["backtrack_parse_checks"]), "backtrack_parseable": int(stats["backtrack_parseable"]), "backtrack_valid": int(stats["backtrack_valid"]), "backtrack_fallback": int(stats["backtrack_fallback"]), "backtrack_repair_attempted": int(stats["backtrack_repair_attempted"]), "backtrack_repair_success": int(stats["backtrack_repair_success"]), "cot_output_tokens": int(stats["cot_output_tokens"]), "cot_trace_samples": cot_trace_samples, "chance_sum": float(stats["chance_sum"]), "branch_decisions": int(stats["branch_decisions"]), "branch_correct": int(stats["branch_correct"]), "retractions": int(stats["retractions"]), "input_tokens": int(stats["input_tokens"]), "total_tokens": int(stats["total_tokens"]), "answer": _official_answer(assignment) if score >= 1.0 else None, "source": SOURCE, "provenance": "kvcache_backjump_lora_search_eval_row_v0"}


def _select_eval_entries(args: argparse.Namespace, bin_spec: dict[str, Any], split: str) -> tuple[Any, list[dict[str, Any]]]:
    dataset = _make_dataset(args, bin_spec)
    selected: list[dict[str, Any]] = []
    for source_index in range(args.scan_limit):
        instance_id = _instance_id(str(bin_spec["label"]), source_index)
        if _split_for_instance(instance_id, str(bin_spec["label"]), args) != split:
            continue
        entry = dataset[source_index]
        entry.setdefault("metadata", {})["source_index"] = source_index
        trace = _clean_trace(entry, args.order_mode, args.node_cap, dataset)
        if trace.get("solved") and int(trace.get("total_retractions", 0)) >= args.min_backtracks:
            selected.append({"entry": entry, "source_index": source_index, "trace": trace, "bin": bin_spec["label"], "split": split})
        if len(selected) >= args.n_instances:
            break
    return dataset, selected


def _summarize_search(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = sorted({(row["bin"], row["split"], int(row["R"]), row["condition"], row["backjump_policy"]) for row in rows})
    summary: list[dict[str, Any]] = []
    for bin_label, split, r_value, condition, policy in groups:
        subset = [row for row in rows if row["bin"] == bin_label and row["split"] == split and int(row["R"]) == r_value and row["condition"] == condition and row["backjump_policy"] == policy]
        decisions = sum(int(row["backtrack_decisions"]) for row in subset)
        parse_checks = sum(int(row.get("backtrack_parse_checks", 0)) for row in subset)
        status_counts = dict(Counter(row["status"] for row in subset))
        summary.append({"bin": bin_label, "split": split, "R": r_value, "condition": condition, "backjump_policy": policy, "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "mean_official_score": mean(float(row["official_score"]) for row in subset), "status_counts": status_counts, "no_recovery_target_rate": status_counts.get("NO_RECOVERY_TARGET", 0) / len(subset), "mean_retractions": mean(float(row.get("retractions", 0)) for row in subset), "mean_total_tokens": mean(float(row.get("total_tokens", 0)) for row in subset), "backtrack_decisions": decisions, "backtrack_accuracy": (sum(int(row["backtrack_exact"]) for row in subset) / decisions) if decisions else None, "any_legal_rate": (sum(int(row["backtrack_legal"]) for row in subset) / decisions) if decisions else None, "chance_baseline": (sum(float(row["chance_sum"]) for row in subset) / decisions) if decisions else None, "parseable_rate": (sum(int(row.get("backtrack_parseable", 0)) for row in subset) / parse_checks) if parse_checks else None, "valid_parse_rate": (sum(int(row.get("backtrack_valid", 0)) for row in subset) / parse_checks) if parse_checks else None, "fallback_rate": (sum(int(row.get("backtrack_fallback", 0)) for row in subset) / parse_checks) if parse_checks else None, "repair_attempt_rate": (sum(int(row.get("backtrack_repair_attempted", 0)) for row in subset) / parse_checks) if parse_checks else None, "repair_success_rate": (sum(int(row.get("backtrack_repair_success", 0)) for row in subset) / parse_checks) if parse_checks else None, "mean_cot_output_tokens": (sum(int(row.get("cot_output_tokens", 0)) for row in subset) / parse_checks) if parse_checks else None, "branch_accuracy": (sum(int(row["branch_correct"]) for row in subset) / sum(int(row["branch_decisions"]) for row in subset)) if sum(int(row["branch_decisions"]) for row in subset) else None, "source": SOURCE, "provenance": "kvcache_backjump_lora_search_eval_summary_v0"})
    return summary


def _chronological_oracle_gaps(summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    groups = sorted({(row["bin"], row["split"], int(row["R"]), row["condition"]) for row in summary})
    for bin_label, split, r_value, condition in groups:
        chrono = next((row for row in summary if row["bin"] == bin_label and row["split"] == split and int(row["R"]) == r_value and row["condition"] == condition and row["backjump_policy"] == "chrono"), None)
        oracle = next((row for row in summary if row["bin"] == bin_label and row["split"] == split and int(row["R"]) == r_value and row["condition"] == condition and row["backjump_policy"] == "oracle"), None)
        random_row = next((row for row in summary if row["bin"] == bin_label and row["split"] == split and int(row["R"]) == r_value and row["condition"] == condition and row["backjump_policy"] == "random"), None)
        if not chrono or not oracle:
            continue
        rows.append({
            "bin": bin_label,
            "split": split,
            "R": r_value,
            "condition": condition,
            "chrono_solve_rate": chrono["solve_rate"],
            "oracle_solve_rate": oracle["solve_rate"],
            "random_solve_rate": random_row["solve_rate"] if random_row else None,
            "chrono_minus_oracle_solve_gap": chrono["solve_rate"] - oracle["solve_rate"],
            "chrono_minus_random_solve_gap": (chrono["solve_rate"] - random_row["solve_rate"]) if random_row else None,
            "chrono_no_recovery_target_rate": chrono.get("no_recovery_target_rate"),
            "oracle_no_recovery_target_rate": oracle.get("no_recovery_target_rate"),
            "source": SOURCE,
            "provenance": "kvcache_backjump_lora_chrono_oracle_gap_v0",
        })
    return rows


def _conflict_analysis_gaps(summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    conflict_policies = {row["backjump_policy"] for row in summary if _is_conflict_analysis_policy(str(row["backjump_policy"]))}
    for conflict_policy in sorted(conflict_policies):
        groups = sorted({(row["bin"], row["split"], int(row["R"]), row["condition"]) for row in summary if row["backjump_policy"] == conflict_policy})
        for bin_label, split, r_value, condition in groups:
            conflict = next((row for row in summary if row["bin"] == bin_label and row["split"] == split and int(row["R"]) == r_value and row["condition"] == condition and row["backjump_policy"] == conflict_policy), None)
            chrono = next((row for row in summary if row["bin"] == bin_label and row["split"] == split and int(row["R"]) == r_value and row["condition"] == condition and row["backjump_policy"] == "chrono"), None)
            oracle = next((row for row in summary if row["bin"] == bin_label and row["split"] == split and int(row["R"]) == r_value and row["condition"] == condition and row["backjump_policy"] == "oracle"), None)
            random_row = next((row for row in summary if row["bin"] == bin_label and row["split"] == split and int(row["R"]) == r_value and row["condition"] == condition and row["backjump_policy"] == "random"), None)
            if not conflict:
                continue
            rows.append({
                "bin": bin_label,
                "split": split,
                "R": r_value,
                "condition": condition,
                "conflict_policy": conflict_policy,
                "conflict_solve_rate": conflict["solve_rate"],
                "chrono_solve_rate": chrono["solve_rate"] if chrono else None,
                "oracle_solve_rate": oracle["solve_rate"] if oracle else None,
                "random_solve_rate": random_row["solve_rate"] if random_row else None,
                "conflict_minus_chrono_solve_gap": (conflict["solve_rate"] - chrono["solve_rate"]) if chrono else None,
                "conflict_minus_oracle_solve_gap": (conflict["solve_rate"] - oracle["solve_rate"]) if oracle else None,
                "conflict_minus_random_solve_gap": (conflict["solve_rate"] - random_row["solve_rate"]) if random_row else None,
                "parseable_rate": conflict.get("parseable_rate"),
                "fallback_rate": conflict.get("fallback_rate"),
                "source": SOURCE,
                "provenance": "kvcache_backjump_lora_conflict_analysis_gap_v0",
            })
    return rows


def eval_search(args: argparse.Namespace) -> dict[str, Any]:
    model, tokenizer = _load_lora_model(args, training=False)
    bins = _parse_bins(args.bins)
    r_values = _parse_ints(args.r_values)
    policies = [item.strip() for item in args.backjump_policies.split(",") if item.strip()]
    conditions = [item.strip() for item in args.conditions.split(",") if item.strip()]
    rows = _read_json(args.checkpoint_path) if args.resume and args.checkpoint_path.exists() else []
    if isinstance(rows, dict):
        rows = rows.get("rows", [])
    rows = list(rows or [])
    done = {(row["bin"], int(row["source_index"]), int(row["R"]), row["condition"], row["backjump_policy"]) for row in rows}
    preflight: list[dict[str, Any]] = []
    task_index = 0
    for bin_spec in bins:
        split = "ood_eval" if str(bin_spec["label"]).startswith("v18") else "val"
        dataset, selected = _select_eval_entries(args, bin_spec, split)
        preflight.append({"bin": bin_spec["label"], "split": split, "selected": len(selected), "requested": args.n_instances})
        for item in selected:
            for r_value in r_values:
                for condition in conditions:
                    for policy in policies:
                        current_task_index = task_index
                        task_index += 1
                        if current_task_index % int(args.num_shards) != int(args.shard_index):
                            continue
                        key = (str(item["bin"]), int(item["source_index"]), int(r_value), str(condition), str(policy))
                        if key in done:
                            continue
                        row = _run_search(model, tokenizer, dataset, item, r_value, condition, policy, args)
                        row["task_index"] = current_task_index
                        row["shard_index"] = int(args.shard_index)
                        row["num_shards"] = int(args.num_shards)
                        rows.append(row)
                        done.add(key)
                        _write_json(args.checkpoint_path, rows)
                        print(json.dumps({"bin": row["bin"], "source_index": row["source_index"], "R": row["R"], "condition": condition, "policy": policy, "status": row["status"]}), flush=True)
    summary = _summarize_search(rows)
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_EVAL_COMPLETE, "generated_at": _now(), "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "preflight": preflight, "planned_tasks_all_shards": task_index, "summary": summary, "chronological_oracle_gaps": _chronological_oracle_gaps(summary), "conflict_analysis_gaps": _conflict_analysis_gaps(summary), "rows": rows, "source": SOURCE, "provenance": "kvcache_backjump_lora_search_eval_v0"}
    _write_json(args.output, payload)
    return payload


def merge_search(args: argparse.Namespace) -> dict[str, Any]:
    rows_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    input_files: list[str] = []
    preflight: list[dict[str, Any]] = []
    planned_tasks = 0
    for pattern in args.inputs:
        for path in sorted(Path().glob(pattern)):
            payload = _read_json(path)
            input_files.append(str(path))
            if isinstance(payload, list):
                rows = payload
            else:
                rows = payload.get("rows", [])
                if payload.get("preflight") and not preflight:
                    preflight = payload.get("preflight", [])
                planned_tasks = max(planned_tasks, int(payload.get("planned_tasks_all_shards", 0)))
            for row in rows:
                key = (row["bin"], int(row["source_index"]), int(row["R"]), row["condition"], row["backjump_policy"])
                rows_by_key[key] = row
    rows = [rows_by_key[key] for key in sorted(rows_by_key)]
    summary = _summarize_search(rows)
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_EVAL_COMPLETE, "generated_at": _now(), "config": {"inputs": args.inputs}, "input_files": input_files, "preflight": preflight, "planned_tasks_all_shards": planned_tasks, "summary": summary, "chronological_oracle_gaps": _chronological_oracle_gaps(summary), "conflict_analysis_gaps": _conflict_analysis_gaps(summary), "rows": rows, "source": SOURCE, "provenance": "kvcache_backjump_lora_search_eval_merged_v0"}
    _write_json(args.output, payload)
    return payload


@torch.no_grad()
def _forward_logits(model: Any, input_ids: torch.Tensor, past: Any | None = None) -> tuple[torch.Tensor, Any]:
    out = model(input_ids=input_ids, past_key_values=past, use_cache=True)
    return out.logits[:, -1, :], out.past_key_values


@torch.no_grad()
def _greedy_extend(model: Any, prompt_ids: torch.Tensor, n_new: int) -> tuple[torch.Tensor, Any, list[torch.Tensor]]:
    logits, cache = _forward_logits(model, prompt_ids)
    generated: list[torch.Tensor] = []
    step_logits: list[torch.Tensor] = []
    for _ in range(n_new):
        step_logits.append(logits.detach().float().cpu())
        token = logits.argmax(dim=-1, keepdim=True)
        generated.append(token)
        logits, cache = _forward_logits(model, token, past=cache)
    return torch.cat([prompt_ids] + generated, dim=1), cache, step_logits


def km3_check(args: argparse.Namespace) -> dict[str, Any]:
    rows = _read_jsonl(args.examples_jsonl)
    if not rows:
        payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_PREFLIGHT_FAIL, "reason": "no example rows for real backjump prompt", "source": SOURCE, "provenance": SCHEMA_VERSION}
        _write_json(args.output, payload)
        return payload
    row = rows[int(args.example_index) % len(rows)]
    prompt = str(row["prompt"])
    model, tokenizer = _load_lora_model(args, training=False)
    model.config.use_cache = True
    prompt_ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(model.device)
    prompt_len = int(prompt_ids.shape[1])
    full_ids, full_cache, step_logits = _greedy_extend(model, prompt_ids, args.depth)
    checkpoints = [int(item) for item in args.checkpoints.split(",") if item.strip()]
    avoid_ids = {token for token in [tokenizer.eos_token_id, tokenizer.pad_token_id, tokenizer.bos_token_id] if token is not None}
    tests: list[dict[str, Any]] = []
    overall = True
    crop_paths = set()
    for generated_prefix_len in checkpoints:
        checkpoint_len = prompt_len + generated_prefix_len
        if not (1 <= generated_prefix_len < args.depth - 1):
            continue
        same_token = full_ids[:, checkpoint_len: checkpoint_len + 1]
        cropped_same = copy.deepcopy(full_cache)
        cropped_same, crop_path = _crop_cache(cropped_same, checkpoint_len)
        crop_paths.add(crop_path)
        same_logits, same_after = _forward_logits(model, same_token, cropped_same)
        same_dev = _deviation(same_logits, step_logits[generated_prefix_len + 1])
        same_pass = _cache_seq_length(cropped_same) == checkpoint_len + 1 and _cache_seq_length(same_after) == checkpoint_len + 1 and same_dev["argmax_equal"] and same_dev["max_abs_logit_delta"] <= args.tol
        tests.append({"test": "resume_same", "checkpoint_generated_tokens": generated_prefix_len, "checkpoint_seq_len": checkpoint_len, "crop_path": crop_path, "pass": same_pass, **same_dev})
        overall = overall and same_pass

        diff_token_id = _different_token(int(same_token[0, 0].item()), int(model.config.vocab_size), avoid_ids)
        diff_token = torch.tensor([[diff_token_id]], dtype=full_ids.dtype, device=model.device)
        cropped_diff = copy.deepcopy(full_cache)
        cropped_diff, crop_path = _crop_cache(cropped_diff, checkpoint_len)
        crop_paths.add(crop_path)
        diff_logits, diff_after = _forward_logits(model, diff_token, cropped_diff)
        fresh_ids = torch.cat([full_ids[:, :checkpoint_len], diff_token], dim=1)
        fresh_logits, fresh_cache = _forward_logits(model, fresh_ids)
        diff_dev = _deviation(diff_logits, fresh_logits)
        diff_pass = _cache_seq_length(cropped_diff) == checkpoint_len + 1 and _cache_seq_length(diff_after) == checkpoint_len + 1 and _cache_seq_length(fresh_cache) == checkpoint_len + 1 and diff_dev["argmax_equal"] and diff_dev["max_abs_logit_delta"] <= args.tol
        tests.append({"test": "resume_different_equals_fresh", "checkpoint_generated_tokens": generated_prefix_len, "checkpoint_seq_len": checkpoint_len, "crop_path": crop_path, "different_token_id": diff_token_id, "pass": diff_pass, **diff_dev})
        overall = overall and diff_pass
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_KM3_PASS if overall else STATUS_KM3_FAIL,
        "generated_at": _now(),
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()},
        "example_id": row.get("example_id"),
        "prompt_tokens": prompt_len,
        "depth": args.depth,
        "full_cache_seq_len": _cache_seq_length(full_cache),
        "cache_type": type(full_cache).__name__,
        "cache_inventory": _cache_inventory(full_cache),
        "crop_paths": sorted(crop_paths),
        "tol": args.tol,
        "max_abs_logit_delta": max((float(test.get("max_abs_logit_delta", 0.0)) for test in tests), default=0.0),
        "overall_pass": overall,
        "tests": tests,
        "source": SOURCE,
        "provenance": "kvcache_backjump_lora_km3_v0",
    }
    _write_json(args.output, payload)
    return payload


def _add_common_data_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scan-limit", type=int, default=5000)
    parser.add_argument("--max-selected-instances", type=int, default=120)
    parser.add_argument("--n-instances", type=int, default=30)
    parser.add_argument("--min-backtracks", type=int, default=4)
    parser.add_argument("--node-cap", type=int, default=500)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--order-mode", default="degree_desc", choices=["degree_desc", "natural"])
    parser.add_argument("--bins", default="v14_p04:14:0.4,v16_p04:16:0.4,v18_p04:18:0.4")
    parser.add_argument("--r-values", default="2,4,8")
    parser.add_argument("--train-fraction", type=float, default=0.8)
    parser.add_argument("--progress-every-selected", type=int, default=10)


def _add_model_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="bf16")
    parser.add_argument("--adapter-path", type=Path, default=None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backjump-only LoRA for graph_color KV-cache search.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build-data")
    _add_common_data_args(build_parser)
    build_parser.add_argument("--output-dir", type=Path, default=Path("results/kvcache_backjump_lora/data_v0"))

    c2_collect_parser = subparsers.add_parser("collect-c2-data")
    _add_common_data_args(c2_collect_parser)
    _add_model_args(c2_collect_parser)
    c2_collect_parser.add_argument("--output", type=Path, default=Path("results/kvcache_backjump_lora/c2_reasoning_data_v0/shard_0.json"))
    c2_collect_parser.add_argument("--checkpoint-path", type=Path, default=Path("results/kvcache_backjump_lora/c2_reasoning_data_v0/shard_0_checkpoint.json"))
    c2_collect_parser.add_argument("--conditions", default="isolation,autonomous")
    c2_collect_parser.add_argument("--call-cap", type=int, default=220)
    c2_collect_parser.add_argument("--cot-max-new-tokens", type=int, default=256)
    c2_collect_parser.add_argument("--cot-fallback", choices=["chrono", "fail"], default="fail")
    c2_collect_parser.add_argument("--cot-prompt-style", choices=["blockers", "per_color"], default="per_color")
    c2_collect_parser.add_argument("--cot-chat-template", dest="cot_chat_template", action="store_true", default=True)
    c2_collect_parser.add_argument("--no-cot-chat-template", dest="cot_chat_template", action="store_false")
    c2_collect_parser.add_argument("--num-shards", type=int, default=1)
    c2_collect_parser.add_argument("--shard-index", type=int, default=0)
    c2_collect_parser.add_argument("--resume", action="store_true")
    c2_collect_parser.set_defaults(dtype="fp32")

    c2_merge_parser = subparsers.add_parser("merge-c2-data")
    c2_merge_parser.add_argument("--output-dir", type=Path, default=Path("results/kvcache_backjump_lora/c2_reasoning_data_v0"))
    c2_merge_parser.add_argument("--inputs", nargs="+", default=["results/kvcache_backjump_lora/c2_reasoning_data_v0/shard_*_checkpoint.json"])

    c2_repair_parser = subparsers.add_parser("repair-c2-data")
    c2_repair_parser.add_argument("--input-dir", type=Path, default=Path("results/kvcache_backjump_lora/c2_reasoning_data_n30_v0"))
    c2_repair_parser.add_argument("--output-dir", type=Path, default=Path("results/kvcache_backjump_lora/c2_reasoning_data_n30_repaired_v0"))

    train_parser = subparsers.add_parser("train")
    _add_model_args(train_parser)
    train_parser.add_argument("--train-jsonl", type=Path, default=Path("results/kvcache_backjump_lora/data_v0/train.jsonl"))
    train_parser.add_argument("--val-jsonl", type=Path, default=Path("results/kvcache_backjump_lora/data_v0/val.jsonl"))
    train_parser.add_argument("--output-dir", type=Path, default=Path("results/kvcache_backjump_lora/adapter_v0"))
    train_parser.add_argument("--output", type=Path, default=Path("results/kvcache_backjump_lora/train_v0.json"))
    train_parser.add_argument("--target-modules", default="q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj")
    train_parser.add_argument("--lora-r", type=int, default=8)
    train_parser.add_argument("--lora-alpha", type=int, default=16)
    train_parser.add_argument("--lora-dropout", type=float, default=0.05)
    train_parser.add_argument("--learning-rate", type=float, default=2e-4)
    train_parser.add_argument("--weight-decay", type=float, default=0.0)
    train_parser.add_argument("--epochs", type=int, default=1)
    train_parser.add_argument("--batch-size", type=int, default=2)
    train_parser.add_argument("--grad-accum-steps", type=int, default=8)
    train_parser.add_argument("--max-length", type=int, default=2048)
    train_parser.add_argument("--max-val-examples", type=int, default=128)
    train_parser.add_argument("--log-every", type=int, default=10)
    train_parser.add_argument("--full-sequence-val-loss", action="store_true")

    decision_parser = subparsers.add_parser("eval-decisions")
    _add_model_args(decision_parser)
    decision_parser.add_argument("--examples-jsonl", type=Path, default=Path("results/kvcache_backjump_lora/data_v0/all_examples.jsonl"))
    decision_parser.add_argument("--output", type=Path, default=Path("results/kvcache_backjump_lora/eval_decisions_v0.json"))
    decision_parser.add_argument("--checkpoint-path", type=Path, default=Path("results/kvcache_backjump_lora/eval_decisions_v0_checkpoint.json"))
    decision_parser.add_argument("--batch-size", type=int, default=8)
    decision_parser.add_argument("--num-shards", type=int, default=1)
    decision_parser.add_argument("--shard-index", type=int, default=0)
    decision_parser.add_argument("--resume", action="store_true")

    merge_decisions_parser = subparsers.add_parser("merge-decisions")
    merge_decisions_parser.add_argument("--output", type=Path, default=Path("results/kvcache_backjump_lora/eval_decisions_v0.json"))
    merge_decisions_parser.add_argument("--inputs", nargs="+", default=["results/kvcache_backjump_lora/eval_decisions_shards/shard_*.json"])

    search_parser = subparsers.add_parser("eval-search")
    _add_common_data_args(search_parser)
    _add_model_args(search_parser)
    search_parser.add_argument("--output", type=Path, default=Path("results/kvcache_backjump_lora/eval_search_v0.json"))
    search_parser.add_argument("--checkpoint-path", type=Path, default=Path("results/kvcache_backjump_lora/eval_search_v0_checkpoint.json"))
    search_parser.add_argument("--conditions", default="isolation,autonomous")
    search_parser.add_argument("--backjump-policies", default="frozen,chrono,random,oracle")
    search_parser.add_argument("--call-cap", type=int, default=160)
    search_parser.add_argument("--cot-max-new-tokens", type=int, default=256)
    search_parser.add_argument("--cot-fallback", choices=["chrono", "fail"], default="chrono")
    search_parser.add_argument("--cot-invalid-repair", choices=["none", "score"], default="none")
    search_parser.add_argument("--cot-prompt-style", choices=["blockers", "per_color"], default="per_color")
    search_parser.add_argument("--cot-trace-samples", type=int, default=2)
    search_parser.add_argument("--cot-chat-template", dest="cot_chat_template", action="store_true", default=True)
    search_parser.add_argument("--no-cot-chat-template", dest="cot_chat_template", action="store_false")
    search_parser.add_argument("--num-shards", type=int, default=1)
    search_parser.add_argument("--shard-index", type=int, default=0)
    search_parser.add_argument("--resume", action="store_true")
    search_parser.set_defaults(dtype="fp32")

    merge_search_parser = subparsers.add_parser("merge-search")
    merge_search_parser.add_argument("--output", type=Path, default=Path("results/kvcache_backjump_lora/eval_search_v0.json"))
    merge_search_parser.add_argument("--inputs", nargs="+", default=["results/kvcache_backjump_lora/eval_search_shards/shard_*.json"])

    km3_parser = subparsers.add_parser("km3-check")
    _add_model_args(km3_parser)
    km3_parser.add_argument("--examples-jsonl", type=Path, default=Path("results/kvcache_backjump_lora/data_v0/val.jsonl"))
    km3_parser.add_argument("--output", type=Path, default=Path("results/kvcache_backjump_lora/km3_lora_v0.json"))
    km3_parser.add_argument("--example-index", type=int, default=0)
    km3_parser.add_argument("--depth", type=int, default=16)
    km3_parser.add_argument("--checkpoints", default="2,4,8,12")
    km3_parser.add_argument("--tol", type=float, default=1e-3)
    km3_parser.set_defaults(dtype="fp32")

    args = parser.parse_args()
    if args.command == "build-data":
        build_data(args)
    elif args.command == "collect-c2-data":
        collect_c2_data(args)
    elif args.command == "merge-c2-data":
        merge_c2_data(args)
    elif args.command == "repair-c2-data":
        repair_c2_data(args)
    elif args.command == "train":
        train(args)
    elif args.command == "eval-decisions":
        eval_decisions(args)
    elif args.command == "merge-decisions":
        merge_decisions(args)
    elif args.command == "eval-search":
        eval_search(args)
    elif args.command == "merge-search":
        merge_search(args)
    elif args.command == "km3-check":
        km3_check(args)


if __name__ == "__main__":
    main()