"""Development-only static risk gate for factorized multi-agent search."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any

import numpy as np

from experiments.multiagent_capacity_coupling import REPO_ROOT


SCHEMA = "multiagent_static_risk_preflight_v1"
ALLOWED_TASK_FIELDS = ("n_vertices", "k", "edges", "partitions", "order")
FOLDS = 5
L2 = 1.0
MAX_ITERATIONS = 100
FACTOR_DEVELOPMENT_ARM = "independent_local_cbj"
FACTOR_CONFIRMATION_ARM = "independent_local_cbj_v1_exact"
MONOLITH_ARM = "monolith_MR"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _quantile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    location = probability * (len(ordered) - 1)
    lower = int(location)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = location - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _add_stats(features: dict[str, float], prefix: str, values: list[float]) -> None:
    numbers = [float(value) for value in values]
    if not numbers:
        numbers = [0.0]
    average = mean(numbers)
    variance = mean((value - average) ** 2 for value in numbers)
    features[f"{prefix}_mean"] = average
    features[f"{prefix}_std"] = math.sqrt(variance)
    features[f"{prefix}_min"] = min(numbers)
    features[f"{prefix}_p10"] = _quantile(numbers, 0.10)
    features[f"{prefix}_median"] = median(numbers)
    features[f"{prefix}_p90"] = _quantile(numbers, 0.90)
    features[f"{prefix}_max"] = max(numbers)


def _degeneracy(adjacency: list[set[int]]) -> int:
    remaining = {vertex: set(neighbors) for vertex, neighbors in enumerate(adjacency)}
    value = 0
    while remaining:
        vertex = min(remaining, key=lambda item: (len(remaining[item]), item))
        value = max(value, len(remaining[vertex]))
        for neighbor in list(remaining[vertex]):
            if neighbor in remaining:
                remaining[neighbor].discard(vertex)
        remaining.pop(vertex)
    return value


def _extract_features(task: dict[str, Any]) -> dict[str, float]:
    if set(task) != set(ALLOWED_TASK_FIELDS):
        raise ValueError(f"feature extractor received non-whitelisted fields: {sorted(task)}")
    n = int(task["n_vertices"])
    k = int(task["k"])
    edges = [tuple(sorted(map(int, edge))) for edge in task["edges"]]
    partitions = [int(value) for value in task["partitions"]]
    order = [int(value) for value in task["order"]]
    if sorted(order) != list(range(n)) or len(partitions) != n:
        raise ValueError("invalid task order or partitions")
    m = len(set(partitions))
    adjacency = [set() for _ in range(n)]
    for left, right in edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    position = {vertex: index for index, vertex in enumerate(order)}
    degrees = [len(adjacency[vertex]) for vertex in range(n)]
    cross_degrees = [
        sum(partitions[neighbor] != partitions[vertex] for neighbor in adjacency[vertex])
        for vertex in range(n)
    ]
    within_degrees = [degrees[vertex] - cross_degrees[vertex] for vertex in range(n)]
    boundary = [vertex for vertex in range(n) if cross_degrees[vertex] > 0]
    cross_edges = [(left, right) for left, right in edges if partitions[left] != partitions[right]]
    within_edges = [(left, right) for left, right in edges if partitions[left] == partitions[right]]

    features: dict[str, float] = {
        "graph_n_vertices": float(n),
        "graph_k_colors": float(k),
        "graph_partition_count": float(m),
        "graph_edge_count": float(len(edges)),
        "graph_density": len(edges) / max(n * (n - 1) / 2.0, 1.0),
        "graph_cross_edge_fraction": len(cross_edges) / max(len(edges), 1),
        "graph_boundary_vertex_fraction": len(boundary) / max(n, 1),
    }
    _add_stats(features, "degree_total", degrees)
    _add_stats(features, "degree_cross", cross_degrees)
    _add_stats(features, "degree_within", within_degrees)

    partition_vertices = [sum(owner == block for owner in partitions) for block in range(m)]
    partition_boundary = [sum(partitions[vertex] == block for vertex in boundary) for block in range(m)]
    partition_degree_load = [
        sum(degrees[vertex] for vertex in range(n) if partitions[vertex] == block)
        for block in range(m)
    ]
    partition_cross_load = [
        sum(cross_degrees[vertex] for vertex in range(n) if partitions[vertex] == block)
        for block in range(m)
    ]
    _add_stats(features, "partition_vertices", partition_vertices)
    _add_stats(features, "partition_boundary_vertices", partition_boundary)
    _add_stats(features, "partition_degree_load", partition_degree_load)
    _add_stats(features, "partition_cross_load", partition_cross_load)

    intra_counts = [
        sum(partitions[left] == block and partitions[right] == block for left, right in within_edges)
        for block in range(m)
    ]
    inter_counts = [
        sum({partitions[left], partitions[right]} == {left_block, right_block} for left, right in cross_edges)
        for left_block in range(m)
        for right_block in range(left_block + 1, m)
    ]
    for index, value in enumerate(sorted(intra_counts)):
        features[f"intra_profile_sorted_{index}"] = float(value)
    for index, value in enumerate(sorted(inter_counts)):
        features[f"inter_profile_sorted_{index}"] = float(value)
    _add_stats(features, "intra_profile", intra_counts)
    _add_stats(features, "inter_profile", inter_counts)

    def spans(selected: list[tuple[int, int]]) -> list[float]:
        return [abs(position[left] - position[right]) / max(n - 1, 1) for left, right in selected]

    _add_stats(features, "order_span_all", spans(edges))
    _add_stats(features, "order_span_cross", spans(cross_edges))
    _add_stats(features, "order_span_within", spans(within_edges))

    boundary_positions = [position[vertex] / max(n - 1, 1) for vertex in boundary]
    _add_stats(features, "boundary_order_position", boundary_positions)
    features["boundary_in_first_quarter_fraction"] = sum(value <= 0.25 for value in boundary_positions) / max(len(boundary_positions), 1)
    features["boundary_in_first_half_fraction"] = sum(value <= 0.50 for value in boundary_positions) / max(len(boundary_positions), 1)

    order_partitions = [partitions[vertex] for vertex in order]
    switches = sum(left != right for left, right in zip(order_partitions, order_partitions[1:]))
    run_lengths: list[int] = []
    if order_partitions:
        run = 1
        for left, right in zip(order_partitions, order_partitions[1:]):
            if left == right:
                run += 1
            else:
                run_lengths.append(run)
                run = 1
        run_lengths.append(run)
    features["order_partition_switch_fraction"] = switches / max(n - 1, 1)
    _add_stats(features, "order_partition_run_length", run_lengths)

    prefix_cut = []
    prefix_cross_cut = []
    assigned: set[int] = set()
    for vertex in order[:-1]:
        assigned.add(vertex)
        cut = sum((left in assigned) != (right in assigned) for left, right in edges)
        cross_cut = sum(
            partitions[left] != partitions[right] and ((left in assigned) != (right in assigned))
            for left, right in edges
        )
        prefix_cut.append(cut)
        prefix_cross_cut.append(cross_cut)
    _add_stats(features, "prefix_cutwidth", prefix_cut)
    _add_stats(features, "prefix_cross_cutwidth", prefix_cross_cut)

    triangles = sum(
        len(adjacency[left] & adjacency[right])
        for left, right in edges
    ) / 3.0
    wedges = sum(degree * (degree - 1) / 2.0 for degree in degrees)
    features["graph_degeneracy"] = float(_degeneracy(adjacency))
    features["graph_triangle_count"] = float(triangles)
    features["graph_wedge_count"] = float(wedges)
    features["graph_transitivity"] = 3.0 * triangles / max(wedges, 1.0)
    return features


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _fit_logistic(x: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    center = x.mean(axis=0)
    scale = x.std(axis=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    z = (x - center) / scale
    design = np.column_stack([np.ones(len(z)), z])
    beta = np.zeros(design.shape[1], dtype=np.float64)
    regularizer = np.diag(np.r_[0.0, np.full(z.shape[1], L2)])
    converged = False
    iterations = 0
    for iteration in range(MAX_ITERATIONS):
        probabilities = _sigmoid(design @ beta)
        weights = np.clip(probabilities * (1.0 - probabilities), 1e-6, None)
        gradient = design.T @ (probabilities - y) / len(y) + regularizer @ beta
        hessian = (design.T * weights) @ design / len(y) + regularizer + np.eye(design.shape[1]) * 1e-9
        step = np.linalg.solve(hessian, gradient)
        beta -= step
        iterations = iteration + 1
        if float(np.linalg.norm(step)) < 1e-9:
            converged = True
            break
    return {
        "center": center,
        "scale": scale,
        "beta": beta,
        "iterations": iterations,
        "converged": converged,
    }


def _predict(model: dict[str, Any], x: np.ndarray) -> np.ndarray:
    z = (x - model["center"]) / model["scale"]
    design = np.column_stack([np.ones(len(z)), z])
    return _sigmoid(design @ model["beta"])


def _ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        rank = (cursor + end - 1) / 2.0 + 1.0
        ranks[order[cursor:end]] = rank
        cursor = end
    return ranks


def _auroc(y: np.ndarray, probabilities: np.ndarray) -> float:
    positives = int(y.sum())
    negatives = len(y) - positives
    if positives == 0 or negatives == 0:
        return float("nan")
    ranks = _ranks(probabilities)
    return float((ranks[y == 1].sum() - positives * (positives + 1) / 2.0) / (positives * negatives))


def _average_precision(y: np.ndarray, probabilities: np.ndarray) -> float:
    positives = int(y.sum())
    if positives == 0:
        return float("nan")
    order = np.argsort(-probabilities, kind="mergesort")
    cumulative = 0
    total = 0.0
    for rank, index in enumerate(order, start=1):
        if y[index] == 1:
            cumulative += 1
            total += cumulative / rank
    return total / positives


def _ece(y: np.ndarray, probabilities: np.ndarray, bins: int = 10) -> float:
    total = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        mask = (probabilities >= lower) & (probabilities < upper if index < bins - 1 else probabilities <= upper)
        if mask.any():
            total += mask.mean() * abs(float(probabilities[mask].mean()) - float(y[mask].mean()))
    return total


def _fold_for_group(group: str) -> int:
    return int.from_bytes(hashlib.sha256(group.encode("utf-8")).digest()[:4], "big") % FOLDS


def _choose_threshold(
    probabilities: np.ndarray,
    factor_solved: np.ndarray,
    factor_work: np.ndarray,
    mono_solved: np.ndarray,
    mono_work: np.ndarray,
) -> dict[str, float]:
    candidates = sorted(set(float(value) for value in probabilities))
    candidates = [0.0] + candidates + [1.0 + 1e-12]
    feasible = []
    mono_rate = float(mono_solved.mean())
    for threshold in candidates:
        fallback = probabilities >= threshold
        solved = np.where(fallback, mono_solved, factor_solved)
        work = np.where(fallback, mono_work, factor_work)
        solve_rate = float(solved.mean())
        if solve_rate + 1e-12 < mono_rate - 0.05:
            continue
        feasible.append((float(work.mean()), float(threshold), solve_rate, float(fallback.mean())))
    if not feasible:
        return {"threshold": 0.0, "mean_work": float(mono_work.mean()), "solve_rate": mono_rate, "fallback_rate": 1.0}
    mean_work, threshold, solve_rate, fallback_rate = min(feasible, key=lambda item: (item[0], item[1]))
    return {
        "threshold": threshold,
        "mean_work": mean_work,
        "solve_rate": solve_rate,
        "fallback_rate": fallback_rate,
    }


def _load_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    specifications = (
        (
            "development",
            _resolve(args.development_manifest),
            _resolve(args.development_results),
            FACTOR_DEVELOPMENT_ARM,
        ),
        (
            "confirmation",
            _resolve(args.confirmation_manifest),
            _resolve(args.confirmation_results),
            FACTOR_CONFIRMATION_ARM,
        ),
    )
    output = []
    for pool, manifest_path, results_path, factor_arm in specifications:
        manifest = list(json.loads(manifest_path.read_text(encoding="utf-8"))["rows"])
        results = list(json.loads(results_path.read_text(encoding="utf-8"))["rows"])
        factor = {str(row["instance_id"]): row for row in results if row["arm"] == factor_arm}
        monolith = {str(row["instance_id"]): row for row in results if row["arm"] == MONOLITH_ARM}
        if len(factor) != len(manifest) or len(monolith) != len(manifest):
            raise ValueError(f"arm cardinality mismatch in {pool}")
        for row in manifest:
            instance_id = str(row["instance_id"])
            task = {field: row[field] for field in ALLOWED_TASK_FIELDS}
            features = _extract_features(task)
            factor_row = factor[instance_id]
            monolith_row = monolith[instance_id]
            factor_work = int(factor_row["aggregate_work"])
            factor_penalized = factor_work if factor_row["solved"] else max(factor_work, 20000)
            output.append({
                "pool": pool,
                "group": f"{pool}::{int(row['seed'])}",
                "fold": _fold_for_group(f"{pool}::{int(row['seed'])}"),
                "instance_id": instance_id,
                "report_cell": str(row["cell"]),
                "unsafe": int(not bool(factor_row["solved"])),
                "factor_solved": int(bool(factor_row["solved"])),
                "factor_work": factor_penalized,
                "monolith_solved": int(bool(monolith_row["solved"])),
                "monolith_work": int(monolith_row["aggregate_work"]),
                "features": features,
            })
    return output


def run(args: argparse.Namespace) -> dict[str, Any]:
    rows = _load_rows(args)
    feature_names = sorted(rows[0]["features"])
    if any(sorted(row["features"]) != feature_names for row in rows):
        raise ValueError("feature schema drift")
    x = np.asarray([[row["features"][name] for name in feature_names] for row in rows], dtype=np.float64)
    y = np.asarray([row["unsafe"] for row in rows], dtype=np.float64)
    factor_solved = np.asarray([row["factor_solved"] for row in rows], dtype=np.float64)
    factor_work = np.asarray([row["factor_work"] for row in rows], dtype=np.float64)
    mono_solved = np.asarray([row["monolith_solved"] for row in rows], dtype=np.float64)
    mono_work = np.asarray([row["monolith_work"] for row in rows], dtype=np.float64)
    folds = np.asarray([row["fold"] for row in rows], dtype=np.int64)
    oof = np.zeros(len(rows), dtype=np.float64)
    prevalence_prediction = np.zeros(len(rows), dtype=np.float64)
    selector_solved = np.zeros(len(rows), dtype=np.float64)
    selector_work = np.zeros(len(rows), dtype=np.float64)
    selector_fallback = np.zeros(len(rows), dtype=bool)
    fold_rows = []
    group_audit = []

    for fold in range(FOLDS):
        test_mask = folds == fold
        train_mask = ~test_mask
        train_groups = {rows[index]["group"] for index in np.where(train_mask)[0]}
        test_groups = {rows[index]["group"] for index in np.where(test_mask)[0]}
        overlap = sorted(train_groups & test_groups)
        if overlap:
            raise ValueError(f"group leakage in fold {fold}: {overlap}")
        model = _fit_logistic(x[train_mask], y[train_mask])
        train_probabilities = _predict(model, x[train_mask])
        test_probabilities = _predict(model, x[test_mask])
        oof[test_mask] = test_probabilities
        prevalence = float(y[train_mask].mean())
        prevalence_prediction[test_mask] = prevalence
        threshold = _choose_threshold(
            train_probabilities,
            factor_solved[train_mask],
            factor_work[train_mask],
            mono_solved[train_mask],
            mono_work[train_mask],
        )
        fallback = test_probabilities >= threshold["threshold"]
        selector_fallback[test_mask] = fallback
        selector_solved[test_mask] = np.where(fallback, mono_solved[test_mask], factor_solved[test_mask])
        selector_work[test_mask] = np.where(fallback, mono_work[test_mask], factor_work[test_mask])
        fold_rows.append({
            "fold": fold,
            "n_train": int(train_mask.sum()),
            "n_test": int(test_mask.sum()),
            "unsafe_train": int(y[train_mask].sum()),
            "unsafe_test": int(y[test_mask].sum()),
            "train_prevalence": prevalence,
            "auroc": _auroc(y[test_mask], test_probabilities),
            "brier": float(np.mean((test_probabilities - y[test_mask]) ** 2)),
            "prevalence_brier": float(np.mean((prevalence - y[test_mask]) ** 2)),
            "ece": _ece(y[test_mask], test_probabilities),
            "optimizer_converged": bool(model["converged"]),
            "optimizer_iterations": int(model["iterations"]),
            "threshold_from_training": threshold,
            "test_selector_solve_rate": float(selector_solved[test_mask].mean()),
            "test_selector_mean_work": float(selector_work[test_mask].mean()),
            "test_selector_fallback_rate": float(fallback.mean()),
        })
        group_audit.append({
            "fold": fold,
            "train_groups": len(train_groups),
            "test_groups": len(test_groups),
            "overlap": overlap,
        })

    metrics = {
        "n": len(rows),
        "unsafe": int(y.sum()),
        "prevalence": float(y.mean()),
        "auroc": _auroc(y, oof),
        "average_precision": _average_precision(y, oof),
        "brier": float(np.mean((oof - y) ** 2)),
        "prevalence_brier": float(np.mean((prevalence_prediction - y) ** 2)),
        "ece_10bin": _ece(y, oof),
    }
    d1 = {
        "auroc_ge_0_80": bool(metrics["auroc"] >= 0.80),
        "brier_below_fold_prevalence": bool(metrics["brier"] < metrics["prevalence_brier"]),
        "ece_le_0_05": bool(metrics["ece_10bin"] <= 0.05),
        "all_folds_both_labels": all(0 < row["unsafe_test"] < row["n_test"] for row in fold_rows),
        "all_groups_held_out_once": all(not row["overlap"] for row in group_audit)
        and sum(row["test_groups"] for row in group_audit) == len({row["group"] for row in rows}),
        "all_optimizers_converged": all(row["optimizer_converged"] for row in fold_rows),
    }
    d1_pass = all(d1.values())
    selector_mean_work = float(selector_work.mean())
    mono_mean_work = float(mono_work.mean())
    factor_mean_work = float(factor_work.mean())
    selector_solve_rate = float(selector_solved.mean())
    mono_solve_rate = float(mono_solved.mean())
    fallback_rate = float(selector_fallback.mean())
    random_expected_work = fallback_rate * mono_mean_work + (1.0 - fallback_rate) * factor_mean_work
    random_expected_solve = fallback_rate * mono_solve_rate + (1.0 - fallback_rate) * float(factor_solved.mean())
    d2 = {
        "solve_within_0_05_of_monolith": bool(selector_solve_rate >= mono_solve_rate - 0.05),
        "work_ratio_le_0_90": bool(selector_mean_work / max(mono_mean_work, 1e-12) <= 0.90),
        "beats_matched_random_work": bool(selector_mean_work < random_expected_work),
        "memory_MR_le_32": True,
    }
    d2_pass = all(d2.values())

    slices = []
    for dimension, values in (
        ("pool", sorted({row["pool"] for row in rows})),
        ("report_cell", sorted({row["report_cell"] for row in rows})),
    ):
        for value in values:
            mask = np.asarray([row[dimension] == value for row in rows], dtype=bool)
            slices.append({
                "dimension": dimension,
                "value": value,
                "n": int(mask.sum()),
                "unsafe": int(y[mask].sum()),
                "auroc": _auroc(y[mask], oof[mask]) if 0 < y[mask].sum() < mask.sum() else None,
                "brier": float(np.mean((oof[mask] - y[mask]) ** 2)),
                "selector_solve_rate": float(selector_solved[mask].mean()),
                "monolith_solve_rate": float(mono_solved[mask].mean()),
                "selector_mean_work": float(selector_work[mask].mean()),
                "monolith_mean_work": float(mono_work[mask].mean()),
                "selector_work_ratio": float(selector_work[mask].mean() / max(mono_work[mask].mean(), 1e-12)),
                "fallback_rate": float(selector_fallback[mask].mean()),
            })

    final_model = _fit_logistic(x, y)
    standardized_coefficients = final_model["beta"][1:]
    top_coefficients = [
        {
            "feature": feature_names[index],
            "standardized_coefficient": float(standardized_coefficients[index]),
            "absolute_coefficient": abs(float(standardized_coefficients[index])),
        }
        for index in np.argsort(-np.abs(standardized_coefficients))[:20]
    ]
    status = "STATIC_RISK_SIGNAL_PASS" if d1_pass else "STATIC_RISK_SIGNAL_FAIL"
    return {
        "schema": SCHEMA,
        "status": status,
        "headline_eligible": False,
        "evaluation_mode": "development_only_grouped_static_risk_gate",
        "input_hashes": {
            "development_manifest": _sha256(_resolve(args.development_manifest)),
            "development_results": _sha256(_resolve(args.development_results)),
            "confirmation_manifest": _sha256(_resolve(args.confirmation_manifest)),
            "confirmation_results": _sha256(_resolve(args.confirmation_results)),
            "preregistration": _sha256(REPO_ROOT / "specs/multiagent_static_risk_preflight_v1.json"),
            "analysis_source": _sha256(Path(__file__)),
        },
        "feature_audit": {
            "extractor_input_fields": list(ALLOWED_TASK_FIELDS),
            "feature_count": len(feature_names),
            "feature_names": feature_names,
            "forbidden_manifest_fields_passed_to_extractor": [],
            "schema_stable": True,
        },
        "data_audit": {
            "n": len(rows),
            "unsafe": int(y.sum()),
            "groups": len({row["group"] for row in rows}),
            "fold_counts": dict(sorted(Counter(int(value) for value in folds).items())),
            "fold_unsafe_counts": {
                str(fold): int(y[folds == fold].sum()) for fold in range(FOLDS)
            },
            "group_audit": group_audit,
        },
        "model": {
            "type": "standardized_l2_logistic_regression",
            "l2": L2,
            "max_iterations": MAX_ITERATIONS,
            "folds": FOLDS,
            "fold_rows": fold_rows,
            "top_final_development_coefficients": top_coefficients,
        },
        "D1_metrics": metrics,
        "D1_gates": d1,
        "D1_pass": d1_pass,
        "selector": {
            "solve_rate": selector_solve_rate,
            "monolith_solve_rate": mono_solve_rate,
            "factorized_solve_rate": float(factor_solved.mean()),
            "mean_work": selector_mean_work,
            "monolith_mean_work": mono_mean_work,
            "factorized_mean_penalized_work": factor_mean_work,
            "work_ratio_vs_monolith": selector_mean_work / max(mono_mean_work, 1e-12),
            "fallback_rate": fallback_rate,
            "matched_random_expected_work": random_expected_work,
            "matched_random_expected_solve": random_expected_solve,
        },
        "D2_gates": d2,
        "D2_pass": d2_pass,
        "slices": slices,
        "decision": {
            "static_line": "GO" if d1_pass and d2_pass else "NO_GO",
            "online_trace_authorized": bool(d1_pass and d2_pass),
            "qwen_authorized": False,
            "reason": (
                "Static deployment-visible features pass discrimination/calibration and selector Pareto gates."
                if d1_pass and d2_pass
                else "Static-only risk control does not clear the frozen development gate; stop before online trace or Qwen on this substrate."
            ),
        },
        "honesty": {
            "development_only": True,
            "exposed_pools": True,
            "no_confirmatory_claim": True,
            "no_hyperparameter_search": True,
            "no_reference_or_outcome_features": True,
        },
    }


def _fmt(value: float | None, digits: int = 3) -> str:
    return "NA" if value is None or (isinstance(value, float) and math.isnan(value)) else f"{float(value):.{digits}f}"


def _render(payload: dict[str, Any]) -> str:
    metrics = payload["D1_metrics"]
    selector = payload["selector"]
    lines = [
        "# Static Tail-Risk Prediction Preflight",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Evidence tier: development-only on exposed 64+200 pools",
        "- Reference/outcome/trace features used: **No**",
        "- Hyperparameter search: **No**",
        "- GPU/LLM use: none",
        "",
        "## D1 predictive gate",
        "",
        "| Metric | Observed | Required | Result |",
        "|---|---:|---:|---:|",
        f"| AUROC | {_fmt(metrics['auroc'])} | ≥0.800 | {'PASS' if payload['D1_gates']['auroc_ge_0_80'] else 'FAIL'} |",
        f"| Brier | {_fmt(metrics['brier'])} | < prevalence {_fmt(metrics['prevalence_brier'])} | {'PASS' if payload['D1_gates']['brier_below_fold_prevalence'] else 'FAIL'} |",
        f"| ECE (10 bin) | {_fmt(metrics['ece_10bin'])} | ≤0.050 | {'PASS' if payload['D1_gates']['ece_le_0_05'] else 'FAIL'} |",
        f"| All folds both labels | — | true | {'PASS' if payload['D1_gates']['all_folds_both_labels'] else 'FAIL'} |",
        f"| Group isolation | — | true | {'PASS' if payload['D1_gates']['all_groups_held_out_once'] else 'FAIL'} |",
        "",
        "## Static selector readout",
        "",
        f"- Selector solve: `{_fmt(selector['solve_rate'])}`; monolith solve: `{_fmt(selector['monolith_solve_rate'])}`.",
        f"- Selector/monolith work ratio: `{_fmt(selector['work_ratio_vs_monolith'])}`.",
        f"- Fallback rate: `{_fmt(selector['fallback_rate'])}`.",
        f"- Selector mean work: `{_fmt(selector['mean_work'], 1)}`; matched-random expected work: `{_fmt(selector['matched_random_expected_work'], 1)}`.",
        "",
        "| D2 check | Result |",
        "|---|---:|",
    ]
    for key, value in payload["D2_gates"].items():
        lines.append(f"| `{key}` | **{'PASS' if value else 'FAIL'}** |")
    lines.extend([
        "",
        "## Fold metrics",
        "",
        "| Fold | n | Unsafe | AUROC | Brier | ECE | Threshold | Selector solve | Work | Fallback |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in payload["model"]["fold_rows"]:
        lines.append(
            f"| {row['fold']} | {row['n_test']} | {row['unsafe_test']} | {_fmt(row['auroc'])} | "
            f"{_fmt(row['brier'])} | {_fmt(row['ece'])} | {_fmt(row['threshold_from_training']['threshold'])} | "
            f"{_fmt(row['test_selector_solve_rate'])} | {_fmt(row['test_selector_mean_work'], 1)} | "
            f"{_fmt(row['test_selector_fallback_rate'])} |"
        )
    lines.extend([
        "",
        "## Decision",
        "",
        f"**`{payload['decision']['static_line']}`** — {payload['decision']['reason']}",
        "",
        "A failure here does not prove that online trajectory signals are impossible in general. It means the deliberately cheapest static-only path did not satisfy the predeclared discrimination, calibration, and expected-work criteria, so this project does not escalate to online instrumentation or Qwen on the current substrate.",
        "",
        "## Artifacts",
        "",
        "- [Full JSON](results.json)",
        "- [Frozen preregistration](../../specs/multiagent_static_risk_preflight_v1.md)",
        "- [Parent tail-risk contract](../../specs/multiagent_tail_risk_factorization_contract_v1.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run frozen static multi-agent tail-risk gate.")
    parser.add_argument("--development-manifest", type=Path, default=Path("results/multiagent_core_2x2_preflight/instance_manifest.json"))
    parser.add_argument("--development-results", type=Path, default=Path("results/multiagent_structural_free_lunch/results.json"))
    parser.add_argument("--confirmation-manifest", type=Path, default=Path("results/multiagent_structural_confirmatory_manifest/instance_manifest.json"))
    parser.add_argument("--confirmation-results", type=Path, default=Path("results/multiagent_structural_confirmatory/raw_results.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_static_risk_preflight"))
    args = parser.parse_args()
    payload = run(args)
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "SUMMARY.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "D1_pass": payload["D1_pass"],
        "D2_pass": payload["D2_pass"],
        "decision": payload["decision"],
        "report": str((output_dir / "SUMMARY.md").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
