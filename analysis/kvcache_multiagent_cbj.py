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
from experiments.rung1_reasoning_gym_bounded_register import _current_domain, _deadend_nogood, _ensure_reasoning_gym, _graph_color_view


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

    args = parser.parse_args()
    if args.command == "km3-gate":
        km3_gate(args)
    elif args.command == "probe":
        probe(args)
    elif args.command == "merge-probe":
        merge_probe(args)


if __name__ == "__main__":
    main()