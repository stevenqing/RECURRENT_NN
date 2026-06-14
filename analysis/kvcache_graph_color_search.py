"""Run graph_color KV-cache checkpoint search arms under direct Transformers."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from statistics import mean
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from analysis.kvcache_exactness_gate import _cache_seq_length, _crop_cache
from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_reasoning_gym_bounded_register import (
    _backtrack_prompt,
    _branch_prompt,
    _clean_trace,
    _current_domain,
    _deadend_nogood,
    _ensure_reasoning_gym,
    _entry_for_register,
    _graph_color_view,
    _official_answer,
    _official_score,
)


SCHEMA_VERSION = "kvcache_graph_color_search_v1"
STATUS_COMPLETE = "KVCACHE_GRAPH_COLOR_SEARCH_COMPLETE"
STATUS_PREFLIGHT_FAIL = "KVCACHE_GRAPH_COLOR_SEARCH_PREFLIGHT_FAIL"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status = payload.get("status") if isinstance(payload, dict) else f"rows={len(payload)}"
    print(json.dumps({"path": _rel(path), "status": status}), flush=True)


def _read_json(path: Path) -> Any:
    path = path if path.is_absolute() else REPO_ROOT / path
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _make_dataset(args: argparse.Namespace) -> Any:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
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
    selected: list[dict[str, Any]] = []
    preflight: list[dict[str, Any]] = []
    for index in range(args.scan_limit):
        entry = dataset[index]
        entry.setdefault("metadata", {})["source_index"] = index
        trace = _clean_trace(entry, args.order_mode, args.node_cap, dataset)
        row = {"source_index": index, "selected": bool(trace.get("solved") and int(trace.get("total_retractions", 0)) >= args.min_backtracks), **trace}
        preflight.append(row)
        if row["selected"]:
            selected.append({"entry": entry, "source_index": index, "trace": trace})
        if len(selected) >= args.n_instances:
            break
    return selected, preflight, {"selected_instances": len(selected), "scan_limit": args.scan_limit, "min_backtracks": args.min_backtracks, "source": SOURCE, "provenance": "kvcache_graph_color_preflight_v1"}


def _load_model(args: argparse.Namespace) -> tuple[Any, Any]:
    device = torch.device(args.device if torch.cuda.is_available() or not args.device.startswith("cuda") else "cpu")
    dtype = torch.float32 if args.dtype == "fp32" else torch.bfloat16 if args.dtype == "bf16" and device.type == "cuda" else torch.float16 if args.dtype == "fp16" and device.type == "cuda" else torch.float32
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=dtype, trust_remote_code=True).to(device).eval()
    model.config.use_cache = True
    return model, tokenizer


@torch.no_grad()
def _forward(model: Any, ids: torch.Tensor, cache: Any | None) -> tuple[torch.Tensor, Any]:
    out = model(input_ids=ids, past_key_values=cache, use_cache=True)
    return out.logits[:, -1, :], out.past_key_values


def _feed(model: Any, tokenizer: Any, text: str, cache: Any | None) -> tuple[torch.Tensor, Any, int]:
    ids = tokenizer(text, return_tensors="pt", add_special_tokens=False).input_ids.to(model.device)
    logits, cache = _forward(model, ids, cache)
    return logits, cache, int(ids.shape[1])


@torch.no_grad()
def _generate_json(model: Any, tokenizer: Any, prompt: str, cache: Any | None, max_new_tokens: int) -> tuple[str, Any, dict[str, int]]:
    logits, cache, prompt_tokens = _feed(model, tokenizer, prompt, cache)
    generated: list[torch.Tensor] = []
    for _ in range(max_new_tokens):
        token = logits.argmax(dim=-1, keepdim=True)
        generated.append(token)
        text = tokenizer.decode(torch.cat(generated, dim=1)[0], skip_special_tokens=True)
        logits, cache = _forward(model, token, cache)
        if "{" in text and "}" in text and text.find("{") < text.rfind("}"):
            break
    output = torch.cat(generated, dim=1) if generated else torch.empty((1, 0), dtype=torch.long, device=model.device)
    text = tokenizer.decode(output[0], skip_special_tokens=True).strip()
    return text, cache, {"input_tokens": prompt_tokens, "output_tokens": int(output.shape[1]), "total_tokens": prompt_tokens + int(output.shape[1])}


def _parse_json(text: str) -> dict[str, Any] | None:
    candidates = []
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{"): text.rfind("}") + 1])
    candidates.extend(re.findall(r"\{.*?\}", text, flags=re.DOTALL))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _branch_prompt_ext(entry: dict[str, Any], vertex: int, domain: list[int], neighbors: list[dict[str, int]], tried: set[int], arm: str) -> str:
    return _branch_prompt(entry, vertex, domain, neighbors) + f"\narm={arm}; already_tried_values={sorted(int(v) for v in tried)}\nReturn only JSON now.\n"


def _backtrack_prompt_ext(entry: dict[str, Any], vertex: int, blockers: list[int], bounded: list[dict[str, Any]], arm: str) -> str:
    return _backtrack_prompt(entry, vertex, blockers, bounded) + f"\narm={arm}\nReturn only JSON now.\n"


def _choose_color(parsed: dict[str, Any] | None, domain: list[int]) -> tuple[int, bool, bool]:
    if parsed is None or "color" not in parsed:
        return int(domain[0]), False, False
    try:
        color = int(parsed["color"])
    except Exception:
        return int(domain[0]), False, False
    return (color if color in domain else int(domain[0])), True, color in domain


def _choose_backtrack(parsed: dict[str, Any] | None, view_len: int) -> tuple[int, bool, bool]:
    fallback = max(0, view_len - 1)
    if parsed is None or "entry_index" not in parsed:
        return fallback, False, False
    try:
        index = int(parsed["entry_index"])
    except Exception:
        return fallback, False, False
    return (index if 0 <= index < view_len else fallback), True, 0 <= index < view_len


def _rollback(assignment: dict[int, int], tried: dict[int, set[int]], register: list[dict[str, Any]], conflict_vertex: int, target_abs: int) -> tuple[int, int]:
    popped = register[target_abs:]
    for item in popped:
        assignment.pop(int(item["vertex"]), None)
    for item in popped[1:]:
        tried[int(item["vertex"])] = set()
    tried[conflict_vertex] = set()
    cursor = int(register[target_abs]["order_index"])
    del register[target_abs:]
    return cursor, len(popped)


def _finish(dataset: Any, selected: dict[str, Any], arm: str, r: int, status: str, assignment: dict[int, int], stats: Counter, context_rows: list[dict[str, Any]]) -> dict[str, Any]:
    score = _official_score(dataset, selected["entry"], assignment) if len(assignment) == len(selected["entry"]["metadata"]["puzzle"]["vertices"]) else 0.0
    return {
        "source_index": int(selected["source_index"]),
        "arm": arm,
        "R": int(r),
        "status": "SOLVED" if score >= 1.0 else status,
        "solved": score >= 1.0,
        "official_score": score,
        "decision_calls": int(stats["decision_calls"]),
        "branch_calls": int(stats["branch_calls"]),
        "backtrack_calls": int(stats["backtrack_calls"]),
        "branch_accuracy_vs_oracle": int(stats["branch_correct"]) / max(1, int(stats["branch_calls"])),
        "backtrack_accuracy_vs_oracle": int(stats["backtrack_correct"]) / max(1, int(stats["backtrack_calls"])),
        "parseable_rate": int(stats["parseable"]) / max(1, int(stats["decision_calls"])),
        "valid_decision_rate": int(stats["valid"]) / max(1, int(stats["decision_calls"])),
        "input_tokens": int(stats["input_tokens"]),
        "output_tokens": int(stats["output_tokens"]),
        "total_tokens": int(stats["total_tokens"]),
        "total_retractions": int(stats["retractions"]),
        "context_rows": context_rows,
        "answer": _official_answer(assignment) if score >= 1.0 else None,
        "source": SOURCE,
        "provenance": "kvcache_graph_color_search_row_v1",
    }


def _run_arm(model: Any, tokenizer: Any, dataset: Any, selected: dict[str, Any], arm: str, r: int, args: argparse.Namespace) -> dict[str, Any]:
    entry = selected["entry"]
    view = _graph_color_view(entry, args.order_mode)
    position = {vertex: i for i, vertex in enumerate(view["order"])}
    assignment: dict[int, int] = {}
    tried: dict[int, set[int]] = defaultdict(set)
    register: list[dict[str, Any]] = []
    transcript = f"Graph_color search arm={arm}.\nProblem:\n{entry.get('question','')}\n"
    cache = None
    stats = Counter()
    if arm == "A_cache":
        _, cache, used = _feed(model, tokenizer, transcript, None)
        stats["input_tokens"] += used
        stats["total_tokens"] += used
    cursor = 0
    context_rows: list[dict[str, Any]] = []
    while True:
        if int(stats["decision_calls"]) >= args.call_cap:
            return _finish(dataset, selected, arm, r, "CALL_CAP", assignment, stats, context_rows)
        if cursor >= len(view["order"]):
            return _finish(dataset, selected, arm, r, "SOLVED", assignment, stats, context_rows)
        vertex = view["order"][cursor]
        domain = _current_domain(view, vertex, assignment, tried)
        if domain:
            if r > 0 and len(register) >= r:
                return _finish(dataset, selected, arm, r, "NO_RECOVERY_TARGET", assignment, stats, context_rows)
            neighbors = [{"neighbor": n, "color": assignment[n]} for n in sorted(view["adjacency"][vertex]) if n in assignment]
            oracle = int(domain[0])
            prompt = _branch_prompt_ext(entry, vertex, domain, neighbors, tried[vertex], arm)
            checkpoint = _cache_seq_length(cache) if arm == "A_cache" else None
            if arm == "A_cache":
                context_tokens = _cache_seq_length(cache)
                text, cache, usage = _generate_json(model, tokenizer, "\nNEXT_BRANCH\n" + prompt, cache, args.max_new_tokens)
            elif arm == "C_incontext":
                full_prompt = transcript + "\nNEXT_BRANCH\n" + prompt
                context_tokens = len(tokenizer(full_prompt, add_special_tokens=False).input_ids)
                text, _, usage = _generate_json(model, tokenizer, full_prompt, None, args.max_new_tokens)
            else:
                context_tokens = len(tokenizer(prompt, add_special_tokens=False).input_ids)
                text, _, usage = _generate_json(model, tokenizer, prompt, None, args.max_new_tokens)
            parsed = _parse_json(text)
            color, parseable, valid = _choose_color(parsed, domain)
            stats["decision_calls"] += 1
            stats["branch_calls"] += 1
            stats["branch_correct"] += int(valid and color == oracle)
            stats["parseable"] += int(parseable)
            stats["valid"] += int(valid)
            stats["input_tokens"] += usage["input_tokens"]
            stats["output_tokens"] += usage["output_tokens"]
            stats["total_tokens"] += usage["total_tokens"]
            tried[vertex].add(color)
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor, "cache_pos": checkpoint})
            transcript += f"BRANCH vertex={vertex} color={color} domain={domain} tried={sorted(tried[vertex])}\n"
            context_rows.append({"depth": len(register), "context_tokens": context_tokens, "action": "branch"})
            cursor += 1
            continue
        if r == 0:
            return _finish(dataset, selected, arm, r, "FORWARD_DEAD_END", assignment, stats, context_rows)
        nogood = _deadend_nogood(view, vertex, assignment, position)
        oracle_vertex = max(nogood, key=lambda item: position[item]) if nogood else register[-1]["vertex"]
        oracle_abs = max((i for i, item in enumerate(register) if item["vertex"] == oracle_vertex), default=len(register) - 1)
        start = max(0, len(register) - r)
        bounded = [_entry_for_register(item, i - start) for i, item in enumerate(register[start:])]
        oracle_view = oracle_abs - start
        if not (0 <= oracle_view < len(bounded)):
            return _finish(dataset, selected, arm, r, "NO_RECOVERY_TARGET", assignment, stats, context_rows)
        prompt = _backtrack_prompt_ext(entry, vertex, sorted(nogood), bounded, arm)
        if arm == "A_cache":
            context_tokens = _cache_seq_length(cache)
            text, cache, usage = _generate_json(model, tokenizer, "\nDEAD_END\n" + prompt, cache, args.max_new_tokens)
        elif arm == "C_incontext":
            full_prompt = transcript + f"DEAD_END vertex={vertex} blockers={sorted(nogood)}\n" + prompt
            context_tokens = len(tokenizer(full_prompt, add_special_tokens=False).input_ids)
            text, _, usage = _generate_json(model, tokenizer, full_prompt, None, args.max_new_tokens)
        else:
            context_tokens = len(tokenizer(prompt, add_special_tokens=False).input_ids)
            text, _, usage = _generate_json(model, tokenizer, prompt, None, args.max_new_tokens)
        parsed = _parse_json(text)
        chosen, parseable, valid = _choose_backtrack(parsed, len(bounded))
        stats["decision_calls"] += 1
        stats["backtrack_calls"] += 1
        stats["backtrack_correct"] += int(valid and chosen == oracle_view)
        stats["parseable"] += int(parseable)
        stats["valid"] += int(valid)
        stats["input_tokens"] += usage["input_tokens"]
        stats["output_tokens"] += usage["output_tokens"]
        stats["total_tokens"] += usage["total_tokens"]
        target_abs = start + chosen
        if arm == "A_cache":
            checkpoint = register[target_abs].get("cache_pos")
            if checkpoint is None:
                return _finish(dataset, selected, arm, r, "CACHE_CHECKPOINT_MISSING", assignment, stats, context_rows)
            cache, _ = _crop_cache(cache, int(checkpoint))
        cursor, popped = _rollback(assignment, tried, register, vertex, target_abs)
        stats["retractions"] += popped
        transcript += f"DEAD_END vertex={vertex} chosen={chosen} oracle={oracle_view} popped={popped}\n"
        context_rows.append({"depth": len(register), "context_tokens": context_tokens, "action": "backtrack"})


def _run_one_shot(model: Any, tokenizer: Any, dataset: Any, selected: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    prompt = selected["entry"].get("question", "") + "\nReturn exactly one JSON object mapping every vertex string to an integer color.\n"
    text, _, usage = _generate_json(model, tokenizer, prompt, None, args.one_shot_max_tokens)
    try:
        score = float(dataset.score_answer(text, selected["entry"]))
    except Exception:
        score = 0.0
    return {"source_index": int(selected["source_index"]), "arm": "D_one_shot", "R": 0, "status": "SOLVED" if score >= 1.0 else "SCORE_FAIL", "solved": score >= 1.0, "official_score": score, "decision_calls": 1, "branch_calls": 0, "backtrack_calls": 0, "branch_accuracy_vs_oracle": None, "backtrack_accuracy_vs_oracle": None, "parseable_rate": None, "valid_decision_rate": None, "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"], "total_tokens": usage["total_tokens"], "context_rows": [{"depth": 0, "context_tokens": usage["input_tokens"], "action": "one_shot"}], "source": SOURCE, "provenance": "kvcache_graph_color_one_shot_v1"}


def _summarize(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    solve_by_R: list[dict[str, Any]] = []
    quality: list[dict[str, Any]] = []
    context: list[dict[str, Any]] = []
    tokens: list[dict[str, Any]] = []
    for arm, r in sorted({(row["arm"], int(row["R"])) for row in rows}):
        subset = [row for row in rows if row["arm"] == arm and int(row["R"]) == r]
        solve_by_R.append({"arm": arm, "R": r, "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "mean_official_score": mean(float(row["official_score"]) for row in subset), "status_counts": dict(Counter(row["status"] for row in subset)), "source": SOURCE, "provenance": "kvcache_solve_by_R_v1"})
        branches = [row["branch_accuracy_vs_oracle"] for row in subset if row.get("branch_accuracy_vs_oracle") is not None]
        backs = [row["backtrack_accuracy_vs_oracle"] for row in subset if row.get("backtrack_accuracy_vs_oracle") is not None]
        quality.append({"arm": arm, "R": r, "n": len(subset), "branch_accuracy_vs_oracle": mean(branches) if branches else None, "backtrack_accuracy_vs_oracle": mean(backs) if backs else None, "source": SOURCE, "provenance": "kvcache_decision_quality_v1"})
        tokens.append({"arm": arm, "R": r, "n": len(subset), "mean_total_tokens": mean(int(row["total_tokens"]) for row in subset), "mean_input_tokens": mean(int(row.get("input_tokens", 0)) for row in subset), "mean_output_tokens": mean(int(row.get("output_tokens", 0)) for row in subset), "source": SOURCE, "provenance": "kvcache_tokens_v1"})
        buckets: dict[int, list[int]] = defaultdict(list)
        for row in subset:
            for item in row.get("context_rows", []):
                buckets[int(item["depth"])].append(int(item["context_tokens"]))
        for depth, vals in sorted(buckets.items()):
            context.append({"arm": arm, "R": r, "depth": depth, "n": len(vals), "mean_context_tokens": mean(vals), "max_context_tokens": max(vals), "source": SOURCE, "provenance": "kvcache_context_vs_depth_v1"})
    def rate(arm: str, r: int) -> float | None:
        return next((row["solve_rate"] for row in solve_by_R if row["arm"] == arm and row["R"] == r), None)
    fork = {"A_vs_C": {"solve_gap": {str(r): None if rate("A_cache", r) is None or rate("C_incontext", r) is None else rate("A_cache", r) - rate("C_incontext", r) for r in [0, 2, 4, 8, 16]}}, "A_vs_B": {"solve_gap": {str(r): None if rate("A_cache", r) is None or rate("B_textual", r) is None else rate("A_cache", r) - rate("B_textual", r) for r in [0, 2, 4, 8, 16]}}, "source": SOURCE, "provenance": "kvcache_fork_verdicts_v1"}
    return solve_by_R, quality, context, tokens, fork


def run(args: argparse.Namespace) -> dict[str, Any]:
    km3 = _read_json(args.km3_real_prompt)
    if km3.get("status") != "KVCACHE_REAL_PROMPT_KM3_PASS":
        payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_PREFLIGHT_FAIL, "reason": "KM3 real prompt gate did not pass", "km3_real_prompt": km3, "source": SOURCE, "provenance": SCHEMA_VERSION}
        _write_json(args.output, payload)
        return payload
    dataset = _make_dataset(args)
    selected, preflight_rows, preflight = _select_entries(dataset, args)
    if len(selected) < args.n_instances:
        payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_PREFLIGHT_FAIL, "reason": "not enough selected graph_color instances", "preflight": preflight, "preflight_rows": preflight_rows, "source": SOURCE, "provenance": SCHEMA_VERSION}
        _write_json(args.output, payload)
        return payload
    all_selected_count = len(selected)
    if args.num_shards > 1:
        selected = [item for item_index, item in enumerate(selected) if item_index % args.num_shards == args.shard_index]
        preflight = preflight | {"all_selected_instances": all_selected_count, "shard_index": args.shard_index, "num_shards": args.num_shards, "shard_selected_instances": len(selected)}
    model, tokenizer = _load_model(args)
    rows = _read_json(args.checkpoint_path) if args.resume else []
    done = {(row["arm"], int(row["R"]), int(row["source_index"])) for row in rows}
    arms = [item.strip() for item in args.arms.split(",") if item.strip()]
    r_values = [int(item) for item in args.r_values.split(",") if item.strip()]
    for selected_item in selected:
        for arm in arms:
            arm_r_values = [0] if arm in {"D_forward", "D_one_shot"} else r_values
            for r in arm_r_values:
                key = (arm, int(r), int(selected_item["source_index"]))
                if key in done:
                    continue
                print(json.dumps({"arm": arm, "R": r, "source_index": selected_item["source_index"]}), flush=True)
                row = _run_one_shot(model, tokenizer, dataset, selected_item, args) if arm == "D_one_shot" else _run_arm(model, tokenizer, dataset, selected_item, arm, r, args)
                rows.append(row)
                done.add(key)
                _write_json(args.checkpoint_path, rows)
    solve_by_R, quality, context, tokens, fork = _summarize(rows)
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_COMPLETE, "generated_at": _now(), "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "preflight": preflight, "km3_real_prompt": {"KM3_PASS": km3.get("overall_pass"), "status": km3.get("status"), "max_abs_logit_delta": km3.get("max_abs_logit_delta")}, "solve_by_R": solve_by_R, "decision_quality": quality, "context_vs_depth": context, "tokens": tokens, "fork_verdicts": fork, "rows": rows, "source": SOURCE, "provenance": SCHEMA_VERSION}
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run graph_color KV-cache checkpoint search arms.")
    parser.add_argument("--output", type=Path, default=Path("results/kvcache_graph_color/search_arms.json"))
    parser.add_argument("--checkpoint-path", type=Path, default=Path("results/kvcache_graph_color/search_arms_checkpoint.json"))
    parser.add_argument("--km3-real-prompt", type=Path, default=Path("results/kvcache_exactness/km3_real_graph_color_prompt_qwen3_fp32.json"))
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scan-limit", type=int, default=500)
    parser.add_argument("--n-instances", type=int, default=30)
    parser.add_argument("--min-backtracks", type=int, default=4)
    parser.add_argument("--node-cap", type=int, default=80)
    parser.add_argument("--num-vertices", type=int, default=14)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--edge-probability", type=float, default=0.4)
    parser.add_argument("--order-mode", default="degree_desc", choices=["degree_desc", "natural"])
    parser.add_argument("--r-values", default="0,2,4,8,16")
    parser.add_argument("--arms", default="A_cache,B_textual,C_incontext,D_forward,D_one_shot")
    parser.add_argument("--call-cap", type=int, default=80)
    parser.add_argument("--max-new-tokens", type=int, default=32)
    parser.add_argument("--one-shot-max-tokens", type=int, default=512)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--num-shards", type=int, default=1)
    run(parser.parse_args())


if __name__ == "__main__":
    main()