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
from tasks.sudoku.generator_6x6 import Sudoku6x6Instance, generate_6x6_by_depth_band
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
    depth: int
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
        self.dead_head = torch.nn.Linear(hidden_dim, 1)

    def forward(self, x: torch.Tensor) -> dict[str, list[torch.Tensor]]:
        h = torch.tanh(self.in_proj(x))
        outputs = {"action": [], "var": [], "val": [], "dead": []}
        for _ in range(self.recurrence_steps):
            h = self.cell(x, h)
            outputs["action"].append(self.action_head(h))
            outputs["var"].append(self.var_head(h))
            outputs["val"].append(self.val_head(h))
            outputs["dead"].append(self.dead_head(h))
        return outputs


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
    tensor = torch.zeros(INPUT_DIM, dtype=torch.float32)
    assignment = _givens_to_assignment(example)
    for var in range(MAX_VARS):
        value = int(assignment.get(var, 0))
        if digit_map and value:
            value = digit_map[value]
        tensor[var * 7 + value] = 1.0
    return tensor


def _tensorize(examples: list[TrainingExample], augment_digits: bool, seed: int) -> list[TensorExample]:
    generator = torch.Generator().manual_seed(seed)
    out = []
    for example in examples:
        digit_map = None
        if augment_digits:
            perm = torch.randperm(MAX_VALS, generator=generator).tolist()
            digit_map = {index + 1: perm[index] + 1 for index in range(MAX_VALS)}
        action = ACTION_TO_ID[example.target_action]
        target_var = -100 if example.target_var is None or example.target_var >= MAX_VARS else int(example.target_var)
        target_val = -100 if example.target_val is None else int(example.target_val) - 1
        if digit_map and target_val >= 0:
            target_val = digit_map[target_val + 1] - 1
        out.append(TensorExample(_encode_assignment(example, digit_map), action, target_var, target_val, int(example.depth), int(example.dpll_backtrack_depth)))
    return out


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
    return x, action, var, val


def _loss(outputs: dict[str, list[torch.Tensor]], action: torch.Tensor, var: torch.Tensor, val: torch.Tensor) -> torch.Tensor:
    losses = []
    for action_logits, var_logits, val_logits in zip(outputs["action"], outputs["var"], outputs["val"]):
        step_loss = F.cross_entropy(action_logits, action)
        var_mask = var >= 0
        val_mask = val >= 0
        if var_mask.any():
            step_loss = step_loss + F.cross_entropy(var_logits[var_mask], var[var_mask])
        if val_mask.any():
            step_loss = step_loss + F.cross_entropy(val_logits[val_mask], val[val_mask])
        losses.append(step_loss)
    return sum(losses) / len(losses)


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
        pred_val = outputs["val"][-1].argmax(dim=-1)
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
    model: torch.nn.Module = WeightTiedRecurrentOperator(hidden_dim=hidden_dim, recurrence_steps=recurrence_steps).to(device)
    if len(device_ids) > 1:
        model = torch.nn.DataParallel(model, device_ids=device_ids)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    ema_state = {key: value.detach().clone() for key, value in _base_model(model).state_dict().items()}
    ema_decay = 0.995
    history = []
    for step in range(1, steps + 1):
        model.train()
        x, action, var, val = _batch(train_rows, batch_size, device, seed * 100000 + step)
        outputs = model(x)
        loss = _loss(outputs, action, var, val)
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        with torch.no_grad():
            for key, value in _base_model(model).state_dict().items():
                ema_state[key].mul_(ema_decay).add_(value.detach(), alpha=1.0 - ema_decay)
        if step == 1 or step == steps or step % max(1, steps // 10) == 0:
            eval_metrics = _evaluate(model, eval_rows[: min(len(eval_rows), 2048)], device)
            history.append({"step": step, "loss": float(loss.detach().item()), "eval_joint_accuracy": eval_metrics["joint_accuracy"]})
            print(json.dumps({"event": "recurrent_operator_train", "step": step, "steps": steps, "loss": float(loss.detach().item()), "eval_joint_accuracy": eval_metrics["joint_accuracy"]}), flush=True)
    checkpoint_path = out / f"learned_recurrent_operator_seed{seed}.pt"
    torch.save({
        "model_class": "WeightTiedRecurrentOperator",
        "operator_type": "learned_recurrent",
        "state_dict": _base_model(model).state_dict(),
        "ema_state_dict": ema_state,
        "config": {"input_dim": INPUT_DIM, "hidden_dim": hidden_dim, "recurrence_steps": recurrence_steps, "max_vars": MAX_VARS, "max_vals": MAX_VALS, "seed": seed, "devices": device_ids},
    }, checkpoint_path)
    g1 = _evaluate(model, eval_rows, device)
    g2 = _evaluate(model, l4_rows, device)
    g3 = {
        "n_instances": len(sudoku9_probe),
        "depth_histogram": {str(depth): count for depth, count in sorted(Counter(row.dpll_backtrack_depth for row in sudoku9_probe).items())},
        "status": "generated_for_external_anchor" if sudoku9_probe else "empty_or_too_hard_for_current_generator_budget",
    }
    passed = g1["joint_accuracy"] >= 0.95
    payload = {
        "module": "train_recurrent_operator",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "operator_type": "learned_recurrent",
        "source": "learned_recurrent_training_run",
        "status": "G1_PASS" if passed else "G1_NOT_MET",
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
        },
        "training_curve_summary": {"history": history, "steps": steps, "batch_size": batch_size, "lr": lr, "data_parallel_devices": [f"cuda:{index}" for index in device_ids], "generation_workers": generation_workers},
        "G1": g1["joint_accuracy"],
        "G2": g2["joint_accuracy"],
        "G3": g3,
        "acceptance": {
            "operator_type": "learned_recurrent",
            "G1_threshold": 0.95,
            "G1_pass": passed,
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
    args = parser.parse_args()
    train_recurrent_operator(args.output_dir, args.seed, args.device, args.train_instances, args.eval_instances, args.l4_instances, args.steps, args.batch_size, args.hidden_dim, args.recurrence_steps, args.lr, args.devices, args.generation_workers)