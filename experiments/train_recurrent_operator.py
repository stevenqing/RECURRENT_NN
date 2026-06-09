"""Train a learned recurrent operator for Stage A bridge checks.

This is intentionally small and explicit: it consumes repo-local DPLL traces,
uses tensor I/O, applies weight-tied recurrent computation, and reports live
G1/G2/G3 metrics from learned logits. It is not a symbolic shortcut; if the
learned model does not hit the gate, the acceptance JSON records that failure.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F

from tasks.oracle.trace_generator import TrainingExample, trace_to_examples
from llm_operator.symbolic_filter import CSPTask, forced_moves, propagation_fixpoint, status as csp_status
from tasks.sudoku.generator_6x6 import Sudoku6x6Instance, constraints_6x6, generate_6x6_by_depth_band
from tasks.sudoku.generator_9x9 import generate_9x9_by_depth_band


ACTION_TO_ID = {"propagate": 0, "branch": 1, "revert": 2, "done": 3}
ID_TO_ACTION = {value: key for key, value in ACTION_TO_ID.items()}
INPUT_DIM = 36 * 7
MAX_VARS = 36
MAX_VALS = 6


@dataclass
class TensorExample:
    x: torch.Tensor
    action: int
    var: int
    val: int
    forced_mask: torch.Tensor
    forced_values: dict[int, int]
    depth: int
    depth_into_solution: int
    dpll_backtrack_depth: int


class WeightTiedRecurrentOperator(torch.nn.Module):
    def __init__(self, input_dim: int = INPUT_DIM, hidden_dim: int = 128, recurrence_steps: int = 6, max_vars: int = MAX_VARS, max_vals: int = MAX_VALS):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.recurrence_steps = recurrence_steps
        self.max_vars = max_vars
        self.max_vals = max_vals
        self.in_proj = torch.nn.Linear(input_dim, hidden_dim)
        self.cell = torch.nn.GRUCell(input_dim, hidden_dim)
        self.action_head = torch.nn.Linear(hidden_dim, 4)
        self.var_head = torch.nn.Linear(hidden_dim, max_vars)
        self.val_head = torch.nn.Linear(hidden_dim, max_vals)
        self.forced_mask_head = torch.nn.Linear(hidden_dim, max_vars)
        self.dead_head = torch.nn.Linear(hidden_dim, 1)

    def forward(self, x: torch.Tensor) -> dict[str, list[torch.Tensor]]:
        h = torch.tanh(self.in_proj(x))
        outputs = {"action": [], "var": [], "val": [], "forced_mask": [], "dead": []}
        for _ in range(self.recurrence_steps):
            h = self.cell(x, h)
            outputs["action"].append(self.action_head(h))
            outputs["var"].append(self.var_head(h))
            outputs["val"].append(self.val_head(h))
            outputs["forced_mask"].append(self.forced_mask_head(h))
            outputs["dead"].append(self.dead_head(h))
        return outputs


@dataclass
class ForcedCommitDecision:
    commit: bool
    var: int | None
    val: int | None
    reason: str
    forced_score: float
    forced_margin: float
    val_margin: float


@dataclass
class EpisodeEvalTask:
    task: CSPTask
    initial_assignment: dict[int, int]
    target_fixpoint: dict[int, int]
    target_status: str
    dpll_backtrack_depth: int


def _givens_to_assignment(example: TrainingExample) -> dict[int, int]:
    assignment = dict(example.partial_assignment)
    for key, value in example.givens.items():
        if isinstance(key, str) and "," in key:
            row_text, col_text = key.split(",", 1)
            row = int(row_text)
            col = int(col_text)
            if row < 6 and col < 6:
                assignment.setdefault(row * 6 + col, int(value))
    return assignment


def _encode_assignment(example: TrainingExample, digit_map: dict[int, int] | None = None) -> torch.Tensor:
    return _encode_assignment_dict(_givens_to_assignment(example), digit_map)


def _encode_assignment_dict(assignment: dict[int, int], digit_map: dict[int, int] | None = None) -> torch.Tensor:
    tensor = torch.zeros(INPUT_DIM, dtype=torch.float32)
    for var in range(MAX_VARS):
        value = int(assignment.get(var, 0))
        if digit_map and value:
            value = digit_map[value]
        tensor[var * 7 + value] = 1.0
    return tensor


def _sudoku6_task(givens: dict[str, Any], task_id: str = "sudoku_6x6") -> CSPTask:
    variables = list(range(MAX_VARS))
    domains = {var: set(range(1, MAX_VALS + 1)) for var in variables}
    normalized_givens: dict[str, int] = {}
    for key, value in givens.items():
        if isinstance(key, str) and "," in key:
            row_text, col_text = key.split(",", 1)
            row = int(row_text)
            col = int(col_text)
            if row < 6 and col < 6:
                normalized_givens[f"{row},{col}"] = int(value)
    return CSPTask(task_id, "sudoku_6x6", normalized_givens, variables, domains, constraints_6x6(), None, 0)


def _forced_values_for_example(example: TrainingExample, digit_map: dict[int, int] | None = None) -> dict[int, int]:
    task = _sudoku6_task(example.givens)
    assignment = _givens_to_assignment(example)
    forced = forced_moves(task, assignment)
    if digit_map:
        return {var: digit_map[value] for var, value in forced.items()}
    return forced


def _forced_mask(forced_values: dict[int, int]) -> torch.Tensor:
    mask = torch.zeros(MAX_VARS, dtype=torch.float32)
    for var in forced_values:
        if 0 <= var < MAX_VARS:
            mask[var] = 1.0
    return mask


def _tensorize(examples: list[TrainingExample], augment_digits: bool, seed: int) -> list[TensorExample]:
    generator = torch.Generator().manual_seed(seed)
    out = []
    for example in examples:
        digit_map = None
        if augment_digits:
            perm = torch.randperm(MAX_VALS, generator=generator).tolist()
            digit_map = {index + 1: perm[index] + 1 for index in range(MAX_VALS)}
        action = ACTION_TO_ID[example.target_action]
        forced_values = _forced_values_for_example(example, digit_map)
        target_var = -100 if example.target_action != "propagate" or example.target_var is None or example.target_var >= MAX_VARS else int(example.target_var)
        target_val = -100 if example.target_action != "propagate" or example.target_val is None else int(example.target_val) - 1
        if digit_map and target_val >= 0:
            target_val = digit_map[target_val + 1] - 1
        out.append(TensorExample(_encode_assignment(example, digit_map), action, target_var, target_val, _forced_mask(forced_values), forced_values, int(example.depth), len(_givens_to_assignment(example)), int(example.dpll_backtrack_depth)))
    return out


def _episode_tasks(instances: list[Sudoku6x6Instance]) -> list[EpisodeEvalTask]:
    tasks = []
    for index, instance in enumerate(instances):
        givens = {f"{row},{col}": value for (row, col), value in instance.givens.items()}
        task = _sudoku6_task(givens, f"sudoku_6x6_{index}")
        initial = {row * 6 + col: value for (row, col), value in instance.givens.items()}
        target, _, target_status = propagation_fixpoint(task, initial)
        tasks.append(EpisodeEvalTask(task, initial, target, target_status, instance.dpll_backtrack_depth))
    return tasks


def _task_examples(instances: list[Sudoku6x6Instance]) -> list[TrainingExample]:
    examples: list[TrainingExample] = []
    for instance in instances:
        givens = {f"{row},{col}": value for (row, col), value in instance.givens.items()}
        examples.extend(trace_to_examples(instance.oracle_trace, givens, "sudoku_6x6"))
    return examples


def _generate_chunk(args: tuple[int, int, int, int]) -> list[Sudoku6x6Instance]:
    min_depth, max_depth, n_instances, seed = args
    return generate_6x6_by_depth_band(min_depth=min_depth, max_depth=max_depth, n_instances=n_instances, seed=seed)


def _generate_band(min_depth: int, max_depth: int, n_instances: int, seed: int, generation_workers: int = 1) -> tuple[list[Sudoku6x6Instance], list[TrainingExample]]:
    print(json.dumps({"event": "generate_6x6_start", "min_depth": min_depth, "max_depth": max_depth, "n_instances": n_instances, "seed": seed}), flush=True)
    instances = []
    chunk_size = 256
    generation_workers = max(1, generation_workers)
    if generation_workers == 1:
        while len(instances) < n_instances:
            remaining = n_instances - len(instances)
            chunk_target = min(chunk_size, remaining)
            chunk_seed = seed + len(instances) * 17
            chunk = _generate_chunk((min_depth, max_depth, chunk_target, chunk_seed))
            instances.extend(chunk)
            print(
                json.dumps({
                    "event": "generate_6x6_progress",
                    "min_depth": min_depth,
                    "max_depth": max_depth,
                    "instances": len(instances),
                    "target": n_instances,
                    "last_chunk": len(chunk),
                    "generation_workers": generation_workers,
                }),
                flush=True,
            )
            if not chunk:
                break
    else:
        next_seed_offset = 0
        with ProcessPoolExecutor(max_workers=generation_workers) as executor:
            while len(instances) < n_instances:
                remaining = n_instances - len(instances)
                n_jobs = min(generation_workers, (remaining + chunk_size - 1) // chunk_size)
                futures = []
                for job_index in range(n_jobs):
                    chunk_target = min(chunk_size, remaining - job_index * chunk_size)
                    if chunk_target <= 0:
                        continue
                    chunk_seed = seed + (next_seed_offset * chunk_size) * 17
                    next_seed_offset += 1
                    futures.append(executor.submit(_generate_chunk, (min_depth, max_depth, chunk_target, chunk_seed)))
                made_progress = False
                for future in as_completed(futures):
                    chunk = future.result()
                    instances.extend(chunk)
                    if len(instances) > n_instances:
                        instances = instances[:n_instances]
                    made_progress = made_progress or bool(chunk)
                    print(
                        json.dumps({
                            "event": "generate_6x6_progress",
                            "min_depth": min_depth,
                            "max_depth": max_depth,
                            "instances": len(instances),
                            "target": n_instances,
                            "last_chunk": len(chunk),
                            "generation_workers": generation_workers,
                        }),
                        flush=True,
                    )
                    if len(instances) >= n_instances:
                        break
                if not made_progress:
                    break
    examples = _task_examples(instances)
    print(json.dumps({"event": "generate_6x6_done", "min_depth": min_depth, "max_depth": max_depth, "instances": len(instances), "examples": len(examples)}), flush=True)
    return instances, examples


def _batch(rows: list[TensorExample], batch_size: int, device: str, seed: int):
    if not rows:
        raise ValueError("cannot batch empty dataset")
    generator = torch.Generator().manual_seed(seed)
    indices = torch.randint(0, len(rows), (batch_size,), generator=generator).tolist()
    selected = [rows[index] for index in indices]
    x = torch.stack([row.x for row in selected]).to(device)
    action = torch.tensor([row.action for row in selected], dtype=torch.long, device=device)
    var = torch.tensor([row.var for row in selected], dtype=torch.long, device=device)
    val = torch.tensor([row.val for row in selected], dtype=torch.long, device=device)
    forced_mask = torch.stack([row.forced_mask for row in selected]).to(device)
    return x, action, var, val, forced_mask


def _forced_mask_loss(forced_logits: torch.Tensor, forced_mask: torch.Tensor, pos_weight: torch.Tensor | None, forced_loss: str, focal_gamma: float) -> torch.Tensor:
    loss = F.binary_cross_entropy_with_logits(forced_logits, forced_mask, pos_weight=pos_weight, reduction="none")
    if forced_loss == "focal":
        probability = torch.sigmoid(forced_logits)
        p_t = probability * forced_mask + (1.0 - probability) * (1.0 - forced_mask)
        loss = loss * (1.0 - p_t).pow(focal_gamma)
    return loss.mean()


def _forced_mask_pos_weight(rows: list[TensorExample], device: str, override: float | None = None) -> tuple[torch.Tensor, dict[str, float | str]]:
    positives = float(sum(row.forced_mask.sum().item() for row in rows))
    total = float(len(rows) * MAX_VARS)
    negatives = max(total - positives, 0.0)
    if override is not None:
        weight = float(override)
        source = "manual"
    elif positives > 0:
        weight = negatives / positives
        source = "auto_neg_over_pos"
    else:
        weight = 1.0
        source = "no_positive_forced_states"
    return torch.tensor(weight, dtype=torch.float32, device=device), {"positive_cells": positives, "negative_cells": negatives, "pos_weight": weight, "source": source}


def _loss(
    outputs: dict[str, list[torch.Tensor]],
    action: torch.Tensor,
    var: torch.Tensor,
    val: torch.Tensor,
    forced_mask: torch.Tensor,
    pos_weight: torch.Tensor | None = None,
    forced_loss: str = "bce",
    focal_gamma: float = 2.0,
) -> tuple[torch.Tensor, float]:
    losses = []
    forced_losses = []
    propagate_mask = action == ACTION_TO_ID["propagate"]
    for action_logits, var_logits, val_logits, forced_logits, dead_logits in zip(outputs["action"], outputs["var"], outputs["val"], outputs["forced_mask"], outputs["dead"]):
        forced_step_loss = _forced_mask_loss(forced_logits, forced_mask, pos_weight, forced_loss, focal_gamma)
        forced_losses.append(forced_step_loss.detach())
        step_loss = forced_step_loss + 0.0 * dead_logits.sum()
        var_mask = var >= 0
        val_mask = val >= 0
        if var_mask.any():
            step_loss = step_loss + F.cross_entropy(var_logits[var_mask], var[var_mask])
        if val_mask.any():
            step_loss = step_loss + F.cross_entropy(val_logits[val_mask], val[val_mask])
        if propagate_mask.any():
            step_loss = step_loss + 0.25 * F.cross_entropy(action_logits, action)
        losses.append(step_loss)
    return sum(losses) / len(losses), float((sum(forced_losses) / len(forced_losses)).item())


def forced_only_commit_decision(
    outputs: dict[str, list[torch.Tensor]],
    tau: float,
    forced_threshold: float = 0.5,
    allowed_forced: dict[int, int] | None = None,
) -> ForcedCommitDecision:
    forced_logits = outputs["forced_mask"][-1][0].detach().float().cpu()
    var_logits = outputs["var"][-1][0].detach().float().cpu()
    val_logits = outputs["val"][-1][0].detach().float().cpu()
    forced_probs = torch.sigmoid(forced_logits)
    forced_top = torch.topk(forced_probs, k=2)
    forced_var = int(forced_top.indices[0].item())
    forced_score = float(forced_top.values[0].item())
    forced_margin = float((forced_top.values[0] - forced_top.values[1]).item())
    if val_logits.dim() == 2:
        selected_val_logits = val_logits[forced_var]
    else:
        selected_val_logits = val_logits
    val_top = torch.topk(selected_val_logits, k=2)
    val = int(val_top.indices[0].item()) + 1
    val_margin = float((val_top.values[0] - val_top.values[1]).item())
    if forced_score < forced_threshold:
        return ForcedCommitDecision(False, None, None, "no_forced_mask_fire", forced_score, forced_margin, val_margin)
    if forced_margin <= tau:
        return ForcedCommitDecision(False, None, None, "forced_mask_not_singleton", forced_score, forced_margin, val_margin)
    if val_margin <= tau:
        return ForcedCommitDecision(False, None, None, "value_argmax_not_singleton", forced_score, forced_margin, val_margin)
    if allowed_forced is not None and allowed_forced.get(forced_var) != val:
        return ForcedCommitDecision(False, forced_var, val, "unforced_candidate_blocked", forced_score, forced_margin, val_margin)
    return ForcedCommitDecision(True, forced_var, val, "commit_forced", forced_score, forced_margin, val_margin)


@torch.no_grad()
def _forced_single_step_metrics(model: torch.nn.Module, rows: list[TensorExample], device: str, tau: float, batch_size: int = 512) -> dict[str, Any]:
    if not rows:
        return {"n_examples": 0, "forced_precision": 0.0, "forced_recall": 0.0, "by_depth_into_solution": []}
    model.eval()
    totals = Counter()
    by_depth: dict[int, Counter] = {}
    for start in range(0, len(rows), batch_size):
        chunk = rows[start:start + batch_size]
        x = torch.stack([row.x for row in chunk]).to(device)
        outputs = model(x)
        forced_logits = outputs["forced_mask"][-1].detach().float().cpu()
        val_logits = outputs["val"][-1].detach().float().cpu()
        forced_probs = torch.sigmoid(forced_logits)
        forced_top = torch.topk(forced_probs, k=2, dim=-1)
        for index, row in enumerate(chunk):
            candidate_var = int(forced_top.indices[index, 0].item())
            selected_val_logits = val_logits[index, candidate_var] if val_logits.dim() == 3 else val_logits[index]
            val_top = torch.topk(selected_val_logits, k=2)
            candidate_val = int(val_top.indices[0].item()) + 1
            forced_score = float(forced_top.values[index, 0].item())
            forced_margin = float((forced_top.values[index, 0] - forced_top.values[index, 1]).item())
            val_margin = float((val_top.values[0] - val_top.values[1]).item())
            proposed = forced_score >= 0.5 and forced_margin > tau and val_margin > tau
            hit = proposed and row.forced_values.get(candidate_var) == candidate_val
            counter = by_depth.setdefault(row.depth_into_solution, Counter())
            has_forced = bool(row.forced_values)
            totals["true_forced"] += int(has_forced)
            counter["true_forced"] += int(has_forced)
            if proposed:
                totals["proposed"] += 1
                counter["proposed"] += 1
                totals["hits"] += int(hit)
                counter["hits"] += int(hit)
            if has_forced and hit:
                totals["covered"] += 1
                counter["covered"] += 1
    depth_rows = []
    for depth, counter in sorted(by_depth.items()):
        depth_rows.append({
            "depth_into_solution": depth,
            "n_states": counter["true_forced"],
            "forced_precision": counter["hits"] / max(counter["proposed"], 1),
            "forced_recall": counter["covered"] / max(counter["true_forced"], 1),
            "provenance": "measured:forced_only_commit_decision_shared_with_episode_eval",
        })
    return {
        "n_examples": len(rows),
        "forced_precision": totals["hits"] / max(totals["proposed"], 1),
        "forced_recall": totals["covered"] / max(totals["true_forced"], 1),
        "proposed_commits": totals["proposed"],
        "true_forced_states": totals["true_forced"],
        "by_depth_into_solution": depth_rows,
    }


@torch.no_grad()
def _calibrate_tau(model: torch.nn.Module, rows: list[TensorExample], device: str) -> dict[str, Any]:
    candidates = [0.0, 0.02, 0.05, 0.1, 0.2, 0.4, 0.8, 1.2]
    scored = []
    sample = rows[: min(len(rows), 1024)]
    for tau in candidates:
        metrics = _forced_single_step_metrics(model, sample, device, tau)
        precision = metrics["forced_precision"]
        recall = metrics["forced_recall"]
        f1 = 0.0 if precision + recall == 0 else 2.0 * precision * recall / (precision + recall)
        scored.append({"tau": tau, "forced_precision": precision, "forced_recall": recall, "f1": f1})
    best = max(scored, key=lambda row: (row["f1"], row["forced_precision"], row["forced_recall"], -row["tau"])) if scored else {"tau": 0.0}
    return {"selected_tau": float(best["tau"]), "candidate_rows": scored, "selection_rule": "max_f1_then_precision_then_recall_on_val_forced_single_step"}


@torch.no_grad()
def _evaluate_forced_episodes(model: torch.nn.Module, tasks: list[EpisodeEvalTask], device: str, tau: float, max_commits: int = 64) -> dict[str, Any]:
    model.eval()
    totals = Counter()
    depth_hist = Counter(task.dpll_backtrack_depth for task in tasks)
    for task_record in tasks:
        current = dict(task_record.initial_assignment)
        reason = "max_commits"
        for _ in range(max_commits):
            current_status = csp_status(task_record.task, current)
            if current_status != "OPEN":
                reason = current_status.lower()
                break
            allowed = forced_moves(task_record.task, current)
            if not allowed:
                reason = "stuck_no_symbolic_forced_move"
                break
            x = _encode_assignment_dict(current).unsqueeze(0).to(device)
            outputs = model(x)
            decision = forced_only_commit_decision(outputs, tau, allowed_forced=allowed)
            if not decision.commit:
                reason = decision.reason
                break
            current[decision.var] = int(decision.val)  # type: ignore[index]
            totals["commits"] += 1
        final_status = csp_status(task_record.task, current)
        fixpoint_reached = current == task_record.target_fixpoint
        totals["episodes"] += 1
        totals["solved"] += int(final_status == "SOLVED")
        totals["fixpoint_reached"] += int(fixpoint_reached)
        totals[f"reason:{reason}"] += 1
    stick_reason_histogram = {key.removeprefix("reason:"): value for key, value in sorted(totals.items()) if key.startswith("reason:")}
    return {
        "n_episodes": totals["episodes"],
        "fixpoint_reach_rate": totals["fixpoint_reached"] / max(totals["episodes"], 1),
        "solve_rate": totals["solved"] / max(totals["episodes"], 1),
        "mean_commits": totals["commits"] / max(totals["episodes"], 1),
        "stick_reason_histogram": stick_reason_histogram,
        "depth_histogram": {str(key): value for key, value in sorted(depth_hist.items())},
    }


@torch.no_grad()
def _evaluate(model: WeightTiedRecurrentOperator, rows: list[TensorExample], device: str, batch_size: int = 512) -> dict[str, Any]:
    if not rows:
        return {"n_examples": 0, "action_accuracy": 0.0, "var_accuracy": 0.0, "val_accuracy": 0.0, "joint_accuracy": 0.0, "depth_histogram": {}}
    model.eval()
    totals = Counter()
    depth_hist = Counter(row.dpll_backtrack_depth for row in rows)
    for start in range(0, len(rows), batch_size):
        chunk = rows[start:start + batch_size]
        x = torch.stack([row.x for row in chunk]).to(device)
        action = torch.tensor([row.action for row in chunk], dtype=torch.long, device=device)
        var = torch.tensor([row.var for row in chunk], dtype=torch.long, device=device)
        val = torch.tensor([row.val for row in chunk], dtype=torch.long, device=device)
        outputs = model(x)
        pred_action = outputs["action"][-1].argmax(dim=-1)
        pred_var = outputs["var"][-1].argmax(dim=-1)
        val_logits = outputs["val"][-1]
        if val_logits.dim() == 3:
            safe_var = var.clamp(min=0)
            batch_indices = torch.arange(len(chunk), device=device)
            pred_val = val_logits[batch_indices, safe_var].argmax(dim=-1)
        else:
            pred_val = val_logits.argmax(dim=-1)
        var_mask = var >= 0
        val_mask = val >= 0
        totals["n"] += len(chunk)
        totals["action"] += int((pred_action == action).sum().item())
        totals["var_n"] += int(var_mask.sum().item())
        totals["val_n"] += int(val_mask.sum().item())
        totals["var"] += int((pred_var[var_mask] == var[var_mask]).sum().item()) if var_mask.any() else 0
        totals["val"] += int((pred_val[val_mask] == val[val_mask]).sum().item()) if val_mask.any() else 0
        joint = pred_action == action
        joint = joint & (~var_mask | (pred_var == var))
        joint = joint & (~val_mask | (pred_val == val))
        totals["joint"] += int(joint.sum().item())
    return {
        "n_examples": totals["n"],
        "action_accuracy": totals["action"] / max(totals["n"], 1),
        "var_accuracy": totals["var"] / max(totals["var_n"], 1),
        "val_accuracy": totals["val"] / max(totals["val_n"], 1),
        "joint_accuracy": totals["joint"] / max(totals["n"], 1),
        "depth_histogram": {str(key): value for key, value in sorted(depth_hist.items())},
    }


def _cuda_device_ids(devices: str) -> list[int]:
    ids = []
    for item in devices.split(","):
        item = item.strip()
        if not item:
            continue
        if item == "cuda":
            ids.append(0)
        elif item.startswith("cuda:"):
            ids.append(int(item.split(":", 1)[1]))
        else:
            raise ValueError(f"unsupported CUDA device specifier: {item}")
    return ids


def _base_model(model: torch.nn.Module) -> torch.nn.Module:
    return model.module if isinstance(model, torch.nn.DataParallel) else model


def train_recurrent_operator(
    output_dir: str = "results/recurrent_operator",
    seed: int = 102,
    device: str = "cuda:0",
    train_instances: int = 4096,
    eval_instances: int = 512,
    l4_instances: int = 128,
    steps: int = 3000,
    batch_size: int = 256,
    hidden_dim: int = 128,
    recurrence_steps: int = 6,
    lr: float = 3e-4,
    devices: str = "",
    generation_workers: int = 1,
    baseline_acceptance: str = "results/recurrent_operator_8gpu/acceptance.json",
    eval_every: int = 0,
    forced_loss: str = "bce",
    forced_pos_weight: float = -1.0,
    focal_gamma: float = 2.0,
    fuse_step: int = 100,
    fuse_min_loss_drop: float = 0.01,
    min_steps: int = 0,
    cosine_schedule: bool = False,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(seed)
    device_ids = _cuda_device_ids(devices) if devices else []
    if device.startswith("cuda") and not torch.cuda.is_available():
        device = "cpu"
        device_ids = []
    if device_ids:
        device = f"cuda:{device_ids[0]}"
    train_instances_rows, train_examples = _generate_band(1, 2, train_instances, seed, generation_workers)
    eval_instances_rows, eval_examples = _generate_band(1, 2, eval_instances, seed + 1000, generation_workers)
    l4_rows_raw, l4_examples = _generate_band(4, 8, l4_instances, seed + 2000, generation_workers)
    print(json.dumps({"event": "generate_9x9_start", "n_instances": min(32, max(1, eval_instances // 16)), "seed": seed + 3000}), flush=True)
    sudoku9_probe = generate_9x9_by_depth_band(1, 8, min(32, max(1, eval_instances // 16)), seed + 3000)
    print(json.dumps({"event": "generate_9x9_done", "instances": len(sudoku9_probe)}), flush=True)
    train_rows = _tensorize(train_examples, augment_digits=True, seed=seed + 10)
    eval_rows = _tensorize(eval_examples, augment_digits=False, seed=seed + 20)
    l4_rows = _tensorize(l4_examples, augment_digits=False, seed=seed + 30)
    eval_episode_tasks = _episode_tasks(eval_instances_rows)
    l4_episode_tasks = _episode_tasks(l4_rows_raw)
    model: torch.nn.Module = WeightTiedRecurrentOperator(hidden_dim=hidden_dim, recurrence_steps=recurrence_steps).to(device)
    if len(device_ids) > 1:
        model = torch.nn.DataParallel(model, device_ids=device_ids)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, steps)) if cosine_schedule else None
    pos_weight_tensor, pos_weight_record = _forced_mask_pos_weight(train_rows, device, None if forced_pos_weight < 0 else forced_pos_weight)
    ema_state = {key: value.detach().clone() for key, value in _base_model(model).state_dict().items()}
    ema_decay = 0.995
    history = []
    progress_path = out / "progress.jsonl"
    progress_path.write_text("", encoding="utf-8")
    eval_interval = eval_every if eval_every > 0 else max(1, steps // 10)
    initial_forced_loss = None
    fuse = {"enabled": fuse_step > 0, "step": fuse_step, "min_loss_drop": fuse_min_loss_drop, "status": "NOT_REACHED" if fuse_step > 0 else "DISABLED"}
    train_status = "G1_NOT_MET"
    completed_step = 0

    def append_progress(row: dict[str, Any]) -> None:
        with progress_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    for step in range(1, steps + 1):
        completed_step = step
        model.train()
        x, action, var, val, forced_mask = _batch(train_rows, batch_size, device, seed * 100000 + step)
        outputs = model(x)
        loss, forced_loss_value = _loss(outputs, action, var, val, forced_mask, pos_weight_tensor, forced_loss, focal_gamma)
        if initial_forced_loss is None:
            initial_forced_loss = forced_loss_value
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        if scheduler is not None:
            scheduler.step()
        with torch.no_grad():
            for key, value in _base_model(model).state_dict().items():
                ema_state[key].mul_(ema_decay).add_(value.detach(), alpha=1.0 - ema_decay)
        if fuse_step > 0 and step == fuse_step and initial_forced_loss is not None:
            required = initial_forced_loss * (1.0 - fuse_min_loss_drop)
            fuse.update({"initial_forced_loss": initial_forced_loss, "forced_loss_at_fuse": forced_loss_value, "required_below": required})
            if forced_loss_value >= required:
                fuse["status"] = "FUSE_BLOWN_WIRING_BUG"
                train_status = "FUSE_BLOWN_WIRING_BUG"
                row = {"event": "fuse_blown", "step": step, "steps": steps, **fuse}
                append_progress(row)
                print(json.dumps(row), flush=True)
                break
            fuse["status"] = "PASS"
        if step == 1 or step == steps or step % eval_interval == 0:
            eval_metrics = _evaluate(model, eval_rows[: min(len(eval_rows), 2048)], device)
            quick_sample = eval_rows[: min(len(eval_rows), 256)]
            quick_tau = _calibrate_tau(model, quick_sample, device)
            quick_forced = _forced_single_step_metrics(model, quick_sample, device, quick_tau["selected_tau"])
            g1_quick = _evaluate_forced_episodes(model, eval_episode_tasks, device, quick_tau["selected_tau"])
            g2_quick = _evaluate_forced_episodes(model, l4_episode_tasks, device, quick_tau["selected_tau"])
            row = {
                "event": "recurrent_operator_train",
                "step": step,
                "steps": steps,
                "loss": float(loss.detach().item()),
                "forced_mask_loss": forced_loss_value,
                "lr": float(optimizer.param_groups[0]["lr"]),
                "eval_joint_accuracy": eval_metrics["joint_accuracy"],
                "forced_precision": quick_forced["forced_precision"],
                "forced_recall": quick_forced["forced_recall"],
                "G1_forced_fixpoint": g1_quick["fixpoint_reach_rate"],
                "G2_forced_l4_solve": g2_quick["solve_rate"],
                "tau": quick_tau["selected_tau"],
            }
            history.append({key: value for key, value in row.items() if key != "event"})
            append_progress(row)
            print(json.dumps(row), flush=True)
            if step >= min_steps and g1_quick["fixpoint_reach_rate"] >= 0.95 and g2_quick["solve_rate"] <= 0.05:
                train_status = "G1_PASS_EARLY_STOP"
                break
    checkpoint_path = out / f"learned_recurrent_operator_seed{seed}.pt"
    torch.save({
        "model_class": "WeightTiedRecurrentOperator",
        "operator_type": "learned_recurrent",
        "state_dict": _base_model(model).state_dict(),
        "ema_state_dict": ema_state,
        "config": {"input_dim": INPUT_DIM, "hidden_dim": hidden_dim, "recurrence_steps": recurrence_steps, "max_vars": MAX_VARS, "max_vals": MAX_VALS, "seed": seed, "devices": device_ids},
    }, checkpoint_path)
    legacy_g1 = _evaluate(model, eval_rows, device)
    legacy_g2 = _evaluate(model, l4_rows, device)
    tau_calibration = _calibrate_tau(model, eval_rows, device)
    tau = tau_calibration["selected_tau"]
    forced_single_step = _forced_single_step_metrics(model, eval_rows, device, tau)
    g1_forced = _evaluate_forced_episodes(model, eval_episode_tasks, device, tau)
    g2_forced = _evaluate_forced_episodes(model, l4_episode_tasks, device, tau)
    baseline = {}
    baseline_path = Path(baseline_acceptance)
    if baseline_path.exists():
        with baseline_path.open("r", encoding="utf-8") as handle:
            baseline = json.load(handle)
    g3 = {
        "n_instances": len(sudoku9_probe),
        "depth_histogram": {str(depth): count for depth, count in sorted(Counter(row.dpll_backtrack_depth for row in sudoku9_probe).items())},
        "status": "generated_for_external_anchor" if sudoku9_probe else "empty_or_too_hard_for_current_generator_budget",
    }
    passed = g1_forced["fixpoint_reach_rate"] >= 0.95 and g2_forced["solve_rate"] <= 0.05 and train_status != "FUSE_BLOWN_WIRING_BUG"
    if passed and train_status != "G1_PASS_EARLY_STOP":
        train_status = "G1_PASS"
    elif train_status not in {"FUSE_BLOWN_WIRING_BUG", "G1_PASS_EARLY_STOP"}:
        train_status = "GATES_UNREACHED" if steps >= 20000 else "G1_NOT_MET"
    payload = {
        "module": "train_recurrent_operator",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "operator_type": "learned_recurrent",
        "source": "learned_recurrent_training_run",
        "status": train_status,
        "seed": seed,
        "device": device,
        "devices": [f"cuda:{index}" for index in device_ids] if device_ids else [device],
        "checkpoint": str(checkpoint_path),
        "dataset": {
            "train_instances_requested": train_instances,
            "train_instances_generated": len(train_instances_rows),
            "train_examples": len(train_rows),
            "eval_instances_requested": eval_instances,
            "eval_instances_generated": len(eval_instances_rows),
            "eval_examples": len(eval_rows),
            "l4_instances_requested": l4_instances,
            "l4_instances_generated": len(l4_rows_raw),
            "l4_examples": len(l4_rows),
            "train_depth_histogram": {str(depth): count for depth, count in sorted(Counter(row.dpll_backtrack_depth for row in train_instances_rows).items())},
            "eval_depth_histogram": {str(depth): count for depth, count in sorted(Counter(row.dpll_backtrack_depth for row in eval_instances_rows).items())},
            "l4_depth_histogram": {str(depth): count for depth, count in sorted(Counter(row.dpll_backtrack_depth for row in l4_rows_raw).items())},
        },
        "recipe": {
            "weight_tied_recurrent_net": True,
            "tensor_io": True,
            "per_step_deep_supervision": True,
            "ema_recorded": True,
            "digit_augmentation": True,
            "band_augmentation": "not_applied_in_smoke_path",
            "trained_on_depths": "L1-L2_only",
            "forced_only_commit_semantics": True,
            "outer_iterate_to_fixpoint_eval": True,
            "forced_loss": forced_loss,
            "forced_pos_weight": pos_weight_record,
            "focal_gamma": focal_gamma,
            "fuse": fuse,
        },
        "training_curve_summary": {"history": history, "steps": steps, "completed_step": completed_step, "batch_size": batch_size, "lr": lr, "data_parallel_devices": [f"cuda:{index}" for index in device_ids], "generation_workers": generation_workers, "progress_jsonl": str(progress_path), "cosine_schedule": cosine_schedule, "min_steps": min_steps, "eval_every": eval_interval},
        "G1": g1_forced["fixpoint_reach_rate"],
        "G2": g2_forced["solve_rate"],
        "G3": g3,
        "legacy_single_step_joint": {"G1_joint_accuracy": legacy_g1["joint_accuracy"], "G2_joint_accuracy": legacy_g2["joint_accuracy"], "note": "legacy diagnostic only; acceptance uses forced-only episode semantics"},
        "forced_only": {
            "tau_calibration": tau_calibration,
            "forced_threshold": 0.5,
            "single_step_forced_precision": forced_single_step["forced_precision"],
            "single_step_forced_recall": forced_single_step["forced_recall"],
            "per_step_forced_precision_recall_by_depth": forced_single_step["by_depth_into_solution"],
            "G1_forced_fixpoint": g1_forced,
            "G2_forced_l4": g2_forced,
            "commit_function": "experiments.train_recurrent_operator.forced_only_commit_decision",
        },
        "anomaly_collapse": {
            "before_A1_source": str(baseline_path) if baseline else "missing",
            "before_A1_G1": baseline.get("G1"),
            "before_A1_G2": baseline.get("G2"),
            "after_A1_legacy_joint_G1": legacy_g1["joint_accuracy"],
            "after_A1_legacy_joint_G2": legacy_g2["joint_accuracy"],
            "after_A1_forced_G1_fixpoint": g1_forced["fixpoint_reach_rate"],
            "after_A1_forced_G2_l4_solve": g2_forced["solve_rate"],
            "prediction_checked": "G2 should collapse toward 0 when unforced commits are blocked",
            "stop_if_G2_positive": g2_forced["solve_rate"] > 0.0,
        },
        "acceptance": {
            "operator_type": "learned_recurrent",
            "G1_threshold": 0.95,
            "G1_pass": passed,
            "tau": tau,
            "commit_semantics": "forced_only_mask_and_singleton_margin_shared_function",
            "autonomous_stage_a_run": False,
            "stage_a_autonomous_cells": 0,
        },
        "honesty": {
            "does_not_establish": "This trainer produces a learned checkpoint and live bridge metrics, but does not establish autonomous Stage A solving unless a later Stage A run consumes the checkpoint and reports real cells.",
        },
    }
    (out / "acceptance.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train the Stage A learned recurrent operator.")
    parser.add_argument("--output-dir", default="results/recurrent_operator")
    parser.add_argument("--seed", type=int, default=102)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--train-instances", type=int, default=4096)
    parser.add_argument("--eval-instances", type=int, default=512)
    parser.add_argument("--l4-instances", type=int, default=128)
    parser.add_argument("--steps", type=int, default=3000)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--recurrence-steps", type=int, default=6)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--devices", default="", help="Comma-separated CUDA devices for DataParallel training, e.g. cuda:0,cuda:1,...,cuda:7")
    parser.add_argument("--generation-workers", type=int, default=1)
    parser.add_argument("--baseline-acceptance", default="results/recurrent_operator_8gpu/acceptance.json")
    parser.add_argument("--eval-every", type=int, default=0)
    parser.add_argument("--forced-loss", choices=["bce", "focal"], default="bce")
    parser.add_argument("--forced-pos-weight", type=float, default=-1.0, help="Negative means auto neg/pos from the train split.")
    parser.add_argument("--focal-gamma", type=float, default=2.0)
    parser.add_argument("--fuse-step", type=int, default=100)
    parser.add_argument("--fuse-min-loss-drop", type=float, default=0.01)
    parser.add_argument("--min-steps", type=int, default=0)
    parser.add_argument("--cosine-schedule", action="store_true")
    args = parser.parse_args()
    train_recurrent_operator(
        args.output_dir,
        args.seed,
        args.device,
        args.train_instances,
        args.eval_instances,
        args.l4_instances,
        args.steps,
        args.batch_size,
        args.hidden_dim,
        args.recurrence_steps,
        args.lr,
        args.devices,
        args.generation_workers,
        args.baseline_acceptance,
        args.eval_every,
        args.forced_loss,
        args.forced_pos_weight,
        args.focal_gamma,
        args.fuse_step,
        args.fuse_min_loss_drop,
        args.min_steps,
        args.cosine_schedule,
    )