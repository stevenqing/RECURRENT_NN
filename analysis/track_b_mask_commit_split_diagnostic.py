"""Track B mask-only versus full-commit diagnostic for seed102 checkpoint."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import torch

from experiments.train_recurrent_operator import _generate_band, forced_only_commit_decision
from experiments.train_trm_operator import (
    PerCellTokenRecurrentOperator,
    TrackBConfig,
    _load_torch_payload,
    _tensorize_token_examples_parallel,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"event": "write_json", "path": str(path), "status": payload.get("status")}), flush=True)
    return payload


def _load_model(checkpoint: Path, device: str) -> torch.nn.Module:
    payload = _load_torch_payload(checkpoint)
    config = payload.get("config", {})
    model = PerCellTokenRecurrentOperator(TrackBConfig(
        hidden_dim=int(config.get("hidden_dim", 384)),
        nhead=int(config.get("nhead", 6)),
        feedforward_dim=int(config.get("feedforward_dim", 8192)),
        recurrence_steps=int(config.get("recurrence_steps", 12)),
        dropout=float(config.get("dropout", 0.0)),
        value_head_mode=str(config.get("value_head_mode", "global")),
    )).to(device)
    state = payload.get("state_dict")
    if state is None:
        raise ValueError(f"checkpoint has no state_dict: {checkpoint}")
    model.load_state_dict(state)
    model.eval()
    return model


def _top_values(tensor: torch.Tensor, k: int = 6) -> list[dict[str, float | int]]:
    k = min(k, int(tensor.numel()))
    values, indices = torch.topk(tensor.detach().float().cpu(), k=k)
    return [{"index": int(index.item()), "logit": float(value.item())} for value, index in zip(values, indices)]


@torch.no_grad()
def _metrics(model: torch.nn.Module, rows: list[Any], device: str, batch_size: int, example_limit: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    totals = Counter()
    reason_hist = Counter()
    examples: list[dict[str, Any]] = []
    model.eval()
    for start in range(0, len(rows), batch_size):
        chunk = rows[start:start + batch_size]
        x = torch.stack([row.x for row in chunk]).to(device)
        outputs = model(x)
        forced_logits = outputs["forced_mask"][-1].detach().float().cpu()
        forced_probs = torch.sigmoid(forced_logits)
        val_logits = outputs["val"][-1].detach().float().cpu()
        forced_top = torch.topk(forced_probs, k=2, dim=-1)
        for index, row in enumerate(chunk):
            target = {int(cell): int(value) for cell, value in row.forced_values.items()}
            target_cells = set(target)
            mask_cells = {int(cell) for cell in torch.nonzero(forced_probs[index] >= 0.5, as_tuple=False).flatten().tolist()}
            mask_hits = mask_cells & target_cells
            totals["mask_proposed_cells"] += len(mask_cells)
            totals["mask_true_cells"] += len(target_cells)
            totals["mask_hits"] += len(mask_hits)

            candidate_var = int(forced_top.indices[index, 0].item())
            selected_val_logits = val_logits[index, candidate_var] if val_logits.dim() == 3 else val_logits[index]
            val_top = torch.topk(selected_val_logits, k=2)
            candidate_val = int(val_top.indices[0].item()) + 1
            forced_score = float(forced_top.values[index, 0].item())
            forced_margin = float((forced_top.values[index, 0] - forced_top.values[index, 1]).item())
            val_margin = float((val_top.values[0] - val_top.values[1]).item())
            full_proposed = forced_score >= 0.5 and forced_margin > 0.0 and val_margin > 0.0
            full_hit = full_proposed and target.get(candidate_var) == candidate_val
            totals["full_true_states"] += int(bool(target))
            totals["full_proposed_commits"] += int(full_proposed)
            totals["full_hits"] += int(full_hit)
            totals["full_covered"] += int(bool(target) and full_hit)

            single_outputs = {name: [step[index:index + 1] for step in steps] for name, steps in outputs.items()}
            decision = forced_only_commit_decision(single_outputs, 0.0, allowed_forced=target)
            reason_hist[decision.reason] += 1
            if len(examples) < example_limit and target:
                examples.append({
                    "row_index": start + index,
                    "target_forced": target,
                    "mask_logits_top": _top_values(forced_logits[index], k=8),
                    "mask_probs_ge_0_5_cells": sorted(mask_cells),
                    "value_logits_top": [{"value": int(item["index"]) + 1, "logit": item["logit"]} for item in _top_values(selected_val_logits, k=6)],
                    "commit_rule": {
                        "commit": decision.commit,
                        "var": decision.var,
                        "val": decision.val,
                        "reason": decision.reason,
                        "forced_score": decision.forced_score,
                        "forced_margin": decision.forced_margin,
                        "val_margin": decision.val_margin,
                    },
                    "drop_location": "mask_missed_true_cell" if not mask_hits else ("value_or_commit_conjunction" if not decision.commit else "commit_passed"),
                })
    metrics = {
        "n_examples": len(rows),
        "mask_only_precision": totals["mask_hits"] / max(totals["mask_proposed_cells"], 1),
        "mask_only_recall": totals["mask_hits"] / max(totals["mask_true_cells"], 1),
        "mask_proposed_cells": totals["mask_proposed_cells"],
        "mask_true_cells": totals["mask_true_cells"],
        "full_commit_precision": totals["full_hits"] / max(totals["full_proposed_commits"], 1),
        "full_commit_recall": totals["full_covered"] / max(totals["full_true_states"], 1),
        "full_proposed_commits": totals["full_proposed_commits"],
        "full_true_forced_states": totals["full_true_states"],
        "stick_reason_histogram": dict(sorted(reason_hist.items())),
    }
    return metrics, examples


CORRECTED_VALUE_HEAD_LABEL = "VALUE_HEAD_COMMIT_CONJUNCTION_BUG_DIAGNOSED_ONE_RETRAIN_ALLOWED_NO_DAGGER_RL"


def _decision(train: dict[str, Any], eval_: dict[str, Any], threshold: float) -> dict[str, Any]:
    mask_identification_high = (
        train["mask_only_precision"] >= 0.8
        and train["mask_only_recall"] >= 0.8
        and eval_["mask_only_precision"] >= 0.8
        and eval_["mask_only_recall"] >= 0.8
    )
    full_low = train["full_commit_precision"] < threshold or train["full_commit_recall"] < threshold
    if mask_identification_high and full_low:
        outcome = CORRECTED_VALUE_HEAD_LABEL
        next_step = "Run exactly one supervised value-head/commit-conjunction retrain; no DAgger and no RL."
    elif not mask_identification_high:
        outcome = "MASK_HEAD_LOW_CLOSE_AS_OPERATOR_LEARNABILITY_FINDING_NO_DAGGER_RL"
        next_step = "Close Track B as an off-critical-path operator learnability finding."
    else:
        outcome = "MASK_AND_FULL_COMMIT_BOTH_HIGH_UNEXPECTED_RECHECK_ROLLOUT"
        next_step = "Recheck rollout wiring because single-step diagnostic no longer explains low G1."
    return {
        "outcome": outcome,
        "threshold": threshold,
        "no_dagger_rl": True,
        "next_step": next_step,
        "train_mask_high": mask_identification_high,
        "train_full_low": full_low,
        "eval_mask_only_precision": eval_["mask_only_precision"],
        "eval_mask_only_recall": eval_["mask_only_recall"],
        "localization": "value_head_or_commit_conjunction" if mask_identification_high and full_low else "mask_or_rollout_recheck",
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.out_dir)
    device = args.device if torch.cuda.is_available() or not args.device.startswith("cuda") else "cpu"
    model = _load_model(Path(args.checkpoint), device)
    train_instances, train_examples = _generate_band(1, 2, args.train_instances, args.seed, args.generation_workers)
    eval_instances, eval_examples = _generate_band(1, 2, args.eval_instances, args.seed + 1000, args.generation_workers)
    train_rows = _tensorize_token_examples_parallel("mask_commit_train", train_examples, augment_digits=True, seed=args.seed + 10, workers=args.tensorize_workers)
    eval_rows = _tensorize_token_examples_parallel("mask_commit_eval", eval_examples, augment_digits=False, seed=args.seed + 20, workers=args.tensorize_workers)
    train_metrics, examples = _metrics(model, train_rows, device, args.batch_size, args.trace_examples)
    eval_metrics, _ = _metrics(model, eval_rows, device, args.batch_size, 0)
    decision = _decision(train_metrics, eval_metrics, args.high_threshold)
    payload = {
        "module": "track_b_mask_commit_split_diagnostic",
        "generated_at": _now(),
        "status": decision["outcome"],
        "checkpoint": args.checkpoint,
        "device": device,
        "dataset": {
            "seed": args.seed,
            "train_instances": len(train_instances),
            "train_examples": len(train_rows),
            "eval_instances": len(eval_instances),
            "eval_examples": len(eval_rows),
        },
        "result_tables": {
            "mask_only_vs_full_commit_pr": {
                "columns": ["split", "n_examples", "mask_only_precision", "mask_only_recall", "mask_proposed_cells", "mask_true_cells", "full_commit_precision", "full_commit_recall", "full_proposed_commits", "full_true_forced_states"],
                "rows": [
                    {"split": "train", **train_metrics},
                    {"split": "eval", **eval_metrics},
                ],
            },
            "training_trace_examples": {
                "columns": ["row_index", "target_forced", "mask_logits_top", "mask_probs_ge_0_5_cells", "value_logits_top", "commit_rule", "drop_location"],
                "rows": examples,
            },
        },
        "decision": decision,
        "fail_closed": False,
    }
    return _write(out / "track_b_mask_commit_split_diagnostic.json", payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Track B mask-only versus full-commit diagnostic.")
    parser.add_argument("--out-dir", default="results/closeout_047/track_b_mask_commit")
    parser.add_argument("--checkpoint", default="results/track_b_trm_retry_seed102_ddp8_sharded_20260608T114308Z/seed102_ddp8/trm_operator_seed102.pt")
    parser.add_argument("--seed", type=int, default=102)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--train-instances", type=int, default=4096)
    parser.add_argument("--eval-instances", type=int, default=512)
    parser.add_argument("--generation-workers", type=int, default=4)
    parser.add_argument("--tensorize-workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--trace-examples", type=int, default=10)
    parser.add_argument("--high-threshold", type=float, default=0.9)
    run(parser.parse_args())


if __name__ == "__main__":
    main()