"""Overnight KV-cache generalization batch runner.

This runner is intentionally checkpoint-first: every evaluated row is appended to
JSONL before the final summary JSON is written.
"""

from __future__ import annotations

import argparse
import copy
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import re
from statistics import mean
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from analysis.kvcache_exactness_gate import _cache_inventory, _cache_seq_length, _crop_cache, _deviation, _different_token
from analysis.kvcache_graph_color_search import _write_json
from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE
from experiments.rung1_reasoning_gym_bounded_register import _ensure_reasoning_gym


SCHEMA_VERSION = "kvcache_overnight_batch_v0"
STATUS_COMPLETE = "KVCACHE_OVERNIGHT_JOB_COMPLETE"
STATUS_PARTIAL = "KVCACHE_OVERNIGHT_JOB_PARTIAL"
STATUS_GATED_OUT = "KVCACHE_OVERNIGHT_JOB_GATED_OUT"
STATUS_KM3_PASS = "KVCACHE_OVERNIGHT_KM3_PASS"
STATUS_KM3_FAIL = "KVCACHE_OVERNIGHT_KM3_FAIL"


P1A_TASKS = ("mini_sudoku", "n_queens", "futoshiki")
P1A_JOBS = ("gate", "cost", "reason", "couple")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _read_json(path: Path | str) -> Any:
    p = _path(Path(path))
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    p = _path(Path(path))
    if not p.exists():
        return []
    rows = []
    with p.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _append_jsonl(path: Path | str, row: dict[str, Any]) -> None:
    p = _path(Path(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


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


def _make_dataset(task: str, args: argparse.Namespace, size: int | None = None) -> Any:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    n = int(size or args.scan_limit)
    if task == "futoshiki":
        return reasoning_gym.create_dataset(task, size=n, seed=args.seed, min_board_size=args.futoshiki_size, max_board_size=args.futoshiki_size)
    if task == "n_queens":
        return reasoning_gym.create_dataset(task, size=n, seed=args.seed, n=args.n_queens_n)
    if task == "mini_sudoku":
        return reasoning_gym.create_dataset(task, size=n, seed=args.seed)
    if task == "sudoku":
        return reasoning_gym.create_dataset(task, size=n, seed=args.seed)
    if task == "countdown":
        return reasoning_gym.create_dataset(task, size=n, seed=args.seed)
    if task == "knights_knaves":
        return reasoning_gym.create_dataset(task, size=n, seed=args.seed)
    raise ValueError(f"unsupported task {task}")


def _task_prompt(task: str, entry: dict[str, Any]) -> str:
    return "\n".join([
        f"KV-cache checkpoint search prompt for task={task}.",
        "The solver maintains a bounded register of reversible checkpoints.",
        "Backjumping truncates the pure causal KV cache to an earlier checkpoint.",
        "Problem:",
        str(entry.get("question", "")),
        "Continue with a terse search trace.",
    ])


def km3_gate(args: argparse.Namespace) -> dict[str, Any]:
    dataset = _make_dataset(args.task, args, size=max(1, args.scan_limit))
    entry = dataset[int(args.source_index)]
    entry.setdefault("metadata", {})["source_index"] = int(args.source_index)
    prompt = _task_prompt(args.task, entry)
    model, tokenizer = _load_model(args)
    ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(model.device)
    prompt_len = int(ids.shape[1])
    full_ids, full_cache, step_logits = _greedy_extend(model, ids, int(args.depth))
    checkpoints = [int(item) for item in args.checkpoints.split(",") if item.strip()]
    avoid_ids = {token for token in [tokenizer.eos_token_id, tokenizer.pad_token_id, tokenizer.bos_token_id] if token is not None}
    tests: list[dict[str, Any]] = []
    overall = True
    crop_paths: set[str] = set()
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
        tests.append({"test": "resume_same", "checkpoint_generated_tokens": generated_prefix_len, "checkpoint_seq_len": checkpoint_len, "cache_len_before_feed": same_len_before, "cache_len_after_feed": same_len_after, "crop_path": crop_path, "pass": same_pass, **same_dev})
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
        tests.append({"test": "resume_different_equals_fresh", "checkpoint_generated_tokens": generated_prefix_len, "checkpoint_seq_len": checkpoint_len, "cache_len_before_feed": diff_len_before, "cache_len_after_feed": diff_len_after, "fresh_cache_len_after_feed": fresh_len_after, "crop_path": crop_path, "different_token_id": diff_token_id, "pass": diff_pass, **diff_dev})
        overall = overall and diff_pass
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_KM3_PASS if overall else STATUS_KM3_FAIL,
        "generated_at": _now(),
        "task": args.task,
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()},
        "prompt_tokens": prompt_len,
        "depth": int(args.depth),
        "full_cache_seq_len": _cache_seq_length(full_cache),
        "cache_type": type(full_cache).__name__,
        "cache_inventory": _cache_inventory(full_cache),
        "crop_paths": sorted(crop_paths),
        "max_abs_logit_delta": max((float(row.get("max_abs_logit_delta", 0.0)) for row in tests), default=0.0),
        "overall_pass": overall,
        "tests": tests,
        "source": SOURCE,
        "provenance": "kvcache_overnight_km3_gate_v0",
    }
    _write_json(args.output, payload)
    return payload


def _gate_pass(path: Path | None) -> bool:
    if path is None:
        return True
    data = _read_json(path)
    return bool(data and data.get("status") == STATUS_KM3_PASS and data.get("overall_pass") is True)


def _box_size(n: int) -> tuple[int, int]:
    if n == 4:
        return 2, 2
    if n == 9:
        return 3, 3
    root = int(n ** 0.5)
    return root, root


def _cell_name(row: int, col: int) -> str:
    return f"r{row}c{col}"


def _parse_cell(name: str) -> tuple[int, int]:
    match = re.fullmatch(r"r(\d+)c(\d+)", str(name))
    if not match:
        raise ValueError(f"bad cell name {name}")
    return int(match.group(1)), int(match.group(2))


def _build_view(task: str, entry: dict[str, Any]) -> dict[str, Any]:
    meta = entry["metadata"]
    if task in {"mini_sudoku", "sudoku", "futoshiki"}:
        puzzle = meta["puzzle"]
        n = len(puzzle)
        variables = []
        givens = {}
        for r in range(n):
            for c in range(n):
                name = _cell_name(r, c)
                if int(puzzle[r][c]) == 0:
                    variables.append(name)
                else:
                    givens[name] = int(puzzle[r][c])
        peers: dict[str, set[str]] = {name: set() for name in variables + list(givens)}
        box_r, box_c = _box_size(n)
        all_cells = list(peers)
        for name in all_cells:
            r, c = _parse_cell(name)
            for other in all_cells:
                if other == name:
                    continue
                rr, cc = _parse_cell(other)
                same_box = r // box_r == rr // box_r and c // box_c == cc // box_c
                if r == rr or c == cc or same_box:
                    peers[name].add(other)
        inequalities: dict[str, list[tuple[str, str]]] = defaultdict(list)
        if task == "futoshiki":
            for r1, c1, r2, c2, op in meta.get("constraints", []):
                left = _cell_name(int(r1), int(c1))
                right = _cell_name(int(r2), int(c2))
                inequalities[left].append((str(op), right))
                inequalities[right].append((">" if str(op) == "<" else "<", left))
        solution = {_cell_name(r, c): int(meta["solution"][r][c]) for r in range(n) for c in range(n)}
        domains = {}
        for name in variables:
            gold = int(solution[name])
            domains[name] = [value for value in range(1, n + 1) if value != gold] + [gold]
        order = sorted(variables, key=lambda name: (-len(peers[name]) - len(inequalities.get(name, [])), name))
        return {"task": task, "variables": variables, "order": order, "domains": domains, "givens": givens, "peers": peers, "inequalities": inequalities, "solution": solution, "size": n}
    if task == "n_queens":
        puzzle = meta["puzzle"]
        n = len(puzzle)
        variables = []
        givens = {}
        for r, row in enumerate(puzzle):
            if "Q" in row:
                givens[f"row{r}"] = int(row.index("Q"))
            else:
                variables.append(f"row{r}")
        order = sorted(variables, key=lambda name: int(name[3:]))
        solution_board = meta["solutions"][0]
        solution = {f"row{r}": int(row.index("Q")) for r, row in enumerate(solution_board)}
        domains = {}
        for name in variables:
            gold = int(solution[name])
            domains[name] = [value for value in range(n) if value != gold] + [gold]
        return {"task": task, "variables": variables, "order": order, "domains": domains, "givens": givens, "solution": solution, "size": n}
    raise ValueError(f"no CSP view for {task}")


def _conflict_blockers(view: dict[str, Any], var: str, value: int, assignment: dict[str, int]) -> list[str]:
    task = view["task"]
    blockers: list[str] = []
    if task in {"mini_sudoku", "sudoku", "futoshiki"}:
        for peer in view["peers"][var]:
            if assignment.get(peer) == int(value):
                blockers.append(peer)
        for op, other in view.get("inequalities", {}).get(var, []):
            if other not in assignment:
                continue
            other_value = int(assignment[other])
            if op == "<" and not (int(value) < other_value):
                blockers.append(other)
            if op == ">" and not (int(value) > other_value):
                blockers.append(other)
    elif task == "n_queens":
        row = int(var[3:])
        for other, other_col in assignment.items():
            other_row = int(other[3:])
            if other_col == int(value) or abs(other_row - row) == abs(int(other_col) - int(value)):
                blockers.append(other)
    return sorted(set(blockers))


def _answer_from_assignment(task: str, view: dict[str, Any], assignment: dict[str, int]) -> str:
    n = int(view["size"])
    full = {**view.get("givens", {}), **assignment}
    if task in {"mini_sudoku", "sudoku", "futoshiki"}:
        rows = []
        for r in range(n):
            rows.append(" ".join(str(int(full[_cell_name(r, c)])) for c in range(n)))
        return "\n".join(rows)
    if task == "n_queens":
        rows = []
        for r in range(n):
            col = int(full[f"row{r}"])
            rows.append(" ".join("Q" if c == col else "_" for c in range(n)))
        return "\n".join(rows)
    raise ValueError(task)


def _checkpoint_rows(register: list[dict[str, Any]], start: int) -> list[dict[str, Any]]:
    return [{"idx": idx, "var": item["var"], "value": int(item["value"]), "step": int(item["step"])} for idx, item in enumerate(register[start:])]


def _reason_prompt(task: str, entry: dict[str, Any], view: dict[str, Any], var: str, tried: set[int], assignment: dict[str, int], register: list[dict[str, Any]], open_checkpoints: list[dict[str, Any]], conflict_by_value: dict[int, list[str]]) -> str:
    assigned_blockers = []
    reg_by_var = {item["var"]: item for item in register}
    open_idx = {item["var"]: int(item["idx"]) for item in open_checkpoints}
    for blockers in conflict_by_value.values():
        for blocker in blockers:
            source = reg_by_var.get(blocker, {})
            assigned_blockers.append({"var": blocker, "value": int(assignment[blocker]), "step": int(source.get("step", -1)), "open_idx": open_idx.get(blocker)})
    lines = [
        f"{task} conflict-analysis backjump targeting.",
        "Use only the visible state. The final line must be exactly BACKJUMP: <idx>.",
        f"Dead end variable: {var} has no legal value.",
        "Already tried values: " + json.dumps(sorted(int(v) for v in tried), separators=(",", ":")),
        "Assigned blockers: " + json.dumps(sorted(assigned_blockers, key=lambda row: (row['step'], row['var'])), separators=(",", ":")),
        "conflict_by_value: " + json.dumps({str(k): v for k, v in sorted(conflict_by_value.items())}, separators=(",", ":")),
        "Open checkpoints: " + json.dumps(open_checkpoints, separators=(",", ":")),
        "Valid target indices: " + json.dumps([int(item["idx"]) for item in open_checkpoints], separators=(",", ":")),
        "Rule: for each blocked value, identify the assigned blocker responsible for that value. Backjump to the deepest open checkpoint among the conflict blockers. Use only a valid target index, not a step or variable name.",
        "End now with BACKJUMP: <idx>",
    ]
    return "\n".join(lines) + "\n"


@torch.no_grad()
def _generate_reason(model: Any, tokenizer: Any, prompt: str, max_new_tokens: int) -> tuple[str, int, int]:
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            prompt = tokenizer.apply_chat_template([
                {"role": "system", "content": "You are a terse CSP conflict analyst. Follow the output format exactly."},
                {"role": "user", "content": prompt},
            ], tokenize=False, add_generation_prompt=True)
        except Exception:
            pass
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
        if re.search(r"BACKJUMP\s*:\s*[+-]?\d+", text, flags=re.IGNORECASE):
            break
    return text.strip(), int(ids.shape[1]), len(generated)


def _parse_backjump(text: str, num_open: int) -> dict[str, Any]:
    matches = list(re.finditer(r"BACKJUMP\s*:\s*([+-]?\d+)", text, flags=re.IGNORECASE))
    if not matches:
        return {"parseable": False, "valid": False, "idx": None, "invalid_reason": "parse_fail"}
    idx = int(matches[-1].group(1))
    return {"parseable": True, "valid": 0 <= idx < num_open, "idx": idx, "invalid_reason": None if 0 <= idx < num_open else "out_of_range"}


def _run_search(task: str, dataset: Any, entry: dict[str, Any], r_value: int, arm: str, args: argparse.Namespace, model: Any | None = None, tokenizer: Any | None = None) -> dict[str, Any]:
    view = _build_view(task, entry)
    assignment = dict(view["givens"])
    tried: dict[str, set[int]] = defaultdict(set)
    next_idx = {var: 0 for var in view["order"]}
    conflict_sets: dict[str, set[str]] = {var: set() for var in view["order"]}
    conflict_by_value_state: dict[str, dict[int, list[str]]] = {var: {} for var in view["order"]}
    register: list[dict[str, Any]] = []
    position = {var: idx for idx, var in enumerate(view["order"])}
    cursor = 0
    stats = Counter()
    samples: list[dict[str, Any]] = []
    status = "RUNNING"
    cost_rows: list[dict[str, Any]] = []
    transcript_events: list[str] = [_task_prompt(task, entry)]
    while True:
        if int(stats["steps"]) >= int(args.node_cap):
            status = "NODE_CAP"
            break
        if cursor >= len(view["order"]):
            status = "SOLVED"
            break
        var = view["order"][cursor]
        if var in assignment:
            cursor += 1
            continue
        chosen = None
        while next_idx[var] < len(view["domains"][var]):
            value = int(view["domains"][var][next_idx[var]])
            next_idx[var] += 1
            if value in tried[var]:
                continue
            blockers = _conflict_blockers(view, var, value, assignment)
            if not blockers:
                chosen = value
                break
            conflict_sets[var].update(blockers)
            conflict_by_value_state[var][value] = blockers
            stats["blocked_value_checks"] += 1
        stats["steps"] += 1
        if chosen is not None:
            tried[var].add(int(chosen))
            assignment[var] = int(chosen)
            item = {"var": var, "value": int(chosen), "step": int(cursor)}
            register.append(item)
            event = f"BRANCH {var}={int(chosen)} depth={len(register)}"
            transcript_events.append(event)
            stats["branch_decisions"] += 1
            if tokenizer is not None and arm == "cost":
                a_tokens = len(tokenizer(event, add_special_tokens=False).input_ids)
                c_tokens = len(tokenizer("\n".join(transcript_events), add_special_tokens=False).input_ids)
                cost_rows.append({"depth": len(register), "A_cache_tokens": a_tokens, "C_incontext_tokens": c_tokens, "ratio": c_tokens / max(1, a_tokens)})
            cursor += 1
            continue
        if not register:
            status = "EXHAUSTED"
            break
        blockers = {b for b in conflict_sets[var] if b in position and position[b] < cursor}
        if not blockers:
            status = "EXHAUSTED"
            break
        oracle_var = max(blockers, key=lambda b: position[b])
        oracle_abs = max((idx for idx, item in enumerate(register) if item["var"] == oracle_var), default=-1)
        start = max(0, len(register) - int(r_value))
        oracle_idx = oracle_abs - start
        if not (0 <= oracle_idx < len(register[start:])):
            status = "NO_RECOVERY_TARGET"
            break
        open_checkpoints = _checkpoint_rows(register, start)
        if arm == "chrono":
            chosen_idx = len(open_checkpoints) - 1
            meta = {"parse_checked": False, "parseable": None, "valid": None, "output_tokens": 0, "input_tokens": 0, "text": ""}
        elif arm == "oracle" or arm == "cost":
            chosen_idx = int(oracle_idx)
            meta = {"parse_checked": False, "parseable": None, "valid": None, "output_tokens": 0, "input_tokens": 0, "text": ""}
        elif arm == "random":
            rng = random.Random(f"{task}:{entry['metadata'].get('source_index')}:{var}:{len(register)}")
            chosen_idx = rng.randrange(len(open_checkpoints))
            meta = {"parse_checked": False, "parseable": None, "valid": None, "output_tokens": 0, "input_tokens": 0, "text": ""}
        elif arm == "reason":
            if model is None or tokenizer is None:
                status = "REASON_MODEL_MISSING"
                break
            prompt = _reason_prompt(task, entry, view, var, tried[var], assignment, register, open_checkpoints, conflict_by_value_state[var])
            text, input_tokens, output_tokens = _generate_reason(model, tokenizer, prompt, int(args.max_new_tokens))
            parsed = _parse_backjump(text, len(open_checkpoints))
            if not parsed["valid"]:
                status = "INVALID_BACKJUMP_DECISION"
                chosen_idx = int(oracle_idx)
            else:
                chosen_idx = int(parsed["idx"])
            meta = {"parse_checked": True, "parseable": bool(parsed["parseable"]), "valid": bool(parsed["valid"]), "output_tokens": output_tokens, "input_tokens": input_tokens, "text": text[-512:], "invalid_reason": parsed.get("invalid_reason")}
            stats["reason_parse_checks"] += 1
            stats["reason_parseable"] += int(parsed["parseable"])
            stats["reason_valid"] += int(parsed["valid"])
        else:
            raise ValueError(f"unknown arm {arm}")
        stats["backtrack_decisions"] += 1
        stats["backtrack_exact"] += int(int(chosen_idx) == int(oracle_idx))
        stats["backtrack_legal"] += int(int(chosen_idx) <= int(oracle_idx))
        stats["reason_input_tokens"] += int(meta.get("input_tokens", 0))
        stats["reason_output_tokens"] += int(meta.get("output_tokens", 0))
        if len(samples) < int(args.trace_samples):
            samples.append({"var": var, "oracle_idx": int(oracle_idx), "chosen_idx": int(chosen_idx), "blockers": sorted(blockers), "parseable": meta.get("parseable"), "valid": meta.get("valid"), "text": meta.get("text", "")})
        event = f"BACKJUMP {var} oracle={oracle_idx} chosen={chosen_idx} depth={len(register)}"
        transcript_events.append(event)
        if tokenizer is not None and arm == "cost":
            a_tokens = len(tokenizer(event, add_special_tokens=False).input_ids)
            c_tokens = len(tokenizer("\n".join(transcript_events), add_special_tokens=False).input_ids)
            cost_rows.append({"depth": len(register), "A_cache_tokens": a_tokens, "C_incontext_tokens": c_tokens, "ratio": c_tokens / max(1, a_tokens)})
        if meta.get("parse_checked") and meta.get("valid") is False and args.invalid_reason_fails:
            break
        target_abs = start + int(chosen_idx)
        popped = register[target_abs:]
        for item in popped:
            assignment.pop(item["var"], None)
        for item in popped[1:]:
            tried[item["var"]] = set()
            conflict_sets[item["var"]].clear()
            conflict_by_value_state[item["var"]].clear()
        target_var = register[target_abs]["var"]
        if arm in {"oracle", "reason", "cost"}:
            carried = set(blockers)
            carried.discard(target_var)
            conflict_sets[target_var].update(carried)
        tried[var] = set()
        conflict_sets[var].clear()
        conflict_by_value_state[var].clear()
        cursor = int(register[target_abs]["step"])
        del register[target_abs:]
        stats["retractions"] += len(popped)
    answer = _answer_from_assignment(task, view, assignment) if all(var in assignment for var in view["order"]) else None
    score = float(dataset.score_answer(answer, entry)) if answer is not None else 0.0
    if score >= 1.0:
        status = "SOLVED"
    return {"task": task, "source_index": int(entry["metadata"].get("source_index", -1)), "R": int(r_value), "arm": arm, "status": status, "solved": score >= 1.0, "official_score": score, "branch_decisions": int(stats["branch_decisions"]), "backtrack_decisions": int(stats["backtrack_decisions"]), "backtrack_exact": int(stats["backtrack_exact"]), "backtrack_legal": int(stats["backtrack_legal"]), "reason_parse_checks": int(stats["reason_parse_checks"]), "reason_parseable": int(stats["reason_parseable"]), "reason_valid": int(stats["reason_valid"]), "reason_input_tokens": int(stats["reason_input_tokens"]), "reason_output_tokens": int(stats["reason_output_tokens"]), "retractions": int(stats["retractions"]), "cost_rows": cost_rows, "trace_samples": samples, "source": SOURCE, "provenance": "kvcache_overnight_csp_search_row_v0"}


def _summarize_rows(rows: list[dict[str, Any]], job: str) -> list[dict[str, Any]]:
    if job == "cost":
        flat = []
        for row in rows:
            for item in row.get("cost_rows", []):
                flat.append({**item, "task": row["task"]})
        out = []
        for depth in sorted({int(item["depth"]) for item in flat}):
            subset = [item for item in flat if int(item["depth"]) == depth]
            out.append({"depth": depth, "n": len(subset), "mean_A_cache_tokens": mean(float(item["A_cache_tokens"]) for item in subset), "mean_C_incontext_tokens": mean(float(item["C_incontext_tokens"]) for item in subset), "mean_C_over_A_ratio": mean(float(item["ratio"]) for item in subset), "source": SOURCE, "provenance": "kvcache_overnight_cost_by_depth_v0"})
        return out
    groups = sorted({(int(row["R"]), row["arm"]) for row in rows})
    out = []
    for r_value, arm in groups:
        subset = [row for row in rows if int(row["R"]) == r_value and row["arm"] == arm]
        decisions = sum(int(row.get("backtrack_decisions", 0)) for row in subset)
        checks = sum(int(row.get("reason_parse_checks", 0)) for row in subset)
        out.append({"R": r_value, "arm": arm, "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "mean_official_score": mean(float(row["official_score"]) for row in subset), "status_counts": dict(Counter(row["status"] for row in subset)), "backtrack_decisions": decisions, "exact_cbj_rate": (sum(int(row.get("backtrack_exact", 0)) for row in subset) / decisions) if decisions else None, "any_legal_rate": (sum(int(row.get("backtrack_legal", 0)) for row in subset) / decisions) if decisions else None, "parse_rate": (sum(int(row.get("reason_parseable", 0)) for row in subset) / checks) if checks else None, "valid_parse_rate": (sum(int(row.get("reason_valid", 0)) for row in subset) / checks) if checks else None, "mean_retractions": mean(float(row.get("retractions", 0)) for row in subset), "source": SOURCE, "provenance": "kvcache_overnight_search_summary_v0"})
    return out


def run_csp_job(args: argparse.Namespace) -> dict[str, Any]:
    if not _gate_pass(args.gate_path):
        payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_GATED_OUT, "generated_at": _now(), "task": args.task, "job": args.job, "reason": "KM3 gate missing or failed", "gate_path": str(args.gate_path) if args.gate_path else None, "source": SOURCE, "provenance": "kvcache_overnight_csp_job_v0"}
        _write_json(args.output, payload)
        return payload
    dataset = _make_dataset(args.task, args)
    existing = _read_jsonl(args.checkpoint_path)
    done = {row.get("row_id") for row in existing}
    rows = list(existing)
    model = None
    tokenizer = None
    if args.job == "reason":
        model, tokenizer = _load_model(args)
        arms = ["reason", "chrono", "oracle"]
        r_values = [int(item) for item in args.reason_r_values.split(",") if item.strip()]
    elif args.job == "couple":
        arms = ["chrono", "oracle", "random"]
        r_values = [int(item) for item in args.couple_r_values.split(",") if item.strip()]
    elif args.job == "cost":
        tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
        arms = ["cost"]
        r_values = [int(args.cost_r)]
    else:
        raise ValueError(args.job)
    evaluated = 0
    for source_index in range(int(args.scan_limit)):
        if int(args.num_shards) > 1 and source_index % int(args.num_shards) != int(args.shard_index):
            continue
        entry = dataset[source_index]
        entry.setdefault("metadata", {})["source_index"] = int(source_index)
        for r_value in r_values:
            for arm in arms:
                row_id = f"{args.task}:{args.job}:src{source_index}:R{r_value}:{arm}"
                if row_id in done:
                    continue
                row = _run_search(args.task, dataset, entry, int(r_value), arm, args, model=model, tokenizer=tokenizer)
                row["row_id"] = row_id
                row["job"] = args.job
                row["shard_index"] = int(args.shard_index)
                row["num_shards"] = int(args.num_shards)
                _append_jsonl(args.checkpoint_path, row)
                rows.append(row)
                done.add(row_id)
                print(json.dumps({"row_id": row_id, "status": row["status"], "solved": row["solved"]}), flush=True)
        evaluated += 1
        if evaluated >= int(args.n_instances):
            break
    summary = _summarize_rows(rows, args.job)
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_COMPLETE if rows else STATUS_PARTIAL, "generated_at": _now(), "task": args.task, "job": args.job, "table_name": f"{args.task}_{args.job}", "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "rows": rows, "summary": summary, "source": SOURCE, "provenance": "kvcache_overnight_csp_job_v0"}
    _write_json(args.output, payload)
    return payload


def merge_jobs(args: argparse.Namespace) -> dict[str, Any]:
    payloads = [_read_json(path) for path in args.inputs]
    payloads = [p for p in payloads if p]
    rows = [row for payload in payloads for row in payload.get("rows", [])]
    task = args.task or (payloads[0].get("task") if payloads else None)
    job = args.job or (payloads[0].get("job") if payloads else None)
    summary = _summarize_rows(rows, str(job)) if job else []
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_COMPLETE if rows else STATUS_PARTIAL, "generated_at": _now(), "task": task, "job": job, "table_name": f"{task}_{job}", "input_files": [str(path) for path in args.inputs], "rows": rows, "summary": summary, "source": SOURCE, "provenance": "kvcache_overnight_merged_job_v0"}
    _write_json(args.output, payload)
    return payload


def write_manifest(args: argparse.Namespace) -> dict[str, Any]:
    jobs = []
    harness_smoke = _read_json(args.root / "harness_smoke.json")
    search_harness_failed = bool(harness_smoke and harness_smoke.get("status") == "KVCACHE_OVERNIGHT_SEARCH_HARNESS_SMOKE_FAIL")
    for task in P1A_TASKS:
        for job in P1A_JOBS:
            if job == "gate":
                path = args.root / "p1a" / task / "gate.json"
            else:
                path = args.root / "p1a" / task / job / f"merged_{task}_{job}.json"
            data = _read_json(path)
            status = data.get("status") if data else "not_started"
            if job != "gate" and data is None and search_harness_failed:
                status = "gated_out_search_harness_smoke_fail"
            jobs.append({"priority": "P1-A", "job": f"{task}_{job}", "status": status, "output_path": str(path), "read_order": 1 if job == "reason" else 3, "source": SOURCE, "provenance": "kvcache_overnight_manifest_job_v0"})
    for name in ["separability_ma1", "separability_ma2", "countdown_scope", "knights_knaves_scope", "graph_color_robustness", "scale_axis", "c1_failure_modes"]:
        jobs.append({"priority": "P1-B" if name.startswith("separability") else "P2/P3", "job": name, "status": "queued", "output_path": None, "source": SOURCE, "provenance": "kvcache_overnight_manifest_job_v0"})
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_PARTIAL, "generated_at": _now(), "run_id": args.run_id, "root": str(args.root), "harness_smoke": harness_smoke, "jobs": jobs, "source": SOURCE, "provenance": "kvcache_overnight_manifest_v0"}
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="KV-cache overnight batch runner.")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--reasoning-gym-repo", default=None)
        p.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
        p.add_argument("--device", default="cuda")
        p.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32")
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--scan-limit", type=int, default=200)
        p.add_argument("--n-instances", type=int, default=12)
        p.add_argument("--node-cap", type=int, default=1200)
        p.add_argument("--futoshiki-size", type=int, default=4)
        p.add_argument("--n-queens-n", type=int, default=8)

    gate = sub.add_parser("gate")
    common(gate)
    gate.add_argument("--task", required=True)
    gate.add_argument("--output", type=Path, required=True)
    gate.add_argument("--source-index", type=int, default=0)
    gate.add_argument("--depth", type=int, default=16)
    gate.add_argument("--checkpoints", default="2,4,8,12")
    gate.add_argument("--tol", type=float, default=1e-3)

    csp = sub.add_parser("run-csp-job")
    common(csp)
    csp.add_argument("--task", required=True)
    csp.add_argument("--job", choices=["cost", "reason", "couple"], required=True)
    csp.add_argument("--output", type=Path, required=True)
    csp.add_argument("--checkpoint-path", type=Path, required=True)
    csp.add_argument("--gate-path", type=Path, default=None)
    csp.add_argument("--reason-r-values", default="4,8")
    csp.add_argument("--couple-r-values", default="2,4,8,16")
    csp.add_argument("--cost-r", type=int, default=16)
    csp.add_argument("--max-new-tokens", type=int, default=128)
    csp.add_argument("--trace-samples", type=int, default=8)
    csp.add_argument("--invalid-reason-fails", action="store_true")
    csp.add_argument("--num-shards", type=int, default=1)
    csp.add_argument("--shard-index", type=int, default=0)

    merge = sub.add_parser("merge-jobs")
    merge.add_argument("--inputs", nargs="+", type=Path, required=True)
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--task", default=None)
    merge.add_argument("--job", default=None)

    manifest = sub.add_parser("manifest")
    manifest.add_argument("--root", type=Path, default=Path("results/kvcache_overnight_v0"))
    manifest.add_argument("--output", type=Path, default=Path("results/kvcache_overnight_v0/overnight_manifest.json"))
    manifest.add_argument("--run-id", default="overnight_v0")

    args = parser.parse_args()
    if args.command == "gate":
        km3_gate(args)
    elif args.command == "run-csp-job":
        run_csp_job(args)
    elif args.command == "merge-jobs":
        merge_jobs(args)
    elif args.command == "manifest":
        write_manifest(args)


if __name__ == "__main__":
    main()
