"""LFS-style no-train baseline under the shared matched-budget counter.

Port basis: NathanHerr/LLM-First-Search, commit
3025bdaa3add6f41388c1d5a6d354522489d312e. The original repo uses a tree of
PathNode states, LLM child-value evaluation, and an LLM explore/continue decision.
This adapter maps that control loop onto the common CSP environment used here.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import heapq
import json
from pathlib import Path
from statistics import mean
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from analysis.kvcache_gate2_csp_solver import _legal_values, _make_dataset as _make_csp_dataset, parse_instance, render_answer
from analysis.kvcache_graph_color_search import _make_dataset as _make_graph_dataset, _write_json
from experiments.rung1_distributed_graph_coloring import SOURCE
from experiments.rung1_reasoning_gym_bounded_register import _current_domain as _gc_current_domain, _graph_color_view, _official_score as _gc_official_score


SCHEMA_VERSION = "kvcache_lfs_baseline_v0"
STATUS_COMPLETE = "KVCACHE_LFS_BASELINE_COMPLETE"
STATUS_MERGED = "KVCACHE_LFS_BASELINE_MERGED"
LFS_REPO = "NathanHerr/LLM-First-Search"
LFS_URL = "https://github.com/NathanHerr/LLM-First-Search"
LFS_COMMIT = "3025bdaa3add6f41388c1d5a6d354522489d312e"


@dataclass(order=True)
class FrontierItem:
    priority: float
    tie: int
    state: Any = field(compare=False)


@dataclass(frozen=True)
class CSPState:
    assignment: dict[int, int]
    depth: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _budget_anchors(text: str) -> dict[str, int]:
    anchors = {}
    for item in text.split(","):
        if not item.strip():
            continue
        key, value = item.split(":", 1)
        anchors[key.strip()] = int(float(value.strip()))
    return anchors


def _task_args(task: str, args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        reasoning_gym_repo=args.reasoning_gym_repo,
        task=task,
        seed=args.seed,
        scan_limit=args.scan_limit,
        n_instances=args.n_instances,
        futoshiki_size=args.futoshiki_size,
        futoshiki_difficulty=args.futoshiki_difficulty,
        n_queens_n=8,
        n_queens_min_remove=1,
        n_queens_max_remove=7,
        output=Path("unused.json"),
        model=args.model,
        dtype=args.dtype,
        device=args.device,
        num_vertices=args.graph_num_vertices,
        num_colors=args.graph_num_colors,
        edge_probability=args.graph_edge_probability,
        difficulty_bin_label=args.graph_difficulty_bin_label,
        order_mode="degree_desc",
    )


def _make_dataset(task: str, args: argparse.Namespace) -> Any:
    if task == "graph_color":
        return _make_graph_dataset(_task_args(task, args))
    return _make_csp_dataset(task, _task_args(task, args))


@torch.no_grad()
def _generate_json(model: Any, tokenizer: Any, prompt: str, max_new_tokens: int) -> tuple[str, int, int]:
    ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(model.device)
    out = model.generate(
        ids,
        do_sample=False,
        max_new_tokens=int(max_new_tokens),
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
        use_cache=True,
    )
    generated = out[:, ids.shape[1]:]
    text = tokenizer.decode(generated[0], skip_special_tokens=True).strip()
    return text, int(ids.shape[1]), int(generated.shape[1])


def _extract_json(text: str) -> Any:
    decoder = json.JSONDecoder()
    parsed = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        parsed.append(obj)
    if not parsed:
        raise ValueError("no json object")
    return parsed[-1]


def _state_text(task: str, env: dict[str, Any], state: CSPState) -> str:
    if task == "graph_color":
        assigned = {str(env["order"][idx]): int(value) for idx, value in sorted(state.assignment.items())}
        return json.dumps({"assigned": assigned, "depth": state.depth}, sort_keys=True)
    inst = env["inst"]
    assigned = {inst.variables[idx]: int(value) for idx, value in sorted(state.assignment.items())}
    return json.dumps({"assigned": assigned, "depth": state.depth}, sort_keys=True)


def _legal_actions(task: str, env: dict[str, Any], state: CSPState) -> tuple[int | None, list[int]]:
    if task == "graph_color":
        if state.depth >= len(env["order"]):
            return None, []
        vertex = int(env["order"][state.depth])
        assignment_by_vertex = {int(env["order"][idx]): int(value) for idx, value in state.assignment.items()}
        tried = {int(vertex): set() for vertex in env["order"]}
        return vertex, [int(item) for item in _gc_current_domain(env["view"], vertex, assignment_by_vertex, tried)]
    inst = env["inst"]
    if state.depth >= len(inst.variables):
        return None, []
    legal, _ = _legal_values(inst, state.depth, state.assignment, set())
    return state.depth, [int(item) for item in legal]


def _transition(state: CSPState, value: int) -> CSPState:
    assignment = dict(state.assignment)
    assignment[state.depth] = int(value)
    return CSPState(assignment=assignment, depth=state.depth + 1)


def _is_goal(task: str, env: dict[str, Any], state: CSPState) -> bool:
    if task == "graph_color":
        return state.depth >= len(env["order"])
    return state.depth >= len(env["inst"].variables)


def _score_state(task: str, env: dict[str, Any], state: CSPState) -> float:
    if not _is_goal(task, env, state):
        return 0.0
    if task == "graph_color":
        assignment_by_vertex = {str(env["order"][idx]): int(value) for idx, value in state.assignment.items()}
        return float(_gc_official_score(env["dataset"], env["entry"], {int(k): v for k, v in assignment_by_vertex.items()}))
    answer = render_answer(env["inst"], decision_assignment=state.assignment)
    return float(env["dataset"].score_answer(answer, env["entry"]))


def _make_env(task: str, dataset: Any, entry: dict[str, Any]) -> dict[str, Any]:
    if task == "graph_color":
        view = _graph_color_view(entry, "degree_desc")
        return {"task": task, "dataset": dataset, "entry": entry, "view": view, "order": [int(item) for item in view["order"]]}
    return {"task": task, "dataset": dataset, "entry": entry, "inst": parse_instance(task, entry)}


def _eval_prompt(task: str, env: dict[str, Any], state: CSPState, actions: list[int]) -> str:
    return "\n".join([
        "LFS child-value evaluation for a CSP search state.",
        "Score each legal action from 0.0 to 1.0 by how promising it is for solving.",
        "Return exactly one JSON object mapping action strings to numeric scores. No prose.",
        "Task: " + task,
        "State: " + _state_text(task, env, state),
        "Legal actions: " + json.dumps([int(item) for item in actions]),
    ])


def _explore_prompt(task: str, env: dict[str, Any], state: CSPState, frontier_size: int) -> str:
    return "\n".join([
        "LFS explore decision for CSP search.",
        "Return exactly {\"explore\": true} to pop the best frontier state, or {\"explore\": false} to continue the current path. No prose.",
        "Task: " + task,
        "Current state: " + _state_text(task, env, state),
        f"Frontier size: {int(frontier_size)}",
    ])


def _query_json(model: Any, tokenizer: Any, prompt: str, budget: int, tokens_used: int, max_new_tokens: int) -> tuple[Any | None, int, str]:
    input_tokens = len(tokenizer(prompt, add_special_tokens=False).input_ids)
    remaining = int(budget) - int(tokens_used)
    if remaining <= input_tokens + 1:
        return None, 0, "BUDGET_EXHAUSTED"
    max_new = min(int(max_new_tokens), max(1, remaining - input_tokens))
    text, in_tok, out_tok = _generate_json(model, tokenizer, prompt, max_new)
    used = int(in_tok) + int(out_tok)
    try:
        parsed = _extract_json(text)
    except Exception:
        return None, used, "PARSE_FAIL"
    return parsed, used, "OK"


def _run_lfs_instance(model: Any, tokenizer: Any, dataset: Any, task: str, entry: dict[str, Any], source_index: int, budget: int, args: argparse.Namespace) -> dict[str, Any]:
    env = _make_env(task, dataset, entry)
    root = CSPState(assignment={}, depth=0)
    frontier: list[FrontierItem] = []
    current = root
    tie = 0
    tokens_used = 0
    expansions = 0
    parse_fails = 0
    status = "BUDGET_EXHAUSTED"
    best_score = 0.0
    while expansions < int(args.max_expansions):
        score = _score_state(task, env, current)
        best_score = max(best_score, score)
        if score >= 0.99:
            status = "SOLVED"
            break
        var, actions = _legal_actions(task, env, current)
        local_children: list[tuple[float, CSPState]] = []
        if actions:
            parsed, used, qstatus = _query_json(model, tokenizer, _eval_prompt(task, env, current, actions), int(budget), tokens_used, int(args.max_new_tokens))
            if qstatus == "BUDGET_EXHAUSTED":
                status = "BUDGET_EXHAUSTED"
                break
            tokens_used += used
            values = {}
            if isinstance(parsed, dict):
                for action in actions:
                    try:
                        values[int(action)] = float(parsed.get(str(action), parsed.get(int(action), 0.0)))
                    except Exception:
                        values[int(action)] = 0.0
            else:
                parse_fails += 1
                values = {int(action): 0.0 for action in actions}
            for action in actions:
                tie += 1
                child = _transition(current, int(action))
                value = float(values.get(int(action), 0.0))
                local_children.append((value, child))
                heapq.heappush(frontier, FrontierItem(priority=-value, tie=tie, state=child))
            expansions += 1
        if not frontier:
            status = "NO_FRONTIER"
            break
        parsed, used, qstatus = _query_json(model, tokenizer, _explore_prompt(task, env, current, len(frontier)), int(budget), tokens_used, int(args.max_new_tokens))
        if qstatus == "BUDGET_EXHAUSTED":
            status = "BUDGET_EXHAUSTED"
            break
        tokens_used += used
        explore = True
        if isinstance(parsed, dict) and "explore" in parsed:
            explore = bool(parsed.get("explore"))
        else:
            parse_fails += 1
        if explore:
            current = heapq.heappop(frontier).state
        else:
            current = max(local_children, key=lambda item: item[0])[1] if local_children else heapq.heappop(frontier).state
    else:
        status = "EXPANSION_CAP"
    best_score = max(best_score, _score_state(task, env, current))
    return {
        "method": "LFS_repo_port_smoke",
        "task": task,
        "source_index": int(source_index),
        "budget_B": int(budget),
        "solved": bool(best_score >= 0.99),
        "official_score": float(best_score),
        "tokens_used": int(tokens_used),
        "depth_reached": int(current.depth),
        "expansions": int(expansions),
        "frontier_size": int(len(frontier)),
        "parse_fails": int(parse_fails),
        "status": "SOLVED" if best_score >= 0.99 else status,
        "repo": LFS_REPO,
        "repo_url": LFS_URL,
        "repo_commit": LFS_COMMIT,
        "source": SOURCE,
        "provenance": "kvcache_lfs_budget_run_v0",
    }


def _summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for task, budget in sorted({(row["task"], int(row["budget_B"])) for row in rows}):
        subset = [row for row in rows if row["task"] == task and int(row["budget_B"]) == budget]
        solves = sum(int(row["solved"]) for row in subset)
        summary.append({"method": "LFS_repo_port_smoke", "task": task, "budget_B": budget, "n": len(subset), "solve_count": solves, "solve_rate": solves / len(subset) if subset else 0.0, "mean_tokens_used": mean(float(row["tokens_used"]) for row in subset), "mean_depth_reached": mean(float(row["depth_reached"]) for row in subset), "mean_expansions": mean(float(row["expansions"]) for row in subset), "status_counts": dict(Counter(row["status"] for row in subset)), "source": SOURCE, "provenance": "kvcache_lfs_budget_summary_v0"})
    return summary


def run(args: argparse.Namespace) -> dict[str, Any]:
    model, tokenizer = _load_model(args)
    anchors = _budget_anchors(args.budget_anchors)
    rows = []
    for task in [item.strip() for item in args.tasks.split(",") if item.strip()]:
        dataset = _make_dataset(task, args)
        budget = int(anchors[task])
        for source_index in range(int(args.n_instances)):
            entry = dataset[source_index]
            entry.setdefault("metadata", {})["source_index"] = source_index
            print(json.dumps({"task": task, "source_index": source_index, "budget_B": budget}), flush=True)
            rows.append(_run_lfs_instance(model, tokenizer, dataset, task, entry, source_index, budget, args))
            _write_json(args.checkpoint_path, {"rows": rows})
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_COMPLETE, "generated_at": _now(), "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "summary": _summarize(rows), "rows": rows, "source": SOURCE, "provenance": "kvcache_lfs_baseline_v0"}
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LFS repo-port smoke under matched budgets.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint-path", type=Path, required=True)
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32")
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scan-limit", type=int, default=120)
    parser.add_argument("--n-instances", type=int, default=2)
    parser.add_argument("--tasks", default="sudoku,graph_color")
    parser.add_argument("--budget-anchors", default="sudoku:28070,futoshiki:3206226,graph_color:32895")
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--max-expansions", type=int, default=24)
    parser.add_argument("--futoshiki-size", type=int, default=7)
    parser.add_argument("--futoshiki-difficulty", type=int, default=3)
    parser.add_argument("--graph-num-vertices", type=int, default=16)
    parser.add_argument("--graph-num-colors", type=int, default=3)
    parser.add_argument("--graph-edge-probability", type=float, default=0.4)
    parser.add_argument("--graph-difficulty-bin-label", default="v16_p04")
    args = parser.parse_args()
    payload = run(args)
    print(json.dumps({"path": str(args.output), "status": payload["status"], "rows": len(payload["rows"])}, sort_keys=True))


if __name__ == "__main__":
    main()
