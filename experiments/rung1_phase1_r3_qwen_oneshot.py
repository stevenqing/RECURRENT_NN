"""Rung-1 Phase 1 R3 Qwen one-shot graph-coloring hardness anchor."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any

import torch
from reasoning_gym.algorithmic.graph_color import GraphColorConfig, GraphColorDataset
from tqdm.auto import tqdm

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, _rel

RUN_ROOT = REPO_ROOT / "results/rung1_phase1_r3_qwen_oneshot"
RESULTS_PATH = RUN_ROOT / "results.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_056_rung1_phase1_r3_qwen_oneshot.json"
R4_RESULTS_PATH = REPO_ROOT / "results/rung1_phase1_r4_natural_pool/results.json"
QWEN_DOWNLOAD_PATH = REPO_ROOT / "results/model_download/qwen3_5_4b/qwen_download.json"
SCHEMA_VERSION = "rung1_phase1_r3_qwen_oneshot_v1"
MODEL_ID = "Qwen/Qwen3.5-4B"
DEFAULT_VARIANTS = ("with_cot",)
STATUS_COMPLETE = "RUNG1_PHASE1_R3_QWEN_ONESHOT_RECORDED_V1"
STATUS_HEALTH_FAIL = "RUNG1_PHASE1_R3_QWEN_ONESHOT_HEALTH_FAIL_RERUN"
STATUS_STOP_HARDNESS = "RUNG1_PHASE1_R3_QWEN_ONESHOT_TOO_EASY_STOP"
TOO_EASY_SOLVE_RATE = 0.30
MAX_LENGTH_FRAC_FOR_CONCLUSION = 0.10


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _question(row: dict[str, Any]) -> str:
    vertices = list(range(int(row["n_vertices"])))
    edges = [tuple(edge) for edge in row["edges"]]
    colors = list(range(1, int(row["k"]) + 1))
    return "\n".join([
        "Please provide a coloring for this graph such that every vertex is not connected to a vertex of the same color. The graph has these properties:",
        "",
        f"Vertices: {vertices}",
        f"Edges: {edges}",
        f"Possible colors: {colors}",
        "",
        "Return your solution as a JSON map of vertices to colors. (For example: {\"0\": 1, \"1\": 2, \"2\": 3}.)",
    ])


def _prompt(row: dict[str, Any], variant: str) -> str:
    if variant == "direct_answer":
        return _question(row) + "\n\nReturn only the JSON map. Do not explain. Do not include markdown."
    return _question(row) + "\n\nUse concise chain-of-thought reasoning, then stop. Keep reasoning under 1200 tokens. You must output FINAL_JSON within the first 1600 generated tokens. The final line must be FINAL_JSON: followed by exactly one complete JSON map for all vertices."


def _fallback_prompt(row: dict[str, Any], first_text: str) -> str:
    return "\n".join([_question(row), "", "Previous response did not include a parseable final JSON coloring:", first_text[-3000:], "", "Now output only the final coloring JSON map. No prose. No markdown. Include all vertices 0 through 15."])


def _entry(row: dict[str, Any]) -> dict[str, Any]:
    return {"question": _question(row), "answer": None, "metadata": {"puzzle": {"vertices": list(range(int(row["n_vertices"]))), "edges": [tuple(edge) for edge in row["edges"]], "num_colors": int(row["k"]), "color_options": list(range(1, int(row["k"]) + 1))}}}


def _json_candidates(text: str) -> list[tuple[str, int]]:
    decoder = json.JSONDecoder()
    out: list[tuple[str, int]] = []
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(text[start:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            out.append((json.dumps(parsed, sort_keys=True), start))
    return out


def _looks_like_assignment(candidate: str, n_vertices: int) -> bool:
    try:
        parsed = json.loads(candidate)
    except Exception:
        return False
    if not isinstance(parsed, dict) or not parsed:
        return False
    valid_keys = {str(vertex) for vertex in range(n_vertices)}
    for key, value in parsed.items():
        if str(key) not in valid_keys or isinstance(value, bool):
            return False
        try:
            int(value)
        except Exception:
            return False
    return True


def _extract_final_json_answer(text: str, n_vertices: int) -> tuple[str | None, int | None]:
    lower = text.lower()
    marker = max(lower.rfind("final_json"), lower.rfind("final answer"), text.rfind("..."))
    regions = [(text[marker:], marker)] if marker >= 0 else []
    regions.append((text, 0))
    for region, offset in regions:
        for candidate, start in reversed(_json_candidates(region)):
            if _looks_like_assignment(candidate, n_vertices):
                return candidate, offset + start
    return None, None


def _assignment(answer: str | None) -> dict[int, int] | None:
    if answer is None:
        return None
    try:
        parsed = json.loads(answer)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    out: dict[int, int] = {}
    for key, value in parsed.items():
        try:
            out[int(key)] = int(value)
        except Exception:
            continue
    return out


def _assignment_metrics(row: dict[str, Any], answer: str | None) -> dict[str, Any]:
    assignment = _assignment(answer)
    n_vertices = int(row["n_vertices"])
    k = int(row["k"])
    if assignment is None:
        return {"assignment_complete": False, "num_conflicting_edges": None, "colors_used": None, "over_k_colors": False, "num_assigned_vertices": 0}
    conflicts = sum(1 for u, v in row["edges"] if int(u) in assignment and int(v) in assignment and assignment[int(u)] == assignment[int(v)])
    colors = set(assignment.values())
    return {"assignment_complete": set(assignment) == set(range(n_vertices)), "num_conflicting_edges": conflicts, "colors_used": len(colors), "over_k_colors": bool(colors) and (min(colors) < 1 or max(colors) > k or len(colors) > k), "num_assigned_vertices": len(set(assignment) & set(range(n_vertices)))}


def _format_chat(tokenizer: Any, prompt: str) -> str:
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            return tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            return tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True)
    return prompt


def _trim_tokens(token_ids: list[int], eos_token_id: int | None, max_new_tokens: int) -> tuple[list[int], str]:
    if eos_token_id is not None and eos_token_id in token_ids:
        eos_index = token_ids.index(eos_token_id)
        return token_ids[:eos_index], "stop"
    return token_ids, "length" if len(token_ids) >= max_new_tokens else "unknown"


@torch.no_grad()
def _generate_records(model: Any, tokenizer: Any, prompts: list[str], batch_size: int, max_new_tokens: int, description: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with tqdm(total=len(prompts), desc=description, unit="prompt", dynamic_ncols=True) as progress:
        for start in range(0, len(prompts), batch_size):
            batch = [_format_chat(tokenizer, prompt) for prompt in prompts[start:start + batch_size]]
            inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True).to(model.device)
            generated = model.generate(**inputs, do_sample=False, temperature=None, top_p=None, max_new_tokens=max_new_tokens, pad_token_id=tokenizer.eos_token_id)
            new_tokens = generated[:, inputs["input_ids"].shape[1]:]
            for token_ids in new_tokens.tolist():
                trimmed, finish_reason = _trim_tokens(token_ids, tokenizer.eos_token_id, max_new_tokens)
                records.append({"text": tokenizer.decode(trimmed, skip_special_tokens=True), "output_tokens": len(trimmed), "finish_reason": finish_reason})
            progress.update(len(batch))
    return records


def _load_model(snapshot_path: str | None, device: str, dtype_name: str) -> tuple[Any, Any, str]:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    source = snapshot_path or MODEL_ID
    dtype = torch.bfloat16 if dtype_name == "bfloat16" else torch.float16
    tokenizer = AutoTokenizer.from_pretrained(source)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(source, torch_dtype=dtype).to(device)
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad = False
    return model, tokenizer, source


def _depth_key(value: str) -> int:
    return 10 if value == "9+" else int(value)


def _avg(values: list[float]) -> float | None:
    return mean(values) if values else None


def _by(rows: list[dict[str, Any]], depth_bin: str, variant: str) -> list[dict[str, Any]]:
    return [row for row in rows if row["depth_bin"] == depth_bin and row["variant"] == variant]


def _outcome_breakdown(rows: list[dict[str, Any]], variants: tuple[str, ...]) -> list[dict[str, Any]]:
    out = []
    for depth_bin in sorted({row["depth_bin"] for row in rows}, key=_depth_key):
        for variant in variants:
            subset = _by(rows, depth_bin, variant)
            out.append({"depth_bin": depth_bin, "variant": variant, "n": len(subset), "frac_truncated_no_answer": _avg([float(row["first_finish_reason"] == "length" and not row["json_extracted"]) for row in subset]), "frac_parsable_invalid": _avg([float(row["json_extracted"] and not row["solved"]) for row in subset]), "frac_valid_solve": _avg([float(row["solved"]) for row in subset]), "frac_over_k_colors": _avg([float(row["over_k_colors"]) for row in subset]), "source": "autonomous_stage_a_run", "provenance": "qwen35_4b_temp0_outcome_breakdown_v1"})
    return out


def _generation_health(rows: list[dict[str, Any]], variants: tuple[str, ...], max_tokens_by_variant: dict[str, int]) -> list[dict[str, Any]]:
    out = []
    for depth_bin in sorted({row["depth_bin"] for row in rows}, key=_depth_key):
        for variant in variants:
            subset = _by(rows, depth_bin, variant)
            out.append({"depth_bin": depth_bin, "variant": variant, "n": len(subset), "mean_output_tokens": _avg([float(row["first_output_tokens"]) for row in subset]), "frac_finish_reason_length": _avg([float(row["first_finish_reason"] == "length") for row in subset]), "mean_thinking_tokens": _avg([float(row["thinking_tokens"]) for row in subset]), "fallback_rate": _avg([float(row["fallback_used"]) for row in subset]), "max_tokens_setting": max_tokens_by_variant[variant], "source": "autonomous_stage_a_run", "provenance": "qwen35_4b_temp0_generation_health_v1"})
    return out


def _wrongness(rows: list[dict[str, Any]], variants: tuple[str, ...]) -> list[dict[str, Any]]:
    out = []
    for depth_bin in sorted({row["depth_bin"] for row in rows}, key=_depth_key):
        for variant in variants:
            subset = [row for row in _by(rows, depth_bin, variant) if row["json_extracted"]]
            out.append({"depth_bin": depth_bin, "variant": variant, "n_parseable": len(subset), "mean_num_conflicting_edges": _avg([float(row["num_conflicting_edges"]) for row in subset if row["num_conflicting_edges"] is not None]), "mean_colors_used": _avg([float(row["colors_used"]) for row in subset if row["colors_used"] is not None]), "frac_complete_assignment": _avg([float(row["assignment_complete"]) for row in subset]), "source": "autonomous_stage_a_run", "provenance": "qwen35_4b_temp0_wrongness_conditional_parseable_v1"})
    return out


def _raw_text_samples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    buckets = [("valid_solve", lambda row: row["solved"]), ("parseable_invalid", lambda row: row["json_extracted"] and not row["solved"]), ("truncated_no_answer", lambda row: row["first_finish_reason"] == "length" and not row["json_extracted"]), ("format_no_answer", lambda row: row["first_finish_reason"] != "length" and not row["json_extracted"])]
    for bucket, predicate in buckets:
        for row in [row for row in rows if predicate(row)][:3]:
            samples.append({"bucket": bucket, "instance_id": row["instance_id"], "depth_bin": row["depth_bin"], "variant": row["variant"], "finish_reason": row["finish_reason"], "first_finish_reason": row["first_finish_reason"], "fallback_used": row["fallback_used"], "raw_text": row["raw_text"][:3000]})
    return samples


def _build_item(results: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "log_item_contract_v1", "item_number": "056", "name": "Rung-1 Phase 1 R3 Qwen one-shot hardness anchor", "status": results["status"], "purpose": "Run Qwen3.5-4B temperature-zero one-shot graph-coloring baselines on the exact R4 RG-native natural pool while separating truncation, formatting, and reasoning failures.", "code_added_used": [{"path": "experiments/rung1_phase1_r3_qwen_oneshot.py", "change": "Records finish_reason/output_tokens, extracts final vertex-color JSON, applies no-JSON fallback, and reports outcome/health/wrongness tables."}], "commands": [{"command": ".venv/bin/python -m experiments.rung1_phase1_r3_qwen_oneshot --variants with_cot --max-new-tokens-cot 4096", "purpose": "Run repaired with-CoT one-shot hardness anchor."}], "artifacts": [_rel(RESULTS_PATH), _rel(ITEM_PATH)], "provenance": results["generation_config"], "result_tables": {"oneshot_outcome_breakdown": {"rows": results["oneshot_outcome_breakdown"]}, "oneshot_generation_health": {"rows": results["oneshot_generation_health"]}, "oneshot_wrongness": {"rows": results["oneshot_wrongness"]}, "oneshot_instance_rows": {"rows": results["oneshot_instance_rows"]}, "raw_text_samples": {"rows": results["raw_text_samples"]}}, "honesty": {"does_not_establish": "This is a non-agentic one-shot hardness anchor only. It does not test register recovery, CBJ efficiency, or fallible multi-step operator behavior.", "failure_disambiguation": "solve=0 is interpreted only through separate truncation, formatting, and parseable-invalid reasoning fields."}, "decision": {"gate_outcomes": [{"gate": "generation_health", "outcome": "PASS" if results["acceptance"]["health_pass"] else "RERUN", "number": f"max_frac_finish_reason_length={results['acceptance']['max_frac_finish_reason_length']:.4f}"}, {"gate": "task_hardness_gate", "outcome": "STOP" if results["acceptance"]["too_easy"] else ("PASS" if results["acceptance"]["health_pass"] else "NO_CONCLUSION"), "number": f"with_cot_valid_solve_rate={results['acceptance'].get('with_cot_valid_solve_rate')}"}], "next_step_routing": "Proceed to Phase 1 only if generation_health passes and with_cot valid solve remains below the too-easy threshold.", "outcome": results["status"]}}


def _row_from_generation(row: dict[str, Any], variant: str, generation: dict[str, Any], answer: str | None, json_start: int | None, scorer: GraphColorDataset, source: str, max_tokens: int, shard_index: int | None, num_shards: int, fallback_used: bool, first_generation: dict[str, Any] | None = None) -> dict[str, Any]:
    score = scorer.score_answer(answer, _entry(row)) if answer is not None else 0.0
    metrics = _assignment_metrics(row, answer)
    first = first_generation or generation
    thinking_text = generation["text"][:json_start] if json_start is not None else first["text"]
    return {"instance_id": row["instance_id"], "seed": row["seed"], "depth_bin": row["depth_bin"], "variant": variant, "max_tokens": max_tokens, "finish_reason": generation["finish_reason"], "first_finish_reason": first["finish_reason"], "output_tokens": int(generation["output_tokens"]) + (int(first_generation.get("output_tokens", 0)) if first_generation else 0), "first_output_tokens": int(first["output_tokens"]), "thinking_tokens": len(thinking_text.split()), "json_extracted": answer is not None, "assignment_complete": metrics["assignment_complete"], "num_conflicting_edges": metrics["num_conflicting_edges"], "colors_used": metrics["colors_used"], "over_k_colors": metrics["over_k_colors"], "num_assigned_vertices": metrics["num_assigned_vertices"], "rg_score": score, "solved": score == 1.0, "answer": answer, "raw_text": generation["text"], "fallback_used": fallback_used, "model_id": MODEL_ID, "model_source": source, "temperature": 0, "shard_index": shard_index, "num_shards": num_shards, "source": "autonomous_stage_a_run", "provenance": "qwen35_4b_temp0_rg_graph_color_score_answer_v1"}


def _finalize_results(rows: list[dict[str, Any]], r4_results_path: Path, source: str, batch_size: int, max_tokens_by_variant: dict[str, int], device: str, dtype: str, limit: int | None, variants: tuple[str, ...], shard_index: int | None = None, num_shards: int = 1, shard_result_paths: list[str] | None = None) -> dict[str, Any]:
    health_rows = _generation_health(rows, variants, max_tokens_by_variant)
    max_length_frac = max((float(row["frac_finish_reason_length"] or 0.0) for row in health_rows), default=0.0)
    health_pass = max_length_frac <= MAX_LENGTH_FRAC_FOR_CONCLUSION
    solve_rates = {variant: mean(float(row["solved"]) for row in rows if row["variant"] == variant) for variant in variants if any(row["variant"] == variant for row in rows)}
    max_rate = max(solve_rates.values()) if solve_rates else 0.0
    too_easy = health_pass and max_rate > TOO_EASY_SOLVE_RATE
    status = STATUS_HEALTH_FAIL if not health_pass else (STATUS_STOP_HARDNESS if too_easy else STATUS_COMPLETE)
    results = {"schema_version": SCHEMA_VERSION, "generated_at": _now(), "status": status, "generation_config": {"r4_results_path": _rel(r4_results_path), "model_id": MODEL_ID, "model_source": source, "batch_size": batch_size, "max_tokens_by_variant": max_tokens_by_variant, "device": device, "dtype": dtype, "limit": limit, "shard_index": shard_index, "num_shards": num_shards, "shard_result_paths": shard_result_paths or [], "variants": list(variants), "temperature": 0, "qwen_native_thinking": False, "fallback_on_no_json": True, "scoring_api": "reasoning_gym.algorithmic.graph_color.GraphColorDataset.score_answer", "verifier_api": "reasoning_gym.algorithmic.graph_color.verify_graph_coloring_solution via GraphColorDataset.score_answer"}, "acceptance": {"health_pass": health_pass, "max_frac_finish_reason_length": max_length_frac, "too_easy": too_easy, "variant_solve_rates": solve_rates, "max_variant_solve_rate": max_rate, "with_cot_valid_solve_rate": solve_rates.get("with_cot"), "max_allowed_frac_finish_reason_length": MAX_LENGTH_FRAC_FOR_CONCLUSION}, "oneshot_outcome_breakdown": _outcome_breakdown(rows, variants), "oneshot_generation_health": health_rows, "oneshot_wrongness": _wrongness(rows, variants), "oneshot_instance_rows": rows, "raw_text_samples": _raw_text_samples(rows)}
    _write_json(RESULTS_PATH, results)
    _write_json(ITEM_PATH, _build_item(results))
    return results


def run(r4_results_path: Path, batch_size: int, max_new_tokens_direct: int, max_new_tokens_cot: int, device: str, dtype: str, variants: tuple[str, ...], limit: int | None = None, shard_index: int | None = None, num_shards: int = 1) -> dict[str, Any]:
    r4 = _read_json(r4_results_path)
    manifest = r4["instance_manifest"][:limit]
    if num_shards > 1:
        if shard_index is None or shard_index < 0 or shard_index >= num_shards:
            raise ValueError(f"shard_index must be in [0, {num_shards})")
        manifest = manifest[shard_index::num_shards]
    download = _read_json(QWEN_DOWNLOAD_PATH) if QWEN_DOWNLOAD_PATH.exists() else {}
    model, tokenizer, source = _load_model(download.get("snapshot_path"), device=device, dtype_name=dtype)
    scorer = GraphColorDataset(GraphColorConfig(num_colors=4, min_num_vertices=16, max_num_vertices=16, seed=0, size=1))
    rows: list[dict[str, Any]] = []
    max_tokens_by_variant = {"direct_answer": max_new_tokens_direct, "with_cot": max_new_tokens_cot}
    shard_label = f" shard {shard_index}/{num_shards}" if num_shards > 1 else ""
    for variant in variants:
        max_tokens = max_tokens_by_variant[variant]
        generations = _generate_records(model, tokenizer, [_prompt(row, variant) for row in manifest], batch_size, max_tokens, f"R3 {variant}{shard_label}")
        pending: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for instance_row, generation in zip(manifest, generations):
            answer, json_start = _extract_final_json_answer(generation["text"], int(instance_row["n_vertices"]))
            if answer is None:
                pending.append((instance_row, generation))
            else:
                rows.append(_row_from_generation(instance_row, variant, generation, answer, json_start, scorer, source, max_tokens, shard_index, num_shards, False))
        if pending:
            fallback_generations = _generate_records(model, tokenizer, [_fallback_prompt(row, generation["text"]) for row, generation in pending], batch_size, min(1024, max_tokens), f"R3 fallback {variant}{shard_label}")
            for (instance_row, first_generation), fallback_generation in zip(pending, fallback_generations):
                answer, json_start = _extract_final_json_answer(fallback_generation["text"], int(instance_row["n_vertices"]))
                rows.append(_row_from_generation(instance_row, variant, fallback_generation, answer, json_start, scorer, source, max_tokens, shard_index, num_shards, True, first_generation))
    rows.sort(key=lambda item: (item["variant"], _depth_key(item["depth_bin"]), item["instance_id"]))
    return _finalize_results(rows, r4_results_path, source, batch_size, max_tokens_by_variant, device, dtype, limit, variants, shard_index, num_shards)


def merge_shards(shards_root: Path, num_shards: int, r4_results_path: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    shard_paths: list[str] = []
    first_config: dict[str, Any] | None = None
    for shard_index in range(num_shards):
        shard_path = shards_root / f"shard_{shard_index}" / "results.json"
        shard = _read_json(shard_path)
        shard_paths.append(_rel(shard_path))
        first_config = first_config or shard.get("generation_config", {})
        rows.extend(shard.get("oneshot_instance_rows", []))
    config = first_config or {}
    variants = tuple(config.get("variants", list(DEFAULT_VARIANTS)))
    expected_rows = len(_read_json(r4_results_path)["instance_manifest"]) * len(variants)
    if len(rows) != expected_rows:
        raise ValueError(f"merged {len(rows)} rows, expected {expected_rows}")
    rows.sort(key=lambda item: (item["variant"], _depth_key(item["depth_bin"]), item["instance_id"]))
    return _finalize_results(rows, r4_results_path, str(config.get("model_source", MODEL_ID)), int(config.get("batch_size", 0)), dict(config.get("max_tokens_by_variant", {})), "8x_data_parallel_shards", str(config.get("dtype", "bfloat16")), config.get("limit"), variants, None, num_shards, shard_paths)


def main() -> None:
    global RUN_ROOT, RESULTS_PATH, ITEM_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--r4-results", default=str(R4_RESULTS_PATH))
    parser.add_argument("--output-dir", default=str(RUN_ROOT))
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--max-new-tokens-direct", type=int, default=1024)
    parser.add_argument("--max-new-tokens-cot", type=int, default=4096)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", choices=["bfloat16", "float16"], default="bfloat16")
    parser.add_argument("--variants", nargs="+", choices=["direct_answer", "with_cot"], default=list(DEFAULT_VARIANTS))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--item-output", default=str(ITEM_PATH))
    parser.add_argument("--shard-index", type=int, default=None)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--merge-shards", default=None)
    args = parser.parse_args()
    RUN_ROOT = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO_ROOT / args.output_dir
    RESULTS_PATH = RUN_ROOT / "results.json"
    ITEM_PATH = Path(args.item_output) if Path(args.item_output).is_absolute() else REPO_ROOT / args.item_output
    r4_results = Path(args.r4_results) if Path(args.r4_results).is_absolute() else REPO_ROOT / args.r4_results
    if args.merge_shards:
        shards_root = Path(args.merge_shards) if Path(args.merge_shards).is_absolute() else REPO_ROOT / args.merge_shards
        merge_shards(shards_root, args.num_shards, r4_results)
    else:
        run(r4_results, args.batch_size, args.max_new_tokens_direct, args.max_new_tokens_cot, args.device, args.dtype, tuple(args.variants), args.limit, args.shard_index, args.num_shards)


if __name__ == "__main__":
    main()
