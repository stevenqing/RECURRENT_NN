"""Convert symbolic oracle traces to supervised training examples."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .dpll_oracle import OracleTrace, TraceAction


@dataclass
class TrainingExample:
    givens: dict[str, Any]
    partial_assignment: dict[int, int]
    target_action: str
    target_var: Optional[int]
    target_val: Optional[int]
    is_dead_end: bool
    depth: int
    task_type: str
    dpll_backtrack_depth: int


def trace_to_examples(trace: OracleTrace, givens: dict[str, Any], task_type: str) -> list[TrainingExample]:
    partial: dict[int, int] = {}
    stack: list[dict[int, int]] = []
    examples: list[TrainingExample] = []
    for step in trace.steps:
        action = "done" if step.action == TraceAction.SOLVED else ("revert" if step.action in {TraceAction.BACKTRACK, TraceAction.CONTRADICTION} else step.action.value)
        examples.append(TrainingExample(dict(givens), dict(partial), action, step.variable, step.value, step.dead_end, step.depth, task_type, trace.max_backtrack_depth))
        if step.action in {TraceAction.PROPAGATE, TraceAction.BRANCH} and step.variable is not None and step.value is not None:
            if step.action == TraceAction.BRANCH:
                stack.append(dict(partial))
            partial[step.variable] = step.value
        elif step.action == TraceAction.BACKTRACK and stack:
            partial = stack.pop()
    return examples
