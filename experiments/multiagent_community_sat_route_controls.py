"""Post-confirmation matched-candidate route controls for community SAT.

This module does not modify the hash-locked SAT solver.  The window-valid
control calls its exact ``queued_random_valid`` path while replacing only the
within-candidate RNG draw with a deterministic deepest/last-index choice.
Calls must remain sequential because the temporary module patch is process-wide.
"""

from __future__ import annotations

from unittest.mock import patch
from typing import Any

import experiments.multiagent_community_sat as frozen_sat


ARM = "independent_local_deepest_window_valid_sat"
MODE = "queued_deepest_window_valid"


class _LastIndexRNG:
    """Minimal RNG interface selecting the deepest item from a sorted list."""

    @staticmethod
    def randrange(stop: int) -> int:
        if int(stop) <= 0:
            raise ValueError("randrange stop must be positive")
        return int(stop) - 1


def run_deepest_window_valid_sat(
    instance: dict[str, Any],
    *,
    r_value: int = 8,
    activation_cap: int = 20000,
    channel_cap: int = 16,
    route_seed: int = 20260712,
) -> dict[str, Any]:
    """Run deepest ranking over the exact frozen window-valid candidate set."""

    def stable_last_rng(_instance_id: str, _mode: str, _route_seed: int) -> _LastIndexRNG:
        return _LastIndexRNG()

    with patch.object(frozen_sat, "_stable_rng", stable_last_rng):
        row = frozen_sat.run_factorized_sat(
            instance,
            "queued_random_valid",
            int(r_value),
            int(activation_cap),
            int(channel_cap),
            int(route_seed),
        )
    output = dict(row)
    output.update({
        "arm": ARM,
        "control_mode": MODE,
        "route_mode": "deepest_over_window_valid_candidates",
        "evaluation_mode": "community_sat_matched_route_control_v1",
        "candidate_filter": "target_owner_window_valid",
        "candidate_ranking": "maximum_fixed_order_position",
        "shadow_engine": "frozen_queued_random_valid",
        "sequential_patch_required": True,
        "headline_eligible": False,
    })
    return output
