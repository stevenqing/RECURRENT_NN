"""Probe whether the environment is ready for frozen Qwen operator caching."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import torch


def probe_model_readiness(model_id: str = "Qwen/Qwen3-4B-Instruct-2507", output_dir: str = "results/model_readiness") -> dict[str, Any]:
    transformers_available = importlib.util.find_spec("transformers") is not None
    cuda_available = torch.cuda.is_available()
    cuda_device_count = torch.cuda.device_count() if cuda_available else 0
    hf_home = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": model_id,
        "transformers_available": transformers_available,
        "torch_version": torch.__version__,
        "cuda_available": cuda_available,
        "cuda_device_count": cuda_device_count,
        "cuda_device_names": [torch.cuda.get_device_name(index) for index in range(cuda_device_count)] if cuda_available else [],
        "hf_home": hf_home,
        "can_attempt_load_model": transformers_available,
        "recommended_cache_command": "python -m analysis.operator_cache --load-model --limit 8 --output-name qwen_probe_cache",
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "readiness.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"summary": str(path), **result}


if __name__ == "__main__":
    print(json.dumps(probe_model_readiness(), indent=2, sort_keys=True))