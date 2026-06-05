"""Cache operator features for oracle-supervised Stage D training."""

from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
import os
from typing import Any

import torch

from controller.controller_head import Action
from llm_operator.wrapper import FrozenQwenOperator
from llm_operator.prompt_renderer import PromptRenderer


ACTION_TO_ID = {
    "propagate": int(Action.PROPAGATE),
    "branch": int(Action.BRANCH),
    "revert": int(Action.REVERT),
    "done": int(Action.DONE),
}


def _hashed_prompt_features(prompt: str, hidden_dim: int) -> torch.Tensor:
    values = torch.empty(hidden_dim, dtype=torch.float32)
    seed = hashlib.sha256(prompt.encode("utf-8")).digest()
    for index in range(hidden_dim):
        digest = hashlib.sha256(seed + index.to_bytes(4, "little")).digest()
        integer = int.from_bytes(digest[:4], "little")
        values[index] = (integer / 2**32) * 2.0 - 1.0
    return values


def _load_examples(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def _renderer_partial(task_type: str, partial: dict[str, Any]) -> dict[str, Any]:
    if task_type == "sudoku_4x4":
        converted = {}
        for key, value in partial.items():
            variable = int(key)
            converted[f"{variable // 4},{variable % 4}"] = value
        return converted
    return partial


def _select_examples(examples: list[dict[str, Any]], offset: int, limit: int | None, seeds: list[int] | None, per_seed_limit: int | None) -> list[dict[str, Any]]:
    if seeds is None:
        return examples[offset: None if limit is None else offset + limit]
    selected = []
    counts = {seed: 0 for seed in seeds}
    for row in examples:
        seed = int(row["seed"])
        if seed not in counts:
            continue
        if per_seed_limit is not None and counts[seed] >= per_seed_limit:
            continue
        selected.append(row)
        counts[seed] += 1
        if per_seed_limit is not None and all(count >= per_seed_limit for count in counts.values()):
            break
    return selected


def _parse_seeds(value: str | None) -> list[int] | None:
    if value is None or not value.strip():
        return None
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def build_operator_cache(
    examples_path: str = "results/oracle_dataset/examples.jsonl",
    output_dir: str = "results/operator_cache",
    hidden_dim: int = 256,
    load_model: bool = False,
    model_id: str = "Qwen/Qwen3-4B-Instruct-2507",
    device: str = "cuda",
    limit: int | None = None,
    offset: int = 0,
    output_name: str = "operator_cache",
    seeds: list[int] | None = None,
    per_seed_limit: int | None = None,
) -> dict[str, Any]:
    all_examples = _load_examples(examples_path)
    examples = _select_examples(all_examples, offset, limit, seeds, per_seed_limit)
    renderer = PromptRenderer()
    operator = FrozenQwenOperator(model_id=model_id, device=device, load_model=True) if load_model else None
    feature_source = model_id if operator is not None else "deterministic_hashed_prompt_fallback"
    hidden_dim = operator.hidden_size if operator is not None else hidden_dim
    hidden_states = []
    action_targets = []
    var_targets = []
    val_targets = []
    dead_end_targets = []
    seed_targets = []
    task_types = []
    action_counts: Counter[str] = Counter()
    task_counts: Counter[str] = Counter()
    seed_counts: Counter[int] = Counter()
    for row in examples:
        partial = _renderer_partial(row["task_type"], row["partial_assignment"])
        prompt = renderer.render(row["task_type"], row["givens"], partial)
        if operator is None:
            hidden_states.append(_hashed_prompt_features(prompt, hidden_dim))
        else:
            hidden_states.append(operator.forward_step(row["task_type"], row["givens"], partial).hidden_state.squeeze(0).detach().cpu().float())
        action = row["target_action"]
        action_targets.append(ACTION_TO_ID[action])
        var_targets.append(-100 if row["target_var"] is None else int(row["target_var"]))
        val_targets.append(-100 if row["target_val"] is None else int(row["target_val"]))
        dead_end_targets.append(1.0 if row["is_dead_end"] or action == "revert" else 0.0)
        seed_targets.append(int(row["seed"]))
        task_types.append(row["task_type"])
        action_counts[action] += 1
        task_counts[row["task_type"]] += 1
        seed_counts[int(row["seed"])] += 1

    os.makedirs(output_dir, exist_ok=True)
    cache_path = os.path.join(output_dir, f"{output_name}.pt")
    summary_path = os.path.join(output_dir, f"{output_name}_summary.json" if output_name != "operator_cache" else "summary.json")
    payload = {
        "hidden_states": torch.stack(hidden_states),
        "action_targets": torch.tensor(action_targets, dtype=torch.long),
        "var_targets": torch.tensor(var_targets, dtype=torch.long),
        "val_targets": torch.tensor(val_targets, dtype=torch.long),
        "dead_end_targets": torch.tensor(dead_end_targets, dtype=torch.float32).unsqueeze(-1),
        "seed_targets": torch.tensor(seed_targets, dtype=torch.long),
        "task_types": task_types,
        "metadata": {
            "feature_source": feature_source,
            "hidden_dim": hidden_dim,
            "n_examples": len(examples),
            "n_total_examples": len(all_examples),
            "offset": offset,
            "limit": limit,
            "seeds": seeds,
            "per_seed_limit": per_seed_limit,
            "examples_path": examples_path,
            "action_counts": dict(action_counts),
            "task_counts": dict(task_counts),
            "seed_counts": dict(seed_counts),
        },
    }
    torch.save(payload, cache_path)
    summary = {"cache": cache_path, **payload["metadata"]}
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
    return {"summary": summary_path, **summary}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build cached operator features for Stage D supervision.")
    parser.add_argument("--examples-path", default="results/oracle_dataset/examples.jsonl")
    parser.add_argument("--output-dir", default="results/operator_cache")
    parser.add_argument("--hidden-dim", type=int, default=256)
    parser.add_argument("--load-model", action="store_true", help="Use frozen Qwen instead of deterministic fallback features.")
    parser.add_argument("--model-id", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--output-name", default="operator_cache")
    parser.add_argument("--seeds", default=None, help="Comma-separated seeds to include, e.g. 42,137,256,314,999.")
    parser.add_argument("--per-seed-limit", type=int, default=None)
    args = parser.parse_args()
    print(json.dumps(build_operator_cache(args.examples_path, args.output_dir, args.hidden_dim, args.load_model, args.model_id, args.device, args.limit, args.offset, args.output_name, _parse_seeds(args.seeds), args.per_seed_limit), indent=2, sort_keys=True))