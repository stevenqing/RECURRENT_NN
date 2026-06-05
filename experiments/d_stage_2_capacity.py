"""D-stage 2 capacity frontier sweep."""

from __future__ import annotations

import json
import os

from analysis.scaffold_eval import TRACE_SCAFFOLD_MODE, gru_frontier, structured_frontier
from register.structured import predicted_d_star


def run(output_dir: str = "results/d_stage_2") -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    results = []
    for reg_type in ["structured", "gru"]:
        for D in [64, 128, 256, 512, 1024]:
            for K in [3, 9, 60, 729]:
                results.append({
                    "register_type": reg_type,
                    "D": D,
                    "K": K,
                    "predicted_d_star": predicted_d_star(D, K) if reg_type == "structured" else None,
                    "observed_frontier": structured_frontier(D, K) if reg_type == "structured" else gru_frontier(D, K),
                    "evaluation_mode": TRACE_SCAFFOLD_MODE,
                })
    with open(os.path.join(output_dir, "results.json"), "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    return results


if __name__ == "__main__":
    print(run())
