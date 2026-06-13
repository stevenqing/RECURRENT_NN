"""Generate Item079 full-execution manifest for the externalization paper line."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel


SCHEMA_VERSION = "externalization_paper_full_execution_v1"
STATUS_COMPLETE = "EXTERNALIZATION_FULL_EXECUTION_MANIFEST_COMPLETE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: str) -> dict[str, Any]:
    return json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _probe_vllm(base_url: str, model: str) -> dict[str, Any]:
    try:
        with urlopen(base_url.rstrip("/") + "/models", timeout=5) as response:
            models = response.read().decode("utf-8")
        schema = {"type": "object", "properties": {"answer": {"type": "string"}, "ok": {"type": "boolean"}}, "required": ["answer", "ok"]}
        payload = {"model": model, "messages": [{"role": "user", "content": "Return JSON only. Say answer=ready and ok=true."}], "temperature": 0, "max_tokens": 64, "structured_outputs": {"json": schema}}
        request = Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=120) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        text = decoded["choices"][0]["message"]["content"]
        parsed = json.loads(text)
        return {"status": "OK", "base_url": base_url, "model": model, "models_response_prefix": models[:500], "structured_smoke_parseable": True, "structured_smoke_parsed": parsed, "usage": decoded.get("usage"), "source": SOURCE, "provenance": "externalization_vllm_smoke_v1"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNAVAILABLE", "base_url": base_url, "model": model, "error": f"{type(exc).__name__}: {exc}"[:400], "source": SOURCE, "provenance": "externalization_vllm_smoke_v1"}


def run(args: argparse.Namespace) -> dict[str, Any]:
    preflight = _read_json("results/externalization_validation_v0/preflight.json")
    power = _read_json("results/externalization_validation_v0/power_calibration.json")
    two_rail = _read_json("results/externalization_validation_v0/two_rail_gate.json")
    item070 = _read_json("results/experiment_items/item_070_rung1_paradigm_overnight_real_llm.json")
    item076 = _read_json("results/experiment_items/item_076_rung1_multiagent_solvability.json")
    vllm = _probe_vllm(args.vllm_base_url, args.model)

    two_rail_bins = {row["benchmark"]: row for row in two_rail["bins"]}
    graph_go = vllm["status"] == "OK" and two_rail_bins["graph_color"]["lower_rail_pass"] and two_rail_bins["graph_color"]["upper_rail_pass"]
    sudoku_go = vllm["status"] == "OK" and two_rail_bins["sudoku"]["lower_rail_pass"] and two_rail_bins["sudoku"]["upper_rail_pass"]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "supersedes": ["externalization_paper_validation_v0", "item077_preflight_reorder", "item078_power_gate_upper_rail", "item078_middle_band_bin"],
        "scope": {"externalization_only": True, "no_training_distillation_or_rl": True, "frozen_llm": "Qwen/Qwen3.5-4B", "source": SOURCE, "provenance": "externalization_full_execution_scope_v1"},
        "confirmed_state": {"item070_claims_1_2": item070.get("decision", {}).get("headline", {}), "item076_multiagent": item076.get("decision", {}).get("headline", {}), "reasoning_gym_ready": preflight["readiness"]["tier1_rg_official_scoring_ready"], "agentsnet_formula_ready": preflight["readiness"]["agentsnet_formula_ready"], "vllm": vllm, "two_rail_bins": two_rail["bins"], "source": SOURCE, "provenance": "externalization_full_execution_confirmed_state_v1"},
        "phase_gates": [
            {"phase": "0a_preflight", "gate": "DONE", "reason": "Item077 preflight complete."},
            {"phase": "0b_power_gate", "gate": "DONE_PARTIAL", "reason": "Item078 graph_color/sudoku two-rail gates pass; zebra adapter pending; middle-band calibration pending."},
            {"phase": "1_graph_color_ceiling_llm", "gate": "GO" if graph_go else "NO_GO", "reason": "vLLM smoke OK and graph_color two-rail gate pass; must use n>=30." if graph_go else "vLLM or graph_color two-rail gate unavailable."},
            {"phase": "1_sudoku_ceiling_llm", "gate": "GO" if sudoku_go else "NO_GO", "reason": "vLLM smoke OK and sudoku two-rail gate pass; run after graph_color; must use n>=30." if sudoku_go else "vLLM or sudoku two-rail gate unavailable."},
            {"phase": "1_zebra_llm", "gate": "NO_GO", "reason": "zebra structural adapter pending."},
            {"phase": "0b_middle_band", "gate": "TODO", "reason": "Calibrate n>=20 middle-band bins before K3b stressed-heuristic read."},
            {"phase": "2_secondary_baselines", "gate": "TODO", "reason": "Run after primary shards establish baseline curve."},
            {"phase": "3_multiagent_real_llm", "gate": "TODO", "reason": "AgentsNet formula path ready; requires anchor reproduction and real-LLM team/monolith loop."}
        ],
        "runnable_next_commands": [
            {"name": "graph_color_ceiling_llm_shard", "command": "PYTHONPATH=/tmp/reasoning_benchmarks/reasoning-gym .venv/bin/python -m experiments.rung1_reasoning_gym_bounded_register --dataset graph_color --n-instances 30 --scan-limit 500 --node-cap 2000 --num-vertices 14 --num-colors 3 --edge-probability 0.4 --r-values 0,2,4,8,16 --claim4-r 4 --batch-size 128 --call-cap 40 --output results/externalization_validation_v0/graph_color_ceiling_llm.json --checkpoint-path results/externalization_validation_v0/graph_color_ceiling_llm_checkpoint.json --openai-base-url http://127.0.0.1:8001/v1 --openai-model Qwen/Qwen3.5-4B", "gate": "GO" if graph_go else "NO_GO"},
            {"name": "sudoku_adapter_next", "command": "Implement bounded-register RG sudoku M-register runner before real sudoku LLM shard; existing Item070 runner is graph_color-specific.", "gate": "IMPLEMENTATION_REQUIRED"},
            {"name": "middle_band_calibration", "command": "Run n>=20 no-LLM calibration to find L0-heuristic 0.3..0.9 and L0-random <0.3 bins.", "gate": "TODO"}
        ],
        "honesty": {"does_not_establish": "This item registers the full runnable execution contract and GO gates. It does not itself execute every downstream LLM, secondary-baseline, or multi-agent phase.", "blocked_or_todo": "zebra adapter, sudoku M-register adapter, middle-band calibration, secondary baselines, and multi-agent real-LLM loops remain downstream phases.", "source": SOURCE, "provenance": "externalization_full_execution_honesty_v1"},
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate externalization full-execution v1 manifest.")
    parser.add_argument("--output", type=Path, default=Path("results/externalization_validation_v0/full_execution_manifest.json"))
    parser.add_argument("--vllm-base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--model", default="Qwen/Qwen3.5-4B")
    run(parser.parse_args())


if __name__ == "__main__":
    main()