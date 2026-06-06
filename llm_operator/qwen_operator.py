"""Frozen generative Qwen operator for M2.0 probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re

import torch

from llm_operator.symbolic_filter import CSPTask, valid_values


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
    reason: str | None = None


def _task_body(task: CSPTask, assignment: dict[int, int], sudoku_rendering: str = "grid") -> list[str]:
    body = [f"TASK: {task.task_type}", f"VARIABLES: {task.variables}"]
    body.append(f"DOMAINS: { {var: sorted(values) for var, values in task.domains.items()} }")
    body.append(f"GIVENS: {task.givens}")
    body.append(f"CURRENT_ASSIGNMENT: {dict(sorted(assignment.items()))}")
    if task.task_type in {"horn_sat", "general_sat"}:
        body.append(f"CLAUSES: {task.givens.get('clauses', [])}")
        body.append("SAT values use 1=true, 0=false. A positive literal v is satisfied by v=1; a negative literal -v by v=0.")
    elif task.task_type == "graph_coloring":
        body.append(f"EDGES: {task.givens.get('edges', [])}; adjacent nodes must have different colors.")
    elif task.task_type == "logic_grid":
        body.append(f"CATEGORIES: {task.givens.get('categories', [])}")
        body.append("VARIABLE MAP: vars 0-3 are person_0..person_3 colors; vars 4-7 are person_0..person_3 pets. Values are numbered 1..4.")
        body.append("CLUES:\n" + "\n".join(str(clue) for clue in task.givens.get("clues", [])))
    elif task.task_type == "sudoku_4x4":
        body.append("SUDOKU_CELL_IDS: var = row*4+col for rows/cols 0..3; values are 1..4.")
        if sudoku_rendering == "cells":
            cells = []
            for row in range(4):
                for col in range(4):
                    var = row * 4 + col
                    value = assignment.get(var, task.givens.get(f"{row},{col}", "."))
                    cells.append(f"r{row}c{col}(var{var})={value}")
            body.append("CELLS: " + "; ".join(cells))
        elif sudoku_rendering == "candidates":
            candidates = []
            for row in range(4):
                for col in range(4):
                    var = row * 4 + col
                    if var in assignment:
                        candidates.append(f"r{row}c{col}(var{var}) fixed={assignment[var]}")
                    elif f"{row},{col}" in task.givens:
                        candidates.append(f"r{row}c{col}(var{var}) given={task.givens[f'{row},{col}']}")
                    else:
                        candidates.append(f"r{row}c{col}(var{var}) candidates={sorted(valid_values(task, assignment, var))}")
            body.append("CELL_CANDIDATES: " + "; ".join(candidates))
        else:
            grid = []
            for row in range(4):
                cells = []
                for col in range(4):
                    var = row * 4 + col
                    cells.append(str(assignment.get(var, task.givens.get(f"{row},{col}", "."))))
                grid.append(" ".join(cells))
            body.append("GRID:\n" + "\n".join(grid))
    return body


def render_current_node_prompt(task: CSPTask, assignment: dict[int, int], reprompt: bool = False, mode: str = "list_all", sudoku_rendering: str = "grid") -> str:
    if mode == "single":
        header = [
            "You are a frozen non-thinking CSP node operator.",
            "Use only the CURRENT NODE below. Do not use search history. Do not explain beyond the requested one-line reason.",
            "Return exactly these three lines and nothing else:",
            "NEXT: <one var=val that is forced now, or NONE>",
            "REASON: <brief one-line reason, or NONE>",
            "STATUS: OPEN | CONTRADICTION | SOLVED",
        ]
        if reprompt:
            header.append("Your previous answer was not parseable. Return only NEXT, REASON, and STATUS lines.")
        return "\n".join(header + [""] + _task_body(task, assignment, sudoku_rendering))

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
    return "\n".join(header + [""] + _task_body(task, assignment, sudoku_rendering))


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


def parse_single_output(text: str) -> OperatorPrediction:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    fields: dict[str, str] = {}
    failures: list[str] = []
    for label in ["NEXT", "REASON", "STATUS"]:
        matches = [line for line in lines if re.match(rf"^{label}\s*:", line, flags=re.IGNORECASE)]
        if not matches:
            failures.append(f"missing_{label.lower()}_line")
            continue
        fields[label] = re.sub(rf"^{label}\s*:\s*", "", matches[-1], flags=re.IGNORECASE).strip()
    extra = [line for line in lines if not re.match(r"^(NEXT|REASON|STATUS)\s*:", line, flags=re.IGNORECASE)]
    if extra:
        failures.append("extra_prose")
    forced, next_failures = _parse_assignments(fields.get("NEXT", "NONE"))
    failures.extend(next_failures)
    if len(forced) > 1:
        failures.append("multiple_next_moves")
    status = fields.get("STATUS", "").upper()
    if status not in STATUS_VALUES:
        failures.append("bad_status")
        status_value = None
    else:
        status_value = status
    return OperatorPrediction(forced, None, status_value, text, not failures, failures, reason=fields.get("REASON"))


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

    def predict(self, task: CSPTask, assignment: dict[int, int], batch_size: int = 4, mode: str = "list_all", sudoku_rendering: str = "grid") -> OperatorPrediction:
        parser = parse_single_output if mode == "single" else parse_operator_output
        prompt = render_current_node_prompt(task, assignment, reprompt=False, mode=mode, sudoku_rendering=sudoku_rendering)
        first = self.generate_texts([prompt], batch_size=batch_size)[0]
        parsed = parser(first)
        if parsed.parse_success:
            return parsed
        retry_prompt = render_current_node_prompt(task, assignment, reprompt=True, mode=mode, sudoku_rendering=sudoku_rendering)
        retry = self.generate_texts([retry_prompt], batch_size=batch_size)[0]
        reparsed = parser(retry)
        return OperatorPrediction(reparsed.forced, reparsed.guess, reparsed.status, retry, reparsed.parse_success, reparsed.failure_modes, reprompted=True, reason=reparsed.reason)