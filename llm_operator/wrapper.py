"""Frozen Qwen3-4B-Instruct operator wrapper.

One operator step is one forward pass over a bounded current-node prompt.
The stack is not in the prompt; the structured register owns it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

import torch

from .prompt_renderer import PromptRenderer


@dataclass
class OperatorStep:
    prompt: str
    hidden_state: torch.Tensor
    logits: Optional[torch.Tensor] = None


class FrozenQwenOperator(torch.nn.Module):
    def __init__(self, model_id: str = "Qwen/Qwen3-4B-Instruct-2507", device: str = "cuda", dtype: torch.dtype = torch.bfloat16, load_model: bool = True):
        super().__init__()
        self.model_id = model_id
        self.device_name = device
        self.renderer = PromptRenderer()
        self.model = None
        self.tokenizer = None
        self.hidden_size = 2560
        if load_model:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(model_id)
            self.model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=dtype, device_map=device)
            for parameter in self.model.parameters():
                parameter.requires_grad = False
            self.hidden_size = int(self.model.config.hidden_size)

    @torch.no_grad()
    def forward_step(self, task_type: str, givens: Mapping[str, Any], partial: Mapping[str, Any]) -> OperatorStep:
        prompt = self.renderer.render(task_type, givens, partial)
        if self.model is None or self.tokenizer is None:
            hidden = torch.zeros(1, self.hidden_size)
            return OperatorStep(prompt=prompt, hidden_state=hidden)
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True).to(self.model.device)
        outputs = self.model(**inputs, output_hidden_states=True, return_dict=True)
        return OperatorStep(prompt=prompt, hidden_state=outputs.hidden_states[-1][:, -1, :], logits=outputs.logits[:, -1, :])
