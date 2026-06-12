"""Offline Item063 in-loop divergence decomposition.

No model calls are made here. The analysis consumes the completed vLLM
structured full-slice artifact and decomposes recall/value-misselection by
depth, step index, and reconstructed prompt-context size.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _adjacency, _rel
from experiments.rung1_separator_llm_inloop import LOW_SOLVE_THRESHOLD
from experiments.rung1_separator_p1b_full_table import _operator_by_b
from experiments.rung1_separator_p1b_truncation_pilot import Episode, _initial_domains, _operator_prompt


FULL_SLICE_PATH = REPO_ROOT / "results/rung1_separator_llm_inloop/full_slice_vllm_structured/results.json"
EXPLICIT_STATE_PILOT_PATH = REPO_ROOT / "results/rung1_separator_llm_inloop/explicit_state_pilot/results.json"
EXPLICIT_STATE_FULL_PATH = REPO_ROOT / "results/rung1_separator_llm_inloop/full_slice_vllm_explicit_state/results.json"
GRADED_PATH = REPO_ROOT / "results/rung1_separator_fallibility_rungs/p1b_graded_recompute.json"
FULL_TABLE_V1_PATH = REPO_ROOT / "results/rung1_separator_fallibility_rungs/p1b_full_table_v1.json"
OUT_DIR = REPO_ROOT / "results/rung1_separator_llm_inloop/divergence_analysis"
OUT_PATH = OUT_DIR / "item063_inloop_divergence.json"
PLOT_DIR = OUT_DIR / "plots"
SCHEMA_VERSION = "item063_inloop_divergence_analysis_v0"
STATUS = "ITEM063_INLOOP_DIVERGENCE_UNIFORM_FRAMING_GAP_FULL_EXPLICIT_PARTIAL_RECOVERY_NO_CAPACITY_LAW"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _safe_mean(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return mean(clean) if clean else None


def _safe_div(num: float, den: float) -> float | None:
    return None if den == 0 else num / den


def _ols(rows: list[dict[str, Any]], x_key: str, y_key: str, y_binary: bool = False) -> dict[str, Any]:
    pairs = []
    for row in rows:
        x = row.get(x_key)
        y = row.get(y_key)
        if x is None or y is None:
            continue
        try:
            pairs.append((float(x), float(y)))
        except Exception:
            continue
    if len(pairs) < 2:
        return {"x": x_key, "y": y_key, "n": len(pairs), "slope": None, "intercept": None, "r2": None, "pearson_r": None}
    xs = np.array([item[0] for item in pairs], dtype=float)
    ys = np.array([item[1] for item in pairs], dtype=float)
    x_mean = float(xs.mean())
    y_mean = float(ys.mean())
    denom = float(((xs - x_mean) ** 2).sum())
    slope = 0.0 if denom == 0 else float(((xs - x_mean) * (ys - y_mean)).sum() / denom)
    intercept = y_mean - slope * x_mean
    fitted = intercept + slope * xs
    ss_tot = float(((ys - y_mean) ** 2).sum())
    ss_res = float(((ys - fitted) ** 2).sum())
    r2 = None if ss_tot == 0 else 1.0 - ss_res / ss_tot
    pearson = None if float(xs.std()) == 0 or float(ys.std()) == 0 else float(np.corrcoef(xs, ys)[0, 1])
    return {
        "x": x_key,
        "y": y_key,
        "n": len(pairs),
        "slope": slope,
        "intercept": intercept,
        "r2": r2,
        "pearson_r": pearson,
        "y_binary": y_binary,
        "x_min": float(xs.min()),
        "x_max": float(xs.max()),
        "y_mean": y_mean,
    }


def _bin_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = row.get(key)
        if value is not None:
            grouped[int(value)].append(row)
    out = []
    for value, subset in sorted(grouped.items()):
        out.append({
            key: value,
            "n_steps": len(subset),
            "mean_recall": _safe_mean([row.get("propagation_recall") for row in subset]),
            "misselection_rate": _safe_mean([row.get("value_misselection") for row in subset]),
            "format_failure_rate": _safe_mean([row.get("format_failure") for row in subset]),
            "mean_answer_tokens": _safe_mean([row.get("answer_tokens") for row in subset]),
            "mean_prompt_chars_reconstructed": _safe_mean([row.get("prompt_chars_reconstructed") for row in subset]),
            "source": SOURCE,
            "provenance": "item063_inloop_divergence_binned_v0",
        })
    return out


def _load_manifest_by_id() -> dict[str, dict[str, Any]]:
    data = _read_json(REPO_ROOT / "results/rung1_separator_scaling/results.json")
    return {str(row["instance_id"]): row for row in data.get("instance_manifest", [])}


@dataclass
class ReplayState:
    row: dict[str, Any]
    adjacency: dict[int, set[int]]
    order: list[int]
    assignment_by_order: dict[int, tuple[int, int]]


def _reconstructed_prompt_metrics(full: dict[str, Any]) -> dict[tuple[str, int, int], dict[str, Any]]:
    """Approximate prompt chars/tokens from visible assignments only.

    The runner did not persist raw prompts. The P1b prompt includes static edges
    and visible_assignment, not domains, so replaying chosen assignments and
    cursor movements recovers the principal growing-context component. Backjump
    recovery is approximated by dropping assignments at order_index >= current
    cursor when the cursor retreats.
    """
    manifest = _load_manifest_by_id()
    by_instance: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for step in full["inloop_step_metrics"]:
        by_instance[(str(step["instance_id"]), int(step["register_capacity_D"]))].append(step)

    metrics: dict[tuple[str, int, int], dict[str, Any]] = {}
    for (instance_id, register_d), steps in by_instance.items():
        row = manifest[instance_id]
        state = ReplayState(
            row=row,
            adjacency=_adjacency(int(row["n_vertices"]), tuple(tuple(edge) for edge in row["edges"])),
            order=[int(vertex) for vertex in row["order"]],
            assignment_by_order={},
        )
        last_cursor = 0
        for step in sorted(steps, key=lambda item: int(item["call_index"])):
            cursor = int(step["cursor_before"])
            if cursor <= last_cursor:
                state.assignment_by_order = {idx: pair for idx, pair in state.assignment_by_order.items() if idx < cursor}
            assignment = {vertex: color for _, (vertex, color) in sorted(state.assignment_by_order.items())}
            episode = Episode(
                row=row,
                adjacency=state.adjacency,
                order=state.order,
                domains=_initial_domains(row),
                assignment=assignment,
                cursor=cursor,
                calls=int(step["call_index"]) - 1,
            )
            prompt = _operator_prompt(episode, "v1_1")
            visible_assignment_count = prompt.count(":")  # placeholder overwritten below
            marker = "visible_assignment="
            visible_text = prompt[prompt.rfind(marker) + len(marker):] if marker in prompt else "{}"
            visible_assignment_count = 0 if visible_text.strip() == "{}" else visible_text.count(":")
            metrics[(instance_id, register_d, int(step["call_index"]))] = {
                "prompt_chars_reconstructed": len(prompt),
                "prompt_token_proxy_reconstructed": len(prompt.split()),
                "visible_assignment_count_reconstructed": visible_assignment_count,
                "reconstruction_note": "raw prompts were not persisted; reconstructed from logged cursor/chosen_color and static instance manifest",
            }
            state.assignment_by_order[cursor] = (int(step["vertex"]), int(step["chosen_color"]))
            last_cursor = cursor
    return metrics


def _annotated_steps(full: dict[str, Any]) -> list[dict[str, Any]]:
    prompt_metrics = _reconstructed_prompt_metrics(full)
    annotated = []
    for step in full["inloop_step_metrics"]:
        key = (str(step["instance_id"]), int(step["register_capacity_D"]), int(step["call_index"]))
        row = dict(step)
        row.update(prompt_metrics.get(key, {}))
        row["search_depth"] = int(step["cursor_before"])
        row["step_index"] = int(step["call_index"])
        row["value_misselection"] = 1 if step.get("operator_repair") == "value_misselection" else 0
        row["format_failure"] = 1 if step.get("operator_repair") == "format_failure" else 0
        row["missed_prune_count"] = int(step.get("n_missed_prunes") or 0)
        row["accepted_prune_count"] = int(step.get("n_accepted_prunes") or 0)
        row["oracle_prune_count"] = int(step.get("n_oracle_prunes") or 0)
        annotated.append(row)
    return annotated


def _inloop_keff(full: dict[str, Any]) -> dict[str, Any]:
    operator = _operator_by_b(_read_json(GRADED_PATH))[2]
    recall = float(full["inloop_vs_isolated_recall"][0]["inloop_recall"])
    clean = float(operator["k_eff_clean"])
    unpruned = float(operator["unpruned_k_eff"])
    isolated_recall = float(operator["prune_recall"])
    isolated_keff = float(operator["graded_keff_inflated"])
    inloop_keff = clean + (1.0 - recall) * (unpruned - clean)
    return {
        "b": 2,
        "k_eff_clean": clean,
        "unpruned_k_eff": unpruned,
        "isolated_recall": isolated_recall,
        "isolated_graded_keff": isolated_keff,
        "inloop_recall": recall,
        "inloop_recalibrated_keff": inloop_keff,
        "method": "k_eff_clean + (1 - inloop_recall) * (unpruned_k_eff - k_eff_clean)",
        "source": SOURCE,
        "provenance": "item063_inloop_keff_recalibration_v0",
    }


def _interpolate_dstar(depth_rates: list[tuple[int, float]]) -> dict[str, Any]:
    ordered = sorted(depth_rates)
    if not ordered:
        return {"dstar_observed": None, "censoring": "no_depth_rows"}
    threshold = LOW_SOLVE_THRESHOLD
    first_depth, first_rate = ordered[0]
    if first_rate <= threshold:
        return {"dstar_observed": None, "censoring": "left_censored_below_min_depth", "dstar_upper_bound": float(first_depth), "supporting_solve_rates": {str(k): v for k, v in ordered}}
    previous_depth, previous_rate = ordered[0]
    for depth, rate in ordered[1:]:
        if rate <= threshold:
            crossing = float(previous_depth) if previous_rate == rate else float(previous_depth) + (threshold - previous_rate) * float(depth - previous_depth) / (rate - previous_rate)
            return {"dstar_observed": crossing, "censoring": "uncensored_interpolated", "supporting_solve_rates": {str(k): v for k, v in ordered}}
        previous_depth, previous_rate = depth, rate
    return {"dstar_observed": float(previous_depth), "censoring": "right_censored_at_max_depth", "dstar_lower_bound": float(previous_depth), "supporting_solve_rates": {str(k): v for k, v in ordered}}


def _cell_proxy_rows(full: dict[str, Any], keff_row: dict[str, Any]) -> list[dict[str, Any]]:
    capacity_rows = full["capacity_scaling_inloop_b2"]
    full_table = _read_json(FULL_TABLE_V1_PATH)
    footprint_rows = full_table.get("separator_footprint_by_b")
    footprint_b = 0.0
    if isinstance(footprint_rows, dict):
        footprint_b = float(footprint_rows.get("2", footprint_rows.get(2, 0.0)))
    elif isinstance(footprint_rows, list):
        for row in footprint_rows:
            if str(row.get("b_bin")) == "2":
                footprint_b = float(row.get("footprint_b", 0.0))
    out = []
    by_d: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in capacity_rows:
        by_d[int(row["register_capacity_D"])].append(row)
    for register_d, subset in sorted(by_d.items()):
        rates = [(int(row["d_global_bin"]), float(row["solve_rate"])) for row in subset]
        dstar = _interpolate_dstar(rates)
        solve_rates = [rate for _, rate in sorted(rates)]
        nonmonotone = any(solve_rates[index + 1] > solve_rates[index] for index in range(len(solve_rates) - 1))
        inloop_keff = float(keff_row["inloop_recalibrated_keff"])
        d_eff = max(0.0, float(register_d) - footprint_b)
        pred_deff = d_eff / math.log(max(inloop_keff, 1.0001))
        pred_raw = float(register_d) / math.log(max(inloop_keff, 1.0001))
        observed = dstar.get("dstar_observed")
        if nonmonotone:
            residual = None
            law_match = False
        elif observed is not None:
            residual = float(observed) - pred_deff
            law_match = abs(residual) <= 1.0
        elif dstar.get("dstar_upper_bound") is not None:
            residual = None
            law_match = pred_deff <= float(dstar["dstar_upper_bound"])
        elif dstar.get("dstar_lower_bound") is not None:
            residual = None
            law_match = pred_deff >= float(dstar["dstar_lower_bound"])
        else:
            residual = None
            law_match = False
        out.append({
            "register_capacity_D": register_d,
            "b_bin": "2",
            "inloop_recalibrated_keff": inloop_keff,
            "footprint_b_from_p1b_v1": footprint_b,
            "D_eff": d_eff,
            "dstar_predicted_raw_D_over_lnK": pred_raw,
            "dstar_predicted_Deff_over_lnK": pred_deff,
            "dstar_residual_vs_Deff_prediction": residual,
            "law_match_at_inloop_keff": bool(law_match),
            "nonmonotone_solve_curve": nonmonotone,
            "interpretation_guard": "nonmonotone solve curves make capacity-law matching invalid without a monotone collapse front" if nonmonotone else "monotone/interpolatable",
            "source": SOURCE,
            "provenance": "item063_proxy_match_by_cell_inloop_keff_v0",
            **dstar,
        })
    return out


def _failure_rows(full: dict[str, Any], keff_row: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    by_instance_steps: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for step in full["inloop_step_metrics"]:
        by_instance_steps[(str(step["instance_id"]), int(step["register_capacity_D"]))].append(step)
    inloop_keff = float(keff_row["inloop_recalibrated_keff"])
    for row in full["instance_arm_metrics"]:
        key = (str(row["instance_id"]), int(row["register_capacity_D"]))
        steps = by_instance_steps.get(key, [])
        max_depth = max((int(step["cursor_before"]) for step in steps), default=None)
        last_depth = int(steps[-1]["cursor_before"]) if steps else None
        effective_at_last = None if last_depth is None else math.ceil(max(int(row["d_global_reference"]), last_depth) * math.log(max(inloop_keff, 1.0001)))
        status = row["status"]
        if status == "OVERFLOW_FAIL":
            binding = "capacity_bound_by_runner_effective_peak"
        elif status == "CALL_CAP":
            binding = "operator_or_search_bound_call_cap"
        elif status == "NO_RECOVERY_TARGET":
            binding = "operator_search_failure_below_capacity_overflow"
        elif status == "SOLVED":
            binding = "solved"
        else:
            binding = "other"
        out.append({
            "instance_id": row["instance_id"],
            "register_capacity_D": int(row["register_capacity_D"]),
            "d_global_reference": int(row["d_global_reference"]),
            "status": status,
            "llm_calls": int(row["llm_calls"]),
            "call_cap_hit": bool(row["call_cap_hit"]),
            "solved_valid": bool(row["solved_valid"]),
            "last_logged_depth": last_depth,
            "max_logged_depth": max_depth,
            "effective_peak_proxy_at_last_depth_inloop_keff": effective_at_last,
            "capacity_exceeded_proxy_at_last_depth": None if effective_at_last is None else effective_at_last > int(row["register_capacity_D"]),
            "binding_class": binding,
            "source": SOURCE,
            "provenance": "item063_failure_binding_proxy_v0",
        })
    return out


def _plot_binned(depth_rows: list[dict[str, Any]], step_rows: list[dict[str, Any]], prompt_rows: list[dict[str, Any]]) -> list[str]:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    specs = [
        (depth_rows, "search_depth", "depth_recall_misselection.png", "Search depth"),
        (step_rows, "step_index", "step_index_recall_misselection.png", "Step index"),
        (prompt_rows, "prompt_chars_bin", "prompt_chars_recall_misselection.png", "Reconstructed prompt chars"),
    ]
    for rows, x_key, name, xlabel in specs:
        if not rows:
            continue
        xs = [row[x_key] for row in rows]
        recall = [row.get("mean_recall") for row in rows]
        miss = [row.get("misselection_rate") for row in rows]
        fig, ax1 = plt.subplots(figsize=(8, 4.5))
        ax1.plot(xs, recall, marker="o", color="#1f77b4", label="mean propagation recall")
        ax1.set_xlabel(xlabel)
        ax1.set_ylabel("Mean propagation recall", color="#1f77b4")
        ax1.tick_params(axis="y", labelcolor="#1f77b4")
        ax2 = ax1.twinx()
        ax2.plot(xs, miss, marker="s", color="#d62728", label="value-misselection rate")
        ax2.set_ylabel("Value-misselection rate", color="#d62728")
        ax2.tick_params(axis="y", labelcolor="#d62728")
        ax1.grid(True, alpha=0.25)
        fig.tight_layout()
        path = PLOT_DIR / name
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(_rel(path))
    return paths


def run() -> dict[str, Any]:
    full = _read_json(FULL_SLICE_PATH)
    explicit_full = _read_json(EXPLICIT_STATE_FULL_PATH) if EXPLICIT_STATE_FULL_PATH.exists() else None
    steps = _annotated_steps(full)
    valid_opportunity_steps = [row for row in steps if row.get("propagation_recall") is not None]
    depth_rows = _bin_rows(valid_opportunity_steps, "search_depth")
    step_index_rows = _bin_rows(valid_opportunity_steps, "step_index")
    for row in steps:
        chars = row.get("prompt_chars_reconstructed")
        row["prompt_chars_bin"] = None if chars is None else int(chars // 100) * 100
    prompt_rows = _bin_rows([row for row in valid_opportunity_steps if row.get("prompt_chars_bin") is not None], "prompt_chars_bin")

    regressions = [
        _ols(valid_opportunity_steps, "search_depth", "propagation_recall"),
        _ols(valid_opportunity_steps, "step_index", "propagation_recall"),
        _ols(valid_opportunity_steps, "prompt_chars_reconstructed", "propagation_recall"),
        _ols(steps, "search_depth", "value_misselection", y_binary=True),
        _ols(steps, "step_index", "value_misselection", y_binary=True),
        _ols(steps, "prompt_chars_reconstructed", "value_misselection", y_binary=True),
    ]
    keff_row = _inloop_keff(full)
    proxy_rows = _cell_proxy_rows(full, keff_row)
    failure_rows = _failure_rows(full, keff_row)
    failure_counts = Counter(row["status"] for row in full["instance_arm_metrics"])
    binding_counts = Counter(row["binding_class"] for row in failure_rows)
    repair_counts = Counter(row.get("operator_repair") for row in steps)
    n_oracle = sum(int(row.get("n_oracle_prunes") or 0) for row in steps)
    n_missed = sum(int(row.get("n_missed_prunes") or 0) for row in steps)
    n_accepted = sum(int(row.get("n_accepted_prunes") or 0) for row in steps)

    plot_paths = _plot_binned(depth_rows, step_index_rows, prompt_rows)
    recall_depth_slope = next(row for row in regressions if row["x"] == "search_depth" and row["y"] == "propagation_recall")["slope"]
    miss_depth_slope = next(row for row in regressions if row["x"] == "search_depth" and row["y"] == "value_misselection")["slope"]
    total_gap = float(full["inloop_vs_isolated_recall"][0]["isolated_step1A_recall"]) - float(full["inloop_vs_isolated_recall"][0]["inloop_recall"])
    explicit_pilot = _read_json(EXPLICIT_STATE_PILOT_PATH) if EXPLICIT_STATE_PILOT_PATH.exists() else None
    explicit_steps = explicit_pilot.get("inloop_step_metrics", []) if explicit_pilot else []
    explicit_recall = explicit_pilot["inloop_vs_isolated_recall"][0]["inloop_recall"] if explicit_pilot and explicit_pilot.get("inloop_vs_isolated_recall") else None
    explicit_misselection_rate = _safe_div(float(sum(1 for row in explicit_steps if row.get("operator_repair") == "value_misselection")), float(len(explicit_steps))) if explicit_steps else None
    explicit_full_steps = explicit_full.get("inloop_step_metrics", []) if explicit_full else []
    explicit_full_recall = explicit_full["inloop_vs_isolated_recall"][0]["inloop_recall"] if explicit_full and explicit_full.get("inloop_vs_isolated_recall") else None
    explicit_full_misselection_rate = _safe_div(float(sum(1 for row in explicit_full_steps if row.get("operator_repair") == "value_misselection")), float(len(explicit_full_steps))) if explicit_full_steps else None
    explicit_full_keff = _inloop_keff(explicit_full) if explicit_full else None
    explicit_full_proxy_rows = _cell_proxy_rows(explicit_full, explicit_full_keff) if explicit_full and explicit_full_keff else []
    interpretation = "uniform_inloop_framing_gap_not_depth_context_bound"
    rationale = (
        "Changing only the state encoding recovered the operator channel in the pilot and removed value-misselection at full-slice "
        "scale. Full explicit-state recall improves over the original implicit full slice but remains materially below isolated recall, "
        "and the solve curves remain censored/nonmonotone. The correct diagnosis is a uniform framing/state-encoding gap with partial "
        "full-slice recovery, not a demonstrated depth-context collapse or a validated end-to-end capacity law."
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "generated_at": _now(),
        "source_artifact": _rel(FULL_SLICE_PATH),
        "explicit_state_full_artifact": _rel(EXPLICIT_STATE_FULL_PATH) if explicit_full else None,
        "plots": plot_paths,
        "summary": {
            "n_instances": len(full["instance_arm_metrics"]),
            "n_steps": len(steps),
            "n_opportunity_steps": len(valid_opportunity_steps),
            "inloop_recall": full["inloop_vs_isolated_recall"][0]["inloop_recall"],
            "isolated_step1A_recall": full["inloop_vs_isolated_recall"][0]["isolated_step1A_recall"],
            "value_misselection_steps": int(repair_counts.get("value_misselection", 0)),
            "value_misselection_rate": _safe_div(float(repair_counts.get("value_misselection", 0)), float(len(steps))),
            "explicit_state_pilot_recall": explicit_recall,
            "explicit_state_pilot_value_misselection_rate": explicit_misselection_rate,
            "explicit_state_pilot_steps": len(explicit_steps),
            "explicit_state_full_recall": explicit_full_recall,
            "explicit_state_full_value_misselection_rate": explicit_full_misselection_rate,
            "explicit_state_full_steps": len(explicit_full_steps),
            "explicit_state_full_recall_delta_vs_implicit_full": None if explicit_full_recall is None else explicit_full_recall - float(full["inloop_vs_isolated_recall"][0]["inloop_recall"]),
            "explicit_state_full_recall_delta_vs_pilot": None if explicit_full_recall is None or explicit_recall is None else explicit_full_recall - float(explicit_recall),
            "format_failure_steps": int(repair_counts.get("format_failure", 0)),
            "missed_prunes": n_missed,
            "accepted_oracle_prunes": n_accepted,
            "oracle_prunes": n_oracle,
            "missed_prune_rate": _safe_div(float(n_missed), float(n_oracle)),
            "failure_status_counts": dict(failure_counts),
            "failure_binding_counts": dict(binding_counts),
            "recall_vs_depth_slope_ols": recall_depth_slope,
            "misselection_vs_depth_slope_ols": miss_depth_slope,
            "isolated_minus_inloop_recall_gap": total_gap,
            "slope_causality_note": "Univariate depth/step slopes are descriptive and confounded by cell/status/recovery mixture; the explicit-state re-pilot is the discriminating evidence.",
            "interpretation": interpretation,
            "rationale": rationale,
            "source": SOURCE,
            "provenance": "item063_inloop_divergence_summary_v0",
        },
        "keff_recalibration": [keff_row],
        "explicit_full_keff_recalibration": [] if explicit_full_keff is None else [explicit_full_keff],
        "regressions": regressions,
        "recall_and_misselection_by_depth": depth_rows,
        "recall_and_misselection_by_step_index": step_index_rows,
        "recall_and_misselection_by_prompt_chars": prompt_rows,
        "proxy_match_by_cell_inloop_keff": proxy_rows,
        "proxy_match_by_cell_explicit_full_keff": explicit_full_proxy_rows,
        "failure_binding_by_instance": failure_rows,
        "error_channel_summary": [
            {
                "channel": "missed_propagation",
                "events": n_missed,
                "denominator_oracle_prunes": n_oracle,
                "rate": _safe_div(float(n_missed), float(n_oracle)),
                "note": "recall channel measured by accepted oracle prunes over oracle prune opportunities",
            },
            {
                "channel": "value_misselection",
                "events": int(repair_counts.get("value_misselection", 0)),
                "denominator_steps": len(steps),
                "rate": _safe_div(float(repair_counts.get("value_misselection", 0)), float(len(steps))),
                "note": "new in-loop-only state-tracking channel; isolated P1b grading did not exercise accumulated state",
            },
        ],
        "honesty": {
            "no_rerun": "This analysis uses existing Item063 full-slice data only and makes no Qwen/vLLM calls.",
            "prompt_length_limit": "Raw prompts/tokens were not persisted; prompt context is reconstructed as character/word-count proxy from static manifest plus logged cursor/chosen_color assignments.",
            "register_occupancy_limit": "Exact register occupancy history was not persisted. Capacity binding is inferred from runner status OVERFLOW_FAIL and effective-peak proxy; NO_RECOVERY_TARGET/CALL_CAP are not register-overflow successes.",
            "retroactive_qualification": "Earlier b2 calibrated capacity positive used isolated recall 0.524, not real in-loop recall 0.214; it is symbolic-mechanism evidence, not end-to-end LLM evidence until an in-loop framing that functions is used.",
            "prompt_encoding_finding": "The original in-loop prompt supplied visible assignments and graph edges but not explicit current per-vertex remaining domains/eliminated colors; explicit-state encoding removed value-misselection at full-slice scale, but full recall only partially recovered and does not establish the capacity law.",
        },
    }
    _write_json(OUT_PATH, payload)
    return payload


if __name__ == "__main__":
    run()