"""Train Track B learned operator with per-cell tokens and tied transformer recurrence."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import torch

from experiments.train_recurrent_operator import (
    ACTION_TO_ID,
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
from llm_operator.symbolic_filter import CSPTask, forced_moves, status as csp_status, valid_values
from tasks.oracle.trace_generator import TrainingExample

TOKEN_FEATURE_DIM = MAX_VALS + 1 + 6 + 6 + 6


@dataclass
class TrackBConfig:
    hidden_dim: int
    nhead: int
    feedforward_dim: int
    recurrence_steps: int
    dropout: float


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
    eval_every: int = 0,
    forced_loss: str = "focal",
    forced_pos_weight: float = -1.0,
    focal_gamma: float = 2.0,
    min_steps: int = 0,
    fuse_step: int = 100,
    fuse_min_loss_drop: float = 0.01,
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
    from experiments.train_recurrent_operator import _episode_tasks

    eval_episode_tasks = _episode_tasks(eval_instances_rows)
    l4_episode_tasks = _episode_tasks(l4_rows_raw)
    train_rows = _tensorize_token_examples(train_examples, augment_digits=True, seed=seed + 10)
    eval_rows = _tensorize_token_examples(eval_examples, augment_digits=False, seed=seed + 20)
    l4_rows = _tensorize_token_examples(l4_examples, augment_digits=False, seed=seed + 30)
    config = TrackBConfig(hidden_dim=hidden_dim, nhead=nhead, feedforward_dim=feedforward_dim, recurrence_steps=recurrence_steps, dropout=0.0)
    model: torch.nn.Module = PerCellTokenRecurrentOperator(config).to(device)
    parameter_count = _parameter_count(model)
    if len(device_ids) > 1:
        model = torch.nn.DataParallel(model, device_ids=device_ids)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    pos_weight_tensor, pos_weight_record = _forced_mask_pos_weight(train_rows, device, None if forced_pos_weight < 0 else forced_pos_weight)
    ema_state = {key: value.detach().clone() for key, value in _base_model(model).state_dict().items()}
    ema_decay = 0.995
    progress_path = out / "progress.jsonl"
    progress_path.write_text("", encoding="utf-8")
    history: list[dict[str, Any]] = []
    eval_interval = eval_every if eval_every > 0 else max(1, steps // 10)
    initial_forced_loss = None
    completed_step = 0
    train_status = "G1_NOT_MET"
    fuse = {"enabled": fuse_step > 0, "step": fuse_step, "min_loss_drop": fuse_min_loss_drop, "status": "NOT_REACHED" if fuse_step > 0 else "DISABLED"}

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
        with torch.no_grad():
            for key, value in _base_model(model).state_dict().items():
                ema_state[key].mul_(ema_decay).add_(value.detach(), alpha=1.0 - ema_decay)
        if fuse_step > 0 and step == fuse_step and initial_forced_loss is not None:
            required = initial_forced_loss * (1.0 - fuse_min_loss_drop)
            fuse.update({"initial_forced_loss": initial_forced_loss, "forced_loss_at_fuse": forced_loss_value, "required_below": required})
            if forced_loss_value >= required:
                fuse["status"] = "FUSE_BLOWN_WIRING_BUG"
                train_status = "FUSE_BLOWN_WIRING_BUG"
                row = {"event": "trm_operator_fuse_blown", "step": step, **fuse}
                append_progress(row)
                print(json.dumps(row), flush=True)
                break
            fuse["status"] = "PASS"
        if step == 1 or step == steps or step % eval_interval == 0:
            quick_sample = eval_rows[: min(len(eval_rows), 256)]
            quick_tau = _calibrate_tau(model, quick_sample, device)
            quick_forced = _forced_single_step_metrics_token(model, quick_sample, device, quick_tau["selected_tau"])
            g1_quick = _evaluate_forced_episodes_token(model, eval_episode_tasks, device, quick_tau["selected_tau"])
            g2_quick = _evaluate_forced_episodes_token(model, l4_episode_tasks, device, quick_tau["selected_tau"])
            row = {
                "event": "trm_operator_train",
                "step": step,
                "steps": steps,
                "loss": float(loss.detach().item()),
                "forced_mask_loss": forced_loss_value,
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
    checkpoint_path = out / f"trm_operator_seed{seed}.pt"
    torch.save({
        "model_class": "PerCellTokenRecurrentOperator",
        "operator_type": "learned_recurrent",
        "architecture_class": "trm_per_cell_tokens",
        "state_dict": _base_model(model).state_dict(),
        "ema_state_dict": ema_state,
        "config": {**config.__dict__, "token_feature_dim": TOKEN_FEATURE_DIM, "seed": seed, "devices": device_ids},
    }, checkpoint_path)
    tau_calibration = _calibrate_tau(model, eval_rows, device)
    tau = tau_calibration["selected_tau"]
    forced_single_step = _forced_single_step_metrics_token(model, eval_rows, device, tau)
    g1_forced = _evaluate_forced_episodes_token(model, eval_episode_tasks, device, tau)
    g2_forced = _evaluate_forced_episodes_token(model, l4_episode_tasks, device, tau)
    legacy_g1 = _evaluate(model, eval_rows, device)
    legacy_g2 = _evaluate(model, l4_rows, device)
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
        "devices": [f"cuda:{index}" for index in device_ids] if device_ids else [device],
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
            "red_lines": ["no_trm_checkpoint", "no_sudoku_extreme", "repo_local_l1_l2_banded_only"],
        },
        "training_curve_summary": {"history": history, "steps": steps, "completed_step": completed_step, "batch_size": batch_size, "lr": lr, "data_parallel_devices": [f"cuda:{index}" for index in device_ids], "generation_workers": generation_workers, "progress_jsonl": str(progress_path), "min_steps": min_steps, "eval_every": eval_interval},
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
    parser.add_argument("--eval-every", type=int, default=0)
    parser.add_argument("--forced-loss", choices=["bce", "focal"], default="focal")
    parser.add_argument("--forced-pos-weight", type=float, default=-1.0)
    parser.add_argument("--focal-gamma", type=float, default=2.0)
    parser.add_argument("--min-steps", type=int, default=0)
    parser.add_argument("--fuse-step", type=int, default=100)
    parser.add_argument("--fuse-min-loss-drop", type=float, default=0.01)
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
        eval_every=args.eval_every,
        forced_loss=args.forced_loss,
        forced_pos_weight=args.forced_pos_weight,
        focal_gamma=args.focal_gamma,
        min_steps=args.min_steps,
        fuse_step=args.fuse_step,
        fuse_min_loss_drop=args.fuse_min_loss_drop,
    )


if __name__ == "__main__":
    main()
