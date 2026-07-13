"""E2: live-width random-read capacity for one bounded register."""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

import torch

from experiments.capacity.common import (
    RAW_ROOT,
    default_width_grid_from_d_star,
    env_payload,
    experiment_payload,
    instantiate_operator,
    parse_int_csv,
    predicted_d_star,
    resolve_device,
    write_json,
)
from experiments.capacity.encode import BranchRegister, branch_scores, encode_branches, encode_prepared_values, prepare_values, read_branch
from tasks.graph_coloring.generator import generate_graph_coloring


LiveWidthRegister = BranchRegister


def _fit_dim(states: torch.Tensor, D: int) -> torch.Tensor:
    states = states.float()
    if states.shape[-1] == D:
        return states
    if states.shape[-1] > D:
        return states[..., :D]
    pad = torch.zeros(*states.shape[:-1], D - states.shape[-1], device=states.device, dtype=states.dtype)
    return torch.cat([states, pad], dim=-1)


def encode_live_width(operator, branch_states, register) -> "Tensor":
    """Bundle W branch hidden states into one random-access register."""
    encoded = encode_branches(
        branch_states,
        int(register.D),
        int(register.seed),
        encoder=getattr(register, "encoder", "bind"),
        device=getattr(register, "device", "cpu"),
    )
    register.h = encoded.h
    register.value_codebook = encoded.value_codebook
    register.key_codebook = encoded.key_codebook
    return register.h


def _branch_partials(count: int, K: int, n_variables: int) -> list[dict[int, int]]:
    """Generate bounded singleton branch states without out-of-range variables."""
    n_variables = max(1, int(n_variables))
    return [
        {
            int(index % n_variables): int((index // n_variables) % max(1, K)) + 1,
        }
        for index in range(int(count))
    ]


@torch.no_grad()
def _operator_hiddens(operator: Any, task_type: str, givens: dict[str, Any], partials: list[dict[int, int]], batch_size: int = 1) -> torch.Tensor:
    model = getattr(operator, "model", None)
    tokenizer = getattr(operator, "tokenizer", None)
    renderer = getattr(operator, "renderer", None)
    if model is not None and tokenizer is not None and renderer is not None:
        hidden_rows = []
        for start in range(0, len(partials), batch_size):
            if start % 16 == 0:
                print(json.dumps({"event": "operator_hidden_batch", "start": start, "total": len(partials), "batch_size": batch_size}), flush=True)
            batch_partials = partials[start:start + batch_size]
            prompts = [renderer.render(task_type, givens, partial) for partial in batch_partials]
            inputs = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True).to(model.device)
            backbone = getattr(model, "model", model)
            outputs = backbone(**inputs, use_cache=False, return_dict=True)
            hidden = outputs.last_hidden_state
            last_indices = inputs["attention_mask"].sum(dim=1) - 1
            batch_indices = torch.arange(hidden.shape[0], device=hidden.device)
            hidden_rows.append(hidden[batch_indices, last_indices, :].detach().float().cpu())
        return torch.cat(hidden_rows, dim=0)
    rows = [operator.forward_step(task_type, givens, partial).hidden_state.detach().float().cpu().view(-1) for partial in partials]
    return torch.stack(rows)


def _graph_givens(K: int, seed: int, min_variables: int = 1) -> dict[str, Any]:
    n = max(8, min(128, max(K * 2, int(min_variables))))
    edge_prob = min(0.35, 3.0 / max(n, 1))
    task = generate_graph_coloring(n=n, k=K, edge_prob=edge_prob, n_instances=1, seed=seed)
    if task:
        instance = task[0]
        return {"n": instance.n, "k": instance.k, "edges": instance.edges}
    return {"n": n, "k": K, "edges": []}


def _sample_branch_states(operator: Any, D: int, K: int, count: int, seed: int, batch_size: int = 1) -> torch.Tensor:
    givens = _graph_givens(K, seed, min_variables=max(1, min(int(count), 128)))
    partials = _branch_partials(count, K, int(givens["n"]))
    states = _operator_hiddens(operator, "graph_coloring", givens, partials, batch_size=batch_size)
    return _fit_dim(states, D)


def _geometry_values(geometry_result: str | None, D: int, K: int) -> tuple[float | None, float]:
    if not geometry_result:
        return None, predicted_d_star(int(D), int(K))
    payload = json.loads(Path(geometry_result).read_text(encoding="utf-8"))
    geometry = payload.get("geometry", payload)
    d_eff = float(geometry.get("D_eff", 0.0))
    d_star_eff = float(geometry.get("d_star_eff", predicted_d_star(int(D), int(K))))
    return d_eff, d_star_eff


def _run_width_rows(
    operator,
    D,
    K,
    W_grid,
    instances=50,
    seed=0,
    batch_size: int = 1,
    encoder: str = "bind",
    D_eff: float | None = None,
    d_star_eff: float | None = None,
) -> list[dict]:
    """Return fixed-grid v2 rows for compatibility and raw controls."""
    W_values = [int(W) for W in W_grid]
    max_width = max(W_values) if W_values else 0
    branch_states = _sample_branch_states(operator, int(D), int(K), max_width, int(seed), batch_size=batch_size) if max_width else torch.empty(0, int(D))
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for W in W_values:
        register = encode_branches(branch_states[:W], int(D), int(seed) + W, encoder=encoder, device="cpu")
        correct = 0
        raw = []
        for trial in range(int(instances)):
            index = rng.randrange(W)
            prediction = read_branch(register, index)
            is_correct = prediction == index
            correct += int(is_correct)
            raw.append({"trial": trial, "W": W, "query_index": index, "prediction": prediction, "correct": is_correct})
        rows.append({
            "W": W,
            "D": int(D),
            "K": int(K),
            "encoder": encoder,
            "D_eff": D_eff,
            "d_star": predicted_d_star(int(D), int(K)),
            "d_star_eff": d_star_eff,
            "read_accuracy": correct / max(int(instances), 1),
            "n_reads": int(instances),
            "operator_hidden_dim": int(branch_states.shape[-1]) if branch_states.numel() else int(D),
            "raw": raw,
        })
        print(json.dumps({"event": "width_wall_condition_done", "D": int(D), "K": int(K), "W": W, "encoder": encoder, "read_accuracy": rows[-1]["read_accuracy"]}), flush=True)
    return rows


def load_state_shards(shard_dir: str) -> tuple[torch.Tensor, dict[str, Any]]:
    """Load and interleave complete E0 shards back into original sample order."""
    paths = sorted(Path(shard_dir).glob("states_shard*_of_*.pt"))
    if not paths:
        raise FileNotFoundError(f"no E0 state shards found under {shard_dir}")
    payloads = [torch.load(path, map_location="cpu", weights_only=False) for path in paths]
    expected = int(payloads[0]["num_shards"])
    by_index = {int(payload["shard_index"]): payload for payload in payloads}
    if len(paths) != expected or sorted(by_index) != list(range(expected)):
        raise RuntimeError(f"incomplete E0 state shards: expected {expected}, found {sorted(by_index)}")
    first = payloads[0]
    metadata_key = (int(first["K"]), int(first["seed"]), int(first["n_total"]), str(first["task_type"]), first["givens"])
    for payload in payloads[1:]:
        candidate = (int(payload["K"]), int(payload["seed"]), int(payload["n_total"]), str(payload["task_type"]), payload["givens"])
        if candidate != metadata_key:
            raise RuntimeError("E0 state shard metadata mismatch")
    shards = [by_index[index]["states"].detach().float().cpu() for index in range(expected)]
    restored_rows: list[torch.Tensor] = []
    for offset in range(max(int(shard.shape[0]) for shard in shards)):
        for shard in shards:
            if offset < int(shard.shape[0]):
                restored_rows.append(shard[offset])
    states = torch.stack(restored_rows)[: int(first["n_total"])]
    if int(states.shape[0]) != int(first["n_total"]):
        raise RuntimeError(f"restored state count mismatch: expected {first['n_total']}, found {states.shape[0]}")
    givens = dict(first["givens"])
    unique_bound = int(givens.get("n", states.shape[0])) * int(givens.get("k", first["K"]))
    return states, {
        "shard_dir": shard_dir,
        "shard_paths": [str(path) for path in paths],
        "n": int(states.shape[0]),
        "D": int(states.shape[1]),
        "K": int(first["K"]),
        "seed": int(first["seed"]),
        "unique_branch_state_bound": min(int(states.shape[0]), unique_bound),
    }


def nominal_bind_grid(D: int, K: int, available: int) -> list[int]:
    """Return the preregistered v3 bind grid sized from nominal D, never D_eff."""
    upper = min(int(D), int(available), max(4, int(2.0 * predicted_d_star(int(D), int(K)))))
    prescribed = [4, 8, 16, 32, 64, 128, 256, 512, 768, 1024]
    grid = [width for width in prescribed if width <= upper]
    if upper >= 4 and (not grid or grid[-1] < upper):
        grid.append(upper)
    return sorted(set(grid))


def _pairwise_cosine_stats(codebook: torch.Tensor, seed: int, max_pairs: int = 20000, absolute: bool = False) -> dict[str, float | None]:
    count = int(codebook.shape[0])
    if count <= 1:
        return {"mean": None, "p95": None, "max": None}
    normed = codebook.float() / codebook.float().norm(dim=-1, keepdim=True).clamp_min(1e-12)
    generator = torch.Generator(device="cpu").manual_seed(int(seed))
    pair_count = min(int(max_pairs), count * (count - 1))
    left = torch.randint(0, count, (pair_count,), generator=generator)
    right = torch.randint(0, count - 1, (pair_count,), generator=generator)
    right = right + (right >= left).long()
    cosine = (normed[left] * normed[right]).sum(dim=-1)
    if absolute:
        cosine = cosine.abs()
    return {
        "mean": float(cosine.mean().item()),
        "p95": float(torch.quantile(cosine, 0.95).item()),
        "max": float(cosine.max().item()),
    }


def _diagnose_register_failures(register: BranchRegister, query_ids: torch.Tensor, scores: torch.Tensor, predictions: torch.Tensor) -> dict[str, Any]:
    """Split sampled read failures into key- versus value-dominant diagnostics.

    Attribution is diagnostic rather than causal: for each wrong cleanup, compare
    the predicted pair's absolute key cosine with its absolute value cosine.
    """
    if register.value_codebook is None or register.key_codebook is None:
        raise ValueError("bind diagnostics require value and key codebooks")
    errors = predictions.ne(query_ids)
    error_count = int(errors.sum().item())
    key_stage = 0
    value_stage = 0
    if error_count:
        error_queries = query_ids[errors]
        error_predictions = predictions[errors]
        values = register.value_codebook
        keys = register.key_codebook
        value_cosine = (values[error_queries] * values[error_predictions]).sum(dim=-1).abs()
        key_cosine = (keys[error_queries] * keys[error_predictions]).sum(dim=-1).abs() / float(register.D)
        key_stage = int((key_cosine >= value_cosine).sum().item())
        value_stage = error_count - key_stage
    row_indices = torch.arange(query_ids.numel())
    true_scores = scores[row_indices, query_ids]
    wrong_scores = scores.clone()
    wrong_scores[row_indices, query_ids] = float("-inf")
    best_wrong = wrong_scores.max(dim=-1).values
    margins = true_scores - best_wrong
    return {
        "nearest_value_confusion_rate": error_count / max(int(query_ids.numel()), 1),
        "key_stage_error_rate": key_stage / max(int(query_ids.numel()), 1),
        "value_stage_error_rate": value_stage / max(int(query_ids.numel()), 1),
        "key_value_attribution": "larger_absolute_pairwise_cosine",
        "cleanup_margin_mean": float(margins.mean().item()),
        "cleanup_margin_min": float(margins.min().item()),
        "value_pairwise_cosine": _pairwise_cosine_stats(register.value_codebook, 1103 + int(register.seed)),
        "key_pairwise_abs_cosine": _pairwise_cosine_stats(register.key_codebook, 2017 + int(register.seed), absolute=True),
    }


def _evaluate_prepared_width(values: torch.Tensor, D: int, K: int, W: int, reads: int, seed: int, D_eff: float | None, d_star_eff: float | None) -> dict[str, Any]:
    register = encode_prepared_values(values, int(D), int(seed), device="cpu")
    generator = torch.Generator(device="cpu").manual_seed(65537 + int(seed) + 104729 * int(W))
    query_ids = torch.randint(0, int(W), (int(reads),), generator=generator)
    scores = branch_scores(register, query_ids)
    predictions = scores.argmax(dim=-1)
    correct = predictions.eq(query_ids)
    diagnostics = _diagnose_register_failures(register, query_ids, scores, predictions)
    raw = [
        {
            "trial": int(trial),
            "W": int(W),
            "query_index": int(query_ids[trial].item()),
            "prediction": int(predictions[trial].item()),
            "correct": bool(correct[trial].item()),
        }
        for trial in range(int(reads))
    ]
    row = {
        "W": int(W),
        "D": int(D),
        "K": int(K),
        "encoder": "bind",
        "D_eff": D_eff,
        "d_star": predicted_d_star(int(D), int(K)),
        "d_star_eff": d_star_eff,
        "read_accuracy": int(correct.sum().item()) / max(int(reads), 1),
        "n_reads": int(reads),
        "operator_hidden_dim": int(D),
        **diagnostics,
        "raw": raw,
    }
    print(json.dumps({"event": "bind_capacity_condition_done", "W": int(W), "read_accuracy": row["read_accuracy"], "confusion_rate": row["nearest_value_confusion_rate"]}), flush=True)
    return row


def _evaluate_bind_width(branch_states: torch.Tensor, D: int, K: int, W: int, reads: int, seed: int, D_eff: float | None, d_star_eff: float | None) -> dict[str, Any]:
    if int(W) > int(branch_states.shape[0]):
        raise ValueError(f"W={W} exceeds available real hidden states {branch_states.shape[0]}")
    values = prepare_values(branch_states[: int(W)], int(D), "bind")
    return _evaluate_prepared_width(values, D, K, W, reads, seed, D_eff, d_star_eff)


def _classify_regime(W_star: int, d_star_nominal: float, d_star_eff: float) -> tuple[str, dict[str, float]]:
    candidate = max(float(W_star), 1.0)
    nominal = max(float(d_star_nominal), 1e-12)
    effective = max(float(d_star_eff), 1e-12)
    nominal_distance = abs(torch.log(torch.tensor(candidate / nominal)).item())
    effective_distance = abs(torch.log(torch.tensor(candidate / effective)).item())
    regime = "D" if nominal_distance <= effective_distance else "D_eff"
    return regime, {
        "W_star_over_d_star_nominal": candidate / nominal,
        "W_star_over_d_star_eff": candidate / effective,
        "log_distance_to_D_scale": nominal_distance,
        "log_distance_to_D_eff_scale": effective_distance,
    }


def run_width_wall(
    operator,
    D,
    K,
    W_grid=None,
    instances=300,
    seed=0,
    batch_size: int = 1,
    encoder: str = "bind",
    D_eff: float | None = None,
    d_star_eff: float | None = None,
    branch_states: torch.Tensor | None = None,
    threshold: float = 0.9,
) -> dict[str, Any]:
    """Sweep nominal-D bind widths, bisect to W*, and classify D versus D_eff."""
    if encoder != "bind":
        raise ValueError("SPEC v3 adaptive capacity is defined for encoder='bind'")
    d_star_nominal = predicted_d_star(int(D), int(K))
    if d_star_eff is None:
        d_star_eff = (float(D_eff) / (2.0 * torch.log(torch.tensor(float(K))).item())) if D_eff is not None else d_star_nominal
    initial_grid = [int(width) for width in (W_grid or nominal_bind_grid(int(D), int(K), int(branch_states.shape[0]) if branch_states is not None else int(D)))]
    if not initial_grid:
        raise ValueError("bind capacity grid is empty")
    if branch_states is None:
        branch_states = _sample_branch_states(operator, int(D), int(K), max(initial_grid), int(seed), batch_size=batch_size)
    branch_states = _fit_dim(branch_states.detach().float().cpu(), int(D))
    cache: dict[int, dict[str, Any]] = {}

    def evaluate(width: int) -> dict[str, Any]:
        width = int(width)
        if width not in cache:
            cache[width] = _evaluate_bind_width(branch_states, int(D), int(K), width, int(instances), int(seed), D_eff, d_star_eff)
        return cache[width]

    for width in initial_grid:
        evaluate(width)
    ordered_initial = sorted(cache)
    first_fail = next((width for width in ordered_initial if float(cache[width]["read_accuracy"]) + 1e-12 < float(threshold)), None)
    if first_fail is None:
        passing = [width for width in ordered_initial if float(cache[width]["read_accuracy"]) + 1e-12 >= float(threshold)]
        W_star = max(passing) if passing else 0
        wall_censored = True
    else:
        passing = [width for width in ordered_initial if width < first_fail and float(cache[width]["read_accuracy"]) + 1e-12 >= float(threshold)]
        W_star = max(passing) if passing else 0
        wall_censored = False
        low = int(W_star)
        high = int(first_fail)
        while low >= 4 and high - low > 1:
            midpoint = (low + high) // 2
            if float(evaluate(midpoint)["read_accuracy"]) + 1e-12 >= float(threshold):
                low = midpoint
            else:
                high = midpoint
        W_star = low
        first_fail = high
    curve = [cache[width] for width in sorted(cache)]
    regime, regime_evidence = _classify_regime(int(W_star), float(d_star_nominal), float(d_star_eff))
    confusion_half_width = next((int(row["W"]) for row in curve if float(row["nearest_value_confusion_rate"]) > 0.5), None)
    first_fail_accuracy = float(cache[first_fail]["read_accuracy"]) if first_fail is not None else None
    return {
        "curve": curve,
        "W_star": int(W_star),
        "W_star_bind": int(W_star),
        "first_fail_W": int(first_fail) if first_fail is not None else None,
        "first_fail_accuracy": first_fail_accuracy,
        "wall_bracket": [int(W_star), int(first_fail)] if first_fail is not None else [int(W_star), None],
        "wall_censored": bool(wall_censored),
        "threshold": float(threshold),
        "regime": regime,
        "regime_evidence": regime_evidence,
        "d_star_nominal": float(d_star_nominal),
        "d_star_eff": float(d_star_eff),
        "initial_grid": initial_grid,
        "max_tested_W": max(cache),
        "nearest_value_confusion_gt_0_5_W": confusion_half_width,
        "G2_prime_pass": bool(first_fail is not None and int(W_star) >= 4),
        "raw": [item for row in curve for item in row.get("raw", [])],
    }


def diagnose_bind_failures(hidden_states, W_grid) -> dict[str, Any]:
    """Diagnose key-stage and value-stage bind failures across requested widths."""
    states = torch.as_tensor(hidden_states).detach().float().cpu()
    if states.ndim != 2:
        raise ValueError("hidden_states must have shape (n_states, D)")
    widths = sorted(set(int(width) for width in W_grid))
    if not widths or widths[0] < 1 or widths[-1] > int(states.shape[0]):
        raise ValueError("W_grid must be non-empty and bounded by available hidden states")
    rows = [
        _evaluate_bind_width(
            states,
            int(states.shape[1]),
            9,
            width,
            300,
            0,
            None,
            None,
        )
        for width in widths
    ]
    confusion_half_width = next((int(row["W"]) for row in rows if float(row["nearest_value_confusion_rate"]) > 0.5), None)
    for row in rows:
        row.pop("raw", None)
    return {
        "rows": rows,
        "nearest_value_confusion_gt_0_5_W": confusion_half_width,
        "value_pairwise_cosine": {str(row["W"]): row["value_pairwise_cosine"] for row in rows},
    }


def _student_t_975(df: int) -> float:
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}
    return table.get(int(df), 2.086 if df <= 20 else 1.96)


def w_star_ci(
    operator,
    D,
    K,
    seeds,
    reads=500,
    *,
    branch_states: torch.Tensor | None = None,
    W_grid=None,
    D_eff: float | None = None,
    d_star_eff: float | None = None,
    threshold: float = 0.9,
    batch_size: int = 1,
) -> dict[str, Any]:
    """Estimate W* across encoder seeds and return a t-based 95% interval."""
    seed_values = [int(seed) for seed in seeds]
    if len(seed_values) < 2:
        raise ValueError("w_star_ci requires at least two seeds; G3 requires at least five")
    if branch_states is None:
        available = int(D)
        initial_grid = [int(width) for width in (W_grid or nominal_bind_grid(int(D), int(K), available))]
        branch_states = _sample_branch_states(operator, int(D), int(K), max(initial_grid), seed_values[0], batch_size=batch_size)
    branch_states = _fit_dim(branch_states.detach().float().cpu(), int(D))
    initial_grid = [int(width) for width in (W_grid or nominal_bind_grid(int(D), int(K), int(branch_states.shape[0])))]
    if not initial_grid:
        raise ValueError("seed-CI grid is empty")
    if d_star_eff is None:
        d_star_eff = (float(D_eff) / (2.0 * math.log(float(K)))) if D_eff is not None else predicted_d_star(int(D), int(K))
    prepared_cache: dict[int, torch.Tensor] = {}

    def prepared(width: int) -> torch.Tensor:
        width = int(width)
        if width not in prepared_cache:
            prepared_cache[width] = prepare_values(branch_states[:width], int(D), "bind")
        return prepared_cache[width]

    per_seed = []
    for seed in seed_values:
        rows: dict[int, dict[str, Any]] = {}

        def evaluate(width: int) -> dict[str, Any]:
            width = int(width)
            if width not in rows:
                rows[width] = _evaluate_prepared_width(prepared(width), int(D), int(K), width, int(reads), seed, D_eff, d_star_eff)
            return rows[width]

        for width in initial_grid:
            evaluate(width)
        first_fail = next((width for width in sorted(rows) if float(rows[width]["read_accuracy"]) + 1e-12 < float(threshold)), None)
        passing = [width for width in sorted(rows) if (first_fail is None or width < first_fail) and float(rows[width]["read_accuracy"]) + 1e-12 >= float(threshold)]
        W_star = max(passing) if passing else 0
        if first_fail is not None:
            low = int(W_star)
            high = int(first_fail)
            while low >= 4 and high - low > 1:
                midpoint = (low + high) // 2
                if float(evaluate(midpoint)["read_accuracy"]) + 1e-12 >= float(threshold):
                    low = midpoint
                else:
                    high = midpoint
            W_star = low
            first_fail = high
        curve = [
            {"W": int(width), "read_accuracy": float(rows[width]["read_accuracy"])}
            for width in sorted(rows)
        ]
        per_seed.append({
            "seed": seed,
            "W_star": int(W_star),
            "first_fail_W": int(first_fail) if first_fail is not None else None,
            "first_fail_accuracy": float(rows[first_fail]["read_accuracy"]) if first_fail is not None else None,
            "curve": curve,
        })
    stars = [float(row["W_star"]) for row in per_seed]
    mean_star = sum(stars) / len(stars)
    variance = sum((value - mean_star) ** 2 for value in stars) / max(len(stars) - 1, 1)
    std = math.sqrt(variance)
    half_width = _student_t_975(len(stars) - 1) * std / math.sqrt(len(stars))
    return {
        "seeds": seed_values,
        "reads_per_width": int(reads),
        "threshold": float(threshold),
        "initial_grid": initial_grid,
        "per_seed": per_seed,
        "W_stars": [int(value) for value in stars],
        "W_star_mean": mean_star,
        "W_star_std": std,
        "ci95": [mean_star - half_width, mean_star + half_width],
        "ci95_half_width": half_width,
        "G3_pass": len(stars) >= 5 and all(row["first_fail_W"] is not None for row in per_seed),
    }


def _linear_fit(xs: list[float], ys: list[float]) -> dict[str, float]:
    if len(xs) < 2 or len(xs) != len(ys):
        raise ValueError("linear fit requires equal-length vectors with at least two points")
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    ss_x = sum((value - mean_x) ** 2 for value in xs)
    if ss_x <= 0.0:
        raise ValueError("linear fit requires nonconstant x")
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / ss_x
    intercept = mean_y - slope * mean_x
    predictions = [intercept + slope * value for value in xs]
    ss_res = sum((actual - predicted) ** 2 for actual, predicted in zip(ys, predictions))
    ss_total = sum((actual - mean_y) ** 2 for actual in ys)
    r2 = 1.0 - ss_res / ss_total if ss_total > 0.0 else 1.0
    return {"slope": slope, "intercept": intercept, "r2": r2}


def w_star_scaling(operator_ckpts, K) -> dict[str, Any]:
    """Fit W*(D) from at least three checkpoint CI payloads or paths."""
    items = operator_ckpts.items() if isinstance(operator_ckpts, dict) else enumerate(operator_ckpts)
    points = []
    for label, source in items:
        if isinstance(source, (str, Path)):
            payload = json.loads(Path(source).read_text(encoding="utf-8"))
            source_path = str(source)
        else:
            payload = dict(source)
            source_path = None
        ci_payload = payload.get("W_star_ci", payload)
        D_value = int(payload.get("D", ci_payload.get("D", 0)))
        if D_value <= 0 or "W_star_mean" not in ci_payload:
            raise ValueError(f"invalid W-star CI payload for {label}")
        points.append({
            "label": str(label),
            "D": D_value,
            "W_star_mean": float(ci_payload["W_star_mean"]),
            "ci95": list(ci_payload.get("ci95", [])),
            "source": source_path,
        })
    points.sort(key=lambda row: row["D"])
    if len(points) < 3:
        raise ValueError("G4 requires at least three model sizes")
    Ds = [float(row["D"]) for row in points]
    stars = [float(row["W_star_mean"]) for row in points]
    linear = _linear_fit(Ds, stars)
    log_fit = _linear_fit([math.log(value) for value in Ds], [math.log(max(value, 1e-12)) for value in stars])
    return {
        "K": int(K),
        "points": points,
        "slope": linear["slope"],
        "intercept": linear["intercept"],
        "r2": linear["r2"],
        "log_log_slope": log_fit["slope"],
        "log_log_intercept": log_fit["intercept"],
        "log_log_r2": log_fit["r2"],
        "G4_pass": len(points) >= 3,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run E2' adaptive bind capacity or explicit legacy controls.")
    parser.add_argument("--D", type=int, default=2560)
    parser.add_argument("--K", type=int, default=9)
    parser.add_argument("--W-grid", default="")
    parser.add_argument("--instances", type=int, default=300)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32")
    parser.add_argument("--no-load-model", action="store_true")
    parser.add_argument("--sweep-D", action="store_true")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--encoder", choices=["bind", "raw"], default="bind")
    parser.add_argument("--geometry-result", default="")
    parser.add_argument("--states-dir", default="")
    parser.add_argument("--threshold", type=float, default=0.9)
    parser.add_argument("--ci-seeds", default="")
    parser.add_argument("--scaling-results", default="")
    parser.add_argument("--legacy-v2-grid", action="store_true")
    parser.add_argument("--allow-missing-geometry", action="store_true")
    parser.add_argument("--out", default="results/capacity/E2_prime_bind_capacity.json")
    args = parser.parse_args()
    if args.scaling_results:
        sources = [part.strip() for part in args.scaling_results.split(",") if part.strip()]
        result = w_star_scaling(sources, args.K)
        payload = {
            "experiment": "W_star_scaling",
            "schema": "bind_capacity_scaling_v4",
            "model_sources": sources,
            "env": env_payload(args.dtype),
            **result,
        }
        write_json(args.out, payload)
        return
    if args.encoder != "bind" and not args.legacy_v2_grid:
        raise SystemExit("raw is a settled negative control; use --legacy-v2-grid for an explicit raw rerun")
    state_source = None
    source_states = None
    if args.states_dir:
        source_states, state_source = load_state_shards(args.states_dir)
        source_states = source_states[: int(state_source["unique_branch_state_bound"])]
        if int(state_source["K"]) != int(args.K):
            raise SystemExit(f"state-shard K={state_source['K']} does not match --K={args.K}")
    operator = None
    if source_states is None:
        device = resolve_device(args.device)
        operator = instantiate_operator(args.model, device, args.dtype, load_model=not args.no_load_model)
    Ds = [args.D]
    if args.sweep_D:
        Ds = sorted({max(16, args.D // 4), max(16, args.D // 2), args.D})
    if args.encoder == "bind" and not args.legacy_v2_grid:
        if len(Ds) != 1:
            raise SystemExit("E2' adaptive bisection currently requires one D per artifact")
        D = Ds[0]
        if args.geometry_result:
            D_eff, d_star_eff = _geometry_values(args.geometry_result, D, args.K)
        elif args.no_load_model or args.allow_missing_geometry:
            D_eff, d_star_eff = None, predicted_d_star(D, args.K)
        else:
            raise SystemExit("E2' requires --geometry-result from E0")
        available = int(source_states.shape[0]) if source_states is not None else int(D)
        W_grid = parse_int_csv(args.W_grid) if args.W_grid else nominal_bind_grid(D, args.K, available)
        if args.ci_seeds:
            ci = w_star_ci(
                operator,
                D,
                args.K,
                parse_int_csv(args.ci_seeds),
                reads=args.instances,
                branch_states=source_states,
                W_grid=W_grid,
                D_eff=D_eff,
                d_star_eff=d_star_eff,
                threshold=args.threshold,
                batch_size=args.batch_size,
            )
            payload = {
                "experiment": "E2_prime_seed_ci",
                "schema": "bind_capacity_seed_ci_v4",
                "model": args.model,
                "D": int(D),
                "K": int(args.K),
                "geometry_result": args.geometry_result or None,
                "states_source": state_source,
                "env": env_payload(args.dtype),
                **ci,
            }
            write_json(args.out, payload)
            return
        result = run_width_wall(
            operator,
            D,
            args.K,
            W_grid,
            args.instances,
            args.seed,
            batch_size=args.batch_size,
            encoder="bind",
            D_eff=D_eff,
            d_star_eff=d_star_eff,
            branch_states=source_states,
            threshold=args.threshold,
        )
        rows = result.pop("curve")
        raw_rows = result.pop("raw")
        for row in rows:
            row.pop("raw", None)
        RAW_ROOT.mkdir(parents=True, exist_ok=True)
        raw_name = f"{Path(args.out).stem}_raw.json"
        write_json(RAW_ROOT / raw_name, {"rows": raw_rows})
        payload = experiment_payload("E2_prime", args.model, D, args.K, args.seed, args.instances, rows, args.dtype)
        payload.update(result)
        payload["schema"] = "bind_capacity_curve_v3"
        payload["encoder"] = "bind"
        payload["geometry_result"] = args.geometry_result or None
        payload["states_source"] = state_source
        write_json(args.out, payload)
        return

    rows: list[dict[str, Any]] = []
    for D in Ds:
        if args.geometry_result:
            D_eff, d_star_eff = _geometry_values(args.geometry_result, D, args.K)
        elif args.no_load_model or args.allow_missing_geometry:
            D_eff, d_star_eff = None, predicted_d_star(D, args.K)
        else:
            raise SystemExit("E2 requires --geometry-result from E0 unless --allow-missing-geometry or --no-load-model is set")
        W_grid = parse_int_csv(args.W_grid) if args.W_grid else default_width_grid_from_d_star(d_star_eff)
        rows.extend(
            _run_width_rows(
                operator,
                D,
                args.K,
                W_grid,
                args.instances,
                args.seed,
                batch_size=args.batch_size,
                encoder=args.encoder,
                D_eff=D_eff,
                d_star_eff=d_star_eff,
            )
        )
    raw_rows = [item for row in rows for item in row.pop("raw", [])]
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    raw_name = f"{Path(args.out).stem}_raw.json"
    write_json(RAW_ROOT / raw_name, {"rows": raw_rows})
    payload = experiment_payload("E2", args.model, args.D, args.K, args.seed, args.instances, rows, args.dtype)
    payload["encoder"] = args.encoder
    payload["geometry_result"] = args.geometry_result or None
    nontrivial_widths = [int(row["W"]) for row in rows if int(row["W"]) >= 4]
    gate_width = min(nontrivial_widths) if nontrivial_widths else None
    payload["G2_gate_width"] = gate_width
    payload["G2_pass"] = gate_width is not None and all(
        float(row["read_accuracy"]) >= 0.9
        for row in rows
        if int(row["W"]) == gate_width
    )
    write_json(args.out, payload)


if __name__ == "__main__":
    main()
