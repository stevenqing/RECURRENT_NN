"""Run graph_color KV-cache checkpoint search arms under direct Transformers."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import signal
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


SCHEMA_VERSION = "kvcache_graph_color_search_v2"
STATUS_COMPLETE = "KVCACHE_GRAPH_COLOR_SEARCH_COMPLETE"
STATUS_PREFLIGHT_FAIL = "KVCACHE_GRAPH_COLOR_SEARCH_PREFLIGHT_FAIL"
ORACLE_BRANCH_SUFFIX = "_oracle_branch"
ORACLE_SEARCH_SUFFIX = "_oracle_search"


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


def _base_arm(arm: str) -> str:
    for suffix in (ORACLE_SEARCH_SUFFIX, ORACLE_BRANCH_SUFFIX):
        if arm.endswith(suffix):
            return arm[: -len(suffix)]
    return arm


def _branch_policy(arm: str) -> str:
    if arm.endswith(ORACLE_SEARCH_SUFFIX):
        return "oracle_search"
    return "oracle" if arm.endswith(ORACLE_BRANCH_SUFFIX) else "model"


def _uses_oracle_branch(arm: str) -> bool:
    return _branch_policy(arm) in {"oracle", "oracle_search"}


def _uses_oracle_search(arm: str) -> bool:
    return _branch_policy(arm) == "oracle_search"


def _difficulty_bin(args: argparse.Namespace) -> str:
    if args.difficulty_bin_label:
        return args.difficulty_bin_label
    edge = str(args.edge_probability).replace(".", "p")
    return f"v{args.num_vertices}_p{edge}_c{args.num_colors}"


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


def _is_cache_arm(arm: str) -> bool:
    return _base_arm(arm) == "A_cache"


def _is_incontext_arm(arm: str) -> bool:
    return _base_arm(arm) == "C_incontext"


def _select_entries(dataset: Any, args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    preflight: list[dict[str, Any]] = []
    for index in range(args.scan_limit):
        entry = dataset[index]
        entry.setdefault("metadata", {})["source_index"] = index
        if int(getattr(args, "preflight_timeout_seconds", 0)) > 0:
            def _timeout(_signum: int, _frame: Any) -> None:
                raise TimeoutError("preflight_timeout")
            old_handler = signal.signal(signal.SIGALRM, _timeout)
            signal.alarm(int(args.preflight_timeout_seconds))
            try:
                trace = _clean_trace(entry, args.order_mode, args.node_cap, dataset)
            except TimeoutError:
                trace = {"status": "PREFLIGHT_TIMEOUT", "solved": False, "official_score": 0.0, "steps": args.node_cap, "total_retractions": 0, "max_register_len": 0}
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
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


def _invalid_meta(reason: str, parseable: bool, raw_value: Any, fallback_type: str | None, fail: bool) -> dict[str, Any]:
    return {
        "parseable": parseable,
        "valid": False,
        "fallback": fallback_type is not None,
        "fallback_type": fallback_type,
        "fail": fail,
        "invalid_reason": reason,
        "raw_value": raw_value,
    }


def _choose_color(parsed: dict[str, Any] | None, domain: list[int], invalid_mode: str) -> tuple[int | None, dict[str, Any]]:
    raw_value: Any = None
    if parsed is None or "color" not in parsed:
        if invalid_mode == "fail":
            return None, _invalid_meta("parse_fail", False, raw_value, None, True)
        return int(domain[0]), _invalid_meta("parse_fail", False, raw_value, "first_legal", False)
    raw_value = parsed.get("color")
    try:
        color = int(raw_value)
    except Exception:
        if invalid_mode == "fail":
            return None, _invalid_meta("invalid_type", True, raw_value, None, True)
        return int(domain[0]), _invalid_meta("invalid_type", True, raw_value, "first_legal", False)
    if color not in domain:
        if invalid_mode == "fail":
            return None, _invalid_meta("out_of_domain", True, raw_value, None, True)
        return int(domain[0]), _invalid_meta("out_of_domain", True, raw_value, "first_legal", False)
    return color, {"parseable": True, "valid": True, "fallback": False, "fallback_type": None, "fail": False, "invalid_reason": None, "raw_value": raw_value}


def _choose_backtrack(parsed: dict[str, Any] | None, view_len: int, invalid_mode: str) -> tuple[int | None, dict[str, Any]]:
    raw_value: Any = None
    fallback = max(0, view_len - 1)
    if parsed is None or "entry_index" not in parsed:
        if invalid_mode == "fail":
            return None, _invalid_meta("parse_fail", False, raw_value, None, True)
        return fallback, _invalid_meta("parse_fail", False, raw_value, "chronological_latest", False)
    raw_value = parsed.get("entry_index")
    try:
        index = int(raw_value)
    except Exception:
        if invalid_mode == "fail":
            return None, _invalid_meta("invalid_type", True, raw_value, None, True)
        return fallback, _invalid_meta("invalid_type", True, raw_value, "chronological_latest", False)
    if not 0 <= index < view_len:
        if invalid_mode == "fail":
            return None, _invalid_meta("out_of_range", True, raw_value, None, True)
        return fallback, _invalid_meta("out_of_range", True, raw_value, "chronological_latest", False)
    return index, {"parseable": True, "valid": True, "fallback": False, "fallback_type": None, "fail": False, "invalid_reason": None, "raw_value": raw_value}


def _record_model_decision(stats: Counter, kind: str, meta: dict[str, Any], correct: bool) -> None:
    stats["decision_calls"] += 1
    stats[f"{kind}_calls"] += 1
    stats["parseable"] += int(bool(meta["parseable"]))
    stats["valid"] += int(bool(meta["valid"]))
    stats["fallback"] += int(bool(meta["fallback"]))
    stats[f"{kind}_fallback"] += int(bool(meta["fallback"]))
    stats["parse_fail"] += int(not bool(meta["parseable"]))
    stats[f"{kind}_parse_fail"] += int(not bool(meta["parseable"]))
    stats["invalid"] += int(bool(meta["parseable"]) and not bool(meta["valid"]))
    stats[f"{kind}_invalid"] += int(bool(meta["parseable"]) and not bool(meta["valid"]))
    stats[f"{kind}_correct"] += int(correct)


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
    puzzle = selected["entry"]["metadata"]["puzzle"]
    trace = selected.get("trace", {})
    branch_calls = int(stats["branch_calls"])
    backtrack_calls = int(stats["backtrack_calls"])
    decision_calls = int(stats["decision_calls"])
    branch_decisions = int(stats["branch_decisions"])
    return {
        "source_index": int(selected["source_index"]),
        "arm": arm,
        "base_arm": _base_arm(arm),
        "branch_policy": _branch_policy(arm),
        "difficulty_bin": selected.get("difficulty_bin"),
        "num_vertices": len(puzzle["vertices"]),
        "num_edges": len(puzzle["edges"]),
        "num_colors": int(puzzle["num_colors"]),
        "edge_probability": selected.get("edge_probability"),
        "trace_steps": int(trace.get("steps", 0)),
        "trace_total_retractions": int(trace.get("total_retractions", 0)),
        "trace_max_register_len": int(trace.get("max_register_len", 0)),
        "R": int(r),
        "status": "SOLVED" if score >= 1.0 else status,
        "solved": score >= 1.0,
        "official_score": score,
        "decision_calls": decision_calls,
        "oracle_search_decision_points": int(stats["oracle_search_decision_points"]),
        "branch_calls": branch_calls,
        "backtrack_calls": backtrack_calls,
        "branch_decisions": branch_decisions,
        "oracle_branch_decisions": int(stats["oracle_branch_decisions"]),
        "branch_correct_decisions": int(stats["branch_correct"]),
        "backtrack_correct_decisions": int(stats["backtrack_correct"]),
        "parseable_decisions": int(stats["parseable"]),
        "valid_decisions": int(stats["valid"]),
        "fallback_decisions": int(stats["fallback"]),
        "branch_fallback_decisions": int(stats["branch_fallback"]),
        "backtrack_fallback_decisions": int(stats["backtrack_fallback"]),
        "parse_fail_decisions": int(stats["parse_fail"]),
        "invalid_decisions": int(stats["invalid"]),
        "branch_accuracy_vs_oracle": (int(stats["branch_correct"]) / branch_calls) if branch_calls else None,
        "backtrack_accuracy_vs_oracle": (int(stats["backtrack_correct"]) / backtrack_calls) if backtrack_calls else None,
        "parseable_rate": (int(stats["parseable"]) / decision_calls) if decision_calls else None,
        "valid_decision_rate": (int(stats["valid"]) / decision_calls) if decision_calls else None,
        "fallback_rate": (int(stats["fallback"]) / decision_calls) if decision_calls else None,
        "oracle_branch_rate": (int(stats["oracle_branch_decisions"]) / branch_decisions) if branch_decisions else None,
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
    base_arm = _base_arm(arm)
    branch_policy = _branch_policy(arm)
    oracle_search = _uses_oracle_search(arm)
    view = _graph_color_view(entry, args.order_mode)
    position = {vertex: i for i, vertex in enumerate(view["order"])}
    assignment: dict[int, int] = {}
    tried: dict[int, set[int]] = defaultdict(set)
    register: list[dict[str, Any]] = []
    transcript = f"Graph_color search arm={arm}.\nProblem:\n{entry.get('question','')}\n"
    cache = None
    stats = Counter()
    if base_arm == "A_cache":
        _, cache, used = _feed(model, tokenizer, transcript, None)
        stats["input_tokens"] += used
        stats["total_tokens"] += used
    cursor = 0
    context_rows: list[dict[str, Any]] = []
    while True:
        if int(stats["decision_calls"]) + int(stats["oracle_search_decision_points"]) >= args.call_cap:
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
            checkpoint = _cache_seq_length(cache) if base_arm == "A_cache" else None
            if _uses_oracle_branch(arm):
                color = oracle
                stats["branch_decisions"] += 1
                stats["oracle_branch_decisions"] += 1
                stats["oracle_search_decision_points"] += int(oracle_search)
                event = f"\nORACLE_BRANCH vertex={vertex} color={color} domain={domain} tried={sorted(tried[vertex])}\n"
                if base_arm == "A_cache":
                    context_tokens = _cache_seq_length(cache)
                    _, cache, used = _feed(model, tokenizer, event, cache)
                    stats["input_tokens"] += used
                    stats["total_tokens"] += used
                elif base_arm == "C_incontext":
                    context_tokens = len(tokenizer(transcript + "\nNEXT_BRANCH\n" + prompt, add_special_tokens=False).input_ids)
                    if oracle_search:
                        stats["input_tokens"] += context_tokens
                        stats["total_tokens"] += context_tokens
                else:
                    context_tokens = len(tokenizer(prompt, add_special_tokens=False).input_ids) if oracle_search else 0
                    if oracle_search:
                        stats["input_tokens"] += context_tokens
                        stats["total_tokens"] += context_tokens
                action = "oracle_search_branch" if oracle_search else "oracle_branch"
                context_rows.append({"depth": len(register) + 1, "context_tokens": context_tokens, "action": action, "model_decision": False})
            elif base_arm == "A_cache":
                context_tokens = _cache_seq_length(cache)
                text, cache, usage = _generate_json(model, tokenizer, "\nNEXT_BRANCH\n" + prompt, cache, args.max_new_tokens)
                parsed = _parse_json(text)
                color, meta = _choose_color(parsed, domain, args.invalid_branch_mode)
                stats["branch_decisions"] += 1
                _record_model_decision(stats, "branch", meta, bool(meta["valid"] and color == oracle))
                stats["input_tokens"] += usage["input_tokens"]
                stats["output_tokens"] += usage["output_tokens"]
                stats["total_tokens"] += usage["total_tokens"]
                context_rows.append({"depth": len(register) + 1, "context_tokens": context_tokens, "action": "branch", "model_decision": True, "parseable": meta["parseable"], "valid": meta["valid"], "fallback": meta["fallback"], "fallback_type": meta["fallback_type"], "invalid_reason": meta["invalid_reason"]})
                if color is None:
                    return _finish(dataset, selected, arm, r, "INVALID_BRANCH_DECISION", assignment, stats, context_rows)
            elif base_arm == "C_incontext":
                full_prompt = transcript + "\nNEXT_BRANCH\n" + prompt
                context_tokens = len(tokenizer(full_prompt, add_special_tokens=False).input_ids)
                text, _, usage = _generate_json(model, tokenizer, full_prompt, None, args.max_new_tokens)
            else:
                context_tokens = len(tokenizer(prompt, add_special_tokens=False).input_ids)
                text, _, usage = _generate_json(model, tokenizer, prompt, None, args.max_new_tokens)
            if branch_policy == "model" and base_arm != "A_cache":
                parsed = _parse_json(text)
                color, meta = _choose_color(parsed, domain, args.invalid_branch_mode)
                stats["branch_decisions"] += 1
                _record_model_decision(stats, "branch", meta, bool(meta["valid"] and color == oracle))
                stats["input_tokens"] += usage["input_tokens"]
                stats["output_tokens"] += usage["output_tokens"]
                stats["total_tokens"] += usage["total_tokens"]
                context_rows.append({"depth": len(register) + 1, "context_tokens": context_tokens, "action": "branch", "model_decision": True, "parseable": meta["parseable"], "valid": meta["valid"], "fallback": meta["fallback"], "fallback_type": meta["fallback_type"], "invalid_reason": meta["invalid_reason"]})
                if color is None:
                    return _finish(dataset, selected, arm, r, "INVALID_BRANCH_DECISION", assignment, stats, context_rows)
            tried[vertex].add(color)
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor, "cache_pos": checkpoint})
            transcript += f"BRANCH vertex={vertex} color={color} domain={domain} tried={sorted(tried[vertex])}\n"
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
        if oracle_search:
            chosen = oracle_view
            stats["oracle_search_decision_points"] += 1
            if base_arm == "A_cache":
                context_tokens = _cache_seq_length(cache)
            elif base_arm == "C_incontext":
                full_prompt = transcript + f"DEAD_END vertex={vertex} blockers={sorted(nogood)}\n" + prompt
                context_tokens = len(tokenizer(full_prompt, add_special_tokens=False).input_ids)
                stats["input_tokens"] += context_tokens
                stats["total_tokens"] += context_tokens
            else:
                context_tokens = len(tokenizer(prompt, add_special_tokens=False).input_ids)
                stats["input_tokens"] += context_tokens
                stats["total_tokens"] += context_tokens
            context_rows.append({"depth": len(register), "context_tokens": context_tokens, "action": "oracle_search_backtrack", "model_decision": False, "oracle_entry_index": oracle_view})
        else:
            if base_arm == "A_cache":
                context_tokens = _cache_seq_length(cache)
                text, cache, usage = _generate_json(model, tokenizer, "\nDEAD_END\n" + prompt, cache, args.max_new_tokens)
            elif base_arm == "C_incontext":
                full_prompt = transcript + f"DEAD_END vertex={vertex} blockers={sorted(nogood)}\n" + prompt
                context_tokens = len(tokenizer(full_prompt, add_special_tokens=False).input_ids)
                text, _, usage = _generate_json(model, tokenizer, full_prompt, None, args.max_new_tokens)
            else:
                context_tokens = len(tokenizer(prompt, add_special_tokens=False).input_ids)
                text, _, usage = _generate_json(model, tokenizer, prompt, None, args.max_new_tokens)
            parsed = _parse_json(text)
            chosen, meta = _choose_backtrack(parsed, len(bounded), args.invalid_backtrack_mode)
            _record_model_decision(stats, "backtrack", meta, bool(meta["valid"] and chosen == oracle_view))
            stats["input_tokens"] += usage["input_tokens"]
            stats["output_tokens"] += usage["output_tokens"]
            stats["total_tokens"] += usage["total_tokens"]
            context_rows.append({"depth": len(register), "context_tokens": context_tokens, "action": "backtrack", "model_decision": True, "parseable": meta["parseable"], "valid": meta["valid"], "fallback": meta["fallback"], "fallback_type": meta["fallback_type"], "invalid_reason": meta["invalid_reason"]})
            if chosen is None:
                return _finish(dataset, selected, arm, r, "INVALID_BACKTRACK_DECISION", assignment, stats, context_rows)
        target_abs = start + chosen
        if base_arm == "A_cache":
            checkpoint = register[target_abs].get("cache_pos")
            if checkpoint is None:
                return _finish(dataset, selected, arm, r, "CACHE_CHECKPOINT_MISSING", assignment, stats, context_rows)
            cache, _ = _crop_cache(cache, int(checkpoint))
        cursor, popped = _rollback(assignment, tried, register, vertex, target_abs)
        stats["retractions"] += popped
        transcript += f"DEAD_END vertex={vertex} chosen={chosen} oracle={oracle_view} popped={popped}\n"


def _run_one_shot(model: Any, tokenizer: Any, dataset: Any, selected: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    prompt = selected["entry"].get("question", "") + "\nReturn exactly one JSON object mapping every vertex string to an integer color.\n"
    text, _, usage = _generate_json(model, tokenizer, prompt, None, args.one_shot_max_tokens)
    try:
        score = float(dataset.score_answer(text, selected["entry"]))
    except Exception:
        score = 0.0
    puzzle = selected["entry"]["metadata"]["puzzle"]
    return {"source_index": int(selected["source_index"]), "arm": "D_one_shot", "base_arm": "D_one_shot", "branch_policy": "none", "difficulty_bin": selected.get("difficulty_bin"), "num_vertices": len(puzzle["vertices"]), "num_edges": len(puzzle["edges"]), "num_colors": int(puzzle["num_colors"]), "edge_probability": selected.get("edge_probability"), "R": 0, "status": "SOLVED" if score >= 1.0 else "SCORE_FAIL", "solved": score >= 1.0, "official_score": score, "decision_calls": 1, "branch_calls": 0, "backtrack_calls": 0, "branch_decisions": 0, "oracle_branch_decisions": 0, "branch_correct_decisions": 0, "backtrack_correct_decisions": 0, "parseable_decisions": 0, "valid_decisions": 0, "fallback_decisions": 0, "branch_fallback_decisions": 0, "backtrack_fallback_decisions": 0, "parse_fail_decisions": 0, "invalid_decisions": 0, "branch_accuracy_vs_oracle": None, "backtrack_accuracy_vs_oracle": None, "parseable_rate": None, "valid_decision_rate": None, "fallback_rate": 0.0, "oracle_branch_rate": None, "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"], "total_tokens": usage["total_tokens"], "context_rows": [{"depth": 0, "context_tokens": usage["input_tokens"], "action": "one_shot", "model_decision": True}], "source": SOURCE, "provenance": "kvcache_graph_color_one_shot_v2"}


def _summarize(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    def row_bin(row: dict[str, Any]) -> str:
        return str(row.get("difficulty_bin") or "unlabeled")

    def row_vertices(row: dict[str, Any]) -> int:
        return int(row.get("num_vertices") or 0)

    def row_edge(row: dict[str, Any]) -> float:
        return float(row.get("edge_probability") or 0.0)

    def count_rate(num: int, den: int) -> float | None:
        return (num / den) if den else None

    def solved_rate(subset: list[dict[str, Any]]) -> float:
        return mean(float(row["solved"]) for row in subset)

    solve_by_R: list[dict[str, Any]] = []
    quality: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []
    context: list[dict[str, Any]] = []
    tokens: list[dict[str, Any]] = []
    groups = sorted({(row_bin(row), row_vertices(row), row_edge(row), row["arm"], int(row["R"])) for row in rows})
    for difficulty_bin, num_vertices, edge_probability, arm, r in groups:
        subset = [row for row in rows if row_bin(row) == difficulty_bin and row_vertices(row) == num_vertices and row_edge(row) == edge_probability and row["arm"] == arm and int(row["R"]) == r]
        base_arm_value = str(subset[0].get("base_arm") or _base_arm(arm))
        branch_policy_value = str(subset[0].get("branch_policy") or _branch_policy(arm))
        decision_calls = sum(int(row.get("decision_calls", 0)) for row in subset)
        branch_calls = sum(int(row.get("branch_calls", 0)) for row in subset)
        backtrack_calls = sum(int(row.get("backtrack_calls", 0)) for row in subset)
        branch_decisions = sum(int(row.get("branch_decisions", row.get("branch_calls", 0))) for row in subset)
        solve_by_R.append({"difficulty_bin": difficulty_bin, "num_vertices": num_vertices, "edge_probability": edge_probability, "arm": arm, "base_arm": base_arm_value, "branch_policy": branch_policy_value, "R": r, "n": len(subset), "solve_rate": solved_rate(subset), "mean_official_score": mean(float(row["official_score"]) for row in subset), "status_counts": dict(Counter(row["status"] for row in subset)), "source": SOURCE, "provenance": "kvcache_solve_by_R_v2"})
        quality.append({"difficulty_bin": difficulty_bin, "num_vertices": num_vertices, "edge_probability": edge_probability, "arm": arm, "base_arm": base_arm_value, "branch_policy": branch_policy_value, "R": r, "n": len(subset), "decision_calls": decision_calls, "branch_accuracy_vs_oracle": count_rate(sum(int(row.get("branch_correct_decisions", 0)) for row in subset), branch_calls), "backtrack_accuracy_vs_oracle": count_rate(sum(int(row.get("backtrack_correct_decisions", 0)) for row in subset), backtrack_calls), "oracle_branch_rate": count_rate(sum(int(row.get("oracle_branch_decisions", 0)) for row in subset), branch_decisions), "parseable_rate": count_rate(sum(int(row.get("parseable_decisions", 0)) for row in subset), decision_calls), "valid_decision_rate": count_rate(sum(int(row.get("valid_decisions", 0)) for row in subset), decision_calls), "source": SOURCE, "provenance": "kvcache_decision_quality_v2"})
        fallback.append({"difficulty_bin": difficulty_bin, "num_vertices": num_vertices, "edge_probability": edge_probability, "arm": arm, "base_arm": base_arm_value, "branch_policy": branch_policy_value, "R": r, "n": len(subset), "decision_calls": decision_calls, "fallback_decisions": sum(int(row.get("fallback_decisions", 0)) for row in subset), "fallback_rate": count_rate(sum(int(row.get("fallback_decisions", 0)) for row in subset), decision_calls), "branch_fallback_rate": count_rate(sum(int(row.get("branch_fallback_decisions", 0)) for row in subset), branch_calls), "backtrack_fallback_rate": count_rate(sum(int(row.get("backtrack_fallback_decisions", 0)) for row in subset), backtrack_calls), "parse_fail_rate": count_rate(sum(int(row.get("parse_fail_decisions", 0)) for row in subset), decision_calls), "invalid_rate": count_rate(sum(int(row.get("invalid_decisions", 0)) for row in subset), decision_calls), "source": SOURCE, "provenance": "kvcache_fallback_rate_v1"})
        tokens.append({"difficulty_bin": difficulty_bin, "num_vertices": num_vertices, "edge_probability": edge_probability, "arm": arm, "base_arm": base_arm_value, "branch_policy": branch_policy_value, "R": r, "n": len(subset), "mean_total_tokens": mean(int(row["total_tokens"]) for row in subset), "mean_input_tokens": mean(int(row.get("input_tokens", 0)) for row in subset), "mean_output_tokens": mean(int(row.get("output_tokens", 0)) for row in subset), "source": SOURCE, "provenance": "kvcache_tokens_v2"})
        buckets: dict[tuple[int, str], list[int]] = defaultdict(list)
        for row in subset:
            for item in row.get("context_rows", []):
                buckets[(int(item.get("depth", 0)), str(item.get("action", "unknown")))].append(int(item.get("context_tokens", 0)))
        for (depth, action), vals in sorted(buckets.items()):
            context.append({"difficulty_bin": difficulty_bin, "num_vertices": num_vertices, "edge_probability": edge_probability, "arm": arm, "base_arm": base_arm_value, "branch_policy": branch_policy_value, "R": r, "depth": depth, "action": action, "n": len(vals), "mean_context_tokens": mean(vals), "max_context_tokens": max(vals), "source": SOURCE, "provenance": "kvcache_context_vs_depth_v2"})

    a_vs_c_by_depth: list[dict[str, Any]] = []
    pair_groups = sorted({(row_bin(row), row_vertices(row), row_edge(row), int(row["R"]), str(row.get("branch_policy") or _branch_policy(row["arm"]))) for row in rows if str(row.get("base_arm") or _base_arm(row["arm"])) in {"A_cache", "C_incontext"}})
    for difficulty_bin, num_vertices, edge_probability, r, branch_policy in pair_groups:
        a_rows = [row for row in rows if row_bin(row) == difficulty_bin and row_vertices(row) == num_vertices and row_edge(row) == edge_probability and int(row["R"]) == r and str(row.get("branch_policy") or _branch_policy(row["arm"])) == branch_policy and str(row.get("base_arm") or _base_arm(row["arm"])) == "A_cache"]
        c_rows = [row for row in rows if row_bin(row) == difficulty_bin and row_vertices(row) == num_vertices and row_edge(row) == edge_probability and int(row["R"]) == r and str(row.get("branch_policy") or _branch_policy(row["arm"])) == branch_policy and str(row.get("base_arm") or _base_arm(row["arm"])) == "C_incontext"]
        if not a_rows or not c_rows:
            continue
        a_tokens = mean(int(row["total_tokens"]) for row in a_rows)
        c_tokens = mean(int(row["total_tokens"]) for row in c_rows)
        a_fallback_den = sum(int(row.get("decision_calls", 0)) for row in a_rows)
        c_fallback_den = sum(int(row.get("decision_calls", 0)) for row in c_rows)
        a_vs_c_by_depth.append({"difficulty_bin": difficulty_bin, "num_vertices": num_vertices, "edge_probability": edge_probability, "branch_policy": branch_policy, "R": r, "A_n": len(a_rows), "C_n": len(c_rows), "A_solve_rate": solved_rate(a_rows), "C_solve_rate": solved_rate(c_rows), "A_minus_C_solve_gap": solved_rate(a_rows) - solved_rate(c_rows), "A_mean_total_tokens": a_tokens, "C_mean_total_tokens": c_tokens, "C_over_A_token_ratio": (c_tokens / a_tokens) if a_tokens else None, "A_fallback_rate": count_rate(sum(int(row.get("fallback_decisions", 0)) for row in a_rows), a_fallback_den), "C_fallback_rate": count_rate(sum(int(row.get("fallback_decisions", 0)) for row in c_rows), c_fallback_den), "source": SOURCE, "provenance": "kvcache_A_vs_C_by_depth_v1"})

    positive_gaps = [row["A_minus_C_solve_gap"] for row in a_vs_c_by_depth if row["A_minus_C_solve_gap"] is not None]
    fork = {"A_vs_C_by_depth_rows": len(a_vs_c_by_depth), "max_A_minus_C_solve_gap": max(positive_gaps) if positive_gaps else None, "min_A_minus_C_solve_gap": min(positive_gaps) if positive_gaps else None, "source": SOURCE, "provenance": "kvcache_fork_verdicts_v2"}
    return solve_by_R, quality, fallback, context, a_vs_c_by_depth, tokens, fork


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
    difficulty_bin = _difficulty_bin(args)
    for selected_item in selected:
        selected_item["difficulty_bin"] = difficulty_bin
        selected_item["edge_probability"] = float(args.edge_probability)
    preflight = preflight | {"difficulty_bin": difficulty_bin, "num_vertices": args.num_vertices, "num_colors": args.num_colors, "edge_probability": args.edge_probability, "invalid_branch_mode": args.invalid_branch_mode, "invalid_backtrack_mode": args.invalid_backtrack_mode}
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
    solve_by_R, quality, fallback_rate, context, a_vs_c_by_depth, tokens, fork = _summarize(rows)
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_COMPLETE, "generated_at": _now(), "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "preflight": preflight, "km3_real_prompt": {"KM3_PASS": km3.get("overall_pass"), "status": km3.get("status"), "max_abs_logit_delta": km3.get("max_abs_logit_delta")}, "solve_by_R": solve_by_R, "decision_quality": quality, "fallback_rate": fallback_rate, "context_vs_depth": context, "A_vs_C_by_depth": a_vs_c_by_depth, "tokens": tokens, "fork_verdicts": fork, "rows": rows, "source": SOURCE, "provenance": SCHEMA_VERSION}
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
    parser.add_argument("--preflight-timeout-seconds", type=int, default=0)
    parser.add_argument("--num-vertices", type=int, default=14)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--edge-probability", type=float, default=0.4)
    parser.add_argument("--difficulty-bin-label", default="")
    parser.add_argument("--order-mode", default="degree_desc", choices=["degree_desc", "natural"])
    parser.add_argument("--r-values", default="0,2,4,8,16")
    parser.add_argument("--arms", default="A_cache,B_textual,C_incontext,A_cache_oracle_branch,B_textual_oracle_branch,C_incontext_oracle_branch,D_forward,D_one_shot")
    parser.add_argument("--invalid-branch-mode", choices=["first_legal", "fail"], default="first_legal")
    parser.add_argument("--invalid-decision-mode", dest="invalid_branch_mode", choices=["first_legal", "fail"], default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    parser.add_argument("--invalid-backtrack-mode", choices=["chronological_latest", "fail"], default="chronological_latest")
    parser.add_argument("--fallback-backtrack-mode", dest="invalid_backtrack_mode", choices=["chronological_latest", "fail"], default=argparse.SUPPRESS, help=argparse.SUPPRESS)
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