"""BudgetRunner protocol and provenance registry for no-train external baselines."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Protocol

from analysis.kvcache_graph_color_search import _write_json
from experiments.rung1_distributed_graph_coloring import SOURCE


SCHEMA_VERSION = "kvcache_external_budget_baselines_v0"
STATUS_REGISTRY_COMPLETE = "KVCACHE_EXTERNAL_BUDGET_BASELINE_REGISTRY_COMPLETE"


class BudgetRunner(Protocol):
    """Shared interface for budget-capped no-train search baselines."""

    method: str

    def run(self, instance: dict[str, Any], budget_B: int) -> dict[str, Any]:
        """Return solved/tokens/depth under the shared token budget."""
        ...


@dataclass(frozen=True)
class BudgetRunResult:
    method: str
    task: str
    budget_B: int
    solved: bool
    tokens_used: int
    depth_reached: int
    source: str = SOURCE
    provenance: str = "kvcache_external_budget_run_result_v0"


@dataclass(frozen=True)
class BaselineProvenance:
    method: str
    repo: str | None
    url: str | None
    commit: str | None
    status: str
    no_train: bool
    notes: str


BASELINE_REGISTRY = [
    BaselineProvenance(
        method="C_incontext_internal_anchor",
        repo=None,
        url=None,
        commit=None,
        status="IMPLEMENTED_INTERNAL_ANCHOR",
        no_train=True,
        notes="Internal C arm uses the same symbolic/C1 policy as A but accumulates in-context trajectory tokens.",
    ),
    BaselineProvenance(
        method="LFS",
        repo="NathanHerr/LLM-First-Search",
        url="https://github.com/NathanHerr/LLM-First-Search",
        commit="3025bdaa3add6f41388c1d5a6d354522489d312e",
        status="REPO_PORT_SMOKE_IMPLEMENTED_NOT_FINAL",
        no_train=True,
        notes="Official candidate repo. Implements LLM-First Search with explore/value/action queries and max_token_usage accounting. Ported as analysis/kvcache_lfs_baseline.py and smoke-run on sudoku+graph_color n=1; full HB-2 curves pending.",
    ),
    BaselineProvenance(
        method="best_of_n_parallel_sampling",
        repo=None,
        url=None,
        commit=None,
        status="BUDGET_EXHAUSTIVE_SMOKE_IMPLEMENTED_NOT_FINAL",
        no_train=True,
        notes="No external repo required. analysis/kvcache_best_of_n_baseline.py samples complete solutions, bills generated tokens, and now exhausts budget when max_samples_per_budget=0. n=4 B*-only smoke completed; full HB-2 curves pending.",
    ),
    BaselineProvenance(
        method="ToT_RAP_CoTSC",
        repo="maitrix-org/llm-reasoners",
        url="https://github.com/maitrix-org/llm-reasoners",
        commit="f94e5ac2cb9788c3d7d7dbf2173884ed4088e4b2",
        status="REPO_PORT_SMOKE_IMPLEMENTED_NOT_FINAL",
        no_train=True,
        notes="LLM-reasoners README lists ToT, RAP/MCTS, CoT, and related no-train inference-time search examples. ToT/RAP smoke adapters implemented in analysis/kvcache_tot_rap_baselines.py and run on sudoku+graph_color n=1; full HB-2 curves pending.",
    ),
    BaselineProvenance(
        method="First_Finish_Search",
        repo="Aradhye2002/reasoning_exps",
        url="https://github.com/Aradhye2002/reasoning_exps",
        commit="31e1c84c1525ee2f6469c46e433edb1d9e751cf7",
        status="LOCATED_NOT_PORTED",
        no_train=True,
        notes="Official implementation located. Optional baseline, port pending.",
    ),
    BaselineProvenance(
        method="ReST_MCTS_star",
        repo="THUDM/ReST-MCTS",
        url="https://github.com/THUDM/ReST-MCTS",
        commit="2d5f488c3d6e24f99d50a9860e818383b1bb5883",
        status="SCOPED_OUT_RELATED_WORK_ONLY",
        no_train=False,
        notes="Requires trained process reward/value model; scoped out of no-train matched-budget table per addendum.",
    ),
    BaselineProvenance(
        method="Beyond_the_Frontier",
        repo=None,
        url=None,
        commit=None,
        status="OFFICIAL_REPO_NOT_FOUND_NOT_RUN",
        no_train=False,
        notes="GitHub/API/subagent search did not locate official repo. No curve is fabricated; reimpl requires explicit authorization.",
    ),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_registry(output: Path) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_REGISTRY_COMPLETE,
        "generated_at": _now(),
        "budget_runner_protocol": "run(instance, budget_B) -> {solved, tokens_used, depth_reached}",
        "shared_accounting": "All model-generated/exploration/evaluation tokens are billed by the same tokenizer counter; symbolic verifier calls are compute-free but model policy/verifier-prompt tokens are not free.",
        "baselines": [asdict(item) for item in BASELINE_REGISTRY],
        "source": SOURCE,
        "provenance": "kvcache_external_budget_baseline_registry_v0",
    }
    _write_json(output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Write no-train external BudgetRunner baseline registry.")
    parser.add_argument("--output", type=Path, required=True)
    payload = write_registry(parser.parse_args().output)
    print(json.dumps({"path": str(parser.parse_args().output), "status": payload["status"]}, sort_keys=True))


if __name__ == "__main__":
    main()
