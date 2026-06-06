"""Frozen generative Qwen operator for M2.0 probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re

import torch

from llm_operator.symbolic_filter import CSPTask


STATUS_VALUES = {"OPEN", "CONTRADICTION", "SOLVED"}


@dataclass(frozen=True)
class OperatorPrediction:
    forced: dict[int, int]
    guess: tuple[int, int] | None
    status: str | None
    raw_text: str
    parse_success: bool
    failure_modes: list[str]
    reprompted: bool = False


def render_current_node_prompt(task: CSPTask, assignment: dict[int, int], reprompt: bool = False) -> str:
    header = [
        "You are a frozen non-thinking CSP node operator.",
        "Use only the CURRENT NODE below. Do not use search history. Do not explain.",
        "Return exactly these three lines and nothing else:",
        "FORCED: <comma-separated var=val forced by rules in the current state, or NONE>",
        "GUESS: <one var=val to try if no forced move exists, or NONE>",
        "STATUS: OPEN | CONTRADICTION | SOLVED",
    ]
    if reprompt:
        header.append("Your previous answer was not parseable. Return only the three required lines.")
    body = [f"TASK: {task.task_type}", f"VARIABLES: {task.variables}", f"DOMAINS: {{var: sorted(values) for var, values in domains}}"]
    body.append(f"DOMAINS_EXPANDED: { {var: sorted(values) for var, values in task.domains.items()} }")
    body.append(f"GIVENS: {task.givens}")
    body.append(f"CURRENT_ASSIGNMENT: {dict(sorted(assignment.items()))}")
    if task.task_type in {"horn_sat", "general_sat"}:
        body.append(f"CLAUSES: {task.givens.get('clauses', [])}")
        body.append("SAT values use 1=true, 0=false. A positive literal v is satisfied by v=1; a negative literal -v by v=0.")
    elif task.task_type == "graph_coloring":
        body.append(f"EDGES: {task.givens.get('edges', [])}; adjacent nodes must have different colors.")
    elif task.task_type == "sudoku_4x4":
        grid = []
        for row in range(4):
            cells = []
            for col in range(4):
                var = row * 4 + col
                cells.append(str(assignment.get(var, task.givens.get(f"{row},{col}", "."))))
            grid.append(" ".join(cells))
        body.append("SUDOKU_CELL_IDS: var = row*4+col for rows/cols 0..3.")
        body.append("GRID:\n" + "\n".join(grid))
    return "\n".join(header + [""] + body)


def _parse_assignments(text: str) -> tuple[dict[int, int], list[str]]:
    text = text.strip()
    if text.upper() == "NONE":
        return {}, []
    out: dict[int, int] = {}
    failures: list[str] = []
    for part in text.split(","):
        item = part.strip()
        match = re.fullmatch(r"(?:V|v|var)?\s*(\d+)\s*=\s*(-?\d+)", item)
        if match is None:
            failures.append("malformed_var_val")
            continue
        out[int(match.group(1))] = int(match.group(2))
    return out, failures


def parse_operator_output(text: str) -> OperatorPrediction:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    fields: dict[str, str] = {}
    failures: list[str] = []
    for label in ["FORCED", "GUESS", "STATUS"]:
        matches = [line for line in lines if re.match(rf"^{label}\s*:", line, flags=re.IGNORECASE)]
        if not matches:
            failures.append(f"missing_{label.lower()}_line")
            continue
        fields[label] = re.sub(rf"^{label}\s*:\s*", "", matches[-1], flags=re.IGNORECASE).strip()
    extra = [line for line in lines if not re.match(r"^(FORCED|GUESS|STATUS)\s*:", line, flags=re.IGNORECASE)]
    if extra:
        failures.append("extra_prose")
    forced, forced_failures = _parse_assignments(fields.get("FORCED", "NONE"))
    failures.extend(forced_failures)
    guess_dict, guess_failures = _parse_assignments(fields.get("GUESS", "NONE"))
    failures.extend(guess_failures)
    if len(guess_dict) > 1:
        failures.append("multiple_guesses")
    guess = next(iter(guess_dict.items())) if guess_dict else None
    status = fields.get("STATUS", "").upper()
    if status not in STATUS_VALUES:
        failures.append("bad_status")
        status_value = None
    else:
        status_value = status
    return OperatorPrediction(forced, guess, status_value, text, not failures, failures)


class QwenGenerativeOperator:
    def __init__(self, model_id: str = "Qwen/Qwen3-4B-Instruct-2507", device: str = "cuda:0", dtype: str = "bfloat16", max_new_tokens: int = 64):
        from transformers import AutoModelForCausalLM, AutoTokenizer

        torch_dtype = torch.bfloat16 if dtype == "bfloat16" else torch.float16
        self.model_id = model_id
        self.max_new_tokens = max_new_tokens
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch_dtype).to(device)
        self.model.eval()
        for parameter in self.model.parameters():
            parameter.requires_grad = False

    def _format(self, prompt: str) -> str:
        if hasattr(self.tokenizer, "apply_chat_template"):
            messages = [{"role": "user", "content": prompt}]
            return self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        return prompt

    @torch.no_grad()
    def generate_texts(self, prompts: list[str], batch_size: int = 4) -> list[str]:
        outputs: list[str] = []
        for start in range(0, len(prompts), batch_size):
            batch_prompts = [self._format(prompt) for prompt in prompts[start:start + batch_size]]
            inputs = self.tokenizer(batch_prompts, return_tensors="pt", padding=True, truncation=True).to(self.model.device)
            generated = self.model.generate(
                **inputs,
                do_sample=False,
                temperature=None,
                top_p=None,
                max_new_tokens=self.max_new_tokens,
                pad_token_id=self.tokenizer.eos_token_id,
            )
            new_tokens = generated[:, inputs["input_ids"].shape[1]:]
            outputs.extend(self.tokenizer.batch_decode(new_tokens, skip_special_tokens=True))
        return outputs

    def predict(self, task: CSPTask, assignment: dict[int, int], batch_size: int = 4) -> OperatorPrediction:
        prompt = render_current_node_prompt(task, assignment, reprompt=False)
        first = self.generate_texts([prompt], batch_size=batch_size)[0]
        parsed = parse_operator_output(first)
        if parsed.parse_success:
            return parsed
        retry_prompt = render_current_node_prompt(task, assignment, reprompt=True)
        retry = self.generate_texts([retry_prompt], batch_size=batch_size)[0]
        reparsed = parse_operator_output(retry)
        return OperatorPrediction(reparsed.forced, reparsed.guess, reparsed.status, retry, reparsed.parse_success, reparsed.failure_modes, reprompted=True)