"""Plot helpers for Stage D result JSON files."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    plt = None


def describe_plot_inputs() -> dict[str, str]:
    return {
        "two_by_two": "results/two_by_two/results.json",
        "depth1": "results/d_stage_1/results.json",
        "capacity": "results/d_stage_2/results.json",
        "vs_cot": "results/d_stage_3/results.json",
        "verifier": "results/verifier/results.json",
        "ttt": "results/ttt/results.json",
    }


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _save(fig: plt.Figure, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return str(path)


def plot_two_by_two(rows: list[dict[str, Any]], output_dir: Path) -> str:
    labels = [f"{row['method']}\n{row['column']}" for row in rows]
    rates = [row["solve_rate"] for row in rows]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(labels, rates, color=["#5b8def", "#d05a6e", "#4aa56f", "#4aa56f"])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("solve rate")
    ax.set_title("2x2 falsification")
    ax.tick_params(axis="x", labelrotation=20)
    return _save(fig, output_dir / "two_by_two.png")


def plot_depth1(rows: list[dict[str, Any]], output_dir: Path) -> str:
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = [row["method"] for row in rows]
    rates = [row["solve_rate"] for row in rows]
    ax.bar(labels, rates, color="#4aa56f")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("solve rate")
    ax.set_title("D-stage 1 depth-1 revert gate")
    ax.tick_params(axis="x", labelrotation=20)
    return _save(fig, output_dir / "d_stage_1.png")


def plot_capacity(rows: list[dict[str, Any]], output_dir: Path) -> str:
    fig, ax = plt.subplots(figsize=(8, 5))
    for register_type in ["structured", "gru"]:
        subset = [row for row in rows if row["register_type"] == register_type and row["K"] in {60, 729}]
        for K in [60, 729]:
            series = sorted((row for row in subset if row["K"] == K), key=lambda row: row["D"])
            ax.plot([row["D"] for row in series], [row["observed_frontier"] for row in series], marker="o", label=f"{register_type}, K={K}")
    ax.set_xscale("log", base=2)
    ax.set_xlabel("register dimension D")
    ax.set_ylabel("observed frontier")
    ax.set_title("D-stage 2 capacity frontier")
    ax.legend()
    return _save(fig, output_dir / "d_stage_2_capacity.png")


def plot_vs_cot(rows: list[dict[str, Any]], output_dir: Path) -> str:
    paths = []
    configs = sorted({(row["D"], row["K"]) for row in rows})
    for D, K in configs:
        fig, ax = plt.subplots(figsize=(7, 4))
        for row in rows:
            if row["D"] != D or row["K"] != K:
                continue
            curve = row["solve_curve"]
            ax.plot([point["depth"] for point in curve], [point["solve_rate"] for point in curve], marker="o", label=row["method"])
        ax.set_ylim(-0.05, 1.05)
        ax.set_xlabel("required depth")
        ax.set_ylabel("solve rate")
        ax.set_title(f"D-stage 3 vs CoT, D={D}, K={K}")
        ax.legend()
        paths.append(_save(fig, output_dir / f"d_stage_3_D{D}_K{K}.png"))
    return ", ".join(paths)


def plot_verifier(rows: list[dict[str, Any]], output_dir: Path) -> str:
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([row["mode"] for row in rows], [row["solve_rate"] for row in rows], color="#7c6fb0")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("solve rate")
    ax.set_title("Verifier ablation")
    return _save(fig, output_dir / "verifier.png")


def plot_ttt(row: dict[str, Any], output_dir: Path) -> str:
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(["structured", "ttt"], [row["structured_restore_error"], row["ttt_restore_error"]], color=["#4aa56f", "#d05a6e"])
    ax.set_yscale("log")
    ax.set_ylabel("restore error, log scale")
    ax.set_title("Reversibility diagnostic")
    return _save(fig, output_dir / "ttt_reversibility.png")


def write_summary(data: dict[str, Any], output_dir: Path) -> str:
    two_by_two = data["two_by_two"]
    depth1 = data["depth1"]
    verifier = data["verifier"]
    ttt = data["ttt"]
    structured_depth1 = next(row for row in depth1 if row["method"] == "structured_register")
    latent_bt = next(row for row in two_by_two if row["method"] == "latent_only" and row["column"] == "backtracking_required")
    structured_bt = next(row for row in two_by_two if row["method"] == "latent_plus_structured_register" and row["column"] == "backtracking_required")
    oracle_verifier = next(row for row in verifier if row["mode"] == "oracle")
    disabled_verifier = next(row for row in verifier if row["mode"] == "disabled")
    lines = [
        "# Stage D Scaffold Analysis",
        "",
        "These figures summarize oracle-trace scaffold outputs, not trained-model evaluations.",
        "",
        "## Gates",
        "",
        f"- 2x2 falsification backtracking column: latent-only solve rate {latent_bt['solve_rate']:.2f}, structured-register solve rate {structured_bt['solve_rate']:.2f}.",
        f"- D-stage 1 depth-1 gate: structured-register solve rate {structured_depth1['solve_rate']:.2f} with {structured_depth1['applied_reverts']} applied reverts.",
        f"- Verifier ablation: oracle solve rate {oracle_verifier['solve_rate']:.2f}, disabled solve rate {disabled_verifier['solve_rate']:.2f}.",
        f"- TTT diagnostic: restore-error ratio {ttt['ratio']:.2f}.",
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def generate_analysis(output_dir: str = "results/analysis") -> dict[str, str]:
    inputs = describe_plot_inputs()
    missing = [path for path in inputs.values() if not os.path.exists(path)]
    if missing:
        raise FileNotFoundError(f"missing result files: {missing}")
    data = {name: _read_json(path) for name, path in inputs.items()}
    out = Path(output_dir)
    if plt is None:
        return {
            "summary": write_summary(data, out),
            "plots": "skipped: matplotlib is not installed in this environment",
        }
    artifacts = {
        "two_by_two": plot_two_by_two(data["two_by_two"], out),
        "depth1": plot_depth1(data["depth1"], out),
        "capacity": plot_capacity(data["capacity"], out),
        "vs_cot": plot_vs_cot(data["vs_cot"], out),
        "verifier": plot_verifier(data["verifier"], out),
        "ttt": plot_ttt(data["ttt"], out),
        "summary": write_summary(data, out),
    }
    return artifacts


if __name__ == "__main__":
    print(json.dumps(generate_analysis(), indent=2))
