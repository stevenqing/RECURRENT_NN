"""KV-cache multi-agent cross-block CBJ gates and probes for graph_color."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import copy
import json
from pathlib import Path
import re
from statistics import mean
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from analysis.kvcache_decision_probe import _parse_bins, _parse_ints
from analysis.kvcache_exactness_gate import _cache_inventory, _cache_seq_length, _crop_cache, _deviation, _different_token
from analysis.kvcache_graph_color_search import _feed, _write_json
from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE
from experiments.rung1_multiagent_graphcolor import _agent_order, _partition, _partition_stats
from experiments.rung1_reasoning_gym_bounded_register import _current_domain, _deadend_nogood, _ensure_reasoning_gym, _graph_color_view, _official_answer, _official_score


SCHEMA_VERSION = "kvcache_multiagent_cbj_v0"
STATUS_COMPLETE = "KVCACHE_MULTIAGENT_CBJ_COMPLETE"
STATUS_KM3_PASS = "KVCACHE_MULTIAGENT_CBJ_KM3_PASS"
STATUS_KM3_FAIL = "KVCACHE_MULTIAGENT_CBJ_KM3_FAIL"
STATUS_PREFLIGHT_FAIL = "KVCACHE_MULTIAGENT_CBJ_PREFLIGHT_FAIL"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    path = path if path.is_absolute() else REPO_ROOT / path
    return json.loads(path.read_text(encoding="utf-8"))


def _dtype(name: str, device: torch.device) -> torch.dtype:
    if name == "bf16" and device.type == "cuda":
        return torch.bfloat16
    if name == "fp16" and device.type == "cuda":
        return torch.float16
    return torch.float32


def _load_model(args: argparse.Namespace) -> tuple[Any, Any]:
    device = torch.device(args.device if torch.cuda.is_available() or not str(args.device).startswith("cuda") else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=_dtype(args.dtype, device), trust_remote_code=True).to(device).eval()
    model.config.use_cache = True
    return model, tokenizer


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


def _multiagent_gate_prompt(entry: dict[str, Any], view: dict[str, Any], owner: dict[int, int], k_value: int) -> str:
    partition = _partition_stats(view, owner)
    boundary_edges = [(int(left), int(right)) for left, right in view["edges"] if owner[left] != owner[right]]
    return "\n".join([
        "Multi-agent graph_color cache-control prompt.",
        "Each agent owns one block, one KV cache, and one bounded checkpoint register.",
        "A cross-block backjump request truncates exactly one culprit agent cache.",
        f"K={int(k_value)}",
        "partition=" + json.dumps({str(int(vertex)): int(agent) for vertex, agent in sorted(owner.items())}, sort_keys=True),
        "partition_stats=" + json.dumps(partition, sort_keys=True),
        "boundary_edges=" + json.dumps(boundary_edges, separators=(",", ":")),
        "problem=\n" + str(entry.get("question", "")),
        "Continue with a terse multi-agent reasoning trace.",
    ])


def km3_gate(args: argparse.Namespace) -> dict[str, Any]:
    bins = _parse_bins(args.bins)
    dataset = _make_dataset(args, bins[0])
    entry = dataset[int(args.source_index)]
    entry.setdefault("metadata", {})["source_index"] = int(args.source_index)
    view = _graph_color_view(entry, args.order_mode)
    owner = _partition(view, int(args.k_value), float(args.balance_weight), int(args.seed) + int(args.source_index))
    prompt = _multiagent_gate_prompt(entry, view, owner, int(args.k_value))
    model, tokenizer = _load_model(args)
    prompt_ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(model.device)
    prompt_len = int(prompt_ids.shape[1])
    full_ids, full_cache, step_logits = _greedy_extend(model, prompt_ids, int(args.depth))
    checkpoints = [int(item) for item in args.checkpoints.split(",") if item.strip()]
    avoid_ids = {token for token in [tokenizer.eos_token_id, tokenizer.pad_token_id, tokenizer.bos_token_id] if token is not None}
    tests: list[dict[str, Any]] = []
    crop_paths: set[str] = set()
    overall = True
    for generated_prefix_len in checkpoints:
        checkpoint_len = prompt_len + generated_prefix_len
        if not (1 <= generated_prefix_len < int(args.depth) - 1):
            continue
        same_token = full_ids[:, checkpoint_len: checkpoint_len + 1]
        cropped_same = copy.deepcopy(full_cache)
        cropped_same, crop_path = _crop_cache(cropped_same, checkpoint_len)
        crop_paths.add(crop_path)
        same_len_before = _cache_seq_length(cropped_same)
        same_logits, same_after = _forward_logits(model, same_token, cropped_same)
        same_len_after = _cache_seq_length(same_after)
        same_dev = _deviation(same_logits, step_logits[generated_prefix_len + 1])
        same_pass = same_len_before == checkpoint_len and same_len_after == checkpoint_len + 1 and same_dev["argmax_equal"] and same_dev["max_abs_logit_delta"] <= args.tol
        tests.append({"test": "resume_same", "checkpoint_generated_tokens": generated_prefix_len, "checkpoint_seq_len": checkpoint_len, "crop_path": crop_path, "cache_len_before_feed": same_len_before, "cache_len_after_feed": same_len_after, "pass": same_pass, **same_dev})
        overall = overall and same_pass

        diff_token_id = _different_token(int(same_token[0, 0].item()), int(model.config.vocab_size), avoid_ids)
        diff_token = torch.tensor([[diff_token_id]], dtype=full_ids.dtype, device=model.device)
        cropped_diff = copy.deepcopy(full_cache)
        cropped_diff, crop_path = _crop_cache(cropped_diff, checkpoint_len)
        crop_paths.add(crop_path)
        diff_len_before = _cache_seq_length(cropped_diff)
        diff_logits, diff_after = _forward_logits(model, diff_token, cropped_diff)
        diff_len_after = _cache_seq_length(diff_after)
        fresh_ids = torch.cat([full_ids[:, :checkpoint_len], diff_token], dim=1)
        fresh_logits, fresh_cache = _forward_logits(model, fresh_ids)
        fresh_len_after = _cache_seq_length(fresh_cache)
        diff_dev = _deviation(diff_logits, fresh_logits)
        diff_pass = diff_len_before == checkpoint_len and diff_len_after == checkpoint_len + 1 and fresh_len_after == checkpoint_len + 1 and diff_dev["argmax_equal"] and diff_dev["max_abs_logit_delta"] <= args.tol
        tests.append({"test": "resume_different_equals_fresh", "checkpoint_generated_tokens": generated_prefix_len, "checkpoint_seq_len": checkpoint_len, "crop_path": crop_path, "cache_len_before_feed": diff_len_before, "cache_len_after_feed": diff_len_after, "fresh_cache_len_after_feed": fresh_len_after, "different_token_id": diff_token_id, "pass": diff_pass, **diff_dev})
        overall = overall and diff_pass
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_KM3_PASS if overall else STATUS_KM3_FAIL,
        "generated_at": _now(),
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()},
        "prompt_tokens": prompt_len,
        "depth": int(args.depth),
        "full_cache_seq_len": _cache_seq_length(full_cache),
        "cache_type": type(full_cache).__name__,
        "cache_inventory": _cache_inventory(full_cache),
        "crop_paths": sorted(crop_paths),
        "partition_stats": _partition_stats(view, owner),
        "tol": float(args.tol),
        "max_abs_logit_delta": max((float(test.get("max_abs_logit_delta", 0.0)) for test in tests), default=0.0),
        "overall_pass": overall,
        "tests": tests,
        "source": SOURCE,
        "provenance": "kvcache_multiagent_cbj_km3_gate_v0",
    }
    _write_json(args.output, payload)
    return payload


def _chat_prompt(tokenizer: Any, prompt: str) -> str:
    if not hasattr(tokenizer, "apply_chat_template"):
        return prompt
    messages = [
        {"role": "system", "content": "You are a terse multi-agent graph-color conflict analyst. Follow the output format exactly."},
        {"role": "user", "content": prompt},
    ]
    try:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception:
        return prompt


@torch.no_grad()
def _generate_text(model: Any, tokenizer: Any, prompt: str, max_new_tokens: int) -> tuple[str, int, int]:
    ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(model.device)
    out = model(input_ids=ids, use_cache=True)
    cache = out.past_key_values
    logits = out.logits[:, -1, :]
    generated: list[torch.Tensor] = []
    eos_ids = {token for token in [tokenizer.eos_token_id, tokenizer.pad_token_id] if token is not None}
    text = ""
    for _ in range(max_new_tokens):
        token = logits.argmax(dim=-1, keepdim=True)
        generated.append(token)
        text = tokenizer.decode(torch.cat(generated, dim=1)[0], skip_special_tokens=True)
        out = model(input_ids=token, past_key_values=cache, use_cache=True)
        cache = out.past_key_values
        logits = out.logits[:, -1, :]
        if int(token[0, 0].item()) in eos_ids:
            break
        if re.search(r"BACKJUMP\s*:\s*agent\s*=\s*\d+\s+idx\s*=\s*\d+", text, flags=re.IGNORECASE):
            break
    return text.strip(), int(ids.shape[1]), len(generated)


def _parse_agent_idx(text: str, valid_targets: list[dict[str, int]]) -> dict[str, Any]:
    matches = list(re.finditer(r"BACKJUMP\s*:\s*agent\s*=\s*([+-]?\d+)\s+idx\s*=\s*([+-]?\d+)", text, flags=re.IGNORECASE))
    if not matches:
        return {"parseable": False, "valid": False, "agent": None, "idx": None, "invalid_reason": "parse_fail"}
    agent = int(matches[-1].group(1))
    idx = int(matches[-1].group(2))
    valid = any(int(item["agent"]) == agent and int(item["idx"]) == idx for item in valid_targets)
    return {"parseable": True, "valid": valid, "agent": agent, "idx": idx, "invalid_reason": None if valid else "out_of_range"}


def _agent_checkpoint_rows(register: list[dict[str, Any]], r_value: int) -> tuple[int, list[dict[str, int]]]:
    start = max(0, len(register) - int(r_value))
    rows = []
    for local_index, item in enumerate(register[start:]):
        rows.append({"idx": int(local_index), "var": int(item["vertex"]), "color": int(item["color"]), "step": int(item["order_index"])})
    return start, rows


def _cross_prompt(view: dict[str, Any], owner: dict[int, int], current_agent: int, vertex: int, assignment: dict[int, int], blockers: list[int], checkpoints_by_agent: dict[int, list[dict[str, int]]], valid_targets: list[dict[str, int]]) -> str:
    in_block = []
    cross = []
    for blocker in blockers:
        row = {"var": int(blocker), "color": int(assignment[int(blocker)]), "agent": int(owner[int(blocker)])}
        if owner[int(blocker)] == current_agent:
            in_block.append(row)
        else:
            cross.append(row)
    return "\n".join([
        "Multi-agent cross-block graph_color CBJ routing.",
        f"You are agent {int(current_agent)}. Dead end: variable {int(vertex)} has no legal color.",
        "Assigned in-block blockers: " + json.dumps(in_block, separators=(",", ":"), sort_keys=True),
        "Assigned cross-block boundary blockers: " + json.dumps(cross, separators=(",", ":"), sort_keys=True),
        "Open checkpoints by agent: " + json.dumps({str(int(agent)): rows for agent, rows in sorted(checkpoints_by_agent.items())}, separators=(",", ":"), sort_keys=True),
        "Valid backjump targets: " + json.dumps(valid_targets, separators=(",", ":"), sort_keys=True),
        "Choose the deepest culprit among the visible conflict blockers. Route to that agent and checkpoint.",
        "Use only a pair from valid backjump targets. Do not output a vertex id or step as idx.",
        "End with exactly one line: BACKJUMP: agent=<agent> idx=<idx>",
    ])


def _collect_probe_examples(entry: dict[str, Any], source_index: int, bin_label: str, k_value: int, r_values: list[int], args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    view = _graph_color_view(entry, args.order_mode)
    owner = _partition(view, int(k_value), float(args.balance_weight), int(args.seed) + int(source_index) + 100 * int(k_value))
    order = _agent_order(view, owner, args.agent_order)
    position = {vertex: index for index, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    tried: dict[int, set[int]] = defaultdict(set)
    registers: dict[int, list[dict[str, Any]]] = defaultdict(list)
    global_register: list[dict[str, Any]] = []
    cursor = 0
    step = 0
    examples: list[dict[str, Any]] = []
    no_recovery = 0
    while step < int(args.node_cap):
        if cursor >= len(order):
            break
        vertex = int(order[cursor])
        domain = _current_domain(view, vertex, assignment, tried)
        step += 1
        if domain:
            color = int(domain[0])
            tried[vertex].add(color)
            assignment[vertex] = color
            item = {"vertex": vertex, "color": color, "order_index": int(cursor), "agent": int(owner[vertex])}
            registers[int(owner[vertex])].append(item)
            global_register.append(item)
            cursor += 1
            continue
        if not global_register:
            break
        nogood = sorted(int(item) for item in _deadend_nogood(view, vertex, assignment, position))
        if any(owner[item] != owner[vertex] for item in nogood):
            oracle_vertex = max(nogood, key=lambda item: position[item]) if nogood else int(global_register[-1]["vertex"])
            oracle_agent = int(owner[oracle_vertex])
            for r_value in r_values:
                checkpoints_by_agent: dict[int, list[dict[str, int]]] = {}
                starts: dict[int, int] = {}
                valid_targets: list[dict[str, int]] = []
                for agent in sorted(set(owner.values())):
                    starts[int(agent)], checkpoints_by_agent[int(agent)] = _agent_checkpoint_rows(registers[int(agent)], int(r_value))
                for blocker in nogood:
                    agent = int(owner[blocker])
                    agent_register = registers[agent]
                    abs_index = max((idx for idx, item in enumerate(agent_register) if int(item["vertex"]) == int(blocker)), default=-1)
                    local_idx = abs_index - starts[agent]
                    if 0 <= local_idx < len(checkpoints_by_agent[agent]):
                        valid_targets.append({"agent": agent, "idx": int(local_idx), "var": int(blocker), "step": int(agent_register[abs_index]["order_index"])})
                oracle_abs = max((idx for idx, item in enumerate(registers[oracle_agent]) if int(item["vertex"]) == int(oracle_vertex)), default=-1)
                oracle_idx = oracle_abs - starts[oracle_agent]
                if not (0 <= oracle_idx < len(checkpoints_by_agent[oracle_agent])):
                    no_recovery += 1
                    continue
                prompt = _cross_prompt(view, owner, int(owner[vertex]), vertex, assignment, nogood, checkpoints_by_agent, valid_targets)
                latest = global_register[-1]
                latest_agent = int(latest["agent"])
                latest_agent_register = registers[latest_agent]
                latest_abs = len(latest_agent_register) - 1
                chrono_idx = latest_abs - starts[latest_agent]
                examples.append({
                    "example_id": f"{bin_label}_{source_index:04d}_K{k_value}_R{int(r_value)}_step{step:04d}",
                    "bin": bin_label,
                    "source_index": int(source_index),
                    "K": int(k_value),
                    "R": int(r_value),
                    "current_agent": int(owner[vertex]),
                    "conflict_vertex": vertex,
                    "oracle_agent": oracle_agent,
                    "oracle_idx": int(oracle_idx),
                    "oracle_vertex": int(oracle_vertex),
                    "chrono_agent": latest_agent,
                    "chrono_idx": int(chrono_idx) if 0 <= chrono_idx < len(checkpoints_by_agent[latest_agent]) else None,
                    "chrono_exact": bool(latest_agent == oracle_agent and chrono_idx == oracle_idx),
                    "valid_targets": valid_targets,
                    "prompt": prompt,
                    "partition_stats": _partition_stats(view, owner),
                    "source": SOURCE,
                    "provenance": "kvcache_multiagent_cbj_cross_probe_example_v0",
                })
        # Oracle rollback to continue collecting states.
        nogood_set = _deadend_nogood(view, vertex, assignment, position)
        target_vertex = max(nogood_set, key=lambda item: position[item]) if nogood_set else int(global_register[-1]["vertex"])
        target_global_index = max((idx for idx, item in enumerate(global_register) if int(item["vertex"]) == int(target_vertex)), default=len(global_register) - 1)
        popped = global_register[target_global_index:]
        for item in popped:
            assignment.pop(int(item["vertex"]), None)
        popped_vertices = {int(item["vertex"]) for item in popped}
        global_register = [item for item in global_register if int(item["vertex"]) not in popped_vertices]
        for agent in list(registers):
            registers[agent] = [item for item in registers[agent] if int(item["vertex"]) not in popped_vertices]
        for item in popped[1:]:
            tried[int(item["vertex"])] = set()
        tried[vertex] = set()
        cursor = int(popped[0]["order_index"]) if popped else max(0, cursor - 1)
    return examples, {"source_index": int(source_index), "K": int(k_value), "cross_examples": len(examples), "no_recovery_windows": int(no_recovery), "partition": _partition_stats(view, owner)}


def probe(args: argparse.Namespace) -> dict[str, Any]:
    model, tokenizer = _load_model(args)
    bins = _parse_bins(args.bins)
    r_values = _parse_ints(args.r_values)
    k_values = _parse_ints(args.k_values)
    rows: list[dict[str, Any]] = []
    preflight: list[dict[str, Any]] = []
    for bin_spec in bins:
        dataset = _make_dataset(args, bin_spec)
        selected = 0
        for source_index in range(int(args.scan_limit)):
            if int(args.num_shards) > 1 and source_index % int(args.num_shards) != int(args.shard_index):
                continue
            entry = dataset[source_index]
            entry.setdefault("metadata", {})["source_index"] = int(source_index)
            for k_value in k_values:
                examples, meta = _collect_probe_examples(entry, source_index, str(bin_spec["label"]), int(k_value), r_values, args)
                preflight.append({"bin": bin_spec["label"], **meta})
                for example in examples:
                    prompt = _chat_prompt(tokenizer, str(example["prompt"]))
                    text, input_tokens, output_tokens = _generate_text(model, tokenizer, prompt, int(args.max_new_tokens))
                    parsed = _parse_agent_idx(text, example["valid_targets"])
                    exact = bool(parsed.get("valid")) and int(parsed["agent"]) == int(example["oracle_agent"]) and int(parsed["idx"]) == int(example["oracle_idx"])
                    any_legal = bool(parsed.get("valid")) and any(int(target["agent"]) == int(parsed["agent"]) and int(target["idx"]) == int(parsed["idx"]) for target in example["valid_targets"])
                    rows.append({**example, "model_text": text[-512:], "input_tokens": input_tokens, "output_tokens": output_tokens, "parseable": bool(parsed.get("parseable")), "valid": bool(parsed.get("valid")), "pred_agent": parsed.get("agent"), "pred_idx": parsed.get("idx"), "invalid_reason": parsed.get("invalid_reason"), "exact": exact, "any_legal": any_legal, "chrono_baseline_exact": bool(example.get("chrono_exact")), "provenance": "kvcache_multiagent_cbj_cross_probe_row_v0"})
                    print(json.dumps({"bin": example["bin"], "K": example["K"], "R": example["R"], "source_index": example["source_index"], "exact": exact, "parseable": parsed.get("parseable")}), flush=True)
            if any(row["bin"] == str(bin_spec["label"]) for row in rows):
                selected += 1
            if selected >= int(args.n_instances):
                break
    summary = _summarize_probe(rows)
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_COMPLETE if rows else STATUS_PREFLIGHT_FAIL, "generated_at": _now(), "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "preflight": preflight, "summary": summary, "rows": rows, "source": SOURCE, "provenance": "kvcache_multiagent_cbj_cross_probe_v0"}
    _write_json(args.output, payload)
    return payload


def merge_probe(args: argparse.Namespace) -> dict[str, Any]:
    inputs = [Path(item) for item in args.inputs]
    payloads = [_read_json(path) for path in inputs]
    rows = [row for payload in payloads for row in payload.get("rows", [])]
    preflight = [row for payload in payloads for row in payload.get("preflight", [])]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE if rows else STATUS_PREFLIGHT_FAIL,
        "generated_at": _now(),
        "config": {"inputs": [str(path) for path in inputs]},
        "input_files": [str(path) for path in inputs],
        "preflight": preflight,
        "summary": _summarize_probe(rows),
        "rows": rows,
        "source": SOURCE,
        "provenance": "kvcache_multiagent_cbj_cross_probe_merged_v0",
    }
    _write_json(args.output, payload)
    return payload


def _summarize_probe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    groups = sorted({(row["bin"], int(row["K"]), int(row["R"])) for row in rows})
    for bin_label, k_value, r_value in groups:
        subset = [row for row in rows if row["bin"] == bin_label and int(row["K"]) == k_value and int(row["R"]) == r_value]
        out.append({
            "bin": bin_label,
            "K": k_value,
            "R": r_value,
            "n": len(subset),
            "parse_rate": mean(float(row["parseable"]) for row in subset),
            "valid_rate": mean(float(row["valid"]) for row in subset),
            "exact_rate": mean(float(row["exact"]) for row in subset),
            "any_legal_rate": mean(float(row["any_legal"]) for row in subset),
            "chrono_exact_rate": mean(float(row["chrono_baseline_exact"]) for row in subset),
            "mean_output_tokens": mean(float(row["output_tokens"]) for row in subset),
            "source": SOURCE,
            "provenance": "kvcache_multiagent_cbj_cross_probe_summary_v0",
        })
    return out


def _safe_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _blocked_by_color(view: dict[str, Any], owner: dict[int, int], vertex: int, color: int, assignment: dict[int, int], include_cross: bool) -> list[int]:
    blockers = []
    for neighbor in view["adjacency"][vertex]:
        if neighbor not in assignment or int(assignment[neighbor]) != int(color):
            continue
        if include_cross or owner[neighbor] == owner[vertex]:
            blockers.append(int(neighbor))
    return sorted(blockers)


def _estimate_tokens(tokenizer: Any | None, text: str) -> int:
    if tokenizer is None:
        return max(1, len(text) // 4)
    try:
        return int(len(tokenizer(text, add_special_tokens=False).input_ids))
    except Exception:
        return max(1, len(text) // 4)


def _event_tokens(tokenizer: Any | None, kind: str, payload: dict[str, Any]) -> int:
    return _estimate_tokens(tokenizer, kind + "\n" + json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _register_window(register: list[dict[str, Any]], r_value: int) -> tuple[int, list[dict[str, Any]]]:
    start = max(0, len(register) - int(r_value))
    return start, register[start:]


def _valid_targets_from_blockers(registers: dict[int, list[dict[str, Any]]], owner: dict[int, int], blockers: set[int], r_value: int) -> list[dict[str, int]]:
    rows: list[dict[str, int]] = []
    for blocker in sorted(blockers):
        agent = int(owner[int(blocker)])
        register = registers.get(agent, [])
        start, window = _register_window(register, int(r_value))
        abs_index = max((idx for idx, item in enumerate(register) if int(item["vertex"]) == int(blocker)), default=-1)
        local_idx = abs_index - start
        if 0 <= local_idx < len(window):
            item = register[abs_index]
            rows.append({"agent": agent, "idx": int(local_idx), "var": int(blocker), "step": int(item.get("order_index", -1))})
    return rows


def _latest_trail_vertex(trail: list[dict[str, Any]]) -> int | None:
    return int(trail[-1]["vertex"]) if trail else None


def _target_in_window(registers: dict[int, list[dict[str, Any]]], owner: dict[int, int], target_vertex: int, r_value: int) -> bool:
    agent = int(owner[int(target_vertex)])
    register = registers.get(agent, [])
    start, window = _register_window(register, int(r_value))
    abs_index = max((idx for idx, item in enumerate(register) if int(item["vertex"]) == int(target_vertex)), default=-1)
    return 0 <= abs_index - start < len(window)


def _model_route_target(model: Any, tokenizer: Any, prompt: str, valid_targets: list[dict[str, int]], oracle_target: dict[str, int] | None, max_new_tokens: int) -> tuple[int | None, dict[str, Any]]:
    text, input_tokens, output_tokens = _generate_text(model, tokenizer, _chat_prompt(tokenizer, prompt), max_new_tokens)
    parsed = _parse_agent_idx(text, valid_targets)
    row = next((item for item in valid_targets if parsed.get("valid") and int(item["agent"]) == int(parsed["agent"]) and int(item["idx"]) == int(parsed["idx"])), None)
    exact = bool(row and oracle_target and int(row["agent"]) == int(oracle_target["agent"]) and int(row["idx"]) == int(oracle_target["idx"]))
    return (int(row["var"]) if row else None), {"model_text": text[-512:], "input_tokens": input_tokens, "output_tokens": output_tokens, "parseable": bool(parsed.get("parseable")), "valid": bool(parsed.get("valid")), "exact": exact, "pred_agent": parsed.get("agent"), "pred_idx": parsed.get("idx"), "invalid_reason": parsed.get("invalid_reason")}


def _rollback_global_suffix(
    assignment: dict[int, int],
    next_idx: dict[int, int],
    conflict_sets: dict[int, set[int]],
    trail: list[dict[str, Any]],
    registers: dict[int, list[dict[str, Any]]],
    target_vertex: int,
    deadend_vertex: int,
    carry_conflict: set[int] | None,
) -> tuple[int, list[dict[str, Any]]]:
    target_indices = [idx for idx, item in enumerate(trail) if int(item["vertex"]) == int(target_vertex)]
    if not target_indices:
        return -1, []
    target_index = target_indices[-1]
    popped = trail[target_index:]
    popped_vertices = {int(item["vertex"]) for item in popped}
    for item in popped:
        assignment.pop(int(item["vertex"]), None)
    trail[:] = [item for item in trail if int(item["vertex"]) not in popped_vertices]
    for agent in list(registers):
        registers[agent] = [item for item in registers[agent] if int(item["vertex"]) not in popped_vertices]
    for item in popped[1:]:
        next_idx[int(item["vertex"])] = 0
        conflict_sets[int(item["vertex"])].clear()
    next_idx[int(deadend_vertex)] = 0
    conflict_sets[int(deadend_vertex)].clear()
    if carry_conflict is not None:
        conflict_sets[int(target_vertex)].update(int(item) for item in carry_conflict if int(item) != int(target_vertex))
    return int(popped[0]["order_index"]) if popped else -1, popped


def _rollback_broadcast(
    assignment: dict[int, int],
    next_idx: dict[int, int],
    conflict_sets: dict[int, set[int]],
    trail: list[dict[str, Any]],
    registers: dict[int, list[dict[str, Any]]],
    deadend_vertex: int,
) -> tuple[int, list[dict[str, Any]]]:
    latest_by_agent = {agent: entries[-1] for agent, entries in registers.items() if entries}
    if not latest_by_agent:
        return -1, []
    target_order = min(int(item["order_index"]) for item in latest_by_agent.values())
    popped = [item for item in trail if int(item["order_index"]) >= target_order]
    popped_vertices = {int(item["vertex"]) for item in popped}
    for item in popped:
        assignment.pop(int(item["vertex"]), None)
        next_idx[int(item["vertex"])] = 0
        conflict_sets[int(item["vertex"])].clear()
    trail[:] = [item for item in trail if int(item["vertex"]) not in popped_vertices]
    for agent in list(registers):
        registers[agent] = [item for item in registers[agent] if int(item["vertex"]) not in popped_vertices]
    next_idx[int(deadend_vertex)] = 0
    conflict_sets[int(deadend_vertex)].clear()
    return target_order, popped


def _run_structural_team(dataset: Any, entry: dict[str, Any], bin_label: str, k_value: int, r_value: int, arm: str, args: argparse.Namespace, tokenizer: Any | None = None, model: Any | None = None) -> dict[str, Any]:
    view = _graph_color_view(entry, args.order_mode)
    owner = _partition(view, int(k_value), float(args.balance_weight), int(args.seed) + int(entry["metadata"].get("source_index", 0)) + 100 * int(k_value))
    order = _agent_order(view, owner, args.agent_order)
    position = {int(vertex): idx for idx, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    next_idx = {int(vertex): 0 for vertex in order}
    conflict_sets: dict[int, set[int]] = {int(vertex): set() for vertex in order}
    registers: dict[int, list[dict[str, Any]]] = defaultdict(list)
    trail: list[dict[str, Any]] = []
    cursor = 0
    stats = Counter()
    per_agent_tokens: Counter[int] = Counter()
    status = "RUNNING"
    model_route_samples: list[dict[str, Any]] = []

    while True:
        if int(stats["steps"]) >= int(args.node_cap):
            status = "NODE_CAP"
            break
        if len(assignment) == len(order):
            status = "SOLVED"
            break
        while cursor < len(order) and int(order[cursor]) in assignment:
            cursor += 1
        if cursor >= len(order):
            remaining = [position[vertex] for vertex in order if int(vertex) not in assignment]
            if not remaining:
                status = "SOLVED"
                break
            cursor = min(remaining)
        vertex = int(order[cursor])
        agent = int(owner[vertex])
        include_cross = arm != "no_coordination"
        chosen = None
        blocked_this_round: set[int] = set()
        while next_idx[vertex] < len(view["color_options"]):
            color = int(view["color_options"][next_idx[vertex]])
            next_idx[vertex] += 1
            blockers = _blocked_by_color(view, owner, vertex, color, assignment, include_cross)
            if not blockers:
                chosen = color
                break
            conflict_sets[vertex].update(blockers)
            blocked_this_round.update(blockers)
            stats["blocked_color_checks"] += 1
            stats["cross_block_blocked_color_checks"] += int(any(owner[item] != agent for item in blockers))
        stats["steps"] += 1
        if chosen is not None:
            assignment[vertex] = int(chosen)
            item = {"vertex": vertex, "color": int(chosen), "agent": agent, "order_index": int(cursor)}
            trail.append(item)
            registers[agent].append(item)
            stats["branch_decisions"] += 1
            stats["max_trail_len"] = max(int(stats["max_trail_len"]), len(trail))
            stats[f"max_agent_{agent}_register_len"] = max(int(stats[f"max_agent_{agent}_register_len"]), len(registers[agent]))
            tokens = _event_tokens(tokenizer, "BRANCH", {"agent": agent, "vertex": vertex, "color": int(chosen), "blocked": sorted(blocked_this_round), "R": int(r_value)})
            per_agent_tokens[agent] += tokens
            stats["total_tokens"] += tokens
            cursor += 1
            continue

        blockers = {int(item) for item in conflict_sets[vertex] if int(item) in position and position[int(item)] < cursor}
        if not blockers:
            status = "EXHAUSTED"
            break
        cross_block = any(int(owner[item]) != agent for item in blockers)
        stats["deadends"] += 1
        stats["cross_block_deadends"] += int(cross_block)
        target_vertex: int | None
        carry_conflict: set[int] | None = None
        route_meta: dict[str, Any] = {}
        if arm == "cbj_cross_block":
            target_vertex = max(blockers, key=lambda item: position[item])
            carry_conflict = set(blockers)
        elif arm == "chronological_cross_block":
            target_vertex = _latest_trail_vertex(trail)
        elif arm == "broadcast":
            target_vertex = None
        elif arm == "model_route_autonomous" and cross_block and model is not None and tokenizer is not None:
            valid_targets = _valid_targets_from_blockers(registers, owner, blockers, int(r_value))
            oracle_vertex = max(blockers, key=lambda item: position[item])
            oracle_target = next((item for item in valid_targets if int(item["var"]) == int(oracle_vertex)), None)
            checkpoints_by_agent: dict[int, list[dict[str, int]]] = {}
            for item_agent in sorted(set(owner.values())):
                start, window = _register_window(registers[int(item_agent)], int(r_value))
                checkpoints_by_agent[int(item_agent)] = [{"idx": idx, "var": int(row["vertex"]), "color": int(row["color"]), "step": int(row["order_index"])} for idx, row in enumerate(window)]
            prompt = _cross_prompt(view, owner, agent, vertex, assignment, sorted(blockers), checkpoints_by_agent, valid_targets)
            target_vertex, route_meta = _model_route_target(model, tokenizer, prompt, valid_targets, oracle_target, int(args.max_new_tokens))
            stats["model_route_calls"] += 1
            stats["model_route_parseable"] += int(route_meta.get("parseable") is True)
            stats["model_route_valid"] += int(route_meta.get("valid") is True)
            stats["model_route_exact"] += int(route_meta.get("exact") is True)
            stats["total_tokens"] += int(route_meta.get("input_tokens", 0)) + int(route_meta.get("output_tokens", 0))
            per_agent_tokens[agent] += int(route_meta.get("input_tokens", 0)) + int(route_meta.get("output_tokens", 0))
            if len(model_route_samples) < int(args.trace_samples):
                model_route_samples.append({"vertex": vertex, "blockers": sorted(blockers), "oracle_vertex": int(oracle_vertex), **route_meta})
            if target_vertex is None:
                status = "INVALID_MODEL_ROUTE"
                break
            carry_conflict = set(blockers)
        else:
            target_vertex = max(blockers, key=lambda item: position[item])
            carry_conflict = set(blockers)

        tokens = _event_tokens(tokenizer, "BACKJUMP", {"arm": arm, "agent": agent, "vertex": vertex, "blockers": sorted(blockers), "target_vertex": target_vertex, "cross_block": cross_block})
        per_agent_tokens[agent] += tokens
        stats["total_tokens"] += tokens
        if arm == "broadcast" and cross_block:
            new_cursor, popped = _rollback_broadcast(assignment, next_idx, conflict_sets, trail, registers, vertex)
            if new_cursor < 0:
                status = "NO_RECOVERY_TARGET"
                break
            stats["broadcast_backjumps"] += 1
            stats["cross_block_messages"] += len(set(owner.values()))
        else:
            if target_vertex is None or not _target_in_window(registers, owner, int(target_vertex), int(r_value)):
                status = "NO_RECOVERY_TARGET"
                break
            stats["cross_block_backjumps"] += int(cross_block and int(owner[int(target_vertex)]) != agent)
            stats["cross_block_messages"] += int(cross_block)
            new_cursor, popped = _rollback_global_suffix(assignment, next_idx, conflict_sets, trail, registers, int(target_vertex), vertex, carry_conflict if arm in {"cbj_cross_block", "model_route_autonomous"} else None)
            if new_cursor < 0:
                status = "NO_RECOVERY_TARGET"
                break
        popped_agents = {int(item["agent"]) for item in popped}
        stats["recoveries"] += 1
        stats["retractions"] += len(popped)
        stats["cascade_depth_sum"] += len(popped_agents)
        stats["cascade_depth_max"] = max(int(stats["cascade_depth_max"]), len(popped_agents))
        stats["cross_agent_cascade_events"] += int(len(popped_agents) > 1)
        cursor = max(0, int(new_cursor))

    score = _official_score(dataset, entry, assignment) if len(assignment) == len(order) else 0.0
    if score < 1.0 and status == "SOLVED":
        status = "OFFICIAL_SCORE_FAIL"
    return {
        "bin": bin_label,
        "source_index": int(entry["metadata"].get("source_index", -1)),
        "K": int(k_value),
        "R": int(r_value),
        "arm": arm,
        "status": "SOLVED" if score >= 1.0 else status,
        "solved": score >= 1.0,
        "official_score": float(score),
        "B": len(set(owner.values())),
        "n_vertices": len(view["vertices"]),
        "n_edges": len(view["edges"]),
        "partition": _partition_stats(view, owner),
        "branch_decisions": int(stats["branch_decisions"]),
        "deadends": int(stats["deadends"]),
        "cross_block_deadends": int(stats["cross_block_deadends"]),
        "cross_block_backjumps": int(stats["cross_block_backjumps"]),
        "broadcast_backjumps": int(stats["broadcast_backjumps"]),
        "cross_block_messages": int(stats["cross_block_messages"]),
        "recoveries": int(stats["recoveries"]),
        "retractions": int(stats["retractions"]),
        "mean_cascade_depth": float(stats["cascade_depth_sum"]) / max(1, int(stats["recoveries"])),
        "max_cascade_depth": int(stats["cascade_depth_max"]),
        "cross_agent_cascade_events": int(stats["cross_agent_cascade_events"]),
        "total_tokens": int(stats["total_tokens"]),
        "per_agent_tokens": {str(agent): int(per_agent_tokens[agent]) for agent in sorted(set(owner.values()))},
        "model_route_calls": int(stats["model_route_calls"]),
        "model_route_parseable": int(stats["model_route_parseable"]),
        "model_route_valid": int(stats["model_route_valid"]),
        "model_route_exact": int(stats["model_route_exact"]),
        "model_route_samples": model_route_samples,
        "answer": _official_answer(assignment) if score >= 1.0 else None,
        "source": SOURCE,
        "provenance": "kvcache_multiagent_cbj_structural_team_row_v0",
    }


def _run_structural_monolith(dataset: Any, entry: dict[str, Any], bin_label: str, k_value: int, r_value: int, capacity_arm: str, args: argparse.Namespace, tokenizer: Any | None) -> dict[str, Any]:
    effective_r = int(r_value) if capacity_arm == "monolith_R" else int(k_value) * int(r_value)
    row = _run_structural_team(dataset, entry, bin_label, 1, effective_r, "cbj_cross_block", args, tokenizer=tokenizer, model=None)
    row.update({"K_reference": int(k_value), "R_reference": int(r_value), "capacity_arm": capacity_arm, "effective_R": effective_r, "arm": capacity_arm, "provenance": "kvcache_multiagent_cbj_structural_monolith_row_v0"})
    return row


def _summarize_structural(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    team_rows = [row for row in rows if row.get("row_kind") == "team"]
    capacity_rows = [row for row in rows if row.get("row_kind") == "capacity"]
    ma1_solve: list[dict[str, Any]] = []
    ma1_cost: list[dict[str, Any]] = []
    tokens: list[dict[str, Any]] = []
    for key in sorted({(row["bin"], int(row["K"]), int(row["R"]), row["arm"]) for row in team_rows}):
        bin_label, k_value, r_value, arm = key
        subset = [row for row in team_rows if row["bin"] == bin_label and int(row["K"]) == k_value and int(row["R"]) == r_value and row["arm"] == arm]
        status_counts = dict(Counter(str(row["status"]) for row in subset))
        ma1_solve.append({"bin": bin_label, "K": k_value, "R": r_value, "arm": arm, "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "mean_official_score": mean(float(row["official_score"]) for row in subset), "status_counts": status_counts, "source": SOURCE, "provenance": "kvcache_multiagent_cbj_ma1_solve_summary_v0"})
        ma1_cost.append({"bin": bin_label, "K": k_value, "R": r_value, "arm": arm, "n": len(subset), "mean_cross_block_backjumps": mean(float(row.get("cross_block_backjumps", 0)) for row in subset), "mean_cross_block_messages": mean(float(row.get("cross_block_messages", 0)) for row in subset), "mean_retractions": mean(float(row.get("retractions", 0)) for row in subset), "mean_cascade_depth": mean(float(row.get("mean_cascade_depth", 0.0)) for row in subset), "max_cascade_depth": max(int(row.get("max_cascade_depth", 0)) for row in subset), "mean_cross_agent_cascade_events": mean(float(row.get("cross_agent_cascade_events", 0)) for row in subset), "source": SOURCE, "provenance": "kvcache_multiagent_cbj_ma1_coordination_cost_summary_v0"})
        tokens.append({"bin": bin_label, "K": k_value, "R": r_value, "arm": arm, "n": len(subset), "mean_total_tokens": mean(float(row.get("total_tokens", 0)) for row in subset), "source": SOURCE, "provenance": "kvcache_multiagent_cbj_token_summary_v0"})
    ma2_capacity: list[dict[str, Any]] = []
    for key in sorted({(row["bin"], int(row.get("K_reference", row.get("K", 0))), int(row.get("R_reference", row.get("R", 0))), row["capacity_arm"]) for row in capacity_rows}):
        bin_label, k_value, r_value, arm = key
        subset = [row for row in capacity_rows if row["bin"] == bin_label and int(row.get("K_reference", row.get("K", 0))) == k_value and int(row.get("R_reference", row.get("R", 0))) == r_value and row["capacity_arm"] == arm]
        ma2_capacity.append({"bin": bin_label, "K": k_value, "R": r_value, "capacity_arm": arm, "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "mean_official_score": mean(float(row["official_score"]) for row in subset), "mean_total_tokens": mean(float(row.get("total_tokens", 0)) for row in subset), "status_counts": dict(Counter(str(row["status"]) for row in subset)), "source": SOURCE, "provenance": "kvcache_multiagent_cbj_ma2_capacity_summary_v0"})
    model_rows = [row for row in team_rows if row.get("arm") == "model_route_autonomous"]
    model_route_autonomous: list[dict[str, Any]] = []
    for key in sorted({(row["bin"], int(row["K"]), int(row["R"])) for row in model_rows}):
        bin_label, k_value, r_value = key
        subset = [row for row in model_rows if row["bin"] == bin_label and int(row["K"]) == k_value and int(row["R"]) == r_value]
        calls = sum(int(row.get("model_route_calls", 0)) for row in subset)
        model_route_autonomous.append({"bin": bin_label, "K": k_value, "R": r_value, "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "model_route_calls": calls, "parse_rate": (sum(int(row.get("model_route_parseable", 0)) for row in subset) / calls) if calls else None, "valid_rate": (sum(int(row.get("model_route_valid", 0)) for row in subset) / calls) if calls else None, "exact_rate": (sum(int(row.get("model_route_exact", 0)) for row in subset) / calls) if calls else None, "source": SOURCE, "provenance": "kvcache_multiagent_cbj_model_route_autonomous_summary_v0"})
    return {"ma1_solve": ma1_solve, "ma1_coordination_cost": ma1_cost, "ma2_capacity": ma2_capacity, "tokens": tokens, "model_route_autonomous": model_route_autonomous}


def run_structural(args: argparse.Namespace) -> dict[str, Any]:
    bins = _parse_bins(args.bins)
    r_values = _parse_ints(args.r_values)
    k_values = _parse_ints(args.k_values)
    arms = [item.strip() for item in args.arms.split(",") if item.strip()]
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True) if args.token_accounting == "tokenizer" or args.include_model_route else None
    if tokenizer is not None and tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = None
    if args.include_model_route:
        model, tokenizer = _load_model(args)
        if "model_route_autonomous" not in arms:
            arms.append("model_route_autonomous")
    rows: list[dict[str, Any]] = []
    preflight: list[dict[str, Any]] = []
    for bin_spec in bins:
        dataset = _make_dataset(args, bin_spec)
        selected = 0
        for source_index in range(int(args.scan_limit)):
            if int(args.num_shards) > 1 and source_index % int(args.num_shards) != int(args.shard_index):
                continue
            entry = dataset[source_index]
            entry.setdefault("metadata", {})["source_index"] = int(source_index)
            selected += 1
            for k_value in k_values:
                view = _graph_color_view(entry, args.order_mode)
                owner = _partition(view, int(k_value), float(args.balance_weight), int(args.seed) + int(source_index) + 100 * int(k_value))
                preflight.append({"bin": bin_spec["label"], "source_index": int(source_index), "K": int(k_value), "partition": _partition_stats(view, owner)})
                for r_value in r_values:
                    for arm in arms:
                        row = _run_structural_team(dataset, entry, str(bin_spec["label"]), int(k_value), int(r_value), arm, args, tokenizer=tokenizer, model=model)
                        row["row_kind"] = "team"
                        row["capacity_arm"] = "team_cbj" if arm == "cbj_cross_block" else None
                        rows.append(row)
                        print(json.dumps({"bin": row["bin"], "source_index": row["source_index"], "K": row["K"], "R": row["R"], "arm": row["arm"], "status": row["status"], "solved": row["solved"]}), flush=True)
                    team_row = _run_structural_team(dataset, entry, str(bin_spec["label"]), int(k_value), int(r_value), "cbj_cross_block", args, tokenizer=tokenizer, model=None)
                    team_row["row_kind"] = "capacity"
                    team_row["capacity_arm"] = "team_cbj"
                    team_row["K_reference"] = int(k_value)
                    team_row["R_reference"] = int(r_value)
                    rows.append(team_row)
                    for capacity_arm in ["monolith_R", "monolith_KR"]:
                        row = _run_structural_monolith(dataset, entry, str(bin_spec["label"]), int(k_value), int(r_value), capacity_arm, args, tokenizer=tokenizer)
                        row["row_kind"] = "capacity"
                        rows.append(row)
            if selected >= int(args.n_instances):
                break
    summary = _summarize_structural(rows)
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_COMPLETE if rows else STATUS_PREFLIGHT_FAIL, "generated_at": _now(), "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "preflight": preflight, "summary": summary, "rows": rows, "source": SOURCE, "provenance": "kvcache_multiagent_cbj_structural_run_v0"}
    _write_json(args.output, payload)
    return payload


def merge_structural(args: argparse.Namespace) -> dict[str, Any]:
    inputs = [Path(item) for item in args.inputs]
    payloads = [_read_json(path) for path in inputs]
    rows = [row for payload in payloads for row in payload.get("rows", [])]
    preflight = [row for payload in payloads for row in payload.get("preflight", [])]
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_COMPLETE if rows else STATUS_PREFLIGHT_FAIL, "generated_at": _now(), "config": {"inputs": [str(path) for path in inputs]}, "input_files": [str(path) for path in inputs], "preflight": preflight, "summary": _summarize_structural(rows), "rows": rows, "source": SOURCE, "provenance": "kvcache_multiagent_cbj_structural_merged_v0"}
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="KV-cache multi-agent cross-block CBJ gates/probes.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--reasoning-gym-repo", default=None)
        p.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
        p.add_argument("--device", default="cuda")
        p.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32")
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--scan-limit", type=int, default=1000)
        p.add_argument("--num-colors", type=int, default=3)
        p.add_argument("--order-mode", default="degree_desc", choices=["degree_desc", "natural"])
        p.add_argument("--bins", default="v14_p04:14:0.4")
        p.add_argument("--balance-weight", type=float, default=0.2)

    gate = sub.add_parser("km3-gate")
    add_common(gate)
    gate.add_argument("--output", type=Path, default=Path("results/kvcache_multiagent_cbj/km3_gate.json"))
    gate.add_argument("--source-index", type=int, default=0)
    gate.add_argument("--k-value", type=int, default=2)
    gate.add_argument("--depth", type=int, default=16)
    gate.add_argument("--checkpoints", default="2,4,8,12")
    gate.add_argument("--tol", type=float, default=1e-3)

    probe_parser = sub.add_parser("probe")
    add_common(probe_parser)
    probe_parser.add_argument("--output", type=Path, default=Path("results/kvcache_multiagent_cbj/probe_k2.json"))
    probe_parser.add_argument("--k-values", default="2")
    probe_parser.add_argument("--r-values", default="2,4,8")
    probe_parser.add_argument("--n-instances", type=int, default=10)
    probe_parser.add_argument("--node-cap", type=int, default=500)
    probe_parser.add_argument("--agent-order", default="round_robin", choices=["degree_owner", "round_robin", "agent_blocks"])
    probe_parser.add_argument("--max-new-tokens", type=int, default=128)
    probe_parser.add_argument("--num-shards", type=int, default=1)
    probe_parser.add_argument("--shard-index", type=int, default=0)

    merge_parser = sub.add_parser("merge-probe")
    merge_parser.add_argument("--inputs", nargs="+", required=True)
    merge_parser.add_argument("--output", type=Path, default=Path("results/kvcache_multiagent_cbj/probe_merged.json"))

    structural = sub.add_parser("run-structural")
    add_common(structural)
    structural.add_argument("--output", type=Path, default=Path("results/kvcache_multiagent_cbj/structural_k2.json"))
    structural.add_argument("--k-values", default="2")
    structural.add_argument("--r-values", default="2,4")
    structural.add_argument("--n-instances", type=int, default=12)
    structural.add_argument("--node-cap", type=int, default=1000)
    structural.add_argument("--agent-order", default="round_robin", choices=["degree_owner", "round_robin", "agent_blocks"])
    structural.add_argument("--arms", default="cbj_cross_block,chronological_cross_block,broadcast,no_coordination")
    structural.add_argument("--token-accounting", default="tokenizer", choices=["tokenizer", "char_proxy"])
    structural.add_argument("--include-model-route", action="store_true")
    structural.add_argument("--max-new-tokens", type=int, default=96)
    structural.add_argument("--trace-samples", type=int, default=8)
    structural.add_argument("--num-shards", type=int, default=1)
    structural.add_argument("--shard-index", type=int, default=0)

    merge_structural_parser = sub.add_parser("merge-structural")
    merge_structural_parser.add_argument("--inputs", nargs="+", required=True)
    merge_structural_parser.add_argument("--output", type=Path, default=Path("results/kvcache_multiagent_cbj/structural_merged.json"))

    args = parser.parse_args()
    if args.command == "km3-gate":
        km3_gate(args)
    elif args.command == "probe":
        probe(args)
    elif args.command == "merge-probe":
        merge_probe(args)
    elif args.command == "run-structural":
        run_structural(args)
    elif args.command == "merge-structural":
        merge_structural(args)


if __name__ == "__main__":
    main()