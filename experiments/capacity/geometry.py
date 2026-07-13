"""E0 hidden-state geometry for real-operator capacity gates."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import torch

from experiments.capacity.common import d_star_from_dimension, env_payload, instantiate_operator, resolve_device, write_json
from experiments.capacity.width_wall import _branch_partials, _graph_givens, _operator_hiddens


def _effective_dimension(states: torch.Tensor) -> tuple[float, float, list[float]]:
    centered = states.float() - states.float().mean(dim=0, keepdim=True)
    if centered.shape[0] <= 1 or float(centered.norm().item()) == 0.0:
        return 0.0, 0.0, []
    gram = centered @ centered.T / max(centered.shape[0] - 1, 1)
    eigenvalues = torch.linalg.eigvalsh(gram).clamp_min(0.0).flip(0)
    total = float(eigenvalues.sum().item())
    if total <= 0.0:
        return 0.0, 0.0, []
    d_eff = float(total * total / eigenvalues.square().sum().clamp_min(1e-30).item())
    outlier_energy = float(eigenvalues[0].item() / total)
    top = [float(item) for item in eigenvalues[: min(16, eigenvalues.numel())].tolist()]
    return d_eff, outlier_energy, top


def _mean_cosine(states: torch.Tensor, max_pairs: int = 20000) -> float:
    if states.shape[0] <= 1:
        return 0.0
    normed = states.float() / states.float().norm(dim=-1, keepdim=True).clamp_min(1e-12)
    generator = torch.Generator().manual_seed(314159)
    total_pairs = states.shape[0] * (states.shape[0] - 1) // 2
    if total_pairs <= max_pairs:
        sims = normed @ normed.T
        mask = ~torch.eye(states.shape[0], dtype=torch.bool)
        return float(sims[mask].mean().item())
    left = torch.randint(0, states.shape[0], (max_pairs,), generator=generator)
    right = torch.randint(0, states.shape[0] - 1, (max_pairs,), generator=generator)
    right = right + (right >= left).long()
    return float((normed[left] * normed[right]).sum(dim=-1).mean().item())


def _task_spec(task: Any, K: int, n: int, seed: int) -> tuple[str, dict[str, Any], list[dict[int, int]]]:
    if isinstance(task, dict):
        task_type = str(task.get("task_type", "graph_coloring"))
        givens = dict(task.get("givens") or _graph_givens(K, seed, min_variables=max(1, min(n, 128))))
        partials = list(task.get("partials") or _branch_partials(n, K, int(givens.get("n", max(8, K * 4)))))
        return task_type, givens, partials[:n]
    givens = _graph_givens(K, seed, min_variables=max(1, min(n, 128)))
    return "graph_coloring", givens, _branch_partials(n, K, int(givens["n"]))


def _geometry_from_states(states: torch.Tensor, K: int, task_type: str, givens: dict[str, Any]) -> dict[str, Any]:
    d_eff, outlier_energy, top_eigenvalues = _effective_dimension(states)
    return {
        "D": int(states.shape[-1]),
        "D_eff": d_eff,
        "K": int(K),
        "d_star_eff": d_star_from_dimension(max(d_eff, 1e-12), int(K)),
        "d_star_nominal": d_star_from_dimension(int(states.shape[-1]), int(K)),
        "outlier_energy": outlier_energy,
        "mean_cosine": _mean_cosine(states),
        "n": int(states.shape[0]),
        "task_type": task_type,
        "givens_summary": {key: givens[key] for key in sorted(givens) if key != "edges"},
        "n_edges": len(givens.get("edges", [])),
        "top_covariance_eigenvalues": top_eigenvalues,
    }


def hidden_state_geometry(operator, task, n=2000) -> dict:
    """Return hidden-state geometry metrics including D_eff and d_star_eff."""
    K = int(task.get("K", task.get("k", 9))) if isinstance(task, dict) else 9
    seed = int(task.get("seed", 0)) if isinstance(task, dict) else 0
    batch_size = int(task.get("batch_size", 1)) if isinstance(task, dict) else 1
    task_type, givens, partials = _task_spec(task, K, int(n), seed)
    states = _operator_hiddens(operator, task_type, givens, partials, batch_size=batch_size)
    return _geometry_from_states(states, K, task_type, givens)


def run_shard(operator, K: int, seed: int, n: int, shard_index: int, num_shards: int, batch_size: int, shard_dir: str) -> dict[str, Any]:
    task_type, givens, partials = _task_spec({"K": K}, K, int(n), seed)
    shard_partials = partials[int(shard_index)::int(num_shards)]
    states = _operator_hiddens(operator, task_type, givens, shard_partials, batch_size=batch_size)
    target_dir = Path(shard_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    state_path = target_dir / f"states_shard{int(shard_index):03d}_of_{int(num_shards):03d}.pt"
    torch.save(
        {
            "states": states,
            "K": int(K),
            "seed": int(seed),
            "n_total": int(n),
            "shard_index": int(shard_index),
            "num_shards": int(num_shards),
            "task_type": task_type,
            "givens": givens,
        },
        state_path,
    )
    geometry = _geometry_from_states(states, K, task_type, givens)
    geometry["state_path"] = str(state_path)
    geometry["shard_index"] = int(shard_index)
    geometry["num_shards"] = int(num_shards)
    return geometry


def merge_shards(shard_dir: str) -> dict[str, Any]:
    paths = sorted(Path(shard_dir).glob("states_shard*_of_*.pt"))
    if not paths:
        raise FileNotFoundError(f"no shard state files found under {shard_dir}")
    payloads = [torch.load(path, map_location="cpu", weights_only=False) for path in paths]
    first = payloads[0]
    expected = int(first["num_shards"])
    indices = sorted(int(payload["shard_index"]) for payload in payloads)
    if len(paths) != expected or indices != list(range(expected)):
        raise RuntimeError(f"incomplete E0 shards: expected {expected} indices, found {indices}")
    metadata = (int(first["K"]), int(first["seed"]), int(first["n_total"]), str(first["task_type"]), first["givens"])
    for payload in payloads[1:]:
        candidate = (int(payload["K"]), int(payload["seed"]), int(payload["n_total"]), str(payload["task_type"]), payload["givens"])
        if candidate != metadata:
            raise RuntimeError("E0 shard metadata mismatch")
    states = torch.cat([payload["states"].float().cpu() for payload in payloads], dim=0)
    if int(states.shape[0]) != int(first["n_total"]):
        raise RuntimeError(f"E0 merged sample mismatch: expected {first['n_total']}, found {states.shape[0]}")
    geometry = _geometry_from_states(states, int(first["K"]), str(first["task_type"]), dict(first["givens"]))
    geometry["n_shards"] = len(paths)
    geometry["shard_paths"] = [str(path) for path in paths]
    geometry["n_total_requested"] = int(first["n_total"])
    return geometry


def main() -> None:
    parser = argparse.ArgumentParser(description="Run E0 hidden-state geometry measurement.")
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--K", type=int, default=9)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--no-load-model", action="store_true")
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-dir", default="results/capacity/E0_geometry_shards")
    parser.add_argument("--save-states", action="store_true")
    parser.add_argument("--merge-shards", action="store_true")
    parser.add_argument("--out", default="results/capacity/E0_geometry.json")
    args = parser.parse_args()
    if args.merge_shards:
        geometry = merge_shards(args.shard_dir)
    else:
        if args.shard_index < 0 or args.shard_index >= args.num_shards:
            raise SystemExit("--shard-index must be in [0, --num-shards)")
        device = resolve_device(args.device)
        operator = instantiate_operator(args.model, device, args.dtype, load_model=not args.no_load_model)
        if args.num_shards > 1 or args.save_states:
            geometry = run_shard(operator, args.K, args.seed, args.n, args.shard_index, args.num_shards, args.batch_size, args.shard_dir)
        else:
            geometry = hidden_state_geometry(operator, {"K": args.K, "seed": args.seed, "batch_size": args.batch_size}, n=args.n)
    payload = {
        "experiment": "E0",
        "model": args.model,
        "seed": int(args.seed),
        "num_shards": int(args.num_shards),
        "shard_index": int(args.shard_index),
        "shard_dir": args.shard_dir if args.num_shards > 1 or args.merge_shards else None,
        "merged_shards": bool(args.merge_shards),
        "generated_for_gates": {"G0": "D_eff > 0 and hidden-state sampling completed"},
        "geometry": geometry,
        "env": env_payload(args.dtype),
        "status": "G0_PASS" if geometry["D_eff"] > 0.0 else "G0_FAIL_ZERO_EFFECTIVE_DIMENSION",
    }
    write_json(args.out, payload)


if __name__ == "__main__":
    main()