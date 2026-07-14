"""Run EBW Track A obligation-sketch synthesis with a frozen local Qwen model."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import posixpath
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from analysis.appworld_broad_value_bound_template_verifier import run_task_trace, type_mutation
from analysis.recurrent_appworld_generated_typed_provenance_development_v6 import install_v6_compatibility
from experiments.ebw_obligation_sketch import barrier_unique_validity, parse_track_a_sketch
from experiments.appworld_trace_replay import canonical

REPO_ROOT = Path(__file__).resolve().parents[1]
SENSITIVE_KEYS = ("token", "password", "username", "email", "phone", "card", "cvv")


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("<REDACTED>" if any(token in str(key).lower() for token in SENSITIVE_KEYS) else sanitize(child)) for key, child in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def parse_ref(ref: str) -> tuple[str, int | None, list[Any]]:
    if ref.startswith("read_group_"):
        return ref, None, []
    match = re.match(r"read_(\d+)(?:\.(.*))?$", str(ref))
    if not match:
        raise KeyError(ref)
    call_index = int(match.group(1))
    suffix = match.group(2) or ""
    if suffix.startswith("response."):
        suffix = suffix[len("response.") :]
    path: list[Any] = []
    for item in [part for part in suffix.split(".") if part != ""]:
        path.append(int(item) if item.isdigit() else item)
    return "read", call_index, path


def lookup_path(value: Any, path: list[Any]) -> Any:
    current = value
    for item in path:
        current = current[item]
    return current


def values_for_key(value: Any, key_name: str) -> list[Any]:
    output: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == key_name:
                output.append(child)
            output.extend(values_for_key(child, key_name))
    elif isinstance(value, list):
        for child in value:
            output.extend(values_for_key(child, key_name))
    return output


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def norm_path(value: Any) -> str:
    text = str(value).strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    return text.rstrip("/") or text


def same_value(left: Any, right: Any) -> bool:
    return canonical(left) == canonical(right)


def unique(values: list[Any]) -> list[Any]:
    output = []
    seen = set()
    for value in values:
        key = canonical(value)
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output


def read_by_id(calls: list[Any], call_index: int) -> Any:
    for call in calls:
        if call.index == call_index and call.method == "get":
            return call
    raise KeyError(call_index)


def effect_by_id(calls: list[Any], call_index: int) -> Any:
    for call in calls:
        if call.index == call_index and call.method != "get":
            return call
    raise KeyError(call_index)


def candidate_values_for_sketch(sketch: dict[str, Any], calls: list[Any], call_index: int) -> list[Any]:
    obligation = sketch["obligation"]
    if obligation == "derived_path_binding":
        _, read_index, path = parse_ref(str(sketch["source_read_id"]))
        source = lookup_path(read_by_id(calls[:call_index], int(read_index)).response, path)
        return [posixpath.basename(norm_path(source))]
    if obligation == "literal_intent_binding":
        return []
    if obligation == "prior_effect_binding":
        effect_id = str(sketch["effect_step_id"])
        if not effect_id.startswith("effect_"):
            return []
        effect = effect_by_id(calls[:call_index], int(effect_id.split("_", 1)[1]))
        return values_for_key(effect.response, str(sketch["effect_field"]))
    if obligation == "ordered_role_binding":
        source = str(sketch["order_source_read_id"])
        field = str(sketch["order_field"])
        if source.startswith("read_group_spotify_search_songs_before_"):
            values = []
            for call in calls[:call_index]:
                if call.method == "get" and call.app_name == "spotify" and call.api_name == "search_songs":
                    values.extend(values_for_key(call.response, field))
            return unique(values)
        _, read_index, path = parse_ref(source)
        response = lookup_path(read_by_id(calls[:call_index], int(read_index)).response, path)
        return unique(values_for_key(response, field))
    return []


def verify_sketch(sketch: dict[str, Any], candidate: Any, calls: list[Any], call_index: int, instruction: str, ordinal: int) -> tuple[bool, str | None]:
    target_arg = sketch.get("target_arg")
    if not isinstance(target_arg, str):
        return False, "parse_error"
    try:
        if sketch["obligation"] == "derived_path_binding":
            values = candidate_values_for_sketch(sketch, calls, call_index)
            return any(posixpath.basename(norm_path(candidate)).casefold() == normalize_text(value) for value in values), None
        if sketch["obligation"] == "literal_intent_binding":
            span = sketch["user_span"]
            text = instruction[int(span["start"]): int(span["end"])]
            return normalize_text(text) == normalize_text(candidate), None
        if sketch["obligation"] == "prior_effect_binding":
            return any(same_value(candidate, value) for value in candidate_values_for_sketch(sketch, calls, call_index)), None
        if sketch["obligation"] == "ordered_role_binding":
            sequence = candidate_values_for_sketch(sketch, calls, call_index)
            return ordinal < len(sequence) and same_value(candidate, sequence[ordinal]), None
    except Exception:
        return False, "binding_mismatch"
    return False, "role_mismatch"


def adversarial_candidate(sketch: dict[str, Any], live_value: Any, calls: list[Any], call_index: int) -> Any:
    for value in candidate_values_for_sketch(sketch, calls, call_index):
        if not same_value(value, live_value):
            return value
    return type_mutation(live_value)


def make_prompt(base_prompt: str, row: dict[str, Any], calls: list[Any], instruction: str) -> str:
    call_index = int(row["call_index"])
    target = calls[call_index]
    pre_reads = [call for call in calls[:call_index] if call.method == "get" and call.app_name != "supervisor"]
    prior_effects = [call for call in calls[:call_index] if call.method != "get" and call.app_name != "supervisor"]
    context = {
        "task_text": instruction,
        "candidate_action": {"method": target.method, "app": target.app_name, "api_name": target.api_name, "arguments": sanitize(target.arguments), "target_arg": row["field_name"]},
        "immutable_pre_write_reads": [{"read_id": f"read_{call.index}", "app": call.app_name, "api_name": call.api_name, "arguments": sanitize(call.arguments), "response": sanitize(call.response)} for call in pre_reads],
        "prior_effects": [{"effect_step_id": f"effect_{call.index}", "app": call.app_name, "api_name": call.api_name, "arguments": sanitize(call.arguments), "response": sanitize(call.response)} for call in prior_effects],
    }
    return base_prompt + "\n\nNow synthesize the sketch for this input. Return JSON only.\n```json\n" + json.dumps(context, indent=2, sort_keys=True, ensure_ascii=False) + "\n```\n"


@torch.no_grad()
def generate_text(model: Any, tokenizer: Any, prompt: str, max_new_tokens: int) -> tuple[str, int, int]:
    inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
    ids = inputs.input_ids.to(model.device)
    out = model.generate(ids, do_sample=False, max_new_tokens=max_new_tokens, pad_token_id=tokenizer.pad_token_id, eos_token_id=tokenizer.eos_token_id, use_cache=True)
    generated = out[:, ids.shape[1]:]
    return tokenizer.decode(generated[0], skip_special_tokens=True).strip(), int(ids.shape[1]), int(generated.shape[1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_execution_preflight_v1"))
    parser.add_argument("--model-record", type=Path, default=Path("results/model_download/qwen3_4b_instruct_2507/qwen_download.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v1"))
    parser.add_argument("--root", type=Path, default=Path("external_repos/appworld_generated_broad_schema_v1"))
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-input-tokens", type=int, default=28672)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite EBW Track A model run")
    output_dir.mkdir(parents=True)

    install_v6_compatibility()
    from appworld import update_root

    root = resolve(args.root)
    update_root(str(root))
    preflight = load_json(resolve(args.preflight_dir) / "preflight.json")
    manifest = load_json(resolve(args.preflight_dir) / "evaluation_manifest.json")
    model_record = load_json(args.model_record)
    base_prompt = (resolve("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v1/track_a_prompt_template_filled.md")).read_text()
    rows = manifest["rows"][: args.limit or None]

    tokenizer = AutoTokenizer.from_pretrained(model_record["snapshot_path"], trust_remote_code=True, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(model_record["snapshot_path"], torch_dtype=torch.bfloat16, trust_remote_code=True, local_files_only=True).to(torch.device(args.device)).eval()
    model.config.use_cache = True

    traces: dict[str, list[Any]] = {}
    raw_rows = []
    result_rows = []
    counts: Counter[str] = Counter()
    parse_ok = 0
    skipped_long = 0
    total_prompt_tokens = 0
    total_output_tokens = 0
    for index, row in enumerate(rows):
        task_id = row["task_id"]
        if task_id not in traces:
            ok, calls, error = run_task_trace(task_id)
            if not ok:
                raise RuntimeError((task_id, error))
            traces[task_id] = calls
        calls = traces[task_id]
        instruction = load_json(root / "data/tasks" / task_id / "specs.json")["instruction"]
        prompt = make_prompt(base_prompt, row, calls, instruction)
        prompt_tokens = len(tokenizer(prompt, add_special_tokens=False).input_ids)
        if prompt_tokens > args.max_input_tokens:
            skipped_long += 1
            outcome = "abstain_no_valid"
            result_rows.append({"instance_id": row["instance_id"], "task_id": task_id, "decision": outcome, "typed_reason": "missing_read", "parse_ok": False, "skipped_long_prompt": True, "prompt_tokens": prompt_tokens})
            counts[outcome] += 1
            continue
        text, input_tokens, output_tokens = generate_text(model, tokenizer, prompt, args.max_new_tokens)
        total_prompt_tokens += input_tokens
        total_output_tokens += output_tokens
        parsed = parse_track_a_sketch(text)
        repaired = False
        if not parsed.ok:
            retry_prompt = prompt + "\nYour previous output was not valid JSON for the frozen grammar. Emit valid JSON only.\n"
            text2, input2, output2 = generate_text(model, tokenizer, retry_prompt, args.max_new_tokens)
            total_prompt_tokens += input2
            total_output_tokens += output2
            parsed = parse_track_a_sketch(text2)
            repaired = parsed.ok
            raw_text = text2
        else:
            raw_text = text
        raw_rows.append({"instance_id": row["instance_id"], "output": raw_text, "parse_ok": parsed.ok, "used_repair": repaired})
        if not parsed.ok or parsed.sketch is None:
            outcome = "abstain_no_valid"
            result_rows.append({"instance_id": row["instance_id"], "task_id": task_id, "decision": outcome, "typed_reason": "parse_error", "parse_ok": False, "used_repair": repaired, "prompt_tokens": input_tokens, "output_tokens": output_tokens})
            counts[outcome] += 1
            continue
        parse_ok += 1
        target_call = calls[int(row["call_index"])]
        live_value = target_call.arguments[row["field_name"]]
        adv = adversarial_candidate(parsed.sketch, live_value, calls, int(row["call_index"]))
        live_valid, live_reason = verify_sketch(parsed.sketch, live_value, calls, int(row["call_index"]), instruction, int(row.get("write_ordinal_for_schema", 0)))
        adv_valid, adv_reason = verify_sketch(parsed.sketch, adv, calls, int(row["call_index"]), instruction, int(row.get("write_ordinal_for_schema", 0)))
        barrier = barrier_unique_validity({"live": live_valid, "adversarial": adv_valid})
        if barrier["decision"] != "commit":
            outcome = "ambiguous_both_valid" if barrier["typed_reason"] == "competing_valid" else "abstain_no_valid"
        elif barrier["candidate_id"] == "live":
            outcome = "commit_live"
        else:
            outcome = "unsafe_unique_wrong"
        counts[outcome] += 1
        result_rows.append({"instance_id": row["instance_id"], "task_id": task_id, "decision": outcome, "typed_reason": barrier["typed_reason"] or live_reason or adv_reason, "parse_ok": True, "used_repair": repaired, "obligation": parsed.sketch["obligation"], "prompt_tokens": input_tokens, "output_tokens": output_tokens})
        if (index + 1) % 10 == 0:
            write_json(output_dir / "checkpoint.json", {"processed": index + 1, "counts": dict(counts), "parse_ok": parse_ok, "skipped_long": skipped_long})

    write_json(output_dir / "raw_model_outputs.json", {"schema": "ebw_track_a_raw_model_outputs_v1", "rows": raw_rows})
    write_json(output_dir / "rows.json", {"schema": "ebw_track_a_model_rows_v1", "rows": result_rows})
    safe = int(counts.get("commit_live", 0))
    unsafe = int(counts.get("unsafe_unique_wrong", 0))
    ga_pass = unsafe == 0 and safe >= 167
    payload = {"schema": "ebw_track_a_model_run_v1", "status": "RPD_EBW_TRACK_A_MODEL_RUN_COMPLETE", "limit": args.limit, "processed": len(rows), "decision_counts": dict(sorted(counts.items())), "parse_ok": parse_ok, "parse_rate": parse_ok / max(1, len(rows) - skipped_long), "skipped_long_prompts": skipped_long, "safe_commit_recovery": safe / 334, "ga_main_pass": ga_pass, "total_prompt_tokens": total_prompt_tokens, "total_output_tokens": total_output_tokens, "model_id": model_record["model_id"], "preflight_sha256": file_hash(resolve(args.preflight_dir) / "preflight.json"), "sealed_variations_opened": False}
    write_json(output_dir / "results.json", payload)
    (output_dir / "REPORT.md").write_text("\n".join(["# EBW Track A Model Run", "", f"## Status: **`{payload['status']}`**", "", f"- Processed: {len(rows)}", f"- Decision counts: {dict(sorted(counts.items()))}", f"- Parse rate: {payload['parse_rate']:.3f}", f"- Safe commit recovery: {payload['safe_commit_recovery']:.3f}", f"- GA-main pass: {ga_pass}", "- Sealed variations 10-12 opened: No"]) + "\n")
    print(json.dumps({"status": payload["status"], "processed": len(rows), "counts": payload["decision_counts"], "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()