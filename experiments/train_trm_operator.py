"""Train Track B learned operator with per-cell tokens and tied transformer recurrence."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import nullcontext
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel

from experiments.train_recurrent_operator import (
    ACTION_TO_ID,
    EpisodeEvalTask,
    MAX_VALS,
    MAX_VARS,
    TensorExample,
    _base_model,
    _batch,
    _calibrate_tau,
    _cuda_device_ids,
    _evaluate,
    _forced_mask,
    _forced_mask_pos_weight,
    _forced_values_for_example,
    _generate_band,
    _givens_to_assignment,
    _loss,
    _sudoku6_task,
    forced_only_commit_decision,
)
from llm_operator.symbolic_filter import CSPTask, forced_moves, propagation_fixpoint, status as csp_status, valid_values
from tasks.sudoku.generator_6x6 import Sudoku6x6Instance
from tasks.oracle.trace_generator import TrainingExample

TOKEN_FEATURE_DIM = MAX_VALS + 1 + 6 + 6 + 6


@dataclass
class TrackBConfig:
    hidden_dim: int
    nhead: int
    feedforward_dim: int
    recurrence_steps: int
    dropout: float


@dataclass(frozen=True)
class GpuResidentDataset:
    x: torch.Tensor
    action: torch.Tensor
    var: torch.Tensor
    val: torch.Tensor
    forced_mask: torch.Tensor


def _box_id(var: int) -> int:
    row = var // 6
    col = var % 6
    return (row // 2) * 2 + (col // 3)


def _mapped_givens(example: TrainingExample, digit_map: dict[int, int] | None) -> dict[str, int]:
    givens: dict[str, int] = {}
    for key, value in example.givens.items():
        if isinstance(key, str) and "," in key:
            givens[key] = int(digit_map.get(int(value), int(value)) if digit_map else value)
    return givens


def _mapped_assignment(example: TrainingExample, digit_map: dict[int, int] | None) -> dict[int, int]:
    assignment = _givens_to_assignment(example)
    if digit_map:
        assignment = {var: digit_map[value] for var, value in assignment.items()}
    return assignment


def _encode_assignment_tokens(task: CSPTask, assignment: dict[int, int]) -> torch.Tensor:
    tokens = torch.zeros((MAX_VARS, TOKEN_FEATURE_DIM), dtype=torch.float32)
    given_vars = set()
    for key in task.givens:
        row_text, col_text = str(key).split(",", 1)
        given_vars.add(int(row_text) * 6 + int(col_text))
    for var in range(MAX_VARS):
        offset = 0
        if var in assignment:
            value = int(assignment[var])
            if 1 <= value <= MAX_VALS:
                tokens[var, offset + value - 1] = 1.0
        else:
            for value in valid_values(task, assignment, var):
                if 1 <= value <= MAX_VALS:
                    tokens[var, offset + value - 1] = 1.0
        offset += MAX_VALS
        tokens[var, offset] = 1.0 if var in given_vars else 0.0
        offset += 1
        tokens[var, offset + var // 6] = 1.0
        offset += 6
        tokens[var, offset + var % 6] = 1.0
        offset += 6
        tokens[var, offset + _box_id(var)] = 1.0
    return tokens


def _tensorize_token_examples(examples: list[TrainingExample], augment_digits: bool, seed: int) -> list[TensorExample]:
    generator = torch.Generator().manual_seed(seed)
    rows: list[TensorExample] = []
    for example in examples:
        digit_map = None
        if augment_digits:
            perm = torch.randperm(MAX_VALS, generator=generator).tolist()
            digit_map = {index + 1: perm[index] + 1 for index in range(MAX_VALS)}
        mapped_givens = _mapped_givens(example, digit_map)
        task = _sudoku6_task(mapped_givens)
        assignment = _mapped_assignment(example, digit_map)
        forced_values = _forced_values_for_example(example, digit_map)
        action = ACTION_TO_ID[example.target_action]
        target_var = -100 if example.target_action != "propagate" or example.target_var is None or example.target_var >= MAX_VARS else int(example.target_var)
        target_val = -100 if example.target_action != "propagate" or example.target_val is None else int(example.target_val) - 1
        if digit_map and target_val >= 0:
            target_val = digit_map[target_val + 1] - 1
        rows.append(TensorExample(_encode_assignment_tokens(task, assignment), action, target_var, target_val, _forced_mask(forced_values), forced_values, int(example.depth), len(assignment), int(example.dpll_backtrack_depth)))
    return rows


def _tensorize_token_chunk(args: tuple[list[TrainingExample], bool, int]) -> list[TensorExample]:
    examples, augment_digits, seed = args
    return _tensorize_token_examples(examples, augment_digits, seed)


def _tensorize_token_examples_parallel(label: str, examples: list[TrainingExample], augment_digits: bool, seed: int, workers: int) -> list[TensorExample]:
    print(json.dumps({"event": "tensorize_start", "label": label, "examples": len(examples), "augment_digits": augment_digits, "workers": workers}), flush=True)
    workers = max(1, workers)
    if workers == 1 or len(examples) < 2048:
        rows = _tensorize_token_examples(examples, augment_digits, seed)
        print(json.dumps({"event": "tensorize_done", "label": label, "examples": len(examples), "rows": len(rows), "workers": 1}), flush=True)
        return rows
    chunk_size = max(1024, (len(examples) + workers - 1) // workers)
    chunks = [examples[start:start + chunk_size] for start in range(0, len(examples), chunk_size)]
    rows: list[TensorExample] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_tensorize_token_chunk, (chunk, augment_digits, seed + index * 1009)) for index, chunk in enumerate(chunks)]
        for future in as_completed(futures):
            chunk_rows = future.result()
            rows.extend(chunk_rows)
            print(json.dumps({"event": "tensorize_progress", "label": label, "rows": len(rows), "target": len(examples), "last_chunk": len(chunk_rows), "workers": workers}), flush=True)
    print(json.dumps({"event": "tensorize_done", "label": label, "examples": len(examples), "rows": len(rows), "workers": workers}), flush=True)
    return rows


def _episode_task_from_instance(args: tuple[int, Sudoku6x6Instance]) -> tuple[int, dict[str, int], dict[int, int], dict[int, int], str, int]:
    index, instance = args
    givens = {f"{row},{col}": value for (row, col), value in instance.givens.items()}
    task = _sudoku6_task(givens, f"sudoku_6x6_{index}")
    initial = {row * 6 + col: value for (row, col), value in instance.givens.items()}
    target, _, target_status = propagation_fixpoint(task, initial)
    return index, givens, initial, target, target_status, instance.dpll_backtrack_depth


def _episode_eval_task(row: tuple[int, dict[str, int], dict[int, int], dict[int, int], str, int]) -> EpisodeEvalTask:
    index, givens, initial, target, target_status, dpll_backtrack_depth = row
    return EpisodeEvalTask(_sudoku6_task(givens, f"sudoku_6x6_{index}"), initial, target, target_status, dpll_backtrack_depth)


EpisodeTaskRow = tuple[int, dict[str, int], dict[int, int], dict[int, int], str, int]


def _episode_task_rows_parallel(label: str, instances: list[Sudoku6x6Instance], workers: int) -> list[EpisodeTaskRow]:
    print(json.dumps({"event": "episode_tasks_start", "label": label, "n_instances": len(instances), "workers": workers}), flush=True)
    workers = max(1, workers)
    if workers == 1 or len(instances) < 64:
        rows = []
        for index, instance in enumerate(instances):
            rows.append(_episode_task_from_instance((index, instance)))
            if len(rows) % 64 == 0 or len(rows) == len(instances):
                print(json.dumps({"event": "episode_tasks_progress", "label": label, "instances": len(rows), "target": len(instances), "workers": 1}), flush=True)
        print(json.dumps({"event": "episode_tasks_done", "label": label, "instances": len(rows), "workers": 1}), flush=True)
        return rows
    rows_by_index: dict[int, EpisodeTaskRow] = {}
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_episode_task_from_instance, (index, instance)) for index, instance in enumerate(instances)]
        for future in as_completed(futures):
            row = future.result()
            index = row[0]
            rows_by_index[index] = row
            if len(rows_by_index) % 64 == 0 or len(rows_by_index) == len(instances):
                print(json.dumps({"event": "episode_tasks_progress", "label": label, "instances": len(rows_by_index), "target": len(instances), "workers": workers}), flush=True)
    rows = [rows_by_index[index] for index in sorted(rows_by_index)]
    print(json.dumps({"event": "episode_tasks_done", "label": label, "instances": len(rows), "workers": workers}), flush=True)
    return rows


def _episode_tasks_parallel(label: str, instances: list[Sudoku6x6Instance], workers: int) -> list[EpisodeEvalTask]:
    rows = _episode_task_rows_parallel(label, instances, workers)
    return [_episode_eval_task(row) for row in rows]


class PerCellTokenRecurrentOperator(torch.nn.Module):
    def __init__(self, config: TrackBConfig):
        super().__init__()
        self.config = config
        self.input_proj = torch.nn.Linear(TOKEN_FEATURE_DIM, config.hidden_dim)
        self.layer = torch.nn.TransformerEncoderLayer(
            d_model=config.hidden_dim,
            nhead=config.nhead,
            dim_feedforward=config.feedforward_dim,
            dropout=config.dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.norm = torch.nn.LayerNorm(config.hidden_dim)
        self.action_head = torch.nn.Linear(config.hidden_dim, 4)
        self.var_head = torch.nn.Linear(config.hidden_dim, 1)
        self.val_head = torch.nn.Linear(config.hidden_dim, MAX_VALS)
        self.forced_mask_head = torch.nn.Linear(config.hidden_dim, 1)
        self.dead_head = torch.nn.Linear(config.hidden_dim, 1)

    def forward(self, x: torch.Tensor) -> dict[str, list[torch.Tensor]]:
        h = self.input_proj(x)
        outputs = {"action": [], "var": [], "val": [], "forced_mask": [], "dead": []}
        for _ in range(self.config.recurrence_steps):
            h = self.layer(h)
            normed = self.norm(h)
            pooled = normed.mean(dim=1)
            outputs["action"].append(self.action_head(pooled))
            outputs["var"].append(self.var_head(normed).squeeze(-1))
            outputs["val"].append(self.val_head(pooled))
            outputs["forced_mask"].append(self.forced_mask_head(normed).squeeze(-1))
            outputs["dead"].append(self.dead_head(pooled))
        return outputs


@torch.no_grad()
def _evaluate_forced_episodes_token(model: torch.nn.Module, tasks: list[Any], device: str, tau: float, max_commits: int = 64) -> dict[str, Any]:
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
            x = _encode_assignment_tokens(task_record.task, current).unsqueeze(0).to(device)
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
    return {
        "n_episodes": totals["episodes"],
        "fixpoint_reach_rate": totals["fixpoint_reached"] / max(totals["episodes"], 1),
        "solve_rate": totals["solved"] / max(totals["episodes"], 1),
        "mean_commits": totals["commits"] / max(totals["episodes"], 1),
        "stick_reason_histogram": {key.removeprefix("reason:"): value for key, value in sorted(totals.items()) if key.startswith("reason:")},
        "depth_histogram": {str(key): value for key, value in sorted(depth_hist.items())},
    }


def _parameter_count(model: torch.nn.Module) -> int:
    return sum(param.numel() for param in model.parameters())


def _base_trm_model(model: torch.nn.Module) -> torch.nn.Module:
    base = model
    while isinstance(base, (torch.nn.DataParallel, DistributedDataParallel)):
        base = base.module
    base = _base_model(base)
    return getattr(base, "_orig_mod", base)


@dataclass(frozen=True)
class DdpContext:
    enabled: bool
    rank: int
    local_rank: int
    world_size: int
    device: str
    device_index: int | None


def _init_ddp_if_needed(device: str, devices: str, initialize: bool = True) -> DdpContext:
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    rank = int(os.environ.get("RANK", "0"))
    local_rank = int(os.environ.get("LOCAL_RANK", str(rank)))
    if world_size <= 1:
        match = re.search(r"cuda:(\d+)", device)
        return DdpContext(False, 0, 0, 1, device, int(match.group(1)) if match else None)
    if not torch.cuda.is_available():
        raise RuntimeError("DDP Track B training requires CUDA")
    device_ids = _cuda_device_ids(devices) if devices else list(range(torch.cuda.device_count()))
    if not device_ids:
        raise RuntimeError("DDP Track B training requires at least one CUDA device")
    device_index = device_ids[local_rank % len(device_ids)]
    if initialize:
        torch.cuda.set_device(device_index)
    if initialize and not dist.is_initialized():
        dist.init_process_group(backend="nccl", init_method="env://")
    return DdpContext(True, rank, local_rank, world_size, f"cuda:{device_index}", device_index)


def _ddp_barrier(ddp: DdpContext) -> None:
    if ddp.enabled and dist.is_initialized():
        dist.barrier()


def _ddp_mean_float(value: float, device: str, ddp: DdpContext) -> float:
    if not ddp.enabled:
        return float(value)
    tensor = torch.tensor(float(value), dtype=torch.float64, device=device)
    dist.all_reduce(tensor, op=dist.ReduceOp.SUM)
    tensor /= ddp.world_size
    return float(tensor.item())


def _ddp_broadcast_bool(value: bool, device: str, ddp: DdpContext) -> bool:
    if not ddp.enabled:
        return value
    tensor = torch.tensor(1 if value else 0, dtype=torch.int64, device=device)
    dist.broadcast(tensor, src=0)
    return bool(tensor.item())


def _load_torch_payload(path: Path) -> dict[str, Any]:
    try:
        return torch.load(path, map_location="cpu", weights_only=False)
    except TypeError:
        return torch.load(path, map_location="cpu")


def _dataset_cache_manifest(seed: int, train_instances: int, eval_instances: int, l4_instances: int, generation_workers: int, tensorize_workers: int, episode_workers: int) -> dict[str, Any]:
    return {
        "version": "track_b_trm_dataset_cache_v1",
        "seed": seed,
        "train_instances": train_instances,
        "eval_instances": eval_instances,
        "l4_instances": l4_instances,
        "generation_workers": generation_workers,
        "tensorize_workers": tensorize_workers,
        "episode_workers": episode_workers,
    }


def _prepare_dataset_payload(
    cache_path: Path,
    manifest: dict[str, Any],
    seed: int,
    train_instances: int,
    eval_instances: int,
    l4_instances: int,
    generation_workers: int,
    tensorize_workers: int,
    episode_workers: int,
) -> dict[str, Any]:
    if cache_path.exists():
        payload = _load_torch_payload(cache_path)
        if payload.get("manifest") == manifest:
            print(json.dumps({"event": "dataset_cache_hit", "path": str(cache_path)}), flush=True)
            return payload
        print(json.dumps({"event": "dataset_cache_stale", "path": str(cache_path)}), flush=True)
    train_instances_rows, train_examples = _generate_band(1, 2, train_instances, seed, generation_workers)
    eval_instances_rows, eval_examples = _generate_band(1, 2, eval_instances, seed + 1000, generation_workers)
    l4_rows_raw, l4_examples = _generate_band(4, 8, l4_instances, seed + 2000, generation_workers)
    eval_episode_rows = _episode_task_rows_parallel("eval", eval_instances_rows, workers=episode_workers)
    l4_episode_rows = _episode_task_rows_parallel("l4", l4_rows_raw, workers=episode_workers)
    train_rows = _tensorize_token_examples_parallel("train", train_examples, augment_digits=True, seed=seed + 10, workers=tensorize_workers)
    eval_rows = _tensorize_token_examples_parallel("eval", eval_examples, augment_digits=False, seed=seed + 20, workers=tensorize_workers)
    l4_rows = _tensorize_token_examples_parallel("l4", l4_examples, augment_digits=False, seed=seed + 30, workers=tensorize_workers)
    payload = {
        "manifest": manifest,
        "train_instances_rows": train_instances_rows,
        "eval_instances_rows": eval_instances_rows,
        "l4_rows_raw": l4_rows_raw,
        "train_rows": train_rows,
        "eval_rows": eval_rows,
        "l4_rows": l4_rows,
        "eval_episode_rows": eval_episode_rows,
        "l4_episode_rows": l4_episode_rows,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(cache_path.suffix + f".tmp.{os.getpid()}")
    torch.save(payload, tmp_path)
    os.replace(tmp_path, cache_path)
    print(json.dumps({"event": "dataset_cache_write", "path": str(cache_path)}), flush=True)
    return payload


def _shard_size(total: int, world_size: int, rank: int) -> int:
    base = total // world_size
    remainder = total % world_size
    return base + (1 if rank < remainder else 0)


def _dataset_shard_path(cache_root: Path, seed: int, train_instances: int, eval_instances: int, l4_instances: int, world_size: int, rank: int) -> Path:
    return cache_root / f"track_b_trm_seed{seed}_train{train_instances}_eval{eval_instances}_l4{l4_instances}_world{world_size}_rank{rank}.pt"


def _prepare_dataset_shard_payload(
    cache_path: Path,
    manifest: dict[str, Any],
    seed: int,
    train_instances: int,
    eval_instances: int,
    l4_instances: int,
    generation_workers: int,
    tensorize_workers: int,
    episode_workers: int,
    rank: int,
    world_size: int,
) -> dict[str, Any]:
    shard_manifest = {**manifest, "shard_rank": rank, "shard_world_size": world_size}
    if cache_path.exists():
        payload = _load_torch_payload(cache_path)
        if payload.get("manifest") == shard_manifest:
            print(json.dumps({"event": "dataset_shard_cache_hit", "rank": rank, "path": str(cache_path)}), flush=True)
            return payload
        print(json.dumps({"event": "dataset_shard_cache_stale", "rank": rank, "path": str(cache_path)}), flush=True)
    train_count = _shard_size(train_instances, world_size, rank)
    eval_count = _shard_size(eval_instances, world_size, rank)
    l4_count = _shard_size(l4_instances, world_size, rank)
    shard_seed = seed + rank * 1000003
    train_instances_rows, train_examples = _generate_band(1, 2, train_count, shard_seed, generation_workers)
    eval_instances_rows, eval_examples = _generate_band(1, 2, eval_count, seed + 1000 + rank * 1000003, generation_workers)
    l4_rows_raw, l4_examples = _generate_band(4, 8, l4_count, seed + 2000 + rank * 1000003, generation_workers)
    eval_episode_rows = _episode_task_rows_parallel("eval", eval_instances_rows, workers=episode_workers)
    l4_episode_rows = _episode_task_rows_parallel("l4", l4_rows_raw, workers=episode_workers)
    train_rows = _tensorize_token_examples_parallel("train", train_examples, augment_digits=True, seed=seed + 10 + rank * 1000003, workers=tensorize_workers)
    eval_rows = _tensorize_token_examples_parallel("eval", eval_examples, augment_digits=False, seed=seed + 20 + rank * 1000003, workers=tensorize_workers)
    l4_rows = _tensorize_token_examples_parallel("l4", l4_examples, augment_digits=False, seed=seed + 30 + rank * 1000003, workers=tensorize_workers)
    train_positive_cells = float(sum(row.forced_mask.sum().item() for row in train_rows))
    payload = {
        "manifest": shard_manifest,
        "rank": rank,
        "world_size": world_size,
        "train_instances_rows": train_instances_rows,
        "eval_instances_rows": eval_instances_rows,
        "l4_rows_raw": l4_rows_raw,
        "train_rows": train_rows,
        "eval_rows": eval_rows,
        "l4_rows": l4_rows,
        "eval_episode_rows": eval_episode_rows,
        "l4_episode_rows": l4_episode_rows,
        "summary": {
            "train_examples": len(train_rows),
            "eval_examples": len(eval_rows),
            "l4_examples": len(l4_rows),
            "train_positive_cells": train_positive_cells,
            "train_total_cells": float(len(train_rows) * MAX_VARS),
        },
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(cache_path.suffix + f".tmp.{os.getpid()}")
    torch.save(payload, tmp_path)
    os.replace(tmp_path, cache_path)
    print(json.dumps({"event": "dataset_shard_cache_write", "rank": rank, "path": str(cache_path), "train_examples": len(train_rows), "eval_examples": len(eval_rows), "l4_examples": len(l4_rows)}), flush=True)
    return payload


def _wait_for_dataset_shards(paths: list[Path], timeout_s: float = 3600.0) -> None:
    start = time.monotonic()
    while True:
        missing = [str(path) for path in paths if not path.exists()]
        if not missing:
            return
        if time.monotonic() - start > timeout_s:
            raise TimeoutError(f"timed out waiting for dataset shard caches: {missing[:4]}")
        time.sleep(1.0)


def _combine_dataset_shards(paths: list[Path]) -> dict[str, Any]:
    combined: dict[str, Any] = {
        "train_instances_rows": [],
        "eval_instances_rows": [],
        "l4_rows_raw": [],
        "train_rows": [],
        "eval_rows": [],
        "l4_rows": [],
        "eval_episode_rows": [],
        "l4_episode_rows": [],
    }
    for path in paths:
        payload = _load_torch_payload(path)
        for key in combined:
            combined[key].extend(payload[key])
    return combined


def _forced_mask_pos_weight_distributed(rows: list[TensorExample], device: str, override: float | None, ddp: DdpContext) -> tuple[torch.Tensor, dict[str, float | str]]:
    positives = float(sum(row.forced_mask.sum().item() for row in rows))
    total = float(len(rows) * MAX_VARS)
    counts = torch.tensor([positives, total], dtype=torch.float64, device=device)
    if ddp.enabled:
        dist.all_reduce(counts, op=dist.ReduceOp.SUM)
    positives = float(counts[0].item())
    total = float(counts[1].item())
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


def _gpu_resident_dataset(rows: list[TensorExample], device: str) -> GpuResidentDataset:
    if not rows:
        raise ValueError("cannot build GPU-resident dataset from empty rows")
    return GpuResidentDataset(
        x=torch.stack([row.x for row in rows]).to(device),
        action=torch.tensor([row.action for row in rows], dtype=torch.long, device=device),
        var=torch.tensor([row.var for row in rows], dtype=torch.long, device=device),
        val=torch.tensor([row.val for row in rows], dtype=torch.long, device=device),
        forced_mask=torch.stack([row.forced_mask for row in rows]).to(device),
    )


def _batch_gpu_resident(dataset: GpuResidentDataset, batch_size: int, seed: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    generator = torch.Generator().manual_seed(seed)
    indices = torch.randint(0, dataset.x.shape[0], (batch_size,), generator=generator).to(dataset.x.device)
    return (
        dataset.x.index_select(0, indices),
        dataset.action.index_select(0, indices),
        dataset.var.index_select(0, indices),
        dataset.val.index_select(0, indices),
        dataset.forced_mask.index_select(0, indices),
    )


def _autocast_context(device: str, amp_bf16: bool):
    if amp_bf16 and device.startswith("cuda"):
        return torch.autocast(device_type="cuda", dtype=torch.bfloat16)
    return nullcontext()


def _gpu_indices_for_progress(device: str, device_ids: list[int]) -> list[int]:
    if device_ids:
        return device_ids
    match = re.search(r"cuda:(\d+)", device)
    return [int(match.group(1))] if match else []


def _gpu_utilization_snapshot(gpu_indices: list[int]) -> dict[str, Any]:
    if not gpu_indices:
        return {"n_gpus": 0, "mean_utilization_gpu_percent": 0.0, "per_gpu": {}}
    command = [
        "nvidia-smi",
        f"--id={','.join(str(index) for index in gpu_indices)}",
        "--query-gpu=index,utilization.gpu,memory.used",
        "--format=csv,noheader,nounits",
    ]
    try:
        output = subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL, timeout=5.0)
    except (OSError, subprocess.SubprocessError):
        return {"n_gpus": len(gpu_indices), "mean_utilization_gpu_percent": 0.0, "per_gpu": {}, "error": "nvidia_smi_unavailable"}
    per_gpu = {}
    utilizations = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3:
            continue
        try:
            gpu_index = int(parts[0])
            utilization = float(parts[1])
            memory_used = float(parts[2])
        except ValueError:
            continue
        per_gpu[str(gpu_index)] = {"utilization_gpu_percent": utilization, "memory_used_mib": memory_used}
        utilizations.append(utilization)
    return {
        "n_gpus": len(per_gpu),
        "mean_utilization_gpu_percent": sum(utilizations) / max(len(utilizations), 1),
        "per_gpu": per_gpu,
    }


def train_trm_operator(
    output_dir: str = "results/trm_operator_smoke",
    seed: int = 102,
    device: str = "cuda:0",
    train_instances: int = 1024,
    eval_instances: int = 256,
    l4_instances: int = 64,
    steps: int = 1000,
    batch_size: int = 128,
    hidden_dim: int = 384,
    nhead: int = 6,
    feedforward_dim: int = 1536,
    recurrence_steps: int = 6,
    lr: float = 3e-4,
    devices: str = "",
    generation_workers: int = 1,
    tensorize_workers: int = 1,
    episode_workers: int = 1,
    eval_every: int = 0,
    forced_loss: str = "focal",
    forced_pos_weight: float = -1.0,
    focal_gamma: float = 2.0,
    min_steps: int = 0,
    fuse_step: int = 100,
    fuse_min_loss_drop: float = 0.01,
    gpu_resident_batches: bool = False,
    amp_bf16: bool = False,
    torch_compile: bool = False,
    require_param_min: int = 0,
    require_param_max: int = 0,
    dataset_cache_dir: str = "",
    progress_eval_episodes: int = -1,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(seed)
    ddp = _init_ddp_if_needed(device, devices, initialize=False)
    is_main = ddp.rank == 0
    device_ids = _cuda_device_ids(devices) if devices else []
    if device.startswith("cuda") and not torch.cuda.is_available():
        device = "cpu"
        device_ids = []
    if not ddp.enabled and device_ids:
        device = f"cuda:{device_ids[0]}"
    manifest = _dataset_cache_manifest(seed, train_instances, eval_instances, l4_instances, generation_workers, tensorize_workers, episode_workers)
    cache_root = Path(dataset_cache_dir) if dataset_cache_dir else out / "dataset_cache"
    if ddp.enabled:
        shard_paths = [_dataset_shard_path(cache_root, seed, train_instances, eval_instances, l4_instances, ddp.world_size, rank) for rank in range(ddp.world_size)]
        cache_path = cache_root / f"track_b_trm_seed{seed}_train{train_instances}_eval{eval_instances}_l4{l4_instances}_world{ddp.world_size}.sharded"
        dataset_payload = _prepare_dataset_shard_payload(shard_paths[ddp.rank], manifest, seed, train_instances, eval_instances, l4_instances, generation_workers, tensorize_workers, episode_workers, ddp.rank, ddp.world_size)
        _wait_for_dataset_shards(shard_paths)
        ddp = _init_ddp_if_needed(device, devices, initialize=True)
        is_main = ddp.rank == 0
        device = ddp.device
    else:
        shard_paths = []
        cache_path = cache_root / f"track_b_trm_seed{seed}_train{train_instances}_eval{eval_instances}_l4{l4_instances}.pt"
        dataset_payload = _prepare_dataset_payload(cache_path, manifest, seed, train_instances, eval_instances, l4_instances, generation_workers, tensorize_workers, episode_workers)
    train_instances_rows = dataset_payload["train_instances_rows"]
    eval_instances_rows = dataset_payload["eval_instances_rows"]
    l4_rows_raw = dataset_payload["l4_rows_raw"]
    train_rows = dataset_payload["train_rows"]
    eval_rows = dataset_payload["eval_rows"]
    l4_rows = dataset_payload["l4_rows"]
    eval_episode_tasks = [_episode_eval_task(row) for row in dataset_payload["eval_episode_rows"]]
    l4_episode_tasks = [_episode_eval_task(row) for row in dataset_payload["l4_episode_rows"]]
    config = TrackBConfig(hidden_dim=hidden_dim, nhead=nhead, feedforward_dim=feedforward_dim, recurrence_steps=recurrence_steps, dropout=0.0)
    model: torch.nn.Module = PerCellTokenRecurrentOperator(config).to(device)
    parameter_count = _parameter_count(model)
    if require_param_min > 0 and parameter_count < require_param_min:
        raise ValueError(f"parameter_count={parameter_count} below required minimum {require_param_min}")
    if require_param_max > 0 and parameter_count > require_param_max:
        raise ValueError(f"parameter_count={parameter_count} above required maximum {require_param_max}")
    if torch_compile and len(device_ids) > 1 and not ddp.enabled:
        raise ValueError("--torch-compile is only supported for single-GPU or torchrun-DDP Track B retry runs")
    if torch_compile:
        model = torch.compile(model)
    if ddp.enabled:
        model = DistributedDataParallel(model, device_ids=[ddp.device_index], output_device=ddp.device_index, broadcast_buffers=False)
    elif len(device_ids) > 1:
        model = torch.nn.DataParallel(model, device_ids=device_ids)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    if ddp.enabled:
        pos_weight_tensor, pos_weight_record = _forced_mask_pos_weight_distributed(train_rows, device, None if forced_pos_weight < 0 else forced_pos_weight, ddp)
    else:
        pos_weight_tensor, pos_weight_record = _forced_mask_pos_weight(train_rows, device, None if forced_pos_weight < 0 else forced_pos_weight)
    ema_state = {key: value.detach().clone() for key, value in _base_trm_model(model).state_dict().items()}
    ema_decay = 0.995
    train_dataset = _gpu_resident_dataset(train_rows, device) if gpu_resident_batches else None
    progress_path = out / "progress.jsonl"
    if is_main:
        progress_path.write_text("", encoding="utf-8")
    history: list[dict[str, Any]] = []
    eval_interval = eval_every if eval_every > 0 else max(1, steps // 10)
    progress_gpu_indices = device_ids if ddp.enabled and device_ids else (list(range(ddp.world_size)) if ddp.enabled else _gpu_indices_for_progress(device, device_ids))
    last_progress_time = time.perf_counter()
    last_progress_step = 0
    initial_forced_loss = None
    completed_step = 0
    train_status = "G1_NOT_MET"
    fuse = {"enabled": fuse_step > 0, "step": fuse_step, "min_loss_drop": fuse_min_loss_drop, "status": "NOT_REACHED" if fuse_step > 0 else "DISABLED"}
    per_rank_batch_size = max(1, batch_size // ddp.world_size) if ddp.enabled else batch_size
    effective_batch_size = per_rank_batch_size * ddp.world_size

    def append_progress(row: dict[str, Any]) -> None:
        if not is_main:
            return
        with progress_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    for step in range(1, steps + 1):
        completed_step = step
        model.train()
        if train_dataset is not None:
            x, action, var, val, forced_mask = _batch_gpu_resident(train_dataset, per_rank_batch_size, seed * 100000 + step * ddp.world_size + ddp.rank)
        else:
            x, action, var, val, forced_mask = _batch(train_rows, per_rank_batch_size, device, seed * 100000 + step * ddp.world_size + ddp.rank)
        with _autocast_context(device, amp_bf16):
            outputs = model(x)
            loss, forced_loss_value = _loss(outputs, action, var, val, forced_mask, pos_weight_tensor, forced_loss, focal_gamma)
        local_loss_value = float(loss.detach().item())
        local_forced_loss_value = forced_loss_value
        if initial_forced_loss is None:
            initial_forced_loss = _ddp_mean_float(local_forced_loss_value, device, ddp)
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        with torch.no_grad():
            for key, value in _base_trm_model(model).state_dict().items():
                ema_state[key].mul_(ema_decay).add_(value.detach(), alpha=1.0 - ema_decay)
        if fuse_step > 0 and step == fuse_step and initial_forced_loss is not None:
            forced_loss_value = _ddp_mean_float(local_forced_loss_value, device, ddp)
            required = initial_forced_loss * (1.0 - fuse_min_loss_drop)
            fuse.update({"initial_forced_loss": initial_forced_loss, "forced_loss_at_fuse": forced_loss_value, "required_below": required})
            if forced_loss_value >= required:
                fuse["status"] = "FUSE_BLOWN_WIRING_BUG"
                train_status = "FUSE_BLOWN_WIRING_BUG"
                row = {"event": "trm_operator_fuse_blown", "step": step, **fuse}
                append_progress(row)
                if is_main:
                    print(json.dumps(row), flush=True)
                break
            fuse["status"] = "PASS"
        if step == 1 or step == steps or step % eval_interval == 0:
            loss_value = _ddp_mean_float(local_loss_value, device, ddp)
            forced_loss_value = _ddp_mean_float(local_forced_loss_value, device, ddp)
            should_stop = False
            if is_main:
                progress_now = time.perf_counter()
                progress_elapsed = max(progress_now - last_progress_time, 1e-9)
                progress_steps = step - last_progress_step
                gpu_util_snapshot = _gpu_utilization_snapshot(progress_gpu_indices)
                quick_sample = eval_rows[: min(len(eval_rows), 256)]
                eval_model = _base_trm_model(model)
                quick_tau = _calibrate_tau(eval_model, quick_sample, device)
                quick_forced = _forced_single_step_metrics_token(eval_model, quick_sample, device, quick_tau["selected_tau"])
                if progress_eval_episodes == 0:
                    g1_quick = {"fixpoint_reach_rate": None, "n_episodes": 0}
                    g2_quick = {"solve_rate": None, "n_episodes": 0}
                else:
                    n_eval_tasks = len(eval_episode_tasks) if progress_eval_episodes < 0 else min(len(eval_episode_tasks), progress_eval_episodes)
                    n_l4_tasks = len(l4_episode_tasks) if progress_eval_episodes < 0 else min(len(l4_episode_tasks), progress_eval_episodes)
                    g1_quick = _evaluate_forced_episodes_token(eval_model, eval_episode_tasks[:n_eval_tasks], device, quick_tau["selected_tau"])
                    g2_quick = _evaluate_forced_episodes_token(eval_model, l4_episode_tasks[:n_l4_tasks], device, quick_tau["selected_tau"])
                row = {
                    "event": "trm_operator_train",
                    "step": step,
                    "steps": steps,
                    "loss": loss_value,
                    "forced_mask_loss": forced_loss_value,
                    "forced_precision": quick_forced["forced_precision"],
                    "forced_recall": quick_forced["forced_recall"],
                    "G1_forced_fixpoint": g1_quick["fixpoint_reach_rate"],
                    "G2_forced_l4_solve": g2_quick["solve_rate"],
                    "progress_eval_episodes": progress_eval_episodes,
                    "tau": quick_tau["selected_tau"],
                    "steps_per_sec": progress_steps / progress_elapsed,
                    "examples_per_sec": (progress_steps * effective_batch_size) / progress_elapsed,
                    "gpu_util": gpu_util_snapshot["mean_utilization_gpu_percent"],
                    "gpu_util_snapshot": gpu_util_snapshot,
                }
                last_progress_time = progress_now
                last_progress_step = step
                history.append({key: value for key, value in row.items() if key != "event"})
                append_progress(row)
                print(json.dumps(row), flush=True)
                if step >= min_steps and g1_quick["fixpoint_reach_rate"] is not None and g2_quick["solve_rate"] is not None and g1_quick["fixpoint_reach_rate"] >= 0.95 and g2_quick["solve_rate"] <= 0.05:
                    train_status = "G1_PASS_EARLY_STOP"
                    should_stop = True
            should_stop = _ddp_broadcast_bool(should_stop, device, ddp)
            if should_stop:
                break
    if ddp.enabled and not is_main:
        _ddp_barrier(ddp)
        if dist.is_initialized():
            dist.destroy_process_group()
        return {"module": "train_trm_operator", "status": "DDP_WORKER_COMPLETE", "rank": ddp.rank, "world_size": ddp.world_size, "completed_step": completed_step}
    if ddp.enabled and is_main:
        combined_payload = _combine_dataset_shards(shard_paths)
        train_instances_rows = combined_payload["train_instances_rows"]
        eval_instances_rows = combined_payload["eval_instances_rows"]
        l4_rows_raw = combined_payload["l4_rows_raw"]
        train_rows = combined_payload["train_rows"]
        eval_rows = combined_payload["eval_rows"]
        l4_rows = combined_payload["l4_rows"]
        eval_episode_tasks = [_episode_eval_task(row) for row in combined_payload["eval_episode_rows"]]
        l4_episode_tasks = [_episode_eval_task(row) for row in combined_payload["l4_episode_rows"]]
    checkpoint_path = out / f"trm_operator_seed{seed}.pt"
    run_devices = [f"cuda:{index}" for index in device_ids] if device_ids else ([f"cuda:{index}" for index in range(ddp.world_size)] if ddp.enabled else [device])
    torch.save({
        "model_class": "PerCellTokenRecurrentOperator",
        "operator_type": "learned_recurrent",
        "architecture_class": "trm_per_cell_tokens",
        "state_dict": _base_trm_model(model).state_dict(),
        "ema_state_dict": ema_state,
        "config": {**config.__dict__, "token_feature_dim": TOKEN_FEATURE_DIM, "seed": seed, "devices": run_devices, "distributed": ddp.enabled, "world_size": ddp.world_size},
    }, checkpoint_path)
    eval_model = _base_trm_model(model)
    tau_calibration = _calibrate_tau(eval_model, eval_rows, device)
    tau = tau_calibration["selected_tau"]
    forced_single_step = _forced_single_step_metrics_token(eval_model, eval_rows, device, tau)
    g1_forced = _evaluate_forced_episodes_token(eval_model, eval_episode_tasks, device, tau)
    g2_forced = _evaluate_forced_episodes_token(eval_model, l4_episode_tasks, device, tau)
    legacy_g1 = _evaluate(eval_model, eval_rows, device)
    legacy_g2 = _evaluate(eval_model, l4_rows, device)
    passed = g1_forced["fixpoint_reach_rate"] >= 0.95 and g2_forced["solve_rate"] <= 0.05 and train_status != "FUSE_BLOWN_WIRING_BUG"
    if passed and train_status != "G1_PASS_EARLY_STOP":
        train_status = "G1_PASS"
    elif train_status not in {"FUSE_BLOWN_WIRING_BUG", "G1_PASS_EARLY_STOP"}:
        train_status = "GATES_UNREACHED" if steps >= 20000 else "G1_NOT_MET"
    payload = {
        "module": "train_trm_operator",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "operator_type": "learned_recurrent",
        "architecture_class": "trm_per_cell_tokens",
        "source": "track_b_trm_class_training_run",
        "status": train_status,
        "seed": seed,
        "device": device,
        "devices": run_devices,
        "checkpoint": str(checkpoint_path),
        "parameter_count": parameter_count,
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
            "per_cell_tokens": True,
            "token_features": ["candidate_set_bitmask", "given_flag", "row_id", "col_id", "box_id"],
            "weight_tied_transformer": True,
            "trm_class": True,
            "per_recurrence_deep_supervision": True,
            "ema_recorded": True,
            "digit_augmentation": True,
            "trained_on_depths": "L1-L2_only",
            "forced_only_commit_semantics": True,
            "commit_function": "experiments.train_recurrent_operator.forced_only_commit_decision",
            "forced_loss": forced_loss,
            "forced_pos_weight": pos_weight_record,
            "focal_gamma": focal_gamma,
            "fuse": fuse,
            "gpu_resident_batches": gpu_resident_batches,
            "amp_bf16": amp_bf16,
            "torch_compile": torch_compile,
            "distributed_data_parallel": ddp.enabled,
            "dataset_cache": str(cache_path),
            "progress_eval_episodes": progress_eval_episodes,
            "parameter_count_gate": {"min": require_param_min, "max": require_param_max, "parameter_count": parameter_count, "passed": (require_param_min <= 0 or parameter_count >= require_param_min) and (require_param_max <= 0 or parameter_count <= require_param_max)},
            "red_lines": ["no_trm_checkpoint", "no_sudoku_extreme", "repo_local_l1_l2_banded_only"],
        },
        "training_curve_summary": {"history": history, "steps": steps, "completed_step": completed_step, "batch_size": effective_batch_size, "per_rank_batch_size": per_rank_batch_size, "lr": lr, "data_parallel_devices": [] if ddp.enabled else [f"cuda:{index}" for index in device_ids], "distributed_data_parallel_devices": run_devices if ddp.enabled else [], "world_size": ddp.world_size, "generation_workers": generation_workers, "tensorize_workers": tensorize_workers, "episode_workers": episode_workers, "progress_jsonl": str(progress_path), "min_steps": min_steps, "eval_every": eval_interval, "progress_eval_episodes": progress_eval_episodes, "gpu_resident_batches": gpu_resident_batches, "amp_bf16": amp_bf16, "torch_compile": torch_compile},
        "G1": g1_forced["fixpoint_reach_rate"],
        "G2": g2_forced["solve_rate"],
        "legacy_single_step_joint": {"G1_joint_accuracy": legacy_g1["joint_accuracy"], "G2_joint_accuracy": legacy_g2["joint_accuracy"], "note": "legacy diagnostic only; acceptance uses forced-only episode semantics"},
        "forced_only": {
            "tau_calibration": tau_calibration,
            "forced_threshold": 0.5,
            "single_step_forced_precision": forced_single_step["forced_precision"],
            "single_step_forced_recall": forced_single_step["forced_recall"],
            "per_step_forced_precision_recall_by_depth": forced_single_step["by_depth_into_solution"],
            "G1_forced_fixpoint": g1_forced,
            "G2_forced_l4": g2_forced,
        },
        "acceptance": {
            "operator_type": "learned_recurrent",
            "architecture_class": "trm_per_cell_tokens",
            "G1_threshold": 0.95,
            "G1_pass": passed,
            "leading_indicator_success": forced_single_step["forced_precision"] >= 0.95 and forced_single_step["forced_recall"] >= 0.95,
            "autonomous_stage_a_run": False,
            "stage_a_autonomous_cells": 0,
        },
        "honesty": {
            "does_not_establish": "Track B acceptance is per-seed learned-operator evidence only. It does not become Stage A evidence unless a later run consumes the checkpoint and reports operator=learned_recurrent autonomous cells side by side with Track A.",
        },
    }
    (out / "acceptance.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    _ddp_barrier(ddp)
    if ddp.enabled and dist.is_initialized():
        dist.destroy_process_group()
    return payload


@torch.no_grad()
def _forced_single_step_metrics_token(model: torch.nn.Module, rows: list[TensorExample], device: str, tau: float, batch_size: int = 512) -> dict[str, Any]:
    from experiments.train_recurrent_operator import _forced_single_step_metrics

    return _forced_single_step_metrics(model, rows, device, tau, batch_size)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Track B TRM-class per-cell-token operator.")
    parser.add_argument("--output-dir", default="results/trm_operator_smoke")
    parser.add_argument("--seed", type=int, default=102)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--train-instances", type=int, default=1024)
    parser.add_argument("--eval-instances", type=int, default=256)
    parser.add_argument("--l4-instances", type=int, default=64)
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--hidden-dim", type=int, default=384)
    parser.add_argument("--nhead", type=int, default=6)
    parser.add_argument("--feedforward-dim", type=int, default=1536)
    parser.add_argument("--recurrence-steps", type=int, default=6)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--devices", default="")
    parser.add_argument("--generation-workers", type=int, default=1)
    parser.add_argument("--tensorize-workers", type=int, default=1)
    parser.add_argument("--episode-workers", type=int, default=1)
    parser.add_argument("--eval-every", type=int, default=0)
    parser.add_argument("--forced-loss", choices=["bce", "focal"], default="focal")
    parser.add_argument("--forced-pos-weight", type=float, default=-1.0)
    parser.add_argument("--focal-gamma", type=float, default=2.0)
    parser.add_argument("--min-steps", type=int, default=0)
    parser.add_argument("--fuse-step", type=int, default=100)
    parser.add_argument("--fuse-min-loss-drop", type=float, default=0.01)
    parser.add_argument("--gpu-resident-batches", action="store_true")
    parser.add_argument("--amp-bf16", action="store_true")
    parser.add_argument("--torch-compile", action="store_true")
    parser.add_argument("--require-param-min", type=int, default=0)
    parser.add_argument("--require-param-max", type=int, default=0)
    parser.add_argument("--dataset-cache-dir", default="")
    parser.add_argument("--progress-eval-episodes", type=int, default=-1, help="Progress rollout episodes per G1/G2 band; -1=all, 0=skip rollout during training, final acceptance remains full.")
    args = parser.parse_args()
    train_trm_operator(
        output_dir=args.output_dir,
        seed=args.seed,
        device=args.device,
        train_instances=args.train_instances,
        eval_instances=args.eval_instances,
        l4_instances=args.l4_instances,
        steps=args.steps,
        batch_size=args.batch_size,
        hidden_dim=args.hidden_dim,
        nhead=args.nhead,
        feedforward_dim=args.feedforward_dim,
        recurrence_steps=args.recurrence_steps,
        lr=args.lr,
        devices=args.devices,
        generation_workers=args.generation_workers,
        tensorize_workers=args.tensorize_workers,
        episode_workers=args.episode_workers,
        eval_every=args.eval_every,
        forced_loss=args.forced_loss,
        forced_pos_weight=args.forced_pos_weight,
        focal_gamma=args.focal_gamma,
        min_steps=args.min_steps,
        fuse_step=args.fuse_step,
        fuse_min_loss_drop=args.fuse_min_loss_drop,
        gpu_resident_batches=args.gpu_resident_batches,
        amp_bf16=args.amp_bf16,
        torch_compile=args.torch_compile,
        require_param_min=args.require_param_min,
        require_param_max=args.require_param_max,
        dataset_cache_dir=args.dataset_cache_dir,
        progress_eval_episodes=args.progress_eval_episodes,
    )


if __name__ == "__main__":
    main()
