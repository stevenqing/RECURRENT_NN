"""Shared utilities for reversible-search capacity experiments."""

from __future__ import annotations

import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import torch

from llm_operator.wrapper import FrozenQwenOperator
from register.structured import predicted_d_star


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = REPO_ROOT / "results" / "capacity"
RAW_ROOT = RESULTS_ROOT / "raw"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def env_payload(dtype: str = "fp32") -> dict[str, Any]:
    return {
        "git_sha": git_sha(),
        "torch": torch.__version__,
        "dtype": dtype,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_count": torch.cuda.device_count(),
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(path.relative_to(REPO_ROOT)), "rows": len(payload.get("rows", []))}), flush=True)


def parse_int_csv(text: str) -> list[int]:
    return [int(part.strip()) for part in text.split(",") if part.strip()]


def default_depths(D: int, K: int) -> list[int]:
    ceiling = max(1, int(math.floor(predicted_d_star(D, K))))
    candidates = {8, 16, 32, 64, 128, 256, ceiling, max(1, 2 * ceiling), max(1, 4 * ceiling), max(1, 8 * ceiling)}
    return sorted(depth for depth in candidates if depth > 0)


def default_width_grid(D: int, K: int) -> list[int]:
    return default_width_grid_from_d_star(predicted_d_star(D, K))


def d_star_from_dimension(dimension: float, K: int) -> float:
    return float(dimension) / (2.0 * math.log(K))


def default_width_grid_from_d_star(d_star: float) -> list[int]:
    ceiling = max(1, int(math.floor(d_star)))
    candidates = {4, max(4, ceiling // 8), max(4, ceiling // 4), max(4, ceiling // 2), ceiling, max(4, 2 * ceiling), max(4, 3 * ceiling)}
    return sorted(candidates)


def resolve_device(device: str) -> str:
    if device == "auto":
        return "cuda:0" if torch.cuda.is_available() else "cpu"
    if device.startswith("cuda") and not torch.cuda.is_available():
        return "cpu"
    return device


def instantiate_operator(model: str, device: str, dtype: str, load_model: bool) -> FrozenQwenOperator:
    torch_dtype = torch.float32
    if dtype == "bf16":
        torch_dtype = torch.bfloat16
    elif dtype == "fp16":
        torch_dtype = torch.float16
    return FrozenQwenOperator(model_id=model, device=device, dtype=torch_dtype, load_model=load_model)


def chunked(items: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def experiment_payload(experiment: str, model: str, D: int, K: int, seed: int, n_instances: int, rows: list[dict[str, Any]], dtype: str) -> dict[str, Any]:
    return {
        "experiment": experiment,
        "model": model,
        "D": int(D),
        "K": int(K),
        "d_star": predicted_d_star(D, K),
        "seed": int(seed),
        "n_instances": int(n_instances),
        "generated_at": now(),
        "rows": rows,
        "env": env_payload(dtype),
    }
