"""D-stage 3 structured register vs token-CoT, after pre-registration."""

from __future__ import annotations

import json
import os

from analysis.scaffold_eval import TRACE_SCAFFOLD_MODE, solve_curve
from analysis.preregistration import compute_d_star


def run(output_dir: str = "results/d_stage_3") -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    configs = [(256, 60), (4096, 60)]
    results = []
    for D, K in configs:
        d_star = compute_d_star(D, K)
        for method in ["latent_structured", "qwen_thinking_cot", "naive_pass_scaling"]:
            results.append({
                "D": D,
                "K": K,
                "method": method,
                "predicted_d_star": d_star,
                "matched_compute": True,
                "solve_curve": solve_curve(method, D, K),
                "evaluation_mode": TRACE_SCAFFOLD_MODE,
            })
    with open(os.path.join(output_dir, "results.json"), "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    return results


if __name__ == "__main__":
    print(run())
