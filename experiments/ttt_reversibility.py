"""D.6 TTT vs rotation register diagnostic entry."""

from __future__ import annotations

import json
import os

from register.ttt_diagnostic import run_diagnostic


def run(output_dir: str = "results/ttt") -> dict:
    os.makedirs(output_dir, exist_ok=True)
    result = run_diagnostic(dim=64, hidden_dim=128, pushes=3)
    with open(os.path.join(output_dir, "results.json"), "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    return result


if __name__ == "__main__":
    print(run())
