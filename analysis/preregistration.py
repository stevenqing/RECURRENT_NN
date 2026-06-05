"""D.7 pre-registration utilities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import os


@dataclass
class PreregisteredBand:
    D: int
    K: int
    predicted_d_star: float
    label: str


def compute_d_star(D: int, K: int) -> float:
    if K <= 1:
        raise ValueError("K must be greater than 1")
    return D / (2.0 * math.log(K))


def generate_preregistration(output_dir: str = "results/preregistration") -> list[PreregisteredBand]:
    configs = [(256, 729, "small_D_large_K"), (512, 729, "medium_D_large_K"), (256, 60, "small_D_medium_K"), (512, 60, "medium_D_medium_K"), (1024, 729, "large_D_large_K"), (4096, 60, "offscreen_control")]
    bands = [PreregisteredBand(D, K, compute_d_star(D, K), label) for D, K, label in configs]
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "preregistration.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"formula": "D / (2 ln K)", "bands": [asdict(b) for b in bands]}, handle, indent=2)
    print(f"wrote {path}")
    return bands


if __name__ == "__main__":
    generate_preregistration()
