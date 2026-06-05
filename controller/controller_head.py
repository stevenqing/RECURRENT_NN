"""Controller head and in-loop search skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

import torch


class Action(IntEnum):
    PROPAGATE = 0
    BRANCH = 1
    REVERT = 2
    DONE = 3


@dataclass
class ControllerDecision:
    action: Action
    action_logits: torch.Tensor
    var_logits: torch.Tensor
    val_logits: torch.Tensor
    confidence: torch.Tensor


class ControllerHead(torch.nn.Module):
    def __init__(self, hidden_dim: int = 2560, max_vars: int = 81, max_vals: int = 9):
        super().__init__()
        fused = hidden_dim * 2
        self.action = torch.nn.Sequential(torch.nn.Linear(fused, hidden_dim), torch.nn.ReLU(), torch.nn.Linear(hidden_dim, 4))
        self.var = torch.nn.Linear(fused, max_vars)
        self.val = torch.nn.Linear(fused, max_vals)
        self.conf = torch.nn.Sequential(torch.nn.Linear(fused, 1), torch.nn.Sigmoid())

    def forward(self, operator_hidden: torch.Tensor, register_readout: torch.Tensor, verifier_signal: torch.Tensor | None = None) -> ControllerDecision:
        x = torch.cat([operator_hidden, register_readout], dim=-1)
        action_logits = self.action(x)
        if verifier_signal is not None:
            action_logits[:, Action.REVERT] += 5.0 * verifier_signal.squeeze(-1)
        action = Action(int(action_logits.argmax(dim=-1)[0].item()))
        return ControllerDecision(action, action_logits, self.var(x), self.val(x), self.conf(x).squeeze(-1))


class SearchLoop:
    def __init__(self, operator, controller: ControllerHead, register, verifier, max_steps: int = 200):
        self.operator = operator
        self.controller = controller
        self.register = register
        self.verifier = verifier
        self.max_steps = max_steps

    def solve(self, task_type: str, givens: dict[str, Any]) -> dict[str, Any]:
        device = next(self.controller.parameters()).device
        h = self.register.init_state(1, device)
        partial: dict[Any, Any] = {}
        branch_stack: list[tuple[Any, Any, dict[Any, Any], torch.Tensor]] = []
        applied_reverts = 0
        for step in range(self.max_steps):
            op = self.operator.forward_step(task_type, givens, partial)
            hidden = op.hidden_state.to(device)
            dead_end = self.verifier(hidden)
            decision = self.controller(hidden, self.register.read(h), dead_end)
            if decision.action == Action.PROPAGATE:
                partial[int(decision.var_logits.argmax())] = int(decision.val_logits.argmax())
            elif decision.action == Action.BRANCH:
                var = int(decision.var_logits.argmax())
                val = int(decision.val_logits.argmax())
                branch_stack.append((var, val, dict(partial), hidden.detach()))
                h = self.register.push(h, hidden, len(branch_stack) - 1)
                partial[var] = val
            elif decision.action == Action.REVERT and branch_stack:
                _var, _val, saved_partial, saved_hidden = branch_stack.pop()
                h = self.register.pop(h, saved_hidden, len(branch_stack))
                partial = saved_partial
                applied_reverts += 1
            elif decision.action == Action.DONE:
                return {"solved": True, "partial": partial, "steps": step + 1, "applied_reverts": applied_reverts}
        return {"solved": False, "partial": partial, "steps": self.max_steps, "applied_reverts": applied_reverts}
