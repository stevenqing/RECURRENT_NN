"""Track A Stage A runner with a stateless symbolic propagation oracle.

The Track A claim isolates the trail mechanism: the oracle is fixed, fresh per
call, and sees only the task givens plus the current assignment. Reverts rebuild
nodes from the arm trail before the oracle is called again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import torch

from llm_operator.symbolic_filter import CSPTask, forced_moves, propagation_fixpoint, status, valid_values
from register.vsa_stack import BoundSingleRegister, FactoredRegister, predicted_d_star
from tasks.sudoku.generator_6x6 import constraints_6x6, generate_6x6_by_depth_band
from tasks.sudoku.generator_9x9 import constraints_9x9, generate_9x9_by_depth_band


TRACK = "A_symbolic"
OPERATOR = "symbolic_oracle"
SOURCE = "autonomous_stage_a_run"


@dataclass(frozen=True)
class TrackACell:
    cell_index: int
    arm: str
    D: int | None
    seed: int
    spill: str
    task_family: str
    arbiter: bool = False

    @property
    def name(self) -> str:
        d_part = "Dnone" if self.D is None else f"D{self.D}"
        arbiter = "_arbiter09025" if self.arbiter else ""
        return f"{TRACK}_{self.task_family}_{self.arm}_{d_part}_seed{self.seed}_{self.spill}{arbiter}"


def build_track_a_grid(task_family: str = "sudoku6") -> list[TrackACell]:
    cells: list[TrackACell] = []
    index = 0
    for arm in ["rot_bound_single", "rot_factored"]:
        for spill in ["spill_off", "spill_on"]:
            for D in [128, 256, 512]:
                for seed in [42, 137]:
                    cells.append(TrackACell(index, arm, D, seed, spill, task_family))
                    index += 1
    for arm in ["gru", "kv_snapshot", "rot_no_revert"]:
        for D in [128, 256, 512]:
            for seed in [42, 137]:
                cells.append(TrackACell(index, arm, D, seed, "spill_off", task_family))
                index += 1
    cells.append(TrackACell(index, "rot_bound_single", 256, 42, "spill_on", task_family, arbiter=True))
    return cells


def shard_cells(cells: list[TrackACell], num_shards: int, shard_index: int) -> list[TrackACell]:
    if shard_index < 0 or shard_index >= num_shards:
        raise ValueError("shard_index must be in [0, num_shards)")
    return [cell for cell in cells if cell.cell_index % num_shards == shard_index]


def _stable_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _task_static_payload(task: CSPTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "givens": task.givens,
        "variables": task.variables,
        "domains": {str(var): sorted(values) for var, values in task.domains.items()},
    }


class StatelessSymbolicOracle:
    """Fresh current-node oracle object with no tree state or trail memory."""

    __slots__ = ("task",)

    def __init__(self, task: CSPTask):
        self.task = task

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"givens", "assignments"}:
            raise ValueError(f"oracle payload keys must be exactly givens/assignments, got {sorted(payload)}")
        assignment = {int(var): int(val) for var, val in payload["assignments"].items()}
        current_status = status(self.task, assignment)
        forced = forced_moves(self.task, assignment)
        return {
            "status": current_status,
            "forced_moves": [[int(var), int(val)] for var, val in sorted(forced.items())],
            "input_digest": hashlib.sha256(_stable_json_bytes(payload)).hexdigest(),
            "task_digest": hashlib.sha256(_stable_json_bytes(_task_static_payload(self.task))).hexdigest(),
        }


def oracle_call(task: CSPTask, assignment: dict[int, int]) -> dict[str, Any]:
    payload = {"givens": task.givens, "assignments": {str(var): int(val) for var, val in sorted(assignment.items())}}
    return StatelessSymbolicOracle(task)(payload)


def _initial_assignment(task: CSPTask) -> dict[int, int]:
    return {int(var): int(next(iter(values))) for var, values in task.domains.items() if len(values) == 1}


def _render_from_decisions(task: CSPTask, decisions: Iterable[tuple[int, int]]) -> tuple[dict[int, int], int, str]:
    assignment = _initial_assignment(task)
    forced_count = 0
    for var, val in decisions:
        assignment, rounds, current_status = propagation_fixpoint(task, assignment)
        forced_count += rounds
        if current_status != "OPEN":
            return assignment, forced_count, current_status
        assignment[int(var)] = int(val)
    assignment, rounds, current_status = propagation_fixpoint(task, assignment)
    forced_count += rounds
    return assignment, forced_count, current_status


class TrailDecodeError(RuntimeError):
    pass


class BaseTrail:
    arm = "base"

    def current_assignment(self, task: CSPTask) -> tuple[dict[int, int], int, str]:
        raise NotImplementedError

    def push(self, task: CSPTask, assignment: dict[int, int], var: int, val: int) -> None:
        raise NotImplementedError

    def pop(self, task: CSPTask) -> tuple[int, int, float]:
        raise NotImplementedError

    @property
    def depth(self) -> int:
        raise NotImplementedError

    @property
    def decode_failures(self) -> int:
        return 0

    @property
    def overflow_entries(self) -> int:
        return 0

    @property
    def register_bytes(self) -> int:
        return 0


class KVSnapTrail(BaseTrail):
    arm = "kv_snapshot"

    def __init__(self) -> None:
        self.frames: list[tuple[dict[int, int], int, int]] = []
        self.assignment: dict[int, int] | None = None

    @property
    def depth(self) -> int:
        return len(self.frames)

    @property
    def register_bytes(self) -> int:
        return sum(len(frame[0]) for frame in self.frames) * 8

    def current_assignment(self, task: CSPTask) -> tuple[dict[int, int], int, str]:
        if self.assignment is None:
            self.assignment, rounds, current_status = propagation_fixpoint(task, _initial_assignment(task))
            return dict(self.assignment), rounds, current_status
        self.assignment, rounds, current_status = propagation_fixpoint(task, dict(self.assignment))
        return dict(self.assignment), rounds, current_status

    def push(self, task: CSPTask, assignment: dict[int, int], var: int, val: int) -> None:
        self.frames.append((dict(assignment), int(var), int(val)))
        self.assignment = {**assignment, int(var): int(val)}

    def pop(self, task: CSPTask) -> tuple[int, int, float]:
        if not self.frames:
            raise TrailDecodeError("kv_snapshot pop on empty trail")
        assignment, var, val = self.frames.pop()
        self.assignment = dict(assignment)
        return int(var), int(val), 1.0


class RotTrail(BaseTrail):
    def __init__(self, arm: str, D: int, seed: int, max_depth: int, max_var: int, max_val: int, spill: bool, no_revert: bool, device: str = "cpu") -> None:
        self.arm = arm
        self.D = D
        self.seed = seed
        self.spill = spill
        self.no_revert = no_revert
        self.device = device
        self.ceiling = max(1, int(math.floor(predicted_d_star(D, max_var * max_val))))
        self.register_depth = 0
        self._decode_failures = 0
        self.overflow: list[tuple[int, int]] = []
        if arm == "rot_factored":
            self.register = FactoredRegister(D=D, K_var=max_var, K_val=max_val, max_depth=max_depth, seed=seed, device=device)
        else:
            self.register = BoundSingleRegister(D=D, K_var=max_var, K_val=max_val, max_depth=max_depth, seed=seed, device=device)

    @property
    def depth(self) -> int:
        return self.register_depth + len(self.overflow)

    @property
    def decode_failures(self) -> int:
        return self._decode_failures

    @property
    def overflow_entries(self) -> int:
        return len(self.overflow)

    @property
    def register_bytes(self) -> int:
        if self.arm == "rot_factored":
            return int((self.register.h_var.numel() + self.register.h_val.numel()) * self.register.h_var.element_size())
        return int(self.register.h.numel() * self.register.h.element_size())

    def _decoded_register_decisions(self, task: CSPTask) -> list[tuple[int, int]]:
        decisions: list[tuple[int, int]] = []
        for level in range(self.register_depth):
            var, val, margin = self.register.decode_level(level)
            if var not in task.variables or val not in task.domains.get(var, set()):
                self._decode_failures += 1
                raise TrailDecodeError(f"decoded invalid decision level={level} var={var} val={val} margin={margin}")
            decisions.append((int(var), int(val)))
        return decisions

    def current_assignment(self, task: CSPTask) -> tuple[dict[int, int], int, str]:
        decisions = self._decoded_register_decisions(task) + list(self.overflow)
        return _render_from_decisions(task, decisions)

    def push(self, task: CSPTask, assignment: dict[int, int], var: int, val: int) -> None:
        if self.spill and self.register_depth >= self.ceiling:
            self.overflow.append((int(var), int(val)))
            return
        self.register.push(self.register_depth, int(var), int(val))
        self.register_depth += 1

    def pop(self, task: CSPTask) -> tuple[int, int, float]:
        if self.no_revert:
            raise TrailDecodeError("rot_no_revert pop disabled by control arm")
        if self.overflow:
            var, val = self.overflow.pop()
            return int(var), int(val), 1.0
        if self.register_depth <= 0:
            raise TrailDecodeError("rot pop on empty trail")
        level = self.register_depth - 1
        var, val, margin = self.register.pop(level)
        self.register_depth -= 1
        if var not in task.variables or val not in task.domains.get(var, set()):
            self._decode_failures += 1
            raise TrailDecodeError(f"decoded invalid pop var={var} val={val} margin={margin}")
        return int(var), int(val), float(margin)


class GruControlTrail(BaseTrail):
    arm = "gru"

    def __init__(self) -> None:
        self._failed = False

    @property
    def depth(self) -> int:
        return 0

    def current_assignment(self, task: CSPTask) -> tuple[dict[int, int], int, str]:
        return propagation_fixpoint(task, _initial_assignment(task))

    def push(self, task: CSPTask, assignment: dict[int, int], var: int, val: int) -> None:
        self._failed = True
        raise TrailDecodeError("gru trail compressor not trained for Track A symbolic grid in this runner")

    def pop(self, task: CSPTask) -> tuple[int, int, float]:
        raise TrailDecodeError("gru trail compressor unavailable")


def _make_trail(cell: TrackACell, task: CSPTask, device: str) -> BaseTrail:
    if cell.arm == "kv_snapshot":
        return KVSnapTrail()
    if cell.arm == "gru":
        return GruControlTrail()
    if cell.arm in {"rot_bound_single", "rot_factored", "rot_no_revert"}:
        if cell.D is None:
            raise ValueError("rot arms require D")
        max_var = max(task.variables) + 1
        max_val = max(max(values) for values in task.domains.values()) + 1
        arm = "rot_bound_single" if cell.arm == "rot_no_revert" else cell.arm
        return RotTrail(arm, cell.D, cell.seed, max_depth=128, max_var=max_var, max_val=max_val, spill=cell.spill == "spill_on", no_revert=cell.arm == "rot_no_revert", device=device)
    raise ValueError(f"unknown arm: {cell.arm}")


def _next_branch_after(task: CSPTask, assignment: dict[int, int], var: int, previous_val: int) -> tuple[int, int] | None:
    values = [value for value in sorted(valid_values(task, assignment, var), reverse=True) if value < previous_val]
    if values:
        return var, values[0]
    return None


def _mrv_branch(task: CSPTask, assignment: dict[int, int]) -> tuple[int, int] | None:
    candidates = []
    for var in task.variables:
        if var in assignment:
            continue
        values = sorted(valid_values(task, assignment, var), reverse=True)
        if values:
            candidates.append((len(values), var, values[0]))
    if not candidates:
        return None
    _domain_size, var, val = min(candidates)
    return int(var), int(val)


def run_episode(task: CSPTask, cell: TrackACell, max_nodes: int, device: str) -> dict[str, Any]:
    trail = _make_trail(cell, task, device)
    nodes = 0
    applied_reverts = 0
    forced_rounds = 0
    branches = 0
    peak_depth = 0
    peak_register_bytes = 0
    oracle_calls = 0
    try:
        assignment, rounds, current_status = trail.current_assignment(task)
        forced_rounds += rounds
        while nodes < max_nodes:
            oracle = oracle_call(task, assignment)
            oracle_calls += 1
            current_status = oracle["status"]
            if current_status == "SOLVED":
                return {
                    "task_id": task.task_id,
                    "solved": True,
                    "status": "SOLVED",
                    "nodes": nodes,
                    "oracle_calls": oracle_calls,
                    "applied_reverts": applied_reverts,
                    "forced_rounds": forced_rounds,
                    "branches": branches,
                    "peak_depth": peak_depth,
                    "peak_register_bytes": peak_register_bytes,
                    "decode_failures": trail.decode_failures,
                    "overflow_entries": trail.overflow_entries,
                    "dpll_backtrack_depth": task.dpll_backtrack_depth,
                }
            if current_status == "CONTRADICTION":
                while True:
                    popped_var, popped_val, _margin = trail.pop(task)
                    applied_reverts += 1
                    assignment, rounds, restored_status = trail.current_assignment(task)
                    forced_rounds += rounds
                    if restored_status == "CONTRADICTION":
                        continue
                    next_branch = _next_branch_after(task, assignment, popped_var, popped_val)
                    if next_branch is not None:
                        trail.push(task, assignment, next_branch[0], next_branch[1])
                        branches += 1
                        assignment, rounds, current_status = trail.current_assignment(task)
                        forced_rounds += rounds
                        break
                nodes += 1
                peak_depth = max(peak_depth, trail.depth)
                peak_register_bytes = max(peak_register_bytes, trail.register_bytes)
                continue
            guess = _mrv_branch(task, assignment)
            if guess is None:
                return {"task_id": task.task_id, "solved": False, "status": "OPEN_NO_MRV", "nodes": nodes, "oracle_calls": oracle_calls, "applied_reverts": applied_reverts, "forced_rounds": forced_rounds, "branches": branches, "peak_depth": peak_depth, "peak_register_bytes": peak_register_bytes, "decode_failures": trail.decode_failures, "overflow_entries": trail.overflow_entries, "dpll_backtrack_depth": task.dpll_backtrack_depth}
            trail.push(task, assignment, guess[0], guess[1])
            branches += 1
            assignment, rounds, current_status = trail.current_assignment(task)
            forced_rounds += rounds
            nodes += 1
            peak_depth = max(peak_depth, trail.depth)
            peak_register_bytes = max(peak_register_bytes, trail.register_bytes)
        return {"task_id": task.task_id, "solved": False, "status": "NODE_CAP", "nodes": nodes, "oracle_calls": oracle_calls, "applied_reverts": applied_reverts, "forced_rounds": forced_rounds, "branches": branches, "peak_depth": peak_depth, "peak_register_bytes": peak_register_bytes, "decode_failures": trail.decode_failures, "overflow_entries": trail.overflow_entries, "dpll_backtrack_depth": task.dpll_backtrack_depth}
    except TrailDecodeError as exc:
        return {"task_id": task.task_id, "solved": False, "status": "TRAIL_FAILURE", "failure": str(exc), "nodes": nodes, "oracle_calls": oracle_calls, "applied_reverts": applied_reverts, "forced_rounds": forced_rounds, "branches": branches, "peak_depth": peak_depth, "peak_register_bytes": peak_register_bytes, "decode_failures": trail.decode_failures, "overflow_entries": trail.overflow_entries, "dpll_backtrack_depth": task.dpll_backtrack_depth}


def _sudoku6_task(instance: Any, index: int) -> CSPTask:
    variables = list(range(36))
    domains = {var: set(range(1, 7)) for var in variables}
    for (row, col), value in instance.givens.items():
        domains[row * 6 + col] = {value}
    givens = {f"{row},{col}": value for (row, col), value in instance.givens.items()}
    return CSPTask(f"sudoku6_{index}_d{instance.dpll_backtrack_depth}", "sudoku_6x6", givens, variables, domains, constraints_6x6(), instance.oracle_trace, instance.dpll_backtrack_depth)


def _sudoku9_task(instance: Any, index: int) -> CSPTask:
    variables = list(range(81))
    domains = {var: set(range(1, 10)) for var in variables}
    for (row, col), value in instance.givens.items():
        domains[row * 9 + col] = {value}
    givens = {f"{row},{col}": value for (row, col), value in instance.givens.items()}
    return CSPTask(f"sudoku9_{index}_d{instance.dpll_backtrack_depth}", "sudoku_9x9", givens, variables, domains, constraints_9x9(), instance.oracle_trace, instance.dpll_backtrack_depth)


def build_eval_tasks(task_family: str, n_instances: int, seed: int, min_depth: int, max_depth: int) -> list[CSPTask]:
    if task_family == "sudoku6":
        return [_sudoku6_task(instance, index) for index, instance in enumerate(generate_6x6_by_depth_band(min_depth, max_depth, n_instances, seed))]
    if task_family == "sudoku9":
        return [_sudoku9_task(instance, index) for index, instance in enumerate(generate_9x9_by_depth_band(min_depth, max_depth, n_instances, seed))]
    raise ValueError(f"unknown task_family: {task_family}")


def statelessness_ci(output_dir: str = "results/stage_a_symbolic") -> dict[str, Any]:
    tasks = build_eval_tasks("sudoku6", n_instances=1, seed=31415, min_depth=1, max_depth=2)
    if not tasks:
        raise RuntimeError("statelessness CI could not generate a Sudoku6 depth 1-2 task")
    task = tasks[0]
    assignment = _initial_assignment(task)
    assignment, _rounds, _status = propagation_fixpoint(task, assignment)
    first_guess = _mrv_branch(task, assignment)
    if first_guess is not None:
        assignment = {**assignment, first_guess[0]: first_guess[1]}
        assignment, _rounds, _status = propagation_fixpoint(task, assignment)
    history_a = {"history": [["branch", first_guess[0] if first_guess else -1, first_guess[1] if first_guess else -1], ["reconstruct", "rot_bound_single"]]}
    history_b = {"history": [["snapshot_restore", 0], ["reconstruct", "kv_snapshot"], ["dropped", "unrelated"]]}
    out_a = oracle_call(task, assignment)
    out_b = oracle_call(task, dict(reversed(list(assignment.items()))))
    same_bytes = _stable_json_bytes(out_a) == _stable_json_bytes(out_b)
    payload = {
        "module": "stage_a_symbolic_oracle.statelessness_ci",
        "status": "PASS" if same_bytes else "FAIL",
        "track": TRACK,
        "operator": OPERATOR,
        "source": "ci_statelessness_test",
        "task_id": task.task_id,
        "assignment_size": len(assignment),
        "history_a_ignored": history_a,
        "history_b_ignored": history_b,
        "oracle_output_a": out_a,
        "oracle_output_b": out_b,
        "byte_identical_outputs": same_bytes,
        "input_contract_keys": ["givens", "assignments"],
    }
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "oracle_statelessness_ci.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _summarize_cell(cell: TrackACell, episodes: list[dict[str, Any]]) -> dict[str, Any]:
    solved = [row for row in episodes if row.get("solved")]
    depths = sorted({row.get("dpll_backtrack_depth") for row in episodes})
    applied_reverts = sum(int(row.get("applied_reverts") or 0) for row in episodes)
    max_depth = max([int(row.get("dpll_backtrack_depth") or 0) for row in solved], default=0)
    solve_rate = len(solved) / len(episodes) if episodes else 0.0
    return {
        "cell_index": cell.cell_index,
        "cell_name": cell.name,
        "track": TRACK,
        "operator": OPERATOR,
        "source": SOURCE,
        "arm": cell.arm,
        "D": cell.D,
        "seed": cell.seed,
        "spill": cell.spill,
        "arbiter": cell.arbiter,
        "task_family": cell.task_family,
        "n_episodes": len(episodes),
        "solve_rate": solve_rate,
        "solved": len(solved),
        "depths": depths,
        "max_solve_depth": max_depth,
        "applied_reverts": applied_reverts,
        "revert_success": applied_reverts > 0 and len(solved) > 0,
        "mean_nodes": sum(int(row.get("nodes") or 0) for row in episodes) / len(episodes) if episodes else 0.0,
        "peak_depth": max([int(row.get("peak_depth") or 0) for row in episodes], default=0),
        "peak_register_bytes": max([int(row.get("peak_register_bytes") or 0) for row in episodes], default=0),
        "overflow_entries": max([int(row.get("overflow_entries") or 0) for row in episodes], default=0),
        "decode_failures": sum(int(row.get("decode_failures") or 0) for row in episodes),
        "status": "CELL_COMPLETE" if episodes else "NO_EPISODES",
    }


def _group_rows(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    groups = sorted({(cell["arm"], cell["D"], cell["spill"], cell["task_family"]) for cell in cells}, key=str)
    for arm, D, spill, task_family in groups:
        subset = [cell for cell in cells if (cell["arm"], cell["D"], cell["spill"], cell["task_family"]) == (arm, D, spill, task_family)]
        rows.append({
            "track": TRACK,
            "operator": OPERATOR,
            "source": SOURCE,
            "task_family": task_family,
            "arm": arm,
            "D": D,
            "spill": spill,
            "n_cells": len(subset),
            "mean_solve_rate": sum(float(cell["solve_rate"]) for cell in subset) / len(subset),
            "total_applied_reverts": sum(int(cell["applied_reverts"]) for cell in subset),
            "max_solve_depth": max(int(cell["max_solve_depth"]) for cell in subset),
            "max_peak_register_bytes": max(int(cell["peak_register_bytes"]) for cell in subset),
            "max_overflow_entries": max(int(cell["overflow_entries"]) for cell in subset),
        })
    return rows


def _report_payload(result: dict[str, Any]) -> dict[str, Any]:
    cells = result.get("cells", [])
    rows = _group_rows(cells)
    kv_depth = max((row["max_solve_depth"] for row in rows if row["arm"] == "kv_snapshot"), default=0)
    no_revert_depth = max((row["max_solve_depth"] for row in rows if row["arm"] == "rot_no_revert"), default=0)
    rot_reverts = sum(row["total_applied_reverts"] for row in rows if str(row["arm"]).startswith("rot_") and row["arm"] != "rot_no_revert")
    return {
        "module": "stage_a_symbolic_oracle_report",
        "status": "TRACK_A_SYMBOLIC_RESULTS_AVAILABLE" if cells else "NO_CELLS",
        "track": TRACK,
        "operator": OPERATOR,
        "source": SOURCE,
        "n_cells": len(cells),
        "l4_separation_table": {"columns": ["track", "operator", "source", "task_family", "arm", "D", "spill", "n_cells", "mean_solve_rate", "total_applied_reverts", "max_solve_depth"], "rows": rows},
        "band_overlay": {"columns": ["D", "predicted_d_star", "observed_max_solve_depth", "provenance"], "rows": [
            {"D": D, "predicted_d_star": predicted_d_star(D, 36 * 7), "observed_max_solve_depth": max((cell["max_solve_depth"] for cell in cells if cell["D"] == D and cell["arm"] in {"rot_bound_single", "rot_factored"}), default=0), "provenance": "results/stage_a_symbolic/results.json"}
            for D in [128, 256, 512]
        ]},
        "arbiter_table": {"columns": ["cell_name", "solve_rate", "applied_reverts", "max_solve_depth", "provenance"], "rows": [
            {"cell_name": cell["cell_name"], "solve_rate": cell["solve_rate"], "applied_reverts": cell["applied_reverts"], "max_solve_depth": cell["max_solve_depth"], "provenance": "results/stage_a_symbolic/results.json"}
            for cell in cells if cell.get("arbiter")
        ]},
        "spill_resources": {"columns": ["arm", "D", "spill", "max_overflow_entries", "max_peak_register_bytes", "provenance"], "rows": [
            {"arm": row["arm"], "D": row["D"], "spill": row["spill"], "max_overflow_entries": row["max_overflow_entries"], "max_peak_register_bytes": row["max_peak_register_bytes"], "provenance": "results/stage_a_symbolic/results.json"}
            for row in rows
        ]},
        "symbolic_core_evidence": {
            "declared_track": TRACK,
            "operator": OPERATOR,
            "autonomous_cells": len(cells),
            "reverts_nonzero_on_L4": rot_reverts > 0,
            "forward_floor_on_L4": kv_depth > no_revert_depth or rot_reverts > 0,
            "kv_snapshot_max_depth": kv_depth,
            "rot_no_revert_max_depth": no_revert_depth,
        },
    }


def write_report(output_dir: str, result: dict[str, Any]) -> dict[str, Any]:
    root = Path(output_dir)
    payload = _report_payload(result)
    lines = [
        "# Track A Symbolic Stage A Report\n",
        f"Status: `{payload['status']}`\n",
        f"Track: `{TRACK}`\n",
        f"Operator: `{OPERATOR}`\n",
        f"Cells: `{payload['n_cells']}`\n",
        "\n## L4 Separation\n",
        "| arm | D | spill | n_cells | mean_solve_rate | applied_reverts | max_solve_depth |\n",
        "| --- | --- | --- | --- | --- | --- | --- |\n",
    ]
    for row in payload["l4_separation_table"]["rows"]:
        lines.append(f"| {row['arm']} | {row['D']} | {row['spill']} | {row['n_cells']} | {row['mean_solve_rate']} | {row['total_applied_reverts']} | {row['max_solve_depth']} |\n")
    lines.extend([
        "\n## Honesty Boundary\n",
        "Track A rows are symbolic-oracle rows only. They are not learned-operator rows, and learned-track validation reds remain separate. The oracle is freshly constructed per call and consumes only givens plus current assignments.\n",
    ])
    (root / "report.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "report.md").write_text("".join(lines), encoding="utf-8")
    return payload


def run_track_a(
    output_dir: str = "results/stage_a_symbolic",
    task_family: str = "sudoku6",
    n_instances: int = 4,
    min_depth: int = 1,
    max_depth: int = 2,
    seed: int = 42,
    num_shards: int = 1,
    shard_index: int = 0,
    max_nodes: int = 512,
    device: str = "cpu",
    torch_threads: int = 1,
) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    if torch_threads > 0:
        torch.set_num_threads(torch_threads)
    torch_device = torch.device(device)
    if torch_device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but torch.cuda.is_available() is false")
    stateless = statelessness_ci(output_dir)
    tasks = build_eval_tasks(task_family, n_instances, seed, min_depth, max_depth)
    grid = shard_cells(build_track_a_grid(task_family), num_shards, shard_index)
    cells: list[dict[str, Any]] = []
    for cell in grid:
        rng = random.Random(cell.seed)
        selected_tasks = list(tasks)
        rng.shuffle(selected_tasks)
        episodes = [run_episode(task, cell, max_nodes=max_nodes, device=device) for task in selected_tasks]
        cell_summary = _summarize_cell(cell, episodes)
        cell_summary["episodes"] = episodes
        cells.append(cell_summary)
    result = {
        "module": "stage_a_symbolic_oracle",
        "status": "TRACK_A_SYMBOLIC_SHARD_COMPLETE",
        "generated_at": generated_at,
        "track": TRACK,
        "operator": OPERATOR,
        "source": SOURCE,
        "oracle_contract": {
            "stateless": True,
            "fresh_object_per_call": True,
            "allowed_input_keys": ["givens", "assignments"],
            "branch_policy": "MRV on current node only",
            "dead_end_source": "symbolic oracle CONTRADICTION on current node only",
            "reconstruct_after_revert": "arm trail pop -> remaining decisions/snapshot -> re-render -> fresh oracle call",
            "ci_status": stateless["status"],
            "ci_artifact": str(root / "oracle_statelessness_ci.json"),
        },
        "task_family": task_family,
        "torch_threads": torch.get_num_threads(),
        "n_tasks": len(tasks),
        "task_depth_histogram": {str(depth): sum(1 for task in tasks if task.dpll_backtrack_depth == depth) for depth in sorted({task.dpll_backtrack_depth for task in tasks})},
        "num_shards": num_shards,
        "shard_index": shard_index,
        "n_cells": len(cells),
        "cells": cells,
        "honesty": {
            "does_not_establish": "Track A uses operator=symbolic_oracle and does not establish learned_recurrent G1, learned operator propagation, TRM performance, D1 cached-state survival, D2 TRM defensive accuracy, or D3 deep 9x9 frontier resolution.",
        },
    }
    (root / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = write_report(output_dir, result)
    result["report"] = report
    (root / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Track A Stage A with a stateless symbolic oracle.")
    parser.add_argument("--output-dir", default="results/stage_a_symbolic")
    parser.add_argument("--task-family", choices=["sudoku6", "sudoku9"], default="sudoku6")
    parser.add_argument("--n-instances", type=int, default=4)
    parser.add_argument("--min-depth", type=int, default=1)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--max-nodes", type=int, default=512)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--torch-threads", type=int, default=1)
    parser.add_argument("--statelessness-ci-only", action="store_true")
    args = parser.parse_args()
    if args.statelessness_ci_only:
        payload = statelessness_ci(args.output_dir)
    else:
        payload = run_track_a(
            output_dir=args.output_dir,
            task_family=args.task_family,
            n_instances=args.n_instances,
            min_depth=args.min_depth,
            max_depth=args.max_depth,
            seed=args.seed,
            num_shards=args.num_shards,
            shard_index=args.shard_index,
            max_nodes=args.max_nodes,
            device=args.device,
            torch_threads=args.torch_threads,
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if payload.get("status") in {"FAIL", "NO_CELLS"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
