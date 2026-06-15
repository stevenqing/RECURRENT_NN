"""ToT/RAP no-train baseline smokes under the shared matched-budget counter.

Port basis: maitrix-org/llm-reasoners, commit
f94e5ac2cb9788c3d7d7dbf2173884ed4088e4b2. The upstream examples expose ToT as a
WorldModel + SearchConfig + Beam/DFS search and RAP as WorldModel + SearchConfig
+ MCTS. This adapter maps those control patterns onto the local CSP environment.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import glob
from math import log, sqrt
from pathlib import Path
from statistics import mean
import sys
from typing import Any
import json

import torch

from analysis.kvcache_graph_color_search import _write_json
from analysis.kvcache_lfs_baseline import CSPState, _extract_json, _legal_actions, _load_model, _make_dataset, _make_env, _now, _query_json, _score_state, _state_text, _transition
from experiments.rung1_distributed_graph_coloring import SOURCE


SCHEMA_VERSION = "kvcache_tot_rap_baselines_v0"
STATUS_COMPLETE = "KVCACHE_TOT_RAP_BASELINES_COMPLETE"
LLM_REASONERS_REPO = "maitrix-org/llm-reasoners"
LLM_REASONERS_URL = "https://github.com/maitrix-org/llm-reasoners"
LLM_REASONERS_COMMIT = "f94e5ac2cb9788c3d7d7dbf2173884ed4088e4b2"


@dataclass
class BeamNode:
    state: Any
    reward: float
    action: int | None = None
    depth: int = 0


@dataclass
class RapNode:
    state: Any
    parent: "RapNode | None" = None
    action: int | None = None
    reward: float = 0.0
    children: list["RapNode"] = field(default_factory=list)
    visits: int = 0
    value_sum: float = 0.0

    @property
    def depth(self) -> int:
        return 0 if self.parent is None else self.parent.depth + 1

    @property
    def q(self) -> float:
        return self.value_sum / self.visits if self.visits else self.reward


def _budget_anchors(text: str) -> dict[str, int]:
    anchors = {}
    for item in text.split(","):
        if not item.strip():
            continue
        key, value = item.split(":", 1)
        anchors[key.strip()] = int(float(value.strip()))
    return anchors


def _budget_grid(anchor: int, scales: str) -> list[int]:
    return sorted({max(1, int(round(float(scale.strip()) * int(anchor)))) for scale in scales.split(",") if scale.strip()})


def _wilson(successes: int, n: int, z: float = 1.959963984540054) -> dict[str, float | None]:
    if n <= 0:
        return {"rate": None, "ci_low": None, "ci_high": None}
    phat = successes / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return {"rate": phat, "ci_low": max(0.0, center - half), "ci_high": min(1.0, center + half)}


def _task_depth(task: str, env: dict[str, Any]) -> int:
    if task == "graph_color":
        return len(env["order"])
    return len(env["inst"].variables)


def _max_depth(args: argparse.Namespace, task: str, env: dict[str, Any]) -> int:
    return int(args.max_depth) if int(args.max_depth) > 0 else _task_depth(task, env)


def _action_prompt(method: str, task: str, env: dict[str, Any], state: Any, legal_actions: list[int], limit: int) -> str:
    return "\n".join([
        f"{method} action proposal for a CSP search state.",
        "Choose promising next actions only from the legal action list.",
        "Return exactly one JSON object {\"actions\": [integers]} with no prose.",
        "Task: " + task,
        "State: " + _state_text(task, env, state),
        "Legal actions: " + json.dumps([int(item) for item in legal_actions]),
        f"Maximum actions: {int(limit)}",
    ])


def _value_prompt(method: str, task: str, env: dict[str, Any], state: Any, action: int, child_state: Any) -> str:
    return "\n".join([
        f"{method} state evaluation for CSP search.",
        "Score the child state from 0.0 to 1.0 by how promising it is for reaching a valid complete solution.",
        "Return exactly one JSON object {\"score\": number} with no prose.",
        "Task: " + task,
        "Parent state: " + _state_text(task, env, state),
        f"Action: {int(action)}",
        "Child state: " + _state_text(task, env, child_state),
    ])


def _parse_action_list(parsed: Any, legal_actions: list[int], limit: int) -> list[int]:
    raw = None
    if isinstance(parsed, dict):
        raw = parsed.get("actions", parsed.get("action", parsed.get("values")))
    elif isinstance(parsed, list):
        raw = parsed
    if isinstance(raw, (str, int, float)):
        raw = [raw]
    actions = []
    legal = {int(item) for item in legal_actions}
    if isinstance(raw, list):
        for item in raw:
            try:
                action = int(item)
            except Exception:
                continue
            if action in legal and action not in actions:
                actions.append(action)
            if len(actions) >= int(limit):
                break
    return actions


def _parse_score(parsed: Any) -> float | None:
    if not isinstance(parsed, dict):
        return None
    for key in ["score", "value", "reward"]:
        if key not in parsed:
            continue
        try:
            return max(0.0, min(1.0, float(parsed[key])))
        except Exception:
            return None
    return None


def _propose_actions(model: Any, tokenizer: Any, method: str, task: str, env: dict[str, Any], state: Any, budget: int, tokens_used: int, args: argparse.Namespace) -> tuple[list[int], int, int, str]:
    _, legal_actions = _legal_actions(task, env, state)
    if not legal_actions:
        return [], 0, 0, "NO_LEGAL_ACTIONS"
    parsed, used, qstatus = _query_json(model, tokenizer, _action_prompt(method, task, env, state, legal_actions, int(args.n_actions)), budget, tokens_used, int(args.max_new_tokens))
    if qstatus == "BUDGET_EXHAUSTED":
        return [], used, 0, qstatus
    actions = _parse_action_list(parsed, legal_actions, int(args.n_actions))
    parse_fails = 0
    if not actions:
        parse_fails = 1
        actions = [int(item) for item in legal_actions[: int(args.n_actions)]]
    return actions, used, parse_fails, qstatus


def _score_child(model: Any, tokenizer: Any, method: str, task: str, env: dict[str, Any], state: Any, action: int, child_state: Any, budget: int, tokens_used: int, args: argparse.Namespace) -> tuple[float, int, int, str]:
    parsed, used, qstatus = _query_json(model, tokenizer, _value_prompt(method, task, env, state, int(action), child_state), budget, tokens_used, int(args.max_new_tokens))
    if qstatus == "BUDGET_EXHAUSTED":
        return 0.0, used, 0, qstatus
    score = _parse_score(parsed)
    if score is None:
        return 0.0, used, 1, qstatus
    return score, used, 0, qstatus


@torch.no_grad()
def _generate_json_batch(model: Any, tokenizer: Any, prompts: list[str], max_new_tokens: int) -> list[tuple[str, int, int]]:
    if not prompts:
        return []
    previous_padding_side = getattr(tokenizer, "padding_side", "right")
    tokenizer.padding_side = "left"
    try:
        encoded = tokenizer(prompts, return_tensors="pt", padding=True, add_special_tokens=False)
        input_lengths = encoded.attention_mask.sum(dim=1).tolist()
        encoded = {key: value.to(model.device) for key, value in encoded.items()}
        output = model.generate(
            **encoded,
            do_sample=False,
            max_new_tokens=int(max_new_tokens),
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
            use_cache=True,
        )
        generated = output[:, encoded["input_ids"].shape[1]:]
        generated_tokens = int(generated.shape[1])
        rows = []
        for index in range(generated.shape[0]):
            text = tokenizer.decode(generated[index], skip_special_tokens=True).strip()
            rows.append((text, int(input_lengths[index]), generated_tokens))
        return rows
    finally:
        tokenizer.padding_side = previous_padding_side


def _query_json_batch(model: Any, tokenizer: Any, prompts: list[str], budget: int, tokens_used: int, max_new_tokens: int) -> list[tuple[Any | None, int, str]]:
    if not prompts:
        return []
    prompt_lengths = [len(tokenizer(prompt, add_special_tokens=False).input_ids) for prompt in prompts]
    selected_count = 0
    planned_tokens = int(tokens_used)
    batch_max_new = None
    for input_tokens in prompt_lengths:
        remaining = int(budget) - planned_tokens
        if remaining <= input_tokens + 1:
            break
        candidate_max_new = min(int(max_new_tokens), max(1, remaining - input_tokens))
        if batch_max_new is None:
            batch_max_new = candidate_max_new
        if planned_tokens + input_tokens + int(batch_max_new) > int(budget):
            break
        selected_count += 1
        planned_tokens += input_tokens + int(batch_max_new)
    if selected_count <= 0 or batch_max_new is None:
        return [(None, 0, "BUDGET_EXHAUSTED") for _ in prompts]
    generated = _generate_json_batch(model, tokenizer, prompts[:selected_count], int(batch_max_new))
    results: list[tuple[Any | None, int, str]] = []
    for text, input_tokens, output_tokens in generated:
        used = int(input_tokens) + int(output_tokens)
        try:
            results.append((_extract_json(text), used, "OK"))
        except Exception:
            results.append((None, used, "PARSE_FAIL"))
    results.extend((None, 0, "BUDGET_EXHAUSTED") for _ in prompts[selected_count:])
    return results


def _score_children_batch(model: Any, tokenizer: Any, method: str, task: str, env: dict[str, Any], state: Any, children: list[tuple[int, CSPState]], budget: int, tokens_used: int, args: argparse.Namespace) -> tuple[list[tuple[int, CSPState, float]], int, int, str]:
    scored: list[tuple[int, CSPState, float]] = []
    total_used = 0
    parse_fails = 0
    value_batch_size = max(1, int(args.value_batch_size))
    for start in range(0, len(children), value_batch_size):
        chunk = children[start:start + value_batch_size]
        prompts = [_value_prompt(method, task, env, state, int(action), child_state) for action, child_state in chunk]
        results = _query_json_batch(model, tokenizer, prompts, int(budget), int(tokens_used) + int(total_used), int(args.max_new_tokens))
        for (parsed, used, qstatus), (action, child_state) in zip(results, chunk):
            if qstatus == "BUDGET_EXHAUSTED":
                return scored, total_used, parse_fails, "BUDGET_EXHAUSTED"
            total_used += int(used)
            score = _parse_score(parsed)
            if score is None:
                parse_fails += 1
                score = 0.0
            scored.append((int(action), child_state, float(score)))
    return scored, total_used, parse_fails, "OK"


def _run_tot_instance(model: Any, tokenizer: Any, dataset: Any, task: str, entry: dict[str, Any], source_index: int, budget: int, args: argparse.Namespace) -> dict[str, Any]:
    env = _make_env(task, dataset, entry)
    depth_limit = _max_depth(args, task, env)
    root = BeamNode(state=CSPState(assignment={}, depth=0), reward=0.0)
    frontier = [root]
    tokens_used = 0
    expansions = 0
    parse_fails = 0
    best_score = 0.0
    max_depth_reached = 0
    status = "BUDGET_EXHAUSTED"
    while frontier:
        next_frontier: list[BeamNode] = []
        for node in frontier[: int(args.beam_size)]:
            if int(args.max_expansions) > 0 and expansions >= int(args.max_expansions):
                status = "EXPANSION_CAP"
                break
            best_score = max(best_score, _score_state(task, env, node.state))
            max_depth_reached = max(max_depth_reached, int(node.depth))
            if best_score >= 0.99:
                status = "SOLVED"
                frontier = []
                break
            if node.depth >= depth_limit:
                continue
            actions, used, fails, qstatus = _propose_actions(model, tokenizer, "ToT", task, env, node.state, int(budget), tokens_used, args)
            tokens_used += used
            parse_fails += fails
            if qstatus == "BUDGET_EXHAUSTED":
                status = "BUDGET_EXHAUSTED"
                frontier = []
                break
            children = [(int(action), _transition(node.state, int(action))) for action in actions]
            scored_children, used, fails, qstatus = _score_children_batch(model, tokenizer, "ToT", task, env, node.state, children, int(budget), tokens_used, args)
            tokens_used += used
            parse_fails += fails
            if qstatus == "BUDGET_EXHAUSTED":
                status = "BUDGET_EXHAUSTED"
            for action, child_state, reward in scored_children:
                child = BeamNode(state=child_state, reward=float(reward), action=int(action), depth=node.depth + 1)
                best_score = max(best_score, _score_state(task, env, child_state))
                max_depth_reached = max(max_depth_reached, int(child.depth))
                next_frontier.append(child)
            expansions += 1
            if status == "BUDGET_EXHAUSTED":
                break
        if status in {"SOLVED", "BUDGET_EXHAUSTED", "EXPANSION_CAP"}:
            break
        if not next_frontier:
            status = "NO_FRONTIER"
            break
        frontier = sorted(next_frontier, key=lambda item: item.reward, reverse=True)[: int(args.beam_size)]
    best_score = max([best_score, *[_score_state(task, env, node.state) for node in frontier]]) if frontier else best_score
    if best_score >= 0.99:
        status = "SOLVED"
    return _row("ToT_Beam_repo_port_budget_exhaustive", task, source_index, budget, best_score, tokens_used, max_depth_reached, expansions, parse_fails, status)


def _uct_child(node: RapNode, w_exp: float) -> RapNode:
    parent_visits = max(1, node.visits)
    return max(node.children, key=lambda child: child.q + float(w_exp) * sqrt(log(parent_visits + 1.0) / max(1, child.visits)))


def _backprop(node: RapNode, value: float) -> None:
    current: RapNode | None = node
    while current is not None:
        current.visits += 1
        current.value_sum += float(value)
        current = current.parent


def _run_rap_instance(model: Any, tokenizer: Any, dataset: Any, task: str, entry: dict[str, Any], source_index: int, budget: int, args: argparse.Namespace) -> dict[str, Any]:
    env = _make_env(task, dataset, entry)
    depth_limit = _max_depth(args, task, env)
    root = RapNode(state=CSPState(assignment={}, depth=0))
    tokens_used = 0
    expansions = 0
    parse_fails = 0
    best_score = 0.0
    max_depth_reached = 0
    status = "BUDGET_EXHAUSTED"
    iterations = 0
    while True:
        if int(args.mcts_iters) > 0 and iterations >= int(args.mcts_iters):
            status = "MCTS_ITER_CAP"
            break
        if int(args.max_expansions) > 0 and expansions >= int(args.max_expansions):
            status = "EXPANSION_CAP"
            break
        tokens_before_iter = tokens_used
        iterations += 1
        node = root
        while node.children and node.depth < depth_limit:
            node = _uct_child(node, float(args.uct_weight))
        best_score = max(best_score, _score_state(task, env, node.state))
        max_depth_reached = max(max_depth_reached, int(node.depth))
        if best_score >= 0.99:
            status = "SOLVED"
            break
        if node.depth < depth_limit:
            actions, used, fails, qstatus = _propose_actions(model, tokenizer, "RAP", task, env, node.state, int(budget), tokens_used, args)
            tokens_used += used
            parse_fails += fails
            if qstatus == "BUDGET_EXHAUSTED":
                status = "BUDGET_EXHAUSTED"
                break
            children = [(int(action), _transition(node.state, int(action))) for action in actions]
            scored_children, used, fails, qstatus = _score_children_batch(model, tokenizer, "RAP", task, env, node.state, children, int(budget), tokens_used, args)
            tokens_used += used
            parse_fails += fails
            if qstatus == "BUDGET_EXHAUSTED":
                status = "BUDGET_EXHAUSTED"
            for action, child_state, reward in scored_children:
                child = RapNode(state=child_state, parent=node, action=int(action), reward=float(reward))
                node.children.append(child)
                best_score = max(best_score, _score_state(task, env, child_state))
                max_depth_reached = max(max_depth_reached, int(child.depth))
            expansions += 1
            if status == "BUDGET_EXHAUSTED":
                break
        if not node.children:
            _backprop(node, 0.0)
            if int(args.mcts_iters) <= 0 and tokens_used == tokens_before_iter:
                status = "NO_FRONTIER"
                break
            continue
        rollout = max(node.children, key=lambda child: child.reward)
        reward_sum = rollout.reward
        rollout_state = rollout.state
        rollout_depth = rollout.depth
        rollout_steps = depth_limit if int(args.rollout_depth) <= 0 else int(args.rollout_depth)
        for _rollout_step in range(rollout_steps):
            if rollout_depth >= depth_limit:
                break
            actions, used, fails, qstatus = _propose_actions(model, tokenizer, "RAP", task, env, rollout_state, int(budget), tokens_used, args)
            tokens_used += used
            parse_fails += fails
            if qstatus == "BUDGET_EXHAUSTED" or not actions:
                status = "BUDGET_EXHAUSTED" if qstatus == "BUDGET_EXHAUSTED" else status
                break
            rollout_children = [(int(action), _transition(rollout_state, int(action))) for action in actions[: max(1, int(args.rollout_branching))]]
            scored_children, used, fails, qstatus = _score_children_batch(model, tokenizer, "RAP", task, env, rollout_state, rollout_children, int(budget), tokens_used, args)
            tokens_used += used
            parse_fails += fails
            if qstatus == "BUDGET_EXHAUSTED":
                status = "BUDGET_EXHAUSTED"
            scored = [(reward, child_state) for _, child_state, reward in scored_children]
            if status == "BUDGET_EXHAUSTED" or not scored:
                break
            reward, rollout_state = max(scored, key=lambda item: item[0])
            reward_sum += reward
            rollout_depth += 1
            max_depth_reached = max(max_depth_reached, int(rollout_depth))
            best_score = max(best_score, _score_state(task, env, rollout_state))
        _backprop(rollout, reward_sum)
        if best_score >= 0.99:
            status = "SOLVED"
            break
        if status == "BUDGET_EXHAUSTED":
            break
        if int(args.mcts_iters) <= 0 and tokens_used == tokens_before_iter:
            status = "NO_FRONTIER"
            break
    if best_score >= 0.99:
        status = "SOLVED"
    return _row("RAP_MCTS_repo_port_budget_exhaustive", task, source_index, budget, best_score, tokens_used, max_depth_reached, expansions, parse_fails, status)


def _row(method: str, task: str, source_index: int, budget: int, best_score: float, tokens_used: int, depth_reached: int, expansions: int, parse_fails: int, status: str) -> dict[str, Any]:
    return {
        "method": method,
        "task": task,
        "source_index": int(source_index),
        "budget_B": int(budget),
        "solved": bool(best_score >= 0.99),
        "official_score": float(best_score),
        "tokens_used": int(tokens_used),
        "depth_reached": int(depth_reached),
        "expansions": int(expansions),
        "parse_fails": int(parse_fails),
        "status": "SOLVED" if best_score >= 0.99 else status,
        "repo": LLM_REASONERS_REPO,
        "repo_url": LLM_REASONERS_URL,
        "repo_commit": LLM_REASONERS_COMMIT,
        "source": SOURCE,
        "provenance": "kvcache_tot_rap_budget_run_v0",
    }


def _summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    keys = sorted({(row["method"], row["task"], int(row["budget_B"])) for row in rows})
    for method, task, budget in keys:
        subset = [row for row in rows if row["method"] == method and row["task"] == task and int(row["budget_B"]) == budget]
        solves = sum(int(row["solved"]) for row in subset)
        ci = _wilson(solves, len(subset))
        summary.append({
            "method": method,
            "task": task,
            "budget_B": budget,
            "n": len(subset),
            "solve_count": solves,
            "solve_rate": ci["rate"],
            "solve_ci_low": ci["ci_low"],
            "solve_ci_high": ci["ci_high"],
            "mean_tokens_used": mean(float(row["tokens_used"]) for row in subset),
            "mean_depth_reached": mean(float(row["depth_reached"]) for row in subset),
            "mean_expansions": mean(float(row["expansions"]) for row in subset),
            "status_counts": dict(Counter(row["status"] for row in subset)),
            "source": SOURCE,
            "provenance": "kvcache_tot_rap_budget_summary_v0",
        })
    return summary


def run_shard(args: argparse.Namespace) -> dict[str, Any]:
    model, tokenizer = _load_model(args)
    anchors = _budget_anchors(args.budget_anchors)
    rows = []
    methods = [item.strip() for item in args.methods.split(",") if item.strip()]
    tasks = [item.strip() for item in args.tasks.split(",") if item.strip()]
    checkpoint_rows = []
    if args.resume and args.checkpoint_path.exists():
        checkpoint = json.loads(args.checkpoint_path.read_text(encoding="utf-8"))
        checkpoint_rows = list(checkpoint.get("rows", []))
    done = {(row["method"], row["task"], int(row["source_index"]), int(row["budget_B"])) for row in checkpoint_rows}
    rows = list(checkpoint_rows)
    task_counter = 0
    for task in tasks:
        dataset = _make_dataset(task, args)
        budgets = _budget_grid(anchors[task], args.budget_scales)
        for source_index in range(int(args.n_instances)):
            entry = dataset[source_index]
            entry.setdefault("metadata", {})["source_index"] = source_index
            for budget in budgets:
                for method in methods:
                    current_index = task_counter
                    task_counter += 1
                    if current_index % int(args.num_shards) != int(args.shard_index):
                        continue
                    if method == "tot":
                        method_name = "ToT_Beam_repo_port_budget_exhaustive"
                    elif method == "rap":
                        method_name = "RAP_MCTS_repo_port_budget_exhaustive"
                    else:
                        raise ValueError(f"unknown method: {method}")
                    key = (method_name, task, int(source_index), int(budget))
                    if key in done:
                        continue
                    print(json.dumps({"method": method, "task": task, "source_index": source_index, "budget_B": int(budget), "shard": int(args.shard_index)}), flush=True)
                    if method == "tot":
                        row = _run_tot_instance(model, tokenizer, dataset, task, entry, source_index, int(budget), args)
                    else:
                        row = _run_rap_instance(model, tokenizer, dataset, task, entry, source_index, int(budget), args)
                    row["shard_index"] = int(args.shard_index)
                    row["num_shards"] = int(args.num_shards)
                    rows.append(row)
                    done.add(key)
                    _write_json(args.checkpoint_path, {"rows": rows})
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()},
        "rows": rows,
        "source": SOURCE,
        "provenance": "kvcache_tot_rap_baselines_shard_v0",
    }
    _write_json(args.output, payload)
    return payload


def merge(args: argparse.Namespace) -> dict[str, Any]:
    row_by_key: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    inputs = sorted(glob.glob(args.inputs))
    for path in inputs:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        for row in payload.get("rows", []):
            row_by_key[(row["method"], row["task"], int(row["source_index"]), int(row["budget_B"]))] = row
    rows = [row_by_key[key] for key in sorted(row_by_key)]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "input_files": inputs,
        "summary": _summarize(rows),
        "rows": rows,
        "source": SOURCE,
        "provenance": "kvcache_tot_rap_baselines_merged_v0",
    }
    _write_json(args.output, payload)
    return payload


def run(args: argparse.Namespace) -> dict[str, Any]:
    model, tokenizer = _load_model(args)
    anchors = _budget_anchors(args.budget_anchors)
    rows = []
    methods = [item.strip() for item in args.methods.split(",") if item.strip()]
    for task in [item.strip() for item in args.tasks.split(",") if item.strip()]:
        dataset = _make_dataset(task, args)
        budget = int(anchors[task])
        for source_index in range(int(args.n_instances)):
            entry = dataset[source_index]
            entry.setdefault("metadata", {})["source_index"] = source_index
            for method in methods:
                print(json.dumps({"method": method, "task": task, "source_index": source_index, "budget_B": budget}), flush=True)
                if method == "tot":
                    rows.append(_run_tot_instance(model, tokenizer, dataset, task, entry, source_index, budget, args))
                elif method == "rap":
                    rows.append(_run_rap_instance(model, tokenizer, dataset, task, entry, source_index, budget, args))
                else:
                    raise ValueError(f"unknown method: {method}")
                _write_json(args.checkpoint_path, {"rows": rows})
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()},
        "summary": _summarize(rows),
        "rows": rows,
        "source": SOURCE,
        "provenance": "kvcache_tot_rap_baselines_v0",
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in {"run-shard", "merge"}:
        parser = argparse.ArgumentParser(description="Run or merge ToT/RAP no-train baselines under matched token budgets.")
        sub = parser.add_subparsers(dest="command", required=True)
        run_parser = sub.add_parser("run-shard")
        _add_common_args(run_parser)
        run_parser.add_argument("--resume", action="store_true")
        run_parser.add_argument("--budget-scales", default="0.25,0.5,1,2,4")
        run_parser.add_argument("--num-shards", type=int, default=1)
        run_parser.add_argument("--shard-index", type=int, default=0)
        merge_parser = sub.add_parser("merge")
        merge_parser.add_argument("--inputs", required=True)
        merge_parser.add_argument("--output", type=Path, required=True)
        args = parser.parse_args()
        payload = run_shard(args) if args.command == "run-shard" else merge(args)
        print(json.dumps({"path": str(args.output), "status": payload["status"], "rows": len(payload["rows"])}, sort_keys=True))
        return
    parser = argparse.ArgumentParser(description="Run ToT/RAP repo-port smokes under matched budgets.")
    _add_common_args(parser)
    args = parser.parse_args()
    payload = run(args)
    print(json.dumps({"path": str(args.output), "status": payload["status"], "rows": len(payload["rows"])}, sort_keys=True))


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint-path", type=Path, required=True)
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32")
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scan-limit", type=int, default=120)
    parser.add_argument("--n-instances", type=int, default=1)
    parser.add_argument("--tasks", default="sudoku,graph_color")
    parser.add_argument("--methods", default="tot,rap")
    parser.add_argument("--budget-anchors", default="sudoku:28070,futoshiki:3206226,graph_color:32895")
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--max-expansions", type=int, default=0, help="0 means no expansion cap")
    parser.add_argument("--max-depth", type=int, default=0, help="0 means use task depth")
    parser.add_argument("--n-actions", type=int, default=3)
    parser.add_argument("--beam-size", type=int, default=2)
    parser.add_argument("--value-batch-size", type=int, default=8)
    parser.add_argument("--mcts-iters", type=int, default=0, help="0 means run MCTS until budget, goal, or safety cap")
    parser.add_argument("--uct-weight", type=float, default=1.0)
    parser.add_argument("--rollout-depth", type=int, default=0, help="0 means simulate until depth limit")
    parser.add_argument("--rollout-branching", type=int, default=1)
    parser.add_argument("--futoshiki-size", type=int, default=7)
    parser.add_argument("--futoshiki-difficulty", type=int, default=3)
    parser.add_argument("--graph-num-vertices", type=int, default=16)
    parser.add_argument("--graph-num-colors", type=int, default=3)
    parser.add_argument("--graph-edge-probability", type=float, default=0.4)
    parser.add_argument("--graph-difficulty-bin-label", default="v16_p04")


if __name__ == "__main__":
    main()
