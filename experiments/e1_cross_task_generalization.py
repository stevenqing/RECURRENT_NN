"""Post-review E1 scalar cross-task generalization run.

The amended E1 spec removes the batched-engine gate: SAT and graph-coloring are
small enough to run one instance at a time through the scalar Stage A register
loop. The scalar oracle is still stateless; the rot arms still use the lossy VSA
registers as the object under test.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
from statistics import mean
from typing import Any, Literal

from analysis.capacity_theory import d_star_factored, d_star_product
from register.vsa_stack import BoundSingleRegister, FactoredRegister


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = REPO_ROOT / "results/post_review_e1_cross_task_generalization"
RESULTS_PATH = RUN_ROOT / "results.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_050_post_review_e1_cross_task_generalization.json"
PANEL_DIR = RUN_ROOT / "panels"
BANDS = ("R0", "R1-2", "R3-5", "R6+")
DS = (128, 256, 512)
SEEDS = (42, 137)
STRUCTURED_ARMS = ("rot_bound_single", "rot_factored")
CONTROL_ARMS = ("rot_no_revert", "gru", "kv_snapshot")
TASKS = ("sat_3sat", "graph_coloring")
SOURCE = "autonomous_stage_a_run"


@dataclass(frozen=True)
class SolveResult:
    solved: bool
    assignment: dict[int, int]
    reverts_needed: int
    trace_length: int
    nodes_visited: int
    max_depth: int
    contradictions: int


@dataclass(frozen=True)
class RegisterEval:
    solved: bool
    applied_reverts: int
    revert_success: bool
    peak_register_bytes: int
    overflow_entries: int
    node_cap_exhausted: bool
    decode_failures: int
    status: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _band(reverts_needed: int) -> str:
    if reverts_needed == 0:
        return "R0"
    if reverts_needed <= 2:
        return "R1-2"
    if reverts_needed <= 5:
        return "R3-5"
    return "R6+"


def _sat_clause_state(clause: list[int], assignment: dict[int, int]) -> tuple[bool, list[int]]:
    open_lits = []
    for lit in clause:
        var = abs(lit)
        if var not in assignment:
            open_lits.append(lit)
        elif (assignment[var] == 1) == (lit > 0):
            return True, []
    return False, open_lits


def _sat_propagate(clauses: list[list[int]], assignment: dict[int, int], n_vars: int) -> tuple[str, dict[int, int], int]:
    current = dict(assignment)
    forced_total = 0
    while True:
        forced: dict[int, int] = {}
        for clause in clauses:
            satisfied, open_lits = _sat_clause_state(clause, current)
            if satisfied:
                continue
            if not open_lits:
                return "CONTRADICTION", current, forced_total
            if len(open_lits) == 1:
                lit = open_lits[0]
                value = 1 if lit > 0 else 0
                var = abs(lit)
                if var in current and current[var] != value:
                    return "CONTRADICTION", current, forced_total
                forced[var] = value
        new_forced = {var: value for var, value in forced.items() if var not in current}
        if not new_forced:
            break
        current.update(new_forced)
        forced_total += len(new_forced)
    return ("SOLVED" if len(current) == n_vars else "OPEN"), current, forced_total


def _sat_branch(clauses: list[list[int]], assignment: dict[int, int], n_vars: int) -> tuple[int, list[int]] | None:
    unsatisfied = [clause for clause in clauses if not _sat_clause_state(clause, assignment)[0]]
    best: tuple[int, int, int] | None = None
    for var in range(1, n_vars + 1):
        if var in assignment:
            continue
        pos = sum(1 for clause in unsatisfied for lit in clause if lit == var)
        neg = sum(1 for clause in unsatisfied for lit in clause if lit == -var)
        if pos + neg == 0:
            pos = sum(1 for clause in clauses for lit in clause if lit == var)
            neg = sum(1 for clause in clauses for lit in clause if lit == -var)
        preferred = 1 if pos >= neg else 0
        key = (pos + neg, -var, preferred)
        if best is None or key > best:
            best = key
    if best is None:
        return None
    _, neg_var, preferred = best
    return -neg_var, [preferred, 1 - preferred]


def _graph_domains(n: int, k: int, edges: list[tuple[int, int]], assignment: dict[int, int]) -> tuple[str, dict[int, set[int]]]:
    neighbors = {node: set() for node in range(n)}
    for left, right in edges:
        neighbors[left].add(right)
        neighbors[right].add(left)
    domains: dict[int, set[int]] = {}
    for node in range(n):
        if node in assignment:
            if any(assignment.get(other) == assignment[node] for other in neighbors[node]):
                return "CONTRADICTION", {}
            domains[node] = {assignment[node]}
        else:
            values = set(range(1, k + 1)) - {assignment[other] for other in neighbors[node] if other in assignment}
            if not values:
                return "CONTRADICTION", {}
            domains[node] = values
    return "OPEN", domains


def _graph_propagate(n: int, k: int, edges: list[tuple[int, int]], assignment: dict[int, int]) -> tuple[str, dict[int, int], int]:
    current = dict(assignment)
    forced_total = 0
    while True:
        state, domains = _graph_domains(n, k, edges, current)
        if state == "CONTRADICTION":
            return state, current, forced_total
        forced = {node: next(iter(values)) for node, values in domains.items() if node not in current and len(values) == 1}
        if not forced:
            break
        current.update(forced)
        forced_total += len(forced)
    return ("SOLVED" if len(current) == n else "OPEN"), current, forced_total


def _graph_branch(n: int, k: int, edges: list[tuple[int, int]], assignment: dict[int, int]) -> tuple[int, list[int]] | None:
    state, domains = _graph_domains(n, k, edges, assignment)
    if state == "CONTRADICTION":
        return None
    candidates = [(len(values), node, sorted(values)) for node, values in domains.items() if node not in assignment]
    if not candidates:
        return None
    _, node, values = min(candidates)
    return node, values


def _oracle_ops(task: str, data: Any, config: dict[str, Any], assignment: dict[int, int]) -> tuple[str, dict[int, int], tuple[int, list[int]] | None, int]:
    if task == "sat_3sat":
        state, current, forced = _sat_propagate(data, assignment, config["n_vars"])
        choice = None if state != "OPEN" else _sat_branch(data, current, config["n_vars"])
        return state, current, choice, forced
    state, current, forced = _graph_propagate(config["n"], config["k"], data, assignment)
    choice = None if state != "OPEN" else _graph_branch(config["n"], config["k"], data, current)
    return state, current, choice, forced


def _solve_reference(task: str, data: Any, config: dict[str, Any], node_cap: int | None = None) -> SolveResult:
    stats = {"reverts": 0, "trace": 0, "nodes": 0, "max_depth": 0, "contradictions": 0}

    def dfs(assignment: dict[int, int], depth: int) -> tuple[bool, dict[int, int]]:
        stats["nodes"] += 1
        stats["trace"] += 1
        stats["max_depth"] = max(stats["max_depth"], depth)
        if node_cap is not None and stats["trace"] > node_cap:
            return False, assignment
        state, current, choice, forced = _oracle_ops(task, data, config, assignment)
        stats["trace"] += forced
        if state == "CONTRADICTION":
            stats["contradictions"] += 1
            return False, current
        if state == "SOLVED":
            return True, current
        if choice is None:
            return False, current
        var, values = choice
        for value in values:
            solved, final = dfs({**current, var: value}, depth + 1)
            if solved:
                return True, final
            stats["reverts"] += 1
            stats["trace"] += 1
        return False, current

    solved, assignment = dfs({}, 0)
    return SolveResult(solved, assignment if solved else {}, stats["reverts"], stats["trace"], stats["nodes"], stats["max_depth"], stats["contradictions"])


def _random_sat(n_vars: int, ratio: float, rng: random.Random) -> list[list[int]]:
    return [[var if rng.random() < 0.5 else -var for var in rng.sample(range(1, n_vars + 1), 3)] for _ in range(round(n_vars * ratio))]


def _random_graph(n: int, edge_prob: float, rng: random.Random) -> list[tuple[int, int]]:
    return [(left, right) for left in range(n) for right in range(left + 1, n) if rng.random() < edge_prob]


def _generate_instance(task: str, config: dict[str, Any], rng: random.Random) -> Any:
    if task == "sat_3sat":
        return _random_sat(config["n_vars"], config["clause_ratio"], rng)
    return _random_graph(config["n"], config["edge_prob"], rng)


def _task_detail(task: str, data: Any, config: dict[str, Any]) -> dict[str, Any]:
    if task == "sat_3sat":
        return {"n_vars": config["n_vars"], "n_clauses": len(data), "clauses": data}
    return {"n_nodes": config["n"], "n_colors": config["k"], "n_edges": len(data), "edges": [list(edge) for edge in data]}


def _recover_item050_pool(task: str, target: int, max_candidates: int, seed: int, config: dict[str, Any]) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    buckets: dict[str, list[dict[str, Any]]] = {band: [] for band in BANDS}
    for index in range(max_candidates):
        if all(len(rows) >= target for rows in buckets.values()):
            break
        data = _generate_instance(task, config, rng)
        reference = _solve_reference(task, data, config)
        if not reference.solved:
            continue
        band = _band(reference.reverts_needed)
        if len(buckets[band]) >= target:
            continue
        no_revert = _run_no_revert(task, data, config)
        buckets[band].append({
            "task": task,
            "instance_index": index,
            "band": band,
            "reverts_needed": reference.reverts_needed,
            "trace_length": reference.trace_length,
            "nodes_visited": reference.nodes_visited,
            "max_depth_observed": reference.max_depth,
            "contradiction_count": reference.contradictions,
            "no_revert_solved": no_revert.solved,
            **_task_detail(task, data, config),
        })
    return [row for band in BANDS for row in buckets[band]]


def _data_from_row(task: str, row: dict[str, Any]) -> Any:
    if task == "sat_3sat":
        return [list(clause) for clause in row["clauses"]]
    return [tuple(edge) for edge in row["edges"]]


def _run_no_revert(task: str, data: Any, config: dict[str, Any]) -> SolveResult:
    stats = {"trace": 0, "nodes": 0, "max_depth": 0, "contradictions": 0}
    assignment: dict[int, int] = {}
    for depth in range(config["n_vars"] + 2 if task == "sat_3sat" else config["n"] + 2):
        stats["nodes"] += 1
        stats["trace"] += 1
        stats["max_depth"] = max(stats["max_depth"], depth)
        state, current, choice, forced = _oracle_ops(task, data, config, assignment)
        stats["trace"] += forced
        if state == "SOLVED":
            return SolveResult(True, current, 0, stats["trace"], stats["nodes"], stats["max_depth"], stats["contradictions"])
        if state == "CONTRADICTION" or choice is None:
            stats["contradictions"] += int(state == "CONTRADICTION")
            return SolveResult(False, {}, 0, stats["trace"], stats["nodes"], stats["max_depth"], stats["contradictions"])
        var, values = choice
        assignment = {**current, var: values[0]}
    return SolveResult(False, {}, 0, stats["trace"], stats["nodes"], stats["max_depth"], stats["contradictions"])


def _capacity_dstar(task: str, arm: str, D: int, config: dict[str, Any]) -> float:
    if task == "sat_3sat":
        k_var, k_val = config["n_vars"], 2
    else:
        k_var, k_val = config["n"], config["k"]
    if arm == "rot_factored":
        return d_star_factored(D, k_var, k_val)
    return d_star_product(D, k_var * k_val)


def _encode_pair(task: str, var: int, value: int) -> tuple[int, int]:
    if task == "sat_3sat":
        return var - 1, value
    return var, value - 1


def _register_for(task: str, arm: str, D: int, seed: int, max_depth: int, config: dict[str, Any]) -> BoundSingleRegister | FactoredRegister:
    if task == "sat_3sat":
        k_var, k_val = config["n_vars"], 2
    else:
        k_var, k_val = config["n"], config["k"]
    if arm == "rot_factored":
        return FactoredRegister(D, k_var, k_val, max_depth, seed)
    return BoundSingleRegister(D, k_var, k_val, max_depth, seed)


class ScalarRegisterLoop:
    def __init__(self, task: str, data: Any, config: dict[str, Any], arm: str, spill: str, D: int, seed: int, node_cap: int):
        self.task = task
        self.data = data
        self.config = config
        self.arm = arm
        self.spill = spill
        self.D = D
        self.seed = seed
        self.node_cap = node_cap
        self.capacity_floor = math.floor(_capacity_dstar(task, arm, D, config)) if arm in STRUCTURED_ARMS else None
        self.register = _register_for(task, arm, D, seed, max(node_cap + 4, 32), config) if arm in STRUCTURED_ARMS else None
        self.overflow_stack: list[tuple[int, int, int]] = []
        self.stats = {"trace": 0, "nodes": 0, "applied_reverts": 0, "successful_reverts": 0, "decode_failures": 0, "overflow_entries": 0, "peak_depth": 0, "node_cap_exhausted": False, "capacity_exceeded": False}

    def push(self, level: int, var: int, value: int) -> bool:
        self.stats["peak_depth"] = max(self.stats["peak_depth"], level + 1)
        if self.arm == "kv_snapshot":
            return True
        if self.arm == "rot_no_revert":
            return True
        assert self.capacity_floor is not None and self.register is not None
        if level > self.capacity_floor:
            self.stats["overflow_entries"] += 1
            if self.spill == "spill_on":
                self.overflow_stack.append((level, var, value))
                return True
            self.stats["capacity_exceeded"] = True
            return False
        reg_var, reg_val = _encode_pair(self.task, var, value)
        self.register.push(level, reg_var, reg_val)
        return True

    def pop(self, level: int, var: int, value: int) -> bool:
        if self.arm in {"kv_snapshot", "rot_no_revert"}:
            self.stats["applied_reverts"] += 1
            self.stats["successful_reverts"] += 1
            return True
        assert self.capacity_floor is not None and self.register is not None
        self.stats["applied_reverts"] += 1
        if level > self.capacity_floor:
            if self.spill == "spill_on" and self.overflow_stack and self.overflow_stack[-1] == (level, var, value):
                self.overflow_stack.pop()
                self.stats["successful_reverts"] += 1
                return True
            self.stats["decode_failures"] += 1
            return False
        decoded_var, decoded_val, _ = self.register.pop(level)
        expected = _encode_pair(self.task, var, value)
        ok = (decoded_var, decoded_val) == expected
        self.stats["successful_reverts"] += int(ok)
        self.stats["decode_failures"] += int(not ok)
        return ok

    def run(self) -> RegisterEval:
        if self.arm == "rot_no_revert":
            no_revert = _run_no_revert(self.task, self.data, self.config)
            return RegisterEval(no_revert.solved, 0, no_revert.solved, 0, 0, no_revert.trace_length > self.node_cap, 0, "RECORDED")
        if self.arm == "kv_snapshot":
            reference = _solve_reference(self.task, self.data, self.config, node_cap=self.node_cap)
            bytes_used = max(1, reference.max_depth) * self._kv_entry_bytes()
            return RegisterEval(reference.solved, reference.reverts_needed, reference.solved, bytes_used, 0, not reference.solved, 0, "RECORDED")

        def dfs(assignment: dict[int, int], depth: int) -> bool:
            self.stats["nodes"] += 1
            self.stats["trace"] += 1
            if self.stats["trace"] > self.node_cap:
                self.stats["node_cap_exhausted"] = True
                return False
            state, current, choice, forced = _oracle_ops(self.task, self.data, self.config, assignment)
            self.stats["trace"] += forced
            if state == "CONTRADICTION":
                return False
            if state == "SOLVED":
                return True
            if choice is None:
                return False
            var, values = choice
            for value in values:
                if not self.push(depth, var, value):
                    return False
                solved = dfs({**current, var: value}, depth + 1)
                if solved:
                    return True
                if not self.pop(depth, var, value):
                    return False
            return False

        solved = dfs({}, 0)
        bytes_used = self.D * 4 + (self.stats["overflow_entries"] * 16 if self.spill == "spill_on" else 0)
        status = "RECORDED" if not self.stats["node_cap_exhausted"] else "NODE_CAP_EXHAUSTED"
        if self.stats["capacity_exceeded"] and self.spill == "spill_off":
            status = "CAPACITY_EXCEEDED_SPILL_OFF"
        if self.stats["decode_failures"]:
            status = "DECODE_FAILURE"
        return RegisterEval(solved, self.stats["applied_reverts"], self.stats["decode_failures"] == 0, bytes_used, self.stats["overflow_entries"], self.stats["node_cap_exhausted"], self.stats["decode_failures"], status)

    def _kv_entry_bytes(self) -> int:
        if self.task == "sat_3sat":
            return self.config["n_vars"] * 2 * 2
        return self.config["n"] * self.config["k"] * 2


def _stateless_oracle_ci(task: str, row: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    data = _data_from_row(task, row)
    if task == "sat_3sat":
        assignment_a = {1: 1, 2: 0}
        assignment_b = {2: 0, 1: 1}
    else:
        assignment_a = {0: 1, 1: 2}
        assignment_b = {1: 2, 0: 1}

    def output(assignment: dict[int, int]) -> bytes:
        state, current, choice, forced = _oracle_ops(task, data, config, assignment)
        payload = {"state": state, "assignment": sorted(current.items()), "choice": choice, "forced_count": forced}
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    left = output(assignment_a)
    right = output(assignment_b)
    return {"task": task, "passed": left == right, "bytes_left": left.decode("utf-8"), "bytes_right": right.decode("utf-8"), "history_a": list(assignment_a.items()), "history_b": list(assignment_b.items()), "source": SOURCE, "provenance": SOURCE}


def _pool_summaries(task: str, rows: list[dict[str, Any]], target: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    band_rows = []
    for band in BANDS:
        selected = [row for row in rows if row["band"] == band]
        band_rows.append({
            "task": task,
            "band": band,
            "n": len(selected),
            "target_n": target,
            "target_met": len(selected) >= target,
            "min_reverts_needed": min((row["reverts_needed"] for row in selected), default=None),
            "max_reverts_needed": max((row["reverts_needed"] for row in selected), default=None),
            "max_trace_length": max((row["trace_length"] for row in selected), default=0),
            "max_depth_observed": max((row["max_depth_observed"] for row in selected), default=0),
            "no_revert_solve_rate": sum(row["no_revert_solved"] for row in selected) / len(selected) if selected else None,
        })
    r3plus = [row for row in rows if row["band"] in {"R3-5", "R6+"}]
    task_summary = {
        "task": task,
        "selected_instances": len(rows),
        "target_per_band": target,
        "node_cap": max((row["trace_length"] for row in rows), default=0) + 1 if rows else None,
        "r3plus_no_revert_solve_rate": sum(row["no_revert_solved"] for row in r3plus) / len(r3plus) if r3plus else None,
        "pool_complete": all(row["target_met"] for row in band_rows),
    }
    return task_summary, band_rows


def _capacity_rows(configs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for task, config in configs.items():
        k_var = config["n_vars"] if task == "sat_3sat" else config["n"]
        k_val = 2 if task == "sat_3sat" else config["k"]
        for D in DS:
            rows.append({
                "task": task,
                "D": D,
                "K_var": k_var,
                "K_val": k_val,
                "bound_single_K_eff": k_var * k_val,
                "bound_single_d_star": d_star_product(D, k_var * k_val),
                "bound_single_d_star_floor": math.floor(d_star_product(D, k_var * k_val)),
                "factored_d_star": d_star_factored(D, k_var, k_val),
                "factored_d_star_floor": math.floor(d_star_factored(D, k_var, k_val)),
            })
    return rows


def _run_arm_grid(pools: dict[str, list[dict[str, Any]]], configs: dict[str, dict[str, Any]], task_summaries: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    episode_rows: list[dict[str, Any]] = []
    cell_rows: list[dict[str, Any]] = []
    for task, rows in pools.items():
        node_cap = int(task_summaries[task]["node_cap"])
        config = configs[task]
        by_band = {band: [row for row in rows if row["band"] == band] for band in BANDS}
        for D in DS:
            for seed in SEEDS:
                for band, band_rows in by_band.items():
                    arm_specs: list[tuple[str, str]] = [(arm, spill) for arm in STRUCTURED_ARMS for spill in ("spill_off", "spill_on")]
                    arm_specs.extend((arm, "not_applicable") for arm in CONTROL_ARMS)
                    for arm, spill in arm_specs:
                        if arm == "gru":
                            cell_rows.append(_gru_audit_row(task, band, D, seed, len(band_rows)))
                            continue
                        evals = []
                        for row in band_rows:
                            data = _data_from_row(task, row)
                            if arm in STRUCTURED_ARMS:
                                result = ScalarRegisterLoop(task, data, config, arm, spill, D, seed, node_cap).run()
                            elif arm == "rot_no_revert":
                                no_revert = _run_no_revert(task, data, config)
                                result = RegisterEval(no_revert.solved, 0, no_revert.solved, 0, 0, no_revert.trace_length > node_cap, 0, "RECORDED")
                            else:
                                reference = _solve_reference(task, data, config, node_cap=node_cap)
                                bytes_used = max(1, int(row["max_depth_observed"])) * (config["n_vars"] * 2 * 2 if task == "sat_3sat" else config["n"] * config["k"] * 2)
                                result = RegisterEval(reference.solved, reference.reverts_needed, reference.solved, bytes_used, 0, not reference.solved, 0, "RECORDED")
                            evals.append(result)
                            episode_rows.append({
                                "track": "E1_cross_task_scalar_stage_a",
                                "source": SOURCE,
                                "task": task,
                                "instance_index": row["instance_index"],
                                "band": band,
                                "arm": arm,
                                "spill": spill,
                                "D": D,
                                "seed": seed,
                                "solve": result.solved,
                                "applied_reverts": result.applied_reverts,
                                "revert_success": result.revert_success,
                                "peak_register_bytes": result.peak_register_bytes,
                                "overflow_entries": result.overflow_entries,
                                "node_cap_exhaustion": result.node_cap_exhausted,
                                "status": result.status,
                            })
                        cell_rows.append(_aggregate_cell(task, arm, spill, band, D, seed, band_rows, evals, config))
    return cell_rows, episode_rows


def _gru_audit_row(task: str, band: str, D: int, seed: int, n: int) -> dict[str, Any]:
    return {
        "track": "E1_cross_task_scalar_stage_a",
        "source": SOURCE,
        "task": task,
        "arm": "gru",
        "spill": "not_applicable",
        "band": band,
        "D": D,
        "seed": seed,
        "n": n,
        "solve_rate": None,
        "applied_reverts": None,
        "revert_success_rate": None,
        "peak_register_bytes": None,
        "overflow_entries": None,
        "node_cap_exhaustions": None,
        "capacity_d_star_floor": None,
        "gru_audit_pass": False,
        "gru_converged": False,
        "gru_training_curve_ref": "",
        "figure_included": False,
        "status": "INCOMPLETE_AUDIT_RED",
        "provenance": SOURCE,
    }


def _aggregate_cell(task: str, arm: str, spill: str, band: str, D: int, seed: int, rows: list[dict[str, Any]], evals: list[RegisterEval], config: dict[str, Any]) -> dict[str, Any]:
    n = len(evals)
    nonzero_revert_den = sum(1 for row in rows if int(row["reverts_needed"]) > 0)
    capacity = math.floor(_capacity_dstar(task, arm, D, config)) if arm in STRUCTURED_ARMS else None
    return {
        "track": "E1_cross_task_scalar_stage_a",
        "source": SOURCE,
        "task": task,
        "arm": arm,
        "spill": spill,
        "band": band,
        "D": D,
        "seed": seed,
        "n": n,
        "solve_rate": sum(result.solved for result in evals) / max(n, 1),
        "applied_reverts": sum(result.applied_reverts for result in evals),
        "mean_applied_reverts": sum(result.applied_reverts for result in evals) / max(n, 1),
        "revert_success_rate": sum(result.revert_success and row["reverts_needed"] > 0 for result, row in zip(evals, rows)) / max(nonzero_revert_den, 1),
        "peak_register_bytes": max((result.peak_register_bytes for result in evals), default=0),
        "overflow_entries": sum(result.overflow_entries for result in evals),
        "node_cap_exhaustions": sum(result.node_cap_exhausted for result in evals),
        "decode_failures": sum(result.decode_failures for result in evals),
        "capacity_d_star_floor": capacity,
        "figure_included": True,
        "status": "RECORDED",
        "provenance": SOURCE,
    }


def _law_transfer_rows(cell_rows: list[dict[str, Any]], pools: dict[str, list[dict[str, Any]]], configs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for task, pool_rows in pools.items():
        for arm in STRUCTURED_ARMS:
            for D in DS:
                cap = math.floor(_capacity_dstar(task, arm, D, configs[task]))
                for band in BANDS:
                    band_rows = [row for row in pool_rows if row["band"] == band]
                    expected = sum(int(row["max_depth_observed"]) <= cap for row in band_rows) / max(len(band_rows), 1)
                    observed_values = sorted({row["solve_rate"] for row in cell_rows if row["task"] == task and row["arm"] == arm and row["spill"] == "spill_off" and row["D"] == D and row["band"] == band and row["figure_included"]})
                    observed = observed_values[0] if len(observed_values) == 1 else None
                    rows.append({
                        "task": task,
                        "arm": arm,
                        "D": D,
                        "band": band,
                        "n": len(band_rows),
                        "predicted_d_star_floor": cap,
                        "fraction_required_depth_le_dstar": expected,
                        "observed_spill_off_solve_rate": observed,
                        "on_y_equals_x": observed is not None and abs(observed - expected) < 1e-12,
                        "source": SOURCE,
                        "provenance": SOURCE,
                    })
    return rows


def _acceptance(cell_rows: list[dict[str, Any]], law_rows: list[dict[str, Any]], stateless_rows: list[dict[str, Any]]) -> dict[str, Any]:
    r3_structured = [row for row in cell_rows if row["figure_included"] and row["arm"] in STRUCTURED_ARMS and row["band"] in {"R3-5", "R6+"}]
    r3_no_revert = [row for row in cell_rows if row["figure_included"] and row["arm"] == "rot_no_revert" and row["band"] in {"R3-5", "R6+"}]
    gru_rows = [row for row in cell_rows if row["arm"] == "gru"]
    return {
        "rot_r3plus_any_positive": any(float(row["solve_rate"]) > 0 for row in r3_structured),
        "no_revert_r3plus_near_zero": all(float(row["solve_rate"]) <= 0.05 for row in r3_no_revert),
        "law_transfer_on_y_equals_x": all(row["on_y_equals_x"] for row in law_rows),
        "stateless_oracle_ci_passed": all(row["passed"] for row in stateless_rows),
        "gru_audit_red_excluded": bool(gru_rows) and all(row["status"] == "INCOMPLETE_AUDIT_RED" and row["figure_included"] is False and row["solve_rate"] is None for row in gru_rows),
    }


def _plot_panels(cell_rows: list[dict[str, Any]], law_rows: list[dict[str, Any]]) -> dict[str, str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    PANEL_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for task in TASKS:
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
        sep_rows = [row for row in cell_rows if row["task"] == task and row["figure_included"] and row["D"] == 512 and row["seed"] == 42]
        labels = []
        values = []
        for arm in ["rot_bound_single", "rot_factored", "rot_no_revert", "kv_snapshot"]:
            for band in BANDS:
                matches = [row for row in sep_rows if row["arm"] == arm and row["band"] == band and (row["spill"] == "spill_off" or row["spill"] == "not_applicable")]
                if matches:
                    labels.append(f"{arm}\n{band}")
                    values.append(matches[0]["solve_rate"])
        axes[0].bar(range(len(values)), values, color="#2563eb")
        axes[0].set_ylim(-0.05, 1.05)
        axes[0].set_ylabel("solve rate")
        axes[0].set_title(f"{task} separation, D=512 seed=42")
        axes[0].set_xticks(range(len(values)))
        axes[0].set_xticklabels(labels, rotation=80, ha="right", fontsize=7)
        task_law = [row for row in law_rows if row["task"] == task]
        xs = [row["fraction_required_depth_le_dstar"] for row in task_law]
        ys = [row["observed_spill_off_solve_rate"] for row in task_law]
        axes[1].plot([0, 1], [0, 1], color="#111827", linewidth=1, linestyle="--")
        axes[1].scatter(xs, ys, color="#dc2626")
        axes[1].set_xlim(-0.05, 1.05)
        axes[1].set_ylim(-0.05, 1.05)
        axes[1].set_xlabel("fraction required depth <= d*(D)")
        axes[1].set_ylabel("observed spill_off solve")
        axes[1].set_title(f"{task} law transfer")
        axes[1].grid(alpha=0.25)
        fig.tight_layout()
        path = PANEL_DIR / f"{task}_figure4_scalar_panels.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        paths[task] = _rel(path)
    return paths


def _build_item(results: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "log_item_contract_v1",
        "item_number": "050",
        "name": "Post-review E1 scalar cross-task generalization",
        "status": results["status"],
        "purpose": "Run amended E1 on SAT and graph coloring with the scalar Stage A register loop, reusing the item050 pool/caps and removing the non-applicable batched-equivalence gate.",
        "code_added_used": [
            {"path": "experiments/e1_cross_task_generalization.py", "change": "Runs scalar SAT/coloring Stage A register arms, stateless-oracle CI, law-transfer panels, and GRU audit-red exclusion."},
            {"path": "analysis/validate_outputs.py", "change": "Validates amended E1 scalar Figure 4 discipline."},
        ],
        "commands": [{"command": ".venv/bin/python -m experiments.e1_cross_task_generalization --reuse-item050", "purpose": "Run amended E1 scalar fast path and regenerate Item050."}],
        "artifacts": [_rel(RESULTS_PATH), _rel(ITEM_PATH), *results["panel_artifacts"].values()],
        "provenance": {"repo": str(REPO_ROOT), "generated_at": results["generated_at"], "source": SOURCE, "binning_key": "reverts_needed", "pool_reuse": results["pool_reuse"]},
        "result_tables": {
            "task_pool_summary": {"columns": ["task", "selected_instances", "target_per_band", "node_cap", "r3plus_no_revert_solve_rate", "pool_complete"], "rows": results["task_pool_summary"]},
            "band_summary": {"columns": ["task", "band", "n", "target_n", "target_met", "min_reverts_needed", "max_reverts_needed", "max_trace_length", "max_depth_observed", "no_revert_solve_rate"], "rows": results["band_summary"]},
            "capacity_predictions": {"columns": ["task", "D", "K_var", "K_val", "bound_single_K_eff", "bound_single_d_star", "bound_single_d_star_floor", "factored_d_star", "factored_d_star_floor"], "rows": results["capacity_predictions"]},
            "stateless_oracle_ci": {"columns": ["task", "passed", "history_a", "history_b", "source", "provenance"], "rows": results["stateless_oracle_ci"]},
            "figure4_separation": {"columns": ["track", "source", "task", "arm", "spill", "band", "D", "seed", "n", "solve_rate", "applied_reverts", "revert_success_rate", "peak_register_bytes", "overflow_entries", "node_cap_exhaustions", "capacity_d_star_floor", "figure_included", "status", "provenance"], "rows": results["figure4_separation"]},
            "law_transfer": {"columns": ["task", "arm", "D", "band", "n", "predicted_d_star_floor", "fraction_required_depth_le_dstar", "observed_spill_off_solve_rate", "on_y_equals_x", "source", "provenance"], "rows": results["law_transfer"]},
        },
        "honesty": {"does_not_establish": "GRU is not reported as a collapse datum; it is audit-red and excluded until trained to the fairness budget with nonzero bytes and a curve."},
        "decision": {
            "outcome": results["status"],
            "gate_outcomes": [
                {"gate": "stateless_oracle_ci", "outcome": "PASS" if results["acceptance"]["stateless_oracle_ci_passed"] else "FAIL", "number": "2/2 tasks"},
                {"gate": "r3plus_rot_vs_no_revert", "outcome": "PASS" if results["acceptance"]["rot_r3plus_any_positive"] and results["acceptance"]["no_revert_r3plus_near_zero"] else "FAIL", "number": f"rot_positive={results['acceptance']['rot_r3plus_any_positive']}; no_revert_near_zero={results['acceptance']['no_revert_r3plus_near_zero']}"},
                {"gate": "law_transfer_y_equals_x", "outcome": "PASS" if results["acceptance"]["law_transfer_on_y_equals_x"] else "FAIL", "number": str(results["acceptance"]["law_transfer_on_y_equals_x"])},
                {"gate": "gru_audit", "outcome": "INCOMPLETE_AUDIT_RED", "number": "excluded_from_figure_no_fabricated_zero"},
            ],
            "next_step_routing": {"ready": ["minimum_viable_figure4_rot_no_revert_kv"], "defer": ["gru_until_audited"]},
            "next_step": "Train/audit the E1 GRU fairness-budget cells before adding GRU rows to Figure 4.",
        },
    }


def run(target_per_band: int = 64, max_candidates: int = 5000, seed: int = 20260609, sat_n_vars: int = 18, sat_clause_ratio: float = 4.2, graph_n: int = 16, graph_k: int = 4, graph_edge_prob: float = 0.45) -> dict[str, Any]:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    configs = {
        "sat_3sat": {"n_vars": sat_n_vars, "clause_ratio": sat_clause_ratio},
        "graph_coloring": {"n": graph_n, "k": graph_k, "edge_prob": graph_edge_prob},
    }
    pools = {
        "sat_3sat": _recover_item050_pool("sat_3sat", target_per_band, max_candidates, seed, configs["sat_3sat"]),
        "graph_coloring": _recover_item050_pool("graph_coloring", target_per_band, max_candidates, seed + 1, configs["graph_coloring"]),
    }
    task_summary_rows = []
    band_summary_rows = []
    task_summaries: dict[str, dict[str, Any]] = {}
    for task, rows in pools.items():
        summary, bands = _pool_summaries(task, rows, target_per_band)
        task_summaries[task] = summary
        task_summary_rows.append(summary)
        band_summary_rows.extend(bands)
    stateless_rows = [_stateless_oracle_ci(task, pools[task][0], configs[task]) for task in TASKS]
    cell_rows, episode_rows = _run_arm_grid(pools, configs, task_summaries)
    figure_rows = [row for row in cell_rows if row["figure_included"] or row["arm"] == "gru"]
    law_rows = _law_transfer_rows(cell_rows, pools, configs)
    acceptance = _acceptance(cell_rows, law_rows, stateless_rows)
    panel_paths = _plot_panels(cell_rows, law_rows)
    status = "E1_SCALAR_FIGURE4_READY_WITH_GRU_AUDIT_RED" if acceptance["stateless_oracle_ci_passed"] and acceptance["no_revert_r3plus_near_zero"] and acceptance["law_transfer_on_y_equals_x"] else "E1_SCALAR_FIGURE4_DEVIATION_RECORDED"
    results = {
        "module": "post_review_e1_cross_task_generalization",
        "generated_at": _now(),
        "status": status,
        "discipline": {"binning_key": "reverts_needed", "node_cap_rule": "reused item050 cap", "batched_engine_required": False, "batched_equivalence_gate_applies": False, "source": SOURCE},
        "pool_reuse": {"method": "deterministic_replay_of_item050_seed_and_config", "reason": "prior Item050 persisted summaries and samples but not full clauses/edges", "seed": seed, "target_per_band": target_per_band, "max_candidates": max_candidates},
        "generation_config": {"target_per_band": target_per_band, "max_candidates": max_candidates, "seed": seed, "sat_n_vars": sat_n_vars, "sat_clause_ratio": sat_clause_ratio, "graph_n": graph_n, "graph_k": graph_k, "graph_edge_prob": graph_edge_prob},
        "task_pool_summary": task_summary_rows,
        "band_summary": band_summary_rows,
        "capacity_predictions": _capacity_rows(configs),
        "stateless_oracle_ci": stateless_rows,
        "figure4_separation": figure_rows,
        "law_transfer": law_rows,
        "episode_records": episode_rows,
        "pool_rows": {task: rows for task, rows in pools.items()},
        "panel_artifacts": panel_paths,
        "acceptance": acceptance,
        "figure4_status": status,
    }
    _write_json(RESULTS_PATH, results)
    _write_json(ITEM_PATH, _build_item(results))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run amended E1 scalar cross-task Figure 4.")
    parser.add_argument("--reuse-item050", action="store_true", help="Documented no-op: pools are recovered by deterministic replay of Item050 config.")
    parser.add_argument("--target-per-band", type=int, default=64)
    parser.add_argument("--max-candidates", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260609)
    parser.add_argument("--sat-n-vars", type=int, default=18)
    parser.add_argument("--sat-clause-ratio", type=float, default=4.2)
    parser.add_argument("--graph-n", type=int, default=16)
    parser.add_argument("--graph-k", type=int, default=4)
    parser.add_argument("--graph-edge-prob", type=float, default=0.45)
    args = parser.parse_args()
    run(args.target_per_band, args.max_candidates, args.seed, args.sat_n_vars, args.sat_clause_ratio, args.graph_n, args.graph_k, args.graph_edge_prob)


if __name__ == "__main__":
    main()
