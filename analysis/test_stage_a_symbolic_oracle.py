"""CI-style checks for Track A stateless symbolic oracle discipline."""

from __future__ import annotations

import json

from experiments.stage_a_symbolic_oracle import statelessness_ci


def run() -> dict:
    result = statelessness_ci("results/stage_a_symbolic_test")
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    payload = run()
    if payload.get("status") != "PASS":
        raise SystemExit(1)
