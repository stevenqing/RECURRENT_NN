"""Download pinned Qwen model snapshots for Stage D."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from huggingface_hub import snapshot_download


def download_qwen(
    model_id: str = "Qwen/Qwen3-4B-Instruct-2507",
    output_dir: str = "results/model_download",
    local_dir: str | None = None,
    revision: str | None = None,
) -> dict[str, Any]:
    path = snapshot_download(
        repo_id=model_id,
        revision=revision,
        local_dir=local_dir,
        local_dir_use_symlinks=False if local_dir else None,
    )
    model_path = Path(path)
    files = [item for item in model_path.rglob("*") if item.is_file()]
    total_bytes = sum(item.stat().st_size for item in files)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": model_id,
        "revision": revision,
        "snapshot_path": str(model_path),
        "n_files": len(files),
        "total_bytes": total_bytes,
        "total_gib": total_bytes / 1024**3,
    }
    summary_path = out / "qwen_download.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"summary": str(summary_path), **summary}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download Qwen model snapshot for Stage D.")
    parser.add_argument("--model-id", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--output-dir", default="results/model_download")
    parser.add_argument("--local-dir", default=None)
    parser.add_argument("--revision", default=None)
    args = parser.parse_args()
    print(json.dumps(download_qwen(args.model_id, args.output_dir, args.local_dir, args.revision), indent=2, sort_keys=True))