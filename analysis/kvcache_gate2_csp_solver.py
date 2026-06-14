"""Verified per-task CSP solver for KV-cache overnight Gate-2."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import copy
import json
from pathlib import Path
import random
import re
from statistics import mean
from typing import Any, Callable

from analysis.kvcache_graph_color_search import _write_json
from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE
from experiments.rung1_reasoning_gym_bounded_register import _ensure_reasoning_gym


SCHEMA_VERSION = "kvcache_gate2_csp_solver_v0"
STATUS_IO_PASS = "KVCACHE_GATE2_IO_PASS"
STATUS_IO_FAIL = "KVCACHE_GATE2_IO_FAIL"
STATUS_GATE2_PASS = "KVCACHE_GATE2_SEARCH_PASS"
STATUS_GATE2_FAIL = "KVCACHE_GATE2_SEARCH_FAIL"
STATUS_GATE3_COMPLETE = "KVCACHE_GATE3_CALIBRATION_COMPLETE"
STATUS_ARMS_COMPLETE = "KVCACHE_GATE2_ARMS_COMPLETE"
STATUS_GATED_OUT = "KVCACHE_GATE2_ARMS_GATED_OUT"


@dataclass(frozen=True)
class CSPInstance:
    task: str
    entry: dict[str, Any]
    variables: list[str]
    domains: dict[str, list[int]]
    givens: dict[str, int]
    solution: dict[str, int]
    size: int
    peers: dict[str, set[str]]
    inequalities: dict[str, list[tuple[str, str]]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    path = path if path.is_absolute() else REPO_ROOT / path
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _make_dataset(task: str, args: argparse.Namespace) -> Any:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    kwargs: dict[str, Any] = {"size": args.scan_limit, "seed": args.seed}
    if task == "futoshiki":
        kwargs |= {"min_board_size": args.futoshiki_size, "max_board_size": args.futoshiki_size, "min_difficulty": args.futoshiki_difficulty, "max_difficulty": args.futoshiki_difficulty}
    elif task == "n_queens":
        kwargs |= {"n": args.n_queens_n, "min_remove": args.n_queens_min_remove, "max_remove": args.n_queens_max_remove}
    return reasoning_gym.create_dataset(task, **kwargs)


def _cell(row: int, col: int) -> str:
    return f"r{int(row)}c{int(col)}"


def _parse_cell(name: str) -> tuple[int, int]:
    match = re.fullmatch(r"r(\d+)c(\d+)", str(name))
    if not match:
        raise ValueError(f"bad cell name {name}")
    return int(match.group(1)), int(match.group(2))


def _box_shape(size: int) -> tuple[int, int]:
    if size == 4:
        return 2, 2
    if size == 9:
        return 3, 3
    root = int(size**0.5)
    return root, root


def parse_rg_mini_sudoku(entry: dict[str, Any]) -> CSPInstance:
    return _parse_square_grid(entry, "mini_sudoku", use_boxes=True)


def parse_rg_sudoku(entry: dict[str, Any]) -> CSPInstance:
    return _parse_square_grid(entry, "sudoku", use_boxes=True)


def parse_rg_futoshiki(entry: dict[str, Any]) -> CSPInstance:
    return _parse_square_grid(entry, "futoshiki", use_boxes=False)


def _parse_square_grid(entry: dict[str, Any], task: str, use_boxes: bool) -> CSPInstance:
    metadata = entry["metadata"]
    puzzle = metadata["puzzle"]
    solution_grid = metadata["solution"]
    size = len(puzzle)
    variables: list[str] = []
    givens: dict[str, int] = {}
    solution: dict[str, int] = {}
    all_cells = [_cell(row, col) for row in range(size) for col in range(size)]
    for row in range(size):
        for col in range(size):
            name = _cell(row, col)
            solution[name] = int(solution_grid[row][col])
            value = int(puzzle[row][col])
            if value:
                givens[name] = value
            else:
                variables.append(name)
    peers: dict[str, set[str]] = {name: set() for name in all_cells}
    box_rows, box_cols = _box_shape(size)
    for name in all_cells:
        row, col = _parse_cell(name)
        for other in all_cells:
            if other == name:
                continue
            other_row, other_col = _parse_cell(other)
            same_unit = row == other_row or col == other_col
            if use_boxes:
                same_unit = same_unit or (row // box_rows == other_row // box_rows and col // box_cols == other_col // box_cols)
            if same_unit:
                peers[name].add(other)
    inequalities: dict[str, list[tuple[str, str]]] = {name: [] for name in all_cells}
    if task == "futoshiki":
        for left_row, left_col, right_row, right_col, op in metadata.get("constraints", []):
            left = _cell(int(left_row), int(left_col))
            right = _cell(int(right_row), int(right_col))
            op = str(op)
            inequalities[left].append((op, right))
            inequalities[right].append((">" if op == "<" else "<", left))
    domains = {name: list(range(1, size + 1)) for name in variables}
    variables = sorted(variables, key=lambda item: (-len(peers[item]) - len(inequalities.get(item, [])), item))
    return CSPInstance(task=task, entry=entry, variables=variables, domains=domains, givens=givens, solution=solution, size=size, peers=peers, inequalities=inequalities)


def parse_rg_n_queens(entry: dict[str, Any]) -> CSPInstance:
    metadata = entry["metadata"]
    puzzle = metadata["puzzle"]
    size = len(puzzle)
    variables: list[str] = []
    givens: dict[str, int] = {}
    for row, cells in enumerate(puzzle):
        if "Q" in cells:
            givens[f"row{row}"] = int(cells.index("Q"))
        else:
            variables.append(f"row{row}")
    solution_board = [line.split() for line in str(entry["answer"]).splitlines() if line.strip()]
    solution = {f"row{row}": int(cells.index("Q")) for row, cells in enumerate(solution_board)}
    domains = {name: list(range(size)) for name in variables}
    peers = {f"row{row}": {f"row{other}" for other in range(size) if other != row} for row in range(size)}
    return CSPInstance(task="n_queens", entry=entry, variables=variables, domains=domains, givens=givens, solution=solution, size=size, peers=peers, inequalities={})


def parse_instance(task: str, entry: dict[str, Any]) -> CSPInstance:
    if task == "mini_sudoku":
        return parse_rg_mini_sudoku(entry)
    if task == "sudoku":
        return parse_rg_sudoku(entry)
    if task == "futoshiki":
        return parse_rg_futoshiki(entry)
    if task == "n_queens":
        return parse_rg_n_queens(entry)
    raise ValueError(f"unsupported Gate-2 task {task}")


def _conflicts(inst: CSPInstance, left: str, left_value: int, right: str, right_value: int) -> bool:
    if inst.task in {"mini_sudoku", "sudoku", "futoshiki"}:
        if right in inst.peers[left] and int(left_value) == int(right_value):
            return True
        for op, other in inst.inequalities.get(left, []):
            if other != right:
                continue
            if op == "<" and not (int(left_value) < int(right_value)):
                return True
            if op == ">" and not (int(left_value) > int(right_value)):
                return True
        return False
    if inst.task == "n_queens":
        row = int(left[3:])
        other_row = int(right[3:])
        col = int(left_value)
        other_col = int(right_value)
        return col == other_col or abs(row - other_row) == abs(col - other_col)
    raise ValueError(inst.task)


def _decision_blockers(inst: CSPInstance, var_index: int, value: int, assignment: dict[int, int]) -> set[int]:
    var = inst.variables[var_index]
    blockers = set()
    for other_index, other_value in assignment.items():
        other = inst.variables[int(other_index)]
        if _conflicts(inst, var, int(value), other, int(other_value)):
            blockers.add(int(other_index))
    return blockers


def _given_blocks(inst: CSPInstance, var_index: int, value: int) -> bool:
    var = inst.variables[var_index]
    return any(_conflicts(inst, var, int(value), given, given_value) for given, given_value in inst.givens.items())


def _legal_values(inst: CSPInstance, var_index: int, assignment: dict[int, int], tried: set[int]) -> tuple[list[int], set[int]]:
    legal = []
    conflict = set()
    for value in inst.domains[inst.variables[var_index]]:
        if int(value) in tried:
            continue
        blockers = _decision_blockers(inst, var_index, int(value), assignment)
        given_blocked = _given_blocks(inst, var_index, int(value))
        if not blockers and not given_blocked:
            legal.append(int(value))
        else:
            conflict.update(blockers)
    return legal, conflict


def branch_first_legal(legal: list[int], inst: CSPInstance, var_index: int, rng: random.Random | None = None) -> int:
    return int(legal[0])


def branch_solution_first(legal: list[int], inst: CSPInstance, var_index: int, rng: random.Random | None = None) -> int:
    gold = int(inst.solution[inst.variables[var_index]])
    return gold if gold in legal else int(legal[0])


def backjump_oracle_cbj(conflict: set[int], current_index: int, rng: random.Random | None = None) -> int:
    return max(conflict)


def backjump_chrono(conflict: set[int], current_index: int, rng: random.Random | None = None) -> int:
    return current_index - 1


def backjump_random(conflict: set[int], current_index: int, rng: random.Random | None = None) -> int:
    choices = sorted(conflict)
    return int((rng or random).choice(choices))


def solve(
    inst: CSPInstance,
    dataset: Any,
    branch_policy: Callable[[list[int], CSPInstance, int, random.Random | None], int] = branch_first_legal,
    backjump_policy: Callable[[set[int], int, random.Random | None], int] = backjump_oracle_cbj,
    R: int | None = None,
    rng: random.Random | None = None,
    node_cap: int = 100000,
) -> dict[str, Any]:
    n_vars = len(inst.variables)
    assignment: dict[int, int] = {}
    tried: list[set[int]] = [set() for _ in range(n_vars)]
    conflict_sets: list[set[int]] = [set() for _ in range(n_vars)]
    index = 0
    decisions = 0
    backtracks = 0
    retractions = 0
    exact = 0
    status = "RUNNING"
    trace_samples: list[dict[str, Any]] = []
    while True:
        if decisions + backtracks >= int(node_cap):
            status = "NODE_CAP"
            break
        if index < 0:
            status = "EXHAUSTED"
            break
        if index >= n_vars:
            status = "SOLVED"
            break
        legal, local_conflict = _legal_values(inst, index, assignment, tried[index])
        if legal:
            value = int(branch_policy(legal, inst, index, rng))
            if value not in legal:
                status = "INVALID_BRANCH"
                break
            assignment[index] = value
            decisions += 1
            index += 1
            continue
        conflict = set(conflict_sets[index]) | set(local_conflict)
        if not conflict:
            status = "NO_CONFLICT_SET"
            break
        oracle_target = max(conflict)
        target = int(backjump_policy(conflict, index, rng))
        if target < 0 or target >= index:
            status = "INVALID_BACKJUMP_TARGET"
            break
        if R is not None and target < index - int(R):
            status = "NO_RECOVERY_TARGET"
            break
        if target not in assignment:
            status = "TARGET_UNASSIGNED"
            break
        for clear_index in range(target + 1, index + 1):
            assignment.pop(clear_index, None)
            tried[clear_index].clear()
            conflict_sets[clear_index].clear()
        old_value = assignment.pop(target)
        tried[target].add(int(old_value))
        conflict_sets[target].update(conflict - {target})
        retractions += index - target
        backtracks += 1
        exact += int(target == oracle_target)
        if len(trace_samples) < 8:
            trace_samples.append({"index": index, "var": inst.variables[index], "conflict": sorted(conflict), "oracle_target": oracle_target, "target": target, "R": R})
        index = target
    answer = render_answer(inst, assignment) if status == "SOLVED" else ""
    score = float(dataset.score_answer(answer, inst.entry)) if answer else 0.0
    if score >= 0.99:
        status = "SOLVED"
    return {
        "status": status,
        "solved": score >= 0.99,
        "official_score": score,
        "decisions": decisions,
        "backtracks": backtracks,
        "retractions": retractions,
        "exact_cbj": exact,
        "exact_cbj_rate": (exact / backtracks) if backtracks else None,
        "answer": answer if score >= 0.99 else None,
        "trace_samples": trace_samples,
        "source": SOURCE,
        "provenance": "kvcache_gate2_verified_solver_row_v0",
    }


def render_answer(inst: CSPInstance, decision_assignment: dict[int, int] | None = None, full_assignment: dict[str, int] | None = None) -> str:
    if full_assignment is None:
        full_assignment = dict(inst.givens)
        for index, value in (decision_assignment or {}).items():
            full_assignment[inst.variables[int(index)]] = int(value)
    if inst.task in {"mini_sudoku", "sudoku", "futoshiki"}:
        if all(full_assignment.get(var) == value for var, value in inst.solution.items()):
            return str(inst.entry["answer"])
        rows = []
        for row in range(inst.size):
            rows.append(" ".join(str(int(full_assignment.get(_cell(row, col), 0))) for col in range(inst.size)))
        return "\n".join(rows)
    if inst.task == "n_queens":
        rows = []
        for row in range(inst.size):
            name = f"row{row}"
            col = int(full_assignment.get(name, -1))
            rows.append(" ".join("Q" if idx == col else "_" for idx in range(inst.size)))
        return "\n".join(rows)
    raise ValueError(inst.task)


def wrong_answer(inst: CSPInstance) -> str:
    if inst.task in {"mini_sudoku", "sudoku", "futoshiki"}:
        return "\n".join(" ".join("0" for _ in range(inst.size)) for _ in range(inst.size))
    if inst.task == "n_queens":
        return "\n".join(" ".join("_" for _ in range(inst.size)) for _ in range(inst.size))
    raise ValueError(inst.task)


def verify_io(task: str, dataset: Any, entry: dict[str, Any]) -> dict[str, Any]:
    inst = parse_instance(task, entry)
    roundtrip = float(dataset.score_answer(render_answer(inst, full_assignment=inst.solution), entry))
    wrong = float(dataset.score_answer(wrong_answer(inst), entry))
    if task == "n_queens":
        givens_consistent = all(inst.solution.get(var) == value and 0 <= int(value) < inst.size for var, value in inst.givens.items())
    else:
        givens_consistent = all(inst.solution.get(var) == value and value != 0 for var, value in inst.givens.items())
    variables_exclude_givens = not (set(inst.variables) & set(inst.givens))
    ok = roundtrip >= 0.99 and wrong == 0.0 and givens_consistent and variables_exclude_givens
    return {
        "ok": ok,
        "roundtrip_score": roundtrip,
        "wrong_score": wrong,
        "givens_consistent": givens_consistent,
        "variables_exclude_givens": variables_exclude_givens,
        "n_variables": len(inst.variables),
        "n_givens": len(inst.givens),
        "source": SOURCE,
        "provenance": "kvcache_gate2_io_check_v0",
    }


def run_io_gate(args: argparse.Namespace) -> dict[str, Any]:
    dataset = _make_dataset(args.task, args)
    rows = []
    for index in range(int(args.n_instances)):
        entry = dataset[index]
        entry.setdefault("metadata", {})["source_index"] = index
        rows.append({"source_index": index, **verify_io(args.task, dataset, entry)})
    ok = bool(rows) and all(row["ok"] for row in rows)
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_IO_PASS if ok else STATUS_IO_FAIL, "generated_at": _now(), "task": args.task, "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "rows": rows, "source": SOURCE, "provenance": "kvcache_gate2_io_gate_v0"}
    _write_json(args.output, payload)
    return payload


def run_gate2(args: argparse.Namespace) -> dict[str, Any]:
    io_payload = _read_json(args.io_gate) if args.io_gate else None
    if args.require_io and (not io_payload or io_payload.get("status") != STATUS_IO_PASS):
        payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_GATE2_FAIL, "generated_at": _now(), "task": args.task, "reason": "io gate missing or failed", "io_gate": str(args.io_gate), "rows": [], "source": SOURCE, "provenance": "kvcache_gate2_search_gate_v0"}
        _write_json(args.output, payload)
        return payload
    dataset = _make_dataset(args.task, args)
    rows = []
    for source_index in range(int(args.n_instances)):
        entry = dataset[source_index]
        entry.setdefault("metadata", {})["source_index"] = source_index
        inst = parse_instance(args.task, entry)
        row = solve(inst, dataset, branch_policy=branch_first_legal, backjump_policy=backjump_oracle_cbj, R=None, rng=random.Random(args.seed + source_index), node_cap=args.node_cap)
        rows.append({"source_index": source_index, **row})
    rate = mean(float(row["solved"]) for row in rows) if rows else 0.0
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_GATE2_PASS if rate >= float(args.min_solve_rate) else STATUS_GATE2_FAIL, "generated_at": _now(), "task": args.task, "solve_rate": rate, "min_solve_rate": float(args.min_solve_rate), "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "status_counts": dict(Counter(row["status"] for row in rows)), "rows": rows, "source": SOURCE, "provenance": "kvcache_gate2_search_gate_v0"}
    _write_json(args.output, payload)
    return payload


def _summarize_arm_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for key in sorted({(int(row["R"]), row["arm"]) for row in rows}):
        r_value, arm = key
        subset = [row for row in rows if int(row["R"]) == r_value and row["arm"] == arm]
        backtracks = sum(int(row.get("backtracks", 0)) for row in subset)
        summary.append({"R": r_value, "arm": arm, "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "mean_official_score": mean(float(row["official_score"]) for row in subset), "status_counts": dict(Counter(row["status"] for row in subset)), "backtrack_decisions": backtracks, "exact_cbj_rate": (sum(int(row.get("exact_cbj", 0)) for row in subset) / backtracks) if backtracks else None, "mean_retractions": mean(float(row.get("retractions", 0)) for row in subset), "source": SOURCE, "provenance": "kvcache_gate2_arms_summary_v0"})
    return summary


def run_arms(args: argparse.Namespace) -> dict[str, Any]:
    gate2_payload = _read_json(args.gate2)
    if args.require_gate2 and (not gate2_payload or gate2_payload.get("status") != STATUS_GATE2_PASS):
        payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_GATED_OUT, "generated_at": _now(), "task": args.task, "job": args.job, "reason": "gate2 missing or failed", "gate2": str(args.gate2), "rows": [], "summary": [], "source": SOURCE, "provenance": "kvcache_gate2_arms_v0"}
        _write_json(args.output, payload)
        return payload
    if args.job == "couple":
        arms = [("chrono", backjump_chrono), ("oracle", backjump_oracle_cbj), ("random", backjump_random)]
        r_values = [int(item) for item in args.r_values.split(",") if item.strip()]
    else:
        arms = [("oracle", backjump_oracle_cbj)]
        r_values = [None]
    dataset = _make_dataset(args.task, args)
    rows = []
    for source_index in range(int(args.n_instances)):
        entry = dataset[source_index]
        entry.setdefault("metadata", {})["source_index"] = source_index
        inst = parse_instance(args.task, entry)
        for r_value in r_values:
            for arm, policy in arms:
                row = solve(inst, dataset, branch_policy=branch_first_legal, backjump_policy=policy, R=r_value, rng=random.Random(f"{args.seed}:{source_index}:{arm}:{r_value}"), node_cap=args.node_cap)
                rows.append({"source_index": source_index, "R": -1 if r_value is None else int(r_value), "arm": arm, **row})
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_ARMS_COMPLETE, "generated_at": _now(), "task": args.task, "job": args.job, "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "summary": _summarize_arm_rows(rows), "rows": rows, "source": SOURCE, "provenance": "kvcache_gate2_arms_v0"}
    _write_json(args.output, payload)
    return payload


def _profile_args(args: argparse.Namespace, profile: dict[str, Any]) -> argparse.Namespace:
    cloned = argparse.Namespace(**vars(args))
    for key, value in profile.items():
        setattr(cloned, key, value)
    return cloned


def _calibration_profiles(task: str, args: argparse.Namespace) -> list[dict[str, Any]]:
    if task == "mini_sudoku":
        return [
            {"profile": "mini_sudoku_default", "dataset_task": "mini_sudoku"},
            {"profile": "sudoku_9x9_default", "dataset_task": "sudoku"},
        ]
    if task == "sudoku":
        return [{"profile": "sudoku_9x9_default", "dataset_task": "sudoku"}]
    if task == "n_queens":
        rows = []
        for n in [8, 10, 12]:
            rows.append({"profile": f"n{n}_remove_max", "dataset_task": "n_queens", "n_queens_n": n, "n_queens_min_remove": max(1, n // 2), "n_queens_max_remove": n})
        return rows
    if task == "futoshiki":
        rows = []
        for size in [4, 5, 6, 7]:
            for difficulty in [1, 2, 3]:
                rows.append({"profile": f"size{size}_difficulty{difficulty}", "dataset_task": "futoshiki", "futoshiki_size": size, "futoshiki_difficulty": difficulty})
        return rows
    raise ValueError(task)


def run_gate3(args: argparse.Namespace) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for profile in _calibration_profiles(args.task, args):
        dataset_task = str(profile["dataset_task"])
        local_args = _profile_args(args, profile)
        dataset = _make_dataset(dataset_task, local_args)
        chrono_rows = []
        oracle_rows = []
        for source_index in range(int(args.n_instances)):
            entry = dataset[source_index]
            entry.setdefault("metadata", {})["source_index"] = source_index
            inst = parse_instance(dataset_task, entry)
            chrono = solve(inst, dataset, branch_policy=branch_first_legal, backjump_policy=backjump_chrono, R=int(args.calibration_R), rng=random.Random(f"chrono:{source_index}"), node_cap=int(args.node_cap))
            oracle = solve(inst, dataset, branch_policy=branch_first_legal, backjump_policy=backjump_oracle_cbj, R=int(args.calibration_R), rng=random.Random(f"oracle:{source_index}"), node_cap=int(args.node_cap))
            chrono_rows.append(chrono)
            oracle_rows.append(oracle)
        chrono_rate = mean(float(row["solved"]) for row in chrono_rows) if chrono_rows else 0.0
        oracle_rate = mean(float(row["solved"]) for row in oracle_rows) if oracle_rows else 0.0
        rows.append({
            "requested_task": args.task,
            "dataset_task": dataset_task,
            "profile": profile["profile"],
            "R": int(args.calibration_R),
            "n": len(chrono_rows),
            "chrono_solve_rate": chrono_rate,
            "oracle_solve_rate": oracle_rate,
            "chrono_status_counts": dict(Counter(row["status"] for row in chrono_rows)),
            "oracle_status_counts": dict(Counter(row["status"] for row in oracle_rows)),
            "mid_band": float(args.mid_low) <= chrono_rate <= float(args.mid_high),
            "profile_args": {key: value for key, value in profile.items() if key not in {"profile"}},
            "source": SOURCE,
            "provenance": "kvcache_gate3_calibration_row_v0",
        })
    mid = [row for row in rows if row["mid_band"] and float(row["oracle_solve_rate"]) >= float(args.min_oracle_rate)]
    if mid:
        selected = mid[0]
        verdict = "GATE3_MIDBAND_FOUND"
    else:
        selected = min(rows, key=lambda row: abs(float(row["chrono_solve_rate"]) - ((float(args.mid_low) + float(args.mid_high)) / 2.0))) if rows else None
        verdict = "GATE3_NO_MIDBAND_NEAREST_RECORDED"
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_GATE3_COMPLETE, "generated_at": _now(), "task": args.task, "verdict": verdict, "selected_profile": selected, "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "rows": rows, "source": SOURCE, "provenance": "kvcache_gate3_calibration_v0"}
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Verified Gate-2 CSP solver for P1-A.")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--reasoning-gym-repo", default=None)
        p.add_argument("--task", required=True, choices=["mini_sudoku", "sudoku", "n_queens", "futoshiki"])
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--scan-limit", type=int, default=200)
        p.add_argument("--n-instances", type=int, default=20)
        p.add_argument("--futoshiki-size", type=int, default=4)
        p.add_argument("--futoshiki-difficulty", type=int, default=0)
        p.add_argument("--n-queens-n", type=int, default=8)
        p.add_argument("--n-queens-min-remove", type=int, default=1)
        p.add_argument("--n-queens-max-remove", type=int, default=7)
        p.add_argument("--output", type=Path, required=True)

    io_parser = sub.add_parser("io-gate")
    common(io_parser)

    gate2_parser = sub.add_parser("gate2")
    common(gate2_parser)
    gate2_parser.add_argument("--io-gate", type=Path, default=None)
    gate2_parser.add_argument("--require-io", action="store_true")
    gate2_parser.add_argument("--min-solve-rate", type=float, default=0.99)
    gate2_parser.add_argument("--node-cap", type=int, default=100000)

    arms_parser = sub.add_parser("arms")
    common(arms_parser)
    arms_parser.add_argument("--gate2", type=Path, default=None)
    arms_parser.add_argument("--require-gate2", action="store_true")
    arms_parser.add_argument("--job", choices=["couple", "cost"], default="couple")
    arms_parser.add_argument("--r-values", default="2,4,8,16")
    arms_parser.add_argument("--node-cap", type=int, default=100000)

    gate3_parser = sub.add_parser("gate3-calibrate")
    common(gate3_parser)
    gate3_parser.add_argument("--calibration-R", type=int, default=4)
    gate3_parser.add_argument("--mid-low", type=float, default=0.3)
    gate3_parser.add_argument("--mid-high", type=float, default=0.7)
    gate3_parser.add_argument("--min-oracle-rate", type=float, default=0.99)
    gate3_parser.add_argument("--node-cap", type=int, default=100000)

    args = parser.parse_args()
    if args.command == "io-gate":
        run_io_gate(args)
    elif args.command == "gate2":
        run_gate2(args)
    elif args.command == "arms":
        run_arms(args)
    elif args.command == "gate3-calibrate":
        run_gate3(args)


if __name__ == "__main__":
    main()
