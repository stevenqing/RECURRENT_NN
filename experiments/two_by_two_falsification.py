"""D.3 2x2 falsification. Run first."""

from __future__ import annotations

import json
import os

from analysis.scaffold_eval import summarize_method
from tasks.logic_grid.generator import generate_logic_grid
from tasks.sat.generators import generate_general_sat, generate_horn_sat
from tasks.sudoku.generator_4x4 import generate_4x4_by_depth


def run(output_dir: str = "results/two_by_two") -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    prop_tasks = generate_horn_sat(n_instances=5) + generate_4x4_by_depth(target_depth=0, n_instances=5)
    bt_tasks = generate_general_sat(n_instances=5, min_depth=1) + generate_4x4_by_depth(target_depth=1, n_instances=5) + generate_logic_grid(target_depth=5, n_instances=5)
    results = []
    for method in ["latent_only", "latent_plus_structured_register"]:
        for column, tasks in [("propagation_only", prop_tasks), ("backtracking_required", bt_tasks)]:
            row = summarize_method(method, tasks)
            row["column"] = column
            results.append(row)
    with open(os.path.join(output_dir, "results.json"), "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    return results


if __name__ == "__main__":
    print(run())
