"""P1c unguarded operator truncation pilot for Rung-1 separator fallibility."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
from statistics import mean, median
import sys
from typing import Any

import torch
from tqdm.auto import tqdm

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _adjacency, _rel
from experiments.rung1_separator_llm_po_forward_gate import MODEL_ID, QWEN35_DOWNLOAD_PATH, SEPARATOR_RESULTS_PATH, _last_json, _load_model, _read_json, _trim_tokens


RESULTS_ROOT = REPO_ROOT / "results/rung1_separator_fallibility_rungs"
PILOT_RESULTS_PATH = RESULTS_ROOT / "p1c_truncation_pilot.json"
SHARD_DIR = RESULTS_ROOT / "p1c_truncation_pilot_shards"
SCHEMA_VERSION = "rung1_separator_p1c_truncation_pilot_v0"
RUNG = "P1c_operator_triggered_unguarded"
DEFAULT_N_PER_CELL = 12
DEFAULT_CALL_CAP = 200
DEFAULT_PILOT_STEPS_PER_INSTANCE = 1
DEFAULT_MAX_NEW_TOKENS = 12288
DEFAULT_BATCH_SIZE_PER_GPU = 1
TRUNCATION_RATE_THRESHOLD = 0.10
THINKING_DISABLED = False
PROMPT_CONTRACT = "p1c_unguarded_branch_propagation_conflict_culprit_v0"
PROMPT_CONTRACT_V1 = "p1c_unguarded_structured_json_no_thinking_v1"
PROMPT_CONTRACT_V2 = "p1c_unguarded_structured_json_capped_thinking_v2"
B_PILOT_BINS = (12,)
OPERATOR_VERSION = "p1c_unguarded_v0"
OPERATOR_VERSION_V1 = "p1c_unguarded_structured_no_thinking_v1"
OPERATOR_VERSION_V2 = "p1c_unguarded_structured_capped_thinking_v2"
DEFAULT_OPERATOR_VERSION = OPERATOR_VERSION_V1
OPERATOR_VERSIONS = {OPERATOR_VERSION, OPERATOR_VERSION_V1, OPERATOR_VERSION_V2}
THINKING_BUDGET_REQUESTED_V2 = 3000
ANSWER_TOKEN_BUDGET_REQUESTED_V2 = 1500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _initial_domains(row: dict[str, Any]) -> dict[int, set[int]]:
    colors = set(range(1, int(row["k"]) + 1))
    return {vertex: set(colors) for vertex in range(int(row["n_vertices"]))}


def _visible_context(episode: dict[str, Any], vertex: int) -> dict[str, Any]:
    """Compute visible context for P1c operator: own block and boundary vertices."""
    row = episode["row"]
    block = int(row["partitions"][vertex])
    own_vertices = [idx for idx, part in enumerate(row["partitions"]) if int(part) == block]
    own_set = set(own_vertices)
    internal_edges = [edge for edge in row["edges"] if int(edge[0]) in own_set and int(edge[1]) in own_set]
    boundary_edges = [edge for edge in row["edges"] if (int(edge[0]) in own_set) ^ (int(edge[1]) in own_set)]
    visible_assignment = {}
    boundary_vertices = set()
    for u, v in boundary_edges:
        boundary_vertices.update([int(u), int(v)])
    visible_vertices = own_set | boundary_vertices
    for assigned_vertex, color in episode["assignment"].items():
        if assigned_vertex in visible_vertices:
            visible_assignment[assigned_vertex] = color
    return {
        "agent_block": block,
        "own_block_vertices": own_vertices,
        "internal_edges": internal_edges,
        "incident_boundary_edges": boundary_edges,
        "visible_assignment": dict(sorted(visible_assignment.items())),
    }


def _prompt_p1c_unguarded(episode: dict[str, Any]) -> str:
    """P1c unguarded operator prompt: branch + propagation + conflict detection + culprit."""
    row = episode["row"]
    order = episode["order"]
    cursor = episode.get("cursor", 0)
    if cursor >= len(order):
        return ""
    vertex = order[cursor]
    context = _visible_context(episode, vertex)
    colors = list(range(1, int(row["k"]) + 1))
    return "\n".join([
        "P1c unguarded local graph-coloring operator.",
        "You are in charge of branch selection, propagation, conflict detection, and culprit identification.",
        "Task: choose a branch color for the current vertex; perform local propagation; detect conflicts; if a conflict is found, identify a culprit vertex.",
        "Use only internal_edges, incident_boundary_edges, and visible_assignment. Do not use any hidden oracle.",
        "Return exactly one JSON object at the end with this schema:",
        "{\"color\": <int in 1..k>, \"propagation\": [{\"vertex\": <int>, \"remaining_domain\": [<colors>], \"reason\": <short string>}], \"conflict_detected\": <bool>, \"culprit\": <int or null>, \"conflict_reason\": <short string>, \"notes\": <short string>}",
        "Rules:",
        "- color: the color you select for current_vertex; must be in 1..k.",
        "- propagation: list every own_block_vertices vertex with its remaining valid domain after the branch.",
        "- For current_vertex, remaining_domain must be the chosen singleton color.",
        "- conflict_detected: true if visible constraints are unsatisfiable after the branch.",
        "- culprit: if conflict detected, one vertex whose assignment caused it.",
        "- conflict_reason: one sentence explaining the conflict.",
        "- notes: short summary, under 20 words.",
        f"colors={colors}; current_vertex={vertex}; agent_block={context['agent_block']}",
        f"own_block_vertices={context['own_block_vertices']}",
        f"internal_edges={context['internal_edges']}",
        f"incident_boundary_edges={context['incident_boundary_edges']}",
        f"visible_assignment={context['visible_assignment']}",
    ])


def _prompt_p1c_unguarded_v1(episode: dict[str, Any]) -> str:
    """Compact P1c prompt: same unguarded operator, JSON-only answer."""
    row = episode["row"]
    order = episode["order"]
    cursor = episode.get("cursor", 0)
    if cursor >= len(order):
        return ""
    vertex = order[cursor]
    context = _visible_context(episode, vertex)
    colors = list(range(1, int(row["k"]) + 1))
    return "\n".join([
        "Unguarded graph-coloring operator. Return JSON only, no reasoning.",
        "Choose color for current_vertex, update local domains, detect visible conflict, and name one culprit if conflict=true.",
        "Schema: {\"color\":int,\"propagation\":[{\"vertex\":int,\"remaining_domain\":[int]}],\"conflict_detected\":bool,\"culprit\":int|null,\"conflict_reason\":str}",
        "Use only the supplied local/boundary context. No hidden oracle. No markdown.",
        f"colors={colors}",
        f"current_vertex={vertex}",
        f"agent_block={context['agent_block']}",
        f"own_block_vertices={context['own_block_vertices']}",
        f"internal_edges={context['internal_edges']}",
        f"incident_boundary_edges={context['incident_boundary_edges']}",
        f"visible_assignment={context['visible_assignment']}",
    ])


def _prompt_for_operator(episode: dict[str, Any], operator_version: str) -> str:
    if operator_version in {OPERATOR_VERSION_V1, OPERATOR_VERSION_V2}:
        return _prompt_p1c_unguarded_v1(episode)
    return _prompt_p1c_unguarded(episode)


def _prompt_contract(operator_version: str) -> str:
    if operator_version == OPERATOR_VERSION_V2:
        return PROMPT_CONTRACT_V2
    if operator_version == OPERATOR_VERSION_V1:
        return PROMPT_CONTRACT_V1
    return PROMPT_CONTRACT


def _thinking_disabled(operator_version: str) -> bool:
    return operator_version == OPERATOR_VERSION_V1


def _thinking_budget(operator_version: str) -> int | None:
    return THINKING_BUDGET_REQUESTED_V2 if operator_version == OPERATOR_VERSION_V2 else 0 if operator_version == OPERATOR_VERSION_V1 else None


def _answer_budget(operator_version: str) -> int | None:
    return ANSWER_TOKEN_BUDGET_REQUESTED_V2 if operator_version == OPERATOR_VERSION_V2 else None


def _parse_last_json(text: str) -> dict[str, Any]:
    parsed = _last_json(text)
    if isinstance(parsed, tuple):
        return parsed[0] or {}
    return parsed or {}


def _format_chat(tokenizer: Any, prompt: str, operator_version: str) -> str:
    if hasattr(tokenizer, "apply_chat_template"):
        if _thinking_disabled(operator_version):
            for kwargs in ({"enable_thinking": False}, {}):
                try:
                    return tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True, **kwargs)
                except TypeError:
                    continue
        if operator_version == OPERATOR_VERSION_V2:
            for kwargs in ({"enable_thinking": True, "thinking_budget": THINKING_BUDGET_REQUESTED_V2}, {"enable_thinking": True}, {}):
                try:
                    return tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True, **kwargs)
                except TypeError:
                    continue
        return tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True)
    return prompt


@torch.no_grad()
def _generate_batch_p1c(model: Any, tokenizer: Any, prompts: list[str], max_new_tokens: int, operator_version: str) -> list[dict[str, Any]]:
    """Generate from P1c unguarded operator (no capped thinking)."""
    formatted = [_format_chat(tokenizer, prompt, operator_version) for prompt in prompts]
    if operator_version == OPERATOR_VERSION_V2:
        thinking_inputs = tokenizer(formatted, return_tensors="pt", padding=True, truncation=True).to(model.device)
        thinking_generated = model.generate(
            **thinking_inputs,
            do_sample=False,
            temperature=None,
            top_p=None,
            max_new_tokens=THINKING_BUDGET_REQUESTED_V2,
            pad_token_id=tokenizer.eos_token_id,
        )
        thinking_tokens = thinking_generated[:, thinking_inputs["input_ids"].shape[1]:]
        contexts = []
        thinking_parts = []
        for prompt, token_ids in zip(formatted, thinking_tokens.tolist()):
            trimmed, thinking_finish_reason = _trim_tokens(token_ids, tokenizer.eos_token_id, THINKING_BUDGET_REQUESTED_V2)
            thinking_text = tokenizer.decode(trimmed, skip_special_tokens=True)
            if "</think>" in thinking_text:
                thinking_text = thinking_text[:thinking_text.index("</think>") + len("</think>")]
            else:
                thinking_text = thinking_text.rstrip() + "\n</think>"
            contexts.append(prompt + thinking_text + "\n\n")
            thinking_parts.append({"text": thinking_text, "tokens": len(trimmed), "finish_reason": thinking_finish_reason})
        answer_inputs = tokenizer(contexts, return_tensors="pt", padding=True, truncation=True).to(model.device)
        answer_generated = model.generate(
            **answer_inputs,
            do_sample=False,
            temperature=None,
            top_p=None,
            max_new_tokens=ANSWER_TOKEN_BUDGET_REQUESTED_V2,
            pad_token_id=tokenizer.eos_token_id,
        )
        answer_tokens = answer_generated[:, answer_inputs["input_ids"].shape[1]:]
        out = []
        for thinking, token_ids in zip(thinking_parts, answer_tokens.tolist()):
            trimmed, answer_finish_reason = _trim_tokens(token_ids, tokenizer.eos_token_id, ANSWER_TOKEN_BUDGET_REQUESTED_V2)
            answer_text = tokenizer.decode(trimmed, skip_special_tokens=True)
            out.append({
                "text": thinking["text"] + "\n\n" + answer_text,
                "output_tokens": int(thinking["tokens"]) + len(trimmed),
                "thinking_tokens": int(thinking["tokens"]),
                "answer_tokens": len(trimmed),
                "thinking_finish_reason": thinking["finish_reason"],
                "answer_finish_reason": answer_finish_reason,
                "finish_reason": answer_finish_reason,
            })
        return out
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
        out.append({
            "text": tokenizer.decode(trimmed, skip_special_tokens=True),
            "output_tokens": len(trimmed),
            "finish_reason": finish_reason,
        })
    return out


def _read_separator_manifest() -> list[dict[str, Any]]:
    """Load separator manifest and select deepest b=12 cells for P1c pilot."""
    data = _read_json(SEPARATOR_RESULTS_PATH)
    if not data:
        return []
    
    acceptance = data.get("acceptance", {})
    if (data.get("schema_version") != "rung1_separator_scaling_symbolic_v0_2_3" or 
        not acceptance.get("overall_pass") or 
        not acceptance.get("fairness_corner_clean")):
        print("Warning: symbolic separator v0.2.3 fairness gate may not be fully passed")
    
    manifest = data.get("instance_manifest", [])
    if not manifest:
        return []
    
    # Select deepest b=12 cells
    by_b = [row for row in manifest if int(row.get("b", 0)) == 12]
    if not by_b:
        return []
    
    max_d = max(int(row.get("d_global_reference", 0)) for row in by_b)
    deepest = [row for row in by_b if int(row.get("d_global_reference", 0)) == max_d]
    
    # Group by cell and select one cell
    deepest_by_cell: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in deepest:
        deepest_by_cell[row.get("cell_id", "unknown")].append(row)
    
    if not deepest_by_cell:
        return []
    
    selected_cell = sorted(deepest_by_cell.keys())[0]
    return deepest_by_cell[selected_cell]


def _collect_pilot_instances(num_per_cell: int = 12) -> list[dict[str, Any]]:
    """Collect instances for P1c pilot from separator manifest."""
    manifest = _read_separator_manifest()
    if not manifest:
        return []
    return manifest[:num_per_cell]


def _run_pilot_on_device(device: str, instances: list[dict[str, Any]], max_new_tokens: int, operator_version: str) -> list[dict[str, Any]]:
    """Run P1c pilot on instances on specified device."""
    print(json.dumps({"event": "p1c_shard_start", "device": device, "n_instances": len(instances), "max_new_tokens": max_new_tokens, "operator_version": operator_version}), flush=True)
    model, tokenizer, _ = _load_model(device, "auto")
    if not tokenizer:
        return []
    
    results = []
    
    try:
        for row_index, row in enumerate(instances):
            print(json.dumps({"event": "p1c_instance_start", "device": device, "row_index": row_index, "instance_id": row.get("instance_id", "unknown")}), flush=True)
            n_vertices = int(row["n_vertices"])
            edges = tuple(tuple(int(x) for x in edge) for edge in row["edges"])
            adjacency = _adjacency(n_vertices, edges)
            order = sorted(range(n_vertices))
            domains = _initial_domains(row)
            
            episode = {
                "row": row,
                "adjacency": adjacency,
                "order": order,
                "domains": domains,
                "assignment": {},
                "cursor": 0,
                "calls": 0,
                "generations": [],
            }
            
            for step in range(DEFAULT_PILOT_STEPS_PER_INSTANCE):
                if episode["cursor"] >= len(episode["order"]):
                    break
                
                prompt = _prompt_for_operator(episode, operator_version)
                if not prompt:
                    break
                
                gens = _generate_batch_p1c(model, tokenizer, [prompt], max_new_tokens, operator_version)
                if not gens:
                    break
                
                gen = gens[0]
                episode["calls"] += 1
                episode["generations"].append(gen)
                episode["cursor"] += 1
                
                if gen.get("finish_reason") == "length":
                    break
            
            truncated_count = sum(1 for g in episode["generations"] if g.get("finish_reason") == "length")
            frac_truncated = truncated_count / max(1, episode["calls"])
            results.append({
                "instance_id": row.get("instance_id", "unknown"),
                "calls": episode["calls"],
                "truncated_generations": truncated_count,
                "frac_truncated_no_answer": frac_truncated,
                "frac_parsable": sum(1 for g in episode["generations"] if _parse_last_json(g["text"])) / max(1, episode["calls"]),
            })
            print(json.dumps({"event": "p1c_instance_done", "device": device, "row_index": row_index, "instance_id": row.get("instance_id", "unknown"), "calls": episode["calls"], "truncated_generations": truncated_count}), flush=True)
            if frac_truncated > TRUNCATION_RATE_THRESHOLD:
                print(json.dumps({"event": "p1c_shard_early_stop_gate_failure", "device": device, "row_index": row_index, "frac_truncated_no_answer": frac_truncated, "threshold": TRUNCATION_RATE_THRESHOLD}), flush=True)
                break
    finally:
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    return results


def run_shard(shard_index: int, num_shards: int, output_dir: str | None, num_per_cell: int, max_new_tokens: int, device: str, operator_version: str) -> dict[str, Any]:
    """Run one P1c pilot shard and write a shard artifact."""
    output_root = Path(output_dir).absolute() if output_dir else RESULTS_ROOT
    shard_dir = output_root / "p1c_truncation_pilot_shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    instances = _collect_pilot_instances(num_per_cell)
    shard_instances = instances[shard_index::num_shards]
    rows = _run_pilot_on_device(device, shard_instances, max_new_tokens, operator_version)
    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "shard_index": shard_index,
        "num_shards": num_shards,
        "device": device,
        "max_new_tokens": max_new_tokens,
        "num_per_cell": num_per_cell,
        "operator_version": operator_version,
        "prompt_contract": _prompt_contract(operator_version),
        "instance_rows": rows,
        "status": "P1C_TRUNCATION_PILOT_SHARD_COMPLETE",
    }
    _write_json(shard_dir / f"shard_{shard_index:02d}.json", result)
    return result


def _launch_shards(num_shards: int, num_per_cell: int, max_new_tokens: int, output_dir: Path, operator_version: str) -> list[dict[str, Any]]:
    """Launch P1c shards as separate processes so CUDA devices are used concurrently."""
    shard_dir = output_dir / "p1c_truncation_pilot_shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    for stale in shard_dir.glob("shard_*.json"):
        stale.unlink()
    processes = []
    cuda_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
    for shard_index in range(num_shards):
        device = f"cuda:{shard_index % cuda_count}" if cuda_count else "cpu"
        cmd = [
            sys.executable,
            "-u",
            "-m",
            "experiments.rung1_separator_p1c_truncation_pilot",
            "--shard-index",
            str(shard_index),
            "--num-shards",
            str(num_shards),
            "--num-per-cell",
            str(num_per_cell),
            "--max-new-tokens",
            str(max_new_tokens),
            "--output-dir",
            str(output_dir),
            "--device",
            device,
            "--operator-version",
            operator_version,
        ]
        print(json.dumps({"event": "p1c_launch_shard", "shard_index": shard_index, "device": device, "cmd": cmd}), flush=True)
        processes.append(subprocess.Popen(cmd, cwd=str(REPO_ROOT)))
    failures = []
    for shard_index, process in enumerate(processes):
        return_code = process.wait()
        if return_code != 0:
            failures.append({"shard_index": shard_index, "return_code": return_code})
    if failures:
        raise RuntimeError(f"P1c shard failures: {failures}")
    shard_payloads = []
    for shard_index in range(num_shards):
        shard_path = shard_dir / f"shard_{shard_index:02d}.json"
        shard_payload = _read_json(shard_path)
        if shard_payload:
            shard_payloads.append(shard_payload)
    return shard_payloads


def run(num_shards: int = 1, num_per_cell: int = DEFAULT_N_PER_CELL, max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS, output_dir: str | None = None, operator_version: str = DEFAULT_OPERATOR_VERSION) -> dict[str, Any]:
    """Main entry point for P1c truncation pilot."""
    if operator_version not in OPERATOR_VERSIONS:
        raise ValueError(f"unknown operator_version={operator_version}; expected one of {sorted(OPERATOR_VERSIONS)}")
    if output_dir:
        global RESULTS_ROOT, PILOT_RESULTS_PATH, SHARD_DIR
        RESULTS_ROOT = Path(output_dir).absolute()
        PILOT_RESULTS_PATH = RESULTS_ROOT / "p1c_truncation_pilot.json"
        SHARD_DIR = RESULTS_ROOT / "p1c_truncation_pilot_shards"
    
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    
    instances = _collect_pilot_instances(num_per_cell)
    if not instances:
        result = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _now(),
            "status": "RUNG1_SEPARATOR_P1C_TRUNCATION_PILOT_NO_DATA",
            "message": "No instances collected from separator manifest",
        }
        _write_json(PILOT_RESULTS_PATH, result)
        return result
    
    if num_shards > 1:
        shard_payloads = _launch_shards(num_shards, num_per_cell, max_new_tokens, RESULTS_ROOT, operator_version)
        all_results = [row for payload in shard_payloads for row in payload.get("instance_rows", [])]
    else:
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        all_results = _run_pilot_on_device(device, instances, max_new_tokens, operator_version)
    
    max_truncation_frac = max((r.get("frac_truncated_no_answer", 0) for r in all_results), default=0)
    truncation_gate_pass = max_truncation_frac <= TRUNCATION_RATE_THRESHOLD
    
    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": "RUNG1_SEPARATOR_P1C_TRUNCATION_PILOT_PASS" if truncation_gate_pass else "RUNG1_SEPARATOR_P1C_TRUNCATION_PILOT_FAIL",
        "generation_config": {
            "model_id": MODEL_ID,
            "max_new_tokens": max_new_tokens,
            "thinking_disabled": _thinking_disabled(operator_version),
            "prompt_contract": _prompt_contract(operator_version),
            "operator_version": operator_version,
            "thinking_budget_requested": _thinking_budget(operator_version),
            "answer_token_budget_requested": _answer_budget(operator_version),
            "n_per_cell": num_per_cell,
            "pilot_steps": DEFAULT_PILOT_STEPS_PER_INSTANCE,
            "n_shards": num_shards,
            "early_stop_on_gate_failure": True,
        },
        "acceptance": {
            "p1c_truncation_gate_pass": truncation_gate_pass,
            "max_truncation_frac": max_truncation_frac,
            "truncation_threshold": TRUNCATION_RATE_THRESHOLD,
        },
        "prelaunch_truncation_gate": [
            {
                "max_frac_truncated_no_answer": max_truncation_frac,
                "pass": truncation_gate_pass,
                "threshold": TRUNCATION_RATE_THRESHOLD,
                "provenance": "qwen35_p1c_truncation_gate_v0",
                "source": SOURCE,
            }
        ],
        "instance_rows": all_results,
        "verdict": [
            {
                "check": "p1c_truncation_pass",
                "predicted": f"max frac_truncated_no_answer <= {TRUNCATION_RATE_THRESHOLD:.2f}",
                "observed": f"max_frac={max_truncation_frac:.4f}",
                "pass": truncation_gate_pass,
                "source": SOURCE,
                "provenance": "p1c_truncation_verdict_v0",
            }
        ],
    }
    
    _write_json(PILOT_RESULTS_PATH, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="P1c unguarded truncation pilot for Rung-1 separator fallibility.")
    parser.add_argument("--shard-index", type=int, default=None)
    parser.add_argument("--num-shards", type=int, default=4)
    parser.add_argument("--num-per-cell", type=int, default=DEFAULT_N_PER_CELL)
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    parser.add_argument("--output-dir", default=str(RESULTS_ROOT))
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--operator-version", choices=sorted(OPERATOR_VERSIONS), default=DEFAULT_OPERATOR_VERSION)
    args = parser.parse_args()
    if args.shard_index is not None:
        run_shard(
            shard_index=args.shard_index,
            num_shards=args.num_shards,
            output_dir=args.output_dir,
            num_per_cell=args.num_per_cell,
            max_new_tokens=args.max_new_tokens,
            device=args.device,
            operator_version=args.operator_version,
        )
        return
    run(
        num_shards=args.num_shards,
        num_per_cell=args.num_per_cell,
        max_new_tokens=args.max_new_tokens,
        output_dir=args.output_dir,
        operator_version=args.operator_version,
    )


if __name__ == "__main__":
    main()
