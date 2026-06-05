"""D.5 verifier verification / ablation entry."""

from __future__ import annotations

import json
import os

from analysis.scaffold_eval import verifier_summary
from tasks.logic_grid.generator import generate_logic_grid
from tasks.sat.generators import generate_general_sat
from tasks.sudoku.generator_4x4 import generate_4x4_by_depth


def run(output_dir: str = "results/verifier") -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    tasks = generate_general_sat(min_depth=1, n_instances=10) + generate_4x4_by_depth(target_depth=1, n_instances=5) + generate_logic_grid(target_depth=5, n_instances=5)
    results = [verifier_summary(mode, tasks) for mode in ["oracle", "learned", "noisy", "disabled"]]
    with open(os.path.join(output_dir, "results.json"), "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    return results


if __name__ == "__main__":
    print(run())
