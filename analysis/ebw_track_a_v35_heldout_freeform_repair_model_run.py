"""Run Qwen free-form RepairAgent patch generation for held-out residuals."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList

from analysis.ebw_track_a_v35_heldout_freeform_repair_eval import parse_freeform_patch

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


class ParseablePatchStoppingCriteria(StoppingCriteria):
    def __init__(self, tokenizer: Any, start_length: int, response_prefill: str) -> None:
        self.tokenizer = tokenizer
        self.start_length = start_length
        self.response_prefill = response_prefill

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs: Any) -> bool:
        generated = input_ids[0, self.start_length:]
        if generated.numel() == 0:
            return False
        text = (self.response_prefill + self.tokenizer.decode(generated, skip_special_tokens=True)).strip()
        return text.endswith("}") and parse_freeform_patch(text).ok


def render_prompt(tokenizer: Any, row: dict[str, Any]) -> tuple[str, str]:
    prompt = tokenizer.apply_chat_template(row["messages"], tokenize=False, add_generation_prompt=True)
    response_prefill = row.get("response_prefill", "")
    return prompt + response_prefill, response_prefill


@torch.no_grad()
def generate(model: Any, tokenizer: Any, row: dict[str, Any], max_new_tokens: int) -> tuple[str, int, int]:
    prompt, response_prefill = render_prompt(tokenizer, row)
    ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(model.device)
    stopping = StoppingCriteriaList([ParseablePatchStoppingCriteria(tokenizer, int(ids.shape[1]), response_prefill)]) if response_prefill else None
    out = model.generate(ids, do_sample=False, max_new_tokens=max_new_tokens, pad_token_id=tokenizer.pad_token_id, eos_token_id=tokenizer.eos_token_id, use_cache=True, stopping_criteria=stopping)
    gen = out[:, ids.shape[1]:]
    text = tokenizer.decode(gen[0], skip_special_tokens=True)
    if response_prefill:
        text = response_prefill + text
    return text.strip(), int(ids.shape[1]), int(gen.shape[1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v35_heldout_freeform_repair_prompt_manifest/prompt_manifest.json"))
    parser.add_argument("--model-record", type=Path, default=Path("results/model_download/qwen3_4b_instruct_2507/qwen_download.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v35_heldout_freeform_repair"))
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--max-new-tokens", type=int, default=320)
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v35 held-out free-form model run")
    output_dir.mkdir(parents=True)
    manifest_path = resolve(args.prompt_manifest)
    manifest = load_json(manifest_path)
    record = load_json(args.model_record)
    tokenizer = AutoTokenizer.from_pretrained(record["snapshot_path"], trust_remote_code=True, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(record["snapshot_path"], torch_dtype=torch.bfloat16, trust_remote_code=True, local_files_only=True).to(torch.device(args.device)).eval()
    model.config.use_cache = True
    rows = []
    counts: Counter[str] = Counter()
    prompt_tokens = output_tokens = 0
    for row in manifest["rows"]:
        text, ptok, otok = generate(model, tokenizer, row, args.max_new_tokens)
        prompt_tokens += ptok
        output_tokens += otok
        parsed = parse_freeform_patch(text)
        counts["parse_ok" if parsed.ok else "parse_error"] += 1
        rows.append({"residual_id": row["residual_id"], "residual_class": row["residual_class"], "output": text, "parse_ok": parsed.ok})
    raw_path = output_dir / "raw_model_outputs.json"
    write_json(raw_path, {"schema": "ebw_track_a_v35_freeform_repair_raw_outputs_v1", "rows": rows})
    payload = {
        "schema": "ebw_track_a_v35_freeform_repair_model_run_v1",
        "status": "RPD_EBW_TRACK_A_V35_HELDOUT_FREEFORM_REPAIR_MODEL_RUN_COMPLETE",
        "processed": len(rows),
        "parse_counts": dict(sorted(counts.items())),
        "parse_rate": counts.get("parse_ok", 0) / max(1, len(rows)),
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "model_id": record["model_id"],
        "prompt_manifest_sha256": file_hash(manifest_path),
        "raw_outputs_sha256": file_hash(raw_path),
        "prompt_protocol": manifest.get("prompt_protocol", "unknown"),
        "sealed_variations_opened": bool(manifest.get("sealed_variations_opened", False)),
    }
    write_json(output_dir / "results.json", payload)
    sealed_text = "Yes" if payload["sealed_variations_opened"] else "No"
    report = [
        "# EBW Track A v35 Held-Out Free-Form Repair Model Run",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Processed: {len(rows)}",
        f"- Parse counts: {payload['parse_counts']}",
        f"- Parse rate: {payload['parse_rate']:.3f}",
        f"- Sealed variations 10-12 opened: {sealed_text}",
    ]
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "processed": len(rows), "parse_counts": payload["parse_counts"], "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()