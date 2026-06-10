"""8-GPU Qwen P1a forward-only hardness gate for separator PO experiments."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from statistics import mean, median
from typing import Any

import torch
from tqdm.auto import tqdm

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _adjacency, _rel

RESULTS_ROOT = REPO_ROOT / "results/rung1_separator_llm_po"
GATE_RESULTS_PATH = RESULTS_ROOT / "p1a_forward_gate.json"
SEPARATOR_RESULTS_PATH = REPO_ROOT / "results/rung1_separator_scaling/results.json"
QWEN35_DOWNLOAD_PATH = REPO_ROOT / "results/model_download/qwen3_5_4b/qwen_download.json"
SCHEMA_VERSION = "rung1_separator_llm_po_forward_gate_v1"
MODEL_ID = "Qwen/Qwen3.5-4B"
SELECTED_CELL_IDS = {"corner_local_heavy", "dg_m2_dl5", "dg_m4_dl5", "dg_m6_dl5", "b_b12_db2", "b_b12_db4"}
DEFAULT_N_PER_CELL = 24
DEFAULT_CALL_CAP = 200
DEFAULT_MAX_NEW_TOKENS = 8192
DEFAULT_BATCH_SIZE_PER_GPU = 2
OOM_RETRY_BATCH_SIZE_PER_GPU = 1
TRUNCATION_RATE_THRESHOLD = 0.10
P1A_PROMPT_CONTRACT = "p1a_json_only_branch_value_no_reasoning_v1"


@dataclass
class Episode:
    row: dict[str, Any]
    adjacency: dict[int, set[int]]
    order: list[int]
    assignment: dict[int, int] = field(default_factory=dict)
    cursor: int = 0
    calls: int = 0
    status: str = "RUNNING"
    solved: bool = False
    trace: list[dict[str, Any]] = field(default_factory=list)
    operator_error_counts: Counter[str] = field(default_factory=Counter)
    generation_counts: Counter[str] = field(default_factory=Counter)
    distinct_attempts_by_vertex: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _last_json(text: str) -> tuple[dict[str, Any] | None, int | None]:
    decoder = json.JSONDecoder()
    found: tuple[dict[str, Any], int] | None = None
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            found = (parsed, index)
    if found is None:
        return None, None
    return found


def _trim_tokens(token_ids: list[int], eos_token_id: int | None, max_new_tokens: int) -> tuple[list[int], str]:
    if eos_token_id is not None and eos_token_id in token_ids:
        eos_index = token_ids.index(eos_token_id)
        return token_ids[:eos_index], "stop"
    return token_ids, "length" if len(token_ids) >= max_new_tokens else "unknown"


def _load_model(device: str, dtype_name: str) -> tuple[Any, Any, str]:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    download = _read_json(QWEN35_DOWNLOAD_PATH)
    source = download.get("snapshot_path") or MODEL_ID
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


def _format_chat(tokenizer: Any, prompt: str) -> str:
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            return tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            return tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True)
    return prompt


@torch.no_grad()
def _generate_batch(model: Any, tokenizer: Any, prompts: list[str], max_new_tokens: int) -> list[dict[str, Any]]:
    formatted = [_format_chat(tokenizer, prompt) for prompt in prompts]
    inputs = tokenizer(formatted, return_tensors="pt", padding=True, truncation=True).to(model.device)
    generated = model.generate(
        **inputs,
        do_sample=False,
        temperature=None,
        top_p=None,
        max_new_tokens=max_new_tokens,
        pad_token_id=tokenizer.eos_token_id,
    )
    new_tokens = generated[:, inputs["input_ids"].shape[1]:]
    out = []
    for token_ids in new_tokens.tolist():
        trimmed, finish_reason = _trim_tokens(token_ids, tokenizer.eos_token_id, max_new_tokens)
        out.append({"text": tokenizer.decode(trimmed, skip_special_tokens=True), "output_tokens": len(trimmed), "finish_reason": finish_reason})
    return out


def _prompt(episode: Episode) -> str:
    row = episode.row
    vertex = episode.order[episode.cursor]
    block = int(row["partitions"][vertex])
    feasible_colors = _feasible_colors(episode, vertex)
    own_vertices = [idx for idx, part in enumerate(row["partitions"]) if int(part) == block]
    own_set = set(own_vertices)
    boundary_edges = [edge for edge in row["edges"] if (int(edge[0]) in own_set) ^ (int(edge[1]) in own_set)]
    visible_assignment = {}
    for assigned_vertex, color in episode.assignment.items():
        if assigned_vertex in own_set or any(assigned_vertex in map(int, edge) and vertex in map(int, edge) for edge in boundary_edges):
            visible_assignment[assigned_vertex] = color
    return "\n".join([
        "P1a branch-only value-ordering operator.",
        "Symbolic guards already computed the live domain. Choose exactly one listed color.",
        "Do not reason, explain, restate the task, use markdown, or add extra keys.",
        "Return exactly one compact JSON object: {\"color\": <one value from feasible_colors>}.",
        f"current_vertex={vertex}; agent_block={block}; k={row['k']}",
        f"feasible_colors={feasible_colors}",
        f"own_block_vertices={own_vertices}",
        f"incident_boundary_edges={boundary_edges}",
        f"visible_assignment={dict(sorted(visible_assignment.items()))}",
    ])


def _feasible_colors(episode: Episode, vertex: int) -> list[int]:
    feasible = []
    for color in range(1, int(episode.row["k"]) + 1):
        if all(episode.assignment.get(neighbor) != color for neighbor in episode.adjacency[vertex]):
            feasible.append(color)
    return feasible


def _parse_generation(generation: dict[str, Any], k: int) -> dict[str, Any]:
    parsed, start = _last_json(generation["text"])
    if parsed is None:
        state = "truncated_no_answer" if generation["finish_reason"] == "length" else "format_failure"
        return {"generation_state": state, "color": None, "json_start": None, "parseable": False, "valid": False}
    color = parsed.get("color")
    valid = isinstance(color, int) and not isinstance(color, bool) and 1 <= color <= k
    return {"generation_state": "valid" if valid else "parsable_invalid", "color": color if isinstance(color, int) and not isinstance(color, bool) else None, "json_start": start, "parseable": True, "valid": valid}


def _step_episode(episode: Episode, generation: dict[str, Any]) -> None:
    if episode.status != "RUNNING":
        return
    if episode.calls >= DEFAULT_CALL_CAP:
        episode.status = "CALL_CAP"
        return
    vertex = episode.order[episode.cursor]
    feasible = _feasible_colors(episode, vertex)
    if not feasible:
        episode.status = "FORWARD_DEAD_END"
        return
    parsed = _parse_generation(generation, int(episode.row["k"]))
    episode.calls += 1
    episode.generation_counts[parsed["generation_state"]] += 1
    chosen = parsed["color"]
    if parsed["generation_state"] in {"format_failure", "truncated_no_answer", "parsable_invalid"}:
        episode.operator_error_counts["format_failure"] += 1
        chosen = feasible[0]
    elif chosen not in feasible:
        episode.operator_error_counts["value_misselection"] += 1
        episode.distinct_attempts_by_vertex[vertex].add(int(chosen))
        chosen = feasible[0]
    episode.distinct_attempts_by_vertex[vertex].add(int(chosen))
    episode.assignment[vertex] = int(chosen)
    episode.trace.append({
        "vertex": vertex,
        "chosen_color": int(chosen),
        "llm_color": parsed["color"],
        "feasible_colors": feasible,
        "generation_state": parsed["generation_state"],
        "finish_reason": generation["finish_reason"],
        "output_tokens": generation["output_tokens"],
    })
    episode.cursor += 1
    if episode.cursor >= len(episode.order):
        episode.status = "SOLVED"
        episode.solved = True


def _select_manifest(n_per_cell: int) -> list[dict[str, Any]]:
    data = _read_json(SEPARATOR_RESULTS_PATH)
    acceptance = data.get("acceptance", {})
    if data.get("schema_version") != "rung1_separator_scaling_symbolic_v0_2_3" or not acceptance.get("overall_pass") or not acceptance.get("fairness_corner_clean"):
        raise RuntimeError("symbolic separator v0.2.3 fairness gate is not passed")
    by_cell: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data["instance_manifest"]:
        if row.get("cell_id") in SELECTED_CELL_IDS:
            by_cell[row["cell_id"]].append(row)
    selected = []
    for cell_id in sorted(SELECTED_CELL_IDS):
        rows = by_cell.get(cell_id, [])[:n_per_cell]
        selected.extend(rows)
    return selected


def _episode_row(episode: Episode, model_source: str, shard_index: int, num_shards: int, n_per_cell: int, batch_size: int, max_new_tokens: int) -> dict[str, Any]:
    attempts = sum(len(values) for values in episode.distinct_attempts_by_vertex.values())
    clean = max(1, len(episode.distinct_attempts_by_vertex))
    generation_total = sum(episode.generation_counts.values()) or 1
    return {
        "instance_id": episode.row["instance_id"],
        "cell_id": episode.row["cell_id"],
        "sweep": episode.row["sweep"],
        "d_global_reference": episode.row["d_global_reference"],
        "b": episode.row["b"],
        "rung": "P1a_branch_only_sound_forward_gate",
        "arm": "forward_markov_team_qwen_p1a",
        "solved": episode.solved,
        "status": episode.status,
        "llm_calls": episode.calls,
        "steps_to_solve_or_cap": len(episode.trace),
        "call_cap": DEFAULT_CALL_CAP,
        "finish_reason": Counter(item["finish_reason"] for item in episode.trace).most_common(1)[0][0] if episode.trace else None,
        "output_tokens": sum(int(item["output_tokens"]) for item in episode.trace),
        "thinking_tokens": 0,
        "generation_truncated_no_answer": episode.generation_counts["truncated_no_answer"],
        "generation_parsable_invalid": episode.generation_counts["parsable_invalid"],
        "generation_valid": episode.generation_counts["valid"],
        "generation_format_failure": episode.generation_counts["format_failure"],
        "false_pos_deadend": episode.operator_error_counts["false_pos_deadend"],
        "false_neg_missed_conflict": episode.operator_error_counts["false_neg_missed_conflict"],
        "value_misselection": episode.operator_error_counts["value_misselection"],
        "format_failure": episode.operator_error_counts["format_failure"],
        "frac_valid_generation": episode.generation_counts["valid"] / generation_total,
        "k_eff_clean": episode.row.get("mean_live_domain_at_decision"),
        "k_eff_inflated": attempts / clean,
        "rho": (attempts / clean) / max(float(episode.row.get("mean_live_domain_at_decision") or 1.0), 1e-9),
        "model_id": MODEL_ID,
        "model_source": model_source,
        "temperature": 0,
        "max_new_tokens": max_new_tokens,
        "n_per_cell": n_per_cell,
        "batch_size_per_gpu": batch_size,
        "prompt_contract": P1A_PROMPT_CONTRACT,
        "shard_index": shard_index,
        "num_shards": num_shards,
        "source": SOURCE,
        "provenance": "qwen35_p1a_forward_only_po_gate_v1",
    }


def run_shard(shard_index: int, num_shards: int, output_dir: Path, n_per_cell: int, batch_size: int, max_new_tokens: int, device: str, dtype: str) -> dict[str, Any]:
    manifest = _select_manifest(n_per_cell)
    shard_rows = [row for index, row in enumerate(manifest) if index % num_shards == shard_index]
    model, tokenizer, model_source = _load_model(device, dtype)
    episodes = [Episode(row=row, adjacency=_adjacency(int(row["n_vertices"]), tuple(tuple(edge) for edge in row["edges"])), order=[int(v) for v in row["order"]]) for row in shard_rows]
    active = [episode for episode in episodes if episode.status == "RUNNING"]
    with tqdm(total=len(episodes), desc=f"p1a forward shard {shard_index}", unit="inst", dynamic_ncols=True) as progress:
        completed = 0
        while active:
            batch = active[:batch_size]
            generations = _generate_batch(model, tokenizer, [_prompt(episode) for episode in batch], max_new_tokens)
            for episode, generation in zip(batch, generations):
                before = episode.status
                _step_episode(episode, generation)
                if episode.status != "RUNNING" and before == "RUNNING":
                    completed += 1
                    progress.update(1)
            active = [episode for episode in episodes if episode.status == "RUNNING" and episode.calls < DEFAULT_CALL_CAP]
            for episode in episodes:
                if episode.status == "RUNNING" and episode.calls >= DEFAULT_CALL_CAP:
                    episode.status = "CALL_CAP"
                    completed += 1
                    progress.update(1)
    rows = [_episode_row(episode, model_source, shard_index, num_shards, n_per_cell, batch_size, max_new_tokens) for episode in episodes]
    payload = {"schema_version": SCHEMA_VERSION, "generated_at": _now(), "status": "SHARD_COMPLETE", "shard_index": shard_index, "num_shards": num_shards, "instance_arm_metrics": rows, "source": SOURCE}
    _write_json(output_dir / f"shard_{shard_index:02d}.json", payload)
    return payload


def _summaries(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    op_rows = []
    keff_rows = []
    budget_rows = []
    keys = sorted({(row["rung"], row["d_global_reference"], row["b"]) for row in rows}, key=lambda item: (item[0], item[1], item[2]))
    for rung, d_global, b in keys:
        subset = [row for row in rows if row["rung"] == rung and row["d_global_reference"] == d_global and row["b"] == b]
        n = len(subset)
        op_rows.append({
            "rung": rung,
            "d_global_bin": str(d_global),
            "b_bin": str(b),
            "n": n,
            "false_pos_deadend_rate": mean(float(row["false_pos_deadend"] > 0) for row in subset),
            "false_neg_missed_conflict_rate": mean(float(row["false_neg_missed_conflict"] > 0) for row in subset),
            "value_misselection_rate": mean(float(row["value_misselection"] > 0) for row in subset),
            "format_failure_rate": mean(float(row["format_failure"] > 0) for row in subset),
            "frac_truncated_no_answer": mean(float(row["generation_truncated_no_answer"] > 0) for row in subset),
            "frac_parsable_invalid": mean(float(row["generation_parsable_invalid"] > 0) for row in subset),
            "frac_valid": mean(float(row["generation_valid"] > 0) for row in subset),
            "source": SOURCE,
            "provenance": "qwen35_p1a_operator_error_breakdown_v0",
        })
        keff_rows.append({
            "rung": rung,
            "d_global_bin": str(d_global),
            "b_bin": str(b),
            "k_eff_clean": mean(float(row["k_eff_clean"]) for row in subset),
            "k_eff_inflated": mean(float(row["k_eff_inflated"]) for row in subset),
            "rho": mean(float(row["rho"]) for row in subset),
            "n": n,
            "source": SOURCE,
            "provenance": "qwen35_p1a_keff_inflation_v0",
        })
        budget_rows.append({
            "arm": "forward_markov_team_qwen_p1a",
            "d_global_bin": str(d_global),
            "b_bin": str(b),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "n": n,
            "source": SOURCE,
            "provenance": "qwen35_p1a_forward_gate_solve_rate_v0",
        })
    return op_rows, keff_rows, budget_rows


def _truncation_gate(op_rows: list[dict[str, Any]]) -> dict[str, Any]:
    deepest = max((int(row["d_global_bin"]) for row in op_rows), default=0)
    deep_rows = [row for row in op_rows if int(row["d_global_bin"]) == deepest]
    max_deep = max((float(row["frac_truncated_no_answer"]) for row in deep_rows), default=0.0)
    max_all = max((float(row["frac_truncated_no_answer"]) for row in op_rows), default=0.0)
    return {
        "gate": "forward_gate_truncation_ok",
        "pass": max_deep <= TRUNCATION_RATE_THRESHOLD and max_all <= TRUNCATION_RATE_THRESHOLD,
        "threshold": TRUNCATION_RATE_THRESHOLD,
        "deepest_d_global": deepest,
        "max_deep_frac_truncated_no_answer": max_deep,
        "max_all_frac_truncated_no_answer": max_all,
        "source": SOURCE,
        "provenance": "qwen35_p1a_forward_gate_truncation_prelaunch_v1",
    }


def _cost_estimate(rows: list[dict[str, Any]], n_per_cell: int, selected_cell_count: int) -> dict[str, Any]:
    calls = [int(row["llm_calls"]) for row in rows]
    median_calls = median(calls) if calls else 0
    arms = ["forward_markov_team_qwen_p1a", "chronological_rollback_team_qwen_p1a", "cbj_bounded_team_qwen_p1a"]
    total_without_budget_sweep = int(median_calls * n_per_cell * len(arms) * selected_cell_count)
    comm_budget_sweep_len = 8
    return {
        "pilot_median_calls_per_instance": median_calls,
        "n_per_cell": n_per_cell,
        "n_cells": selected_cell_count,
        "arms": arms,
        "estimated_qwen_calls_without_comm_budget_sweep": total_without_budget_sweep,
        "comm_budget_sweep_len_if_applied": comm_budget_sweep_len,
        "estimated_qwen_calls_with_comm_budget_sweep": total_without_budget_sweep * comm_budget_sweep_len,
        "source": SOURCE,
        "provenance": "qwen35_p1a_recovery_sweep_call_estimate_v1",
    }


def merge(output_dir: Path, num_shards: int) -> dict[str, Any]:
    rows = []
    shard_paths = []
    for shard_index in range(num_shards):
        path = output_dir / f"shard_{shard_index:02d}.json"
        shard_paths.append(_rel(path))
        rows.extend(_read_json(path)["instance_arm_metrics"])
    op_rows, keff_rows, budget_rows = _summaries(rows)
    solve_rate = mean(float(row["solved"]) for row in rows) if rows else 0.0
    truncation_gate = _truncation_gate(op_rows)
    observed_n_per_cell = sorted({int(row.get("n_per_cell", DEFAULT_N_PER_CELL)) for row in rows})
    observed_batch_sizes = sorted({int(row.get("batch_size_per_gpu", DEFAULT_BATCH_SIZE_PER_GPU)) for row in rows})
    cost_n_per_cell = observed_n_per_cell[0] if len(observed_n_per_cell) == 1 else DEFAULT_N_PER_CELL
    cost_estimate = _cost_estimate(rows, cost_n_per_cell, len(SELECTED_CELL_IDS))
    too_easy = solve_rate >= 0.30
    status = "RUNG1_SEPARATOR_LLM_PO_FORWARD_GATE_TOO_EASY_STOP" if too_easy else "RUNG1_SEPARATOR_LLM_PO_FORWARD_GATE_PASS"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": status,
        "generation_config": {
            "model_id": MODEL_ID,
            "temperature": 0,
            "max_new_tokens": rows[0]["max_new_tokens"] if rows else None,
            "prompt_contract": rows[0].get("prompt_contract") if rows else P1A_PROMPT_CONTRACT,
            "n_shards": num_shards,
            "selected_cell_ids": sorted(SELECTED_CELL_IDS),
            "n_per_cell": cost_n_per_cell,
            "n_per_cell_observed_values": observed_n_per_cell,
            "batch_size_per_gpu_observed_values": observed_batch_sizes,
            "batch_size_per_gpu_max_allowed": DEFAULT_BATCH_SIZE_PER_GPU,
            "oom_retry_batch_size_per_gpu": OOM_RETRY_BATCH_SIZE_PER_GPU,
            "call_cap": DEFAULT_CALL_CAP,
            "truncation_rate_threshold": TRUNCATION_RATE_THRESHOLD,
            "po_visibility": "own block, incident boundary edges, and messaged boundary-neighbor colors only",
            "source": SOURCE,
            "provenance": "qwen35_p1a_forward_gate_config_v1",
        },
        "acceptance": {"forward_gate_pass": not too_easy, "forward_gate_truncation_ok": bool(truncation_gate["pass"]), "solve_rate": solve_rate, "too_easy_threshold": 0.30, "llm_p1a_full_table_allowed": not too_easy and bool(truncation_gate["pass"])},
        "prelaunch_truncation_gate": [truncation_gate],
        "recovery_sweep_cost_estimate": [cost_estimate],
        "operator_error_breakdown": op_rows,
        "keff_inflation": keff_rows,
        "budget_at_95_solve": budget_rows,
        "instance_arm_metrics": rows,
        "shard_paths": shard_paths,
        "verdict": [
            {"check": "kill_po_too_easy", "predicted": "forward-only LLM solve rate < 0.30", "observed": f"solve_rate={solve_rate:.4f}", "pass": not too_easy, "source": SOURCE, "provenance": "qwen35_p1a_forward_gate_verdict_v1"},
            {"check": "forward_gate_truncation_ok", "predicted": f"deepest and all-cell truncated_no_answer fraction <= {TRUNCATION_RATE_THRESHOLD:.2f}", "observed": f"deepest_d_global={truncation_gate['deepest_d_global']}; max_deep={truncation_gate['max_deep_frac_truncated_no_answer']:.4f}; max_all={truncation_gate['max_all_frac_truncated_no_answer']:.4f}", "pass": bool(truncation_gate["pass"]), "source": SOURCE, "provenance": "qwen35_p1a_forward_gate_verdict_v1"},
        ],
    }
    _write_json(GATE_RESULTS_PATH, payload)
    return payload


def _log_has_oom(log_path: Path) -> bool:
    if not log_path.exists():
        return False
    text = log_path.read_text(encoding="utf-8", errors="ignore").lower()
    oom_needles = ["out of memory", "cuda oom", "cuda error: out of memory", "cublas_status_alloc_failed", "hip out of memory"]
    return any(needle in text for needle in oom_needles)


def _launch_shard(args: argparse.Namespace, output_dir: Path, shard_index: int, batch_size: int, log_suffix: str = "") -> tuple[int, Path]:
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(shard_index)
    cmd = [
        args.python_bin,
        "-u",
        "-m",
        "experiments.rung1_separator_llm_po_forward_gate",
        "--shard-index",
        str(shard_index),
        "--num-shards",
        str(args.num_shards),
        "--output-dir",
        str(output_dir),
        "--n-per-cell",
        str(args.n_per_cell),
        "--batch-size",
        str(batch_size),
        "--max-new-tokens",
        str(args.max_new_tokens),
        "--device",
        "cuda:0",
        "--dtype",
        args.dtype,
    ]
    log_path = output_dir / f"shard_{shard_index:02d}{log_suffix}.log"
    with log_path.open("w", encoding="utf-8") as log_handle:
        code = subprocess.Popen(cmd, cwd=REPO_ROOT, env=env, stdout=log_handle, stderr=subprocess.STDOUT, text=True).wait()
    return code, log_path


def launch_8gpu(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    python = args.python_bin
    processes = []
    for shard_index in range(args.num_shards):
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(shard_index)
        cmd = [
            python,
            "-u",
            "-m",
            "experiments.rung1_separator_llm_po_forward_gate",
            "--shard-index",
            str(shard_index),
            "--num-shards",
            str(args.num_shards),
            "--output-dir",
            str(output_dir),
            "--n-per-cell",
            str(args.n_per_cell),
            "--batch-size",
            str(args.batch_size),
            "--max-new-tokens",
            str(args.max_new_tokens),
            "--device",
            "cuda:0",
            "--dtype",
            args.dtype,
        ]
        log_path = output_dir / f"shard_{shard_index:02d}.log"
        log_handle = log_path.open("w", encoding="utf-8")
        processes.append((shard_index, log_handle, subprocess.Popen(cmd, cwd=REPO_ROOT, env=env, stdout=log_handle, stderr=subprocess.STDOUT, text=True)))
    failed = []
    retry_candidates = []
    for shard_index, log_handle, process in processes:
        code = process.wait()
        log_handle.close()
        if code != 0:
            log_path = output_dir / f"shard_{shard_index:02d}.log"
            if args.batch_size > OOM_RETRY_BATCH_SIZE_PER_GPU and _log_has_oom(log_path):
                retry_candidates.append(shard_index)
            else:
                failed.append((shard_index, code))
    for shard_index in retry_candidates:
        shard_json = output_dir / f"shard_{shard_index:02d}.json"
        if shard_json.exists():
            shard_json.unlink()
        code, retry_log = _launch_shard(args, output_dir, shard_index, OOM_RETRY_BATCH_SIZE_PER_GPU, "_retry_batch1")
        if code != 0:
            failed.append((shard_index, code, str(retry_log)))
    if failed:
        raise SystemExit(f"failed shards: {failed}")
    merge(output_dir, args.num_shards)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-8gpu", action="store_true")
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--num-shards", type=int, default=8)
    parser.add_argument("--output-dir", default="results/rung1_separator_llm_po/p1a_forward_gate_shards")
    parser.add_argument("--n-per-cell", type=int, default=DEFAULT_N_PER_CELL)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE_PER_GPU)
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--python-bin", default=str(REPO_ROOT / ".venv/bin/python"))
    args = parser.parse_args()
    output_dir = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO_ROOT / args.output_dir
    if args.launch_8gpu:
        launch_8gpu(args)
    elif args.merge:
        merge(output_dir, args.num_shards)
    else:
        if args.shard_index is None:
            raise SystemExit("provide --shard-index or use --launch-8gpu")
        run_shard(args.shard_index, args.num_shards, output_dir, args.n_per_cell, args.batch_size, args.max_new_tokens, args.device, args.dtype)


if __name__ == "__main__":
    main()
