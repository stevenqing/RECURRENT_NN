"""D-stage 1 latent boundary plus depth-1 register gate."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

from analysis.scaffold_eval import summarize_method
from tasks.oracle.dpll_oracle import OracleTrace, TraceAction, TraceStep


def _depth1_revert_tasks(n_instances: int) -> list[SimpleNamespace]:
    tasks = []
    for index in range(n_instances):
        trace = OracleTrace(
            steps=[
                TraceStep(TraceAction.BRANCH, variable=1, value=0, depth=0),
                TraceStep(TraceAction.CONTRADICTION, depth=1, dead_end=True),
                TraceStep(TraceAction.BACKTRACK, variable=1, value=0, depth=0),
                TraceStep(TraceAction.BRANCH, variable=1, value=1, depth=0),
                TraceStep(TraceAction.SOLVED, depth=1),
            ],
            solved=True,
            solution={1: 1},
            max_backtrack_depth=1,
            total_backtracks=1,
        )
        tasks.append(SimpleNamespace(kind="depth1_revert_fixture", instance_id=index, dpll_backtrack_depth=1, oracle_trace=trace))
    return tasks


def run(output_dir: str = "results/d_stage_1") -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    tasks = _depth1_revert_tasks(n_instances=10)
    methods = ["latent_only", "structured_register", "gru_register", "no_revert_ablation"]
    results = [summarize_method(method, tasks) for method in methods]
    with open(os.path.join(output_dir, "results.json"), "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    return results


if __name__ == "__main__":
    print(run())
