"""Matched-compute accounting for Stage D comparisons."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ComputeAccounter:
    hidden_size: int = 2560
    num_layers: int = 36
    vocab_size: int = 151936

    @property
    def estimated_params(self) -> int:
        return 12 * self.num_layers * self.hidden_size * self.hidden_size + self.vocab_size * self.hidden_size

    def tokens_to_flops(self, tokens: int) -> float:
        return 2.0 * self.estimated_params * tokens

    def flops_to_tokens(self, flops: float) -> int:
        return max(1, int(flops / (2.0 * self.estimated_params)))

    def structured_loop_flops(self, operator_calls: int, prompt_tokens: int, register_dim: int) -> float:
        operator = operator_calls * self.tokens_to_flops(prompt_tokens)
        register = operator_calls * register_dim * 10.0
        return operator + register
