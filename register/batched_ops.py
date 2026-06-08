"""Batched Sudoku6 operations that preserve scalar CSP semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import torch

from sudoku_engine_gpu import apply_commits, forced_set, from_assignments, propagate, status, to_assignments


@dataclass(frozen=True)
class BatchedForcedResult:
    forced_values: list[dict[int, int]]
    statuses: list[str]


@dataclass(frozen=True)
class BatchedPropagationResult:
    assignments: list[dict[int, int]]
    statuses: list[str]


def batched_forced_values(assignments: Sequence[dict[int, int]], device: str | torch.device = "cuda:0") -> BatchedForcedResult:
    resolved_device = _resolve_device(device)
    batch = from_assignments(assignments, device=resolved_device)
    forced_tensor = forced_set(batch).detach().cpu()
    forced_values = []
    for row_index in range(forced_tensor.shape[0]):
        forced_values.append({cell: int(forced_tensor[row_index, cell].item()) for cell in range(forced_tensor.shape[1]) if int(forced_tensor[row_index, cell].item()) > 0})
    return BatchedForcedResult(forced_values=forced_values, statuses=status(batch))


def batched_propagation_fixpoint(assignments: Sequence[dict[int, int]], device: str | torch.device = "cuda:0") -> BatchedPropagationResult:
    resolved_device = _resolve_device(device)
    propagated = propagate(from_assignments(assignments, device=resolved_device))
    return BatchedPropagationResult(assignments=to_assignments(propagated), statuses=status(propagated))


def batched_apply_commits(assignments: Sequence[dict[int, int]], commits: Sequence[dict[int, int]], device: str | torch.device = "cuda:0") -> list[dict[int, int]]:
    if len(assignments) != len(commits):
        raise ValueError("assignments and commits must have the same length")
    resolved_device = _resolve_device(device)
    batch = from_assignments(assignments, device=resolved_device)
    commit_tensor = torch.zeros_like(batch.candidates)
    for row_index, row_commits in enumerate(commits):
        for cell, value in row_commits.items():
            commit_tensor[row_index, int(cell)] = int(value)
    return to_assignments(apply_commits(batch, commit_tensor))


def _resolve_device(device: str | torch.device) -> str | torch.device:
    if str(device).startswith("cuda") and not torch.cuda.is_available():
        return "cpu"
    return device