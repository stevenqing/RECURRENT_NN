"""Run Qwen one-shot thinking baseline on calibrated Reasoning Gym graph_color bins."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from statistics import mean
from typing import Any
from urllib.request import Request, urlopen

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_reasoning_gym_bounded_register import _ensure_reasoning_gym, _select_entries


SCHEMA_VERSION = "externalization_oneshot_thinking_v0"
STATUS_COMPLETE = "EXTERNALIZATION_ONESHOT_THINKING_COMPLETE"
STATUS_PREFLIGHT_FAIL = "EXTERNALIZATION_ONESHOT_THINKING_PREFLIGHT_FAIL"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _make_dataset(args: argparse.Namespace) -> Any:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    return reasoning_gym.create_dataset(
        "graph_color",
        size=args.scan_limit,
        seed=args.seed,
        num_colors=args.num_colors,
        min_num_vertices=args.num_vertices,
        max_num_vertices=args.num_vertices,
        edge_probability=args.edge_probability,
    )


def _extract_json_object(text: str) -> str | None:
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    candidates = fenced + re.findall(r"\{.*?\}", text, flags=re.DOTALL)
    valid: list[str] = []
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            valid.append(json.dumps(parsed, sort_keys=True))
    return valid[-1] if valid else None


def _chat(base_url: str, model: str, prompt: str, max_tokens: int, enable_thinking: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if enable_thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": True}
    request = Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=3600) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    choice = decoded.get("choices", [{}])[0]
    text = choice.get("message", {}).get("content", "")
    usage = decoded.get("usage") or {}
    return {"text": text, "finish_reason": choice.get("finish_reason"), "completion_tokens": int(usage.get("completion_tokens") or 0), "prompt_tokens": int(usage.get("prompt_tokens") or 0), "total_tokens": int(usage.get("total_tokens") or 0)}


def _prompt(entry: dict[str, Any]) -> str:
    return "\n".join(
        [
            entry["question"],
            "You may reason internally, but your final answer must include exactly one JSON object mapping every vertex string to an integer color.",
            "Do not omit vertices. The final JSON object is what will be checked by the official scorer.",
        ]
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.dataset = "graph_color"
    dataset = _make_dataset(args)
    selected, traces, preflight = _select_entries(dataset, args)
    if len(selected) < args.n_instances:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "status": STATUS_PREFLIGHT_FAIL,
            "generated_at": _now(),
            "preflight": preflight,
            "trace_rows": traces[: args.max_trace_rows],
            "source": SOURCE,
            "provenance": SCHEMA_VERSION,
        }
        _write_json(args.output, payload)
        return payload
    def run_one(item: dict[str, Any]) -> dict[str, Any]:
        entry = item["entry"]
        generation = _chat(args.openai_base_url, args.openai_model, _prompt(entry), args.one_shot_max_tokens, args.one_shot_thinking)
        extracted = _extract_json_object(generation["text"])
        raw_score = float(dataset.score_answer(generation["text"], entry))
        extracted_score = float(dataset.score_answer(extracted, entry)) if extracted is not None else 0.0
        return {
            "source_index": int(item["source_index"]),
            "mode": "one_shot_thinking" if args.one_shot_thinking else "one_shot_vanilla",
            "official_score": extracted_score,
            "raw_official_score": raw_score,
            "solved": extracted_score >= 1.0,
            "finish_reason": generation["finish_reason"],
            "truncated": generation["finish_reason"] == "length",
            "completion_tokens": generation["completion_tokens"],
            "prompt_tokens": generation["prompt_tokens"],
            "total_tokens": generation["total_tokens"],
            "parseable_json": extracted is not None,
            "answer": extracted,
            "raw_text_prefix": generation["text"][: args.max_text_prefix],
            "source": SOURCE,
            "provenance": "externalization_oneshot_thinking_row_v0",
        }

    rows = []
    with ThreadPoolExecutor(max_workers=max(1, args.batch_size)) as pool:
        futures = [pool.submit(run_one, item) for item in selected]
        for future in as_completed(futures):
            rows.append(future.result())
            if args.checkpoint_path:
                checkpoint = args.checkpoint_path if args.checkpoint_path.is_absolute() else REPO_ROOT / args.checkpoint_path
                checkpoint.parent.mkdir(parents=True, exist_ok=True)
                checkpoint.write_text(json.dumps(sorted(rows, key=lambda row: row["source_index"]), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = sorted(rows, key=lambda row: row["source_index"])
    truncated_count = sum(1 for row in rows if row["truncated"])
    solve_rate = mean(float(row["solved"]) for row in rows) if rows else 0.0
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "dataset_config": {"dataset": "graph_color", "seed": args.seed, "num_vertices": args.num_vertices, "num_colors": args.num_colors, "edge_probability": args.edge_probability, "official_scoring": "dataset.score_answer", "source": SOURCE, "provenance": "externalization_oneshot_dataset_config_v0"},
        "preflight": preflight,
        "rows": rows,
        "summary": {
            "n": len(rows),
            "solve_rate": solve_rate,
            "mean_official_score": mean(row["official_score"] for row in rows) if rows else 0.0,
            "parseable_json_rate": mean(float(row["parseable_json"]) for row in rows) if rows else 0.0,
            "truncated_count": truncated_count,
            "truncation_guard_pass": truncated_count == 0,
            "mean_completion_tokens": mean(row["completion_tokens"] for row in rows) if rows else 0.0,
            "max_completion_tokens": max([row["completion_tokens"] for row in rows], default=0),
            "finish_reason_counts": dict((reason, sum(1 for row in rows if row["finish_reason"] == reason)) for reason in sorted({row["finish_reason"] for row in rows})),
            "source": SOURCE,
            "provenance": "externalization_oneshot_thinking_summary_v0",
        },
        "claim1_verdict": {
            "k1_readable": truncated_count == 0,
            "thinking_solve_rate": solve_rate,
            "verdict": "scope_thinking_partially_can" if truncated_count == 0 and solve_rate > args.thinking_scope_threshold else ("claim1_positive_including_thinking" if truncated_count == 0 else "truncation_rerun_required"),
            "source": SOURCE,
            "provenance": "externalization_k1_thinking_verdict_v0",
        },
        "honesty": {"does_not_establish": "This artifact only reads the L1 one-shot thinking baseline for K1 on graph_color ceiling bin; it does not run M-register or sudoku.", "truncation_guard": "K1 is readable only when truncated_count is zero or approximately zero.", "source": SOURCE, "provenance": "externalization_oneshot_thinking_honesty_v0"},
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one-shot thinking baseline on calibrated graph_color ceiling bin.")
    parser.add_argument("--output", type=Path, default=Path("results/externalization_validation_v0/graph_color_ceiling_oneshot_thinking.json"))
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scan-limit", type=int, default=500)
    parser.add_argument("--n-instances", type=int, default=30)
    parser.add_argument("--min-backtracks", type=int, default=4)
    parser.add_argument("--node-cap", type=int, default=2000)
    parser.add_argument("--num-vertices", type=int, default=14)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--edge-probability", type=float, default=0.4)
    parser.add_argument("--order-mode", choices=["degree_desc", "natural"], default="degree_desc")
    parser.add_argument("--one-shot-thinking", action="store_true")
    parser.add_argument("--one-shot-max-tokens", type=int, default=8192)
    parser.add_argument("--thinking-scope-threshold", type=float, default=0.3)
    parser.add_argument("--openai-base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--openai-model", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--max-trace-rows", type=int, default=200)
    parser.add_argument("--max-text-prefix", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--checkpoint-path", type=Path, default=Path("results/externalization_validation_v0/graph_color_ceiling_oneshot_thinking_checkpoint.json"))
    run(parser.parse_args())


if __name__ == "__main__":
    main()