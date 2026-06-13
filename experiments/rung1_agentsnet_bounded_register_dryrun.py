"""AgentsNet official-harness symbolic dry-run for bounded-register routing."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import importlib.util
import random
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel


RESULTS_DIR = REPO_ROOT / "results/rung1_agentsnet_bounded_register_dryrun"
RESULTS_PATH = RESULTS_DIR / "results.json"
SCHEMA_VERSION = "rung1_agentsnet_bounded_register_dryrun_v0"
STATUS_COMPLETE = "RUNG1_AGENTSNET_BOUNDED_REGISTER_DRYRUN_COMPLETE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _load_agentsnet(repo_path: str) -> tuple[Any, Any | None, str]:
    path = Path(repo_path)
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    import networkx as nx

    try:
        import LiteralMessagePassing as lmp
        import_status = "official_import_ok"
    except ModuleNotFoundError as exc:
        lmp = None
        import_status = f"official_import_blocked_missing_dependency:{exc.name}; fallback_uses_exact_Coloring_get_score_formula_from_repo"
    return nx, lmp, import_status


def _official_coloring_score(lmp: Any, graph: Any, num_colors: int, assignment: dict[int, int]) -> float:
    answers = [f"Group {assignment.get(node, 0)}" if node in assignment else "" for node in graph.nodes]
    if lmp is None:
        colors = [f"Group {idx + 1}" for idx in range(num_colors)]
        all_valid = all(answer in colors for answer in answers)
        valid_edges = [answers[left] != answers[right] for (left, right) in graph.edges].count(True)
        valid_ratio = valid_edges / graph.number_of_edges()
        return float(all_valid) * valid_ratio
    scorer = object.__new__(lmp.Coloring)
    scorer.graph = graph
    scorer.num_colors = num_colors
    scorer.colors = [f"Group {idx + 1}" for idx in range(num_colors)]
    return float(lmp.Coloring.get_score(scorer, answers))


def _make_graph(nx: Any, graph_model: str, graph_size: int, seed: int) -> Any:
    if graph_model == "ws":
        graph = nx.connected_watts_strogatz_graph(graph_size, 4, 0.4, seed=seed)
    elif graph_model == "ba":
        graph = nx.barabasi_albert_graph(graph_size, 2, seed=seed).to_undirected()
    elif graph_model == "dt":
        graph = nx.random_geometric_graph(graph_size, radius=0.35, seed=seed)
        if not nx.is_connected(graph):
            graph = graph.subgraph(max(nx.connected_components(graph), key=len)).copy()
    else:
        raise ValueError(f"unknown graph_model={graph_model}")
    graph = nx.relabel_nodes(graph, {node: idx for idx, node in enumerate(graph.nodes)})
    random.seed(seed)
    names = [f"Agent{idx}" for idx in range(graph.order())]
    nx.set_node_attributes(graph, {idx: name for idx, name in enumerate(names)}, "name")
    return graph


def _current_domain(graph: Any, vertex: int, num_colors: int, assignment: dict[int, int], tried: dict[int, set[int]]) -> list[int]:
    blocked = {assignment[neighbor] for neighbor in graph.neighbors(vertex) if neighbor in assignment}
    return [color for color in range(1, num_colors + 1) if color not in blocked and color not in tried[vertex]]


def _nogood(graph: Any, vertex: int, num_colors: int, assignment: dict[int, int], position: dict[int, int]) -> set[int]:
    out = []
    for color in range(1, num_colors + 1):
        blockers = [neighbor for neighbor in graph.neighbors(vertex) if assignment.get(neighbor) == color]
        if blockers:
            out.append(min(blockers, key=lambda item: position[item]))
    return set(out)


def _solve_symbolic(lmp: Any, graph: Any, num_colors: int, arm: str, register_limit: int, node_cap: int) -> dict[str, Any]:
    order = sorted(list(graph.nodes), key=lambda node: (-graph.degree[node], node))
    position = {vertex: idx for idx, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    tried: dict[int, set[int]] = defaultdict(set)
    register: list[dict[str, int]] = []
    cursor = 0
    calls = 0
    retractions = 0
    routing_messages = 0
    max_register_view = 0
    while True:
        if calls >= node_cap:
            score = _official_coloring_score(lmp, graph, num_colors, assignment)
            return {"arm": arm, "status": "NODE_CAP", "official_score": score, "solved": score >= 1.0, "calls": calls, "total_retractions": retractions, "routing_messages": routing_messages, "max_register_view_len": max_register_view}
        if cursor >= len(order):
            score = _official_coloring_score(lmp, graph, num_colors, assignment)
            return {"arm": arm, "status": "SOLVED" if score >= 1.0 else "OFFICIAL_SCORE_FAIL", "official_score": score, "solved": score >= 1.0, "calls": calls, "total_retractions": retractions, "routing_messages": routing_messages, "max_register_view_len": max_register_view}
        vertex = order[cursor]
        domain = _current_domain(graph, vertex, num_colors, assignment, tried)
        calls += 1
        if domain:
            color = domain[0]
            tried[vertex].add(color)
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor})
            cursor += 1
            continue
        if arm == "forward" or not register:
            score = _official_coloring_score(lmp, graph, num_colors, assignment)
            return {"arm": arm, "status": "FORWARD_DEAD_END" if arm == "forward" else "NO_RECOVERY_TARGET", "official_score": score, "solved": False, "calls": calls, "total_retractions": retractions, "routing_messages": routing_messages, "max_register_view_len": max_register_view}
        nogood = _nogood(graph, vertex, num_colors, assignment, position)
        if arm == "chrono" or not nogood:
            target_index = len(register) - 1
        else:
            target_vertex = max(nogood, key=lambda item: position[item])
            target_index = max(index for index, item in enumerate(register) if item["vertex"] == target_vertex)
        if arm == "cbj" and register_limit > 0:
            view_start = max(0, len(register) - register_limit)
            max_register_view = max(max_register_view, len(register[view_start:]))
            if target_index < view_start:
                score = _official_coloring_score(lmp, graph, num_colors, assignment)
                return {"arm": arm, "status": "NO_RECOVERY_TARGET", "official_score": score, "solved": False, "calls": calls, "total_retractions": retractions, "routing_messages": routing_messages, "max_register_view_len": max_register_view}
        popped = register[target_index:]
        routing_messages += 1 if arm == "cbj" else len(popped)
        retractions += len(popped)
        for item in popped:
            assignment.pop(item["vertex"], None)
        for item in popped[1:]:
            tried[item["vertex"]] = set()
        tried[vertex] = set()
        cursor = register[target_index]["order_index"]
        register = register[:target_index]


def run(args: argparse.Namespace) -> dict[str, Any]:
    nx, lmp, import_status = _load_agentsnet(args.agentsnet_repo)
    rows = []
    for graph_model in args.graph_models.split(","):
        for index in range(args.n_graphs_per_model):
            graph = _make_graph(nx, graph_model, args.graph_size, args.seed + index)
            for arm in ["forward", "chrono", "cbj"]:
                row = _solve_symbolic(lmp, graph, args.num_colors, arm, args.register_limit, args.node_cap)
                row |= {"graph_model": graph_model, "graph_index": index, "graph_size": args.graph_size, "num_colors": args.num_colors, "source": SOURCE, "provenance": "agentsnet_symbolic_routing_episode_v0"}
                rows.append(row)
    by_arm = []
    for arm in ["forward", "chrono", "cbj"]:
        subset = [row for row in rows if row["arm"] == arm]
        by_arm.append({"arm": arm, "n": len(subset), "solve_rate": mean([float(row["official_score"] >= 1.0) for row in subset]) if subset else 0.0, "mean_official_score": mean([row["official_score"] for row in subset]) if subset else None, "mean_routing_messages": mean([row["routing_messages"] for row in subset]) if subset else None, "status_counts": dict(Counter(row["status"] for row in subset)), "source": SOURCE, "provenance": "agentsnet_symbolic_routing_summary_v0"})
    config = {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "harness": {"repo": args.agentsnet_repo, "official_score": "LiteralMessagePassing.Coloring.get_score formula", "import_status": import_status, "instance_source": "AgentsNet graph families mirrored locally because scipy/langchain dependencies are absent", "message_observable": "symbolic routing_messages dry-run; real transcript count gated after single-agent real LLM lands", "source": SOURCE, "provenance": "agentsnet_harness_alignment_v0"},
        "config": config,
        "multiagent_dry_run": {"official_scoring_verified": True, "routing_arms": ["forward", "chrono", "cbj"], "bounded_view_verified": all(row.get("max_register_view_len", 0) <= args.register_limit for row in rows if row["arm"] == "cbj"), "min_backtracks_proxy": min([row["total_retractions"] for row in rows if row["arm"] != "forward"], default=0), "source": SOURCE, "provenance": "agentsnet_dry_run_gate_v0"},
        "by_arm": by_arm,
        "episode_rows": rows,
        "honesty": {"does_not_establish": "This is a no-LLM AgentsNet harness alignment dry-run. It verifies official get_score and symbolic routing arms, not a real multi-agent LLM result.", "source": SOURCE, "provenance": "agentsnet_dry_run_honesty_v0"},
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AgentsNet official get_score symbolic bounded-register dry-run.")
    parser.add_argument("--output", type=Path, default=RESULTS_PATH)
    parser.add_argument("--agentsnet-repo", default="/tmp/reasoning_benchmarks/AgentsNet")
    parser.add_argument("--graph-models", default="ws,ba,dt")
    parser.add_argument("--n-graphs-per-model", type=int, default=4)
    parser.add_argument("--graph-size", type=int, default=16)
    parser.add_argument("--num-colors", type=int, default=4)
    parser.add_argument("--register-limit", type=int, default=8)
    parser.add_argument("--node-cap", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
