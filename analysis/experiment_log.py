"""Generate a consolidated experiment log for Stage D runs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


RESULT_FILES = {
    "preregistration": "results/preregistration/preregistration.json",
    "oracle_dataset": "results/oracle_dataset/summary.json",
    "operator_cache": "results/operator_cache/summary.json",
    "model_readiness": "results/model_readiness/readiness.json",
    "qwen_instruct_download": "results/model_download/qwen_download.json",
    "qwen_thinking_download": "results/model_download/thinking/qwen_download.json",
    "qwen_probe_cache": "results/operator_cache/qwen_probe_cache_summary.json",
    "qwen_128_cache": "results/operator_cache/qwen_128_cache_summary.json",
    "learned_wiring_qwen_128": "results/learned_wiring_qwen_128/results.json",
    "qwen_balanced_320_cache": "results/operator_cache/qwen_balanced_320_cache_summary.json",
    "learned_wiring_qwen_balanced_320": "results/learned_wiring_qwen_balanced_320/results.json",
    "module1_stack_capacity": "results/module1_stack_capacity/results.json",
    "module1_stack_capacity_full": "results/module1_stack_capacity_full/results.json",
    "module1_capacity_batching_large": "results/module1_capacity_batching_large/results.json",
    "module1_capacity_benchmark_full_shards": "results/module1_capacity_benchmark_full_shards/results.json",
    "module1_k_direction_corrected": "results/module1_capacity_benchmark_full_shards/k_direction_corrected.json",
    "module1_capacity_diagnostic_full_shards": "results/module1_capacity_diagnostic_full_shards/results.json",
    "module1_capacity_perdepth_shards": "results/module1_capacity_perdepth_shards/results.json",
    "module1_gru_smoke": "results/gru_stack_smoke/results.json",
    "module1_gru_grid_full": "results/gru_stack_grid_full/results.json",
    "learned_wiring": "results/learned_wiring/results.json",
    "two_by_two": "results/two_by_two/results.json",
    "d_stage_0": "results/d_stage_0/results.json",
    "d_stage_1": "results/d_stage_1/results.json",
    "d_stage_2": "results/d_stage_2/results.json",
    "d_stage_3": "results/d_stage_3/results.json",
    "verifier": "results/verifier/results.json",
    "ttt": "results/ttt/results.json",
    "analysis_summary": "results/analysis/summary.md",
    "validation": "results/validation/validation.json",
}


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read().strip()


def _load_results() -> dict[str, Any]:
    missing = [path for path in RESULT_FILES.values() if not os.path.exists(path)]
    if missing:
        raise FileNotFoundError(f"missing result files: {missing}")
    data: dict[str, Any] = {}
    for name, path in RESULT_FILES.items():
        data[name] = _read_text(path) if path.endswith(".md") else _read_json(path)
    return data


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    def cell(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.4g}"
        return str(value)

    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return lines


def _two_by_two_status(rows: list[dict[str, Any]]) -> str:
    latent_prop = next(row for row in rows if row["method"] == "latent_only" and row["column"] == "propagation_only")
    structured_prop = next(row for row in rows if row["method"] == "latent_plus_structured_register" and row["column"] == "propagation_only")
    latent_bt = next(row for row in rows if row["method"] == "latent_only" and row["column"] == "backtracking_required")
    structured_bt = next(row for row in rows if row["method"] == "latent_plus_structured_register" and row["column"] == "backtracking_required")
    helps_only_backtracking = structured_bt["solve_rate"] > latent_bt["solve_rate"] and structured_prop["solve_rate"] == latent_prop["solve_rate"]
    return "PASS" if helps_only_backtracking else "FAIL"


def _depth1_status(rows: list[dict[str, Any]]) -> str:
    structured = next(row for row in rows if row["method"] == "structured_register")
    latent = next(row for row in rows if row["method"] == "latent_only")
    gru = next(row for row in rows if row["method"] == "gru_register")
    no_revert = next(row for row in rows if row["method"] == "no_revert_ablation")
    ok = structured["applied_reverts"] > 0 and structured["solve_rate"] > latent["solve_rate"] and gru["solve_rate"] == latent["solve_rate"] and no_revert["solve_rate"] == latent["solve_rate"]
    return "PASS" if ok else "FAIL"


def _verifier_status(rows: list[dict[str, Any]]) -> str:
    by_mode = {row["mode"]: row for row in rows}
    ok = by_mode["oracle"]["solve_rate"] >= by_mode["learned"]["solve_rate"] >= by_mode["noisy"]["solve_rate"] >= by_mode["disabled"]["solve_rate"]
    return "PASS" if ok else "FAIL"


def _ttt_status(row: dict[str, Any]) -> str:
    return "PASS" if row["ttt_restore_error"] > row["structured_restore_error"] else "FAIL"


def _capacity_rows(rows: list[dict[str, Any]]) -> list[list[Any]]:
    selected = [row for row in rows if row["K"] in {60, 729}]
    return [[row["register_type"], row["D"], row["K"], row.get("predicted_d_star", ""), row["observed_frontier"]] for row in selected]


def _stage3_rows(rows: list[dict[str, Any]]) -> list[list[Any]]:
    out = []
    for row in rows:
        frontier_depth = max(point["depth"] for point in row["solve_curve"] if point["solve_rate"] > 0)
        out.append([row["D"], row["K"], row["method"], row["predicted_d_star"], frontier_depth, row["matched_compute"]])
    return out


def _incremental_items(data: dict[str, Any]) -> list[list[Any]]:
    return [
        ["01", "preregistration", "Computed d*_dyn bands before D-stage 3.", "results/preregistration/preregistration.json", f"bands={len(data['preregistration']['bands'])}"],
        ["02", "oracle dataset", "Materialized symbolic oracle supervision as JSONL.", "results/oracle_dataset/examples.jsonl", f"tasks={data['oracle_dataset']['n_tasks']}, examples={data['oracle_dataset']['n_examples']}"],
        ["03", "fallback operator cache", "Cached deterministic hashed prompt features for local learned-head checks.", data["operator_cache"]["cache"], f"hidden_dim={data['operator_cache']['hidden_dim']}, examples={data['operator_cache']['n_examples']}"],
        ["04", "uv/qwen readiness", "Verified uv environment, CUDA, and transformers availability.", "results/model_readiness/readiness.json", f"cuda={data['model_readiness']['cuda_available']}, transformers={data['model_readiness']['transformers_available']}"],
        ["05", "qwen downloads", "Downloaded frozen Instruct operator and Thinking CoT baseline snapshots.", "results/model_download/", f"instruct={data['qwen_instruct_download']['total_gib']:.2f}GiB, thinking={data['qwen_thinking_download']['total_gib']:.2f}GiB"],
        ["06", "qwen probe cache", "Confirmed Qwen Instruct loads and emits 2560-d hidden states.", data["qwen_probe_cache"]["cache"], f"examples={data['qwen_probe_cache']['n_examples']}, hidden_dim={data['qwen_probe_cache']['hidden_dim']}"],
        ["07", "qwen 128 smoke", "Ran a single-seed Qwen hidden-state wiring smoke test.", "results/learned_wiring_qwen_128/results.json", f"action={data['learned_wiring_qwen_128']['action_accuracy']:.4f}, verifier={data['learned_wiring_qwen_128']['verifier_accuracy']:.4f}"],
        ["08", "qwen balanced 320", "Ran balanced 5-seed Qwen hidden cache with seed-999 holdout.", "results/learned_wiring_qwen_balanced_320/results.json", f"holdout_action={data['learned_wiring_qwen_balanced_320']['holdout_action_accuracy']:.4f}, holdout_verifier={data['learned_wiring_qwen_balanced_320']['holdout_verifier_accuracy']:.4f}"],
        ["09", "module 1 quick", "Ran fast operator-free stack capacity sweep to validate pipeline.", "results/module1_stack_capacity/results.json", f"rows={len(data['module1_stack_capacity']['rows'])}, summary={len(data['module1_stack_capacity']['summary'])}"],
        ["10", "module 1 full gpu", "Ran full GPU stack sweep with rotation, GRU sequence proxy, and tape.", "results/module1_stack_capacity_full/results.json", f"rows={len(data['module1_stack_capacity_full']['rows'])}, device={data['module1_stack_capacity_full'].get('device')}"],
        ["11", "module 1 batching", "Benchmarked single-GPU batch sizes and raised default benchmark batch size.", "results/module1_capacity_batching_large/results.json", f"best_batches={[row['batch_size'] for row in data['module1_capacity_batching_large']['best_by_case']]}"] ,
        ["12", "module 1 capacity benchmark full", "Ran 8-shard task-free HRR/permutation capacity benchmark for K-direction.", "results/module1_capacity_benchmark_full_shards/results.json", f"decision={data['module1_capacity_benchmark_full_shards']['theory']['decision']}, open={data['module1_capacity_benchmark_full_shards']['theory']['open']}"],
        ["13", "ceiling-aware K reanalysis", "Recomputed K-direction after dropping frontier points capped by K_var/sweep ceiling.", "results/module1_capacity_benchmark_full_shards/k_direction_corrected.json", f"target={data['module1_k_direction_corrected']['expected_target']['classification']}, passed={data['module1_k_direction_corrected']['expected_target_passed']}"],
        ["14", "module 1 diagnostic full", "Ran fixed-depth diagnostic benchmark with joint/var/val K-direction metrics.", "results/module1_capacity_diagnostic_full_shards/results.json", f"decision={data['module1_capacity_diagnostic_full_shards']['decision']}, open={data['module1_capacity_diagnostic_full_shards']['open']}"],
        ["15", "module 1 per-depth full", "Ran ceiling-free per-depth benchmark with with/without replacement and K_eff fits.", "results/module1_capacity_perdepth_shards/results.json", f"decision={data['module1_capacity_perdepth_shards']['decision']}, open={data['module1_capacity_perdepth_shards']['open']}"],
        ["16", "gru tuned smoke", "Implemented tuned GRUStack and ran a val-selected checkpoint smoke.", "results/gru_stack_smoke/results.json", f"converged={data['module1_gru_smoke']['converged']}, frontier={data['module1_gru_smoke']['frontier_joint_095']}"],
        ["17", "gru tuned full grid", "Ran tuned GRUStack full grid and compared against structured capacity.", "results/gru_stack_grid_full/results.json", f"all_converged={data['module1_gru_grid_full']['all_converged']}, below_structured={data['module1_gru_grid_full']['all_gru_below_structured']}"],
        ["18", "scaffold gates", "Ran D.3, D-stage 0/1/2/3, verifier, and TTT scaffold gates.", "results/*/results.json", f"validation={data['validation']['passed']}"],
        ["19", "validation", "Validated required files, schemas, gate expectations, and Module 1 comparisons.", "results/validation/validation.json", f"checks={len(data['validation']['checks'])}, passed={data['validation']['passed']}"],
    ]


def _module1_full_table(data: dict[str, Any]) -> list[str]:
    rows = [[row["method"], row["D"], row["K"], row["predicted_d_star"], row["frontier_decode_095"]] for row in data["module1_stack_capacity_full"]["summary"]]
    return _table(["method", "D", "K", "predicted_d_star", "frontier_decode_095"], rows)


def _core_sweep_numeric_summaries(data: dict[str, Any]) -> list[str]:
    perdepth = data["module1_capacity_perdepth_shards"]
    gru = data["module1_gru_grid_full"]
    lines: list[str] = [
        "",
        "## Core Sweep Numeric Summaries",
        "",
        "These are the concrete values from the decisive Module 1 sweeps. Full curves and per-cell records remain in the JSON artifacts listed above.",
        "",
        "### Per-depth K-direction, D=1024, K_val=2, joint accuracy capacity@0.95",
        "",
    ]
    direction_rows = [
        item
        for item in perdepth["directions"]
        if item["D"] == 1024 and item["K_val"] == 2 and item["metric"] == "joint"
    ]
    lines.extend(_table(
        ["variant", "replacement", "K_vars", "capacity_joint_095", "signs"],
        [[row["variant"], row["replacement"], row["K_vars"], row["capacities"], row["signs"]] for row in direction_rows],
    ))
    lines.extend([
        "",
        "### K_eff fit summary, joint metric",
        "",
    ])
    fit_rows = [fit for fit in perdepth["fits"] if fit["metric"] == "joint"]
    lines.extend(_table(
        ["variant", "replacement", "best_k_eff", "n_points", "product_slope", "product_r2", "Kvar_slope", "Kvar_r2", "max_factor_slope", "max_factor_r2"],
        [[
            fit["variant"],
            fit["replacement"],
            fit["best_k_eff"],
            fit["n_points"],
            fit["fits"].get("D_over_ln_product", {}).get("slope"),
            fit["fits"].get("D_over_ln_product", {}).get("r2"),
            fit["fits"].get("D_over_ln_Kvar", {}).get("slope"),
            fit["fits"].get("D_over_ln_Kvar", {}).get("r2"),
            fit["fits"].get("halfD_over_ln_max_factor", {}).get("slope"),
            fit["fits"].get("halfD_over_ln_max_factor", {}).get("r2"),
        ] for fit in fit_rows],
    ))
    lines.extend([
        "",
        "### Tuned GRU grid vs structured register, matched cells",
        "",
    ])
    comparison_rows = sorted(gru["comparisons"], key=lambda row: (row["D"], row["K_var"], row["K_val"], row["replacement"]))
    lines.extend(_table(
        ["D", "K_var", "K_val", "replacement", "structured_variant", "structured_capacity", "gru_capacity", "gap", "gru_below"],
        [[
            row["D"],
            row["K_var"],
            row["K_val"],
            row["replacement"],
            row["structured_variant"],
            row["structured_capacity_joint_095"],
            row["gru_capacity_joint_095"],
            row["structured_capacity_joint_095"] - row["gru_capacity_joint_095"],
            row["gru_below_structured"],
        ] for row in comparison_rows],
    ))
    lines.extend([
        "",
        "### Batching sweep best cases",
        "",
    ])
    lines.extend(_table(
        ["variant", "D", "K_var", "K_val", "depth", "best_batch", "trials_per_sec", "elapsed_sec", "peak_gib"],
        [[row["variant"], row["D"], row["K_var"], row["K_val"], row["depth"], row["batch_size"], row["trials_per_sec"], row["elapsed_sec"], row["peak_gib"]] for row in data["module1_capacity_batching_large"]["best_by_case"]],
    ))
    return lines


def _detailed_run_items(data: dict[str, Any]) -> list[str]:
    lines: list[str] = ["", "## Detailed Itemized Run Log", ""]
    lines.extend([
        "### 001. Established preregistration bands and scaffold run order",
        "",
        "Purpose: make the Stage D ceiling claim auditable before downstream scaffold runs. This records the d*_dyn formula and predeclared D/K bands.",
        "",
        "Code used:",
        "",
        "- `analysis/preregistration.py`",
        "- `PLAN.md`",
        "- `config/experiments.yaml`",
        "",
        "Command:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm && python -m analysis.preregistration",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/preregistration/preregistration.json`",
        "",
        "Result summary:",
        "",
    ])
    lines.extend(_table(["label", "D", "K", "predicted_d_star"], [[row["label"], row["D"], row["K"], row["predicted_d_star"]] for row in data["preregistration"]["bands"]]))
    lines.extend([
        "",
        "Decision: preregistration pass. These bands are now the fixed reference for later D-stage claims.",
        "",
        "### 002. Built symbolic oracle supervision dataset",
        "",
        "Purpose: enforce the discipline that supervision comes from symbolic oracle traces, not stronger LLM CoT. This materializes the current-node training examples used by later cache/head experiments.",
        "",
        "Code added/used:",
        "",
        "- `analysis/oracle_dataset.py`",
        "- `tasks/oracle/trace_generator.py`",
        "- `tasks/sat/generators.py`",
        "- `tasks/sudoku/generator_4x4.py`",
        "- `tasks/graph_coloring/generator.py`",
        "- `tasks/logic_grid/generator.py`",
        "",
        "Command:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm && python -m analysis.oracle_dataset",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/oracle_dataset/examples.jsonl`",
        "- `results/oracle_dataset/summary.json`",
        "",
        "Dataset summary:",
        "",
        f"- tasks: {data['oracle_dataset']['n_tasks']}",
        f"- examples: {data['oracle_dataset']['n_examples']}",
        f"- max_backtrack_depth: {data['oracle_dataset']['max_backtrack_depth']}",
        "",
    ])
    lines.extend(_table(["task_type", "tasks", "examples"], [[name, row["tasks"], row["examples"]] for name, row in data["oracle_dataset"]["task_types"].items()]))
    lines.extend([
        "",
        "Decision: dataset pass. This is still oracle-supervised scaffold data, but it is now explicit and reusable.",
        "",
        "### 003. Set up uv environment and downloaded Qwen3-4B variants",
        "",
        "Purpose: move from missing dependencies to a reproducible uv-managed environment, then download both Qwen roles required by the Stage D design.",
        "",
        "Code added/used:",
        "",
        "- `.venv` created by `uv`",
        "- `analysis/model_readiness.py`",
        "- `analysis/download_qwen.py`",
        "- `config/backbone.yaml`",
        "",
        "Validation/setup commands:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm",
        "~/.local/bin/uv venv .venv --python 3.10",
        "~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt huggingface_hub accelerate",
        "~/.local/bin/uv run --python .venv/bin/python python -m analysis.model_readiness",
        "~/.local/bin/uv run --python .venv/bin/python python -m analysis.download_qwen --model-id Qwen/Qwen3-4B-Instruct-2507",
        "~/.local/bin/uv run --python .venv/bin/python python -m analysis.download_qwen --model-id Qwen/Qwen3-4B-Thinking-2507 --output-dir results/model_download/thinking",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/model_readiness/readiness.json`",
        "- `results/model_download/qwen_download.json`",
        "- `results/model_download/thinking/qwen_download.json`",
        "",
        "Environment/model summary:",
        "",
        f"- transformers_available: {data['model_readiness']['transformers_available']}",
        f"- cuda_available: {data['model_readiness']['cuda_available']}",
        f"- cuda_device_count: {data['model_readiness']['cuda_device_count']}",
        f"- Instruct snapshot: `{data['qwen_instruct_download']['snapshot_path']}`",
        f"- Thinking snapshot: `{data['qwen_thinking_download']['snapshot_path']}`",
        "",
        "Decision: environment pass. Both Qwen3-4B snapshots are local and the uv environment can load transformers with CUDA visible.",
        "",
        "### 004. Confirmed real Qwen hidden-state contact with probe cache",
        "",
        "Purpose: verify that Qwen3-4B-Instruct actually loads and emits hidden states with the expected hidden dimension, before attempting larger caches.",
        "",
        "Code used:",
        "",
        "- `analysis/operator_cache.py`",
        "- `llm_operator/wrapper.py`",
        "- `llm_operator/prompt_renderer.py`",
        "",
        "Command:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm && ~/.local/bin/uv run --python .venv/bin/python python -m analysis.operator_cache --load-model --limit 8 --output-name qwen_probe_cache",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/operator_cache/qwen_probe_cache.pt`",
        "- `results/operator_cache/qwen_probe_cache_summary.json`",
        "",
        "Probe result:",
        "",
        f"- feature_source: `{data['qwen_probe_cache']['feature_source']}`",
        f"- hidden_dim: {data['qwen_probe_cache']['hidden_dim']}",
        f"- examples: {data['qwen_probe_cache']['n_examples']}",
        "",
        "Decision: Qwen hidden-state probe pass. This validates the frozen operator loading path.",
        "",
        "### 005. Ran Qwen hidden-state learned wiring smoke and balanced holdout",
        "",
        "Purpose: move beyond deterministic fallback features and test whether frozen Qwen hidden states support supervised controller/verifier heads, including a seed-999 holdout split.",
        "",
        "Code added/used:",
        "",
        "- `analysis/operator_cache.py`",
        "- `experiments/learned_wiring_baseline.py`",
        "- `controller/controller_head.py`",
        "- `controller/verifier_head.py`",
        "",
        "Commands:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm",
        "~/.local/bin/uv run --python .venv/bin/python python -m analysis.operator_cache --load-model --limit 128 --output-name qwen_128_cache",
        "~/.local/bin/uv run --python .venv/bin/python python -m experiments.learned_wiring_baseline --cache-path results/operator_cache/qwen_128_cache.pt --output-dir results/learned_wiring_qwen_128 --epochs 20 --batch-size 32",
        "~/.local/bin/uv run --python .venv/bin/python python -m analysis.operator_cache --load-model --seeds 42,137,256,314,999 --per-seed-limit 64 --output-name qwen_balanced_320_cache",
        "~/.local/bin/uv run --python .venv/bin/python python -m experiments.learned_wiring_baseline --cache-path results/operator_cache/qwen_balanced_320_cache.pt --output-dir results/learned_wiring_qwen_balanced_320 --epochs 24 --batch-size 32",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/operator_cache/qwen_128_cache.pt`",
        "- `results/operator_cache/qwen_128_cache_summary.json`",
        "- `results/learned_wiring_qwen_128/results.json`",
        "- `results/learned_wiring_qwen_128/heads.pt`",
        "- `results/operator_cache/qwen_balanced_320_cache.pt`",
        "- `results/operator_cache/qwen_balanced_320_cache_summary.json`",
        "- `results/learned_wiring_qwen_balanced_320/results.json`",
        "- `results/learned_wiring_qwen_balanced_320/heads.pt`",
        "",
        "Result summary:",
        "",
    ])
    lines.extend(_table(
        ["run", "examples", "train_action", "holdout_action", "train_verifier", "holdout_verifier"],
        [
            ["qwen_128_smoke", data["learned_wiring_qwen_128"]["n_examples"], data["learned_wiring_qwen_128"]["train_action_accuracy"], data["learned_wiring_qwen_128"].get("holdout_action_accuracy", 0.0), data["learned_wiring_qwen_128"]["train_verifier_accuracy"], data["learned_wiring_qwen_128"].get("holdout_verifier_accuracy", 0.0)],
            ["qwen_balanced_320", data["learned_wiring_qwen_balanced_320"]["n_examples"], data["learned_wiring_qwen_balanced_320"]["train_action_accuracy"], data["learned_wiring_qwen_balanced_320"]["holdout_action_accuracy"], data["learned_wiring_qwen_balanced_320"]["train_verifier_accuracy"], data["learned_wiring_qwen_balanced_320"]["holdout_verifier_accuracy"]],
        ],
    ))
    lines.extend([
        "",
        "Decision: Qwen hidden-state wiring passes as a small supervised probe. The balanced seed-999 holdout action accuracy is materially higher than the deterministic fallback baseline.",
        "",
        "### 006. Ran deterministic fallback learned wiring baseline with seed holdout",
        "",
        "Purpose: keep a non-Qwen local baseline for comparison and sanity-check whether the learned-head path can memorize train seeds without real operator features.",
        "",
        "Commands:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm",
        "python -m analysis.operator_cache",
        "python -m experiments.learned_wiring_baseline",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/operator_cache/operator_cache.pt`",
        "- `results/operator_cache/summary.json`",
        "- `results/learned_wiring/results.json`",
        "- `results/learned_wiring/heads.pt`",
        "",
        "Result summary:",
        "",
        f"- train_action_accuracy: {data['learned_wiring']['train_action_accuracy']:.4f}",
        f"- holdout_action_accuracy: {data['learned_wiring']['holdout_action_accuracy']:.4f}",
        f"- train_verifier_accuracy: {data['learned_wiring']['train_verifier_accuracy']:.4f}",
        f"- holdout_verifier_accuracy: {data['learned_wiring']['holdout_verifier_accuracy']:.4f}",
        "",
        "Decision: fallback baseline is useful as a sanity check, but weak for seed-holdout action generalization. Do not use it for the Qwen claim.",
        "",
        "### 007. Ran Module 1 operator-free stack capacity quick and full GPU sweeps",
        "",
        "Purpose: start the new three-module design at Module 1, isolating the bounded reversible stack from Qwen. This compares rotation/VSA, GRU bounded vector proxy, and explicit tape.",
        "",
        "Code added/modified:",
        "",
        "- `register/vsa_stack.py`",
        "- `experiments/module1_stack_capacity.py`",
        "",
        "Commands:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm",
        "~/.local/bin/uv run --python .venv/bin/python python -m experiments.module1_stack_capacity --mode quick --output-dir results/module1_stack_capacity",
        "~/.local/bin/uv run --python .venv/bin/python python -m experiments.module1_stack_capacity --mode full --device cuda:0 --output-dir results/module1_stack_capacity_full",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/module1_stack_capacity/results.json`",
        "- `results/module1_stack_capacity/run.log`",
        "- `results/module1_stack_capacity_full/results.json`",
        "- `results/module1_stack_capacity_full/run.log`",
        "",
        "Full GPU frontier summary:",
        "",
    ])
    lines.extend(_module1_full_table(data))
    lines.extend([
        "",
        "Decision: Module 1 full GPU run passes the current validation checks: rotation frontier is above matched GRU sequence proxy, and tape remains the upper bound. Scientific caveat: current rotation implementation is still a random level-key/Hadamard proxy, not the stronger orthogonal rotation + HRR cleanup implementation from the design note, and observed frontiers are below the d*(D) line.",
        "",
        "### 008. Benchmarked Module 1 capacity batch sizes",
        "",
        "Purpose: find a faster single-GPU batch size before launching sharded full capacity runs. The first batched implementation still used a conservative default; this item measures throughput and peak memory directly on `cuda:0`.",
        "",
        "Code added/modified:",
        "",
        "- `analysis/benchmark_capacity_batching.py`",
        "- `experiments/module1_capacity_benchmark.py`",
        "",
        "Command:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm && ~/.local/bin/uv run --python .venv/bin/python python -u -m analysis.benchmark_capacity_batching --device cuda:0 --batch-sizes 512,1024,2048,4096,8192,16384 --n-trials 8192 --output-dir results/module1_capacity_batching_large",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/module1_capacity_batching_large/results.json`",
        "- `results/module1_capacity_batching_large/run.log`",
        "",
        "Best batch by case:",
        "",
    ])
    lines.extend(_table(["variant", "D", "K_var", "K_val", "best_batch", "trials_per_sec", "peak_gib"], [[row["variant"], row["D"], row["K_var"], row["K_val"], row["batch_size"], row["trials_per_sec"], row["peak_gib"]] for row in data["module1_capacity_batching_large"]["best_by_case"]]))
    lines.extend([
        "",
        "Decision: use `--batch-size 8192` as the robust default for Module 1 capacity benchmark shards. It is near-best across cases and uses far below available A100 memory; 16384 can be faster for some factored cases but is less uniformly best.",
        "",
        "### 009. Ran 8-shard task-free Module 1 capacity benchmark",
        "",
        "Purpose: resolve whether the earlier K-inversion was a proxy artifact by using the proper HRR/permutation bound-single and factored registers over a task-free storage stress benchmark. This is the decisive K-direction test before any d* claim.",
        "",
        "Code added/modified:",
        "",
        "- `register/vsa_stack.py`",
        "- `experiments/module1_capacity_benchmark.py`",
        "- `analysis/capacity_theory.py`",
        "- `analysis/merge_capacity_shards.py`",
        "",
        "Command:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm && for i in 0 1 2 3 4 5 6 7; do CUDA_VISIBLE_DEVICES=$i ~/.local/bin/uv run --python .venv/bin/python python -u -m experiments.module1_capacity_benchmark --mode full --device cuda:0 --num-shards 8 --shard-index $i --batch-size 8192 --output-dir results/module1_capacity_benchmark_full_shards/shard_$i & done; wait; ~/.local/bin/uv run --python .venv/bin/python python -m analysis.merge_capacity_shards --input-dir results/module1_capacity_benchmark_full_shards",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/module1_capacity_benchmark_full_shards/results.json`",
        "- `results/module1_capacity_benchmark_full_shards/curves.json`",
        "- `results/module1_capacity_benchmark_full_shards/merge.log`",
        "- `results/module1_capacity_benchmark_full_shards/shard_*/results.json`",
        "- `results/module1_capacity_benchmark_full_shards/shard_*/run.log`",
        "",
        "K-direction result:",
        "",
    ])
    lines.extend(_table(["variant", "D", "K_val", "K_vars", "frontiers", "signs"], [[item["variant"], item["D"], item["K_val"], item["K_vars"], item["frontiers"], item["signs"]] for item in data["module1_capacity_benchmark_full_shards"]["theory"]["k_direction"]]))
    lines.extend([
        "",
        f"- calibrated_c: {data['module1_capacity_benchmark_full_shards']['theory']['calibrated_c']}",
        f"- decision: `{data['module1_capacity_benchmark_full_shards']['theory']['decision']}`",
        f"- open: {data['module1_capacity_benchmark_full_shards']['theory']['open']}",
        "",
        "Decision: K-direction remains open/nonmonotonic under the proper HRR/permutation benchmark. Do not claim d* = D/(2 ln K). The safe current claim is linear-in-D improvement for the measured construction plus GRU/tape comparison, with K-scaling unresolved.",
        "",
        "### 010. Recomputed K-direction after excluding ceiling-bound points",
        "",
        "Purpose: correct the initial K-direction decision logic. Since variables are sampled without replacement, small K_var runs cannot exceed K_var stack levels; those points must be excluded before judging K monotonicity.",
        "",
        "Code added:",
        "",
        "- `analysis/k_direction_recompute.py`",
        "",
        "Command:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm && ~/.local/bin/uv run --python .venv/bin/python python -m analysis.k_direction_recompute",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/module1_capacity_benchmark_full_shards/k_direction_corrected.json`",
        "",
        "Corrected target result:",
        "",
    ])
    target = data["module1_k_direction_corrected"]["expected_target"]
    lines.extend(_table(["variant", "D", "K_val", "full_classification", "corrected_classification", "kept", "dropped"], [[target["variant"], target["D"], target["K_val"], target["full_classification"], target["classification"], [(p["K_var"], p["frontier"]) for p in target["kept_points"]], [(p["K_var"], p["frontier"]) for p in target["dropped_points"]]]]))
    lines.extend([
        "",
        "Decision: the bound_single D=1024 K_val=2 group is theory-consistent after dropping ceiling-bound K_var=9 and K_var=20. The earlier open flag was confounded by finite variable count at low K.",
        "",
        "### 011. Ran fixed-depth Module 1 K-direction diagnostic benchmark",
        "",
        "Purpose: test whether the K-direction issue is caused by variable depth grids or by joint `(var,val)` aggregation. This run uses a fixed depth grid and reports joint, var-only, and val-only frontiers separately.",
        "",
        "Code added/used:",
        "",
        "- `experiments/module1_capacity_diagnostic.py`",
        "- `analysis/merge_diagnostic_shards.py`",
        "",
        "Command:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm && for i in 0 1 2 3 4 5 6 7; do CUDA_VISIBLE_DEVICES=$i ~/.local/bin/uv run --python .venv/bin/python python -u -m experiments.module1_capacity_diagnostic --mode full --device cuda:0 --num-shards 8 --shard-index $i --batch-size 8192 --trials 4096 --output-dir results/module1_capacity_diagnostic_full_shards/shard_$i & done; wait; ~/.local/bin/uv run --python .venv/bin/python python -m analysis.merge_diagnostic_shards --input-dir results/module1_capacity_diagnostic_full_shards",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/module1_capacity_diagnostic_full_shards/results.json`",
        "- `results/module1_capacity_diagnostic_full_shards/curves.json`",
        "- `results/module1_capacity_diagnostic_full_shards/shard_*/results.json`",
        "- `results/module1_capacity_diagnostic_full_shards/shard_*/run.log`",
        "",
        "K-direction diagnostic:",
        "",
    ])
    lines.extend(_table(["variant", "metric", "D", "K_val", "K_vars", "frontiers", "signs"], [[item["variant"], item["metric"], item["D"], item["K_val"], item["K_vars"], item["frontiers"], item["signs"]] for item in data["module1_capacity_diagnostic_full_shards"]["directions"]]))
    lines.extend([
        "",
        f"- decision: `{data['module1_capacity_diagnostic_full_shards']['decision']}`",
        f"- open: {data['module1_capacity_diagnostic_full_shards']['open']}",
        "",
        "Decision: fixed-depth diagnostic still records K-direction as open/inverted. Important caveat: small `K_var` values cap possible depth because vars are sampled without replacement, so low-K frontiers are partly ceiling-limited. This strengthens the conclusion that no d* claim should be made yet from frontier buckets alone; the next per-depth benchmark resolves this directly.",
        "",
        "### 011. Ran ceiling-free per-depth Module 1 capacity benchmark",
        "",
        "Purpose: remove the K_var ceiling and coarse frontier-bucket artifacts by measuring accuracy at every fixed depth, with both without-replacement and with-replacement var sampling. This is the clean K-direction and K_eff fit test.",
        "",
        "Code added/used:",
        "",
        "- `experiments/module1_capacity_perdepth.py`",
        "- `analysis/merge_perdepth_shards.py`",
        "- `analysis/capacity_theory.py`",
        "",
        "Command:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm && for i in 0 1 2 3 4 5 6 7; do CUDA_VISIBLE_DEVICES=$i ~/.local/bin/uv run --python .venv/bin/python python -u -m experiments.module1_capacity_perdepth --mode full --device cuda:0 --num-shards 8 --shard-index $i --batch-size 8192 --trials 4096 --output-dir results/module1_capacity_perdepth_shards/shard_$i & done; wait; ~/.local/bin/uv run --python .venv/bin/python python -m analysis.merge_perdepth_shards --input-dir results/module1_capacity_perdepth_shards",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/module1_capacity_perdepth_shards/results.json`",
        "- `results/module1_capacity_perdepth_shards/curves.json`",
        "- `results/module1_capacity_perdepth_shards/shard_*/results.json`",
        "- `results/module1_capacity_perdepth_shards/shard_*/run.log`",
        "",
        "Per-depth K-direction:",
        "",
    ])
    lines.extend(_table(["variant", "replacement", "metric", "D", "K_val", "K_vars", "capacities", "signs"], [[item["variant"], item["replacement"], item["metric"], item["D"], item["K_val"], item["K_vars"], item["capacities"], item["signs"]] for item in data["module1_capacity_perdepth_shards"]["directions"]]))
    lines.extend(["", "K_eff fits:", ""])
    lines.extend(_table(["variant", "replacement", "metric", "best_k_eff", "n_points", "r2_product", "r2_Kvar", "r2_max_factor"], [[fit["variant"], fit["replacement"], fit["metric"], fit["best_k_eff"], fit["n_points"], fit["fits"].get("D_over_ln_product", {}).get("r2"), fit["fits"].get("D_over_ln_Kvar", {}).get("r2"), fit["fits"].get("halfD_over_ln_max_factor", {}).get("r2")] for fit in data["module1_capacity_perdepth_shards"]["fits"]]))
    lines.extend([
        "",
        f"- decision: `{data['module1_capacity_perdepth_shards']['decision']}`",
        f"- open: {data['module1_capacity_perdepth_shards']['open']}",
        "",
        "Decision: per-depth benchmark resolves the K-direction for the measured construction. With- and without-replacement agree: capacity is non-increasing in K on ceiling-free points. Bound-single is best fit by product codebook size, while factored is best fit by K_var / max-factor scaling. This upgrades the safe claim to linear in D and decreasing in effective codebook size, with a fitted constant rather than the raw D/(2 ln K) constant.",
        "",
        "### 012. Implemented tuned GRUStack smoke with val-selected checkpoint",
        "",
        "Purpose: start the clean labeled negative baseline required for Module 1 closeout. This smoke verifies the GRUStack interface, val-loss checkpoint selection, convergence metadata, and per-depth eval curve before launching the full GRU grid.",
        "",
        "Code added:",
        "",
        "- `register/gru_stack.py`",
        "- `experiments/train_gru_stack.py`",
        "",
        "Command:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm && ~/.local/bin/uv run --python .venv/bin/python python -m experiments.train_gru_stack --D 128 --K-var 60 --K-val 2 --replacement without_replacement --max-depth 8 --steps 80 --batch-size 512 --eval-every 20 --patience 3 --device cuda:0 --output-dir results/gru_stack_smoke",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/gru_stack_smoke/results.json`",
        "- `results/gru_stack_smoke/gru_stack_best.pt`",
        "",
        "Smoke result:",
        "",
        f"- converged: {data['module1_gru_smoke']['converged']}",
        f"- selection: `{data['module1_gru_smoke']['selection']}`",
        f"- frontier_joint_095: {data['module1_gru_smoke']['frontier_joint_095']}",
        f"- best_config: `{data['module1_gru_smoke']['best_config']}`",
        "",
        "Decision: GRU smoke interface pass. This is not yet the closeout GRU grid; the full tuned GRU per-depth grid still needs to run before the GRU negative headline is final.",
        "",
        "### 013. Ran tuned GRUStack full grid and structured comparison",
        "",
        "Purpose: complete the clean labeled negative baseline. This full grid trains GRUStack cells with val-selected checkpoints and compares each matched D/K/replacement cell against the best structured register capacity from the per-depth benchmark.",
        "",
        "Code added/used:",
        "",
        "- `register/gru_stack.py`",
        "- `experiments/train_gru_stack.py`",
        "- `experiments/train_gru_stack_grid.py`",
        "- `analysis/merge_gru_grid.py`",
        "",
        "Command:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm && for i in 0 1 2 3 4 5 6 7; do CUDA_VISIBLE_DEVICES=$i ~/.local/bin/uv run --python .venv/bin/python python -u -m experiments.train_gru_stack_grid --mode full --device cuda:0 --num-shards 8 --shard-index $i --max-depth 32 --steps 600 --batch-size 1024 --eval-every 50 --patience 6 --output-dir results/gru_stack_grid_full/shard_$i & done; wait; ~/.local/bin/uv run --python .venv/bin/python python -m analysis.merge_gru_grid",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/gru_stack_grid_full/results.json`",
        "- `results/gru_stack_grid_full/curves.json`",
        "- `results/gru_stack_grid_full/shard_*/cell_*/results.json`",
        "- `results/gru_stack_grid_full/shard_*/cell_*/gru_stack_best.pt`",
        "",
        "Result summary:",
        "",
        f"- cells: {data['module1_gru_grid_full']['n_cells']}",
        f"- summary rows: {len(data['module1_gru_grid_full']['summary'])}",
        f"- all_converged: {data['module1_gru_grid_full']['all_converged']}",
        f"- all_gru_below_structured: {data['module1_gru_grid_full']['all_gru_below_structured']}",
        "",
        "Decision: tuned GRU negative baseline passes closeout checks. At every matched D/K/replacement cell, val-selected GRU capacity is below the best structured register capacity.",
        "",
        "### 014. Ran scaffold gates and centralized validation",
        "",
        "Purpose: keep the older scaffold gates auditable while the build pivots toward the three-module design. Validation records whether required files, schemas, and comparison checks pass.",
        "",
        "Commands:",
        "",
        "```bash",
        "cd /home/aiscuser/stage_d_llm",
        "python -m experiments.two_by_two_falsification",
        "python -m experiments.d_stage_0_propagation",
        "python -m experiments.d_stage_1_depth1_gate",
        "python -m experiments.d_stage_2_capacity",
        "python -m experiments.d_stage_3_vs_cot",
        "python -m experiments.verifier_verification",
        "python -m experiments.ttt_reversibility",
        "python -m analysis.validate_outputs",
        "python -m analysis.experiment_log",
        "```",
        "",
        "Artifacts:",
        "",
        "- `results/two_by_two/results.json`",
        "- `results/d_stage_0/results.json`",
        "- `results/d_stage_1/results.json`",
        "- `results/d_stage_2/results.json`",
        "- `results/d_stage_3/results.json`",
        "- `results/verifier/results.json`",
        "- `results/ttt/results.json`",
        "- `results/validation/validation.md`",
        "- `results/experiment_log/experiment_log.md`",
        "",
        "Validation summary:",
        "",
        f"- checks: {len(data['validation']['checks'])}",
        f"- passed: {data['validation']['passed']}",
        "",
        "Decision: centralized validation pass. Continue using this log as the top-level experiment ledger, but treat scaffold gates as legacy/supporting evidence rather than the new Module 1 core claim.",
        "",
    ])
    return lines


def _markdown(data: dict[str, Any], artifacts: dict[str, str]) -> str:
    lines: list[str] = [
        "# Stage D Experiment Log",
        "",
        f"Generated at: {artifacts['generated_at']}",
        "",
        "Scope: consolidated log for oracle-trace scaffold outputs. These are not trained-model evaluations.",
        "",
        "## Artifact Index",
        "",
    ]
    lines.extend(_table(["artifact", "path"], [[name, path] for name, path in RESULT_FILES.items()]))
    lines.extend([
        "",
        "## Run Metadata",
        "",
        f"- Evaluation mode: `{data['two_by_two'][0].get('evaluation_mode', 'unknown')}`",
        f"- Oracle dataset supervision: `{data['oracle_dataset']['supervision']}`",
        f"- Oracle dataset tasks: {data['oracle_dataset']['n_tasks']}",
        f"- Oracle dataset examples: {data['oracle_dataset']['n_examples']}",
        f"- Max oracle backtrack depth in dataset: {data['oracle_dataset']['max_backtrack_depth']}",
        f"- Operator cache feature source: `{data['operator_cache']['feature_source']}`",
        f"- Transformers available for Qwen cache: {data['model_readiness']['transformers_available']}",
        f"- CUDA available for Qwen cache: {data['model_readiness']['cuda_available']}",
        f"- Qwen Instruct snapshot: `{data['qwen_instruct_download']['snapshot_path']}`",
        f"- Qwen Thinking snapshot: `{data['qwen_thinking_download']['snapshot_path']}`",
        f"- Qwen probe hidden dim: {data['qwen_probe_cache']['hidden_dim']}",
        f"- Qwen-128 learned wiring action accuracy: {data['learned_wiring_qwen_128']['action_accuracy']:.4f}",
        f"- Qwen-128 learned wiring verifier accuracy: {data['learned_wiring_qwen_128']['verifier_accuracy']:.4f}",
        f"- Qwen balanced-320 holdout action accuracy: {data['learned_wiring_qwen_balanced_320']['holdout_action_accuracy']:.4f}",
        f"- Qwen balanced-320 holdout verifier accuracy: {data['learned_wiring_qwen_balanced_320']['holdout_verifier_accuracy']:.4f}",
        f"- Module 1 stack capacity mode: `{data['module1_stack_capacity']['mode']}`",
        f"- Module 1 full stack capacity device: `{data['module1_stack_capacity_full'].get('device')}`",
        f"- Module 1 per-depth K-direction: `{data['module1_capacity_perdepth_shards']['decision']}`",
        f"- Module 1 per-depth open flag: {data['module1_capacity_perdepth_shards']['open']}",
        f"- Module 1 bound-single K_eff: `{next(fit['best_k_eff'] for fit in data['module1_capacity_perdepth_shards']['fits'] if fit['variant'] == 'bound_single' and fit['replacement'] == 'with_replacement' and fit['metric'] == 'joint')}`",
        f"- Module 1 factored K_eff: `{next(fit['best_k_eff'] for fit in data['module1_capacity_perdepth_shards']['fits'] if fit['variant'] == 'factored' and fit['replacement'] == 'with_replacement' and fit['metric'] == 'joint')}`",
        f"- Learned wiring train action accuracy: {data['learned_wiring']['train_action_accuracy']:.4f}",
        f"- Learned wiring holdout action accuracy: {data['learned_wiring']['holdout_action_accuracy']:.4f}",
        f"- Learned wiring train verifier accuracy: {data['learned_wiring']['train_verifier_accuracy']:.4f}",
        f"- Learned wiring holdout verifier accuracy: {data['learned_wiring']['holdout_verifier_accuracy']:.4f}",
        f"- Validation passed: {data['validation']['passed']}",
        "",
        "## Gate Status",
        "",
    ])
    lines.extend(_table(
        ["gate", "status", "criterion"],
        [
            ["D.3 2x2 falsification", _two_by_two_status(data["two_by_two"]), "register helps backtracking only"],
            ["D-stage 1 depth-1", _depth1_status(data["d_stage_1"]), "structured has reverts and ablations collapse"],
            ["D.5 verifier", _verifier_status(data["verifier"]), "oracle >= learned >= noisy >= disabled"],
            ["D.6 TTT diagnostic", _ttt_status(data["ttt"]), "TTT restore error > structured restore error"],
        ],
    ))
    lines.extend(["", "## Incremental Run Items", ""])
    lines.extend(_table(["item", "name", "what changed", "artifact", "key result"], _incremental_items(data)))
    lines.extend(_core_sweep_numeric_summaries(data))
    lines.extend(_detailed_run_items(data))
    lines.extend([
        "",
        "## Reference Archive",
        "",
        "Static/reference tables are kept out of the main review path. See `results/experiment_log/reference.md` for preregistration bands, dataset summaries, legacy scaffold tables, model download metadata, and validation details.",
        "",
    ])
    return "\n".join(lines)


def _reference_markdown(data: dict[str, Any], generated_at: str) -> str:
    lines: list[str] = [
        "# Stage D Reference Archive",
        "",
        f"Generated at: {generated_at}",
        "",
        "This file holds stable/reference tables that are useful for audit but noisy during incremental review. The main log is `results/experiment_log/experiment_log.md`.",
    ]
    lines.extend(["", "## Preregistration Bands", ""])
    lines.extend(_table(["label", "D", "K", "predicted d*_dyn"], [[row["label"], row["D"], row["K"], row["predicted_d_star"]] for row in data["preregistration"]["bands"]]))
    lines.extend(["", "## Oracle Dataset", ""])
    lines.extend(_table(["task type", "tasks", "examples"], [[name, row["tasks"], row["examples"]] for name, row in data["oracle_dataset"]["task_types"].items()]))
    lines.extend(["", "## Operator Cache", ""])
    lines.extend(_table(["feature_source", "hidden_dim", "n_examples", "cache"], [[data["operator_cache"]["feature_source"], data["operator_cache"]["hidden_dim"], data["operator_cache"]["n_examples"], data["operator_cache"]["cache"]]]))
    lines.extend(["", "## Model Readiness", ""])
    lines.extend(_table(["field", "value"], [["transformers_available", data["model_readiness"]["transformers_available"]], ["cuda_available", data["model_readiness"]["cuda_available"]], ["cuda_device_count", data["model_readiness"]["cuda_device_count"]], ["recommended_cache_command", data["model_readiness"]["recommended_cache_command"]]]))
    lines.extend(["", "## Model Downloads", ""])
    lines.extend(_table(["model", "snapshot_path", "n_files", "total_gib"], [[data["qwen_instruct_download"]["model_id"], data["qwen_instruct_download"]["snapshot_path"], data["qwen_instruct_download"]["n_files"], data["qwen_instruct_download"]["total_gib"]], [data["qwen_thinking_download"]["model_id"], data["qwen_thinking_download"]["snapshot_path"], data["qwen_thinking_download"]["n_files"], data["qwen_thinking_download"]["total_gib"]]]))
    lines.extend(["", "## Qwen Probe Cache", ""])
    lines.extend(_table(["feature_source", "hidden_dim", "n_examples", "cache"], [[data["qwen_probe_cache"]["feature_source"], data["qwen_probe_cache"]["hidden_dim"], data["qwen_probe_cache"]["n_examples"], data["qwen_probe_cache"]["cache"]]]))
    lines.extend(["", "## Qwen 128 Cache", ""])
    lines.extend(_table(["feature_source", "hidden_dim", "n_examples", "cache"], [[data["qwen_128_cache"]["feature_source"], data["qwen_128_cache"]["hidden_dim"], data["qwen_128_cache"]["n_examples"], data["qwen_128_cache"]["cache"]]]))
    lines.extend(["", "## Qwen 128 Learned Wiring Smoke Test", ""])
    lines.extend(_table(["metric", "value"], [["action_accuracy", data["learned_wiring_qwen_128"]["action_accuracy"]], ["var_accuracy", data["learned_wiring_qwen_128"]["var_accuracy"]], ["val_accuracy", data["learned_wiring_qwen_128"]["val_accuracy"]], ["verifier_accuracy", data["learned_wiring_qwen_128"]["verifier_accuracy"]], ["n_examples", data["learned_wiring_qwen_128"]["n_examples"]], ["feature_source", data["learned_wiring_qwen_128"]["feature_source"]]]))
    lines.extend(["", "## Qwen Balanced 320 Cache", ""])
    lines.extend(_table(["feature_source", "hidden_dim", "n_examples", "seed_counts", "cache"], [[data["qwen_balanced_320_cache"]["feature_source"], data["qwen_balanced_320_cache"]["hidden_dim"], data["qwen_balanced_320_cache"]["n_examples"], data["qwen_balanced_320_cache"]["seed_counts"], data["qwen_balanced_320_cache"]["cache"]]]))
    lines.extend(["", "## Qwen Balanced 320 Learned Wiring", ""])
    lines.extend(_table(["metric", "value"], [["train_action_accuracy", data["learned_wiring_qwen_balanced_320"]["train_action_accuracy"]], ["holdout_action_accuracy", data["learned_wiring_qwen_balanced_320"]["holdout_action_accuracy"]], ["train_var_accuracy", data["learned_wiring_qwen_balanced_320"]["train_var_accuracy"]], ["holdout_var_accuracy", data["learned_wiring_qwen_balanced_320"]["holdout_var_accuracy"]], ["train_val_accuracy", data["learned_wiring_qwen_balanced_320"]["train_val_accuracy"]], ["holdout_val_accuracy", data["learned_wiring_qwen_balanced_320"]["holdout_val_accuracy"]], ["train_verifier_accuracy", data["learned_wiring_qwen_balanced_320"]["train_verifier_accuracy"]], ["holdout_verifier_accuracy", data["learned_wiring_qwen_balanced_320"]["holdout_verifier_accuracy"]], ["n_train_examples", data["learned_wiring_qwen_balanced_320"]["n_train_examples"]], ["n_holdout_examples", data["learned_wiring_qwen_balanced_320"]["n_holdout_examples"]], ["holdout_seed", data["learned_wiring_qwen_balanced_320"]["holdout_seed"]]]))
    lines.extend(["", "## Module 1 Stack Capacity Quick", ""])
    module1_rows = [[row["method"], row["D"], row["K"], row["predicted_d_star"], row["frontier_decode_095"]] for row in data["module1_stack_capacity"]["summary"]]
    lines.extend(_table(["method", "D", "K", "predicted_d_star", "frontier_decode_095"], module1_rows))
    lines.extend(["", "## Module 1 Stack Capacity Full GPU", ""])
    module1_full_rows = [[row["method"], row["D"], row["K"], row["predicted_d_star"], row["frontier_decode_095"]] for row in data["module1_stack_capacity_full"]["summary"]]
    lines.extend(_table(["method", "D", "K", "predicted_d_star", "frontier_decode_095"], module1_full_rows))
    lines.extend(["", f"Module 1 full notes: {data['module1_stack_capacity_full']['notes']}", ""])
    lines.extend(["", "## Learned Wiring Baseline", ""])
    lines.extend(_table(["metric", "value"], [["train_action_accuracy", data["learned_wiring"]["train_action_accuracy"]], ["holdout_action_accuracy", data["learned_wiring"]["holdout_action_accuracy"]], ["train_var_accuracy", data["learned_wiring"]["train_var_accuracy"]], ["holdout_var_accuracy", data["learned_wiring"]["holdout_var_accuracy"]], ["train_val_accuracy", data["learned_wiring"]["train_val_accuracy"]], ["holdout_val_accuracy", data["learned_wiring"]["holdout_val_accuracy"]], ["train_verifier_accuracy", data["learned_wiring"]["train_verifier_accuracy"]], ["holdout_verifier_accuracy", data["learned_wiring"]["holdout_verifier_accuracy"]], ["holdout_seed", data["learned_wiring"]["holdout_seed"]], ["feature_source", data["learned_wiring"]["feature_source"]]]))
    lines.extend(["", "## D.3 2x2 Falsification", ""])
    lines.extend(_table(["method", "column", "n_tasks", "solve_rate", "applied_reverts", "max_required_depth"], [[row["method"], row["column"], row["n_tasks"], row["solve_rate"], row["applied_reverts"], row["max_required_depth"]] for row in data["two_by_two"]]))
    lines.extend(["", "## D-stage 0 Propagation", ""])
    lines.extend(_table(["depth", "task_kind", "solve_rate"], [[row["depth"], row["task_kind"], row["solve_rate"]] for row in data["d_stage_0"]]))
    lines.extend(["", "## D-stage 1 Depth-1 Gate", ""])
    lines.extend(_table(["method", "n_tasks", "solve_rate", "applied_reverts", "max_required_depth"], [[row["method"], row["n_tasks"], row["solve_rate"], row["applied_reverts"], row["max_required_depth"]] for row in data["d_stage_1"]]))
    lines.extend(["", "## D-stage 2 Capacity Frontier", ""])
    lines.extend(_table(["register", "D", "K", "predicted_d_star", "observed_frontier"], _capacity_rows(data["d_stage_2"])))
    lines.extend(["", "## D-stage 3 Vs CoT", ""])
    lines.extend(_table(["D", "K", "method", "predicted_d_star", "last_solved_depth", "matched_compute"], _stage3_rows(data["d_stage_3"])))
    lines.extend(["", "## D.5 Verifier Verification", ""])
    lines.extend(_table(["mode", "n_tasks", "solve_rate", "false_positive_reverts", "false_negative_misses"], [[row["mode"], row["n_tasks"], row["solve_rate"], row["false_positive_reverts"], row["false_negative_misses"]] for row in data["verifier"]]))
    lines.extend(["", "## D.6 TTT Reversibility", ""])
    lines.extend(_table(["structured_restore_error", "ttt_restore_error", "ratio"], [[data["ttt"]["structured_restore_error"], data["ttt"]["ttt_restore_error"], data["ttt"]["ratio"]]]))
    lines.extend(["", "## Analysis Summary", "", data["analysis_summary"], ""])
    lines.extend(["", "## Validation Checks", ""])
    lines.extend(_table(["check", "status", "detail"], [[row["name"], row["status"], row["detail"]] for row in data["validation"]["checks"]]))
    return "\n".join(lines)


def generate_experiment_log(output_dir: str = "results/experiment_log") -> dict[str, str]:
    data = _load_results()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "markdown": str(out / "experiment_log.md"),
        "reference": str(out / "reference.md"),
        "json": str(out / "experiment_log.json"),
    }
    payload = {
        "generated_at": artifacts["generated_at"],
        "artifact_index": RESULT_FILES,
        "gate_status": {
            "two_by_two": _two_by_two_status(data["two_by_two"]),
            "d_stage_1": _depth1_status(data["d_stage_1"]),
            "verifier": _verifier_status(data["verifier"]),
            "ttt": _ttt_status(data["ttt"]),
            "validation": "PASS" if data["validation"]["passed"] else "FAIL",
        },
        "results": data,
    }
    Path(artifacts["markdown"]).write_text(_markdown(data, artifacts) + "\n", encoding="utf-8")
    Path(artifacts["reference"]).write_text(_reference_markdown(data, artifacts["generated_at"]) + "\n", encoding="utf-8")
    Path(artifacts["json"]).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifacts


if __name__ == "__main__":
    print(json.dumps(generate_experiment_log(), indent=2, sort_keys=True))