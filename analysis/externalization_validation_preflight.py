"""Preflight and preregistration artifact for externalization-paper validation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
from urllib.request import urlopen

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_reasoning_gym_bounded_register import _ensure_reasoning_gym


SCHEMA_VERSION = "externalization_paper_validation_v0"
STATUS_COMPLETE = "EXTERNALIZATION_VALIDATION_PREFLIGHT_COMPLETE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _read_json(path: str) -> dict[str, Any] | None:
    target = REPO_ROOT / path
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def _score_candidate(dataset: Any, entry: dict[str, Any]) -> dict[str, Any]:
    candidates = []
    if entry.get("answer") is not None:
        candidates.append(("answer", entry["answer"]))
    possible = entry.get("metadata", {}).get("possible_answer")
    if possible is not None:
        candidates.append(("metadata.possible_answer", json.dumps(possible, sort_keys=True)))
    rows = []
    for source, answer in candidates:
        try:
            score = float(dataset.score_answer(answer, entry))
        except Exception as exc:  # noqa: BLE001 - preflight should capture shape failures.
            rows.append({"source": source, "status": "score_error", "error": f"{type(exc).__name__}: {exc}"[:240]})
            continue
        rows.append({"source": source, "status": "scored", "score": score})
    best = max([row.get("score", 0.0) for row in rows], default=0.0)
    return {"candidate_scores": rows, "best_score": best, "score_answer_usable": best >= 1.0}


def _probe_reasoning_gym(args: argparse.Namespace) -> list[dict[str, Any]]:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    configs: dict[str, dict[str, Any]] = {
        "graph_color": {"size": 2, "seed": args.seed, "num_colors": 3, "min_num_vertices": 8, "max_num_vertices": 8, "edge_probability": 0.3},
        "zebra_puzzles": {"size": 2, "seed": args.seed},
        "sudoku": {"size": 2, "seed": args.seed},
    }
    rows = []
    for name, kwargs in configs.items():
        try:
            dataset = reasoning_gym.create_dataset(name, **kwargs)
            entry = dataset[0]
            score_probe = _score_candidate(dataset, entry)
            rows.append(
                {
                    "benchmark": name,
                    "status": "OK",
                    "config": kwargs,
                    "entry_keys": sorted(entry.keys()),
                    "metadata_keys": sorted(entry.get("metadata", {}).keys()),
                    **score_probe,
                    "source": SOURCE,
                    "provenance": "rg_tier1_preflight_v0",
                }
            )
        except Exception as exc:  # noqa: BLE001 - preflight should capture dependency failures.
            rows.append({"benchmark": name, "status": "FAIL", "config": kwargs, "error": f"{type(exc).__name__}: {exc}"[:400], "source": SOURCE, "provenance": "rg_tier1_preflight_v0"})
    return rows


def _probe_vllm(urls: list[str]) -> list[dict[str, Any]]:
    rows = []
    for url in urls:
        model_url = url.rstrip("/") + "/models"
        try:
            with urlopen(model_url, timeout=2) as response:
                body = response.read().decode("utf-8")
            rows.append({"base_url": url, "status": "OK", "models_response_prefix": body[:500], "source": SOURCE, "provenance": "vllm_endpoint_preflight_v0"})
        except Exception as exc:  # noqa: BLE001
            rows.append({"base_url": url, "status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"[:240], "source": SOURCE, "provenance": "vllm_endpoint_preflight_v0"})
    return rows


def _probe_agentsnet(repo: str) -> dict[str, Any]:
    path = Path(repo)
    candidates = list(path.rglob("*.py"))[:400] if path.exists() else []
    coloring_hits = []
    for candidate in candidates:
        try:
            text = candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "class Coloring" in text or "get_score" in text:
            coloring_hits.append(str(candidate))
    return {
        "repo": repo,
        "exists": path.exists(),
        "python_files_scanned": len(candidates),
        "coloring_get_score_hits": coloring_hits[:20],
        "runtime_policy": "Use Coloring.get_score formula directly; do not import langchain runtime for v0.",
        "source": SOURCE,
        "provenance": "agentsnet_preflight_v0",
    }


def _known_anchors() -> dict[str, Any]:
    item070 = _read_json("results/experiment_items/item_070_rung1_paradigm_overnight_real_llm.json") or {}
    item076 = _read_json("results/experiment_items/item_076_rung1_multiagent_solvability.json") or {}
    closeout = _read_json("results/rung1_multiagent_solvability/closeout.json") or {}
    return {
        "item070_claims_1_2": item070.get("decision", {}).get("headline", {}),
        "item070_honesty": item070.get("honesty", {}),
        "item076_multiagent_headline": item076.get("decision", {}).get("headline", {}),
        "item076_closeout_verdict": closeout.get("consolidated_multiagent_verdict", {}),
        "source": SOURCE,
        "provenance": "externalization_known_anchor_summary_v0",
    }


def _matrix() -> dict[str, Any]:
    return {
        "primary_headline_matrix": {
            "benchmarks": ["graph_color", "zebra_puzzles", "sudoku"],
            "arms": ["M-register R={0,2,4,8,16}", "L0-symbolic-heuristic", "L0-symbolic-random", "L1-oneshot-vanilla", "L1-oneshot-thinking"],
            "budgets": [20, 40, 80, 160, 320],
            "difficulty_requirement": "Hardest bin should degrade random-culprit below 0.7 solve_rate where possible.",
        },
        "secondary_positioning_matrix": {
            "benchmarks": ["one Tier-1 benchmark", "ZebraLogic"],
            "arms": ["L1-bestofN N={5,10}", "L1-selfverify", "L2-tot", "L3-llm2solver", "optional L3-llm-modulo"],
            "purpose": "Position against recent test-time compute and solver-outsourcing baselines, not claim raw solver superiority.",
        },
        "multiagent_matrix": {
            "benchmarks": ["AgentsNet get_score substrate", "controlled partition graph_color", "controlled partition zebra_puzzles"],
            "arms": ["CBJ", "chrono", "forward", "team-vs-monolith no-LLM", "team-vs-monolith frozen-LLM agents"],
            "guard": "No new dense graph_color CBJ instrument cycle; one separator read only.",
        },
        "source": SOURCE,
        "provenance": "externalization_matrix_preregistration_v0",
    }


def _kills() -> list[dict[str, Any]]:
    return [
        {"gate": "claim1_strong_thinking_baseline", "kill_or_scope": "If L1-oneshot-thinking >0.3 on hard bins, scope claim1 to vanilla one-shot cannot search; thinking partially can."},
        {"gate": "claim2_capacity_law", "kill_or_scope": "Confirmed only if solve_rate rises monotonically with R and saturates on at least two Tier-1 benchmarks."},
        {"gate": "llm_adds_value", "kill_or_scope": "If M-register is within noise of L0-symbolic-random/heuristic at matched budget, bank the negative and frame external structure rather than LLM decision superiority."},
        {"gate": "strong_baselines", "kill_or_scope": "If ToT or best-of/selfverify match M-register, narrow contribution to bounded-memory/prompt-flat efficiency."},
        {"gate": "claim3_multiagent", "kill_or_scope": "Claim3 remains structure-dependent unless separator venues show CBJ flat while chrono rises."},
        {"gate": "claim4b_real_llm", "kill_or_scope": "If frozen-LLM team-over-monolith gap does not open past single-register capacity, scope the real-LLM capacity result while preserving symbolic positive."},
    ]


def _next_commands(args: argparse.Namespace) -> list[dict[str, str]]:
    return [
        {
            "name": "start_vllm_qwen35",
            "command": "CUDA_VISIBLE_DEVICES=0,1,2,3 .venv-vllm/bin/python -m vllm.entrypoints.openai.api_server --model /home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3.5-4B/snapshots/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a --served-model-name Qwen/Qwen3.5-4B --port 8001 --tensor-parallel-size 4 --gpu-memory-utilization 0.30 --max-model-len 4096 --max-num-seqs 512",
        },
        {
            "name": "primary_matrix_first_shard",
            "command": "Run graph_color hard-bin matched-budget shard first, then zebra_puzzles and sudoku after CSP adapters land; do not read raw solve_rate as primary.",
        },
        {
            "name": "multiagent_agentsnet_first_shard",
            "command": "Use local AgentsNet graph families plus direct Coloring.get_score formula; avoid langchain runtime import; sweep topology/size/separator.",
        },
    ]


def run(args: argparse.Namespace) -> dict[str, Any]:
    rg_rows = _probe_reasoning_gym(args)
    vllm_rows = _probe_vllm(args.vllm_base_urls.split(","))
    anchors = _known_anchors()
    preregistered = _matrix()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "scope": {
            "validates": "Externalization only: bounded reversible register outside frozen LLM; no training/distillation/RL.",
            "does_not_claim": "This preflight does not execute the full real-LLM validation matrix.",
            "source": SOURCE,
            "provenance": "externalization_scope_v0",
        },
        "known_anchors": anchors,
        "preregistered_matrix": preregistered,
        "kills_and_forks": _kills(),
        "preflight": {
            "reasoning_gym_tier1": rg_rows,
            "vllm_endpoints": vllm_rows,
            "agentsnet": _probe_agentsnet(args.agentsnet_repo),
            "source": SOURCE,
            "provenance": "externalization_preflight_v0",
        },
        "readiness": {
            "tier1_rg_official_scoring_ready": all(row.get("status") == "OK" and row.get("score_answer_usable") for row in rg_rows),
            "vllm_ready": any(row.get("status") == "OK" for row in vllm_rows),
            "agentsnet_formula_ready": Path(args.agentsnet_repo).exists(),
            "primary_blocker": "vLLM endpoint unavailable" if not any(row.get("status") == "OK" for row in vllm_rows) else "implement non-graph_color CSP adapters before full Tier-1 matrix",
            "source": SOURCE,
            "provenance": "externalization_readiness_v0",
        },
        "next_commands": _next_commands(args),
        "honesty": {
            "does_not_establish": "This is preregistration and harness preflight for the externalization paper validation. It banks no new claim result beyond Item070 and Item076 anchors.",
            "main_blockers": "vLLM is not currently serving on the checked endpoints; zebra_puzzles/sudoku need bounded-register CSP adapters before the full primary matrix can be read.",
            "source": SOURCE,
            "provenance": "externalization_preflight_honesty_v0",
        },
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Externalization paper validation preregistration/preflight.")
    parser.add_argument("--output", type=Path, default=Path("results/externalization_validation_v0/preflight.json"))
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--agentsnet-repo", default="/tmp/reasoning_benchmarks/AgentsNet")
    parser.add_argument("--vllm-base-urls", default="http://127.0.0.1:8001/v1,http://127.0.0.1:8000/v1")
    parser.add_argument("--seed", type=int, default=1)
    run(parser.parse_args())


if __name__ == "__main__":
    main()