"""Bounded current-node prompt rendering for Stage D.

The prompt contains only givens plus the partial assignment at the current
search node. It is re-rendered every step and never stores the branch stack.
"""

from __future__ import annotations

from typing import Any, Mapping


class PromptRenderer:
    def render(self, task_type: str, givens: Mapping[str, Any], partial: Mapping[str, Any]) -> str:
        if task_type.startswith("sudoku"):
            return self._sudoku(task_type, givens, partial)
        if task_type in {"horn_sat", "general_sat"}:
            return self._sat(task_type, givens, partial)
        if task_type == "graph_coloring":
            return self._graph_coloring(givens, partial)
        if task_type == "logic_grid":
            return self._logic_grid(givens, partial)
        return f"Task: {task_type}\nGivens: {dict(givens)}\nCurrent assignment: {dict(partial)}\nReturn forced moves or a branch candidate."

    def _sudoku(self, task_type: str, givens: Mapping[str, Any], partial: Mapping[str, Any]) -> str:
        n = 4 if task_type == "sudoku_4x4" else 9
        grid = [["." for _ in range(n)] for _ in range(n)]
        for key, value in {**dict(givens), **dict(partial)}.items():
            row, col = key if isinstance(key, tuple) else tuple(map(int, str(key).split(",")))
            grid[row][col] = str(value)
        rows = [" ".join(row) for row in grid]
        return "\n".join([f"Current {n}x{n} Sudoku node (. = empty):", *rows, "Return forced moves or one branch candidate."])

    def _sat(self, task_type: str, givens: Mapping[str, Any], partial: Mapping[str, Any]) -> str:
        return "\n".join([
            f"Current {task_type} node.",
            f"Clauses: {givens.get('clauses', [])}",
            f"Variables: {givens.get('n_vars', 0)}",
            f"Current assignment: {dict(partial)}",
            "Return unit propagations or one branch candidate.",
        ])

    def _graph_coloring(self, givens: Mapping[str, Any], partial: Mapping[str, Any]) -> str:
        return "\n".join([
            f"Graph coloring node, k={givens.get('k')}, n={givens.get('n')}.",
            f"Edges: {givens.get('edges', [])}",
            f"Current assignment: {dict(partial)}",
            "Return forced colors or one branch candidate.",
        ])

    def _logic_grid(self, givens: Mapping[str, Any], partial: Mapping[str, Any]) -> str:
        return "\n".join([
            "Logic grid current node.",
            f"Categories: {givens.get('categories', [])}",
            f"Clues: {givens.get('clues', [])}",
            f"Current assignment: {dict(partial)}",
            "Return forced deductions or one branch candidate.",
        ])
