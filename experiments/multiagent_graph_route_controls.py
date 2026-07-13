"""Matched-candidate graph-color route controls built on the frozen shadow engine."""

from __future__ import annotations

from unittest.mock import patch
from typing import Any

import experiments.multiagent_factorization_controls as frozen_controls


ARM = "independent_local_deepest_window_valid_graph"
MODE = "queued_deepest_window_valid"


class _LastIndexRNG:
    @staticmethod
    def randrange(stop: int) -> int:
        if int(stop) <= 0:
            raise ValueError("randrange stop must be positive")
        return int(stop) - 1


def run_deepest_window_valid_graph(
    row: dict[str, Any],
    *,
    r_value: int = 8,
    activation_cap: int = 20000,
    channel_cap: int = 16,
    route_seed: int = 20260711,
) -> dict[str, Any]:
    """Choose deepest over the exact frozen random-valid candidate filter."""

    def stable_last_rng(_instance_id: str, _mode: str, _route_seed: int) -> _LastIndexRNG:
        return _LastIndexRNG()

    with patch.object(frozen_controls, "_stable_rng", stable_last_rng):
        result = frozen_controls.run_factorized_control(
            row,
            "queued_random_valid",
            int(r_value),
            int(activation_cap),
            int(channel_cap),
            int(route_seed),
        )
    output = dict(result)
    output.update({
        "arm": ARM,
        "control_mode": MODE,
        "route_mode": "deepest_over_window_valid_candidates",
        "evaluation_mode": "graph_matched_route_control_v1",
        "candidate_filter": "target_owner_window_valid",
        "candidate_ranking": "maximum_fixed_order_position",
        "shadow_engine": "frozen_graph_queued_random_valid",
        "sequential_patch_required": True,
        "headline_eligible": False,
    })
    return output
