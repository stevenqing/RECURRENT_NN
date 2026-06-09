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
from statistics import mean, median, quantiles
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
SUDOKU_LIVE_LOAD_TIMEOUT_SECONDS = 3
SUDOKU_LIVE_LOAD_PRESCREEN_MAX_NODES = 0
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
        },
        "honesty": {"does_not_establish": "GRU is not reported as a collapse datum; it is audit-red and excluded until trained to the fairness budget with nonzero bytes and a curve."},
        "decision": {
            "outcome": results["status"],
            "gate_outcomes": [
                {"gate": "stateless_oracle_ci", "outcome": "PASS" if results["acceptance"]["stateless_oracle_ci_passed"] else "FAIL", "number": "2/2 tasks"},
                {"gate": "r3plus_rot_vs_no_revert", "outcome": "PASS" if results["acceptance"]["rot_r3plus_any_positive"] and results["acceptance"]["no_revert_r3plus_near_zero"] else "FAIL", "number": f"rot_positive={results['acceptance']['rot_r3plus_any_positive']}; no_revert_near_zero={results['acceptance']['no_revert_r3plus_near_zero']}"},
                {"gate": "small_d_knee_exercised", "outcome": "PASS" if results["acceptance"]["small_d_knee_exercised"] else "FAIL", "number": f"knee_rows={results['acceptance']['small_d_knee_rows']}"},
                {"gate": "storage_dstar_measured", "outcome": "PASS", "number": f"rows={len(results['storage_dstar_summary'])}; threshold={STORAGE_THRESHOLD}; trials_per_seed={STORAGE_TRIALS}"},
                {"gate": "law_transfer_y_equals_x_measured_dstar", "outcome": "PASS" if results["acceptance"]["law_transfer_on_y_equals_x"] else "FAIL", "number": f"passed_rows={results['acceptance']['law_transfer_pass_rows']}/{results['acceptance']['law_transfer_total_rows']}; tolerance={LAW_TRANSFER_TOLERANCE}"},
                {"gate": "live_load_path_b_predictor", "outcome": "RECORDED", "number": f"E1_best={results['acceptance']['live_load_path_b_best_predictor']} ({results['acceptance']['live_load_path_b_best_pass_rows']}/{results['acceptance']['live_load_path_b_total_rows']}); Sudoku_best={results['acceptance']['sudoku_path_b_best_predictor']} ({results['acceptance']['sudoku_path_b_best_pass_rows']}/{results['acceptance']['sudoku_path_b_total_rows']})"},
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
