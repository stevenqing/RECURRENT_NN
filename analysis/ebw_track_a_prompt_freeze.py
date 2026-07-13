"""Build EBW Track A few-shot examples and prompt hash from frozen dev slice IDs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from analysis.appworld_broad_literal_text_derivation_verifier import quoted_literals
from analysis.appworld_broad_value_bound_template_verifier import run_task_trace, same_value
from analysis.recurrent_appworld_generated_typed_provenance_development_v6 import install_v6_compatibility
from experiments.ebw_obligation_sketch import parse_track_a_sketch
from experiments.appworld_trace_replay import canonical

REPO_ROOT = Path(__file__).resolve().parents[1]
SENSITIVE_KEYS = ("token", "password", "username", "email", "phone", "card", "cvv")


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


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        output = {}
        for key, child in value.items():
            if any(token in str(key).lower() for token in SENSITIVE_KEYS):
                output[key] = "<REDACTED>"
            else:
                output[key] = sanitize(child)
        return output
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def scalar_paths(value: Any, target: Any, path: list[Any] | None = None) -> list[list[Any]]:
    path = [] if path is None else path
    if same_value(value, target):
        return [path]
    found: list[list[Any]] = []
    if isinstance(value, dict):
        for key in sorted(value):
            found.extend(scalar_paths(value[key], target, path + [key]))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(scalar_paths(item, target, path + [index]))
    return found


def read_ref_for_value(calls: list[Any], call_index: int, target: Any) -> tuple[str, str] | None:
    for call in calls[:call_index]:
        if call.method != "get" or call.app_name == "supervisor":
            continue
        paths = scalar_paths(call.response, target)
        if paths:
            return f"read_{call.index}", "response." + ".".join(str(item) for item in paths[0])
    return None


def prior_create_playlist_effect(calls: list[Any], call_index: int) -> str | None:
    for call in reversed(calls[:call_index]):
        if call.method == "post" and call.app_name == "spotify" and call.api_name == "create_playlist":
            return f"effect_{call.index}"
    return None


def latest_queue_or_search_ref(calls: list[Any], call_index: int) -> str | None:
    queue_ref = None
    search_ref = None
    for call in calls[:call_index]:
        if call.method == "get" and call.app_name == "spotify" and call.api_name == "show_song_queue":
            queue_ref = f"read_{call.index}"
        if call.method == "get" and call.app_name == "spotify" and call.api_name == "search_songs":
            search_ref = f"read_group_spotify_search_songs_before_{call_index}"
    return queue_ref or search_ref


def instruction_span(instruction: str, target: Any) -> dict[str, int] | None:
    target_text = re.sub(r"\s+", " ", str(target).strip())
    if not target_text:
        return None
    # Prefer exact quoted spans already accepted by the literal verifier.
    for pattern in [r'"([^"\n]+)"', r"'([^'\n]+)'", r"“([^”\n]+)”", r"‘([^’\n]+)’"]:
        for match in re.finditer(pattern, instruction):
            if re.sub(r"\s+", " ", match.group(1).strip()).casefold() == target_text.casefold():
                return {"start": match.start(1), "end": match.end(1)}
    start = instruction.casefold().find(target_text.casefold())
    if start >= 0:
        return {"start": start, "end": start + len(target_text)}
    return None


def expected_sketch(row: dict[str, Any], calls: list[Any], instruction: str) -> dict[str, Any]:
    target_call = calls[int(row["call_index"])]
    arguments = target_call.arguments
    target_arg = row["field_name"]
    obligation = row["obligation"]
    if obligation == "derived_path_binding":
        source_path = arguments.get("source_file_path") or arguments.get("directory_path") or arguments.get(target_arg)
        ref = read_ref_for_value(calls, int(row["call_index"]), source_path)
        if ref is None:
            ref = ("read_missing_source", "response")
        return {"obligation": obligation, "source_read_id": ref[0], "source_path_field": ref[1], "derivation": "basename", "target_arg": target_arg}
    if obligation == "literal_intent_binding":
        span = instruction_span(instruction, arguments[target_arg])
        if span is None:
            span = {"start": 0, "end": 1}
        return {"obligation": obligation, "user_span": span, "target_arg": target_arg}
    if obligation == "prior_effect_binding":
        effect_id = prior_create_playlist_effect(calls, int(row["call_index"])) or "effect_missing"
        return {"obligation": obligation, "effect_step_id": effect_id, "effect_field": target_arg, "target_arg": target_arg}
    if obligation == "ordered_role_binding":
        read_id = latest_queue_or_search_ref(calls, int(row["call_index"])) or "read_missing_order"
        return {"obligation": obligation, "order_source_read_id": read_id, "order_field": target_arg, "index_expr": "same_rank", "target_arg": target_arg}
    raise RuntimeError(f"unsupported obligation: {obligation}")


def compact_context(row: dict[str, Any], calls: list[Any], instruction: str) -> dict[str, Any]:
    call_index = int(row["call_index"])
    target_call = calls[call_index]
    pre_reads = [call for call in calls[:call_index] if call.method == "get" and call.app_name != "supervisor"]
    prior_effects = [call for call in calls[:call_index] if call.method != "get" and call.app_name != "supervisor"]
    return {
        "task_text": instruction,
        "candidate_action": {
            "method": target_call.method,
            "app": target_call.app_name,
            "api_name": target_call.api_name,
            "arguments": sanitize(target_call.arguments),
            "target_arg": row["field_name"],
        },
        "pre_write_reads": [
            {"read_id": f"read_{call.index}", "app": call.app_name, "api_name": call.api_name, "method": call.method, "arguments": sanitize(call.arguments), "response": sanitize(call.response)}
            for call in pre_reads
        ],
        "prior_effects": [
            {"effect_step_id": f"effect_{call.index}", "app": call.app_name, "api_name": call.api_name, "method": call.method, "arguments": sanitize(call.arguments), "response": sanitize(call.response)}
            for call in prior_effects
        ],
    }


def example_block(row: dict[str, Any], context: dict[str, Any], sketch: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"### Example: {row['obligation']}",
            "Input:",
            "```json",
            json.dumps(context, indent=2, sort_keys=True, ensure_ascii=False),
            "```",
            "Output:",
            "```json",
            json.dumps(sketch, indent=2, sort_keys=True, ensure_ascii=False),
            "```",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev-slice", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_dev_slice_v1/dev_slice_manifest.json"))
    parser.add_argument("--template", type=Path, default=Path("specs/recurrent_parallel_ebw_track_a_prompt_template_v1.md"))
    parser.add_argument("--root", type=Path, default=Path("external_repos/appworld_generated_broad_schema_v1"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v1"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite EBW Track A prompt freeze")

    install_v6_compatibility()
    from appworld import update_root

    root = resolve(args.root)
    update_root(str(root))
    dev_slice_path = resolve(args.dev_slice)
    template_path = resolve(args.template)
    dev_slice = load_json(dev_slice_path)
    rows_by_id = {row["instance_id"]: row for row in dev_slice["rows"]}
    example_ids = dev_slice["example_ids"]
    examples = {}
    example_rows = []
    for obligation in sorted(example_ids):
        row = rows_by_id[example_ids[obligation]]
        baseline_pass, calls, error_type = run_task_trace(row["task_id"])
        if not baseline_pass:
            raise RuntimeError((row["task_id"], error_type))
        instruction = load_json(root / "data/tasks" / row["task_id"] / "specs.json")["instruction"]
        sketch = expected_sketch(row, calls, instruction)
        parsed = parse_track_a_sketch(sketch)
        if not parsed.ok:
            raise RuntimeError((row["instance_id"], parsed))
        context = compact_context(row, calls, instruction)
        block = example_block(row, context, sketch)
        examples[obligation] = block
        example_rows.append(
            {
                "obligation": obligation,
                "instance_id": row["instance_id"],
                "task_id": row["task_id"],
                "generator_id": row["generator_id"],
                "variation": row["variation"],
                "target_schema": f"{row['method']}.{row['app']}.{row['api_name']}.{row['field_name']}",
                "expected_sketch": sketch,
                "context_sha256": text_hash(json.dumps(context, sort_keys=True, ensure_ascii=False)),
                "example_block_sha256": text_hash(block),
            }
        )

    filled = template_path.read_text()
    replacements = {
        "{{example_derived_path_binding}}": examples["derived_path_binding"],
        "{{example_literal_intent_binding}}": examples["literal_intent_binding"],
        "{{example_prior_effect_binding}}": examples["prior_effect_binding"],
        "{{example_ordered_role_binding}}": examples["ordered_role_binding"],
    }
    for key, value in replacements.items():
        filled = filled.replace(key, value)
    output_dir.mkdir(parents=True)
    prompt_path = output_dir / "track_a_prompt_template_filled.md"
    prompt_path.write_text(filled)
    examples_path = output_dir / "few_shot_examples.json"
    write_json(examples_path, {"schema": "ebw_track_a_few_shot_examples_v1", "rows": example_rows, "contains_opened_task_context": True, "sealed_variations_opened": False})
    payload = {
        "schema": "ebw_track_a_prompt_freeze_v1",
        "status": "RPD_EBW_TRACK_A_PROMPT_EXAMPLES_READY_NOT_TAGGED",
        "prompt_template_sha256": file_hash(prompt_path),
        "few_shot_examples_sha256": file_hash(examples_path),
        "source_template_sha256": file_hash(template_path),
        "dev_slice_manifest_sha256": file_hash(dev_slice_path),
        "example_ids": example_ids,
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
        "contains_opened_task_context": True,
    }
    write_json(output_dir / "prompt_freeze.json", payload)
    report = [
        "# EBW Track A Prompt Freeze v1",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Prompt SHA256: `{payload['prompt_template_sha256']}`",
        "- Few-shot examples: 4",
        "- Contains opened task context: Yes",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Examples",
        "",
        "| Obligation | Instance ID | Task | Target schema |",
        "|---|---|---|---|",
    ]
    report += [f"| {row['obligation']} | {row['instance_id']} | {row['task_id']} | {row['target_schema']} |" for row in example_rows]
    (output_dir / "PROMPT_FREEZE.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "prompt_sha256": payload["prompt_template_sha256"], "report": str((output_dir / "PROMPT_FREEZE.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()