"""Exact paired tests and family-wise corrections for capacity experiments."""

from __future__ import annotations

import math


def mcnemar_exact(correct_a, correct_b) -> float:
    """Return the two-sided exact McNemar p-value for paired correctness vectors."""
    left = [bool(value) for value in correct_a]
    right = [bool(value) for value in correct_b]
    if len(left) != len(right):
        raise ValueError("paired correctness vectors must have equal length")
    a_only = sum(a and not b for a, b in zip(left, right))
    b_only = sum(b and not a for a, b in zip(left, right))
    discordant = a_only + b_only
    if discordant == 0:
        return 1.0
    smaller = min(a_only, b_only)
    tail = sum(math.comb(discordant, index) for index in range(smaller + 1)) / float(2**discordant)
    return min(1.0, 2.0 * tail)


def holm_bonferroni(p_values: dict[str, float]) -> dict[str, float]:
    """Return Holm step-down family-wise corrected p-values."""
    ordered = sorted(((name, float(value)) for name, value in p_values.items()), key=lambda item: item[1])
    count = len(ordered)
    corrected: dict[str, float] = {}
    running = 0.0
    for rank, (name, value) in enumerate(ordered):
        adjusted = min(1.0, (count - rank) * value)
        running = max(running, adjusted)
        corrected[name] = running
    return corrected


holm_correct = holm_bonferroni
