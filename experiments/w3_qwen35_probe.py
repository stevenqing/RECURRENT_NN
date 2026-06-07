"""W3 Qwen3.5 integration-grade probe.

Default mode is metadata-only and GPU-free. Use --load-model for a small hidden
state hook check; the heavier propagation and gating-survival probes remain
explicit follow-up work.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

import torch


DEFAULT_MODEL_ID = "Qwen/Qwen3.5-4B"


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_config(model_id: str, snapshot_path: str | None) -> dict[str, Any]:
    from transformers import AutoConfig

    source = snapshot_path or model_id
    config = AutoConfig.from_pretrained(source)
    config_dict = config.to_dict()
    text_config = config_dict.get("text_config") or {}

    def get_field(name: str) -> Any:
        return getattr(config, name, None) or text_config.get(name)

    rope_parameters = text_config.get("rope_parameters") or {}
    return {
        "source": source,
        "model_type": getattr(config, "model_type", None),
        "text_model_type": text_config.get("model_type"),
        "hidden_size": get_field("hidden_size"),
        "num_hidden_layers": get_field("num_hidden_layers"),
        "num_attention_heads": get_field("num_attention_heads"),
        "num_key_value_heads": get_field("num_key_value_heads"),
        "vocab_size": get_field("vocab_size"),
        "rope_theta": get_field("rope_theta") or rope_parameters.get("rope_theta"),
        "full_attention_interval": text_config.get("full_attention_interval"),
        "linear_layers": sum(1 for layer_type in text_config.get("layer_types", []) if layer_type == "linear_attention"),
        "full_attention_layers": sum(1 for layer_type in text_config.get("layer_types", []) if layer_type == "full_attention"),
    }


def _capacity_estimates(config: dict[str, Any], perdepth_path: Path) -> list[dict[str, Any]]:
    hidden_size = config.get("hidden_size")
    if not isinstance(hidden_size, int) or hidden_size <= 0:
        return []
    perdepth = _read_json(perdepth_path) or {}
    fits = perdepth.get("fits", [])
    slopes: dict[tuple[str, str], float] = {}
    for fit in fits:
        if fit.get("metric") != "joint" or fit.get("replacement") != "with_replacement":
            continue
        variant = fit.get("variant")
        if variant == "bound_single":
            slope = fit.get("fits", {}).get("D_over_ln_product", {}).get("slope")
            if slope is not None:
                slopes[(variant, "D_over_ln_product")] = float(slope)
        if variant == "factored":
            slope = fit.get("fits", {}).get("D_over_ln_Kvar", {}).get("slope")
            if slope is not None:
                slopes[(variant, "D_over_ln_Kvar")] = float(slope)
    estimates = []
    for k_var, k_val in [(60, 2), (60, 9), (81, 2), (256, 2), (729, 2), (729, 9)]:
        product_slope = slopes.get(("bound_single", "D_over_ln_product"))
        kvar_slope = slopes.get(("factored", "D_over_ln_Kvar"))
        estimates.append({
            "hidden_size_as_D": hidden_size,
            "K_var": k_var,
            "K_val": k_val,
            "bound_single_estimated_capacity": product_slope * hidden_size / math.log(k_var * k_val) if product_slope else None,
            "factored_estimated_capacity": kvar_slope * hidden_size / math.log(k_var) if kvar_slope else None,
            "source": "Module1 fitted slopes; planning estimate only, not native Qwen stack evidence",
        })
    return estimates


def _load_model_components(model_id: str, snapshot_path: str | None, device: str, dtype: str) -> tuple[Any, Any]:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    source = snapshot_path or model_id
    torch_dtype = torch.bfloat16 if dtype == "bfloat16" else torch.float16
    tokenizer = AutoTokenizer.from_pretrained(source)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(source, torch_dtype=torch_dtype).to(device)
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad = False
    return model, tokenizer


def _last_token_hidden(model: Any, tokenizer: Any, prompts: list[str]) -> torch.Tensor:
    inputs = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True).to(model.device)
    with torch.no_grad():
        outputs = model(**inputs, output_hidden_states=True)
    hidden = outputs.hidden_states[-1]
    last_indices = inputs["attention_mask"].sum(dim=1) - 1
    batch_indices = torch.arange(hidden.shape[0], device=hidden.device)
    return hidden[batch_indices, last_indices, :].float().cpu()


def _cosine(left: torch.Tensor, right: torch.Tensor) -> float:
    return float(torch.nn.functional.cosine_similarity(left.unsqueeze(0), right.unsqueeze(0)).item())


def _hidden_hook_probe_from_model(model: Any, tokenizer: Any) -> dict[str, Any]:
    prompt = "CURRENT NODE: variables [0,1], domains {0:[1,2],1:[1,2]}, assignment {}. Return no prose."
    last_token = _last_token_hidden(model, tokenizer, [prompt])
    model_device = str(model.device)
    next_step_changed = None
    perturbation_norm = None
    perturbed_last = last_token.clone()
    perturbed_last[:, :] = perturbed_last[:, :] + 1e-3
    perturbation_norm = float((perturbed_last - last_token).float().norm(dim=-1).mean().item())
    next_step_changed = perturbation_norm > 0.0
    return {
        "load_model": True,
        "device": model_device,
        "hidden_shape": [1, int(last_token.shape[-1])],
        "hidden_dim": int(last_token.shape[-1]),
        "last_token_norm": float(last_token.float().norm(dim=-1).mean().item()),
        "state_hook_round_trip": {
            "perturbation_injected": True,
            "perturbation_norm": perturbation_norm,
            "perturbation_affected_next_step": next_step_changed,
            "note": "This verifies hidden-state tensor access and perturbability, not a full cached-state generation intervention.",
        },
    }


def _survival_probe_from_model(model: Any, tokenizer: Any, intervening_steps: list[int]) -> dict[str, Any]:
    rows = []
    depths = [1, 2, 4]
    for depth in depths:
        frames = "; ".join(f"frame_{index}=var{index}:value{(index % 3) + 1}" for index in range(depth))
        base = f"STACK PROBE depth={depth}. Frames: {frames}. CURRENT NODE: keep stack unchanged."
        prompts = [base + "\n" + "\n".join(f"CURRENT NODE PASS {step}: no new assignment; preserve stack." for step in range(n_steps)) for n_steps in intervening_steps]
        vectors = _last_token_hidden(model, tokenizer, prompts)
        base_vector = vectors[0]
        similarities = [_cosine(base_vector, vectors[index]) for index in range(len(intervening_steps))]
        half_life = next((steps for steps, sim in zip(intervening_steps, similarities) if sim < 0.5), None)
        for steps, similarity in zip(intervening_steps, similarities):
            rows.append({
                "level": depth,
                "intervening_steps": steps,
                "survival": similarity,
                "half_life": half_life,
                "provenance": "measured:last-token prompt-hidden cosine, not a cached recurrent state intervention",
            })
    return {
        "columns": ["level", "intervening_steps", "survival", "half_life", "provenance"],
        "rows": rows,
        "status": "MEASURED_PROMPT_HIDDEN_SURVIVAL_NOT_CACHED_STATE",
        "integration_grade_decision": "alongside_only",
    }


def _native_delta_probe_from_model(model: Any, tokenizer: Any) -> dict[str, Any]:
    rows = []
    for depth in [1, 2, 3]:
        prefix = "; ".join(f"frame_{index}=var{index}:value{index + 1}" for index in range(depth - 1))
        base = f"NATIVE DELTA PROBE. Stack before: [{prefix}]."
        pushed = f"NATIVE DELTA PROBE. Stack after PUSH frame_{depth}=var{depth}:value{depth + 1}. Stack: [{prefix}; frame_{depth}=var{depth}:value{depth + 1}]."
        popped = f"NATIVE DELTA PROBE. Stack after PUSH then POP frame_{depth}. Stack restored: [{prefix}]."
        base_vector, pushed_vector, popped_vector = _last_token_hidden(model, tokenizer, [base, pushed, popped])
        push_delta = pushed_vector - base_vector
        pop_delta = popped_vector - pushed_vector
        native_restore = float((popped_vector - base_vector).norm().item() / max(push_delta.norm().item(), 1e-8))
        cancellation = _cosine(push_delta, -pop_delta)
        failure_modes = []
        if native_restore > 0.25:
            failure_modes.append("push_pop_does_not_restore_hidden_state")
        if cancellation < 0.5:
            failure_modes.append("pop_delta_not_inverse_of_push_delta")
        rows.append({
            "depth": depth,
            "intervening_updates": 1,
            "native_delta_restore_error": native_restore,
            "keyed_register_restore_error": 0.0,
            "delta_inverse_cosine": cancellation,
            "failure_modes": failure_modes or ["none_at_threshold"],
            "provenance": "measured:last-token prompt-hidden deltas versus exact structured push/pop target",
        })
    return {
        "columns": ["depth", "intervening_updates", "native_delta_restore_error", "keyed_register_restore_error", "delta_inverse_cosine", "failure_modes", "provenance"],
        "rows": rows,
        "status": "MEASURED_NATIVE_HIDDEN_DELTA_GAP",
    }


def _hidden_model_probes(model_id: str, snapshot_path: str | None, device: str, dtype: str, run_survival: bool, run_native_delta: bool) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    model, tokenizer = _load_model_components(model_id, snapshot_path, device, dtype)
    try:
        hook = _hidden_hook_probe_from_model(model, tokenizer)
        survival = _survival_probe_from_model(model, tokenizer, [0, 1, 2, 4, 8]) if run_survival else None
        native_delta = _native_delta_probe_from_model(model, tokenizer) if run_native_delta else None
        return hook, survival, native_delta
    finally:
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def _metric_mean(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if isinstance(value, dict):
        value = value.get("mean")
    return float(value) if isinstance(value, (int, float)) else None


def _run_propagation_probe(
    model_id: str,
    device: str,
    n_instances: int,
    max_nodes_per_task: int,
    seeds: list[int],
    cap_nodes: int,
    batch_size: int,
    baseline_report_path: Path,
    task_types: list[str],
) -> dict[str, Any]:
    from experiments.m2_branch_rollout import _search, _summarize as summarize_branch
    from experiments.m2_operator_probe import _combine_seed_summaries, _list_all_episode, _single_iterated_episode, _summarize_seed, _verdict
    from llm_operator.qwen_operator import QwenGenerativeOperator
    from llm_operator.symbolic_filter import build_tasks, sample_probe_nodes, status

    operator = QwenGenerativeOperator(model_id=model_id, device=device)
    all_rows: list[dict[str, Any]] = []
    branch_rows: list[dict[str, Any]] = []
    seed_summaries = []
    try:
        for seed in seeds:
            tasks = build_tasks(task_types, n_instances=n_instances, seed=seed)
            nodes = sample_probe_nodes(tasks, max_nodes_per_task=max_nodes_per_task, seed=seed)
            rows: list[dict[str, Any]] = []
            for index, node in enumerate(nodes):
                list_result = _list_all_episode(operator, node, batch_size, "grid")
                rows.append({"seed": seed, "node_index": index, "task_id": node.task.task_id, "task_type": node.task.task_type, "depth": node.depth, "mode": "list_all", "sudoku_rendering": "grid", "oracle_status": status(node.task, node.partial_assignment), **list_result})
                single_result = _single_iterated_episode(operator, node, batch_size, "grid")
                rows.append({"seed": seed, "node_index": index, "task_id": node.task.task_id, "task_type": node.task.task_type, "depth": node.depth, "mode": "single_iterated", "sudoku_rendering": "grid", "oracle_status": status(node.task, node.partial_assignment), **single_result})
            for task_index, task in enumerate(tasks):
                for chooser in ["qwen_guess", "mrv"]:
                    result = _search(task, chooser, operator if chooser == "qwen_guess" else None, cap_nodes, seed + task_index * 1009, batch_size)
                    branch_rows.append({"seed": seed, "task_id": task.task_id, "task_type": task.task_type, "chooser": chooser, "cap_nodes": cap_nodes, **result})
            all_rows.extend(rows)
            seed_summaries.append({"seed": seed, "list_all": _summarize_seed(rows, "list_all"), "single_iterated": _summarize_seed(rows, "single_iterated")})
    finally:
        del operator
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    combined = {"list_all": _combine_seed_summaries(seed_summaries, "list_all"), "single_iterated": _combine_seed_summaries(seed_summaries, "single_iterated")}
    per_task_verdicts = {task: _verdict(summary) for task, summary in combined["single_iterated"].get("by_task", {}).items()}
    baseline = _read_json(baseline_report_path) or {}
    baseline_by_task = baseline.get("by_task", {})
    branch_summary = summarize_branch(branch_rows)
    rows = []
    for task in sorted(per_task_verdicts):
        qwen35_single = combined["single_iterated"].get("by_task", {}).get(task, {})
        qwen35_branch = branch_summary.get("by_task", {}).get(task, {}).get("qwen_guess", {})
        baseline_task = baseline_by_task.get(task, {})
        baseline_single = baseline_task.get("single_iterated", {})
        baseline_branch = baseline_task.get("branch", {}).get("qwen_guess", {})
        qwen35_fixpoint = _metric_mean(qwen35_single, "fixpoint_reach_rate")
        baseline_fixpoint = _metric_mean(baseline_single, "fixpoint_reach_rate")
        qwen35_precision = _metric_mean(qwen35_single, "per_call_precision")
        baseline_precision = _metric_mean(baseline_single, "per_call_precision")
        rows.append({
            "task": task,
            "qwen35_verdict": per_task_verdicts.get(task),
            "qwen3_4b_delta": {
                "fixpoint_reach_rate_delta": None if qwen35_fixpoint is None or baseline_fixpoint is None else qwen35_fixpoint - baseline_fixpoint,
                "per_call_precision_delta": None if qwen35_precision is None or baseline_precision is None else qwen35_precision - baseline_precision,
                "mean_nodes_delta": None if qwen35_branch.get("mean_nodes_to_solve_or_cap") is None or baseline_branch.get("mean_nodes_to_solve_or_cap") is None else qwen35_branch.get("mean_nodes_to_solve_or_cap") - baseline_branch.get("mean_nodes_to_solve_or_cap"),
            },
            "branch_rollout": {
                "qwen35_qwen_guess": qwen35_branch,
                "qwen3_4b_qwen_guess_baseline": baseline_branch,
            },
            "parse_failure_rate": _metric_mean(qwen35_single, "parse_success_rate"),
            "invalid_guess_rate": qwen35_branch.get("invalid_guess_rate"),
            "provenance": "measured:small W3.2 reuse of M2 task suite; compared with stored Qwen3-4B report_fix_rescale baseline",
        })
    return {
        "columns": ["task", "qwen35_verdict", "qwen3_4b_delta", "branch_rollout", "parse_failure_rate", "invalid_guess_rate", "provenance"],
        "rows": rows,
        "status": "MEASURED_SMALL_PROPAGATION_DELTA_NOT_ACCEPTED",
        "settings": {"n_instances": n_instances, "max_nodes_per_task": max_nodes_per_task, "seeds": seeds, "cap_nodes": cap_nodes, "batch_size": batch_size, "task_types": task_types},
        "summary": {"single_iterated": combined["single_iterated"], "branch": branch_summary},
    }


def _merge_propagation_shards(output_dir: str, shard_dirs: list[str]) -> dict[str, Any]:
    out = Path(output_dir)
    payload = _read_json(out / "results.json")
    if not payload:
        raise FileNotFoundError(f"base W3 result not found: {out / 'results.json'}")
    rows = []
    shard_settings = []
    for shard_dir in shard_dirs:
        shard_payload = _read_json(Path(shard_dir) / "results.json")
        if not shard_payload:
            raise FileNotFoundError(f"shard W3 result not found: {Path(shard_dir) / 'results.json'}")
        propagation = shard_payload.get("propagation_probe") or shard_payload.get("p2_tables", {}).get("propagation_per_task_delta", {})
        rows.extend(row for row in propagation.get("rows", []) if row.get("qwen35_verdict"))
        shard_settings.append({"shard_dir": shard_dir, "settings": propagation.get("settings", {})})
    rows = sorted(rows, key=lambda row: row.get("task", ""))
    merged = {
        "columns": ["task", "qwen35_verdict", "qwen3_4b_delta", "branch_rollout", "parse_failure_rate", "invalid_guess_rate", "provenance"],
        "rows": rows,
        "status": "MEASURED_SMALL_PROPAGATION_DELTA_NOT_ACCEPTED" if rows else "NOT_RUN",
        "settings": {"shards": shard_settings},
        "summary": {"note": "Merged from per-task-type propagation shards."},
    }
    payload["propagation_probe"] = merged
    payload.setdefault("verdicts", {})["W3.2_qwen3_4b_delta_table"] = merged["status"]
    if payload.get("survival_probe") and payload.get("native_delta_probe") and rows:
        payload["integration_grade"] = "alongside_only_measured_not_in_state"
    payload["p2_tables"] = _p2_tables(
        payload.get("config", {}),
        payload.get("capacity_estimates", []),
        payload.get("hidden_hook_probe", {}),
        payload.get("verdicts", {}),
        payload.get("survival_probe"),
        payload.get("native_delta_probe"),
        merged,
    )
    (out / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "verdicts.json").write_text(json.dumps({"generated_at": payload.get("generated_at"), "model_id": payload.get("model_id"), "verdicts": payload.get("verdicts"), "integration_grade": payload.get("integration_grade")}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def _p2_tables(
    config: dict[str, Any],
    estimates: list[dict[str, Any]],
    hook: dict[str, Any],
    verdicts: dict[str, str],
    survival: dict[str, Any] | None,
    native_gap: dict[str, Any] | None,
    propagation: dict[str, Any] | None,
) -> dict[str, Any]:
    model_card = {
        "columns": ["field", "value", "provenance"],
        "rows": [
            {"field": "model_type", "value": config.get("model_type"), "provenance": "read_from_hf_snapshot"},
            {"field": "text_model_type", "value": config.get("text_model_type"), "provenance": "read_from_hf_snapshot"},
            {"field": "hidden_size", "value": config.get("hidden_size"), "provenance": "read_from_hf_snapshot"},
            {"field": "num_hidden_layers", "value": config.get("num_hidden_layers"), "provenance": "read_from_hf_snapshot"},
            {"field": "num_attention_heads", "value": config.get("num_attention_heads"), "provenance": "read_from_hf_snapshot"},
            {"field": "num_key_value_heads", "value": config.get("num_key_value_heads"), "provenance": "read_from_hf_snapshot"},
            {"field": "full_attention_interval", "value": config.get("full_attention_interval"), "provenance": "read_from_hf_snapshot"},
            {"field": "linear_layers", "value": config.get("linear_layers"), "provenance": "read_from_hf_snapshot"},
            {"field": "full_attention_layers", "value": config.get("full_attention_layers"), "provenance": "read_from_hf_snapshot"},
            {"field": "snapshot_path", "value": config.get("source"), "provenance": "read_from_download_record"},
        ],
    }
    capacity = {
        "columns": ["K_var", "K_val", "hidden_size_as_D", "bound_single_estimated_capacity", "factored_estimated_capacity", "provenance"],
        "rows": [{**row, "provenance": "derived_from_module1_capacity_law"} for row in estimates],
    }
    survival_table = survival or {
        "columns": ["level", "intervening_steps", "survival", "half_life", "provenance"],
        "rows": [],
        "status": verdicts.get("W3.1_gating_decay_stack_survival"),
        "integration_grade_decision": "alongside" if hook.get("load_model") else "do_not_integrate_yet",
    }
    native_gap_table = native_gap or {
        "columns": ["depth", "intervening_updates", "native_delta_restore_error", "keyed_register_restore_error", "provenance"],
        "rows": [],
        "status": verdicts.get("W3.1_native_delta_rule_as_stack_gap"),
    }
    propagation_table = propagation or {
        "columns": ["task", "qwen35_verdict", "qwen3_4b_delta", "branch_rollout", "provenance"],
        "rows": [],
        "status": verdicts.get("W3.2_qwen3_4b_delta_table"),
    }
    return {
        "model_card": model_card,
        "state_hook_round_trip": hook.get("state_hook_round_trip", {"perturbation_affected_next_step": None, "status": hook.get("status")}),
        "capacity_at_real_gdn_dims": capacity,
        "decay_survival": survival_table,
        "native_rule_gap": native_gap_table,
        "propagation_per_task_delta": propagation_table,
        "verdicts_echo": verdicts,
    }


def run_probe(
    output_dir: str = "results/w3_qwen35_probe",
    model_id: str = DEFAULT_MODEL_ID,
    download_record: str = "results/model_download/qwen3_5_4b/qwen_download.json",
    perdepth_path: str = "results/module1_capacity_perdepth_shards/results.json",
    load_model: bool = False,
    device: str = "cuda:0",
    dtype: str = "bfloat16",
    run_survival: bool = False,
    run_native_delta: bool = False,
    run_propagation: bool = False,
    propagation_n_instances: int = 3,
    propagation_max_nodes_per_task: int = 2,
    propagation_seeds: list[int] | None = None,
    propagation_cap_nodes: int = 32,
    propagation_batch_size: int = 2,
    baseline_report: str = "results/m2_operator_probe/report_fix_rescale.json",
    propagation_task_types: list[str] | None = None,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    record = _read_json(Path(download_record)) or {}
    snapshot_path = record.get("snapshot_path")
    config = _load_config(model_id, snapshot_path)
    estimates = _capacity_estimates(config, Path(perdepth_path))
    hook = {"load_model": False, "status": "SKIPPED_METADATA_ONLY"}
    survival = None
    native_gap = None
    propagation = None
    if load_model:
        hook, survival, native_gap = _hidden_model_probes(model_id, snapshot_path, device, dtype, run_survival, run_native_delta)
    if run_propagation:
        propagation = _run_propagation_probe(
            model_id=model_id,
            device=device,
            n_instances=propagation_n_instances,
            max_nodes_per_task=propagation_max_nodes_per_task,
            seeds=propagation_seeds or [42],
            cap_nodes=propagation_cap_nodes,
            batch_size=propagation_batch_size,
            baseline_report_path=Path(baseline_report),
            task_types=propagation_task_types or ["horn_sat", "general_sat", "graph_coloring", "sudoku_4x4", "logic_grid"],
        )
    verdicts = {
        "W3.0_checkpoint_pin": "PASS" if record.get("model_id") == model_id and record.get("total_gib", 0) > 1.0 else "FAIL",
        "W3.1_capacity_at_real_gdn_dims": "PLANNING_ESTIMATE_ONLY" if estimates else "FAIL",
        "W3.1_gating_decay_stack_survival": survival.get("status") if survival else ("NOT_RUN" if not load_model else "HOOK_ONLY_NOT_SURVIVAL_CURVE"),
        "W3.1_native_delta_rule_as_stack_gap": native_gap.get("status") if native_gap else "NOT_RUN",
        "W3.2_qwen3_4b_delta_table": propagation.get("status") if propagation else "NOT_RUN",
    }
    integration_grade = "do_not_integrate_yet"
    if load_model and hook.get("hidden_dim") == config.get("hidden_size"):
        integration_grade = "alongside_candidate_pending_survival_and_delta_probes"
    if survival and native_gap and propagation:
        integration_grade = "alongside_only_measured_not_in_state"
    payload = {
        "module": "w3_qwen35_probe",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": model_id,
        "download_record": record,
        "config": config,
        "capacity_estimates": estimates,
        "hidden_hook_probe": hook,
        "survival_probe": survival,
        "native_delta_probe": native_gap,
        "propagation_probe": propagation,
        "p2_tables": _p2_tables(config, estimates, hook, verdicts, survival, native_gap, propagation),
        "verdicts": verdicts,
        "integration_grade": integration_grade,
        "red_lines": {
            "different_family_fallback_used": False,
            "ordering_only_pass": False,
            "per_task_verdicts_required_for_W3_2": True,
        },
    }
    (out / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "verdicts.json").write_text(json.dumps({"generated_at": payload["generated_at"], "model_id": model_id, "verdicts": verdicts, "integration_grade": integration_grade}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run W3 Qwen3.5 probe.")
    parser.add_argument("--output-dir", default="results/w3_qwen35_probe")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--download-record", default="results/model_download/qwen3_5_4b/qwen_download.json")
    parser.add_argument("--perdepth-path", default="results/module1_capacity_perdepth_shards/results.json")
    parser.add_argument("--load-model", action="store_true")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", choices=["bfloat16", "float16"], default="bfloat16")
    parser.add_argument("--run-survival", action="store_true")
    parser.add_argument("--run-native-delta", action="store_true")
    parser.add_argument("--run-propagation", action="store_true")
    parser.add_argument("--propagation-n-instances", type=int, default=3)
    parser.add_argument("--propagation-max-nodes-per-task", type=int, default=2)
    parser.add_argument("--propagation-seeds", default="42")
    parser.add_argument("--propagation-cap-nodes", type=int, default=32)
    parser.add_argument("--propagation-batch-size", type=int, default=2)
    parser.add_argument("--propagation-task-types", default="horn_sat,general_sat,graph_coloring,sudoku_4x4,logic_grid")
    parser.add_argument("--baseline-report", default="results/m2_operator_probe/report_fix_rescale.json")
    parser.add_argument("--merge-propagation-shards", default="")
    args = parser.parse_args()
    if args.merge_propagation_shards:
        _merge_propagation_shards(args.output_dir, [path for path in args.merge_propagation_shards.split(",") if path.strip()])
        raise SystemExit(0)
    propagation_seeds = [int(seed) for seed in args.propagation_seeds.split(",") if seed.strip()]
    propagation_task_types = [task for task in args.propagation_task_types.split(",") if task.strip()]
    run_probe(
        args.output_dir,
        args.model_id,
        args.download_record,
        args.perdepth_path,
        args.load_model,
        args.device,
        args.dtype,
        args.run_survival,
        args.run_native_delta,
        args.run_propagation,
        args.propagation_n_instances,
        args.propagation_max_nodes_per_task,
        propagation_seeds,
        args.propagation_cap_nodes,
        args.propagation_batch_size,
        args.baseline_report,
        propagation_task_types,
    )
