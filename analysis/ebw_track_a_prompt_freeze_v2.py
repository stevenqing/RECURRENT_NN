"""Build EBW Track A prompt v2 from the frozen dev slice."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_prompt_freeze import compact_context, expected_sketch, run_task_trace
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


def example_line(obligation: str, context: dict[str, Any], sketch: dict[str, Any]) -> str:
    compact = {
        "input": context,
        "output": sketch,
    }
    return f"Example {obligation}: " + json.dumps(compact, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, default=Path("specs/recurrent_parallel_ebw_track_a_prompt_protocol_v2.json"))
    parser.add_argument("--dev-slice", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_dev_slice_v1/dev_slice_manifest.json"))
    parser.add_argument("--template", type=Path, default=Path("specs/recurrent_parallel_ebw_track_a_prompt_template_v2.md"))
    parser.add_argument("--root", type=Path, default=Path("external_repos/appworld_generated_broad_schema_v1"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v2"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite EBW Track A prompt v2 freeze")

    protocol = load_json(args.protocol)
    install_v6_compatibility()
    from appworld import update_root

    root = resolve(args.root)
    update_root(str(root))
    dev_slice_path = resolve(args.dev_slice)
    template_path = resolve(args.template)
    dev_slice = load_json(dev_slice_path)
    rows_by_id = {row["instance_id"]: row for row in dev_slice["rows"]}
    examples = {}
    example_rows = []
    for obligation in sorted(dev_slice["example_ids"]):
        row = rows_by_id[dev_slice["example_ids"][obligation]]
        ok, calls, error = run_task_trace(row["task_id"])
        if not ok:
            raise RuntimeError((row["task_id"], error))
        instruction = load_json(root / "data/tasks" / row["task_id"] / "specs.json")["instruction"]
        context = compact_context(row, calls, instruction)
        sketch = expected_sketch(row, calls, instruction)
        parsed = parse_track_a_sketch(sketch)
        if not parsed.ok:
            raise RuntimeError((row["instance_id"], parsed))
        line = example_line(obligation, context, sketch)
        examples[obligation] = line
        example_rows.append({
            "obligation": obligation,
            "instance_id": row["instance_id"],
            "task_id": row["task_id"],
            "target_schema": f"{row['method']}.{row['app']}.{row['api_name']}.{row['field_name']}",
            "expected_sketch": sketch,
            "example_line_sha256": text_hash(line),
        })
    template = template_path.read_text()
    replacements = {
        "{{example_derived_path_binding}}": examples["derived_path_binding"],
        "{{example_literal_intent_binding}}": examples["literal_intent_binding"],
        "{{example_prior_effect_binding}}": examples["prior_effect_binding"],
        "{{example_ordered_role_binding}}": examples["ordered_role_binding"],
        "{{input_json}}": "{{input_json}}",
    }
    filled = template
    for key, value in replacements.items():
        filled = filled.replace(key, value)
    output_dir.mkdir(parents=True)
    prompt_path = output_dir / "track_a_prompt_template_v2_filled.md"
    prompt_path.write_text(filled)
    examples_path = output_dir / "few_shot_examples_v2.json"
    write_json(examples_path, {"schema": "ebw_track_a_few_shot_examples_v2", "rows": example_rows, "sealed_variations_opened": False})
    payload = {
        "schema": "ebw_track_a_prompt_freeze_v2",
        "status": protocol["verdicts"]["ready"],
        "prompt_template_sha256": file_hash(prompt_path),
        "few_shot_examples_sha256": file_hash(examples_path),
        "protocol_sha256": file_hash(resolve(args.protocol)),
        "source_template_sha256": file_hash(template_path),
        "dev_slice_manifest_sha256": file_hash(dev_slice_path),
        "parent_freeze_tag": protocol["parent_freeze_tag"],
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "prompt_freeze_v2.json", payload)
    report = [
        "# EBW Track A Prompt Freeze v2",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Prompt SHA256: `{payload['prompt_template_sha256']}`",
        "- Repair scope: no Markdown fences, final instruction is bare JSON only",
        "- Few-shot examples: 4",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Examples",
        "",
        "| Obligation | Instance ID | Task | Target schema |",
        "|---|---|---|---|",
    ]
    report += [f"| {row['obligation']} | {row['instance_id']} | {row['task_id']} | {row['target_schema']} |" for row in example_rows]
    (output_dir / "PROMPT_FREEZE_V2.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "prompt_sha256": payload["prompt_template_sha256"], "report": str((output_dir / "PROMPT_FREEZE_V2.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()