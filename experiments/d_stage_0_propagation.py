"""D-stage 0 propagation extrapolation gate."""

from __future__ import annotations

import json
import os

from analysis.scaffold_eval import TRACE_SCAFFOLD_MODE, evaluate_task
from tasks.sat.generators import generate_horn_sat


def run(output_dir: str = "results/d_stage_0") -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    tasks = generate_horn_sat(n_instances=10)
    results = []
    for task in tasks:
        outcome = evaluate_task("latent_only", task)
        results.append({
            "depth": task.dpll_backtrack_depth,
            "task_kind": task.kind,
            "solve_rate": 1.0 if outcome.solved else 0.0,
            "evaluation_mode": TRACE_SCAFFOLD_MODE,
        })
    with open(os.path.join(output_dir, "results.json"), "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    return results


if __name__ == "__main__":
    print(run())
