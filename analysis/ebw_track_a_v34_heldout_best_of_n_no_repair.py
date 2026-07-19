"""Held-out best-of-N proof sketch control without RepairAgent repair."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteriaList

from analysis.ebw_track_a_model_run_from_manifest import (
    DERIVED_PATH_ADVERSARY_POLICY,
    ParseableJsonStoppingCriteria,
    adversarial_candidate,
    render_prompt,
    row_evidence_values,
    row_verify,
    sketch_policy_valid,
)
from experiments.ebw_obligation_sketch import barrier_unique_validity, parse_track_a_sketch

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


@torch.no_grad()
def sample_generate(model: Any, tokenizer: Any, row: dict[str, Any], max_new_tokens: int, seed: int, temperature: float, top_p: float) -> tuple[str, int, int, str]:
    prompt, response_prefill, prompt_mode = render_prompt(tokenizer, row, retry=False)
    ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(model.device)
    stopping = StoppingCriteriaList([ParseableJsonStoppingCriteria(tokenizer, int(ids.shape[1]), response_prefill)]) if response_prefill else None
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    out = model.generate(
        ids,
        do_sample=True,
        temperature=temperature,
        top_p=top_p,
        max_new_tokens=max_new_tokens,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
        use_cache=True,
        stopping_criteria=stopping,
    )
    gen = out[:, ids.shape[1]:]
    text = tokenizer.decode(gen[0], skip_special_tokens=True)
    if response_prefill:
        text = response_prefill + text
    return text.strip(), int(ids.shape[1]), int(gen.shape[1]), prompt_mode


def evaluate_output(raw_output: str, row: dict[str, Any]) -> tuple[str, bool, dict[str, Any] | None]:
    parsed = parse_track_a_sketch(raw_output)
    if not parsed.ok or parsed.sketch is None:
        return "abstain_no_valid", parsed.ok, None
    if not sketch_policy_valid(parsed.sketch, row):
        return "abstain_no_valid", parsed.ok, parsed.sketch
    live_value = row["live_arguments"][row["field_name"]]
    evidence_values = row_evidence_values(parsed.sketch, row)
    adversarial = adversarial_candidate(parsed.sketch, live_value, evidence_values)
    live_valid = row_verify(parsed.sketch, live_value, row, evidence_values)
    adversarial_valid = row_verify(parsed.sketch, adversarial, row, evidence_values)
    barrier = barrier_unique_validity({"live": live_valid, "adversarial": adversarial_valid})
    if barrier["decision"] != "commit":
        decision = "ambiguous_both_valid" if barrier["typed_reason"] == "competing_valid" else "abstain_no_valid"
    elif barrier["candidate_id"] == "live":
        decision = "commit_live"
    else:
        decision = "unsafe_unique_wrong"
    return decision, parsed.ok, parsed.sketch


def aggregate_decision(sample_decisions: list[str]) -> str:
    if "unsafe_unique_wrong" in sample_decisions:
        return "unsafe_unique_wrong"
    if "commit_live" in sample_decisions:
        return "commit_live"
    if "ambiguous_both_valid" in sample_decisions:
        return "ambiguous_both_valid"
    return "abstain_no_valid"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v32_heldout_prompt_manifest_no_repair/prompt_manifest.json"))
    parser.add_argument("--baseline-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v32_heldout_no_repair/rows.json"))
    parser.add_argument("--model-record", type=Path, default=Path("results/model_download/qwen3_4b_instruct_2507/qwen_download.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v34_heldout_best_of_n_no_repair"))
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--seed", type=int, default=3407)
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v34 held-out best-of-N no-repair run")

    manifest_path = resolve(args.prompt_manifest)
    baseline_rows_path = resolve(args.baseline_rows)
    manifest = load_json(manifest_path)
    baseline_rows = load_json(baseline_rows_path)["rows"]
    target_ids = [row["instance_id"] for row in baseline_rows if row["decision"] != "commit_live"]
    manifest_rows = {row["instance_id"]: row for row in manifest["rows"]}
    target_rows = [manifest_rows[instance_id] for instance_id in target_ids]
    record = load_json(args.model_record)
    output_dir.mkdir(parents=True)

    tokenizer = AutoTokenizer.from_pretrained(record["snapshot_path"], trust_remote_code=True, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(record["snapshot_path"], torch_dtype=torch.bfloat16, trust_remote_code=True, local_files_only=True).to(torch.device(args.device)).eval()
    model.config.use_cache = True

    rows = []
    raw_rows = []
    counts: Counter[str] = Counter()
    sample_counts: Counter[str] = Counter()
    prompt_tokens = 0
    output_tokens = 0
    parse_ok_samples = 0
    for row_index, row in enumerate(target_rows):
        samples = []
        sample_decisions = []
        for sample_index in range(args.samples):
            seed = args.seed + row_index * 1000 + sample_index
            text, ptok, otok, prompt_mode = sample_generate(model, tokenizer, row, args.max_new_tokens, seed, args.temperature, args.top_p)
            prompt_tokens += ptok
            output_tokens += otok
            decision, parse_ok, sketch = evaluate_output(text, row)
            parse_ok_samples += int(parse_ok)
            sample_counts[decision] += 1
            sample_decisions.append(decision)
            samples.append({"sample_index": sample_index, "seed": seed, "output": text, "parse_ok": parse_ok, "decision": decision, "sketch": sketch, "prompt_mode": prompt_mode})
        decision = aggregate_decision(sample_decisions)
        counts[decision] += 1
        rows.append({"instance_id": row["instance_id"], "task_id": row["task_id"], "decision": decision, "sample_decisions": sample_decisions})
        raw_rows.append({"instance_id": row["instance_id"], "task_id": row["task_id"], "samples": samples})

    raw_path = output_dir / "raw_model_outputs.json"
    rows_path = output_dir / "rows.json"
    write_json(raw_path, {"schema": "ebw_track_a_v34_best_of_n_raw_outputs_v1", "rows": raw_rows})
    write_json(rows_path, {"schema": "ebw_track_a_v34_best_of_n_rows_v1", "rows": rows})
    payload = {
        "schema": "ebw_track_a_v34_heldout_best_of_n_no_repair_v1",
        "status": "RPD_EBW_TRACK_A_V34_HELDOUT_BEST_OF_N_NO_REPAIR_COMPLETE",
        "target_rows": len(target_rows),
        "samples_per_row": args.samples,
        "decision_counts": dict(sorted(counts.items())),
        "sample_decision_counts": dict(sorted(sample_counts.items())),
        "sample_parse_rate": parse_ok_samples / max(1, len(target_rows) * args.samples),
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "model_id": record["model_id"],
        "prompt_manifest_sha256": file_hash(manifest_path),
        "baseline_rows_sha256": file_hash(baseline_rows_path),
        "raw_outputs_sha256": file_hash(raw_path),
        "rows_sha256": file_hash(rows_path),
        "derived_path_adversary_policy": DERIVED_PATH_ADVERSARY_POLICY,
        "sealed_variations_opened": bool(manifest.get("sealed_variations_opened", False)),
        "repairagent_used": False,
        "model_gpu_docker_used": True,
        "external_process_actions": False,
    }
    write_json(output_dir / "results.json", payload)
    report = [
        "# EBW Track A v34 Held-Out Best-of-N No-Repair Control",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Target rows: {len(target_rows)}",
        f"- Samples per row: {args.samples}",
        f"- Decision counts: {payload['decision_counts']}",
        f"- Sample decision counts: {payload['sample_decision_counts']}",
        f"- Sample parse rate: {payload['sample_parse_rate']:.3f}",
        "- RepairAgent used: No",
        "- Sealed variations 10-12 opened: Yes",
    ]
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "target_rows": len(target_rows), "decision_counts": payload["decision_counts"], "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()