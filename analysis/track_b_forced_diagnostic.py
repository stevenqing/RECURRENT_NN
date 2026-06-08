"""One-shot Track B train-vs-eval forced-mask diagnostic for seed102."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import torch

from experiments.train_recurrent_operator import _generate_band, _forced_values_for_example
from experiments.train_trm_operator import (
    PerCellTokenRecurrentOperator,
    TrackBConfig,
    _calibrate_tau,
    _episode_task_rows_parallel,
    _forced_single_step_metrics_token,
    _load_torch_payload,
    _tensorize_token_examples_parallel,
)
from llm_operator.symbolic_filter import propagation_fixpoint


def _write(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
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
    )).to(device)
    state = payload.get("state_dict")
    if state is None:
        raise ValueError(f"checkpoint has no state_dict: {checkpoint}")
    model.load_state_dict(state)
    model.eval()
    return model


def _trace_examples(instances: list[Any], n: int) -> list[dict[str, Any]]:
    rows = []
    for index, instance in enumerate(instances[:n]):
        example = next(iter(instance.oracle_trace.steps), None)
        givens = {f"{row},{col}": value for (row, col), value in instance.givens.items()}
        # Use the first supervised state with a non-empty forced target when possible.
        from tasks.oracle.trace_generator import trace_to_examples
        examples = trace_to_examples(instance.oracle_trace, givens, "sudoku_6x6")
        selected = next((row for row in examples if _forced_values_for_example(row)), examples[0] if examples else None)
        if selected is None:
            continue
        from experiments.train_recurrent_operator import _givens_to_assignment, _sudoku6_task
        task = _sudoku6_task(givens, f"diagnostic_{index}")
        assignment = _givens_to_assignment(selected)
        fixpoint, _, fixpoint_status = propagation_fixpoint(task, assignment)
        rows.append({
            "index": index,
            "dpll_backtrack_depth": instance.dpll_backtrack_depth,
            "selected_trace_action": getattr(example, "action", None).value if example else None,
            "target_construction": "_forced_values_for_example -> forced_mask over scalar forced_moves at the supervised partial_assignment",
            "eval_metric_definition": "forced_only_commit_decision proposes one forced cell/value per recurrent rollout state; hit requires allowed_forced[var] == value; episode G1 requires reaching propagation_fixpoint",
            "supervised_forced_values": _forced_values_for_example(selected),
            "fixpoint_delta_size": len(set(fixpoint) - set(assignment)),
            "fixpoint_status": fixpoint_status,
        })
    return rows


def run(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    device = args.device if torch.cuda.is_available() or not args.device.startswith("cuda") else "cpu"
    model = _load_model(Path(args.checkpoint), device)
    train_instances, train_examples = _generate_band(1, 2, args.train_instances, args.seed, args.generation_workers)
    eval_instances, eval_examples = _generate_band(1, 2, args.eval_instances, args.seed + 1000, args.generation_workers)
    train_rows = _tensorize_token_examples_parallel("diagnostic_train", train_examples, augment_digits=True, seed=args.seed + 10, workers=args.tensorize_workers)
    eval_rows = _tensorize_token_examples_parallel("diagnostic_eval", eval_examples, augment_digits=False, seed=args.seed + 20, workers=args.tensorize_workers)
    tau_calibration = _calibrate_tau(model, eval_rows, device)
    tau = tau_calibration["selected_tau"]
    train_metrics = _forced_single_step_metrics_token(model, train_rows, device, tau, batch_size=args.batch_size)
    eval_metrics = _forced_single_step_metrics_token(model, eval_rows, device, tau, batch_size=args.batch_size)
    train_high = train_metrics["forced_precision"] >= args.high_threshold and train_metrics["forced_recall"] >= args.high_threshold
    eval_high = eval_metrics["forced_precision"] >= args.high_threshold and eval_metrics["forced_recall"] >= args.high_threshold
    if train_high and not eval_high:
        decision = "CLOSE_AS_GENERALIZATION_GAP_NO_TRAINING_TONIGHT"
    elif not train_high and not eval_high:
        decision = "CLOSE_AS_TARGET_METRIC_OR_OPERATOR_LEARNABILITY_FINDING_NO_DAGGER_RL"
    else:
        decision = "TRIVIAL_BUG_NOT_DETECTED_BY_THIS_AUDIT"
    target_trace = _trace_examples(eval_instances, args.trace_examples)
    payload = {
        "module": "track_b_forced_diagnostic",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": decision,
        "checkpoint": args.checkpoint,
        "device": device,
        "dataset": {
            "seed": args.seed,
            "train_instances": len(train_instances),
            "train_examples": len(train_rows),
            "eval_instances": len(eval_instances),
            "eval_examples": len(eval_rows),
            "train_depth_histogram": dict(sorted(Counter(row.dpll_backtrack_depth for row in train_instances).items())),
            "eval_depth_histogram": dict(sorted(Counter(row.dpll_backtrack_depth for row in eval_instances).items())),
        },
        "tau_calibration": tau_calibration,
        "result_tables": {
            "train_vs_eval_forced_pr": {
                "columns": ["split", "n_examples", "forced_precision", "forced_recall", "proposed_commits", "true_forced_states", "provenance"],
                "rows": [
                    {"split": "train", **{key: train_metrics.get(key) for key in ["n_examples", "forced_precision", "forced_recall", "proposed_commits", "true_forced_states"]}, "provenance": "regenerated seed102 L1-L2 train distribution"},
                    {"split": "eval", **{key: eval_metrics.get(key) for key in ["n_examples", "forced_precision", "forced_recall", "proposed_commits", "true_forced_states"]}, "provenance": "regenerated seed1102 L1-L2 eval distribution"},
                ],
            },
            "target_metric_trace_examples": {"columns": ["index", "dpll_backtrack_depth", "target_construction", "eval_metric_definition", "supervised_forced_values", "fixpoint_delta_size", "fixpoint_status"], "rows": target_trace},
        },
        "decision": {
            "rule": "no further training unless a trivial target/metric bug is found",
            "outcome": decision,
            "no_dagger_rl_tonight": True,
        },
        "fail_closed": False,
    }
    return _write(out / "track_b_forced_diagnostic.json", payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Track B forced-mask train/eval diagnostic.")
    parser.add_argument("--out-dir", default="results/track_b_forced_diagnostic")
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
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()