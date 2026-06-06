"""Reconstruct Stage A parent artifacts inside this repository.

The original parent recurrent-depth artifacts are not present in this workspace.
This script produces explicit reconstructed replacements, records their
provenance in a manifest, and keeps the artifact contract stable for Stage A:

- recurrent_solver_b1a_clean_l2_tied_p96_e300_seed102.pt
- internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl
- item142_factored_cell_digit_decoder_depth8_D128.pt
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch

from llm_operator.symbolic_filter import CSPTask, build_tasks, valid_values
from tasks.oracle.dpll_oracle import TraceAction
from tasks.oracle.trace_generator import trace_to_examples


OPERATOR_NAME = "recurrent_solver_b1a_clean_l2_tied_p96_e300_seed102.pt"
TRACE_NAME = "internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl"
DECODER_NAME = "item142_factored_cell_digit_decoder_depth8_D128.pt"


class ReconstructedRecurrentSolver(torch.nn.Module):
    def __init__(self, hidden_dim: int = 96, layers: int = 2):
        super().__init__()
        self.embedding = torch.nn.Embedding(5, hidden_dim)
        self.gru = torch.nn.GRU(hidden_dim, hidden_dim, num_layers=layers, batch_first=True)
        self.candidate_head = torch.nn.Linear(hidden_dim, 4)

    def forward(self, board_tokens: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        embedded = self.embedding(board_tokens)
        hidden_seq, hidden = self.gru(embedded)
        return self.candidate_head(hidden_seq), hidden[-1]


class FactoredBridgeDecoder(torch.nn.Module):
    def __init__(self, D: int = 128, max_depth: int = 8, K_var: int = 81, K_val: int = 9, hidden: int = 256):
        super().__init__()
        self.position = torch.nn.Embedding(max_depth, 32)
        self.net = torch.nn.Sequential(torch.nn.Linear(D + 32, hidden), torch.nn.ReLU(), torch.nn.Linear(hidden, hidden), torch.nn.ReLU())
        self.var_head = torch.nn.Linear(hidden, K_var)
        self.val_head = torch.nn.Linear(hidden, K_val)

    def forward(self, h: torch.Tensor, levels: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        pos = self.position(levels)
        if h.ndim == 2 and pos.ndim == 2:
            h = h.unsqueeze(1).expand(-1, pos.shape[0], -1)
            pos = pos.unsqueeze(0).expand(h.shape[0], -1, -1)
        x = self.net(torch.cat([h, pos], dim=-1))
        return self.var_head(x), self.val_head(x)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonable_trace(task: CSPTask) -> dict[str, Any]:
    steps = []
    for step in task.oracle_trace.steps:
        steps.append({
            "action": step.action.value if isinstance(step.action, TraceAction) else str(step.action),
            "variable": step.variable,
            "value": step.value,
            "depth": step.depth,
            "dead_end": step.dead_end,
        })
    examples = []
    for example in trace_to_examples(task.oracle_trace, task.givens, task.task_type):
        row = asdict(example)
        row["partial_assignment"] = {str(key): value for key, value in example.partial_assignment.items()}
        examples.append(row)
    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "givens": task.givens,
        "dpll_backtrack_depth": task.dpll_backtrack_depth,
        "solved": bool(task.oracle_trace.solved),
        "solution": {str(key): value for key, value in (task.oracle_trace.solution or {}).items()},
        "max_backtrack_depth": task.oracle_trace.max_backtrack_depth,
        "total_backtracks": task.oracle_trace.total_backtracks,
        "steps": steps,
        "examples": examples,
    }


def _board_from_assignment(task: CSPTask, assignment: dict[int, int]) -> list[int]:
    board = [0 for _ in range(16)]
    for key, value in task.givens.items():
        if isinstance(key, str) and "," in key:
            row, col = (int(part) for part in key.split(",", 1))
            board[row * 4 + col] = int(value)
    for var, value in assignment.items():
        if 0 <= int(var) < 16:
            board[int(var)] = int(value)
    return board


def _candidate_targets(task: CSPTask, assignment: dict[int, int]) -> list[list[float]]:
    targets = []
    for var in range(16):
        valid = valid_values(task, assignment, var)
        targets.append([1.0 if value in valid else 0.0 for value in range(1, 5)])
    return targets


def _operator_dataset(tasks: list[CSPTask]) -> tuple[torch.Tensor, torch.Tensor]:
    boards: list[list[int]] = []
    targets: list[list[list[float]]] = []
    seen: set[tuple[int, ...]] = set()
    for task in tasks:
        for example in trace_to_examples(task.oracle_trace, task.givens, task.task_type):
            board = _board_from_assignment(task, example.partial_assignment)
            key = tuple(board)
            if key in seen:
                continue
            seen.add(key)
            boards.append(board)
            targets.append(_candidate_targets(task, example.partial_assignment))
    return torch.tensor(boards, dtype=torch.long), torch.tensor(targets, dtype=torch.float32)


def write_teacher_trace(tasks: list[CSPTask], path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    n_examples = 0
    max_depth = 0
    with path.open("w", encoding="utf-8") as handle:
        for task in tasks:
            row = _jsonable_trace(task)
            n_examples += len(row["examples"])
            max_depth = max(max_depth, int(row["max_backtrack_depth"]))
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return {"path": str(path), "tasks": len(tasks), "examples": n_examples, "max_backtrack_depth": max_depth, "sha256": _sha256(path)}


def train_operator(tasks: list[CSPTask], path: Path, device: str, steps: int, batch_size: int, seed: int) -> dict[str, Any]:
    torch.manual_seed(seed)
    x_cpu, y_cpu = _operator_dataset(tasks)
    model = ReconstructedRecurrentSolver(hidden_dim=96, layers=2).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    generator = torch.Generator().manual_seed(seed)
    losses = []
    for step in range(1, steps + 1):
        idx = torch.randint(0, x_cpu.shape[0], (min(batch_size, x_cpu.shape[0]),), generator=generator)
        x = x_cpu[idx].to(device)
        y = y_cpu[idx].to(device)
        logits, _hidden = model(x)
        loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, y)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if step == 1 or step % 25 == 0 or step == steps:
            losses.append({"step": step, "loss": float(loss.item())})
            print(json.dumps({"event": "operator_train", "step": step, "steps": steps, "loss": float(loss.item())}), flush=True)
    with torch.no_grad():
        logits, hidden = model(x_cpu.to(device))
        predictions = logits.sigmoid() >= 0.5
        target = y_cpu.to(device) >= 0.5
        exact_cell = (predictions == target).all(dim=-1).float().mean().item()
    payload = {
        "kind": "reconstructed_parent_operator",
        "source": "RECURRENT_NN/tasks/sudoku/generator_4x4.py + DPLLOracle",
        "model_class": "ReconstructedRecurrentSolver",
        "config": {"hidden_dim": 96, "layers": 2, "board_cells": 16, "values": 4, "training_steps": steps, "seed": seed},
        "state_dict": model.cpu().state_dict(),
        "losses": losses,
        "train_exact_candidate_cell_accuracy": exact_cell,
        "dataset_examples": int(x_cpu.shape[0]),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, path)
    return {"path": str(path), "dataset_examples": int(x_cpu.shape[0]), "train_exact_candidate_cell_accuracy": exact_cell, "sha256": _sha256(path), "losses": losses}


def train_bridge_decoder(path: Path, device: str, steps: int, batch_size: int, seed: int) -> dict[str, Any]:
    from register.vsa_stack import FactoredRegister

    torch.manual_seed(seed)
    decoder = FactoredBridgeDecoder(D=128, max_depth=8, K_var=81, K_val=9).to(device)
    register = FactoredRegister(D=128, K_var=81, K_val=9, max_depth=8, seed=seed, device=device)
    optimizer = torch.optim.AdamW(decoder.parameters(), lr=2e-3, weight_decay=1e-4)
    generator = torch.Generator(device=device).manual_seed(seed + 17)
    levels = torch.arange(8, device=device)
    losses = []
    for step in range(1, steps + 1):
        h_batch = []
        var_targets = []
        val_targets = []
        for _ in range(batch_size):
            register.reset()
            vars_for_depth = []
            vals_for_depth = []
            depth = int(torch.randint(1, 9, (1,), generator=generator, device=device).item())
            for level in range(depth):
                var = int(torch.randint(0, 81, (1,), generator=generator, device=device).item())
                val = int(torch.randint(0, 9, (1,), generator=generator, device=device).item())
                register.push(level, var, val)
                vars_for_depth.append(var)
                vals_for_depth.append(val)
            while len(vars_for_depth) < 8:
                vars_for_depth.append(0)
                vals_for_depth.append(0)
            h_batch.append(register.h.detach().clone())
            var_targets.append(vars_for_depth)
            val_targets.append(vals_for_depth)
        h = torch.stack(h_batch).to(device)
        var_y = torch.tensor(var_targets, dtype=torch.long, device=device)
        val_y = torch.tensor(val_targets, dtype=torch.long, device=device)
        var_logits, val_logits = decoder(h, levels)
        loss = torch.nn.functional.cross_entropy(var_logits.reshape(-1, 81), var_y.reshape(-1)) + torch.nn.functional.cross_entropy(val_logits.reshape(-1, 9), val_y.reshape(-1))
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if step == 1 or step % 50 == 0 or step == steps:
            losses.append({"step": step, "loss": float(loss.item())})
            print(json.dumps({"event": "bridge_train", "step": step, "steps": steps, "loss": float(loss.item())}), flush=True)
    with torch.no_grad():
        var_logits, val_logits = decoder(h, levels)
        var_acc = (var_logits.argmax(dim=-1) == var_y).float().mean().item()
        val_acc = (val_logits.argmax(dim=-1) == val_y).float().mean().item()
    payload = {
        "kind": "reconstructed_item142_factored_cell_digit_decoder",
        "source": "FactoredRegister synthetic depth<=8 states",
        "model_class": "FactoredBridgeDecoder",
        "config": {"D": 128, "max_depth": 8, "K_var": 81, "K_val": 9, "training_steps": steps, "seed": seed},
        "state_dict": decoder.cpu().state_dict(),
        "losses": losses,
        "last_batch_var_accuracy": var_acc,
        "last_batch_val_accuracy": val_acc,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, path)
    return {"path": str(path), "last_batch_var_accuracy": var_acc, "last_batch_val_accuracy": val_acc, "sha256": _sha256(path), "losses": losses}


def reconstruct(output_dir: str, n_instances: int, seed: int, device: str, operator_steps: int, bridge_steps: int, batch_size: int) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    tasks = build_tasks(["sudoku_4x4"], n_instances=n_instances, seed=seed)
    solved = [task for task in tasks if task.oracle_trace.solved]
    if not solved:
        raise RuntimeError("no solved Sudoku tasks generated")
    trace_summary = write_teacher_trace(solved, out / TRACE_NAME)
    operator_summary = train_operator(solved, out / OPERATOR_NAME, device, operator_steps, batch_size, seed=102)
    decoder_summary = train_bridge_decoder(out / DECODER_NAME, device, bridge_steps, batch_size=min(batch_size, 128), seed=142)
    manifest = {
        "module": "stage_a_reconstructed_artifacts",
        "status": "READY",
        "artifact_policy": "reconstructed_in_repo_not_inherited",
        "note": "Original parent recurrent-depth artifacts were not present; these replacements are generated from current RECURRENT_NN code and must be reported as reconstructed artifacts.",
        "output_dir": str(out),
        "task_source": "tasks.sudoku.generator_4x4 + tasks.oracle.DPLLOracle",
        "n_requested_instances": n_instances,
        "n_solved_tasks": len(solved),
        "device": device,
        "operator_ckpt": operator_summary,
        "teacher_trace": trace_summary,
        "bridge_decoder": decoder_summary,
        "stage_a_env": {
            "STAGE_A_OPERATOR_CKPT": str(out / OPERATOR_NAME),
            "STAGE_A_BRIDGE_DECODER": str(out / DECODER_NAME),
            "STAGE_A_TEACHER_TRACE": str(out / TRACE_NAME),
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True), flush=True)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct Stage A parent artifacts.")
    parser.add_argument("--output-dir", default="artifacts/stage_a")
    parser.add_argument("--n-instances", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--operator-steps", type=int, default=300)
    parser.add_argument("--bridge-steps", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=256)
    args = parser.parse_args()
    reconstruct(args.output_dir, args.n_instances, args.seed, args.device, args.operator_steps, args.bridge_steps, args.batch_size)


if __name__ == "__main__":
    main()