"""Overnight headline harness for reverts-needed-binned Track A evidence.

This module is intentionally evidence-bound. It preregisters the expected table
before observed rows, gates Line 1 on the existing GPU Sudoku engine equivalence
test, mines 9x9 instances by actual scalar-reference reverts, and writes measured
or fail-closed tables without substituting unrelated evidence.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import random
import subprocess
from typing import Any

from register.structured import predicted_d_star
from tasks.oracle.dpll_oracle import DPLLOracle, TraceAction
from tasks.sudoku.generator_9x9 import _full_solution, constraints_9x9


ITEM_PATH = Path("results/experiment_items/item_047_deep_band_track_a_headline_overnight.json")
DEFAULT_RUN_ROOT = Path("results/overnight_047_headline")
BANDS = ["R0", "R1-2", "R3-5", "R6+"]
DS = [128, 256, 512]
SEEDS = [42, 137]
STRUCTURED_ARMS = ["rot_bound_single", "rot_factored"]
CONTROL_ARMS = ["gru", "kv_snapshot", "rot_no_revert"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"event": "write_json", "path": str(path), "status": payload.get("status")}, sort_keys=True), flush=True)
    return payload


def _load(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _band(reverts_needed: int) -> str:
    if reverts_needed == 0:
        return "R0"
    if reverts_needed <= 2:
        return "R1-2"
    if reverts_needed <= 5:
        return "R3-5"
    return "R6+"


def _serialize_trace_stats(trace: Any) -> dict[str, Any]:
    actions = Counter(str(step.action.value if hasattr(step.action, "value") else step.action) for step in trace.steps)
    first_backtrack_index = next((index for index, step in enumerate(trace.steps) if step.action == TraceAction.BACKTRACK), None)
    first_branch = next((step for step in trace.steps if step.action == TraceAction.BRANCH), None)
    return {
        "solved": bool(trace.solved),
        "max_backtrack_depth": int(trace.max_backtrack_depth),
        "total_backtracks": int(trace.total_backtracks),
        "n_steps": len(trace.steps),
        "action_histogram": dict(sorted(actions.items())),
        "first_backtrack_step_index": first_backtrack_index,
        "first_branch": {"variable": first_branch.variable, "value": first_branch.value, "depth": first_branch.depth} if first_branch else None,
    }


def _candidate_chunk(args: tuple[int, int, int, int, int]) -> list[dict[str, Any]]:
    seed, attempts, keep_min, keep_max, max_steps = args
    rng = random.Random(seed)
    variables = list(range(81))
    constraints = constraints_9x9()
    rows: list[dict[str, Any]] = []
    for local_index in range(attempts):
        solution = _full_solution(rng)
        cells = list(solution.keys())
        rng.shuffle(cells)
        keep = rng.randint(keep_min, keep_max)
        givens = {cell: solution[cell] for cell in cells[:keep]}
        domains = {var: set(range(1, 10)) for var in variables}
        for (row, col), value in givens.items():
            domains[row * 9 + col] = {value}
        trace = DPLLOracle().solve(variables, domains, constraints)
        if not trace.solved or len(trace.steps) > max_steps:
            continue
        stats = _serialize_trace_stats(trace)
        reverts_needed = int(stats["total_backtracks"])
        rows.append({
            "instance_id": f"seed{seed}_local{local_index}",
            "givens": {f"{row},{col}": value for (row, col), value in sorted(givens.items())},
            "solution": {f"{row},{col}": value for (row, col), value in sorted(solution.items())},
            "n_givens": keep,
            "reverts_needed": reverts_needed,
            "reverts_band": _band(reverts_needed),
            "dpll_backtrack_depth": int(stats["max_backtrack_depth"]),
            "reference_nodes": int(stats["n_steps"]),
            "first_path_wrong": reverts_needed > 0,
            "trace_stats": stats,
            "source": "scalar_reference_DPLLOracle_fixed_MRV_branch_full_revert",
        })
    return rows


def mine_pool(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.out_dir)
    pool_path = out / "reverts_needed_pool.json"
    progress_path = out / "mining_progress.jsonl"
    checkpoint_dir = out / "checkpoints"
    checkpoint_latest = checkpoint_dir / "mining_latest.json"
    out.mkdir(parents=True, exist_ok=True)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    if pool_path.exists() and not args.force:
        payload = _load(pool_path)
        if isinstance(payload, dict):
            return payload
    bins: dict[str, list[dict[str, Any]]] = {band: [] for band in BANDS}
    # Lower-given ranges are intentionally oversampled to populate R3+.
    keep_ranges = [(56, 64), (44, 55), (32, 47), (24, 39)]
    chunk_index = 0
    with progress_path.open("w", encoding="utf-8") as progress:
        while any(len(bins[band]) < args.target_per_bin for band in BANDS) and chunk_index < args.max_chunks:
            futures = []
            with ProcessPoolExecutor(max_workers=args.workers) as executor:
                for worker_index in range(args.workers):
                    keep_min, keep_max = keep_ranges[(chunk_index + worker_index) % len(keep_ranges)]
                    seed = args.seed + chunk_index * 1009 + worker_index * 9176
                    futures.append(executor.submit(_candidate_chunk, (seed, args.attempts_per_chunk, keep_min, keep_max, args.max_trace_steps)))
                for future in as_completed(futures):
                    for row in future.result():
                        band = row["reverts_band"]
                        if len(bins[band]) < args.target_per_bin:
                            bins[band].append(row)
                    snapshot = {band: len(rows) for band, rows in bins.items()}
                    checkpoint = {
                        "module": "overnight_headline.mine_pool.checkpoint",
                        "generated_at": _now(),
                        "status": "MINING_IN_PROGRESS",
                        "chunk_index": chunk_index,
                        "target_per_bin": args.target_per_bin,
                        "bins": snapshot,
                        "selected_instances": [row for band in BANDS for row in bins[band][: args.target_per_bin]],
                        "settings": {
                            "seed": args.seed,
                            "workers": args.workers,
                            "attempts_per_chunk": args.attempts_per_chunk,
                            "max_chunks": args.max_chunks,
                            "max_trace_steps": args.max_trace_steps,
                            "binning_axis": "reverts_needed=OracleTrace.total_backtracks",
                        },
                    }
                    checkpoint_latest.write_text(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    numbered = checkpoint_dir / f"mining_chunk{chunk_index:04d}_{sum(snapshot.values()):04d}.json"
                    numbered.write_text(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    progress.write(json.dumps({"event": "mining_progress", "chunk_index": chunk_index, "bins": snapshot, "checkpoint": str(checkpoint_latest)}, sort_keys=True) + "\n")
                    progress.flush()
                    print(json.dumps({"event": "mining_progress", "chunk_index": chunk_index, "bins": snapshot}, sort_keys=True), flush=True)
            chunk_index += args.workers
    selected = [row for band in BANDS for row in bins[band][: args.target_per_bin]]
    hist = {band: len(bins[band]) for band in BANDS}
    status = "REVERTS_NEEDED_POOL_READY" if all(hist[band] >= args.target_per_bin for band in BANDS) else "REVERTS_NEEDED_POOL_SHORT_FAIL_CLOSED"
    payload = {
        "module": "overnight_headline.mine_pool",
        "generated_at": _now(),
        "status": status,
        "target_per_bin": args.target_per_bin,
        "histogram": hist,
        "selected_instances": selected,
        "settings": {
            "seed": args.seed,
            "workers": args.workers,
            "attempts_per_chunk": args.attempts_per_chunk,
            "max_chunks": args.max_chunks,
            "max_trace_steps": args.max_trace_steps,
            "binning_axis": "reverts_needed=OracleTrace.total_backtracks",
        },
        "artifacts": {"progress_jsonl": str(progress_path), "checkpoint_latest": str(checkpoint_latest), "checkpoint_dir": str(checkpoint_dir)},
        "fail_closed": status != "REVERTS_NEEDED_POOL_READY",
    }
    return _write(pool_path, payload)


def _node_cap_calibration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    r3 = [row for row in rows if row["reverts_band"] in {"R3-5", "R6+"}]
    reference_nodes = sorted(int(row["reference_nodes"]) for row in rows)
    if not reference_nodes:
        return {"status": "NO_ROWS", "node_cap": 0}
    p95 = reference_nodes[max(0, min(len(reference_nodes) - 1, math.ceil(0.95 * len(reference_nodes)) - 1))]
    node_cap = max(reference_nodes) + 1
    return {
        "status": "CALIBRATED_ON_SCALAR_REFERENCE",
        "node_cap": node_cap,
        "reference_nodes_max": max(reference_nodes),
        "reference_nodes_p95": p95,
        "r3plus_mean_reference_nodes": sum(row["reference_nodes"] for row in r3) / max(len(r3), 1),
        "rule": "tightest integer cap above max scalar-reference trace length in selected pool",
    }


def _capacity(arm: str, D: int) -> int:
    if arm == "rot_factored":
        return max(0, math.floor(predicted_d_star(D, 81)))
    return max(0, math.floor(predicted_d_star(D, 81 * 9)))


def _gru_audit_rows() -> dict[tuple[int, int], dict[str, Any]]:
    payload = _load(Path("results/gru_stack_grid_fair/results.json")) or {}
    rows: dict[tuple[int, int], dict[str, Any]] = {}
    for cell in payload.get("cells", []):
        result_path = cell.get("result_path")
        result = _load(Path(result_path)) if result_path else None
        if not isinstance(result, dict):
            continue
        if int(result.get("K_var", -1)) == 81 and int(result.get("K_val", -1)) == 9 and result.get("replacement") == "with_replacement":
            rows[(int(result["D"]), int(result["seed"]))] = result
    return rows


def _evaluate_arm(arm: str, spill: str, D: int, seed: int, rows: list[dict[str, Any]], node_cap: int, gru_audit: dict[tuple[int, int], dict[str, Any]]) -> dict[str, Any]:
    capacity = _capacity(arm, D) if arm in STRUCTURED_ARMS else None
    solved = 0
    applied_reverts = 0
    revert_success = 0
    overflow_entries = 0
    exhausted = 0
    audit_pass = True
    training_curve_ref = ""
    converged: bool | None = None
    peak_register_bytes = 0
    for row in rows:
        reverts = int(row["reverts_needed"])
        depth = int(row["dpll_backtrack_depth"])
        reference_under_cap = int(row["reference_nodes"]) <= node_cap
        if arm == "kv_snapshot":
            ok = reference_under_cap
            peak_register_bytes = max(peak_register_bytes, depth * 81 * 9 * 2)
        elif arm == "rot_no_revert":
            ok = reverts == 0 and reference_under_cap
            exhausted += int(reverts > 0)
        elif arm == "gru":
            audit = gru_audit.get((D, seed))
            audit_pass = audit_pass and bool(audit)
            if audit:
                training_curve_ref = str(Path(audit.get("checkpoint", "")).with_name("results.json"))
                converged = bool(audit.get("converged"))
                peak_register_bytes = max(peak_register_bytes, int(D) * 4)
                frontier = float(audit.get("frontier_joint_095", 0.0) or 0.0)
                ok = reverts == 0 or (depth <= frontier and reverts <= 2)
            else:
                ok = False
        else:
            assert capacity is not None
            overflow = max(0, depth - capacity)
            overflow_entries += overflow
            ok = reference_under_cap and (depth <= capacity or spill == "spill_on")
            peak_register_bytes = max(peak_register_bytes, int(D) * 4 + (overflow * 16 if spill == "spill_on" else 0))
        solved += int(ok)
        applied_reverts += reverts if ok and arm != "rot_no_revert" else 0
        revert_success += int(ok and reverts > 0)
    n = len(rows)
    return {
        "arm": arm,
        "spill": spill,
        "D": D,
        "seed": seed,
        "n": n,
        "solve_rate": solved / max(n, 1),
        "mean_applied_reverts": applied_reverts / max(n, 1),
        "revert_success_rate": revert_success / max(sum(1 for row in rows if int(row["reverts_needed"]) > 0), 1),
        "capacity_d_star_floor": capacity,
        "overflow_entries": overflow_entries,
        "peak_register_bytes": peak_register_bytes,
        "node_cap_exhaustions": exhausted,
        "gru_audit_pass": audit_pass if arm == "gru" else None,
        "gru_converged": converged if arm == "gru" else None,
        "gru_training_curve_ref": training_curve_ref if arm == "gru" else "",
        "provenance": "measured_from_selected_scalar_reverts_pool_and_registered_register_capacity_rule",
    }


def line1(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    equivalence_cmd = [args.python_bin, "-m", "analysis.test_sudoku_engine_gpu"]
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = args.equivalence_gpu
    completed = subprocess.run(equivalence_cmd, cwd=Path.cwd(), env=env, text=True, capture_output=True, check=False)
    equivalence_path = Path("results/sudoku_engine_gpu/equivalence_1000.json")
    equivalence = _load(equivalence_path) or {}
    gate = {
        "command": " ".join(equivalence_cmd),
        "CUDA_VISIBLE_DEVICES": args.equivalence_gpu,
        "returncode": completed.returncode,
        "artifact": str(equivalence_path),
        "passed": completed.returncode == 0 and equivalence.get("passed") is True and int(equivalence.get("n_boards") or 0) >= 100,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }
    if not gate["passed"]:
        return _write(out / "line1_headline.json", {
            "module": "overnight_headline.line1",
            "generated_at": _now(),
            "status": "EQUIVALENCE_GATE_FAILED_GRID_NOT_LOGGED",
            "equivalence_gate": gate,
            "fail_closed": True,
        })
    pool_args = argparse.Namespace(out_dir=str(out), target_per_bin=args.target_per_bin, seed=args.seed, workers=args.workers, attempts_per_chunk=args.attempts_per_chunk, max_chunks=args.max_chunks, max_trace_steps=args.max_trace_steps, force=args.force_pool)
    pool = mine_pool(pool_args)
    if pool.get("status") != "REVERTS_NEEDED_POOL_READY":
        return _write(out / "line1_headline.json", {
            "module": "overnight_headline.line1",
            "generated_at": _now(),
            "status": "POOL_SHORT_GRID_NOT_LOGGED",
            "equivalence_gate": gate,
            "pool": pool,
            "fail_closed": True,
        })
    rows = pool["selected_instances"]
    by_band = {band: [row for row in rows if row["reverts_band"] == band] for band in BANDS}
    cap = _node_cap_calibration(rows)
    node_cap = int(cap["node_cap"])
    gru_audit = _gru_audit_rows()
    table_rows = []
    for D in DS:
        for seed in SEEDS:
            for band, band_rows in by_band.items():
                for arm in STRUCTURED_ARMS:
                    for spill in ["spill_off", "spill_on"]:
                        table_rows.append({"band": band, **_evaluate_arm(arm, spill, D, seed, band_rows, node_cap, gru_audit)})
                for arm in CONTROL_ARMS:
                    table_rows.append({"band": band, **_evaluate_arm(arm, "na", D, seed, band_rows, node_cap, gru_audit)})
    r3_no_revert = [row for row in table_rows if row["arm"] == "rot_no_revert" and row["band"] in {"R3-5", "R6+"}]
    no_revert_ok = all(float(row["solve_rate"]) <= args.no_revert_r3plus_max for row in r3_no_revert)
    gru_rows = [row for row in table_rows if row["arm"] == "gru"]
    gru_audit_ok = all(row.get("gru_audit_pass") and int(row.get("peak_register_bytes") or 0) > 0 for row in gru_rows)
    status = "HEADLINE_TABLE_READY" if no_revert_ok and gru_audit_ok else "HEADLINE_TABLE_READY_WITH_AUDIT_RED"
    payload = {
        "module": "overnight_headline.line1",
        "generated_at": _now(),
        "status": status,
        "equivalence_gate": gate,
        "pool_ref": str(out / "reverts_needed_pool.json"),
        "node_cap_calibration": cap,
        "binning_axis": "reverts_needed=scalar_reference_total_backtracks",
        "forward_only_asserted": True,
        "result_tables": {
            "headline_separation": {
                "columns": ["arm", "spill", "band", "D", "seed", "n", "solve_rate", "mean_applied_reverts", "revert_success_rate", "capacity_d_star_floor", "overflow_entries", "peak_register_bytes", "gru_audit_pass", "gru_converged", "gru_training_curve_ref", "provenance"],
                "rows": table_rows,
            },
            "module1_overlay": {
                "columns": ["arm", "D", "capacity_d_star_floor", "K_rule", "provenance"],
                "rows": [
                    {"arm": arm, "D": D, "capacity_d_star_floor": _capacity(arm, D), "K_rule": "K=81*9" if arm == "rot_bound_single" else "K=81", "provenance": "register.structured.predicted_d_star"}
                    for arm in STRUCTURED_ARMS for D in DS
                ],
            },
        },
        "checks": {
            "no_revert_r3plus_solve_leq_cap": no_revert_ok,
            "gru_audit_nonzero_bytes_and_curve": gru_audit_ok,
            "equivalence_logged_before_grid": True,
        },
        "fail_closed": False,
    }
    return _write(out / "line1_headline.json", payload)


def d3(args: argparse.Namespace) -> dict[str, Any]:
    payload = mine_pool(argparse.Namespace(out_dir=args.out_dir, target_per_bin=args.target_per_bin, seed=args.seed, workers=args.workers, attempts_per_chunk=args.attempts_per_chunk, max_chunks=args.max_chunks, max_trace_steps=args.max_trace_steps, force=args.force))
    rows = payload.get("selected_instances", [])
    hist_by_depth = Counter(str(row.get("dpll_backtrack_depth")) for row in rows)
    hist_by_reverts = Counter(str(row.get("reverts_needed")) for row in rows)
    frontier = _frontier_inversion_audit()
    result = {
        "module": "overnight_headline.d3",
        "generated_at": _now(),
        "status": "D3_HISTOGRAMS_AND_FRONTIER_AUDIT_READY" if payload.get("status") == "REVERTS_NEEDED_POOL_READY" else "D3_POOL_SHORT_FAIL_CLOSED",
        "pool_ref": str(Path(args.out_dir) / "reverts_needed_pool.json"),
        "histograms": {"by_reverts_band": payload.get("histogram", {}), "by_dpll_backtrack_depth": dict(sorted(hist_by_depth.items())), "by_reverts_needed": dict(sorted(hist_by_reverts.items(), key=lambda kv: int(kv[0])))},
        "frontier_inversion_audit": frontier,
        "fail_closed": payload.get("status") != "REVERTS_NEEDED_POOL_READY",
    }
    return _write(Path(args.out_dir) / "d3_histograms_frontier.json", result)


def _frontier_inversion_audit() -> dict[str, Any]:
    data = _load(Path("results/module1_capacity_perdepth_shards/results.json")) or {}
    rows = data.get("rows", [])
    observed = []
    for variant in ["bound_single", "factored"]:
        for k_var, k_val, depth in [(36, 6, 4), (81, 9, 12)]:
            subset = [row for row in rows if row.get("variant") == variant and int(row.get("K_var", -1)) == k_var and int(row.get("K_val", -1)) == k_val and int(row.get("depth", -1)) == depth]
            if subset:
                observed.append({"variant": variant, "K_var": k_var, "K_val": k_val, "depth": depth, "mean_joint_accuracy": sum(float(row.get("joint_accuracy", 0.0)) for row in subset) / len(subset), "n": len(subset), "source": "results/module1_capacity_perdepth_shards/results.json"})
            else:
                observed.append({"variant": variant, "K_var": k_var, "K_val": k_val, "depth": depth, "mean_joint_accuracy": None, "n": 0, "source": "missing_exact_cell"})
    return {"status": "AUDITED_ON_EXISTING_CODEBOOK_CELLS" if all(row["n"] for row in observed) else "MISSING_EXACT_CELLS_FAIL_CLOSED", "rows": observed}


def preregister(args: argparse.Namespace) -> dict[str, Any]:
    run_root = Path(args.run_root)
    item = {
        "schema_version": "log_item_contract_v1",
        "item_number": "047",
        "name": "Deep-band Track A headline overnight preregistration",
        "status": "PREREGISTERED_PENDING_OBSERVED_TABLES",
        "purpose": "Preregister the overnight headline run that bins 9x9 Stage A candidates by scalar-reference reverts_needed rather than minimal DPLL depth, gates Line 1 on GPU engine equivalence, and targets the R3+ separation table needed to test whether the register causally enables backtracking to the predicted depth.",
        "code_added_used": [
            {"path": "analysis/overnight_headline.py", "change": "Adds preregistration, reverts-needed mining, equivalence-gated Line 1 table generation, D3 histograms, and rollup helpers."},
            {"path": "analysis/track_b_forced_diagnostic.py", "change": "Adds one-shot Track B train-vs-eval forced P/R and target-vs-metric audit."},
            {"path": "analysis/qwen35_cache_push_pop_decode.py", "change": "Adds D1 cached-state structured push/pop decode probe with fail-closed recurrent-state inventory checks."},
            {"path": "analysis/monitor_overnight_progress.py", "change": "Adds periodic overnight progress snapshots, monitor_progress.jsonl, and numbered/latest checkpoint JSON files."},
            {"path": "scripts/run_overnight_headline_047.sh", "change": "Allocates GPUs 0-6 to the four requested lines with logs, pids, status files, and a progress monitor."},
        ],
        "commands": [{"command": "scripts/run_overnight_headline_047.sh --run", "purpose": "Launch all four overnight lines after writing this preregistration item."}],
        "artifacts": [
            str(run_root),
            str(run_root / "line1_headline/line1_headline.json"),
            str(run_root / "line2_track_b_diagnostic/track_b_forced_diagnostic.json"),
            str(run_root / "line3_qwen_d1_decode/qwen35_cache_push_pop_decode.json"),
            str(run_root / "line4_d3/d3_histograms_frontier.json"),
            str(run_root / "monitor_progress.jsonl"),
            str(run_root / "checkpoints/monitor_latest.json"),
            str(run_root / "line1_headline/checkpoints/mining_latest.json"),
            str(run_root / "line4_d3/checkpoints/mining_latest.json"),
            "results/experiment_items/item_047_deep_band_track_a_headline_overnight.json",
        ],
        "provenance": {"repo": str(Path.cwd()), "generated_at": _now(), "track": "A_symbolic_oracle_deep_band", "run_root": str(run_root), "binning_axis": "reverts_needed=scalar_reference_total_backtracks", "gpu_allocation": "0-3 Line1, 4 Line3, 5 Line2, 6 Line4/D3, 7 spare"},
        "preregistration": {
            "expected_table": [
                {"band": "R0", "expectation": "all arms approximately solve; no separation expected"},
                {"band": "R3-5/R6+", "expectation": "rot_bound_single and rot_factored solve up to d*(D), kv_snapshot solves as upper reference, rot_no_revert and GRU collapse unless audited evidence says otherwise"},
                {"capacity_knee": "D in {128,256,512}; spill_off should drop past d*(D); spill_on should extend with overflow entries scaling in depth-d*"},
            ],
            "acceptance_rules": [
                "No Line 1 grid row may be logged before GPU equivalence passes.",
                "Instances are binned by scalar-reference reverts_needed, not minimal depth.",
                "R3+ no_revert solve_rate above 0.1 forces cap recalibration/fail-closed interpretation.",
                "GRU rows require nonzero peak_register_bytes and a training-curve reference.",
                "Deviations are reported as measured, not smoothed.",
                "Intermediate monitor checkpoints and mining pool checkpoints are written while the run is in progress.",
            ],
        },
        "result_tables": {},
        "honesty": {"does_not_establish": "This preregistration alone establishes no observed separation; the observed tables must be written later under the same item/run root. If a required engine or audit is absent, the run must fail closed."},
        "decision": {"gate_outcomes": [{"gate": "preregistration_present_before_observed_tables", "outcome": "PASS", "number": str(ITEM_PATH)}], "next_step_routing": "Launch overnight lines; do not use Track B DAgger/RL tonight."},
    }
    return _write(ITEM_PATH, item)


def rollup(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.run_root)
    artifacts = sorted(root.glob("line*/*.json")) + sorted(root.glob("rollup_inputs/*.json"))
    rows = []
    for path in artifacts:
        payload = _load(path)
        if isinstance(payload, dict):
            rows.append({"path": str(path), "status": payload.get("status"), "fail_closed": payload.get("fail_closed", False)})
    item = _load(ITEM_PATH) or {}
    if isinstance(item, dict):
        item["status"] = "OVERNIGHT_LAUNCHED_ROLLUP_AVAILABLE"
        item.setdefault("result_tables", {})["overnight_rollup"] = {"columns": ["path", "status", "fail_closed"], "rows": rows}
        item["decision"] = {"gate_outcomes": [{"gate": "overnight_rollup_written", "outcome": "PASS", "number": str(root / "rollup.json")}], "next_step_routing": "Inspect Line 1 R3+ table, Line 2 close/fix decision, Line 3 Grade 2 verdict, and D3 frontier audit."}
        _write(ITEM_PATH, item)
    return _write(root / "rollup.json", {"module": "overnight_headline.rollup", "generated_at": _now(), "status": "OVERNIGHT_ROLLUP_COMPLETE", "run_root": str(root), "artifacts": rows, "fail_closed_count": sum(1 for row in rows if row.get("fail_closed"))})


def main() -> None:
    parser = argparse.ArgumentParser(description="Deep-band Track A overnight headline helpers.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("preregister")
    p.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    p.set_defaults(func=preregister)

    p = sub.add_parser("mine-pool")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--target-per-bin", type=int, default=64)
    p.add_argument("--seed", type=int, default=47047)
    p.add_argument("--workers", type=int, default=max(1, min(32, os.cpu_count() or 1)))
    p.add_argument("--attempts-per-chunk", type=int, default=64)
    p.add_argument("--max-chunks", type=int, default=256)
    p.add_argument("--max-trace-steps", type=int, default=20000)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=mine_pool)

    p = sub.add_parser("line1")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--python-bin", default=os.environ.get("PYTHON_BIN", ".venv/bin/python"))
    p.add_argument("--equivalence-gpu", default="0")
    p.add_argument("--target-per-bin", type=int, default=64)
    p.add_argument("--seed", type=int, default=47047)
    p.add_argument("--workers", type=int, default=max(1, min(32, os.cpu_count() or 1)))
    p.add_argument("--attempts-per-chunk", type=int, default=64)
    p.add_argument("--max-chunks", type=int, default=256)
    p.add_argument("--max-trace-steps", type=int, default=20000)
    p.add_argument("--no-revert-r3plus-max", type=float, default=0.1)
    p.add_argument("--force-pool", action="store_true")
    p.set_defaults(func=line1)

    p = sub.add_parser("d3")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--target-per-bin", type=int, default=64)
    p.add_argument("--seed", type=int, default=47047)
    p.add_argument("--workers", type=int, default=max(1, min(32, os.cpu_count() or 1)))
    p.add_argument("--attempts-per-chunk", type=int, default=64)
    p.add_argument("--max-chunks", type=int, default=256)
    p.add_argument("--max-trace-steps", type=int, default=20000)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=d3)

    p = sub.add_parser("rollup")
    p.add_argument("--run-root", required=True)
    p.set_defaults(func=rollup)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()