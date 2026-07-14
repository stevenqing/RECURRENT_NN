"""Build EBW Track A prompt v3 assets from the frozen dev slice."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_prompt_freeze import expected_sketch, run_task_trace
from analysis.recurrent_appworld_generated_typed_provenance_development_v6 import install_v6_compatibility
from experiments.ebw_obligation_sketch import parse_track_a_sketch

REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, default=Path("specs/recurrent_parallel_ebw_track_a_prompt_protocol_v3.json"))
    parser.add_argument("--dev-slice", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_dev_slice_v1/dev_slice_manifest.json"))
    parser.add_argument("--template", type=Path, default=Path("specs/recurrent_parallel_ebw_track_a_prompt_template_v3.json"))
    parser.add_argument("--root", type=Path, default=Path("external_repos/appworld_generated_broad_schema_v1"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v3"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite EBW Track A prompt v3 freeze")

    protocol = load_json(args.protocol)
    template = load_json(args.template)
    install_v6_compatibility()
    from appworld import update_root

    root = resolve(args.root)
    update_root(str(root))
    dev_slice_path = resolve(args.dev_slice)
    dev_slice = load_json(dev_slice_path)
    rows_by_id = {row["instance_id"]: row for row in dev_slice["rows"]}
    example_rows = []
    output_examples = []
    for obligation in sorted(dev_slice["example_ids"]):
        row = rows_by_id[dev_slice["example_ids"][obligation]]
        ok, calls, error = run_task_trace(row["task_id"])
        if not ok:
            raise RuntimeError((row["task_id"], error))
        instruction = load_json(root / "data/tasks" / row["task_id"] / "specs.json")["instruction"]
        sketch = expected_sketch(row, calls, instruction)
        parsed = parse_track_a_sketch(sketch)
        if not parsed.ok:
            raise RuntimeError((row["instance_id"], parsed))
        output_examples.append(sketch)
        example_rows.append(
            {
                "obligation": obligation,
                "instance_id": row["instance_id"],
                "task_id": row["task_id"],
                "target_schema": f"{row['method']}.{row['app']}.{row['api_name']}.{row['field_name']}",
                "expected_sketch": sketch,
                "expected_sketch_sha256": text_hash(json.dumps(sketch, sort_keys=True, ensure_ascii=False)),
            }
        )

    assets = {
        "schema": "ebw_track_a_prompt_assets_v3",
        "prompt_protocol": "chat_template_json_prefill_v3",
        "system_message": template["system_message"],
        "user_preamble": template["user_preamble"],
        "allowed_schemas": template["allowed_schemas"],
        "response_contract": template["response_contract"],
        "output_examples": output_examples,
        "retry_user_message": template["retry_user_message"],
        "response_prefill": template["response_prefill"],
        "stop_policy": template["stop_policy"],
        "parser_policy": protocol["parser_policy"],
        "primary_gate_policy": protocol["primary_gate_policy"],
        "diagnostic_parser_policy": protocol["diagnostic_parser_policy"],
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    output_dir.mkdir(parents=True)
    assets_path = output_dir / "track_a_prompt_assets_v3.json"
    examples_path = output_dir / "few_shot_output_examples_v3.json"
    write_json(assets_path, assets)
    write_json(examples_path, {"schema": "ebw_track_a_few_shot_output_examples_v3", "rows": example_rows, "sealed_variations_opened": False})
    payload = {
        "schema": "ebw_track_a_prompt_freeze_v3",
        "status": protocol["verdicts"]["ready"],
        "prompt_assets_sha256": file_hash(assets_path),
        "few_shot_output_examples_sha256": file_hash(examples_path),
        "protocol_sha256": file_hash(resolve(args.protocol)),
        "source_template_sha256": file_hash(resolve(args.template)),
        "dev_slice_manifest_sha256": file_hash(dev_slice_path),
        "parent_freeze_tag": protocol["parent_freeze_tag"],
        "prompt_protocol": assets["prompt_protocol"],
        "output_examples": len(output_examples),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "prompt_freeze_v3.json", payload)
    report = [
        "# EBW Track A Prompt Freeze v3",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Prompt assets SHA256: `{payload['prompt_assets_sha256']}`",
        f"- Prompt protocol: `{payload['prompt_protocol']}`",
        "- Repair scope: chat-template messages, output-only examples, assistant `{` prefill, parser-based stop",
        "- Primary parser: strict full-text JSON only",
        "- Tolerant extraction: diagnostic/baseline-compatible only",
        "- Few-shot output examples: 4",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Examples",
        "",
        "| Obligation | Instance ID | Task | Target schema |",
        "|---|---|---|---|",
    ]
    report += [f"| {row['obligation']} | {row['instance_id']} | {row['task_id']} | {row['target_schema']} |" for row in example_rows]
    (output_dir / "PROMPT_FREEZE_V3.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "prompt_assets_sha256": payload["prompt_assets_sha256"], "report": str((output_dir / "PROMPT_FREEZE_V3.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()