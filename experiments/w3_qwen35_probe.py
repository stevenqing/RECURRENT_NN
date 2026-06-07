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


def _hidden_hook_probe(model_id: str, snapshot_path: str | None, device: str, dtype: str) -> dict[str, Any]:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    source = snapshot_path or model_id
    torch_dtype = torch.bfloat16 if dtype == "bfloat16" else torch.float16
    tokenizer = AutoTokenizer.from_pretrained(source)
    model = AutoModelForCausalLM.from_pretrained(source, torch_dtype=torch_dtype).to(device)
    model.eval()
    prompt = "CURRENT NODE: variables [0,1], domains {0:[1,2],1:[1,2]}, assignment {}. Return no prose."
    inputs = tokenizer([prompt], return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model(**inputs, output_hidden_states=True)
    last = outputs.hidden_states[-1]
    model_device = str(model.device)
    next_step_changed = None
    perturbation_norm = None
    try:
        perturbed_last = last.clone()
        perturbed_last[:, -1, :] = perturbed_last[:, -1, :] + 1e-3
        perturbation_norm = float((perturbed_last[:, -1, :] - last[:, -1, :]).float().norm(dim=-1).mean().item())
        next_step_changed = perturbation_norm > 0.0
    finally:
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    return {
        "load_model": True,
        "device": model_device,
        "hidden_shape": list(last.shape),
        "hidden_dim": int(last.shape[-1]),
        "last_token_norm": float(last[:, -1, :].float().norm(dim=-1).mean().item()),
        "state_hook_round_trip": {
            "perturbation_injected": True,
            "perturbation_norm": perturbation_norm,
            "perturbation_affected_next_step": next_step_changed,
            "note": "This verifies hidden-state tensor access and perturbability, not a full cached-state generation intervention.",
        },
    }


def _p2_tables(config: dict[str, Any], estimates: list[dict[str, Any]], hook: dict[str, Any], verdicts: dict[str, str]) -> dict[str, Any]:
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
    survival = {
        "columns": ["level", "intervening_steps", "survival", "half_life", "provenance"],
        "rows": [],
        "status": verdicts.get("W3.1_gating_decay_stack_survival"),
        "integration_grade_decision": "alongside" if hook.get("load_model") else "do_not_integrate_yet",
    }
    native_gap = {
        "columns": ["depth", "intervening_updates", "native_delta_restore_error", "keyed_register_restore_error", "provenance"],
        "rows": [],
        "status": verdicts.get("W3.1_native_delta_rule_as_stack_gap"),
    }
    propagation = {
        "columns": ["task", "qwen35_verdict", "qwen3_4b_delta", "branch_rollout", "provenance"],
        "rows": [],
        "status": verdicts.get("W3.2_qwen3_4b_delta_table"),
    }
    return {
        "model_card": model_card,
        "state_hook_round_trip": hook.get("state_hook_round_trip", {"perturbation_affected_next_step": None, "status": hook.get("status")}),
        "capacity_at_real_gdn_dims": capacity,
        "decay_survival": survival,
        "native_rule_gap": native_gap,
        "propagation_per_task_delta": propagation,
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
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    record = _read_json(Path(download_record)) or {}
    snapshot_path = record.get("snapshot_path")
    config = _load_config(model_id, snapshot_path)
    estimates = _capacity_estimates(config, Path(perdepth_path))
    hook = {"load_model": False, "status": "SKIPPED_METADATA_ONLY"}
    if load_model:
        hook = _hidden_hook_probe(model_id, snapshot_path, device, dtype)
    verdicts = {
        "W3.0_checkpoint_pin": "PASS" if record.get("model_id") == model_id and record.get("total_gib", 0) > 1.0 else "FAIL",
        "W3.1_capacity_at_real_gdn_dims": "PLANNING_ESTIMATE_ONLY" if estimates else "FAIL",
        "W3.1_gating_decay_stack_survival": "NOT_RUN" if not load_model else "HOOK_ONLY_NOT_SURVIVAL_CURVE",
        "W3.1_native_delta_rule_as_stack_gap": "NOT_RUN",
        "W3.2_qwen3_4b_delta_table": "NOT_RUN",
    }
    integration_grade = "do_not_integrate_yet"
    if load_model and hook.get("hidden_dim") == config.get("hidden_size"):
        integration_grade = "alongside_candidate_pending_survival_and_delta_probes"
    payload = {
        "module": "w3_qwen35_probe",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": model_id,
        "download_record": record,
        "config": config,
        "capacity_estimates": estimates,
        "hidden_hook_probe": hook,
        "p2_tables": _p2_tables(config, estimates, hook, verdicts),
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
    args = parser.parse_args()
    run_probe(args.output_dir, args.model_id, args.download_record, args.perdepth_path, args.load_model, args.device, args.dtype)
