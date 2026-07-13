"""Deterministic truth-decoupled rollback-signal noise for SPEC v7-RPD."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping


@dataclass(frozen=True)
class DetectorObservation:
    true_dead: bool
    observed_dead: bool
    false_positive: bool
    false_negative: bool
    uniform: float
    query_index: int


def canonical_assignment(assignment: Mapping[int, int]) -> str:
    return json.dumps([[int(key), int(value)] for key, value in sorted(assignment.items())], separators=(",", ":"))


def _unit_interval(*parts: object) -> float:
    payload = "::".join(str(part) for part in parts).encode("utf-8")
    integer = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return integer / float(2**64)


class DeterministicNoisyDetector:
    """A replayable detector whose noise is independent of truth computation.

    The hash key couples observations across systems whenever they query the same
    instance, state, channel, and query index.
    """

    def __init__(self, eta_fp: float, eta_fn: float = 0.0, seed: int = 20260712):
        if not 0.0 <= float(eta_fp) <= 1.0 or not 0.0 <= float(eta_fn) <= 1.0:
            raise ValueError("eta_fp and eta_fn must lie in [0, 1]")
        self.eta_fp = float(eta_fp)
        self.eta_fn = float(eta_fn)
        self.seed = int(seed)

    def observe(
        self,
        *,
        instance_id: str,
        assignment: Mapping[int, int],
        true_dead: bool,
        query_index: int = 0,
        channel: str = "dead_end",
    ) -> DetectorObservation:
        state_key = canonical_assignment(assignment)
        uniform = _unit_interval("spec_v7_signal", self.seed, instance_id, state_key, channel, int(query_index))
        if bool(true_dead):
            observed = uniform >= self.eta_fn
        else:
            observed = uniform < self.eta_fp
        return DetectorObservation(
            true_dead=bool(true_dead),
            observed_dead=bool(observed),
            false_positive=bool(observed and not true_dead),
            false_negative=bool(true_dead and not observed),
            uniform=float(uniform),
            query_index=int(query_index),
        )


class DeterministicNoisyTarget:
    """Secondary target-noise channel, frozen independently from dead-end noise."""

    def __init__(self, eta_tgt: float, seed: int = 20260712):
        if not 0.0 <= float(eta_tgt) <= 1.0:
            raise ValueError("eta_tgt must lie in [0, 1]")
        self.eta_tgt = float(eta_tgt)
        self.seed = int(seed)

    def choose(
        self,
        *,
        instance_id: str,
        assignment: Mapping[int, int],
        true_target: int,
        alternatives: list[int],
        query_index: int = 0,
    ) -> int:
        valid_alternatives = sorted({int(item) for item in alternatives if int(item) != int(true_target)})
        if not valid_alternatives:
            return int(true_target)
        state_key = canonical_assignment(assignment)
        corrupt = _unit_interval("spec_v7_target_corrupt", self.seed, instance_id, state_key, int(query_index)) < self.eta_tgt
        if not corrupt:
            return int(true_target)
        selector = _unit_interval("spec_v7_target_select", self.seed, instance_id, state_key, int(query_index))
        return valid_alternatives[min(int(selector * len(valid_alternatives)), len(valid_alternatives) - 1)]
