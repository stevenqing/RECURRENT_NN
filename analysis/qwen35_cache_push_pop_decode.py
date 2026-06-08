"""D1 Qwen3.5 cached-state structured push/pop decode probe."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import torch

from experiments.w3_qwen35_probe import DEFAULT_MODEL_ID, _cache_inventory, _load_model_components


def _write(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def _snapshot_cache(model: Any, tokenizer: Any, prompt: str) -> Any:
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model(**inputs, use_cache=True)
    return outputs.past_key_values


def _generate_tokens(model: Any, tokenizer: Any, cache: Any, n_tokens: int) -> Any:
    token = torch.tensor([[tokenizer.eos_token_id or 0]], device=model.device)
    current = cache
    with torch.no_grad():
        for _ in range(n_tokens):
            outputs = model(input_ids=token, past_key_values=current, use_cache=True)
            current = outputs.past_key_values
            token = outputs.logits[:, -1:, :].argmax(dim=-1)
    return current


def _codebooks(k_var: int, k_val: int, rows: int, cols: int, seed: int, device: torch.device, dtype: torch.dtype) -> tuple[torch.Tensor, torch.Tensor]:
    generator = torch.Generator(device="cpu").manual_seed(seed)
    keys = torch.randn(k_var, rows, generator=generator)
    vals = torch.randn(k_val, cols, generator=generator)
    keys = torch.nn.functional.normalize(keys, dim=-1).to(device=device, dtype=dtype)
    vals = torch.nn.functional.normalize(vals, dim=-1).to(device=device, dtype=dtype)
    return keys, vals


def _write_items(state: torch.Tensor, heads: list[int], keys: torch.Tensor, vals: torch.Tensor, variables: torch.Tensor, values: torch.Tensor) -> None:
    for index, (var, val) in enumerate(zip(variables.tolist(), values.tolist())):
        head = heads[index % len(heads)]
        state[0, head] += torch.outer(keys[int(var)], vals[int(val)])


def _decode_items(state: torch.Tensor, heads: list[int], keys: torch.Tensor, vals: torch.Tensor, variables: torch.Tensor, values: torch.Tensor) -> float:
    correct = 0
    total = 0
    for index, (var, expected) in enumerate(zip(variables.tolist(), values.tolist())):
        head = heads[index % len(heads)]
        read = keys[int(var)] @ state[0, head]
        decoded = int((vals @ read).argmax().item())
        correct += int(decoded == int(expected))
        total += 1
    return correct / max(total, 1)


def run(args: argparse.Namespace) -> dict[str, Any]:
    device = args.device if torch.cuda.is_available() or not args.device.startswith("cuda") else "cpu"
    model, tokenizer = _load_model_components(args.model_id, args.snapshot_path or None, device, args.dtype)
    cache = _snapshot_cache(model, tokenizer, args.prompt)
    inventory = _cache_inventory(cache)
    recurrent = [row for row in inventory if row.get("state_name") == "recurrent_states" and row.get("per_head_matrix_dim")]
    if not recurrent:
        return _write(Path(args.out_dir) / "qwen35_cache_push_pop_decode.json", {
            "module": "qwen35_cache_push_pop_decode",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "FAIL_CLOSED_NO_RECURRENT_STATE_EXPOSED",
            "model_id": args.model_id,
            "inventory": inventory,
            "fail_closed": True,
        })
    target_layer = int(recurrent[0]["layer"])
    state = cache.layers[target_layer].recurrent_states
    rows, cols = [int(x) for x in recurrent[0]["per_head_matrix_dim"]]
    max_heads = int(recurrent[0]["num_state_heads"])
    generator = torch.Generator(device="cpu").manual_seed(args.seed)
    keys, vals = _codebooks(args.k_var, args.k_val, rows, cols, args.seed, state.device, state.dtype)
    table_rows = []
    for depth in args.depths:
        variables = torch.randint(0, args.k_var, (depth,), generator=generator)
        values = torch.randint(0, args.k_val, (depth,), generator=generator)
        for n_tokens in args.token_counts:
            for mode, heads in [("single_head", [0]), ("striped_4_head", list(range(min(4, max_heads)))), ("no_write_control", [0])]:
                edited = copy.deepcopy(cache)
                edited_state = edited.layers[target_layer].recurrent_states
                before = edited_state.detach().clone()
                if mode != "no_write_control":
                    _write_items(edited_state, heads, keys, vals, variables, values)
                after_gen = _generate_tokens(model, tokenizer, edited, n_tokens)
                decoded_state = after_gen.layers[target_layer].recurrent_states
                accuracy = _decode_items(decoded_state, heads, keys, vals, variables, values)
                cleanup_norm = float((edited_state - before).float().norm().item()) if mode != "no_write_control" else 0.0
                table_rows.append({
                    "mode": mode,
                    "layer": target_layer,
                    "heads": len(heads),
                    "N_tokens": n_tokens,
                    "depth": depth,
                    "decode_accuracy": accuracy,
                    "cleanup_delta_norm": cleanup_norm,
                    "state_rows": rows,
                    "state_cols": cols,
                    "provenance": "measured:structured_rank1_push_into_cached_recurrent_states_then_decode_after_generation",
                })
    grade2_rows = [row for row in table_rows if row["mode"] != "no_write_control" and row["N_tokens"] == max(args.token_counts)]
    mean_acc = sum(float(row["decode_accuracy"]) for row in grade2_rows) / max(len(grade2_rows), 1)
    verdict = "GRADE2_IN_STATE_LIVE" if mean_acc >= args.grade2_threshold else "GRADE2_IN_STATE_NOT_ESTABLISHED"
    payload = {
        "module": "qwen35_cache_push_pop_decode",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": verdict,
        "model_id": args.model_id,
        "device": device,
        "inventory": inventory,
        "target_layer": target_layer,
        "result_tables": {"decode_accuracy": {"columns": ["mode", "layer", "heads", "N_tokens", "depth", "decode_accuracy", "cleanup_delta_norm", "state_rows", "state_cols", "provenance"], "rows": table_rows}},
        "grade2_verdict": {"threshold": args.grade2_threshold, "mean_max_N_accuracy": mean_acc, "verdict": verdict},
        "fail_closed": False,
    }
    return _write(Path(args.out_dir) / "qwen35_cache_push_pop_decode.json", payload)


def _csv_ints(text: str) -> list[int]:
    return [int(part) for part in text.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Qwen3.5 cached-state structured push/pop decode probe.")
    parser.add_argument("--out-dir", default="results/qwen35_cache_push_pop_decode")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--snapshot-path", default="")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", choices=["float16", "bfloat16"], default="bfloat16")
    parser.add_argument("--depths", type=_csv_ints, default=[1, 2, 4, 8])
    parser.add_argument("--token-counts", type=_csv_ints, default=[1, 2, 4, 8, 16, 32])
    parser.add_argument("--k-var", type=int, default=81)
    parser.add_argument("--k-val", type=int, default=9)
    parser.add_argument("--seed", type=int, default=47047)
    parser.add_argument("--grade2-threshold", type=float, default=0.95)
    parser.add_argument("--prompt", default="Structured cache probe. Continue normally.")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()