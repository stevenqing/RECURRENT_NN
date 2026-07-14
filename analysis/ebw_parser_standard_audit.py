"""Audit EBW strict parsing against prior baseline JSON extraction standards."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from experiments.ebw_obligation_sketch import parse_track_a_sketch

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


def raw_decode_objects(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    objects = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            objects.append(obj)
    return objects


def fenced_objects(text: str) -> list[dict[str, Any]]:
    objects = []
    for candidate in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL):
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            objects.append(obj)
    return objects


def validate(obj: Any) -> bool:
    if obj is None:
        return False
    return parse_track_a_sketch(obj).ok


def analyze_rows(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    rows = payload["rows"]
    counts: Counter[str] = Counter()
    disagreements = 0
    for row in rows:
        text = row["output"]
        raw_objects = raw_decode_objects(text)
        fenced = fenced_objects(text)
        methods = {
            "strict_full_text": parse_track_a_sketch(text).ok,
            "first_fenced_json": validate(fenced[0] if fenced else None),
            "last_fenced_json": validate(fenced[-1] if fenced else None),
            "first_raw_json": validate(raw_objects[0] if raw_objects else None),
            "last_raw_json": validate(raw_objects[-1] if raw_objects else None),
        }
        for name, ok in methods.items():
            counts[f"{name}_ok"] += int(ok)
        if len({name for name, ok in methods.items() if ok}) > 1 or methods["first_raw_json"] != methods["last_raw_json"]:
            disagreements += 1
    return {"rows": len(rows), "counts": dict(sorted(counts.items())), "disagreement_rows": disagreements, "raw_sha256": file_hash(path)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1-raw", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_smoke_v1/raw_model_outputs.json"))
    parser.add_argument("--v2-raw", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_smoke_v2/raw_model_outputs.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/parser_standard_audit_v1"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite parser standard audit")
    output_dir.mkdir(parents=True)
    v1 = analyze_rows(resolve(args.v1_raw))
    v2 = analyze_rows(resolve(args.v2_raw))
    result = {
        "schema": "ebw_parser_standard_audit_v1",
        "status": "RPD_EBW_PARSER_STANDARD_AUDIT_COMPLETE",
        "standards": {
            "ebw_primary": "strict full-text JSON object, no extraction, no regex repair",
            "kvcache_lfs_style": "scan every { and take the last raw-decodable JSON object",
            "reasoning_gym_style": "prefer fenced JSON objects, otherwise regex JSON candidates; score last valid object",
        },
        "v1_smoke": v1,
        "v2_smoke": v2,
        "interpretation": "Prior baselines used tolerant JSON extraction for answer scoring. EBW primary intentionally uses stricter parsing because extracting from prompt-echoed examples can select JSON that the model did not intend as its answer. A tolerant extractor may be reported as a diagnostic/baseline-compatible parser arm, but should not replace the primary Track A safety gate without a new freeze.",
    }
    write_json(output_dir / "results.json", result)
    report = [
        "# EBW Parser Standard Audit",
        "",
        "## Status: **`RPD_EBW_PARSER_STANDARD_AUDIT_COMPLETE`**",
        "",
        "## Prior Baseline Standards",
        "",
        "| Baseline family | Parser standard |",
        "|---|---|",
        "| EBW primary | strict full-text JSON object; no extraction or regex repair |",
        "| KV-cache LFS/ToT/RAP | scan raw text for JSON objects and take a parseable object, usually last |",
        "| ReasoningGym/externalization | accept fenced JSON and raw JSON candidates; often score last valid object |",
        "",
        "## Smoke Parse Counts",
        "",
        "| Smoke | Rows | Strict | First fenced | Last fenced | First raw | Last raw |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, data in [("v1", v1), ("v2", v2)]:
        counts = data["counts"]
        report.append(
            f"| {name} | {data['rows']} | {counts.get('strict_full_text_ok', 0)} | {counts.get('first_fenced_json_ok', 0)} | {counts.get('last_fenced_json_ok', 0)} | {counts.get('first_raw_json_ok', 0)} | {counts.get('last_raw_json_ok', 0)} |"
        )
    report += [
        "",
        "## Interpretation",
        "",
        "Previous baselines were more permissive than EBW Track A's primary parser. That matters for fair baselines, but EBW cannot simply switch to last-object extraction: the Qwen smoke outputs echo prompt examples and templates, so an extractor can parse JSON that comes from the prompt rather than the model's intended final answer.",
        "",
        "Recommendation: keep strict JSON as the primary safety gate, add a baseline-compatible tolerant-parser diagnostic arm, and fix generation with chat-template/stop-token protocol rather than regex repair.",
    ]
    (output_dir / "PARSER_STANDARD_AUDIT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": result["status"], "report": str((output_dir / "PARSER_STANDARD_AUDIT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()