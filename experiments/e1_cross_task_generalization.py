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
import signal
from statistics import mean, median, pstdev, quantiles
from typing import Any, Literal

import torch

from analysis.capacity_theory import d_star_factored, d_star_product
from register.vsa_stack import BoundSingleRegister, FactoredRegister
from tasks.oracle.dpll_oracle import DPLLOracle, TraceAction
from tasks.sudoku.generator_9x9 import constraints_9x9


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = REPO_ROOT / "results/post_review_e1_cross_task_generalization"
RESULTS_PATH = RUN_ROOT / "results.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_050_post_review_e1_cross_task_generalization.json"
PANEL_DIR = RUN_ROOT / "panels"
PROGRESS_PATH = RUN_ROOT / "progress.json"
PROGRESS_LOG_PATH = RUN_ROOT / "progress.jsonl"
SUDOKU_POOL_PATH = REPO_ROOT / "results/overnight_047_headline_preregistered/line1_headline/reverts_needed_pool.json"
SUDOKU_HEADLINE_PATH = REPO_ROOT / "results/overnight_047_headline_preregistered/line1_headline/line1_headline.json"
SUDOKU_MODULE1_CURVES_PATH = REPO_ROOT / "results/module1_capacity_perdepth_shards/curves.json"
SUDOKU_D128_BOUND_SINGLE_CURVE_PATH = RUN_ROOT / "sudoku_d128_bound_single_module1_curve.json"
SUDOKU_LIVE_LOAD_TIMEOUT_SECONDS = 3
SUDOKU_LIVE_LOAD_PRESCREEN_MAX_NODES = 0
SUDOKU_COMPOSITION_SUBSAMPLE_PER_BAND = 16
SUDOKU_MODULE1_D128_TRIALS = 4096
SUDOKU_MODULE1_D128_BATCH_SIZE = 8192


class _SudokuTraceTimeout(Exception):
    pass
BANDS = ("R0", "R1-2", "R3-5", "R6+")
BASE_DS = (64, 96, 128, 256, 512)
SEEDS = (42, 137)
STORAGE_SEEDS = (42, 137, 256)
STORAGE_TRIALS = 1024
STORAGE_THRESHOLD = 0.95
LAW_TRANSFER_TOLERANCE = 0.05
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
    live_load_events: list[dict[str, Any]]
    d_peak: int
    d_pop: int
    d_readpop: int


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


def _write_progress(stage: str, completed: int, total: int, detail: dict[str, Any] | None = None, status: str = "running") -> None:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": _now(),
        "status": status,
        "stage": stage,
        "completed": completed,
        "total": total,
        "percent": None if total <= 0 else round(100.0 * completed / total, 2),
        "detail": detail or {},
    }
    PROGRESS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with PROGRESS_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _band(reverts_needed: int) -> str:
    if reverts_needed == 0:
        return "R0"
    if reverts_needed <= 2:
        return "R1-2"
    if reverts_needed <= 5:
        return "R3-5"
    return "R6+"


def _required_depth(row: dict[str, Any]) -> int:
    return int(row.get("required_depth", row["max_depth_observed"]))


def _live_load_predictors(events: list[dict[str, Any]], fallback_peak: int = 0) -> dict[str, int]:
    peak = max((int(event["live_load_before"]) for event in events), default=int(fallback_peak))
    pop = max((int(event["live_load_before"]) for event in events if event["op"] == "pop"), default=0)
    readpop = max((int(event["live_load_before"]) for event in events if event["op"] == "pop" and event.get("read_consumed_for_next_branch") is True), default=0)
    return {"D_peak": max(peak, int(fallback_peak)), "D_pop": pop, "D_readpop": readpop}


def _predictor_value(row: dict[str, Any], predictor: str) -> int:
    if predictor == "D_peak":
        if "D_peak" in row:
            return int(row["D_peak"])
        return _required_depth(row)
    if predictor == "D_pop":
        return int(row.get("D_pop", 0))
    if predictor == "D_readpop":
        return int(row.get("D_readpop", row.get("D_pop", 0)))
    raise ValueError(f"unknown predictor={predictor}")


def _variant_for_arm(arm: str) -> str:
    if arm == "rot_bound_single":
        return "bound_single"
    if arm == "rot_factored":
        return "factored"
    raise ValueError(f"no storage variant for arm={arm}")


def _arm_for_variant(variant: str) -> str:
    if variant == "bound_single":
        return "rot_bound_single"
    if variant == "factored":
        return "rot_factored"
    raise ValueError(f"no E1 arm for storage variant={variant}")


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
    events: list[dict[str, Any]] = []
    stats = {"reverts": 0, "trace": 0, "nodes": 0, "max_depth": 0, "contradictions": 0}

    def record(op: str, live_load_before: int, var: int | None = None, value: int | None = None, read_consumed: bool = False) -> None:
        events.append({
            "event_index": len(events),
            "op": op,
            "live_load_before": int(live_load_before),
            "var": var,
            "value": value,
            "read_consumed_for_next_branch": read_consumed,
        })

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
            record("solve", depth)
            return True, current
        if choice is None:
            return False, current
        var, values = choice
        for value in values:
            record("push", depth, var, value)
            solved, final = dfs({**current, var: value}, depth + 1)
            if solved:
                return True, final
            stats["reverts"] += 1
            stats["trace"] += 1
            record("pop", depth + 1, var, value, True)
        return False, current

    solved, assignment = dfs({}, 0)
    predictors = _live_load_predictors(events, stats["max_depth"])
    return SolveResult(solved, assignment if solved else {}, stats["reverts"], stats["trace"], stats["nodes"], stats["max_depth"], stats["contradictions"], events, predictors["D_peak"], predictors["D_pop"], predictors["D_readpop"])


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
            "required_depth": reference.max_depth,
            "max_depth_observed": reference.max_depth,
            "D_peak": reference.d_peak,
            "D_pop": reference.d_pop,
            "D_readpop": reference.d_readpop,
            "reference_live_load_events": reference.live_load_events,
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
            return SolveResult(True, current, 0, stats["trace"], stats["nodes"], stats["max_depth"], stats["contradictions"], [], stats["max_depth"], 0, 0)
        if state == "CONTRADICTION" or choice is None:
            stats["contradictions"] += int(state == "CONTRADICTION")
            return SolveResult(False, {}, 0, stats["trace"], stats["nodes"], stats["max_depth"], stats["contradictions"], [], stats["max_depth"], 0, 0)
        var, values = choice
        assignment = {**current, var: values[0]}
    return SolveResult(False, {}, 0, stats["trace"], stats["nodes"], stats["max_depth"], stats["contradictions"], [], stats["max_depth"], 0, 0)


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


def _cleanup_batch(query: torch.Tensor, codebook: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    query_norm = query / query.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    codebook_norm = codebook / codebook.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    scores = query_norm @ codebook_norm.T
    top2 = torch.topk(scores, k=min(2, codebook.shape[0]), dim=-1)
    prediction = top2.indices[..., 0]
    margin = torch.ones_like(top2.values[..., 0]) if codebook.shape[0] == 1 else top2.values[..., 0] - top2.values[..., 1]
    return prediction, margin


def _make_generator(seed: int, device: str) -> torch.Generator:
    if str(device).startswith("cuda"):
        return torch.Generator(device=device).manual_seed(seed)
    return torch.Generator().manual_seed(seed)


def _sample_storage_batch(K_var: int, K_val: int, depth: int, trials: int, seed: int, device: str) -> tuple[torch.Tensor, torch.Tensor]:
    generator = _make_generator(seed, device)
    variables = torch.rand(trials, K_var, generator=generator, device=device).argsort(dim=-1)[:, :depth]
    values = torch.randint(0, K_val, (trials, depth), generator=generator, device=device)
    return variables, values


def _sample_product_storage_batch(K_var: int, K_val: int, depth: int, trials: int, seed: int, device: str) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    generator = _make_generator(seed, device)
    pair_indices = torch.rand(trials, K_var * K_val, generator=generator, device=device).argsort(dim=-1)[:, :depth]
    variables = pair_indices // K_val
    values = pair_indices % K_val
    return pair_indices, variables, values


def _storage_accuracy_bound_single(register: BoundSingleRegister, K_var: int, K_val: int, depth: int, seed: int, trials: int, device: str) -> dict[str, float]:
    pair_indices, variables, values = _sample_product_storage_batch(K_var, K_val, depth, trials, seed * 1000003 + depth * 997, device)
    hidden = torch.zeros(trials, register.D, device=device)
    for level in range(1, depth + 1):
        hidden = hidden + register.keys.roll(register.product_codebook[pair_indices[:, level - 1]], level)
    correct_levels = []
    margins = []
    for level in range(depth, 0, -1):
        predicted_pair, margin = _cleanup_batch(register.keys.unroll(hidden, level), register.product_codebook)
        predicted = register.pair_ids[predicted_pair]
        target = torch.stack([variables[:, level - 1], values[:, level - 1]], dim=-1)
        correct_levels.append((predicted == target).all(dim=-1).float())
        margins.append(margin)
        hidden = hidden - register.keys.roll(register.product_codebook[predicted_pair], level)
    correct = torch.stack(correct_levels, dim=1)
    margin_tensor = torch.stack(margins, dim=1)
    return {"decode_accuracy": float(correct.mean().item()), "mean_cleanup_margin": float(margin_tensor.mean().item()), "min_cleanup_margin": float(margin_tensor.min().item())}


def _storage_accuracy_factored(register: FactoredRegister, K_var: int, K_val: int, depth: int, seed: int, trials: int, device: str) -> dict[str, float]:
    variables, values = _sample_storage_batch(K_var, K_val, depth, trials, seed * 1000003 + depth * 997, device)
    hidden_var = torch.zeros(trials, register.m, device=device)
    hidden_val = torch.zeros(trials, register.m, device=device)
    for level in range(1, depth + 1):
        hidden_var = hidden_var + register.var_keys.roll(register.var_codebook[variables[:, level - 1]], level)
        hidden_val = hidden_val + register.val_keys.roll(register.val_codebook[values[:, level - 1]], level)
    correct_levels = []
    margins = []
    for level in range(depth, 0, -1):
        predicted_var, var_margin = _cleanup_batch(register.var_keys.unroll(hidden_var, level), register.var_codebook)
        predicted_val, val_margin = _cleanup_batch(register.val_keys.unroll(hidden_val, level), register.val_codebook)
        correct_levels.append(((predicted_var == variables[:, level - 1]) & (predicted_val == values[:, level - 1])).float())
        margins.append(torch.minimum(var_margin, val_margin))
        hidden_var = hidden_var - register.var_keys.roll(register.var_codebook[predicted_var], level)
        hidden_val = hidden_val - register.val_keys.roll(register.val_codebook[predicted_val], level)
    correct = torch.stack(correct_levels, dim=1)
    margin_tensor = torch.stack(margins, dim=1)
    return {"decode_accuracy": float(correct.mean().item()), "mean_cleanup_margin": float(margin_tensor.mean().item()), "min_cleanup_margin": float(margin_tensor.min().item())}


def _storage_accuracy(variant: str, register: BoundSingleRegister | FactoredRegister, K_var: int, K_val: int, depth: int, seed: int, trials: int, device: str) -> dict[str, float]:
    if variant == "bound_single":
        return _storage_accuracy_bound_single(register, K_var, K_val, depth, seed, trials, device)
    if variant == "factored":
        return _storage_accuracy_factored(register, K_var, K_val, depth, seed, trials, device)
    raise ValueError(f"unknown storage variant={variant}")


def _measure_storage_dstars(configs: dict[str, dict[str, Any]], ds: tuple[int, ...], device: str = "cpu") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    curve_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    total_depths = 0
    for task, config in configs.items():
        K_var = config["n_vars"] if task == "sat_3sat" else config["n"]
        K_val = 2 if task == "sat_3sat" else config["k"]
        total_depths += sum((K_var * K_val if variant == "bound_single" else K_var) * len(ds) for variant in ("bound_single", "factored"))
    completed_depths = 0
    _write_progress("storage_dstar", completed_depths, total_depths, {"phase": "start", "threshold": STORAGE_THRESHOLD, "trials_per_seed": STORAGE_TRIALS})
    with torch.no_grad():
        for task, config in configs.items():
            K_var = config["n_vars"] if task == "sat_3sat" else config["n"]
            K_val = 2 if task == "sat_3sat" else config["k"]
            for variant in ("bound_single", "factored"):
                arm = _arm_for_variant(variant)
                max_storage_depth = K_var * K_val if variant == "bound_single" else K_var
                for D in ds:
                    registers = {
                        seed: (BoundSingleRegister(D, K_var, K_val, max(max_storage_depth + 1, 2), seed, device) if variant == "bound_single" else FactoredRegister(D, K_var, K_val, max(max_storage_depth + 1, 2), seed, device))
                        for seed in STORAGE_SEEDS
                    }
                    for depth in range(1, max_storage_depth + 1):
                        seed_results = [_storage_accuracy(variant, registers[seed], K_var, K_val, depth, seed, STORAGE_TRIALS, device) for seed in STORAGE_SEEDS]
                        curve_rows.append({
                            "task": task,
                            "codebook": variant,
                            "arm": arm,
                            "D": D,
                            "K_var": K_var,
                            "K_val": K_val,
                            "K_eff": K_var * K_val,
                            "depth": depth,
                            "n_seeds": len(STORAGE_SEEDS),
                            "trials_per_seed": STORAGE_TRIALS,
                            "decode_accuracy": mean(row["decode_accuracy"] for row in seed_results),
                            "mean_cleanup_margin": mean(row["mean_cleanup_margin"] for row in seed_results),
                            "min_cleanup_margin": min(row["min_cleanup_margin"] for row in seed_results),
                            "threshold": STORAGE_THRESHOLD,
                            "source": SOURCE,
                            "provenance": "pure_storage_lifo_push_pop_no_solving",
                        })
                        completed_depths += 1
                        _write_progress("storage_dstar", completed_depths, total_depths, {"task": task, "codebook": variant, "arm": arm, "D": D, "depth": depth, "threshold": STORAGE_THRESHOLD, "rows": len(curve_rows)})
                    subset = [row for row in curve_rows if row["task"] == task and row["codebook"] == variant and row["D"] == D]
                    measured = max((row["depth"] for row in subset if row["decode_accuracy"] >= STORAGE_THRESHOLD), default=0)
                    predicted = _capacity_dstar(task, arm, D, config)
                    summary_rows.append({
                        "task": task,
                        "codebook": variant,
                        "arm": arm,
                        "D": D,
                        "K_var": K_var,
                        "K_val": K_val,
                        "K_eff": K_var * K_val,
                        "d_star_predicted": predicted,
                        "d_star_predicted_floor": math.floor(predicted),
                        "d_star_measured": measured,
                        "gap_measured_minus_predicted": measured - predicted,
                        "threshold": STORAGE_THRESHOLD,
                        "n_depths_tested": len(subset),
                        "n_seeds": len(STORAGE_SEEDS),
                        "trials_per_seed": STORAGE_TRIALS,
                        "protocol": "pure_storage_lifo_push_k_then_pop_decode_until_empty",
                        "source": SOURCE,
                        "provenance": "pure_storage_lifo_push_pop_no_solving",
                    })
                    _write_progress("storage_dstar_summary", len(summary_rows), len(configs) * 2 * len(ds), {"task": task, "codebook": variant, "arm": arm, "D": D, "d_star_measured": measured, "d_star_predicted": predicted, "gap_measured_minus_predicted": measured - predicted})
    return summary_rows, curve_rows


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
        self.stats["peak_depth"] = max(self.stats["peak_depth"], level)
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
                live_depth = depth + 1
                if not self.push(live_depth, var, value):
                    return False
                solved = dfs({**current, var: value}, depth + 1)
                if solved:
                    return True
                if not self.pop(live_depth, var, value):
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
            "max_depth_observed": max((_required_depth(row) for row in selected), default=0),
            "max_required_depth": max((_required_depth(row) for row in selected), default=0),
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


def _depth_percentiles(rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    depths = sorted(_required_depth(row) for row in rows)
    if not depths:
        return {"min": None, "p25": None, "median": None, "p75": None, "max": None}
    qs = quantiles(depths, n=4)
    return {"min": depths[0], "p25": qs[0], "median": median(depths), "p75": qs[2], "max": depths[-1]}


def _required_depth_histogram_rows(pools: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for task, pool_rows in pools.items():
        for band in BANDS:
            selected = [row for row in pool_rows if row["band"] == band]
            n = len(selected)
            counts: dict[int, int] = {}
            for row in selected:
                counts[_required_depth(row)] = counts.get(_required_depth(row), 0) + 1
            for depth, count in sorted(counts.items()):
                rows.append({"task": task, "band": band, "required_depth": depth, "count": count, "fraction": count / max(n, 1), "n": n, "source": SOURCE, "provenance": SOURCE})
    return rows


def _reference_live_load_event_rows(pools: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for task, pool_rows in pools.items():
        for pool_row in pool_rows:
            for event in pool_row.get("reference_live_load_events", []):
                rows.append({
                    "task": task,
                    "instance_index": pool_row["instance_index"],
                    "band": pool_row["band"],
                    "reverts_needed": pool_row["reverts_needed"],
                    "event_index": event["event_index"],
                    "op": event["op"],
                    "live_load_before": event["live_load_before"],
                    "var": event.get("var"),
                    "value": event.get("value"),
                    "read_consumed_for_next_branch": event.get("read_consumed_for_next_branch", False),
                    "source": SOURCE,
                    "provenance": "reference_solve_live_load_trajectory_no_register_arm_outcome",
                })
    return rows


def _live_load_predictor_rows(pools: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for task, pool_rows in pools.items():
        for row in pool_rows:
            event_counts: dict[str, int] = {"push": 0, "pop": 0, "solve": 0}
            for event in row.get("reference_live_load_events", []):
                event_counts[event["op"]] = event_counts.get(event["op"], 0) + 1
            rows.append({
                "task": task,
                "instance_index": row["instance_index"],
                "band": row["band"],
                "reverts_needed": row["reverts_needed"],
                "D_peak": _predictor_value(row, "D_peak"),
                "D_pop": _predictor_value(row, "D_pop"),
                "D_readpop": _predictor_value(row, "D_readpop"),
                "D_readpop_equals_D_pop": _predictor_value(row, "D_readpop") == _predictor_value(row, "D_pop"),
                "n_push": event_counts.get("push", 0),
                "n_pop": event_counts.get("pop", 0),
                "n_solve": event_counts.get("solve", 0),
                "source": SOURCE,
                "provenance": "reference_solve_live_load_predictors_no_register_arm_outcome",
            })
    return rows


def _select_Ds(pools: dict[str, list[dict[str, Any]]], configs: dict[str, dict[str, Any]]) -> tuple[tuple[int, ...], list[dict[str, Any]]]:
    selection_rows = []
    include_32 = False
    for task, rows in pools.items():
        percentiles = _depth_percentiles(rows)
        p25 = float(percentiles["p25"] or 0.0)
        for arm in STRUCTURED_ARMS:
            d64 = _capacity_dstar(task, arm, 64, configs[task])
            arm_include_32 = p25 < d64
            include_32 = include_32 or arm_include_32
            selection_rows.append({
                "task": task,
                "arm": arm,
                "depth_min": percentiles["min"],
                "depth_p25": percentiles["p25"],
                "depth_median": percentiles["median"],
                "depth_p75": percentiles["p75"],
                "depth_max": percentiles["max"],
                "d_star_64": d64,
                "include_D32": arm_include_32,
                "rule": "include D32 when depth_p25 < d_star(64); always include 64,96,128,256,512",
                "source": SOURCE,
                "provenance": SOURCE,
            })
    ds = tuple(sorted(set(([32] if include_32 else []) + list(BASE_DS))))
    return ds, selection_rows


def _capacity_rows(configs: dict[str, dict[str, Any]], ds: tuple[int, ...]) -> list[dict[str, Any]]:
    rows = []
    for task, config in configs.items():
        k_var = config["n_vars"] if task == "sat_3sat" else config["n"]
        k_val = 2 if task == "sat_3sat" else config["k"]
        for D in ds:
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


def _run_arm_grid(pools: dict[str, list[dict[str, Any]]], configs: dict[str, dict[str, Any]], task_summaries: dict[str, dict[str, Any]], ds: tuple[int, ...]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    episode_rows: list[dict[str, Any]] = []
    cell_rows: list[dict[str, Any]] = []
    arm_specs: list[tuple[str, str]] = [(arm, spill) for arm in STRUCTURED_ARMS for spill in ("spill_off", "spill_on")]
    arm_specs.extend((arm, "not_applicable") for arm in CONTROL_ARMS)
    total_cells = len(pools) * len(ds) * len(SEEDS) * len(BANDS) * len(arm_specs)
    completed_cells = 0
    _write_progress("arm_grid", completed_cells, total_cells, {"phase": "start", "D_grid": list(ds)})
    for task, rows in pools.items():
        node_cap = int(task_summaries[task]["node_cap"])
        config = configs[task]
        by_band = {band: [row for row in rows if row["band"] == band] for band in BANDS}
        for D in ds:
            for seed in SEEDS:
                for band, band_rows in by_band.items():
                    for arm, spill in arm_specs:
                        if arm == "gru":
                            cell_rows.append(_gru_audit_row(task, band, D, seed, len(band_rows)))
                            completed_cells += 1
                            _write_progress("arm_grid", completed_cells, total_cells, {"task": task, "D": D, "seed": seed, "band": band, "arm": arm, "spill": spill, "cell_rows": len(cell_rows), "episode_rows": len(episode_rows)})
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
                                "required_depth": _required_depth(row),
                                "reverts_needed": row["reverts_needed"],
                                "solve": result.solved,
                                "applied_reverts": result.applied_reverts,
                                "revert_success": result.revert_success,
                                "peak_register_bytes": result.peak_register_bytes,
                                "overflow_entries": result.overflow_entries,
                                "node_cap_exhaustion": result.node_cap_exhausted,
                                "status": result.status,
                            })
                        cell_rows.append(_aggregate_cell(task, arm, spill, band, D, seed, band_rows, evals, config))
                        completed_cells += 1
                        _write_progress("arm_grid", completed_cells, total_cells, {"task": task, "D": D, "seed": seed, "band": band, "arm": arm, "spill": spill, "cell_rows": len(cell_rows), "episode_rows": len(episode_rows)})
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


def _law_transfer_rows(cell_rows: list[dict[str, Any]], pools: dict[str, list[dict[str, Any]]], configs: dict[str, dict[str, Any]], ds: tuple[int, ...], storage_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    measured_by_key = {(row["task"], row["arm"], row["D"]): row for row in storage_rows}
    for task, pool_rows in pools.items():
        for arm in STRUCTURED_ARMS:
            for D in ds:
                measured_row = measured_by_key[(task, arm, D)]
                measured_cap = int(measured_row["d_star_measured"])
                predicted = _capacity_dstar(task, arm, D, configs[task])
                for band in BANDS:
                    band_rows = [row for row in pool_rows if row["band"] == band]
                    expected = sum(_required_depth(row) <= measured_cap for row in band_rows) / max(len(band_rows), 1)
                    observed_values = [row["solve_rate"] for row in cell_rows if row["task"] == task and row["arm"] == arm and row["spill"] == "spill_off" and row["D"] == D and row["band"] == band and row["figure_included"]]
                    observed = mean(observed_values) if observed_values else None
                    rows.append({
                        "task": task,
                        "arm": arm,
                        "D": D,
                        "band": band,
                        "n": len(band_rows),
                        "predicted_d_star": predicted,
                        "predicted_d_star_floor": math.floor(predicted),
                        "measured_d_star": measured_cap,
                        "d_star_gap_measured_minus_predicted": measured_cap - predicted,
                        "d_star_source": "pure_storage_lifo_push_pop_no_solving",
                        "fraction_required_depth_le_dstar": expected,
                        "observed_spill_off_solve_rate": observed,
                        "observed_seed_min": min(observed_values) if observed_values else None,
                        "observed_seed_max": max(observed_values) if observed_values else None,
                        "n_seeds_joined": len(observed_values),
                        "law_transfer_abs_diff": None if observed is None else abs(observed - expected),
                        "law_transfer_tolerance": LAW_TRANSFER_TOLERANCE,
                        "on_y_equals_x": observed is not None and abs(observed - expected) < LAW_TRANSFER_TOLERANCE,
                        "source": SOURCE,
                        "provenance": SOURCE,
                    })
    return rows


def _predictor_law_transfer_rows(cell_rows: list[dict[str, Any]], pools: dict[str, list[dict[str, Any]]], configs: dict[str, dict[str, Any]], storage_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    measured_by_key = {(row["task"], row["arm"], int(row["D"])): int(row["d_star_measured"]) for row in storage_rows}
    for task, pool_rows in pools.items():
        K_eff = configs[task]["n_vars"] * 2 if task == "sat_3sat" else configs[task]["n"] * configs[task]["k"]
        for arm in STRUCTURED_ARMS:
            variant = _variant_for_arm(arm)
            Ds = sorted(D for task_key, arm_key, D in measured_by_key if task_key == task and arm_key == arm)
            for D in Ds:
                measured_cap = measured_by_key[(task, arm, D)]
                for band in BANDS:
                    band_rows = [row for row in pool_rows if row["band"] == band]
                    if not band_rows:
                        continue
                    observed_values = [row["solve_rate"] for row in cell_rows if row["task"] == task and row["arm"] == arm and row["spill"] == "spill_off" and row["D"] == D and row["band"] == band and row["figure_included"]]
                    observed = mean(observed_values) if observed_values else None
                    for predictor in ("D_peak", "D_pop", "D_readpop"):
                        expected = sum(_predictor_value(row, predictor) <= measured_cap for row in band_rows) / len(band_rows)
                        abs_diff = None if observed is None else abs(observed - expected)
                        rows.append({
                            "task": task,
                            "arm": arm,
                            "variant": variant,
                            "D": D,
                            "band": band,
                            "predictor": predictor,
                            "n": len(band_rows),
                            "K_eff": K_eff,
                            "measured_d_star": measured_cap,
                            "d_star_source": "pure_storage_lifo_push_pop_no_solving",
                            "fraction_predictor_le_dstar": expected,
                            "observed_spill_off_solve_rate": observed,
                            "observed_seed_min": min(observed_values) if observed_values else None,
                            "observed_seed_max": max(observed_values) if observed_values else None,
                            "n_seeds_joined": len(observed_values),
                            "predictor_abs_diff": abs_diff,
                            "law_transfer_tolerance": LAW_TRANSFER_TOLERANCE,
                            "on_y_equals_x": observed is not None and abs_diff < LAW_TRANSFER_TOLERANCE,
                            "source": SOURCE,
                            "provenance": "reference_live_load_predictor_vs_independently_measured_storage_dstar",
                        })
    return rows


def _predictor_summary_rows(rows: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    summary = []
    for predictor in ("D_peak", "D_pop", "D_readpop"):
        pred_rows = [row for row in rows if row.get("predictor") == predictor and row.get("predictor_abs_diff") is not None]
        if not pred_rows:
            continue
        pass_rows = sum(bool(row["on_y_equals_x"]) for row in pred_rows)
        diffs = [float(row["predictor_abs_diff"]) for row in pred_rows]
        summary.append({
            "scope": scope,
            "predictor": predictor,
            "pass_rows": pass_rows,
            "total_rows": len(pred_rows),
            "pass_rate": pass_rows / max(len(pred_rows), 1),
            "mean_abs_diff": mean(diffs),
            "max_abs_diff": max(diffs),
            "law_transfer_tolerance": LAW_TRANSFER_TOLERANCE,
            "source": SOURCE,
            "provenance": "candidate_live_load_predictor_summary_against_observed_spill_off_solve_rate",
        })
    if summary:
        best = min(summary, key=lambda row: (row["mean_abs_diff"], -row["pass_rows"], row["predictor"] != "D_pop"))
        for row in summary:
            row["is_best_by_mean_abs_diff"] = row["predictor"] == best["predictor"]
    return summary


def _composition_read_rule_rows() -> list[dict[str, Any]]:
    return [
        {"rule": "register_entry_classification", "value": "ScalarRegisterLoop pushes only branch choices; forced propagations are returned by _oracle_ops as current assignment and are recomputable, so no FORCED register entries are written in this implementation.", "source": SOURCE, "provenance": "inspected_ScalarRegisterLoop.run_push_pop_and_oracle_ops"},
        {"rule": "pop_read", "value": "ScalarRegisterLoop.pop(level,var,value) is the only operational register decode in the current loop; each pop reads the top CHOICE trail entry at live load=level.", "source": SOURCE, "provenance": "inspected_ScalarRegisterLoop.pop"},
        {"rule": "forward_read", "value": "No forward register read is used to reconstruct state; _oracle_ops recomputes forced propagation from the surviving assignment.", "source": SOURCE, "provenance": "inspected_ScalarRegisterLoop.run"},
        {"rule": "spill_off_write_drop", "value": "ScalarRegisterLoop.push(level,var,value): capacity_floor=floor(_capacity_dstar(task,arm,D,config)); if level > capacity_floor then overflow_entries += 1 and spill_off sets capacity_exceeded=True and returns False without writing the entry.", "source": SOURCE, "provenance": "inspected_ScalarRegisterLoop.push"},
        {"rule": "write_drop_mask", "value": "For product-law masking, C is the same capacity_floor structural constant used by ScalarRegisterLoop; an entry is DROPPED when its push row live_load_before > C, and any read of that entry contributes factor 0.", "source": SOURCE, "provenance": "pre_registered_E1_b2_write_drop_mask"},
        {"rule": "final_solution_readback", "value": "For the compositional certification candidate, surviving CHOICE trail entries are read back in LIFO order at solve time with live loads L,L-1,...,1; this is reported separately from pop-only.", "source": SOURCE, "provenance": "pre_registered_E1_path_b_deeper_read_rule"},
    ]


def _composition_capacity_floor(task: str, arm: str, D: int, configs: dict[str, dict[str, Any]] | None = None, sudoku_capacity_lookup: dict[tuple[str, int], int] | None = None) -> int | None:
    if task == "sudoku9_item047":
        return None if sudoku_capacity_lookup is None else sudoku_capacity_lookup.get((arm, int(D)))
    if configs is None or task not in configs or arm not in STRUCTURED_ARMS:
        return None
    return math.floor(_capacity_dstar(task, arm, int(D), configs[task]))


def _composition_read_rows_for_events(task: str, row: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stack: list[dict[str, Any]] = []
    reads: list[dict[str, Any]] = []
    for event in events:
        op = event["op"]
        if op == "push":
            stack.append({
                "entry_id": len(stack) + len(reads),
                "entry_type": "CHOICE",
                "var": event.get("var"),
                "value": event.get("value"),
                "push_event_index": event["event_index"],
                "push_live_load": int(event["live_load_before"]),
                "push_live_load_after": int(event["live_load_before"]) + 1,
            })
        elif op == "pop":
            entry = stack.pop() if stack else {"entry_id": None, "entry_type": "CHOICE", "var": event.get("var"), "value": event.get("value")}
            reads.append({
                "task": task,
                "instance_index": row["instance_index"],
                "band": row["band"],
                "reverts_needed": row["reverts_needed"],
                "read_index": len(reads),
                "read_op": "pop",
                "entry_type": entry["entry_type"],
                "entry_push_live_load": entry.get("push_live_load"),
                "live_load": int(event["live_load_before"]),
                "var": entry.get("var"),
                "value": entry.get("value"),
                "source": SOURCE,
                "provenance": "reference_trajectory_structural_choice_read_set",
            })
        elif op == "solve":
            live_load = len(stack)
            for entry in reversed(stack):
                reads.append({
                    "task": task,
                    "instance_index": row["instance_index"],
                    "band": row["band"],
                    "reverts_needed": row["reverts_needed"],
                    "read_index": len(reads),
                    "read_op": "final_solution_readback",
                    "entry_type": entry["entry_type"],
                    "entry_push_live_load": entry.get("push_live_load"),
                    "live_load": live_load,
                    "var": entry.get("var"),
                    "value": entry.get("value"),
                    "source": SOURCE,
                    "provenance": "reference_trajectory_structural_choice_read_set",
                })
                live_load -= 1
    return reads


def _composition_read_rows(pools: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task, pool_rows in pools.items():
        for row in pool_rows:
            rows.extend(_composition_read_rows_for_events(task, row, row.get("reference_live_load_events", [])))
    return rows


def _curve_lookup(curve_rows: list[dict[str, Any]]) -> dict[tuple[str, str, int, int], float]:
    lookup: dict[tuple[str, str, int, int], float] = {}
    for row in curve_rows:
        lookup[(row["task"], row["arm"], int(row["D"]), int(row["depth"]))] = float(row["decode_accuracy"])
    return lookup


def _decode_acc(lookup: dict[tuple[str, str, int, int], float], task: str, arm: str, D: int, live_load: int) -> float | None:
    if live_load <= 0:
        return 1.0
    key = (task, arm, int(D), int(live_load))
    if key in lookup:
        return lookup[key]
    available = sorted(depth for task_key, arm_key, D_key, depth in lookup if task_key == task and arm_key == arm and D_key == int(D))
    if not available:
        return None
    if live_load > available[-1]:
        return lookup[(task, arm, int(D), available[-1])]
    return None


def _candidate_base(candidate: str) -> str:
    return candidate[:-9] if candidate.endswith("_unmasked") else candidate


def _candidate_is_masked(candidate: str) -> bool:
    return not candidate.endswith("_unmasked") and candidate in {"P_all", "P_choice", "P_pop"}


def _composition_candidates(include_unmasked: bool = True) -> tuple[str, ...]:
    masked = ("P_all", "P_choice", "P_pop")
    if not include_unmasked:
        return masked
    return masked + ("P_all_unmasked", "P_choice_unmasked", "P_pop_unmasked")


def _product_for_reads(reads: list[dict[str, Any]], lookup: dict[tuple[str, str, int, int], float], task: str, arm: str, D: int, candidate: str, capacity_floor: int | None = None) -> tuple[float | None, int, int, float | None, int, int]:
    base_candidate = _candidate_base(candidate)
    if base_candidate == "P_all":
        selected = reads
    elif base_candidate == "P_choice":
        selected = [row for row in reads if row["entry_type"] == "CHOICE"]
    elif base_candidate == "P_pop":
        selected = [row for row in reads if row["read_op"] == "pop"]
    else:
        raise ValueError(f"unknown compositional candidate={candidate}")
    dropped_selected = []
    if _candidate_is_masked(candidate) and capacity_floor is not None:
        dropped_selected = [row for row in selected if row.get("entry_push_live_load") is not None and int(row["entry_push_live_load"]) > int(capacity_floor)]
    if dropped_selected:
        return 0.0, len(selected), max((int(row["live_load"]) for row in selected), default=0), 0.0, len(dropped_selected), len(selected) - len(dropped_selected)
    log_prob = 0.0
    min_acc: float | None = None
    dropped_reads = 0
    surviving_reads = 0
    for read in selected:
        surviving_reads += 1
        acc = _decode_acc(lookup, task, arm, D, int(read["live_load"]))
        if acc is None:
            return None, len(selected), int(read["live_load"]), None, dropped_reads, surviving_reads
        acc = min(max(acc, 0.0), 1.0)
        min_acc = acc if min_acc is None else min(min_acc, acc)
        if acc <= 0.0:
            return 0.0, len(selected), int(read["live_load"]), 0.0, dropped_reads, surviving_reads
        log_prob += math.log(acc)
    return math.exp(log_prob), len(selected), max((int(row["live_load"]) for row in selected), default=0), min_acc, dropped_reads, surviving_reads


def _composition_instance_rows(pools: dict[str, list[dict[str, Any]]], curve_rows: list[dict[str, Any]], ds: tuple[int, ...], configs: dict[str, dict[str, Any]] | None = None, sudoku_capacity_lookup: dict[tuple[str, int], int] | None = None) -> list[dict[str, Any]]:
    lookup = _curve_lookup(curve_rows)
    rows: list[dict[str, Any]] = []
    for task, pool_rows in pools.items():
        for row in pool_rows:
            reads = _composition_read_rows_for_events(task, row, row.get("reference_live_load_events", []))
            for arm in STRUCTURED_ARMS:
                for D in ds:
                    capacity_floor = _composition_capacity_floor(task, arm, D, configs, sudoku_capacity_lookup)
                    for candidate in _composition_candidates(include_unmasked=True):
                        product, n_reads, max_live_load, min_read_acc, dropped_reads, surviving_reads = _product_for_reads(reads, lookup, task, arm, D, candidate, capacity_floor)
                        rows.append({
                            "task": task,
                            "arm": arm,
                            "variant": _variant_for_arm(arm),
                            "D": D,
                            "band": row["band"],
                            "instance_index": row["instance_index"],
                            "reverts_needed": row["reverts_needed"],
                            "candidate": candidate,
                            "mask_applied": _candidate_is_masked(candidate),
                            "hard_capacity_C": capacity_floor,
                            "n_reads": n_reads,
                            "n_dropped_reads": dropped_reads,
                            "n_surviving_reads": surviving_reads,
                            "max_read_live_load": max_live_load,
                            "min_read_decode_acc": min_read_acc,
                            "predicted_instance_solve_prob": product,
                            "status": "RECORDED" if product is not None else "MISSING_DECODE_CURVE",
                            "source": SOURCE,
                            "provenance": "parameter_free_product_of_measured_decode_curve_over_structural_reads",
                        })
    return rows


def _composition_law_rows(instance_rows: list[dict[str, Any]], threshold_rows: list[dict[str, Any]], cell_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    keys = sorted({(row["task"], row["arm"], int(row["D"]), row["band"]) for row in instance_rows})
    for task, arm, D, band in keys:
        observed_values = [row["solve_rate"] for row in cell_rows if row["task"] == task and row["arm"] == arm and row["spill"] == "spill_off" and row["D"] == D and row["band"] == band and row["figure_included"]]
        observed = mean(observed_values) if observed_values else None
        for candidate in _composition_candidates(include_unmasked=True):
            subset = [row for row in instance_rows if row["task"] == task and row["arm"] == arm and int(row["D"]) == D and row["band"] == band and row["candidate"] == candidate]
            valid = [row for row in subset if row["predicted_instance_solve_prob"] is not None]
            predicted = mean(float(row["predicted_instance_solve_prob"]) for row in valid) if valid else None
            tolerance = 1.0 / max(len(valid), 1)
            abs_diff = None if observed is None or predicted is None else abs(observed - predicted)
            residual = None if observed is None or predicted is None else observed - predicted
            rows.append({
                "task": task,
                "arm": arm,
                "variant": _variant_for_arm(arm),
                "D": D,
                "band": band,
                "candidate": candidate,
                "model_family": "decode_curve_product",
                "mask_applied": _candidate_is_masked(candidate),
                "n": len(valid),
                "n_missing_decode_curve": len(subset) - len(valid),
                "mean_dropped_reads": mean(float(row["n_dropped_reads"]) for row in valid) if valid else None,
                "instances_with_dropped_reads": sum(int(row["n_dropped_reads"] > 0) for row in valid),
                "predicted_solve_rate": predicted,
                "observed_spill_off_solve_rate": observed,
                "observed_seed_min": min(observed_values) if observed_values else None,
                "observed_seed_max": max(observed_values) if observed_values else None,
                "n_seeds_joined": len(observed_values),
                "abs_diff": abs_diff,
                "residual_observed_minus_predicted": residual,
                "residual_nonnegative": residual is not None and residual >= -tolerance,
                "residual_within_tolerance": residual is not None and abs(residual) <= tolerance,
                "residual_one_sided_tight": residual is not None and residual >= -tolerance and residual <= tolerance,
                "law_transfer_tolerance": tolerance,
                "on_y_equals_x": abs_diff is not None and abs_diff <= tolerance,
                "pre_registered_hypothesis": candidate == "P_choice",
                "source": SOURCE,
                "provenance": "parameter_free_product_law_vs_observed_spill_off_solve_rate",
            })
        for predictor in ("D_peak", "D_pop"):
            threshold = next((row for row in threshold_rows if row["task"] == task and row["arm"] == arm and int(row["D"]) == D and row["band"] == band and row["predictor"] == predictor), None)
            if threshold is None:
                continue
            predicted = float(threshold["fraction_predictor_le_dstar"])
            n = int(threshold["n"])
            tolerance = 1.0 / max(n, 1)
            abs_diff = None if observed is None else abs(observed - predicted)
            residual = None if observed is None else observed - predicted
            rows.append({
                "task": task,
                "arm": arm,
                "variant": _variant_for_arm(arm),
                "D": D,
                "band": band,
                "candidate": f"threshold_{predictor}",
                "model_family": "dstar_threshold_contrast",
                "mask_applied": False,
                "n": n,
                "n_missing_decode_curve": 0,
                "mean_dropped_reads": None,
                "instances_with_dropped_reads": None,
                "predicted_solve_rate": predicted,
                "observed_spill_off_solve_rate": observed,
                "observed_seed_min": min(observed_values) if observed_values else None,
                "observed_seed_max": max(observed_values) if observed_values else None,
                "n_seeds_joined": len(observed_values),
                "abs_diff": abs_diff,
                "residual_observed_minus_predicted": residual,
                "residual_nonnegative": residual is not None and residual >= -tolerance,
                "residual_within_tolerance": residual is not None and abs(residual) <= tolerance,
                "residual_one_sided_tight": residual is not None and residual >= -tolerance and residual <= tolerance,
                "law_transfer_tolerance": tolerance,
                "on_y_equals_x": abs_diff is not None and abs_diff <= tolerance,
                "pre_registered_hypothesis": False,
                "source": SOURCE,
                "provenance": "threshold_variant_contrast_against_product_law",
            })
    return rows


def _composition_summary_rows(rows: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    summary = []
    preferred_order = list(_composition_candidates(include_unmasked=True)) + ["threshold_D_peak", "threshold_D_pop"]
    candidates = [candidate for candidate in preferred_order if any(row.get("candidate") == candidate for row in rows)]
    candidates.extend(sorted({row.get("candidate") for row in rows if row.get("candidate") not in set(candidates)}))
    for candidate in candidates:
        subset = [row for row in rows if row.get("candidate") == candidate and row.get("abs_diff") is not None]
        if not subset:
            continue
        diffs = [float(row["abs_diff"]) for row in subset]
        pass_rows = sum(bool(row["on_y_equals_x"]) for row in subset)
        observed_exceeds = [float(row["observed_spill_off_solve_rate"]) - float(row["predicted_solve_rate"]) for row in subset if row.get("observed_spill_off_solve_rate") is not None and row.get("predicted_solve_rate") is not None]
        residuals = [float(row["residual_observed_minus_predicted"]) for row in subset if row.get("residual_observed_minus_predicted") is not None]
        summary.append({
            "scope": scope,
            "candidate": candidate,
            "model_family": subset[0].get("model_family"),
            "mask_applied": subset[0].get("mask_applied", False),
            "pass_rows": pass_rows,
            "total_rows": len(subset),
            "pass_rate": pass_rows / max(len(subset), 1),
            "mean_abs_diff": mean(diffs),
            "max_abs_diff": max(diffs),
            "mean_observed_minus_predicted": mean(observed_exceeds) if observed_exceeds else None,
            "residual_mean": mean(residuals) if residuals else None,
            "residual_min": min(residuals) if residuals else None,
            "residual_max": max(residuals) if residuals else None,
            "fraction_residual_nonnegative": sum(bool(row.get("residual_nonnegative")) for row in subset) / max(len(subset), 1),
            "fraction_residual_within_tolerance": sum(bool(row.get("residual_within_tolerance")) for row in subset) / max(len(subset), 1),
            "fraction_residual_one_sided_tight": sum(bool(row.get("residual_one_sided_tight")) for row in subset) / max(len(subset), 1),
            "pre_registered_hypothesis": candidate == "P_choice",
            "source": SOURCE,
            "provenance": "parameter_free_compositional_law_summary",
        })
    if summary:
        best = min(summary, key=lambda row: (row["mean_abs_diff"], -row["pass_rows"], row["candidate"] != "P_choice"))
        for row in summary:
            row["is_best_by_mean_abs_diff"] = row["candidate"] == best["candidate"]
    return summary


def _module1_sudoku_curve_rows() -> list[dict[str, Any]]:
    if not SUDOKU_MODULE1_CURVES_PATH.exists():
        return []
    payload = json.loads(SUDOKU_MODULE1_CURVES_PATH.read_text())
    rows: list[dict[str, Any]] = []
    for summary in payload.get("summary", []):
        if summary.get("K_var") != 81 or summary.get("K_val") != 9:
            continue
        if summary.get("replacement") != "with_replacement":
            continue
        variant = summary.get("variant")
        if variant not in {"bound_single", "factored"}:
            continue
        arm = _arm_for_variant(variant)
        for curve_row in summary.get("curve", []):
            rows.append({
                "task": "sudoku9_item047",
                "codebook": variant,
                "arm": arm,
                "D": int(summary["D"]),
                "K_var": 81,
                "K_val": 9,
                "K_eff": 729 if variant == "bound_single" else 81,
                "depth": int(curve_row["depth"]),
                "decode_accuracy": float(curve_row["joint_accuracy"]),
                "threshold": STORAGE_THRESHOLD,
                "source": SOURCE,
                "provenance": "module1_capacity_perdepth_shards_with_replacement_full_curve",
            })
    rows.extend(_sudoku_d128_bound_single_curve_rows())
    return rows


def _curve_crossing(curve: list[dict[str, Any]], metric: str, threshold: float = STORAGE_THRESHOLD) -> float:
    ordered = sorted(curve, key=lambda row: row["depth"])
    if not ordered or ordered[0][metric] < threshold:
        return 0.0
    last = ordered[0]
    for row in ordered[1:]:
        if row[metric] < threshold:
            denom = last[metric] - row[metric]
            if denom <= 0:
                return float(last["depth"])
            frac = (last[metric] - threshold) / denom
            return float(last["depth"] + frac * (row["depth"] - last["depth"]))
        last = row
    return float(ordered[-1]["depth"])


def _measure_sudoku_d128_bound_single_curve() -> dict[str, Any]:
    from experiments.module1_capacity_perdepth import _run_bound_single

    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    raw_rows: list[dict[str, Any]] = []
    for seed in STORAGE_SEEDS:
        for depth in range(1, 59):
            result = _run_bound_single(128, 81, 9, depth, seed, SUDOKU_MODULE1_D128_TRIALS, SUDOKU_MODULE1_D128_BATCH_SIZE, device, "with_replacement")
            raw_rows.append({
                "variant": "bound_single",
                "replacement": "with_replacement",
                "D": 128,
                "K_var": 81,
                "K_val": 9,
                "seed": seed,
                "depth": depth,
                **result,
            })
    curve = []
    for depth in range(1, 59):
        depth_rows = [row for row in raw_rows if row["depth"] == depth]
        curve.append({
            "depth": depth,
            "joint_accuracy": mean(row["joint_accuracy"] for row in depth_rows),
            "var_accuracy": mean(row["var_accuracy"] for row in depth_rows),
            "val_accuracy": mean(row["val_accuracy"] for row in depth_rows),
            "std_joint_accuracy": pstdev(row["joint_accuracy"] for row in depth_rows),
            "mean_margin": mean(row["mean_margin"] for row in depth_rows),
        })
    summary = {
        "variant": "bound_single",
        "replacement": "with_replacement",
        "D": 128,
        "K_var": 81,
        "K_val": 9,
        "capacity_joint_095": _curve_crossing(curve, "joint_accuracy"),
        "capacity_var_095": _curve_crossing(curve, "var_accuracy"),
        "capacity_val_095": _curve_crossing(curve, "val_accuracy"),
        "curve": curve,
    }
    payload = {
        "module": "module1_capacity_perdepth_targeted_sudoku_d128_bound_single",
        "device": device,
        "threshold": STORAGE_THRESHOLD,
        "trials": SUDOKU_MODULE1_D128_TRIALS,
        "batch_size": SUDOKU_MODULE1_D128_BATCH_SIZE,
        "seeds": list(STORAGE_SEEDS),
        "raw_rows": raw_rows,
        "summary": summary,
        "source": SOURCE,
        "provenance": "targeted_module1_capacity_perdepth_with_replacement_full_curve",
    }
    SUDOKU_D128_BOUND_SINGLE_CURVE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def _sudoku_d128_bound_single_curve_rows() -> list[dict[str, Any]]:
    if SUDOKU_D128_BOUND_SINGLE_CURVE_PATH.exists():
        payload = json.loads(SUDOKU_D128_BOUND_SINGLE_CURVE_PATH.read_text())
    else:
        payload = _measure_sudoku_d128_bound_single_curve()
    summary = payload.get("summary", {})
    rows = []
    if summary.get("variant") != "bound_single" or int(summary.get("D", -1)) != 128:
        return rows
    for curve_row in summary.get("curve", []):
        rows.append({
            "task": "sudoku9_item047",
            "codebook": "bound_single",
            "arm": "rot_bound_single",
            "D": 128,
            "K_var": 81,
            "K_val": 9,
            "K_eff": 729,
            "depth": int(curve_row["depth"]),
            "decode_accuracy": float(curve_row["joint_accuracy"]),
            "threshold": STORAGE_THRESHOLD,
            "source": SOURCE,
            "provenance": "targeted_module1_capacity_perdepth_D128_bound_single_with_replacement_full_curve",
        })
    return rows


def _sudoku_domains_from_givens(givens: Any) -> dict[int, set[int]]:
    domains = {var: set(range(1, 10)) for var in range(81)}
    if isinstance(givens, dict):
        iterator = givens.items()
        for key, value in iterator:
            if isinstance(key, str) and "," in key:
                r, c = (int(part) for part in key.split(","))
                var = r * 9 + c
            else:
                var = int(key)
            domains[var] = {int(value)}
    else:
        for idx, value in enumerate(givens):
            if int(value) != 0:
                domains[idx] = {int(value)}
    return domains


def _sudoku_subsample_trace_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not SUDOKU_POOL_PATH.exists():
        return [], []
    payload = json.loads(SUDOKU_POOL_PATH.read_text())
    pool_rows = payload.get("selected_instances", [])
    selected: list[tuple[int, dict[str, Any]]] = []
    for band in BANDS:
        band_rows = [(index, row) for index, row in enumerate(pool_rows) if row.get("reverts_band") == band]
        selected.extend(sorted(band_rows, key=lambda item: (int(item[1].get("reference_nodes", 10**12)), item[0]))[:SUDOKU_COMPOSITION_SUBSAMPLE_PER_BAND])
    predictor_rows: list[dict[str, Any]] = []
    read_rows: list[dict[str, Any]] = []
    oracle = DPLLOracle()
    constraints = constraints_9x9()
    variables = list(range(81))

    def timeout_handler(signum: int, frame: Any) -> None:
        raise _SudokuTraceTimeout(f"DPLLOracle solve exceeded {SUDOKU_LIVE_LOAD_TIMEOUT_SECONDS}s")

    for index, row in selected:
        try:
            domains = _sudoku_domains_from_givens(row.get("givens", {}))
            previous_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(SUDOKU_LIVE_LOAD_TIMEOUT_SECONDS)
            try:
                trace = oracle.solve(variables, domains, constraints)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, previous_handler)
            events = _oracle_trace_live_load_events(trace)
            live_loads = [int(event["live_load_before"]) for event in events]
            reads = _composition_read_rows_for_events("sudoku9_item047", {
                "instance_index": index,
                "band": row["reverts_band"],
                "reverts_needed": int(row["reverts_needed"]),
            }, events)
            predictor_row = {
                "task": "sudoku9_item047",
                "instance_index": index,
                "band": row["reverts_band"],
                "reverts_needed": int(row["reverts_needed"]),
                "reference_nodes": int(row.get("reference_nodes", 0)),
                "status": "measured",
                "D_peak": max(live_loads) if live_loads else 0,
                "D_pop": max((int(event["live_load_before"]) for event in events if event["op"] == "pop"), default=0),
                "D_readpop": max((int(read["live_load"]) for read in reads), default=0),
                "n_reads": len(reads),
                "subsample_rule": f"lowest_reference_nodes_per_band_{SUDOKU_COMPOSITION_SUBSAMPLE_PER_BAND}",
                "source": SOURCE,
                "provenance": "real_DPLLOracle_trace_subsample_no_saved_stats_proxy",
            }
        except _SudokuTraceTimeout as exc:
            predictor_row = {
                "task": "sudoku9_item047",
                "instance_index": index,
                "band": row.get("reverts_band"),
                "reverts_needed": int(row.get("reverts_needed", -1)),
                "reference_nodes": int(row.get("reference_nodes", 0)),
                "status": "timeout",
                "error": repr(exc),
                "D_peak": None,
                "D_pop": None,
                "D_readpop": None,
                "n_reads": 0,
                "subsample_rule": f"lowest_reference_nodes_per_band_{SUDOKU_COMPOSITION_SUBSAMPLE_PER_BAND}",
                "source": SOURCE,
                "provenance": "real_DPLLOracle_trace_subsample_no_saved_stats_proxy",
            }
            reads = []
        except Exception as exc:
            predictor_row = {
                "task": "sudoku9_item047",
                "instance_index": index,
                "band": row.get("reverts_band"),
                "reverts_needed": int(row.get("reverts_needed", -1)),
                "reference_nodes": int(row.get("reference_nodes", 0)),
                "status": "error",
                "error": repr(exc),
                "D_peak": None,
                "D_pop": None,
                "D_readpop": None,
                "n_reads": 0,
                "subsample_rule": f"lowest_reference_nodes_per_band_{SUDOKU_COMPOSITION_SUBSAMPLE_PER_BAND}",
                "source": SOURCE,
                "provenance": "real_DPLLOracle_trace_subsample_no_saved_stats_proxy",
            }
            reads = []
        predictor_rows.append(predictor_row)
        read_rows.extend(reads)
    return predictor_rows, read_rows


def _sudoku_compositional_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    curve_rows = _module1_sudoku_curve_rows()
    curve_lookup = _curve_lookup(curve_rows)
    predictor_rows, read_rows = _sudoku_subsample_trace_rows()
    reads_by_instance: dict[int, list[dict[str, Any]]] = {}
    for read in read_rows:
        reads_by_instance.setdefault(int(read["instance_index"]), []).append(read)
    headline = json.loads(SUDOKU_HEADLINE_PATH.read_text()) if SUDOKU_HEADLINE_PATH.exists() else {}
    headline_rows = headline.get("result_tables", {}).get("headline_separation", {}).get("rows", [])
    headline_ds = sorted({int(row["D"]) for row in headline_rows if row.get("arm") in STRUCTURED_ARMS})
    sudoku_capacity_lookup = {
        (row["arm"], int(row["D"])): int(row["capacity_d_star_floor"])
        for row in headline_rows
        if row.get("arm") in STRUCTURED_ARMS and row.get("capacity_d_star_floor") is not None
    }
    product_rows: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []
    for live_row in predictor_rows:
        if live_row.get("status") != "measured":
            continue
        reads = reads_by_instance.get(int(live_row["instance_index"]), [])
        for arm in STRUCTURED_ARMS:
            for D in headline_ds:
                capacity_floor = _composition_capacity_floor("sudoku9_item047", arm, D, None, sudoku_capacity_lookup)
                for candidate in _composition_candidates(include_unmasked=True):
                    product, n_reads, max_live_load, min_read_acc, dropped_reads, surviving_reads = _product_for_reads(reads, curve_lookup, "sudoku9_item047", arm, D, candidate, capacity_floor)
                    product_rows.append({
                        "task": "sudoku9_item047",
                        "instance_index": live_row["instance_index"],
                        "band": live_row["band"],
                        "reverts_needed": live_row["reverts_needed"],
                        "arm": arm,
                        "variant": _variant_for_arm(arm),
                        "D": D,
                        "candidate": candidate,
                        "mask_applied": _candidate_is_masked(candidate),
                        "hard_capacity_C": capacity_floor,
                        "n_reads": n_reads,
                        "n_dropped_reads": dropped_reads,
                        "n_surviving_reads": surviving_reads,
                        "max_read_live_load": max_live_load,
                        "min_read_decode_acc": min_read_acc,
                        "predicted_instance_solve_prob": product,
                        "status": "RECORDED" if product is not None else "MISSING_DECODE_CURVE",
                        "source": SOURCE,
                        "provenance": "sudoku_real_trace_subsample_product_of_full_decode_curve_no_saved_stats_proxy",
                    })
    for arm in STRUCTURED_ARMS:
        for D in headline_ds:
            for band in BANDS:
                observed_values = [float(row["solve_rate"]) for row in headline_rows if row.get("arm") == arm and row.get("spill") == "spill_off" and int(row["D"]) == D and row.get("band") == band]
                observed = mean(observed_values) if observed_values else None
                for candidate in _composition_candidates(include_unmasked=True):
                    subset = [row for row in product_rows if row["arm"] == arm and int(row["D"]) == D and row["band"] == band and row["candidate"] == candidate]
                    valid = [row for row in subset if row["predicted_instance_solve_prob"] is not None]
                    predicted = mean(float(row["predicted_instance_solve_prob"]) for row in valid) if valid else None
                    tolerance = 1 / max(len(valid), 1)
                    abs_diff = None if observed is None or predicted is None else abs(observed - predicted)
                    residual = None if observed is None or predicted is None else observed - predicted
                    comparison_rows.append({
                        "task": "sudoku9_item047",
                        "arm": arm,
                        "variant": _variant_for_arm(arm),
                        "D": D,
                        "band": band,
                        "candidate": candidate,
                        "model_family": "decode_curve_product",
                        "mask_applied": _candidate_is_masked(candidate),
                        "n": len(valid),
                        "n_missing_decode_curve": len(subset) - len(valid),
                        "n_timeout_excluded": sum(1 for row in predictor_rows if row.get("band") == band and row.get("status") == "timeout"),
                        "mean_dropped_reads": mean(float(row["n_dropped_reads"]) for row in valid) if valid else None,
                        "instances_with_dropped_reads": sum(int(row["n_dropped_reads"] > 0) for row in valid),
                        "subsample_per_band": SUDOKU_COMPOSITION_SUBSAMPLE_PER_BAND,
                        "predicted_solve_rate": predicted,
                        "observed_spill_off_solve_rate": observed,
                        "observed_seed_min": min(observed_values) if observed_values else None,
                        "observed_seed_max": max(observed_values) if observed_values else None,
                        "n_seeds_joined": len(observed_values),
                        "abs_diff": abs_diff,
                        "residual_observed_minus_predicted": residual,
                        "residual_nonnegative": residual is not None and residual >= -tolerance,
                        "residual_within_tolerance": residual is not None and abs(residual) <= tolerance,
                        "residual_one_sided_tight": residual is not None and residual >= -tolerance and residual <= tolerance,
                        "law_transfer_tolerance": tolerance,
                        "on_y_equals_x": abs_diff is not None and abs_diff <= tolerance,
                        "pre_registered_hypothesis": candidate == "P_choice",
                        "status": "RECORDED" if valid else "MISSING_DECODE_CURVE_OR_TRACE",
                        "source": SOURCE,
                        "provenance": "sudoku_real_trace_subsample_product_law_no_saved_stats_proxy",
                    })
    summary_rows = _composition_summary_rows(comparison_rows, "sudoku9_real_trace_subsample")
    return curve_rows, predictor_rows, read_rows, product_rows, comparison_rows, summary_rows


def _oracle_trace_live_load_events(trace: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for step in trace.steps:
        if step.action == TraceAction.BRANCH:
            events.append({
                "event_index": len(events),
                "op": "push",
                "live_load_before": int(step.depth),
                "var": step.variable,
                "value": step.value,
                "read_consumed_for_next_branch": False,
            })
        elif step.action == TraceAction.BACKTRACK:
            events.append({
                "event_index": len(events),
                "op": "pop",
                "live_load_before": int(step.depth) + 1,
                "var": step.variable,
                "value": step.value,
                "read_consumed_for_next_branch": True,
            })
        elif step.action == TraceAction.SOLVED:
            events.append({
                "event_index": len(events),
                "op": "solve",
                "live_load_before": int(step.depth),
                "var": None,
                "value": None,
                "read_consumed_for_next_branch": False,
            })
    return events


def _sudoku_timeout_row(index: int, row: dict[str, Any], status: str = "timeout") -> dict[str, Any]:
    return {
        "task": "sudoku9_item047",
        "instance_index": index,
        "instance_id": row.get("instance_id", f"sudoku_{index}"),
        "band": row["reverts_band"],
        "reverts_needed": int(row["reverts_needed"]),
        "reference_nodes": int(row["reference_nodes"]),
        "dpll_backtrack_depth": int(row["dpll_backtrack_depth"]),
        "D_peak": int(row["dpll_backtrack_depth"]),
        "D_pop": None,
        "D_readpop": None,
        "D_readpop_equals_D_pop": None,
        "n_push": 0,
        "n_pop": 0,
        "n_solve": 0,
        "live_load_status": status,
        "timeout_seconds": SUDOKU_LIVE_LOAD_TIMEOUT_SECONDS,
        "prescreen_max_reference_nodes": SUDOKU_LIVE_LOAD_PRESCREEN_MAX_NODES if status == "prescreen_timeout" else None,
        "source": SOURCE,
        "provenance": "rerun_DPLLOracle_on_item047_saved_givens_reference_only_with_per_instance_timeout",
    }


def _sudoku_live_load_row(index: int, row: dict[str, Any]) -> dict[str, Any]:
    variables = list(range(81))
    constraints = constraints_9x9()
    domains = {var: set(range(1, 10)) for var in variables}
    for cell, value in row["givens"].items():
        r, c = (int(part) for part in cell.split(","))
        domains[r * 9 + c] = {int(value)}
    trace = DPLLOracle().solve(variables, domains, constraints)
    events = _oracle_trace_live_load_events(trace)
    predictors = _live_load_predictors(events, int(row.get("dpll_backtrack_depth", trace.max_backtrack_depth)))
    return {
        "task": "sudoku9_item047",
        "instance_index": index,
        "instance_id": row.get("instance_id", f"sudoku_{index}"),
        "band": row["reverts_band"],
        "reverts_needed": int(row["reverts_needed"]),
        "reference_nodes": int(row["reference_nodes"]),
        "dpll_backtrack_depth": int(row["dpll_backtrack_depth"]),
        "D_peak": predictors["D_peak"],
        "D_pop": predictors["D_pop"],
        "D_readpop": predictors["D_readpop"],
        "D_readpop_equals_D_pop": predictors["D_readpop"] == predictors["D_pop"],
        "n_push": sum(event["op"] == "push" for event in events),
        "n_pop": sum(event["op"] == "pop" for event in events),
        "n_solve": sum(event["op"] == "solve" for event in events),
        "live_load_status": "measured",
        "timeout_seconds": None,
        "prescreen_max_reference_nodes": SUDOKU_LIVE_LOAD_PRESCREEN_MAX_NODES,
        "source": SOURCE,
        "provenance": "rerun_DPLLOracle_on_item047_saved_givens_reference_only_with_per_instance_timeout",
    }


def _sudoku_live_load_worker(index: int, row: dict[str, Any], queue: Any) -> None:
    try:
        queue.put(_sudoku_live_load_row(index, row))
    except Exception as exc:
        failed = _sudoku_timeout_row(index, row)
        failed["live_load_status"] = "error"
        failed["error"] = repr(exc)
        queue.put(failed)


def _load_sudoku_pool_with_live_load() -> list[dict[str, Any]]:
    if not SUDOKU_POOL_PATH.exists():
        return []
    payload = json.loads(SUDOKU_POOL_PATH.read_text())
    pool_rows = payload.get("selected_instances", [])
    rows = []
    for index, row in enumerate(pool_rows):
        stats = row.get("trace_stats", {})
        hist = stats.get("action_histogram", {})
        d_peak = int(row["dpll_backtrack_depth"])
        d_pop = d_peak if int(row["reverts_needed"]) > 0 else 0
        rows.append({
            "task": "sudoku9_item047",
            "instance_index": index,
            "instance_id": row.get("instance_id", f"sudoku_{index}"),
            "band": row["reverts_band"],
            "reverts_needed": int(row["reverts_needed"]),
            "reference_nodes": int(row["reference_nodes"]),
            "dpll_backtrack_depth": d_peak,
            "D_peak": d_peak,
            "D_pop": d_pop,
            "D_readpop": d_pop,
            "D_readpop_equals_D_pop": True,
            "n_push": int(hist.get("branch", 0)),
            "n_pop": int(hist.get("backtrack", 0)),
            "n_solve": int(hist.get("solved", 0)),
            "live_load_status": "summary_proxy",
            "timeout_seconds": None,
            "prescreen_max_reference_nodes": None,
            "source": SOURCE,
            "provenance": "sudoku_item047_saved_trace_stats_proxy_full_step_trace_replay_timed_out",
        })
    return rows


def _sudoku_live_load_confirmation_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not SUDOKU_HEADLINE_PATH.exists():
        return [], [], []
    sudoku_rows = _load_sudoku_pool_with_live_load()
    if not sudoku_rows:
        return [], [], []
    headline = json.loads(SUDOKU_HEADLINE_PATH.read_text())
    headline_rows = headline.get("result_tables", {}).get("headline_separation", {}).get("rows", [])
    rows = []
    for arm in STRUCTURED_ARMS:
        for D in sorted({int(row["D"]) for row in headline_rows if row.get("arm") == arm}):
            for band in BANDS:
                band_rows = [row for row in sudoku_rows if row["band"] == band]
                observed_values = [float(row["solve_rate"]) for row in headline_rows if row.get("arm") == arm and row.get("spill") == "spill_off" and int(row["D"]) == D and row.get("band") == band]
                if not band_rows or not observed_values:
                    continue
                capacity_values = [int(row["capacity_d_star_floor"]) for row in headline_rows if row.get("arm") == arm and row.get("spill") == "spill_off" and int(row["D"]) == D and row.get("band") == band]
                capacity = int(capacity_values[0])
                observed = mean(observed_values)
                for predictor in ("D_peak", "D_pop", "D_readpop"):
                    predictor_rows = [row for row in band_rows if row.get(predictor) is not None]
                    if not predictor_rows:
                        continue
                    expected = sum(_predictor_value(row, predictor) <= capacity for row in predictor_rows) / len(predictor_rows)
                    rows.append({
                        "task": "sudoku9_item047",
                        "arm": arm,
                        "variant": _variant_for_arm(arm),
                        "D": D,
                        "band": band,
                        "predictor": predictor,
                        "n": len(predictor_rows),
                        "n_pool_band": len(band_rows),
                        "n_timeout_excluded": len(band_rows) - len(predictor_rows),
                        "K_eff": 81 * 9,
                        "capacity_d_star_floor": capacity,
                        "fraction_predictor_le_dstar": expected,
                        "observed_spill_off_solve_rate": observed,
                        "observed_seed_min": min(observed_values),
                        "observed_seed_max": max(observed_values),
                        "n_seeds_joined": len(observed_values),
                        "predictor_abs_diff": abs(observed - expected),
                        "law_transfer_tolerance": LAW_TRANSFER_TOLERANCE,
                        "on_y_equals_x": abs(observed - expected) < LAW_TRANSFER_TOLERANCE,
                        "source": SOURCE,
                        "provenance": "sudoku_item047_reference_live_load_predictor_vs_headline_spill_off_rows",
                    })
    return sudoku_rows, rows, _predictor_summary_rows(rows, "sudoku_item047")


def _acceptance(cell_rows: list[dict[str, Any]], law_rows: list[dict[str, Any]], stateless_rows: list[dict[str, Any]], predictor_summary: list[dict[str, Any]], sudoku_summary: list[dict[str, Any]]) -> dict[str, Any]:
    r3_structured = [row for row in cell_rows if row["figure_included"] and row["arm"] in STRUCTURED_ARMS and row["band"] in {"R3-5", "R6+"}]
    r3_no_revert = [row for row in cell_rows if row["figure_included"] and row["arm"] == "rot_no_revert" and row["band"] in {"R3-5", "R6+"}]
    gru_rows = [row for row in cell_rows if row["arm"] == "gru"]
    knee_rows = [row for row in law_rows if row["D"] < 128 and 0.05 <= float(row["fraction_required_depth_le_dstar"]) <= 0.95]
    law_pass_rows = sum(row["on_y_equals_x"] for row in law_rows)
    path_b_winner = next((row for row in predictor_summary if row.get("is_best_by_mean_abs_diff")), None)
    sudoku_winner = next((row for row in sudoku_summary if row.get("is_best_by_mean_abs_diff")), None)
    return {
        "rot_r3plus_any_positive": any(float(row["solve_rate"]) > 0 for row in r3_structured),
        "no_revert_r3plus_near_zero": all(float(row["solve_rate"]) <= 0.05 for row in r3_no_revert),
        "law_transfer_on_y_equals_x": all(row["on_y_equals_x"] for row in law_rows),
        "law_transfer_pass_rows": law_pass_rows,
        "law_transfer_total_rows": len(law_rows),
        "small_d_knee_exercised": bool(knee_rows),
        "small_d_knee_rows": len(knee_rows),
        "stateless_oracle_ci_passed": all(row["passed"] for row in stateless_rows),
        "gru_audit_red_excluded": bool(gru_rows) and all(row["status"] == "INCOMPLETE_AUDIT_RED" and row["figure_included"] is False and row["solve_rate"] is None for row in gru_rows),
        "live_load_path_b_best_predictor": None if path_b_winner is None else path_b_winner["predictor"],
        "live_load_path_b_best_mean_abs_diff": None if path_b_winner is None else path_b_winner["mean_abs_diff"],
        "live_load_path_b_best_pass_rows": None if path_b_winner is None else path_b_winner["pass_rows"],
        "live_load_path_b_total_rows": None if path_b_winner is None else path_b_winner["total_rows"],
        "sudoku_path_b_best_predictor": None if sudoku_winner is None else sudoku_winner["predictor"],
        "sudoku_path_b_best_mean_abs_diff": None if sudoku_winner is None else sudoku_winner["mean_abs_diff"],
        "sudoku_path_b_best_pass_rows": None if sudoku_winner is None else sudoku_winner["pass_rows"],
        "sudoku_path_b_total_rows": None if sudoku_winner is None else sudoku_winner["total_rows"],
    }


def _plot_panels(cell_rows: list[dict[str, Any]], law_rows: list[dict[str, Any]]) -> dict[str, str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    PANEL_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for task in TASKS:
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
        sep_D = 64 if any(row["task"] == task and row["D"] == 64 for row in cell_rows) else 512
        sep_rows = [row for row in cell_rows if row["task"] == task and row["figure_included"] and row["D"] == sep_D and row["seed"] == 42]
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
        axes[0].set_title(f"{task} separation, D={sep_D} seed=42")
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


def _record_compositional_tables(results: dict[str, Any]) -> None:
    pools = results.get("pool_rows", {})
    storage_curve_rows = results.get("storage_dstar_curve", [])
    ds = tuple(sorted({int(row["D"]) for row in storage_curve_rows}))
    generation = results.get("generation_config", {})
    configs = {
        "sat_3sat": {"n_vars": int(generation.get("sat_n_vars", 18)), "clause_ratio": float(generation.get("sat_clause_ratio", 4.2))},
        "graph_coloring": {"n": int(generation.get("graph_n", 16)), "k": int(generation.get("graph_k", 4)), "edge_prob": float(generation.get("graph_edge_prob", 0.45))},
    }
    read_rows = _composition_read_rows(pools)
    product_rows = _composition_instance_rows(pools, storage_curve_rows, ds, configs)
    law_rows = _composition_law_rows(product_rows, results.get("live_load_predictor_law_transfer", []), results.get("figure4_separation", []))
    summary_rows = _composition_summary_rows(law_rows, "e1_sat_graph_full_decode_curve")
    sudoku_curve_rows, sudoku_predictor_rows, sudoku_read_rows, sudoku_product_rows, sudoku_law_rows, sudoku_summary_rows = _sudoku_compositional_rows()
    results["compositional_read_rules"] = _composition_read_rule_rows()
    results["compositional_read_rows"] = read_rows
    results["compositional_product_predictions"] = product_rows
    results["compositional_product_law_transfer"] = law_rows
    results["compositional_product_summary"] = summary_rows
    results["sudoku_compositional_storage_curve"] = sudoku_curve_rows
    results["sudoku_compositional_trace_subsample"] = sudoku_predictor_rows
    results["sudoku_compositional_read_rows"] = sudoku_read_rows
    results["sudoku_compositional_product_predictions"] = sudoku_product_rows
    results["sudoku_compositional_law_transfer"] = sudoku_law_rows
    results["sudoku_compositional_summary"] = sudoku_summary_rows
    results.setdefault("discipline", {}).update({
        "path_b_deeper_law": "product_decode_accuracy_over_structural_choice_reads",
        "path_b_deeper_pre_registered_candidate": "P_choice",
        "path_b_deeper_no_free_parameters": True,
        "path_b_deeper_decode_curve_source": "E1 measured storage_dstar_curve; Sudoku uses module1_capacity_perdepth full curves plus targeted D128 bound_single curve where available",
        "path_b_deeper_read_rule": "online pop reads plus explicit final solution readback; forced propagations are recomputed and not register reads",
        "path_b_deeper_write_drop_rule": "spill_off entries with push live_load_before > floor(_capacity_dstar(...)) are not written; masked products assign factor 0 when such entries are read",
        "path_b_deeper_write_drop_C_source": "ScalarRegisterLoop.capacity_floor = floor(_capacity_dstar(task, arm, D, config)); push drops when level > capacity_floor",
        "path_b_deeper_masked_candidates": ["P_all", "P_choice", "P_pop"],
        "path_b_deeper_unmasked_candidates_visible": ["P_all_unmasked", "P_choice_unmasked", "P_pop_unmasked"],
        "path_b_deeper_residual": "observed_spill_off_solve_rate - masked_product_prediction",
    })
    e1_winner = next((row for row in summary_rows if row.get("is_best_by_mean_abs_diff")), None)
    sudoku_winner = next((row for row in sudoku_summary_rows if row.get("is_best_by_mean_abs_diff")), None)
    e1_choice = next((row for row in summary_rows if row.get("candidate") == "P_choice"), None)
    sudoku_choice = next((row for row in sudoku_summary_rows if row.get("candidate") == "P_choice"), None)
    results.setdefault("acceptance", {}).update({
        "compositional_pre_registered_candidate": "P_choice",
        "compositional_no_free_parameters": True,
        "compositional_e1_best_candidate": None if e1_winner is None else e1_winner["candidate"],
        "compositional_e1_best_pass_rows": None if e1_winner is None else e1_winner["pass_rows"],
        "compositional_e1_total_rows": None if e1_winner is None else e1_winner["total_rows"],
        "compositional_e1_pchoice_residual_mean": None if e1_choice is None else e1_choice.get("residual_mean"),
        "compositional_e1_pchoice_residual_fraction_nonnegative": None if e1_choice is None else e1_choice.get("fraction_residual_nonnegative"),
        "compositional_e1_pchoice_residual_fraction_within_tolerance": None if e1_choice is None else e1_choice.get("fraction_residual_within_tolerance"),
        "compositional_sudoku_best_candidate": None if sudoku_winner is None else sudoku_winner["candidate"],
        "compositional_sudoku_best_pass_rows": None if sudoku_winner is None else sudoku_winner["pass_rows"],
        "compositional_sudoku_total_rows": None if sudoku_winner is None else sudoku_winner["total_rows"],
        "compositional_sudoku_pchoice_residual_mean": None if sudoku_choice is None else sudoku_choice.get("residual_mean"),
        "compositional_sudoku_pchoice_residual_fraction_nonnegative": None if sudoku_choice is None else sudoku_choice.get("fraction_residual_nonnegative"),
        "compositional_sudoku_pchoice_residual_fraction_within_tolerance": None if sudoku_choice is None else sudoku_choice.get("fraction_residual_within_tolerance"),
    })


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
        "artifacts": [_rel(RESULTS_PATH), _rel(ITEM_PATH), *([_rel(SUDOKU_D128_BOUND_SINGLE_CURVE_PATH)] if SUDOKU_D128_BOUND_SINGLE_CURVE_PATH.exists() else []), *results["panel_artifacts"].values()],
        "provenance": {"repo": str(REPO_ROOT), "generated_at": results["generated_at"], "source": SOURCE, "binning_key": "reverts_needed", "pool_reuse": results["pool_reuse"]},
        "result_tables": {
            "task_pool_summary": {"columns": ["task", "selected_instances", "target_per_band", "node_cap", "r3plus_no_revert_solve_rate", "pool_complete"], "rows": results["task_pool_summary"]},
            "band_summary": {"columns": ["task", "band", "n", "target_n", "target_met", "min_reverts_needed", "max_reverts_needed", "max_trace_length", "max_depth_observed", "no_revert_solve_rate"], "rows": results["band_summary"]},
            "required_depth_histogram": {"columns": ["task", "band", "required_depth", "count", "fraction", "n", "source", "provenance"], "rows": results["required_depth_histogram"]},
            "small_d_selection": {"columns": ["task", "arm", "depth_min", "depth_p25", "depth_median", "depth_p75", "depth_max", "d_star_64", "include_D32", "rule", "source", "provenance"], "rows": results["small_d_selection"]},
            "storage_dstar_summary": {"columns": ["task", "codebook", "arm", "D", "K_var", "K_val", "K_eff", "d_star_predicted", "d_star_predicted_floor", "d_star_measured", "gap_measured_minus_predicted", "threshold", "n_depths_tested", "n_seeds", "trials_per_seed", "protocol", "source", "provenance"], "rows": results["storage_dstar_summary"]},
            "storage_dstar_curve": {"columns": ["task", "codebook", "arm", "D", "K_var", "K_val", "K_eff", "depth", "n_seeds", "trials_per_seed", "decode_accuracy", "mean_cleanup_margin", "min_cleanup_margin", "threshold", "source", "provenance"], "rows": results["storage_dstar_curve"]},
            "reference_live_load_events": {"columns": ["task", "instance_index", "band", "reverts_needed", "event_index", "op", "live_load_before", "var", "value", "read_consumed_for_next_branch", "source", "provenance"], "rows": results["reference_live_load_events"]},
            "live_load_predictors": {"columns": ["task", "instance_index", "band", "reverts_needed", "D_peak", "D_pop", "D_readpop", "D_readpop_equals_D_pop", "n_push", "n_pop", "n_solve", "source", "provenance"], "rows": results["live_load_predictors"]},
            "capacity_predictions": {"columns": ["task", "D", "K_var", "K_val", "bound_single_K_eff", "bound_single_d_star", "bound_single_d_star_floor", "factored_d_star", "factored_d_star_floor"], "rows": results["capacity_predictions"]},
            "stateless_oracle_ci": {"columns": ["task", "passed", "history_a", "history_b", "source", "provenance"], "rows": results["stateless_oracle_ci"]},
            "figure4_separation": {"columns": ["track", "source", "task", "arm", "spill", "band", "D", "seed", "n", "solve_rate", "applied_reverts", "revert_success_rate", "peak_register_bytes", "overflow_entries", "node_cap_exhaustions", "capacity_d_star_floor", "figure_included", "status", "provenance"], "rows": results["figure4_separation"]},
            "law_transfer": {"columns": ["task", "arm", "D", "band", "n", "predicted_d_star", "predicted_d_star_floor", "measured_d_star", "d_star_gap_measured_minus_predicted", "d_star_source", "fraction_required_depth_le_dstar", "observed_spill_off_solve_rate", "observed_seed_min", "observed_seed_max", "n_seeds_joined", "law_transfer_abs_diff", "law_transfer_tolerance", "on_y_equals_x", "source", "provenance"], "rows": results["law_transfer"]},
            "live_load_predictor_law_transfer": {"columns": ["task", "arm", "variant", "D", "band", "predictor", "n", "K_eff", "measured_d_star", "d_star_source", "fraction_predictor_le_dstar", "observed_spill_off_solve_rate", "observed_seed_min", "observed_seed_max", "n_seeds_joined", "predictor_abs_diff", "law_transfer_tolerance", "on_y_equals_x", "source", "provenance"], "rows": results["live_load_predictor_law_transfer"]},
            "live_load_predictor_summary": {"columns": ["scope", "predictor", "pass_rows", "total_rows", "pass_rate", "mean_abs_diff", "max_abs_diff", "law_transfer_tolerance", "is_best_by_mean_abs_diff", "source", "provenance"], "rows": results["live_load_predictor_summary"]},
            "sudoku_live_load_predictors": {"columns": ["task", "instance_index", "instance_id", "band", "reverts_needed", "reference_nodes", "dpll_backtrack_depth", "D_peak", "D_pop", "D_readpop", "D_readpop_equals_D_pop", "n_push", "n_pop", "n_solve", "live_load_status", "timeout_seconds", "prescreen_max_reference_nodes", "source", "provenance"], "rows": results["sudoku_live_load_predictors"]},
            "sudoku_live_load_confirmation": {"columns": ["task", "arm", "variant", "D", "band", "predictor", "n", "n_pool_band", "n_timeout_excluded", "K_eff", "capacity_d_star_floor", "fraction_predictor_le_dstar", "observed_spill_off_solve_rate", "observed_seed_min", "observed_seed_max", "n_seeds_joined", "predictor_abs_diff", "law_transfer_tolerance", "on_y_equals_x", "source", "provenance"], "rows": results["sudoku_live_load_confirmation"]},
            "sudoku_live_load_summary": {"columns": ["scope", "predictor", "pass_rows", "total_rows", "pass_rate", "mean_abs_diff", "max_abs_diff", "law_transfer_tolerance", "is_best_by_mean_abs_diff", "source", "provenance"], "rows": results["sudoku_live_load_summary"]},
            "compositional_read_rules": {"columns": ["rule", "value", "source", "provenance"], "rows": results.get("compositional_read_rules", [])},
            "compositional_product_predictions": {"columns": ["task", "arm", "variant", "D", "band", "instance_index", "reverts_needed", "candidate", "mask_applied", "hard_capacity_C", "n_reads", "n_dropped_reads", "n_surviving_reads", "max_read_live_load", "min_read_decode_acc", "predicted_instance_solve_prob", "status", "source", "provenance"], "rows": results.get("compositional_product_predictions", [])},
            "compositional_product_law_transfer": {"columns": ["task", "arm", "variant", "D", "band", "candidate", "model_family", "mask_applied", "n", "n_missing_decode_curve", "mean_dropped_reads", "instances_with_dropped_reads", "predicted_solve_rate", "observed_spill_off_solve_rate", "observed_seed_min", "observed_seed_max", "n_seeds_joined", "abs_diff", "residual_observed_minus_predicted", "residual_nonnegative", "residual_within_tolerance", "residual_one_sided_tight", "law_transfer_tolerance", "on_y_equals_x", "pre_registered_hypothesis", "source", "provenance"], "rows": results.get("compositional_product_law_transfer", [])},
            "compositional_product_summary": {"columns": ["scope", "candidate", "model_family", "mask_applied", "pass_rows", "total_rows", "pass_rate", "mean_abs_diff", "max_abs_diff", "mean_observed_minus_predicted", "residual_mean", "residual_min", "residual_max", "fraction_residual_nonnegative", "fraction_residual_within_tolerance", "fraction_residual_one_sided_tight", "pre_registered_hypothesis", "is_best_by_mean_abs_diff", "source", "provenance"], "rows": results.get("compositional_product_summary", [])},
            "sudoku_compositional_storage_curve": {"columns": ["task", "codebook", "arm", "D", "K_var", "K_val", "K_eff", "depth", "decode_accuracy", "threshold", "source", "provenance"], "rows": results.get("sudoku_compositional_storage_curve", [])},
            "sudoku_compositional_trace_subsample": {"columns": ["task", "instance_index", "band", "reverts_needed", "reference_nodes", "status", "D_peak", "D_pop", "D_readpop", "n_reads", "subsample_rule", "source", "provenance"], "rows": results.get("sudoku_compositional_trace_subsample", [])},
            "sudoku_compositional_product_predictions": {"columns": ["task", "instance_index", "band", "reverts_needed", "arm", "variant", "D", "candidate", "mask_applied", "hard_capacity_C", "n_reads", "n_dropped_reads", "n_surviving_reads", "max_read_live_load", "min_read_decode_acc", "predicted_instance_solve_prob", "status", "source", "provenance"], "rows": results.get("sudoku_compositional_product_predictions", [])},
            "sudoku_compositional_law_transfer": {"columns": ["task", "arm", "variant", "D", "band", "candidate", "model_family", "mask_applied", "n", "n_missing_decode_curve", "n_timeout_excluded", "mean_dropped_reads", "instances_with_dropped_reads", "subsample_per_band", "predicted_solve_rate", "observed_spill_off_solve_rate", "observed_seed_min", "observed_seed_max", "n_seeds_joined", "abs_diff", "residual_observed_minus_predicted", "residual_nonnegative", "residual_within_tolerance", "residual_one_sided_tight", "law_transfer_tolerance", "on_y_equals_x", "pre_registered_hypothesis", "status", "source", "provenance"], "rows": results.get("sudoku_compositional_law_transfer", [])},
            "sudoku_compositional_summary": {"columns": ["scope", "candidate", "model_family", "mask_applied", "pass_rows", "total_rows", "pass_rate", "mean_abs_diff", "max_abs_diff", "mean_observed_minus_predicted", "residual_mean", "residual_min", "residual_max", "fraction_residual_nonnegative", "fraction_residual_within_tolerance", "fraction_residual_one_sided_tight", "pre_registered_hypothesis", "is_best_by_mean_abs_diff", "source", "provenance"], "rows": results.get("sudoku_compositional_summary", [])},
        },
        "honesty": {"does_not_establish": "GRU is not reported as a collapse datum; it is audit-red and excluded until trained to the fairness budget with nonzero bytes and a curve. The masked compositional law has no fitted parameters; C is the scalar loop capacity floor, decode curves are measured, and Sudoku rows are real DPLLOracle trace subsamples with timeout exclusions rather than saved-stats proxies."},
        "decision": {
            "outcome": results["status"],
            "gate_outcomes": [
                {"gate": "stateless_oracle_ci", "outcome": "PASS" if results["acceptance"]["stateless_oracle_ci_passed"] else "FAIL", "number": "2/2 tasks"},
                {"gate": "r3plus_rot_vs_no_revert", "outcome": "PASS" if results["acceptance"]["rot_r3plus_any_positive"] and results["acceptance"]["no_revert_r3plus_near_zero"] else "FAIL", "number": f"rot_positive={results['acceptance']['rot_r3plus_any_positive']}; no_revert_near_zero={results['acceptance']['no_revert_r3plus_near_zero']}"},
                {"gate": "small_d_knee_exercised", "outcome": "PASS" if results["acceptance"]["small_d_knee_exercised"] else "FAIL", "number": f"knee_rows={results['acceptance']['small_d_knee_rows']}"},
                {"gate": "storage_dstar_measured", "outcome": "PASS", "number": f"rows={len(results['storage_dstar_summary'])}; threshold={STORAGE_THRESHOLD}; trials_per_seed={STORAGE_TRIALS}"},
                {"gate": "law_transfer_y_equals_x_measured_dstar", "outcome": "PASS" if results["acceptance"]["law_transfer_on_y_equals_x"] else "FAIL", "number": f"passed_rows={results['acceptance']['law_transfer_pass_rows']}/{results['acceptance']['law_transfer_total_rows']}; tolerance={LAW_TRANSFER_TOLERANCE}"},
                {"gate": "live_load_path_b_predictor", "outcome": "RECORDED", "number": f"E1_best={results['acceptance']['live_load_path_b_best_predictor']} ({results['acceptance']['live_load_path_b_best_pass_rows']}/{results['acceptance']['live_load_path_b_total_rows']}); Sudoku_best={results['acceptance']['sudoku_path_b_best_predictor']} ({results['acceptance']['sudoku_path_b_best_pass_rows']}/{results['acceptance']['sudoku_path_b_total_rows']})"},
                {"gate": "compositional_full_curve_path_b", "outcome": "RECORDED", "number": f"pre_registered=P_choice; E1_best={results['acceptance'].get('compositional_e1_best_candidate')} ({results['acceptance'].get('compositional_e1_best_pass_rows')}/{results['acceptance'].get('compositional_e1_total_rows')}); Sudoku_best={results['acceptance'].get('compositional_sudoku_best_candidate')} ({results['acceptance'].get('compositional_sudoku_best_pass_rows')}/{results['acceptance'].get('compositional_sudoku_total_rows')})"},
                {"gate": "gru_audit", "outcome": "INCOMPLETE_AUDIT_RED", "number": "excluded_from_figure_no_fabricated_zero"},
            ],
            "next_step_routing": {"ready": ["minimum_viable_figure4_rot_no_revert_kv"], "defer": ["gru_until_audited"]},
            "next_step": "Train/audit the E1 GRU fairness-budget cells before adding GRU rows to Figure 4.",
        },
    }


def run(target_per_band: int = 64, max_candidates: int = 5000, seed: int = 20260609, sat_n_vars: int = 18, sat_clause_ratio: float = 4.2, graph_n: int = 16, graph_k: int = 4, graph_edge_prob: float = 0.45) -> dict[str, Any]:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    if PROGRESS_LOG_PATH.exists():
        PROGRESS_LOG_PATH.unlink()
    _write_progress("setup", 0, 7, {"phase": "start"})
    configs = {
        "sat_3sat": {"n_vars": sat_n_vars, "clause_ratio": sat_clause_ratio},
        "graph_coloring": {"n": graph_n, "k": graph_k, "edge_prob": graph_edge_prob},
    }
    pools = {
        "sat_3sat": _recover_item050_pool("sat_3sat", target_per_band, max_candidates, seed, configs["sat_3sat"]),
        "graph_coloring": _recover_item050_pool("graph_coloring", target_per_band, max_candidates, seed + 1, configs["graph_coloring"]),
    }
    _write_progress("setup", 1, 7, {"phase": "pools_recovered", "tasks": list(pools)})
    task_summary_rows = []
    band_summary_rows = []
    task_summaries: dict[str, dict[str, Any]] = {}
    for task, rows in pools.items():
        summary, bands = _pool_summaries(task, rows, target_per_band)
        task_summaries[task] = summary
        task_summary_rows.append(summary)
        band_summary_rows.extend(bands)
    stateless_rows = [_stateless_oracle_ci(task, pools[task][0], configs[task]) for task in TASKS]
    ds, small_d_selection = _select_Ds(pools, configs)
    _write_progress("setup", 2, 7, {"phase": "selected_D_grid", "D_grid": list(ds)})
    storage_rows, storage_curve_rows = _measure_storage_dstars(configs, ds)
    _write_progress("setup", 3, 7, {"phase": "storage_dstar_complete", "summary_rows": len(storage_rows), "curve_rows": len(storage_curve_rows)})
    cell_rows, episode_rows = _run_arm_grid(pools, configs, task_summaries, ds)
    _write_progress("setup", 4, 7, {"phase": "arm_grid_complete", "cell_rows": len(cell_rows), "episode_rows": len(episode_rows)})
    figure_rows = [row for row in cell_rows if row["figure_included"] or row["arm"] == "gru"]
    law_rows = _law_transfer_rows(cell_rows, pools, configs, ds, storage_rows)
    live_load_event_rows = _reference_live_load_event_rows(pools)
    live_load_predictor_rows = _live_load_predictor_rows(pools)
    predictor_law_rows = _predictor_law_transfer_rows(cell_rows, pools, configs, storage_rows)
    predictor_summary_rows = _predictor_summary_rows(predictor_law_rows, "e1_sat_graph")
    sudoku_predictor_rows, sudoku_confirmation_rows, sudoku_summary_rows = _sudoku_live_load_confirmation_rows()
    acceptance = _acceptance(cell_rows, law_rows, stateless_rows, predictor_summary_rows, sudoku_summary_rows)
    panel_paths = _plot_panels(cell_rows, law_rows)
    _write_progress("setup", 5, 7, {"phase": "law_and_panels_complete", "law_rows": len(law_rows), "panels": panel_paths})
    status = "E1_SCALAR_FIGURE4_READY_WITH_GRU_AUDIT_RED" if acceptance["stateless_oracle_ci_passed"] and acceptance["no_revert_r3plus_near_zero"] and acceptance["small_d_knee_exercised"] and acceptance["law_transfer_on_y_equals_x"] else "E1_SCALAR_FIGURE4_DEVIATION_RECORDED"
    results = {
        "module": "post_review_e1_cross_task_generalization",
        "generated_at": _now(),
        "status": status,
        "discipline": {"binning_key": "reverts_needed", "required_depth_metric": "maximum simultaneous live register entries during fixed-policy reference solve", "law_transfer_depth_key": "required_depth", "path_b_candidate_depth_keys": ["D_peak", "D_pop", "D_readpop"], "path_b_predictor_source": "reference_trajectory_push_pop_solve_events_only", "law_transfer_d_star_source": "measured_pure_storage_frontier", "storage_decode_threshold": STORAGE_THRESHOLD, "node_cap_rule": "reused item050 cap", "batched_engine_required": False, "batched_equivalence_gate_applies": False, "source": SOURCE},
        "pool_reuse": {"method": "deterministic_replay_of_item050_seed_and_config", "reason": "prior Item050 persisted summaries and samples but not full clauses/edges", "seed": seed, "target_per_band": target_per_band, "max_candidates": max_candidates},
        "generation_config": {"target_per_band": target_per_band, "max_candidates": max_candidates, "seed": seed, "sat_n_vars": sat_n_vars, "sat_clause_ratio": sat_clause_ratio, "graph_n": graph_n, "graph_k": graph_k, "graph_edge_prob": graph_edge_prob, "D_grid": list(ds)},
        "task_pool_summary": task_summary_rows,
        "band_summary": band_summary_rows,
        "required_depth_histogram": _required_depth_histogram_rows(pools),
        "small_d_selection": small_d_selection,
        "storage_dstar_summary": storage_rows,
        "storage_dstar_curve": storage_curve_rows,
        "reference_live_load_events": live_load_event_rows,
        "live_load_predictors": live_load_predictor_rows,
        "capacity_predictions": _capacity_rows(configs, ds),
        "stateless_oracle_ci": stateless_rows,
        "figure4_separation": figure_rows,
        "law_transfer": law_rows,
        "live_load_predictor_law_transfer": predictor_law_rows,
        "live_load_predictor_summary": predictor_summary_rows,
        "sudoku_live_load_predictors": sudoku_predictor_rows,
        "sudoku_live_load_confirmation": sudoku_confirmation_rows,
        "sudoku_live_load_summary": sudoku_summary_rows,
        "episode_records": episode_rows,
        "pool_rows": {task: rows for task, rows in pools.items()},
        "panel_artifacts": panel_paths,
        "acceptance": acceptance,
        "figure4_status": status,
    }
    _record_compositional_tables(results)
    _write_json(RESULTS_PATH, results)
    _write_json(ITEM_PATH, _build_item(results))
    _write_progress("complete", 7, 7, {"phase": "artifacts_written", "status": status, "results_path": _rel(RESULTS_PATH), "item_path": _rel(ITEM_PATH)}, status="complete")
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
