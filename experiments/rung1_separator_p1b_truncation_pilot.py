"""P1b verbose propagation truncation pilot for Rung-1 separator fallibility."""

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
from typing import Any

import torch
from tqdm.auto import tqdm

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _adjacency, _rel
from experiments.rung1_separator_llm_po_forward_gate import MODEL_ID, QWEN35_DOWNLOAD_PATH, SEPARATOR_RESULTS_PATH, _last_json, _load_model, _read_json, _trim_tokens


RESULTS_ROOT = REPO_ROOT / "results/rung1_separator_fallibility_rungs"
PILOT_RESULTS_PATH = RESULTS_ROOT / "p1b_truncation_pilot.json"
RAW_INSPECTION_RESULTS_PATH = RESULTS_ROOT / "p1b_raw_generation_inspection.json"
SCHEMA_VERSION = "rung1_separator_p1b_truncation_pilot_v0"
SCHEMA_VERSION_V1 = "rung1_separator_p1b_truncation_pilot_v1"
SCHEMA_VERSION_V1_1 = "rung1_separator_p1b_truncation_pilot_v1_1"
RAW_INSPECTION_SCHEMA_VERSION = "rung1_separator_p1b_raw_generation_inspection_v0"
RUNG = "P1b_llm_propagation_guarded"
DEFAULT_N_PER_CELL = 24
DEFAULT_CALL_CAP = 200
DEFAULT_PILOT_STEPS_PER_INSTANCE = 2
DEFAULT_MAX_NEW_TOKENS = 8192
DEFAULT_BATCH_SIZE_PER_GPU = 1
TRUNCATION_RATE_THRESHOLD = 0.10
FUNCTIONAL_GATE_THRESHOLD = 0.20
THINKING_BUDGET_REQUESTED = 2500
ANSWER_TOKEN_BUDGET_REQUESTED = 1500
PROMPT_CONTRACT = "p1b_verbose_branch_and_local_propagation_guarded_v0"
PROMPT_CONTRACT_V1 = "p1b_bounded_structured_domain_propagation_guarded_v1"
PROMPT_CONTRACT_V1_1 = "p1b_bounded_structured_domain_propagation_capped_thinking_v1_1"
RAW_INSPECTION_DEFAULT_N = 8
B_PILOT_BINS = (2, 4, 8, 12)
OPERATOR_VERSIONS = {"v0", "v1", "v1_1"}


def _schema_version(operator_version: str) -> str:
    if operator_version == "v1_1":
        return SCHEMA_VERSION_V1_1
    return SCHEMA_VERSION_V1 if operator_version == "v1" else SCHEMA_VERSION


def _prompt_contract(operator_version: str) -> str:
    if operator_version == "v1_1":
        return PROMPT_CONTRACT_V1_1
    return PROMPT_CONTRACT_V1 if operator_version == "v1" else PROMPT_CONTRACT


def _structured_operator(operator_version: str) -> bool:
    return operator_version in {"v1", "v1_1"}


def _thinking_disabled(operator_version: str) -> bool:
    return operator_version == "v1"


def _thinking_budget(operator_version: str) -> int | None:
    return THINKING_BUDGET_REQUESTED if operator_version == "v1_1" else 0 if operator_version == "v1" else None


def _answer_budget(operator_version: str) -> int | None:
    return ANSWER_TOKEN_BUDGET_REQUESTED if _structured_operator(operator_version) else None


def _provenance(base: str, operator_version: str) -> str:
    return f"{base}_{operator_version}"


@dataclass
class Episode:
    row: dict[str, Any]
    adjacency: dict[int, set[int]]
    order: list[int]
    domains: dict[int, set[int]]
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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _format_chat(tokenizer: Any, prompt: str, operator_version: str) -> str:
    if hasattr(tokenizer, "apply_chat_template"):
        if operator_version == "v1":
            for kwargs in (
                {"enable_thinking": False},
                {},
            ):
                try:
                    return tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True, **kwargs)
                except TypeError:
                    continue
        if operator_version == "v1_1":
            for kwargs in (
                {"enable_thinking": True, "thinking_budget": THINKING_BUDGET_REQUESTED},
                {"enable_thinking": True},
                {},
            ):
                try:
                    return tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True, **kwargs)
                except TypeError:
                    continue
        return tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True)
    return prompt


@torch.no_grad()
def _generate_batch(model: Any, tokenizer: Any, prompts: list[str], max_new_tokens: int, operator_version: str = "v0") -> list[dict[str, Any]]:
    formatted = [_format_chat(tokenizer, prompt, operator_version) for prompt in prompts]
    if operator_version == "v1_1":
        thinking_inputs = tokenizer(formatted, return_tensors="pt", padding=True, truncation=True).to(model.device)
        thinking_generated = model.generate(
            **thinking_inputs,
            do_sample=False,
            temperature=None,
            top_p=None,
            max_new_tokens=THINKING_BUDGET_REQUESTED,
            pad_token_id=tokenizer.eos_token_id,
        )
        thinking_tokens = thinking_generated[:, thinking_inputs["input_ids"].shape[1]:]
        contexts = []
        thinking_parts = []
        for prompt, token_ids in zip(formatted, thinking_tokens.tolist()):
            trimmed, thinking_finish_reason = _trim_tokens(token_ids, tokenizer.eos_token_id, THINKING_BUDGET_REQUESTED)
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
            max_new_tokens=ANSWER_TOKEN_BUDGET_REQUESTED,
            pad_token_id=tokenizer.eos_token_id,
        )
        answer_tokens = answer_generated[:, answer_inputs["input_ids"].shape[1]:]
        out = []
        for thinking, token_ids in zip(thinking_parts, answer_tokens.tolist()):
            trimmed, answer_finish_reason = _trim_tokens(token_ids, tokenizer.eos_token_id, ANSWER_TOKEN_BUDGET_REQUESTED)
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
        out.append({"text": tokenizer.decode(trimmed, skip_special_tokens=True), "output_tokens": len(trimmed), "thinking_tokens": None, "answer_tokens": len(trimmed), "thinking_finish_reason": None, "answer_finish_reason": finish_reason, "finish_reason": finish_reason})
    return out


def _initial_domains(row: dict[str, Any]) -> dict[int, set[int]]:
    colors = set(range(1, int(row["k"]) + 1))
    return {vertex: set(colors) for vertex in range(int(row["n_vertices"]))}


def _visible_context(episode: Episode, vertex: int) -> dict[str, Any]:
    row = episode.row
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
    for assigned_vertex, color in episode.assignment.items():
        if assigned_vertex in visible_vertices:
            visible_assignment[assigned_vertex] = color
    return {
        "agent_block": block,
        "own_block_vertices": own_vertices,
        "internal_edges": internal_edges,
        "incident_boundary_edges": boundary_edges,
        "visible_assignment": dict(sorted(visible_assignment.items())),
    }


def _prompt(episode: Episode) -> str:
    row = episode.row
    vertex = episode.order[episode.cursor]
    context = _visible_context(episode, vertex)
    return "\n".join([
        "P1b local graph-coloring operator with fallible propagation.",
        "You may reason. Choose a branch color for the current vertex and propose local propagation prunes implied by visible assignments and edges.",
        "A separate symbolic guard will reject unsound prunes, but it will not add prunes you miss.",
        "Do not assume global graph visibility. Use only the block, boundary edges, and visible assignments below.",
        "Return a JSON object at the end with this schema:",
        "{\"color\": <integer color in 1..k>, \"prunes\": [{\"vertex\": <int>, \"color\": <int>, \"reason\": <short string>}], \"notes\": <short string>}",
        f"k={row['k']}; current_vertex={vertex}; agent_block={context['agent_block']}",
        f"own_block_vertices={context['own_block_vertices']}",
        f"internal_edges={context['internal_edges']}",
        f"incident_boundary_edges={context['incident_boundary_edges']}",
        f"visible_assignment={context['visible_assignment']}",
    ])


def _prompt_v1(episode: Episode) -> str:
    row = episode.row
    vertex = episode.order[episode.cursor]
    context = _visible_context(episode, vertex)
    colors = list(range(1, int(row["k"]) + 1))
    return "\n".join([
        "P1b bounded structured local graph-coloring operator.",
        "Task: choose one branch color for current_vertex, then compute local propagation over own_block_vertices only.",
        "Use only internal_edges, incident_boundary_edges, and visible_assignment. Do not use any hidden oracle, guard output, or feasible-domain answer.",
        "The symbolic guard will later reject unsound prunes; it will not add any prune you miss.",
        "Provide reasoning only inside each propagation reason field; do not print free-form reasoning, markdown, code fences, or schema discussion.",
        "Return exactly one JSON object and nothing else.",
        "JSON schema:",
        "{\"color\": <integer in colors>, \"propagation\": [{\"vertex\": <own-block int>, \"remaining_domain\": [<colors still possible after visible constraints and the branch>], \"reason\": <one short sentence>}], \"notes\": <short string>}",
        "Rules:",
        "- Include each own_block_vertices vertex exactly once in propagation.",
        "- For current_vertex, remaining_domain must be the chosen singleton color.",
        "- For other own-block vertices, remove colors forced impossible by visible_assignment, internal_edges, incident_boundary_edges, and the chosen branch.",
        "- Do not emit boundary vertices in propagation.",
        "- Each reason must be one short sentence, at most 12 words.",
        "- Keep notes under 20 words.",
        f"colors={colors}; current_vertex={vertex}; agent_block={context['agent_block']}",
        f"own_block_vertices={context['own_block_vertices']}",
        f"internal_edges={context['internal_edges']}",
        f"incident_boundary_edges={context['incident_boundary_edges']}",
        f"visible_assignment={context['visible_assignment']}",
    ])


def _prompt_v1_1(episode: Episode) -> str:
    row = episode.row
    vertex = episode.order[episode.cursor]
    context = _visible_context(episode, vertex)
    colors = list(range(1, int(row["k"]) + 1))
    return "\n".join([
        "P1b bounded structured local graph-coloring operator with capped thinking.",
        "Use private reasoning to compute propagation, but keep it concise and bounded.",
        f"Thinking budget request: <= {THINKING_BUDGET_REQUESTED} tokens. Final answer budget request: <= {ANSWER_TOKEN_BUDGET_REQUESTED} tokens.",
        "Task: choose one branch color for current_vertex, then compute local propagation over own_block_vertices only.",
        "Use only internal_edges, incident_boundary_edges, and visible_assignment. Do not use any hidden oracle, guard output, or feasible-domain answer.",
        "The symbolic guard will later reject unsound prunes; it will not add any prune you miss.",
        "Return the final answer as the last parseable JSON object, with no markdown or code fence around it.",
        "JSON schema:",
        "{\"color\": <integer in colors>, \"propagation\": [{\"vertex\": <own-block int>, \"remaining_domain\": [<colors still possible after visible constraints and the branch>], \"reason\": <one short sentence>}], \"notes\": <short string>}",
        "Rules:",
        "- Include each own_block_vertices vertex exactly once in propagation.",
        "- For current_vertex, remaining_domain must be the chosen singleton color.",
        "- For other own-block vertices, remove colors impossible from visible_assignment, internal_edges, incident_boundary_edges, and the chosen branch.",
        "- Do not emit boundary vertices in propagation.",
        "- Each reason must be one short sentence, at most 12 words.",
        "- Keep notes under 20 words.",
        f"colors={colors}; current_vertex={vertex}; agent_block={context['agent_block']}",
        f"own_block_vertices={context['own_block_vertices']}",
        f"internal_edges={context['internal_edges']}",
        f"incident_boundary_edges={context['incident_boundary_edges']}",
        f"visible_assignment={context['visible_assignment']}",
    ])


def _operator_prompt(episode: Episode, operator_version: str) -> str:
    if operator_version == "v1_1":
        return _prompt_v1_1(episode)
    return _prompt_v1(episode) if operator_version == "v1" else _prompt(episode)


def _live_domain(episode: Episode, vertex: int) -> set[int]:
    if vertex in episode.assignment:
        return set()
    live = set(episode.domains[vertex])
    for neighbor in episode.adjacency[vertex]:
        assigned = episode.assignment.get(neighbor)
        if assigned in live:
            live.remove(assigned)
    return live


def _parse_prunes(parsed: dict[str, Any]) -> list[tuple[int, int]]:
    raw = parsed.get("prunes", parsed.get("prune", []))
    prunes: list[tuple[int, int]] = []
    if isinstance(raw, dict):
        for vertex_text, colors in raw.items():
            try:
                vertex = int(vertex_text)
            except Exception:
                continue
            if isinstance(colors, int) and not isinstance(colors, bool):
                prunes.append((vertex, colors))
            elif isinstance(colors, list):
                for color in colors:
                    if isinstance(color, int) and not isinstance(color, bool):
                        prunes.append((vertex, color))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                vertex = item.get("vertex")
                color = item.get("color")
                if isinstance(vertex, int) and not isinstance(vertex, bool) and isinstance(color, int) and not isinstance(color, bool):
                    prunes.append((vertex, color))
            elif isinstance(item, list) and len(item) >= 2 and all(isinstance(value, int) and not isinstance(value, bool) for value in item[:2]):
                prunes.append((item[0], item[1]))
    return prunes


def _operator_json(text: str, operator_version: str) -> tuple[dict[str, Any] | None, int | None]:
    decoder = json.JSONDecoder()
    candidates: list[tuple[dict[str, Any], int]] = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            candidates.append((parsed, index))
    if not candidates:
        return None, None
    if _structured_operator(operator_version):
        for parsed, index in candidates:
            if ("color" in parsed or "branch_color" in parsed) and any(key in parsed for key in ("propagation", "remaining_domains", "domains")):
                return parsed, index
    for parsed, index in candidates:
        if "color" in parsed or "branch_color" in parsed:
            return parsed, index
    return candidates[-1]


def _parse_remaining_domain_prunes(parsed: dict[str, Any], k: int) -> list[tuple[int, int]]:
    entries = parsed.get("propagation", parsed.get("remaining_domains", parsed.get("domains", [])))
    parsed_domains: list[tuple[int, set[int]]] = []
    if isinstance(entries, dict):
        iterable = entries.items()
        for vertex_text, domain in iterable:
            try:
                vertex = int(vertex_text)
            except Exception:
                continue
            if isinstance(domain, dict):
                domain = domain.get("remaining_domain", domain.get("domain", domain.get("colors", [])))
            if isinstance(domain, list):
                remaining = {int(color) for color in domain if isinstance(color, int) and not isinstance(color, bool) and 1 <= int(color) <= k}
                parsed_domains.append((vertex, remaining))
    elif isinstance(entries, list):
        for item in entries:
            if not isinstance(item, dict):
                continue
            vertex = item.get("vertex")
            domain = item.get("remaining_domain", item.get("domain", item.get("colors", [])))
            if isinstance(vertex, int) and not isinstance(vertex, bool) and isinstance(domain, list):
                remaining = {int(color) for color in domain if isinstance(color, int) and not isinstance(color, bool) and 1 <= int(color) <= k}
                parsed_domains.append((int(vertex), remaining))
    all_colors = set(range(1, k + 1))
    prunes: list[tuple[int, int]] = []
    for vertex, remaining in parsed_domains:
        if not remaining:
            continue
        for color in sorted(all_colors - remaining):
            prunes.append((vertex, color))
    return prunes


def _parse_generation(generation: dict[str, Any], k: int, operator_version: str = "v0") -> dict[str, Any]:
    parsed, start = _operator_json(generation["text"], operator_version)
    if parsed is None:
        state = "truncated_no_answer" if generation["finish_reason"] == "length" else "format_failure"
        return {"generation_state": state, "color": None, "prunes": [], "json_start": None, "parseable": False, "valid": False}
    color = parsed.get("color", parsed.get("branch_color"))
    valid = isinstance(color, int) and not isinstance(color, bool) and 1 <= color <= k
    prunes = _parse_prunes(parsed)
    if _structured_operator(operator_version):
        prunes.extend(_parse_remaining_domain_prunes(parsed, k))
    return {"generation_state": "valid" if valid else "parsable_invalid", "color": color if valid else None, "prunes": sorted(set(prunes)), "json_start": start, "parseable": True, "valid": valid}


def _oracle_prunes(episode: Episode) -> set[tuple[int, int]]:
    prunes = set()
    for assigned_vertex, color in episode.assignment.items():
        for neighbor in episode.adjacency[assigned_vertex]:
            if neighbor not in episode.assignment and color in episode.domains[neighbor]:
                prunes.add((neighbor, color))
    return prunes


def _sound_prune(episode: Episode, vertex: int, color: int) -> bool:
    if vertex in episode.assignment or vertex not in episode.domains or color not in episode.domains[vertex]:
        return False
    return any(episode.assignment.get(neighbor) == color for neighbor in episode.adjacency[vertex])


def _apply_guarded_prunes(episode: Episode, proposed: list[tuple[int, int]]) -> dict[str, Any]:
    accepted = set()
    rejected = set()
    for vertex, color in proposed:
        if _sound_prune(episode, vertex, color):
            episode.domains[vertex].discard(color)
            accepted.add((vertex, color))
        else:
            rejected.add((vertex, color))
    oracle = _oracle_prunes(episode)
    missed = oracle - accepted
    if rejected:
        episode.operator_error_counts["unsound_propagation_rejected"] += len(rejected)
    if missed:
        episode.operator_error_counts["missed_propagation"] += len(missed)
    opportunity = bool(oracle)
    correct = opportunity and accepted == oracle and not rejected
    return {"accepted_prunes": sorted(accepted), "rejected_prunes": sorted(rejected), "missed_prunes": sorted(missed), "oracle_prunes": sorted(oracle), "propagation_opportunity": opportunity, "correct_propagation": correct}


def _step_episode(episode: Episode, generation: dict[str, Any], pilot_steps_per_instance: int, operator_version: str = "v0") -> None:
    if episode.status != "RUNNING":
        return
    if episode.calls >= DEFAULT_CALL_CAP:
        episode.status = "CALL_CAP"
        return
    vertex = episode.order[episode.cursor]
    live = _live_domain(episode, vertex)
    if not live:
        episode.status = "FORWARD_DEAD_END"
        return
    parsed = _parse_generation(generation, int(episode.row["k"]), operator_version)
    episode.calls += 1
    episode.generation_counts[parsed["generation_state"]] += 1
    chosen = parsed["color"]
    if parsed["generation_state"] in {"format_failure", "truncated_no_answer", "parsable_invalid"}:
        episode.operator_error_counts["format_failure"] += 1
        chosen = min(live)
    elif chosen not in live:
        episode.operator_error_counts["value_misselection"] += 1
        episode.distinct_attempts_by_vertex[vertex].add(int(chosen))
        chosen = min(live)
    episode.distinct_attempts_by_vertex[vertex].add(int(chosen))
    episode.assignment[vertex] = int(chosen)
    episode.domains[vertex] = {int(chosen)}
    prune_result = _apply_guarded_prunes(episode, parsed["prunes"])
    episode.trace.append({
        "vertex": vertex,
        "chosen_color": int(chosen),
        "llm_color": parsed["color"],
        "live_domain_size_before_branch": len(live),
        "n_proposed_prunes": len(parsed["prunes"]),
        "n_accepted_prunes": len(prune_result["accepted_prunes"]),
        "n_rejected_prunes": len(prune_result["rejected_prunes"]),
        "n_missed_prunes": len(prune_result["missed_prunes"]),
        "n_oracle_prunes": len(prune_result["oracle_prunes"]),
        "propagation_opportunity": bool(prune_result["propagation_opportunity"]),
        "correct_propagation": bool(prune_result["correct_propagation"]),
        "generation_state": parsed["generation_state"],
        "finish_reason": generation["finish_reason"],
        "thinking_finish_reason": generation.get("thinking_finish_reason"),
        "answer_finish_reason": generation.get("answer_finish_reason"),
        "output_tokens": generation["output_tokens"],
        "thinking_tokens": generation.get("thinking_tokens"),
        "answer_tokens": generation.get("answer_tokens"),
    })
    episode.cursor += 1
    if episode.cursor >= len(episode.order):
        episode.status = "SOLVED"
        episode.solved = True
    elif episode.cursor >= pilot_steps_per_instance:
        episode.status = "PILOT_STEP_LIMIT"


def _select_manifest(n_per_cell: int, operator_version: str = "v0") -> list[dict[str, Any]]:
    data = _read_json(SEPARATOR_RESULTS_PATH)
    acceptance = data.get("acceptance", {})
    if data.get("schema_version") != "rung1_separator_scaling_symbolic_v0_2_3" or not acceptance.get("overall_pass") or not acceptance.get("fairness_corner_clean"):
        raise RuntimeError("symbolic separator v0.2.3 fairness gate is not passed")
    manifest = data["instance_manifest"]
    if operator_version == "v1_1":
        selected: list[dict[str, Any]] = []
        for b_value in B_PILOT_BINS:
            by_b = [row for row in manifest if int(row["b"]) == b_value]
            if not by_b:
                raise RuntimeError(f"no separator manifest rows found for b={b_value}")
            max_d = max(int(row["d_global_reference"]) for row in by_b)
            deepest_by_cell: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in by_b:
                if int(row["d_global_reference"]) == max_d:
                    deepest_by_cell[row["cell_id"]].append(row)
            selected_cell = sorted(deepest_by_cell)[0]
            selected.extend(deepest_by_cell[selected_cell][:n_per_cell])
        return selected
    max_d = max(int(row["d_global_reference"]) for row in manifest)
    deepest = [row for row in manifest if int(row["d_global_reference"]) == max_d]
    deepest_by_cell: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in deepest:
        deepest_by_cell[row["cell_id"]].append(row)
    selected_cell = sorted(deepest_by_cell)[0]
    return deepest_by_cell[selected_cell][:n_per_cell]


def _classify_raw_generation(generation: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    text = generation["text"]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    repeated_lines = len(lines) - len(set(lines))
    lower = text.lower()
    schema_words = sum(lower.count(word) for word in ["vertex", "color", "prune", "domain", "edge", "assignment"])
    ramble_words = sum(lower.count(word) for word in ["therefore", "however", "let's", "we need", "consider", "possible", "maybe"])
    output_tokens = int(generation["output_tokens"])
    length_capped = generation["finish_reason"] == "length"
    schema_drift = parsed["generation_state"] != "valid"
    classification = "B_possible_genuinely_long_reasoning"
    if length_capped and schema_drift:
        classification = "A_rambling_or_unbounded_schema_drift"
    elif output_tokens > 3000 and ramble_words > schema_words:
        classification = "A_rambling_or_redundant_reasoning"
    elif parsed["generation_state"] == "valid" and output_tokens <= 3000:
        classification = "clean_bounded_valid"
    return {
        "classification": classification,
        "length_capped": length_capped,
        "schema_drift": schema_drift,
        "line_count": len(lines),
        "repeated_line_count": repeated_lines,
        "schema_word_count": schema_words,
        "ramble_word_count": ramble_words,
        "output_tokens": output_tokens,
    }


def run_raw_inspection_shard(shard_index: int, num_shards: int, output_dir: Path, n_instances: int, batch_size: int, max_new_tokens: int, device: str, dtype: str, operator_version: str = "v0") -> dict[str, Any]:
    manifest = _select_manifest(n_instances, operator_version)
    shard_rows = [row for index, row in enumerate(manifest) if index % num_shards == shard_index]
    model, tokenizer, model_source = _load_model(device, dtype)
    inspection_rows = []
    with tqdm(total=len(shard_rows), desc=f"p1b raw inspect shard {shard_index}", unit="gen", dynamic_ncols=True) as progress:
        for start in range(0, len(shard_rows), batch_size):
            batch_rows = shard_rows[start:start + batch_size]
            episodes = [Episode(row=row, adjacency=_adjacency(int(row["n_vertices"]), tuple(tuple(edge) for edge in row["edges"])), order=[int(v) for v in row["order"]], domains=_initial_domains(row)) for row in batch_rows]
            prompts = [_operator_prompt(episode, operator_version) for episode in episodes]
            generations = _generate_batch(model, tokenizer, prompts, max_new_tokens, operator_version)
            for row, episode, prompt, generation in zip(batch_rows, episodes, prompts, generations):
                parsed = _parse_generation(generation, int(row["k"]), operator_version)
                classification = _classify_raw_generation(generation, parsed)
                inspection_rows.append({
                    "instance_id": row["instance_id"],
                    "cell_id": row["cell_id"],
                    "d_global_reference": row["d_global_reference"],
                    "b": row["b"],
                    "current_vertex": episode.order[episode.cursor],
                    "prompt_contract": _prompt_contract(operator_version),
                    "prompt": prompt,
                    "raw_generation": generation["text"],
                    "finish_reason": generation["finish_reason"],
                    "output_tokens": generation["output_tokens"],
                    "generation_state": parsed["generation_state"],
                    "json_start": parsed["json_start"],
                    "parsed_color": parsed["color"],
                    "n_parsed_prunes": len(parsed["prunes"]),
                    "classification": classification,
                    "model_id": MODEL_ID,
                    "model_source": model_source,
                    "max_new_tokens": max_new_tokens,
                    "temperature": 0,
                    "thinking_disabled": _thinking_disabled(operator_version),
                    "thinking_budget_requested": _thinking_budget(operator_version),
                    "answer_token_budget_requested": _answer_budget(operator_version),
                    "operator_version": operator_version,
                    "shard_index": shard_index,
                    "num_shards": num_shards,
                    "source": SOURCE,
                    "provenance": _provenance("qwen35_p1b_raw_generation_inspection", operator_version),
                })
                progress.update(1)
    payload = {"schema_version": RAW_INSPECTION_SCHEMA_VERSION, "generated_at": _now(), "status": "SHARD_COMPLETE", "shard_index": shard_index, "num_shards": num_shards, "operator_version": operator_version, "inspection_rows": inspection_rows, "source": SOURCE}
    _write_json(output_dir / f"raw_inspect_shard_{shard_index:02d}.json", payload)
    return payload


def merge_raw_inspection(output_dir: Path, num_shards: int) -> dict[str, Any]:
    rows = []
    shard_paths = []
    for shard_index in range(num_shards):
        path = output_dir / f"raw_inspect_shard_{shard_index:02d}.json"
        shard_paths.append(_rel(path))
        rows.extend(_read_json(path)["inspection_rows"])
    class_counts = Counter(row["classification"]["classification"] for row in rows)
    finish_counts = Counter(row["finish_reason"] for row in rows)
    generation_counts = Counter(row["generation_state"] for row in rows)
    payload = {
        "schema_version": RAW_INSPECTION_SCHEMA_VERSION,
        "generated_at": _now(),
        "status": "P1B_RAW_GENERATION_INSPECTION_COMPLETE",
        "generation_config": {
            "model_id": MODEL_ID,
            "temperature": 0,
            "max_new_tokens": rows[0]["max_new_tokens"] if rows else None,
            "prompt_contract": PROMPT_CONTRACT,
            "thinking_disabled": False,
            "n_shards": num_shards,
            "n_inspected": len(rows),
            "source": SOURCE,
            "provenance": "qwen35_p1b_raw_generation_inspection_config_v0",
        },
        "summary": {
            "classification_counts": dict(sorted(class_counts.items())),
            "finish_reason_counts": dict(sorted(finish_counts.items())),
            "generation_state_counts": dict(sorted(generation_counts.items())),
            "frac_length_capped": sum(row["finish_reason"] == "length" for row in rows) / max(len(rows), 1),
            "frac_valid": sum(row["generation_state"] == "valid" for row in rows) / max(len(rows), 1),
            "source": SOURCE,
            "provenance": "qwen35_p1b_raw_generation_inspection_summary_v0",
        },
        "inspection_rows": rows,
        "shard_paths": shard_paths,
    }
    _write_json(RAW_INSPECTION_RESULTS_PATH, payload)
    return payload


def launch_raw_inspection(args: argparse.Namespace) -> None:
    output_dir = Path(args.inspect_output_dir) if Path(args.inspect_output_dir).is_absolute() else REPO_ROOT / args.inspect_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    processes = []
    failed = []
    for shard_index in range(args.num_shards):
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(shard_index)
        cmd = [args.python_bin, "-u", "-m", "experiments.rung1_separator_p1b_truncation_pilot", "--raw-inspection-shard", "--shard-index", str(shard_index), "--num-shards", str(args.num_shards), "--inspect-output-dir", str(output_dir), "--inspect-n", str(args.inspect_n), "--batch-size", str(args.batch_size), "--max-new-tokens", str(args.max_new_tokens), "--operator-version", args.operator_version, "--device", "cuda:0", "--dtype", args.dtype]
        log_path = output_dir / f"raw_inspect_shard_{shard_index:02d}.log"
        log_handle = log_path.open("w", encoding="utf-8")
        processes.append((shard_index, log_handle, subprocess.Popen(cmd, cwd=REPO_ROOT, env=env, stdout=log_handle, stderr=subprocess.STDOUT, text=True)))
    for shard_index, log_handle, process in processes:
        code = process.wait()
        log_handle.close()
        if code != 0:
            failed.append((shard_index, code, str(output_dir / f"raw_inspect_shard_{shard_index:02d}.log")))
    if failed:
        raise SystemExit(f"failed raw inspection shards: {failed}")
    merge_raw_inspection(output_dir, args.num_shards)


def _episode_row(episode: Episode, model_source: str, shard_index: int, num_shards: int, n_per_cell: int, batch_size: int, max_new_tokens: int, pilot_steps_per_instance: int, operator_version: str) -> dict[str, Any]:
    attempts = sum(len(values) for values in episode.distinct_attempts_by_vertex.values())
    clean = max(1, len(episode.distinct_attempts_by_vertex))
    generation_total = sum(episode.generation_counts.values()) or 1
    live_sizes = [int(item["live_domain_size_before_branch"]) for item in episode.trace]
    propagation_opportunities = sum(int(item.get("propagation_opportunity", False)) for item in episode.trace)
    correct_propagation_opportunities = sum(int(item.get("correct_propagation", False)) for item in episode.trace)
    thinking_token_values = [int(item["thinking_tokens"]) for item in episode.trace if item.get("thinking_tokens") is not None]
    return {
        "instance_id": episode.row["instance_id"],
        "cell_id": episode.row["cell_id"],
        "sweep": episode.row["sweep"],
        "d_global_reference": episode.row["d_global_reference"],
        "b": episode.row["b"],
        "rung": RUNG,
        "arm": "forward_markov_team_qwen_p1b_guarded_propagation",
        "solved": episode.solved,
        "status": episode.status,
        "llm_calls": episode.calls,
        "steps_to_solve_or_cap": len(episode.trace),
        "call_cap": DEFAULT_CALL_CAP,
        "pilot_steps_per_instance": pilot_steps_per_instance,
        "finish_reason": Counter(item["finish_reason"] for item in episode.trace).most_common(1)[0][0] if episode.trace else None,
        "output_tokens": sum(int(item["output_tokens"]) for item in episode.trace),
        "thinking_tokens": sum(thinking_token_values) if thinking_token_values else None,
        "answer_tokens": sum(int(item.get("answer_tokens") or 0) for item in episode.trace),
        "thinking_cap_hit": sum(int(item.get("thinking_finish_reason") == "length") for item in episode.trace),
        "answer_cap_hit": sum(int(item.get("answer_finish_reason") == "length") for item in episode.trace),
        "generation_truncated_no_answer": episode.generation_counts["truncated_no_answer"],
        "generation_parsable_invalid": episode.generation_counts["parsable_invalid"],
        "generation_valid": episode.generation_counts["valid"],
        "generation_format_failure": episode.generation_counts["format_failure"],
        "missed_propagation": episode.operator_error_counts["missed_propagation"],
        "unsound_propagation_rejected": episode.operator_error_counts["unsound_propagation_rejected"],
        "propagation_opportunities": propagation_opportunities,
        "correct_propagation_opportunities": correct_propagation_opportunities,
        "correct_propagation_rate": correct_propagation_opportunities / max(propagation_opportunities, 1),
        "value_misselection": episode.operator_error_counts["value_misselection"],
        "format_failure": episode.operator_error_counts["format_failure"],
        "frac_valid_generation": episode.generation_counts["valid"] / generation_total,
        "k_eff_clean": mean(live_sizes) if live_sizes else episode.row.get("mean_live_domain_at_decision"),
        "k_eff_inflated": attempts / clean,
        "rho": (attempts / clean) / max(mean(live_sizes) if live_sizes else float(episode.row.get("mean_live_domain_at_decision") or 1.0), 1e-9),
        "model_id": MODEL_ID,
        "model_source": model_source,
        "temperature": 0,
        "max_new_tokens": max_new_tokens,
        "n_per_cell": n_per_cell,
        "batch_size_per_gpu": batch_size,
        "prompt_contract": _prompt_contract(operator_version),
        "thinking_disabled": _thinking_disabled(operator_version),
        "thinking_budget_requested": _thinking_budget(operator_version),
        "answer_token_budget_requested": _answer_budget(operator_version),
        "operator_version": operator_version,
        "shard_index": shard_index,
        "num_shards": num_shards,
        "source": SOURCE,
        "provenance": _provenance("qwen35_p1b_truncation_pilot_instance", operator_version),
    }


def run_shard(shard_index: int, num_shards: int, output_dir: Path, n_per_cell: int, batch_size: int, max_new_tokens: int, pilot_steps_per_instance: int, device: str, dtype: str, operator_version: str) -> dict[str, Any]:
    manifest = _select_manifest(n_per_cell, operator_version)
    shard_rows = [row for index, row in enumerate(manifest) if index % num_shards == shard_index]
    model, tokenizer, model_source = _load_model(device, dtype)
    episodes = [Episode(row=row, adjacency=_adjacency(int(row["n_vertices"]), tuple(tuple(edge) for edge in row["edges"])), order=[int(v) for v in row["order"]], domains=_initial_domains(row)) for row in shard_rows]
    active = [episode for episode in episodes if episode.status == "RUNNING"]
    with tqdm(total=len(episodes), desc=f"p1b trunc shard {shard_index}", unit="inst", dynamic_ncols=True) as progress:
        while active:
            batch = active[:batch_size]
            generations = _generate_batch(model, tokenizer, [_operator_prompt(episode, operator_version) for episode in batch], max_new_tokens, operator_version)
            for episode, generation in zip(batch, generations):
                before = episode.status
                _step_episode(episode, generation, pilot_steps_per_instance, operator_version)
                if episode.status != "RUNNING" and before == "RUNNING":
                    progress.update(1)
            progress.refresh()
            active = [episode for episode in episodes if episode.status == "RUNNING" and episode.calls < DEFAULT_CALL_CAP]
            for episode in episodes:
                if episode.status == "RUNNING" and episode.calls >= DEFAULT_CALL_CAP:
                    episode.status = "CALL_CAP"
                    progress.update(1)
    rows = [_episode_row(episode, model_source, shard_index, num_shards, n_per_cell, batch_size, max_new_tokens, pilot_steps_per_instance, operator_version) for episode in episodes]
    payload = {"schema_version": _schema_version(operator_version), "generated_at": _now(), "status": "SHARD_COMPLETE", "shard_index": shard_index, "num_shards": num_shards, "operator_version": operator_version, "instance_arm_metrics": rows, "source": SOURCE}
    _write_json(output_dir / f"shard_{shard_index:02d}.json", payload)
    return payload


def _summaries(rows: list[dict[str, Any]], operator_version: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    op_rows = []
    keff_rows = []
    budget_rows = []
    keys = sorted({(row["rung"], row["d_global_reference"], row["b"]) for row in rows}, key=lambda item: (item[0], item[1], item[2]))
    for rung, d_global, b in keys:
        subset = [row for row in rows if row["rung"] == rung and row["d_global_reference"] == d_global and row["b"] == b]
        n = len(subset)
        opportunities = sum(int(row.get("propagation_opportunities", 0)) for row in subset)
        correct_opportunities = sum(int(row.get("correct_propagation_opportunities", 0)) for row in subset)
        op_rows.append({
            "rung": rung,
            "d_global_bin": str(d_global),
            "b_bin": str(b),
            "n": n,
            "propagation_opportunities": opportunities,
            "correct_propagation_opportunities": correct_opportunities,
            "correct_propagation_rate": correct_opportunities / max(opportunities, 1),
            "missed_propagation_rate": mean(float(row["missed_propagation"] > 0) for row in subset),
            "unsound_propagation_rejected_rate": mean(float(row["unsound_propagation_rejected"] > 0) for row in subset),
            "value_misselection_rate": mean(float(row["value_misselection"] > 0) for row in subset),
            "format_failure_rate": mean(float(row["format_failure"] > 0) for row in subset),
            "frac_truncated_no_answer": mean(float(row["generation_truncated_no_answer"] > 0) for row in subset),
            "frac_finish_reason_length": mean(float(row["finish_reason"] == "length") for row in subset),
            "frac_truncated_or_length": mean(float(row["generation_truncated_no_answer"] > 0 or row["finish_reason"] == "length") for row in subset),
            "frac_parsable_invalid": mean(float(row["generation_parsable_invalid"] > 0) for row in subset),
            "frac_valid": mean(float(row["generation_valid"] > 0) for row in subset),
            "source": SOURCE,
            "provenance": _provenance("qwen35_p1b_operator_error_breakdown_pilot", operator_version),
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
            "provenance": _provenance("qwen35_p1b_keff_inflation_pilot", operator_version),
        })
        calls = [int(row["llm_calls"]) for row in subset]
        p90 = sorted(calls)[min(len(calls) - 1, math.ceil(0.9 * len(calls)) - 1)] if calls else 0
        budget_rows.append({
            "rung": rung,
            "d_global_bin": str(d_global),
            "b_bin": str(b),
            "pilot_median_calls_per_instance": median(calls) if calls else 0,
            "pilot_p90_calls_per_instance": p90,
            "recommended_call_cap": int(math.ceil(p90 * 2)),
            "call_cap_status_rate": mean(float(row["status"] == "CALL_CAP") for row in subset),
            "n": n,
            "source": SOURCE,
            "provenance": _provenance("qwen35_p1b_call_cap_pilot", operator_version),
        })
    return op_rows, keff_rows, budget_rows


def _truncation_gate(op_rows: list[dict[str, Any]], operator_version: str) -> dict[str, Any]:
    deepest = max((int(row["d_global_bin"]) for row in op_rows), default=0)
    deep_rows = [row for row in op_rows if int(row["d_global_bin"]) == deepest]
    max_deep = max((float(row["frac_truncated_no_answer"]) for row in deep_rows), default=0.0)
    max_all = max((float(row["frac_truncated_no_answer"]) for row in op_rows), default=0.0)
    max_deep_length = max((float(row["frac_finish_reason_length"]) for row in deep_rows), default=0.0)
    max_all_length = max((float(row["frac_finish_reason_length"]) for row in op_rows), default=0.0)
    max_deep_truncated_or_length = max((float(row["frac_truncated_or_length"]) for row in deep_rows), default=0.0)
    max_all_truncated_or_length = max((float(row["frac_truncated_or_length"]) for row in op_rows), default=0.0)
    return {"gate": "p1b_truncation_gate", "pass": max_deep_truncated_or_length <= TRUNCATION_RATE_THRESHOLD and max_all_truncated_or_length <= TRUNCATION_RATE_THRESHOLD, "threshold": TRUNCATION_RATE_THRESHOLD, "deepest_d_global": deepest, "max_deep_frac_truncated_no_answer": max_deep, "max_all_frac_truncated_no_answer": max_all, "max_deep_frac_finish_reason_length": max_deep_length, "max_all_frac_finish_reason_length": max_all_length, "max_deep_frac_truncated_or_length": max_deep_truncated_or_length, "max_all_frac_truncated_or_length": max_all_truncated_or_length, "source": SOURCE, "provenance": _provenance("qwen35_p1b_truncation_gate_pilot", operator_version)}


def _operator_functional_gate(op_rows: list[dict[str, Any]], operator_version: str) -> dict[str, Any]:
    cell_rows = []
    for row in op_rows:
        truncated_ok = float(row["frac_truncated_or_length"]) <= TRUNCATION_RATE_THRESHOLD
        functional_ok = float(row.get("correct_propagation_rate", 0.0)) >= FUNCTIONAL_GATE_THRESHOLD
        cell_rows.append({
            "cell": f"d{row['d_global_bin']}_b{row['b_bin']}",
            "d_global_bin": row["d_global_bin"],
            "b_bin": row["b_bin"],
            "n": row["n"],
            "frac_truncated_or_length": row["frac_truncated_or_length"],
            "correct_propagation_rate": row.get("correct_propagation_rate", 0.0),
            "propagation_opportunities": row.get("propagation_opportunities", 0),
            "truncation_pass": truncated_ok,
            "functional_pass": functional_ok,
            "cell_allowed_for_full_table": truncated_ok and functional_ok,
        })
    allowed = [row["cell"] for row in cell_rows if row["cell_allowed_for_full_table"]]
    excluded = [row["cell"] for row in cell_rows if not row["cell_allowed_for_full_table"]]
    return {
        "gate": "p1b_operator_functional_gate",
        "pass": bool(cell_rows) and not excluded,
        "threshold": FUNCTIONAL_GATE_THRESHOLD,
        "allowed_cells": allowed,
        "excluded_cells": excluded,
        "cell_gate_rows": cell_rows,
        "source": SOURCE,
        "provenance": _provenance("qwen35_p1b_operator_functional_gate_pilot", operator_version),
    }


def merge(output_dir: Path, num_shards: int, operator_version: str = "v0") -> dict[str, Any]:
    rows = []
    shard_paths = []
    for shard_index in range(num_shards):
        path = output_dir / f"shard_{shard_index:02d}.json"
        shard_paths.append(_rel(path))
        rows.extend(_read_json(path)["instance_arm_metrics"])
    op_rows, keff_rows, budget_rows = _summaries(rows, operator_version)
    truncation_gate = _truncation_gate(op_rows, operator_version)
    functional_gate = _operator_functional_gate(op_rows, operator_version)
    observed_batches = sorted({int(row["batch_size_per_gpu"]) for row in rows})
    observed_n_per_cell = sorted({int(row["n_per_cell"]) for row in rows})
    observed_pilot_steps = sorted({int(row["pilot_steps_per_instance"]) for row in rows})
    if operator_version == "v1_1":
        status = "RUNG1_SEPARATOR_P1B_OPERATOR_V11_PILOT_PASS" if functional_gate["pass"] else "RUNG1_SEPARATOR_P1B_OPERATOR_V11_PILOT_RESTRICTED_OR_FAIL"
    else:
        status = "RUNG1_SEPARATOR_P1B_TRUNCATION_GATE_PASS" if truncation_gate["pass"] else "RUNG1_SEPARATOR_P1B_TRUNCATION_GATE_FAIL_STOP"
    payload = {
        "schema_version": _schema_version(operator_version),
        "generated_at": _now(),
        "status": status,
        "generation_config": {
            "model_id": MODEL_ID,
            "temperature": 0,
            "max_new_tokens": rows[0]["max_new_tokens"] if rows else None,
            "prompt_contract": _prompt_contract(operator_version),
            "thinking_disabled": _thinking_disabled(operator_version),
            "thinking_budget_requested": _thinking_budget(operator_version),
            "answer_token_budget_requested": _answer_budget(operator_version),
            "operator_version": operator_version,
            "n_shards": num_shards,
            "n_per_cell_observed_values": observed_n_per_cell,
            "batch_size_per_gpu_observed_values": observed_batches,
            "pilot_steps_per_instance_observed_values": observed_pilot_steps,
            "call_cap": DEFAULT_CALL_CAP,
            "truncation_rate_threshold": TRUNCATION_RATE_THRESHOLD,
            "functional_gate_threshold": FUNCTIONAL_GATE_THRESHOLD,
            "cross_b_pilot_bins": list(B_PILOT_BINS) if operator_version == "v1_1" else None,
            "source": SOURCE,
            "provenance": _provenance("qwen35_p1b_truncation_pilot_config", operator_version),
        },
        "acceptance": {
            "p1b_truncation_gate_pass": bool(truncation_gate["pass"]),
            "p1b_operator_functional_gate_pass": bool(functional_gate["pass"]),
            "p1b_full_table_allowed_by_truncation": bool(truncation_gate["pass"]),
            "p1b_full_table_allowed_by_operator_functional_gate": bool(functional_gate["pass"]),
            "p1b_full_table_allowed_cells": functional_gate["allowed_cells"],
            "p1b_full_table_excluded_cells": functional_gate["excluded_cells"],
        },
        "prelaunch_truncation_gate": [truncation_gate],
        "operator_functional_gate": [functional_gate],
        "operator_functional_gate_by_cell": functional_gate["cell_gate_rows"],
        "operator_error_breakdown": op_rows,
        "keff_inflation": keff_rows,
        "call_cap_recommendation": budget_rows,
        "instance_arm_metrics": rows,
        "shard_paths": shard_paths,
        "verdict": [
            {"check": "p1b_truncation_gate", "predicted": f"deepest and all-cell truncated_or_length fraction <= {TRUNCATION_RATE_THRESHOLD:.2f}", "observed": f"deepest_d_global={truncation_gate['deepest_d_global']}; max_deep_truncated_or_length={truncation_gate['max_deep_frac_truncated_or_length']:.4f}; max_all_truncated_or_length={truncation_gate['max_all_frac_truncated_or_length']:.4f}", "pass": bool(truncation_gate["pass"]), "source": SOURCE, "provenance": _provenance("qwen35_p1b_truncation_pilot_verdict", operator_version)},
            {"check": "p1b_operator_functional_gate", "predicted": f"each piloted cell correct_propagation_rate >= {FUNCTIONAL_GATE_THRESHOLD:.2f} and truncation gate passes", "observed": f"allowed_cells={functional_gate['allowed_cells']}; excluded_cells={functional_gate['excluded_cells']}", "pass": bool(functional_gate["pass"]), "source": SOURCE, "provenance": _provenance("qwen35_p1b_operator_functional_pilot_verdict", operator_version)},
        ],
    }
    _write_json(PILOT_RESULTS_PATH, payload)
    return payload


def _launch_shard(args: argparse.Namespace, output_dir: Path, shard_index: int) -> tuple[int, Path]:
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(shard_index)
    cmd = [args.python_bin, "-u", "-m", "experiments.rung1_separator_p1b_truncation_pilot", "--shard-index", str(shard_index), "--num-shards", str(args.num_shards), "--output-dir", str(output_dir), "--n-per-cell", str(args.n_per_cell), "--batch-size", str(args.batch_size), "--max-new-tokens", str(args.max_new_tokens), "--pilot-steps", str(args.pilot_steps), "--operator-version", args.operator_version, "--device", "cuda:0", "--dtype", args.dtype]
    log_path = output_dir / f"shard_{shard_index:02d}.log"
    with log_path.open("w", encoding="utf-8") as log_handle:
        code = subprocess.Popen(cmd, cwd=REPO_ROOT, env=env, stdout=log_handle, stderr=subprocess.STDOUT, text=True).wait()
    return code, log_path


def launch(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    failed = []
    processes = []
    for shard_index in range(args.num_shards):
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(shard_index)
        cmd = [args.python_bin, "-u", "-m", "experiments.rung1_separator_p1b_truncation_pilot", "--shard-index", str(shard_index), "--num-shards", str(args.num_shards), "--output-dir", str(output_dir), "--n-per-cell", str(args.n_per_cell), "--batch-size", str(args.batch_size), "--max-new-tokens", str(args.max_new_tokens), "--pilot-steps", str(args.pilot_steps), "--operator-version", args.operator_version, "--device", "cuda:0", "--dtype", args.dtype]
        log_path = output_dir / f"shard_{shard_index:02d}.log"
        log_handle = log_path.open("w", encoding="utf-8")
        processes.append((shard_index, log_handle, subprocess.Popen(cmd, cwd=REPO_ROOT, env=env, stdout=log_handle, stderr=subprocess.STDOUT, text=True)))
    for shard_index, log_handle, process in processes:
        code = process.wait()
        log_handle.close()
        if code != 0:
            failed.append((shard_index, code, str(output_dir / f"shard_{shard_index:02d}.log")))
    if failed:
        raise SystemExit(f"failed shards: {failed}")
    merge(output_dir, args.num_shards, args.operator_version)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-4gpu", action="store_true")
    parser.add_argument("--launch-raw-inspection-4gpu", action="store_true")
    parser.add_argument("--raw-inspection-shard", action="store_true")
    parser.add_argument("--merge-raw-inspection", action="store_true")
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--num-shards", type=int, default=4)
    parser.add_argument("--output-dir", default="results/rung1_separator_fallibility_rungs/p1b_truncation_pilot_shards")
    parser.add_argument("--inspect-output-dir", default="results/rung1_separator_fallibility_rungs/p1b_raw_generation_inspection_shards")
    parser.add_argument("--inspect-n", type=int, default=RAW_INSPECTION_DEFAULT_N)
    parser.add_argument("--n-per-cell", type=int, default=DEFAULT_N_PER_CELL)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE_PER_GPU)
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    parser.add_argument("--pilot-steps", type=int, default=DEFAULT_PILOT_STEPS_PER_INSTANCE)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--python-bin", default=str(REPO_ROOT / ".venv/bin/python"))
    parser.add_argument("--operator-version", choices=sorted(OPERATOR_VERSIONS), default="v0")
    args = parser.parse_args()
    output_dir = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO_ROOT / args.output_dir
    if args.launch_4gpu:
        launch(args)
    elif args.launch_raw_inspection_4gpu:
        launch_raw_inspection(args)
    elif args.raw_inspection_shard:
        if args.shard_index is None:
            raise SystemExit("provide --shard-index for raw inspection shard")
        inspect_output_dir = Path(args.inspect_output_dir) if Path(args.inspect_output_dir).is_absolute() else REPO_ROOT / args.inspect_output_dir
        run_raw_inspection_shard(args.shard_index, args.num_shards, inspect_output_dir, args.inspect_n, args.batch_size, args.max_new_tokens, args.device, args.dtype, args.operator_version)
    elif args.merge_raw_inspection:
        inspect_output_dir = Path(args.inspect_output_dir) if Path(args.inspect_output_dir).is_absolute() else REPO_ROOT / args.inspect_output_dir
        merge_raw_inspection(inspect_output_dir, args.num_shards)
    elif args.merge:
        merge(output_dir, args.num_shards, args.operator_version)
    else:
        if args.shard_index is None:
            raise SystemExit("provide --shard-index or use --launch-4gpu")
        run_shard(args.shard_index, args.num_shards, output_dir, args.n_per_cell, args.batch_size, args.max_new_tokens, args.pilot_steps, args.device, args.dtype, args.operator_version)


if __name__ == "__main__":
    main()