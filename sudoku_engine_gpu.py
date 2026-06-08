"""Batched 6x6 Sudoku candidate engine for Track B pipeline work."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import torch


N_CELLS = 36
N_VALUES = 6
FULL_MASK = (1 << N_VALUES) - 1
VALUE_BITS = tuple(1 << index for index in range(N_VALUES))


def _units() -> list[list[int]]:
    rows = [[row * 6 + col for col in range(6)] for row in range(6)]
    cols = [[row * 6 + col for row in range(6)] for col in range(6)]
    boxes = [[(box_row * 2 + row) * 6 + (box_col * 3 + col) for row in range(2) for col in range(3)] for box_row in range(3) for box_col in range(2)]
    return rows + cols + boxes


UNITS = _units()
PEERS: tuple[tuple[int, ...], ...] = tuple(
    tuple(sorted({peer for unit in UNITS if cell in unit for peer in unit if peer != cell}))
    for cell in range(N_CELLS)
)


@dataclass(frozen=True)
class SudokuBatch:
    candidates: torch.Tensor
    assigned: torch.Tensor

    def __post_init__(self) -> None:
        if self.candidates.shape != self.assigned.shape:
            raise ValueError("candidates and assigned must have the same shape")
        if self.candidates.ndim != 2 or self.candidates.shape[1] != N_CELLS:
            raise ValueError(f"expected [batch,{N_CELLS}] candidate tensor")
        if self.candidates.dtype != torch.int64:
            raise ValueError("candidates must be torch.int64 bitmasks")
        if self.assigned.dtype != torch.bool:
            raise ValueError("assigned must be torch.bool")
        if self.candidates.device != self.assigned.device:
            raise ValueError("candidates and assigned must be on the same device")

    @property
    def device(self) -> torch.device:
        return self.candidates.device

    def clone(self) -> "SudokuBatch":
        return SudokuBatch(self.candidates.clone(), self.assigned.clone())


def from_assignments(assignments: Iterable[dict[int, int]], device: str | torch.device = "cpu") -> SudokuBatch:
    rows = list(assignments)
    candidates = torch.full((len(rows), N_CELLS), FULL_MASK, dtype=torch.int64, device=device)
    assigned = torch.zeros((len(rows), N_CELLS), dtype=torch.bool, device=device)
    for row_index, assignment in enumerate(rows):
        for cell, value in assignment.items():
            if not 0 <= int(cell) < N_CELLS:
                raise ValueError(f"cell out of range: {cell}")
            if not 1 <= int(value) <= N_VALUES:
                raise ValueError(f"value out of range: {value}")
            candidates[row_index, int(cell)] = 1 << (int(value) - 1)
            assigned[row_index, int(cell)] = True
    return SudokuBatch(candidates, assigned)


def to_assignments(batch: SudokuBatch) -> list[dict[int, int]]:
    values = _mask_to_value(batch.candidates)
    assignments: list[dict[int, int]] = []
    assigned_cpu = batch.assigned.detach().cpu()
    values_cpu = values.detach().cpu()
    for row_index in range(batch.candidates.shape[0]):
        row = {}
        for cell in range(N_CELLS):
            if bool(assigned_cpu[row_index, cell]):
                value = int(values_cpu[row_index, cell].item())
                if value:
                    row[cell] = value
        assignments.append(row)
    return assignments


def contradiction(batch: SudokuBatch) -> torch.Tensor:
    popcounts = _popcount(batch.candidates)
    bad_assigned = (batch.assigned & (popcounts != 1)).any(dim=1)
    duplicate = torch.zeros(batch.candidates.shape[0], dtype=torch.bool, device=batch.device)
    for unit in UNITS:
        unit_candidates = batch.candidates[:, unit]
        unit_assigned = batch.assigned[:, unit]
        for bit in VALUE_BITS:
            duplicate |= ((unit_candidates == bit) & unit_assigned).sum(dim=1) > 1
    candidate_view = _candidate_view(batch)
    zero_unassigned = ((candidate_view == 0) & ~batch.assigned).any(dim=1)
    return bad_assigned | duplicate | zero_unassigned


def forced_set(batch: SudokuBatch) -> torch.Tensor:
    candidate_view = _candidate_view(batch)
    forced_mask = (~batch.assigned) & (_popcount(candidate_view) == 1) & ~contradiction(batch).unsqueeze(1)
    forced = torch.zeros_like(batch.candidates)
    forced[forced_mask] = _mask_to_value(candidate_view)[forced_mask]
    return forced


def apply_commits(batch: SudokuBatch, commits: torch.Tensor) -> SudokuBatch:
    if commits.shape != batch.candidates.shape:
        raise ValueError("commits must have shape [batch,36]")
    commits = commits.to(device=batch.device, dtype=torch.int64)
    commit_mask = commits > 0
    if bool((commits[commit_mask] > N_VALUES).any().item()):
        raise ValueError("commit values must be in 1..6")
    candidates = batch.candidates.clone()
    assigned = batch.assigned.clone()
    candidates[commit_mask] = torch.bitwise_left_shift(torch.ones_like(commits[commit_mask]), commits[commit_mask] - 1)
    assigned |= commit_mask
    return SudokuBatch(candidates, assigned)


def propagate(batch: SudokuBatch, max_rounds: int = N_CELLS) -> SudokuBatch:
    current = batch.clone()
    for _ in range(max_rounds):
        bad_before = contradiction(current)
        candidate_view = _candidate_view(current)
        candidates = torch.where(bad_before.unsqueeze(1), current.candidates, candidate_view)
        current = SudokuBatch(candidates, current.assigned)
        bad_after = contradiction(current)
        new_forced = (~current.assigned) & (_popcount(current.candidates) == 1) & ~bad_after.unsqueeze(1)
        if not bool(new_forced.any().item()):
            return current
        current = SudokuBatch(current.candidates, current.assigned | new_forced)
    return current


def status(batch: SudokuBatch) -> list[str]:
    bad = contradiction(batch).detach().cpu()
    solved = batch.assigned.all(dim=1).detach().cpu()
    return ["CONTRADICTION" if bool(bad[index]) else "SOLVED" if bool(solved[index]) else "OPEN" for index in range(batch.candidates.shape[0])]


def _candidate_view(batch: SudokuBatch) -> torch.Tensor:
    candidates = batch.candidates.clone()
    for cell, peers in enumerate(PEERS):
        forbidden = torch.zeros(candidates.shape[0], dtype=torch.int64, device=batch.device)
        for peer in peers:
            peer_bits = torch.where(batch.assigned[:, peer], candidates[:, peer], torch.zeros_like(forbidden))
            forbidden = torch.bitwise_or(forbidden, peer_bits)
        allowed = torch.bitwise_and(candidates[:, cell], FULL_MASK ^ forbidden)
        candidates[:, cell] = torch.where(batch.assigned[:, cell], candidates[:, cell], allowed)
    return candidates


def _popcount(mask: torch.Tensor) -> torch.Tensor:
    table = torch.tensor([int(value).bit_count() for value in range(FULL_MASK + 1)], dtype=torch.int64, device=mask.device)
    return table[mask.clamp(0, FULL_MASK)]


def _mask_to_value(mask: torch.Tensor) -> torch.Tensor:
    table = torch.zeros(FULL_MASK + 1, dtype=torch.int64, device=mask.device)
    for digit in range(1, N_VALUES + 1):
        table[1 << (digit - 1)] = digit
    return table[mask.clamp(0, FULL_MASK)]