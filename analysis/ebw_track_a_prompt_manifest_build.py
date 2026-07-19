"""Build EBW Track A prompt/context manifest with AppWorld dependencies only."""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_prompt_freeze import compact_context, run_task_trace, sanitize
from analysis.ebw_track_a_v11_title_slug_feasibility import title_slug_candidate
from analysis.ebw_track_a_v17_archive_path_feasibility import archive_path_candidate
from analysis.ebw_track_a_v21_source_path_identity_feasibility import source_path_identity_candidate
from analysis.ebw_track_a_v25_ordered_note_title_identity_feasibility import ordered_note_title_identity_candidate
from analysis.ebw_track_a_v27_prior_effect_playlist_feasibility import prior_effect_playlist_candidate
from analysis.ebw_track_a_v9_path_pair_feasibility import path_pair_candidate
from analysis.recurrent_appworld_generated_typed_provenance_development_v6 import install_v6_compatibility

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


def load_source_manifest(preflight_dir: Path, evaluation_manifest: Path | None) -> tuple[dict[str, Any] | None, dict[str, Any], Path | None, Path]:
    if evaluation_manifest is not None:
        manifest_path = resolve(evaluation_manifest)
        return None, load_json(manifest_path), None, manifest_path
    preflight_path = preflight_dir / "preflight.json"
    manifest_path = preflight_dir / "evaluation_manifest.json"
    return load_json(preflight_path), load_json(manifest_path), preflight_path, manifest_path


def ordinal_for(row: dict[str, Any], ordinal_by_instance: dict[str, int]) -> int:
    if "write_ordinal_for_schema" in row:
        return int(row["write_ordinal_for_schema"])
    instance_id = row["instance_id"]
    if instance_id not in ordinal_by_instance:
        raise RuntimeError(f"missing write_ordinal_for_schema for {instance_id}")
    return ordinal_by_instance[instance_id]


def prompt_text_from_messages(messages: list[dict[str, str]], response_prefill: str) -> str:
    parts = []
    for message in messages:
        parts.append(f"[{message['role'].upper()}]\n{message['content']}")
    parts.append(f"[ASSISTANT]\n{response_prefill}")
    return "\n\n".join(parts)


def required_obligation(row: dict[str, Any]) -> str | None:
    if row.get("required_obligation"):
        return str(row["required_obligation"])
    if row["proof_family"] == "filesystem_path_derivation_proof":
        return "derived_path_binding"
    if row["proof_family"] == "literal_text_derivation_proof":
        return "literal_intent_binding"
    if row["proof_family"] == "state_transition_membership_proof":
        if row["api_name"] == "add_song_to_playlist" and row["field_name"] == "playlist_id":
            return "prior_effect_binding"
        return "ordered_role_binding"
    return None


def literal_span_candidates(task_text: str) -> list[dict[str, Any]]:
    candidates = []
    patterns = [r'"([^"\n]+)"', r"'([^'\n]+)'", r"\u201c([^\u201d\n]+)\u201d", r"\u2018([^\u2019\n]+)\u2019"]
    seen: set[tuple[int, int]] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, task_text):
            span = (match.start(1), match.end(1))
            if span in seen:
                continue
            seen.add(span)
            candidates.append({"start": span[0], "end": span[1], "text": match.group(1)})
    return sorted(candidates, key=lambda item: (item["start"], item["end"], item["text"]))


def values_for_key(value: Any, key: str) -> list[Any]:
    out = []
    if isinstance(value, dict):
        for current_key, child in value.items():
            if current_key == key:
                out.append(child)
            out.extend(values_for_key(child, key))
    elif isinstance(value, list):
        for child in value:
            out.extend(values_for_key(child, key))
    return out


def canonical_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def same_value(left: Any, right: Any) -> bool:
    return canonical_key(left) == canonical_key(right)


def norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def unique(values: list[Any]) -> list[Any]:
    output = []
    seen: set[str] = set()
    for value in values:
        key = canonical_key(value)
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output


def norm_path(value: Any) -> str:
    text = str(value).replace("\\", "/").strip()
    while "//" in text:
        text = text.replace("//", "/")
    return text.rstrip("/") or text


def scalar_path_items(value: Any, path: str = "response") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        output: list[tuple[str, Any]] = []
        for key, child in sorted(value.items()):
            output.extend(scalar_path_items(child, f"{path}.{key}"))
        return output
    if isinstance(value, list):
        output = []
        for index, child in enumerate(value):
            output.extend(scalar_path_items(child, f"{path}.{index}"))
        return output
    return [(path, value)]


def derived_path_candidates(context: dict[str, Any]) -> list[dict[str, Any]]:
    args = context["candidate_action"]["arguments"]
    target_arg = context["candidate_action"]["target_arg"]
    source_value = args.get("source_file_path") or args.get("directory_path") or args.get(target_arg)
    target_value = args.get(target_arg)
    if source_value is None or target_value is None:
        return []
    source_norm = norm_path(source_value)
    target_basename = posixpath.basename(norm_path(target_value))
    exact: list[dict[str, Any]] = []
    basename: list[dict[str, Any]] = []
    for read in context["pre_write_reads"]:
        for source_path_field, value in scalar_path_items(read["response"]):
            value_norm = norm_path(value)
            if value_norm == source_norm:
                exact.append({"source_read_id": read["read_id"], "source_path_field": source_path_field, "derivation": "basename", "target_arg": target_arg, "match_policy": "exact_source_file_path"})
            elif posixpath.basename(value_norm) == target_basename:
                basename.append({"source_read_id": read["read_id"], "source_path_field": source_path_field, "derivation": "basename", "target_arg": target_arg, "match_policy": "basename_fallback"})
    return exact or basename


def ordered_role_candidates(context: dict[str, Any], row: dict[str, Any], ordinal: int) -> list[dict[str, Any]]:
    target_arg = context["candidate_action"]["target_arg"]
    live_value = context["candidate_action"]["arguments"].get(target_arg)
    if live_value is None:
        return []
    candidates = []
    grouped: dict[tuple[str, str], list[Any]] = {}
    for read in context["pre_write_reads"]:
        if read["app"] != context["candidate_action"]["app"]:
            continue
        values = values_for_key(read["response"], target_arg)
        if ordinal < len(values) and same_value(values[ordinal], live_value):
            candidates.append({"order_source_read_id": read["read_id"], "order_field": target_arg, "index_expr": "same_rank", "target_arg": target_arg, "match_policy": "individual_read_live_ordinal"})
        if values:
            grouped.setdefault((read["app"], read["api_name"]), []).extend(values)
    group_candidates = []
    for (app, api_name), values in sorted(grouped.items()):
        sequence = unique(values)
        if ordinal < len(sequence) and same_value(sequence[ordinal], live_value):
            group_candidates.append({"order_source_read_id": f"read_group_{app}_{api_name}_before_{row['call_index']}", "order_field": target_arg, "index_expr": "same_rank", "target_arg": target_arg, "match_policy": "read_group_live_ordinal"})
    return group_candidates + candidates


def build_v3_messages(assets: dict[str, Any], row: dict[str, Any], context: dict[str, Any], ordinal: int) -> tuple[list[dict[str, str]], str, dict[str, Any]]:
    allowed_schemas = assets["allowed_schemas"]
    output_examples = assets["output_examples"]
    role_constraint = None
    obligation = required_obligation(row) if "role_constraint_policy" in assets else None
    if obligation is not None:
        allowed_schemas = [schema for schema in allowed_schemas if schema["obligation"] == obligation]
        output_examples = [example for example in output_examples if example["obligation"] == obligation]
        role_constraint = {
            "required_obligation": obligation,
            "source_proof_family": row["proof_family"],
            "source_api_name": row["api_name"],
            "source_field_name": row["field_name"],
        }
    user_payload = {
        "response_contract": assets["response_contract"],
        "allowed_schemas": allowed_schemas,
        "valid_output_examples": output_examples,
        "instance_json": context,
    }
    if role_constraint is not None:
        user_payload["role_constraint"] = role_constraint
        if obligation == "literal_intent_binding" and "literal_span_candidate_policy" in assets:
            candidates = literal_span_candidates(context["task_text"])
            user_payload["literal_span_candidates"] = candidates
            if "literal_span_selection_policy" in assets:
                if ordinal >= len(candidates):
                    raise RuntimeError(("missing_required_literal_span", row["instance_id"], ordinal, len(candidates)))
                user_payload["required_literal_span_index"] = ordinal
                user_payload["required_literal_span"] = candidates[ordinal]
                live_value = context["candidate_action"]["arguments"].get(context["candidate_action"]["target_arg"])
                if norm_text(candidates[ordinal]["text"]) != norm_text(live_value):
                    raise RuntimeError(("required_literal_span_not_live_value", row["instance_id"], ordinal, candidates[ordinal]["text"], live_value))
        if obligation == "derived_path_binding" and "derived_path_candidate_policy" in assets:
            user_payload["derived_path_candidates"] = derived_path_candidates(context)
        if obligation == "ordered_role_binding" and "ordered_role_candidate_policy" in assets:
            candidates = ordered_role_candidates(context, row, ordinal)
            if not candidates:
                raise RuntimeError(("missing_ordered_role_candidate", row["instance_id"], ordinal))
            user_payload["ordered_role_candidates"] = candidates
        if obligation == "prior_effect_binding" and "prior_effect_candidate_policy" in assets:
            candidate = prior_effect_playlist_candidate({"context": context, "live_arguments": sanitize(context["candidate_action"]["arguments"])})
            if candidate is None or not candidate["match"]:
                raise RuntimeError(("missing_prior_effect_candidate", row["instance_id"], candidate))
            user_payload["prior_effect_candidates"] = [candidate]
        if obligation == "path_pair_transform_binding" and "path_pair_candidate_policy" in assets:
            candidate = path_pair_candidate({"context": context, "live_arguments": sanitize(context["candidate_action"]["arguments"])})
            if candidate is None or not candidate["match"]:
                raise RuntimeError(("missing_path_pair_candidate", row["instance_id"], candidate))
            user_payload["path_pair_transform_candidates"] = [candidate]
        if obligation == "title_slug_export_path_binding" and "title_slug_candidate_policy" in assets:
            candidate = title_slug_candidate({"context": context, "live_arguments": sanitize(context["candidate_action"]["arguments"])})
            if candidate is None or not candidate["match"]:
                raise RuntimeError(("missing_title_slug_candidate", row["instance_id"], candidate))
            user_payload["title_slug_export_path_candidates"] = [candidate]
        if obligation == "directory_basename_archive_path_binding" and "archive_path_candidate_policy" in assets:
            candidate = archive_path_candidate({"context": context, "live_arguments": sanitize(context["candidate_action"]["arguments"])})
            if candidate is None or not candidate["match"]:
                raise RuntimeError(("missing_archive_path_candidate", row["instance_id"], candidate))
            user_payload["directory_basename_archive_path_candidates"] = [candidate]
        if obligation == "source_path_identity_binding" and "source_path_identity_candidate_policy" in assets:
            candidate = source_path_identity_candidate({"context": context, "live_arguments": sanitize(context["candidate_action"]["arguments"])})
            if candidate is None or not candidate["match"]:
                raise RuntimeError(("missing_source_path_identity_candidate", row["instance_id"], candidate))
            user_payload["source_path_identity_candidates"] = [candidate]
        if obligation == "ordered_note_title_identity_binding" and "ordered_note_title_identity_candidate_policy" in assets:
            candidate = ordered_note_title_identity_candidate({"context": context, "live_arguments": sanitize(context["candidate_action"]["arguments"])})
            if candidate is None or not candidate["match"]:
                raise RuntimeError(("missing_ordered_note_title_identity_candidate", row["instance_id"], candidate))
            user_payload["ordered_note_title_identity_candidates"] = [candidate]
    user_content = assets["user_preamble"] + "\n" + json.dumps(user_payload, indent=2, sort_keys=True, ensure_ascii=False)
    messages = [
        {"role": "system", "content": assets["system_message"]},
        {"role": "user", "content": user_content},
    ]
    metadata = {
        "required_obligation": obligation,
        "literal_span_candidates": user_payload.get("literal_span_candidates"),
        "required_literal_span": user_payload.get("required_literal_span"),
        "required_literal_span_index": user_payload.get("required_literal_span_index"),
        "literal_span_selection_policy": assets.get("literal_span_selection_policy"),
        "derived_path_candidates": user_payload.get("derived_path_candidates"),
        "ordered_role_candidates": user_payload.get("ordered_role_candidates"),
        "ordered_role_candidate_policy": assets.get("ordered_role_candidate_policy"),
        "prior_effect_candidates": user_payload.get("prior_effect_candidates"),
        "prior_effect_candidate_policy": assets.get("prior_effect_candidate_policy"),
        "path_pair_transform_candidates": user_payload.get("path_pair_transform_candidates"),
        "path_pair_candidate_policy": assets.get("path_pair_candidate_policy"),
        "title_slug_export_path_candidates": user_payload.get("title_slug_export_path_candidates"),
        "title_slug_candidate_policy": assets.get("title_slug_candidate_policy"),
        "directory_basename_archive_path_candidates": user_payload.get("directory_basename_archive_path_candidates"),
        "archive_path_candidate_policy": assets.get("archive_path_candidate_policy"),
        "source_path_identity_candidates": user_payload.get("source_path_identity_candidates"),
        "source_path_identity_candidate_policy": assets.get("source_path_identity_candidate_policy"),
        "ordered_note_title_identity_candidates": user_payload.get("ordered_note_title_identity_candidates"),
        "ordered_note_title_identity_candidate_policy": assets.get("ordered_note_title_identity_candidate_policy"),
    }
    return messages, assets["response_prefill"], {key: value for key, value in metadata.items() if value is not None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_execution_preflight_v1"))
    parser.add_argument("--evaluation-manifest", type=Path, default=None)
    parser.add_argument("--root", type=Path, default=Path("external_repos/appworld_generated_broad_schema_v1"))
    parser.add_argument("--prompt-template", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v1/track_a_prompt_template_filled.md"))
    parser.add_argument("--prompt-assets", type=Path, default=None)
    parser.add_argument("--ordinal-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_broad_value_bound_witness_preflight_v1/instance_manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_v1"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-ineligible", action="store_true")
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite EBW Track A prompt manifest")

    install_v6_compatibility()
    from appworld import update_root

    root = resolve(args.root)
    update_root(str(root))
    preflight_dir = resolve(args.preflight_dir)
    preflight, manifest, preflight_path, source_manifest_path = load_source_manifest(preflight_dir, args.evaluation_manifest)
    prompt_assets = load_json(args.prompt_assets) if args.prompt_assets else None
    base_prompt = None if prompt_assets else resolve(args.prompt_template).read_text()
    ordinal_manifest_path = resolve(args.ordinal_manifest)
    ordinal_manifest = load_json(ordinal_manifest_path)
    ordinal_by_instance = {row["instance_id"]: int(row["write_ordinal_for_schema"]) for row in ordinal_manifest["rows"]}
    rows = manifest["rows"][: args.limit or None]
    trace_cache: dict[str, list[Any]] = {}
    output_rows = []
    skipped_rows = []
    for row in rows:
        task_id = row["task_id"]
        if task_id not in trace_cache:
            ok, calls, error = run_task_trace(task_id)
            if not ok:
                raise RuntimeError((task_id, error))
            trace_cache[task_id] = calls
        calls = trace_cache[task_id]
        instruction = load_json(root / "data/tasks" / task_id / "specs.json")["instruction"]
        context = compact_context(row, calls, instruction)
        write_ordinal = ordinal_for(row, ordinal_by_instance)
        if prompt_assets:
            try:
                messages, response_prefill, prompt_metadata = build_v3_messages(prompt_assets, row, context, write_ordinal)
            except RuntimeError as error:
                if not args.skip_ineligible:
                    raise
                skipped_rows.append({"instance_id": row["instance_id"], "task_id": task_id, "reason": repr(error)})
                continue
            prompt = prompt_text_from_messages(messages, response_prefill)
            prompt_protocol = prompt_assets["prompt_protocol"]
        else:
            messages = None
            response_prefill = ""
            prompt_metadata = {}
            prompt = base_prompt.replace("{{input_json}}", json.dumps(context, indent=2, sort_keys=True, ensure_ascii=False))
            prompt_protocol = "raw_completion_template"
        target_call = calls[int(row["call_index"])]
        output_row = {
            "instance_id": row["instance_id"],
            "task_id": task_id,
            "call_index": row["call_index"],
            "field_name": row["field_name"],
            "proof_family": row["proof_family"],
            "write_ordinal_for_schema": write_ordinal,
            "prompt": prompt,
            "prompt_sha256": text_hash(prompt),
            "prompt_protocol": prompt_protocol,
            "context": context,
            "live_arguments": sanitize(target_call.arguments),
        }
        if messages is not None:
            output_row.update(
                {
                    "messages": messages,
                    "messages_sha256": text_hash(json.dumps(messages, sort_keys=True, ensure_ascii=False)),
                    "response_prefill": response_prefill,
                    "retry_user_message": prompt_assets["retry_user_message"],
                    "stop_policy": prompt_assets["stop_policy"],
                }
            )
            output_row.update(prompt_metadata)
        output_rows.append(output_row)
    output_dir.mkdir(parents=True)
    prompt_path = output_dir / "prompt_manifest.json"
    manifest_payload = {"schema": "ebw_track_a_prompt_manifest_v1", "status": "RPD_EBW_TRACK_A_PROMPT_MANIFEST_READY", "rows": output_rows, "skipped_rows": skipped_rows, "source_manifest_sha256": file_hash(source_manifest_path), "ordinal_manifest_sha256": file_hash(ordinal_manifest_path), "sealed_variations_opened": False}
    if preflight_path is not None:
        manifest_payload["source_preflight_sha256"] = file_hash(preflight_path)
    if prompt_assets:
        manifest_payload["prompt_assets_sha256"] = file_hash(resolve(args.prompt_assets))
        manifest_payload["prompt_protocol"] = prompt_assets["prompt_protocol"]
    write_json(prompt_path, manifest_payload)
    payload = {"schema": "ebw_track_a_prompt_manifest_build_v1", "status": "RPD_EBW_TRACK_A_PROMPT_MANIFEST_READY", "rows": len(output_rows), "skipped_rows": len(skipped_rows), "limit": args.limit, "prompt_manifest_sha256": file_hash(prompt_path), "prompt_protocol": manifest_payload.get("prompt_protocol", "raw_completion_template"), "source_manifest_sha256": file_hash(source_manifest_path), "ordinal_manifest_sha256": file_hash(ordinal_manifest_path), "sealed_variations_opened": False, "model_gpu_docker_used": False}
    write_json(output_dir / "manifest_build.json", payload)
    (output_dir / "PROMPT_MANIFEST.md").write_text("\n".join(["# EBW Track A Prompt Manifest", "", f"## Status: **`{payload['status']}`**", "", f"- Rows: {len(output_rows)}", f"- Skipped rows: {len(skipped_rows)}", f"- Limit: {args.limit}", f"- Prompt protocol: `{payload['prompt_protocol']}`", "- Sealed variations 10-12 opened: No", "- Model/GPU/Docker actions: No"]) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(output_rows), "report": str((output_dir / "PROMPT_MANIFEST.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()