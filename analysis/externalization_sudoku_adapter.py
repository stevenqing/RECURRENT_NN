"""Sudoku bounded-register adapter preflight for externalization Track C."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_reasoning_gym_bounded_register import _ensure_reasoning_gym


SCHEMA_VERSION = "externalization_sudoku_adapter_v0"
STATUS_COMPLETE = "EXTERNALIZATION_SUDOKU_ADAPTER_PREFLIGHT_COMPLETE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _make_dataset(args: argparse.Namespace) -> Any:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    return reasoning_gym.create_dataset("sudoku", size=args.n_instances, seed=args.seed, min_empty=args.empty, max_empty=args.empty)


def _peers(cell: int) -> set[int]:
    row, col = divmod(cell, 9)
    box_row = 3 * (row // 3)
    box_col = 3 * (col // 3)
    peers = {9 * row + c for c in range(9) if c != col}
    peers |= {9 * r + col for r in range(9) if r != row}
    peers |= {9 * r + c for r in range(box_row, box_row + 3) for c in range(box_col, box_col + 3) if (r, c) != (row, col)}
    return peers


PEERS = {cell: _peers(cell) for cell in range(81)}


def _givens(entry: dict[str, Any]) -> dict[int, int]:
    puzzle = entry["metadata"]["puzzle"]
    return {9 * row + col: int(puzzle[row][col]) for row in range(9) for col in range(9) if int(puzzle[row][col]) != 0}


def _domains(assignment: dict[int, int]) -> dict[int, list[int]]:
    out = {}
    for cell in range(81):
        if cell in assignment:
            out[cell] = [assignment[cell]]
        else:
            blocked = {assignment[peer] for peer in PEERS[cell] if peer in assignment}
            out[cell] = [value for value in range(1, 10) if value not in blocked]
    return out


def _answer(assignment: dict[int, int]) -> str:
    return "\n".join(" ".join(str(assignment[9 * row + col]) for col in range(9)) for row in range(9))


def _select_cell(assignment: dict[int, int], tried: dict[int, set[int]]) -> int | None:
    domains = _domains(assignment)
    unassigned = [cell for cell in range(81) if cell not in assignment]
    if not unassigned:
        return None
    return min(unassigned, key=lambda cell: (len([v for v in domains[cell] if v not in tried[cell]]), -len(PEERS[cell]), cell))


def _deadend_blockers(cell: int, assignment: dict[int, int]) -> set[int]:
    blockers = set()
    for value in range(1, 10):
        blockers.update(peer for peer in PEERS[cell] if assignment.get(peer) == value)
    return blockers


def _prompt(entry: dict[str, Any], cell: int, domain: list[int], assignment: dict[int, int], register: list[dict[str, int]], r_value: int) -> str:
    row, col = divmod(cell, 9)
    peers = sorted(peer for peer in PEERS[cell] if peer in assignment)
    peer_values = [{"cell": peer, "row": peer // 9, "col": peer % 9, "value": assignment[peer]} for peer in peers]
    view = [{"entry_index": idx, **item} for idx, item in enumerate(register[-r_value:] if r_value > 0 else [])]
    return "\n".join([
        "Reasoning Gym sudoku bounded-register decision. Return JSON only.",
        "Schema: {\"value\": int, \"reason\": str}",
        f"current_cell={cell}; row={row}; col={col}; remaining_domain={domain}",
        f"assigned_row_col_box_peers={peer_values}",
        f"bounded_register={view}",
    ])


def _run_symbolic(dataset: Any, entry: dict[str, Any], r_value: int, node_budget: int) -> dict[str, Any]:
    assignment = _givens(entry)
    tried: dict[int, set[int]] = defaultdict(set)
    register: list[dict[str, int]] = []
    nodes = 0
    retractions = 0
    max_prompt_chars = 0
    max_register_view = 0
    while True:
        if nodes >= node_budget:
            status = "NODE_CAP"
            break
        cell = _select_cell(assignment, tried)
        if cell is None:
            status = "SOLVED"
            break
        domain = [value for value in _domains(assignment)[cell] if value not in tried[cell]]
        max_prompt_chars = max(max_prompt_chars, len(_prompt(entry, cell, domain, assignment, register, r_value)))
        max_register_view = max(max_register_view, min(r_value, len(register)))
        if domain:
            value = domain[0]
            tried[cell].add(value)
            assignment[cell] = value
            register.append({"cell": cell, "row": cell // 9, "col": cell % 9, "value": value})
            nodes += 1
            continue
        if r_value == 0:
            status = "FORWARD_DEAD_END"
            break
        blockers = _deadend_blockers(cell, assignment)
        indices = [idx for idx, item in enumerate(register) if item["cell"] in blockers]
        if not indices:
            status = "NO_RECOVERY_TARGET"
            break
        target_index = max(indices)
        if len(register) - target_index > r_value:
            status = "NO_RECOVERY_TARGET"
            break
        popped = register[target_index:]
        for item in popped:
            assignment.pop(item["cell"], None)
        for item in popped[1:]:
            tried[item["cell"]].clear()
        tried[cell].clear()
        register = register[:target_index]
        retractions += len(popped)
    score = float(dataset.score_answer(_answer(assignment), entry)) if status == "SOLVED" else 0.0
    return {
        "source_index": int(entry["metadata"].get("source_index", -1)),
        "R": r_value,
        "status": "SOLVED" if score >= 1.0 else status,
        "solved": score >= 1.0,
        "official_score": score,
        "nodes_visited": nodes,
        "retractions": retractions,
        "max_prompt_chars": max_prompt_chars,
        "max_register_view_len": max_register_view,
        "source": SOURCE,
        "provenance": "externalization_sudoku_symbolic_adapter_row_v0",
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    dataset = _make_dataset(args)
    r_values = [int(item) for item in args.r_values.split(",") if item]
    rows = []
    for index in range(args.n_instances):
        entry = dataset[index]
        for r_value in r_values:
            rows.append(_run_symbolic(dataset, entry, r_value, args.node_budget))
    summary = []
    for r_value in r_values:
        subset = [row for row in rows if row["R"] == r_value]
        summary.append({"R": r_value, "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "max_prompt_chars": max(row["max_prompt_chars"] for row in subset), "max_register_view_len": max(row["max_register_view_len"] for row in subset), "status_counts": dict(Counter(row["status"] for row in subset)), "source": SOURCE, "provenance": "externalization_sudoku_adapter_summary_v0"})
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "dataset_config": {"dataset": "sudoku", "empty": args.empty, "node_budget": args.node_budget, "official_scoring": "dataset.score_answer", "source": SOURCE, "provenance": "externalization_sudoku_adapter_dataset_v0"},
        "summary": summary,
        "rows": rows,
        "proceed_gates": {"adapter_ready_for_llm": all(row["max_register_view_len"] <= row["R"] for row in rows), "official_scoring_used": True, "source": SOURCE, "provenance": "externalization_sudoku_adapter_gates_v0"},
        "honesty": {"does_not_establish": "This is a sudoku adapter preflight using symbolic choices only; it does not run Qwen LLM decisions yet.", "source": SOURCE, "provenance": "externalization_sudoku_adapter_honesty_v0"},
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run sudoku bounded-register adapter preflight.")
    parser.add_argument("--output", type=Path, default=Path("results/externalization_validation_v0/sudoku_adapter_preflight.json"))
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--n-instances", type=int, default=8)
    parser.add_argument("--empty", type=int, default=45)
    parser.add_argument("--node-budget", type=int, default=320)
    parser.add_argument("--r-values", default="0,2,4,8,16")
    run(parser.parse_args())


if __name__ == "__main__":
    main()