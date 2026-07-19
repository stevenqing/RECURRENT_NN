"""Build EBW Track A v11 title-slug prompt assets from v9 assets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, default=Path("specs/recurrent_parallel_ebw_track_a_prompt_protocol_v11.json"))
    parser.add_argument("--parent-assets", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v9/track_a_prompt_assets_v9.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v11"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite EBW Track A prompt v11 freeze")

    protocol = load_json(args.protocol)
    parent_assets_path = resolve(args.parent_assets)
    assets = load_json(parent_assets_path)
    assets["schema"] = "ebw_track_a_prompt_assets_v11"
    assets["prompt_protocol"] = "chat_template_json_prefill_title_slug_v11"
    assets["title_slug_candidate_policy"] = protocol["title_slug_candidate_policy"]
    assets["allowed_schemas"] = assets["allowed_schemas"] + [protocol["title_slug_schema"]]
    assets["output_examples"] = assets["output_examples"] + [protocol["title_slug_example"]]
    assets["user_preamble"] = assets["user_preamble"] + " If required_obligation is title_slug_export_path_binding, every field except obligation must exactly match one title_slug_export_path_candidates item."
    output_dir.mkdir(parents=True)
    assets_path = output_dir / "track_a_prompt_assets_v11.json"
    write_json(assets_path, assets)
    payload = {
        "schema": "ebw_track_a_prompt_freeze_v11",
        "status": protocol["verdicts"]["ready"],
        "prompt_assets_sha256": file_hash(assets_path),
        "parent_prompt_assets_sha256": file_hash(parent_assets_path),
        "protocol_sha256": file_hash(resolve(args.protocol)),
        "parent_freeze_tag": protocol["parent_freeze_tag"],
        "prompt_protocol": assets["prompt_protocol"],
        "title_slug_candidate_policy": protocol["title_slug_candidate_policy"],
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "prompt_freeze_v11.json", payload)
    report = [
        "# EBW Track A Prompt Freeze v11",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Prompt assets SHA256: `{payload['prompt_assets_sha256']}`",
        f"- Parent v9 assets SHA256: `{payload['parent_prompt_assets_sha256']}`",
        f"- Prompt protocol: `{payload['prompt_protocol']}`",
        f"- Title-slug candidate policy: `{payload['title_slug_candidate_policy']}`",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
    ]
    (output_dir / "PROMPT_FREEZE_V11.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "prompt_assets_sha256": payload["prompt_assets_sha256"], "report": str((output_dir / "PROMPT_FREEZE_V11.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()