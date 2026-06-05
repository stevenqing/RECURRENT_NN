"""Benchmark single-GPU batch sizes for Module 1 capacity benchmark kernels."""

from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import time

import torch

from experiments.module1_capacity_benchmark import _run_one_batched


def benchmark(output_dir: str = "results/module1_capacity_batching", device: str = "cuda:0", batch_sizes: list[int] | None = None, n_trials: int = 1024) -> dict:
    if batch_sizes is None:
        batch_sizes = [512, 1024, 2048, 4096, 8192, 16384]
    torch_device = torch.device(device)
    cuda_device = torch_device.index if torch_device.index is not None else 0
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    cases = [
        ("bound_single", 512, 81, 9, 32),
        ("factored", 512, 81, 9, 32),
        ("bound_single", 1024, 729, 2, 32),
        ("factored", 1024, 729, 2, 32),
    ]
    rows = []
    for variant, D, K_var, K_val, depth in cases:
        for batch_size in batch_sizes:
            if torch.cuda.is_available() and str(device).startswith("cuda"):
                with torch.cuda.device(cuda_device):
                    torch.cuda.empty_cache()
                    torch.cuda.reset_peak_memory_stats()
                    torch.cuda.synchronize()
            start = time.perf_counter()
            result = _run_one_batched(variant, D, K_var, K_val, depth, seed=42, n_trials=n_trials, device=device, batch_size=batch_size)
            if torch.cuda.is_available() and str(device).startswith("cuda"):
                with torch.cuda.device(cuda_device):
                    torch.cuda.synchronize()
                    peak_bytes = torch.cuda.max_memory_allocated()
            else:
                peak_bytes = 0
            elapsed = time.perf_counter() - start
            rows.append({
                "variant": variant,
                "D": D,
                "K_var": K_var,
                "K_val": K_val,
                "depth": depth,
                "batch_size": batch_size,
                "n_trials": n_trials,
                "elapsed_sec": elapsed,
                "trials_per_sec": n_trials / elapsed,
                "peak_gib": peak_bytes / 1024**3,
                "decode_accuracy": result["decode_accuracy"],
            })
            print(json.dumps(rows[-1]), flush=True)
    best_by_case = []
    for variant, D, K_var, K_val, depth in cases:
        subset = [row for row in rows if (row["variant"], row["D"], row["K_var"], row["K_val"], row["depth"]) == (variant, D, K_var, K_val, depth)]
        best_by_case.append(max(subset, key=lambda row: row["trials_per_sec"]))
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "device": device, "rows": rows, "best_by_case": best_by_case}
    path = Path(output_dir) / "results.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"results": str(path), **payload}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark Module 1 capacity batch sizes.")
    parser.add_argument("--output-dir", default="results/module1_capacity_batching")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-sizes", default="16,32,64,128,256,512,1024")
    parser.add_argument("--n-trials", type=int, default=1024)
    args = parser.parse_args()
    batch_sizes = [int(item) for item in args.batch_sizes.split(",") if item.strip()]
    print(json.dumps(benchmark(args.output_dir, args.device, batch_sizes, args.n_trials), indent=2, sort_keys=True))