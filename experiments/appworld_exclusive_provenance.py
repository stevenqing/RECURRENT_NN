"""Exclusive causal provenance: commit only under one-sided support."""
from __future__ import annotations

from typing import Any


def exclusive_choice_from_tiers(tier_a: int, tier_b: int) -> str | None:
    """Choose only when exactly one candidate has nonzero causal provenance."""

    supported_a = int(tier_a) > 0
    supported_b = int(tier_b) > 0
    if supported_a == supported_b:
        return None
    return "A" if supported_a else "B"


def exclusive_choice(evidence_a: dict[str, Any], evidence_b: dict[str, Any]) -> str | None:
    return exclusive_choice_from_tiers(evidence_a["max_tier"], evidence_b["max_tier"])
