"""Qwen3-4B-Thinking token-CoT baseline.

The <think> trace is the append-only external stack. This is the comparison
against the bounded latent structured register.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import torch

from .compute_accounting import ComputeAccounter


@dataclass
class CoTResult:
    text: str
    think_trace: str
    answer: str
    total_tokens: int
    flops: float
    solved: bool = False


class QwenThinkingCoTBaseline:
    def __init__(self, model_id: str = "Qwen/Qwen3-4B-Thinking-2507", device: str = "cuda", dtype: torch.dtype = torch.bfloat16, load_model: bool = True):
        self.model_id = model_id
        self.model = None
        self.tokenizer = None
        self.accounter = ComputeAccounter()
        if load_model:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(model_id)
            self.model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=dtype, device_map=device)
            self.accounter = ComputeAccounter(self.model.config.hidden_size, self.model.config.num_hidden_layers, self.model.config.vocab_size)

    def solve(self, prompt: str, flops_budget: Optional[float] = None, max_new_tokens: int = 4096) -> CoTResult:
        if flops_budget is not None:
            max_new_tokens = self.accounter.flops_to_tokens(flops_budget)
        if self.model is None or self.tokenizer is None:
            return CoTResult("", "", "", 0, 0.0)
        messages = [{"role": "user", "content": prompt}]
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(text, return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            generated = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        new_tokens = generated[0][inputs["input_ids"].shape[1]:]
        out = self.tokenizer.decode(new_tokens, skip_special_tokens=False)
        think, answer = self._split_think(out)
        return CoTResult(out, think, answer, len(new_tokens), self.accounter.tokens_to_flops(len(new_tokens)))

    @staticmethod
    def _split_think(text: str) -> tuple[str, str]:
        start = text.find("<think>")
        end = text.find("</think>")
        if start >= 0 and end > start:
            return text[start + 7:end].strip(), text[end + 8:].strip()
        return "", text.strip()
