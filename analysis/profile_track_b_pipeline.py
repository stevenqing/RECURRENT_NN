"""Profile the current Track B TRM pipeline before optimization.

This script intentionally mirrors the current trainer's data path and training
semantics while adding wall-clock phase timing, torch.profiler capture, and
nvidia-smi GPU utilization sampling. It is a P0 measurement gate, not an
optimized implementation.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import threading
import time
from typing import Any, Iterator

import torch

from experiments.train_recurrent_operator import (
    _batch,
    _base_model,
    _calibrate_tau,
    _forced_mask_pos_weight,
    _generate_band,
    _loss,
    forced_only_commit_decision,
)
from experiments.train_trm_operator import (
    PerCellTokenRecurrentOperator,
    TrackBConfig,
    _encode_assignment_tokens,
    _episode_tasks_parallel,
    _parameter_count,
    _tensorize_token_examples_parallel,
)
from llm_operator.symbolic_filter import forced_moves, status as csp_status


@dataclass
class PhaseTimer:
    seconds: Counter[str] = field(default_factory=Counter)

    @contextmanager
    def measure(self, name: str, synchronize_cuda: bool = False) -> Iterator[None]:
        if synchronize_cuda and torch.cuda.is_available():
            torch.cuda.synchronize()
        start = time.perf_counter()
        try:
            yield
        finally:
            if synchronize_cuda and torch.cuda.is_available():
                torch.cuda.synchronize()
            self.seconds[name] += time.perf_counter() - start


class GpuUtilSampler:
    def __init__(self, gpu_ids: list[int], interval_seconds: float):
        self.gpu_ids = gpu_ids
        self.interval_seconds = interval_seconds
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.gpu_ids:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        ids = ",".join(str(index) for index in self.gpu_ids)
        command = [
            "nvidia-smi",
            f"--id={ids}",
            "--query-gpu=index,utilization.gpu,memory.used",
            "--format=csv,noheader,nounits",
        ]
        while not self._stop.is_set():
            timestamp = time.time()
            try:
                output = subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                output = ""
            for line in output.splitlines():
                parts = [part.strip() for part in line.split(",")]
                if len(parts) != 3:
                    continue
                try:
                    self.samples.append({
                        "timestamp": timestamp,
                        "gpu_index": int(parts[0]),
                        "utilization_gpu_percent": float(parts[1]),
                        "memory_used_mib": float(parts[2]),
                    })
                except ValueError:
                    continue
            self._stop.wait(self.interval_seconds)

    def summary(self) -> dict[str, Any]:
        if not self.samples:
            return {"n_samples": 0, "per_gpu": {}, "mean_utilization_gpu_percent": 0.0, "max_utilization_gpu_percent": 0.0}
        per_gpu: dict[str, dict[str, float]] = {}
        for gpu_id in sorted({sample["gpu_index"] for sample in self.samples}):
            rows = [sample for sample in self.samples if sample["gpu_index"] == gpu_id]
            utils = [row["utilization_gpu_percent"] for row in rows]
            memories = [row["memory_used_mib"] for row in rows]
            per_gpu[str(gpu_id)] = {
                "n_samples": float(len(rows)),
                "mean_utilization_gpu_percent": sum(utils) / max(len(utils), 1),
                "max_utilization_gpu_percent": max(utils) if utils else 0.0,
                "mean_memory_used_mib": sum(memories) / max(len(memories), 1),
                "max_memory_used_mib": max(memories) if memories else 0.0,
            }
        all_utils = [sample["utilization_gpu_percent"] for sample in self.samples]
        return {
            "n_samples": len(self.samples),
            "per_gpu": per_gpu,
            "mean_utilization_gpu_percent": sum(all_utils) / max(len(all_utils), 1),
            "max_utilization_gpu_percent": max(all_utils) if all_utils else 0.0,
        }


def _cuda_device_ids(devices: str, device: str) -> list[int]:
    if devices:
        return [int(match.group(1)) for item in devices.split(",") if (match := re.search(r"cuda:(\d+)", item.strip()))]
    match = re.search(r"cuda:(\d+)", device)
    return [int(match.group(1))] if match else []


def _percentage_rows(seconds: dict[str, float]) -> list[dict[str, float | str]]:
    total = sum(seconds.values())
    return [
        {"phase": key, "seconds": value, "percent_of_measured_wallclock": (100.0 * value / total) if total else 0.0}
        for key, value in sorted(seconds.items(), key=lambda item: item[1], reverse=True)
    ]


@torch.no_grad()
def _profile_eval_episodes_token(
    model: torch.nn.Module,
    tasks: list[Any],
    device: str,
    tau: float,
    phase_timer: PhaseTimer,
    max_commits: int,
) -> dict[str, Any]:
    model.eval()
    totals = Counter()
    depth_hist = Counter(task.dpll_backtrack_depth for task in tasks)
    for task_record in tasks:
        current = dict(task_record.initial_assignment)
        reason = "max_commits"
        for _ in range(max_commits):
            with phase_timer.measure("eval_symbolic_status_seconds"):
                current_status = csp_status(task_record.task, current)
            if current_status != "OPEN":
                reason = current_status.lower()
                break
            with phase_timer.measure("eval_symbolic_forced_moves_seconds"):
                allowed = forced_moves(task_record.task, current)
            if not allowed:
                reason = "stuck_no_symbolic_forced_move"
                break
            with phase_timer.measure("eval_encode_to_device_seconds", synchronize_cuda=True):
                x = _encode_assignment_tokens(task_record.task, current).unsqueeze(0).to(device)
            with phase_timer.measure("eval_model_forward_seconds", synchronize_cuda=True):
                outputs = model(x)
            with phase_timer.measure("eval_commit_decision_seconds"):
                decision = forced_only_commit_decision(outputs, tau, allowed_forced=allowed)
            if not decision.commit:
                reason = decision.reason
                break
            current[decision.var] = int(decision.val)  # type: ignore[index]
            totals["commits"] += 1
        with phase_timer.measure("eval_symbolic_status_seconds"):
            final_status = csp_status(task_record.task, current)
        fixpoint_reached = current == task_record.target_fixpoint
        totals["episodes"] += 1
        totals["solved"] += int(final_status == "SOLVED")
        totals["fixpoint_reached"] += int(fixpoint_reached)
        totals[f"reason:{reason}"] += 1
    return {
        "n_episodes": totals["episodes"],
        "fixpoint_reach_rate": totals["fixpoint_reached"] / max(totals["episodes"], 1),
        "solve_rate": totals["solved"] / max(totals["episodes"], 1),
        "mean_commits": totals["commits"] / max(totals["episodes"], 1),
        "stick_reason_histogram": {key.removeprefix("reason:"): value for key, value in sorted(totals.items()) if key.startswith("reason:")},
        "depth_histogram": {str(key): value for key, value in sorted(depth_hist.items())},
    }


def run_profile(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    device = args.device
    device_ids = _cuda_device_ids(args.devices, args.device)
    if device.startswith("cuda") and not torch.cuda.is_available():
        device = "cpu"
        device_ids = []
    if device_ids:
        device = f"cuda:{device_ids[0]}"
    torch.manual_seed(args.seed)
    phase_timer = PhaseTimer()
    sampler = GpuUtilSampler(device_ids, args.gpu_sample_interval_seconds)
    sampler.start()
    started_at = datetime.now(timezone.utc).isoformat()
    wall_start = time.perf_counter()
    try:
        with phase_timer.measure("data_generation_seconds"):
            train_instances_rows, train_examples = _generate_band(1, 2, args.train_instances, args.seed, args.generation_workers)
            eval_instances_rows, eval_examples = _generate_band(1, 2, args.eval_instances, args.seed + 1000, args.generation_workers)
            l4_rows_raw, l4_examples = _generate_band(4, 8, args.l4_instances, args.seed + 2000, args.generation_workers)
        with phase_timer.measure("episode_preparation_seconds"):
            eval_episode_tasks = _episode_tasks_parallel("eval", eval_instances_rows, workers=args.episode_workers)
        with phase_timer.measure("tensorization_seconds"):
            train_rows = _tensorize_token_examples_parallel("train", train_examples, augment_digits=True, seed=args.seed + 10, workers=args.tensorize_workers)
            eval_rows = _tensorize_token_examples_parallel("eval", eval_examples, augment_digits=False, seed=args.seed + 20, workers=args.tensorize_workers)
            _tensorize_token_examples_parallel("l4", l4_examples, augment_digits=False, seed=args.seed + 30, workers=args.tensorize_workers)

        config = TrackBConfig(
            hidden_dim=args.hidden_dim,
            nhead=args.nhead,
            feedforward_dim=args.feedforward_dim,
            recurrence_steps=args.recurrence_steps,
            dropout=0.0,
        )
        model: torch.nn.Module = PerCellTokenRecurrentOperator(config).to(device)
        parameter_count = _parameter_count(model)
        if len(device_ids) > 1:
            model = torch.nn.DataParallel(model, device_ids=device_ids)
        optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
        pos_weight_tensor, pos_weight_record = _forced_mask_pos_weight(train_rows, device, None if args.forced_pos_weight < 0 else args.forced_pos_weight)
        ema_state = {key: value.detach().clone() for key, value in _base_model(model).state_dict().items()}
        ema_decay = 0.995
        activities = [torch.profiler.ProfilerActivity.CPU]
        if device.startswith("cuda") and torch.cuda.is_available():
            activities.append(torch.profiler.ProfilerActivity.CUDA)
        profiler_path = output_dir / "torch_profiler_trace.json"
        profiler_table_path = output_dir / "torch_profiler_key_averages.txt"
        last_loss = 0.0
        last_forced_loss = 0.0
        profiler_schedule = torch.profiler.schedule(wait=0, warmup=0, active=max(1, args.profiler_active_steps), repeat=1)
        with phase_timer.measure("training_loop_seconds", synchronize_cuda=True):
            with torch.profiler.profile(activities=activities, schedule=profiler_schedule, record_shapes=False, profile_memory=False) as profiler:
                for step in range(1, args.steps + 1):
                    model.train()
                    with torch.profiler.record_function("batch_sampling_host_to_device"):
                        with phase_timer.measure("batch_sampling_host_to_device_seconds", synchronize_cuda=True):
                            x, action, var, val, forced_mask = _batch(train_rows, args.batch_size, device, args.seed * 100000 + step)
                    with torch.profiler.record_function("forward"):
                        with phase_timer.measure("forward_seconds", synchronize_cuda=True):
                            outputs = model(x)
                    with torch.profiler.record_function("loss"):
                        with phase_timer.measure("loss_seconds", synchronize_cuda=True):
                            loss, forced_loss_value = _loss(outputs, action, var, val, forced_mask, pos_weight_tensor, args.forced_loss, args.focal_gamma)
                    with torch.profiler.record_function("backward"):
                        with phase_timer.measure("backward_seconds", synchronize_cuda=True):
                            optimizer.zero_grad()
                            loss.backward()
                            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    with torch.profiler.record_function("optimizer_step"):
                        with phase_timer.measure("optimizer_step_seconds", synchronize_cuda=True):
                            optimizer.step()
                    with phase_timer.measure("ema_update_seconds"):
                        with torch.no_grad():
                            for key, value in _base_model(model).state_dict().items():
                                ema_state[key].mul_(ema_decay).add_(value.detach(), alpha=1.0 - ema_decay)
                    last_loss = float(loss.detach().item())
                    last_forced_loss = forced_loss_value
                    profiler.step()
            if args.export_chrome_trace:
                profiler.export_chrome_trace(str(profiler_path))
            profiler_table_path.write_text(profiler.key_averages().table(sort_by="cuda_time_total", row_limit=args.profiler_rows), encoding="utf-8")

        with phase_timer.measure("tau_calibration_seconds", synchronize_cuda=True):
            quick_tau = _calibrate_tau(model, eval_rows[: min(len(eval_rows), 1024)], device)
        eval_tasks = eval_episode_tasks[: args.eval_episodes]
        eval_profiler_schedule = torch.profiler.schedule(wait=0, warmup=0, active=1, repeat=1)
        with torch.profiler.profile(activities=activities, schedule=eval_profiler_schedule, record_shapes=False, profile_memory=False) as eval_profiler:
            with torch.profiler.record_function("eval_20_forced_episodes"):
                with phase_timer.measure("eval_episodes_total_seconds", synchronize_cuda=True):
                    eval_metrics = _profile_eval_episodes_token(model, eval_tasks, device, quick_tau["selected_tau"], phase_timer, args.max_commits)
            eval_profiler.step()
        eval_profiler_path = output_dir / "torch_profiler_eval_trace.json"
        eval_profiler_table_path = output_dir / "torch_profiler_eval_key_averages.txt"
        if args.export_chrome_trace:
            eval_profiler.export_chrome_trace(str(eval_profiler_path))
        eval_profiler_table_path.write_text(eval_profiler.key_averages().table(sort_by="cuda_time_total", row_limit=args.profiler_rows), encoding="utf-8")
    finally:
        sampler.stop()

    total_seconds = time.perf_counter() - wall_start
    phase_seconds = dict(phase_timer.seconds)
    training_step_seconds = phase_seconds.get("training_loop_seconds", 0.0) / max(args.steps, 1)
    report = {
        "module": "analysis.profile_track_b_pipeline",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "started_at": started_at,
        "purpose": "P0 profile gate before GPU efficiency optimization; semantics mirror current Track B trainer.",
        "no_optimization_claim": True,
        "profiled_object": "experiments.train_trm_operator current Track B per-cell-token trainer",
        "config": {
            "seed": args.seed,
            "device": device,
            "devices": [f"cuda:{index}" for index in device_ids] if device_ids else [device],
            "train_instances": args.train_instances,
            "eval_instances": args.eval_instances,
            "l4_instances": args.l4_instances,
            "steps": args.steps,
            "batch_size": args.batch_size,
            "hidden_dim": args.hidden_dim,
            "nhead": args.nhead,
            "feedforward_dim": args.feedforward_dim,
            "recurrence_steps": args.recurrence_steps,
            "lr": args.lr,
            "generation_workers": args.generation_workers,
            "episode_workers": args.episode_workers,
            "tensorize_workers": args.tensorize_workers,
            "eval_episodes": args.eval_episodes,
            "max_commits": args.max_commits,
            "profiler_active_steps": args.profiler_active_steps,
        },
        "dataset": {
            "train_instances_generated": len(train_instances_rows),
            "train_examples": len(train_rows),
            "eval_instances_generated": len(eval_instances_rows),
            "eval_examples": len(eval_rows),
            "l4_instances_generated": len(l4_rows_raw),
        },
        "model": {"parameter_count": parameter_count, "data_parallel": len(device_ids) > 1, "pos_weight": pos_weight_record},
        "timing": {
            "total_seconds": total_seconds,
            "phase_seconds": phase_seconds,
            "phase_percentages": _percentage_rows(phase_seconds),
            "training_step_seconds": training_step_seconds,
            "steps_per_sec": (args.steps / phase_seconds.get("training_loop_seconds", total_seconds)) if phase_seconds.get("training_loop_seconds", total_seconds) else 0.0,
            "examples_per_sec": (args.steps * args.batch_size / phase_seconds.get("training_loop_seconds", total_seconds)) if phase_seconds.get("training_loop_seconds", total_seconds) else 0.0,
        },
        "gpu_utilization": sampler.summary(),
        "training_last": {"loss": last_loss, "forced_mask_loss": last_forced_loss},
        "eval_20_episodes": eval_metrics,
        "tau_calibration": quick_tau,
        "artifacts": {
            "torch_profiler_trace": str(profiler_path) if args.export_chrome_trace else None,
            "torch_profiler_key_averages": str(profiler_table_path),
            "torch_profiler_eval_trace": str(eval_profiler_path) if args.export_chrome_trace else None,
            "torch_profiler_eval_key_averages": str(eval_profiler_table_path),
            "report": str(output_dir / "profile_report.json"),
        },
        "acceptance_gate": {
            "profile_steps": args.steps,
            "profiler_active_steps": args.profiler_active_steps,
            "eval_episodes": args.eval_episodes,
            "has_torch_profiler_artifacts": profiler_table_path.exists() and eval_profiler_table_path.exists(),
            "has_gpu_utilization_samples": sampler.summary().get("n_samples", 0) > 0,
        },
    }
    (output_dir / "profile_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "gpu_util_samples.jsonl").write_text("".join(json.dumps(sample, sort_keys=True) + "\n" for sample in sampler.samples), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="P0 profile gate for the current Track B TRM pipeline.")
    parser.add_argument("--output-dir", default="results/profile_gate/track_b_current")
    parser.add_argument("--seed", type=int, default=102)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--devices", default="cuda:0,cuda:1,cuda:2,cuda:3,cuda:4,cuda:5,cuda:6,cuda:7")
    parser.add_argument("--train-instances", type=int, default=4096)
    parser.add_argument("--eval-instances", type=int, default=512)
    parser.add_argument("--l4-instances", type=int, default=128)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--hidden-dim", type=int, default=768)
    parser.add_argument("--nhead", type=int, default=8)
    parser.add_argument("--feedforward-dim", type=int, default=3072)
    parser.add_argument("--recurrence-steps", type=int, default=7)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--generation-workers", type=int, default=8)
    parser.add_argument("--episode-workers", type=int, default=8)
    parser.add_argument("--tensorize-workers", type=int, default=8)
    parser.add_argument("--forced-loss", choices=["bce", "focal"], default="focal")
    parser.add_argument("--forced-pos-weight", type=float, default=-1.0)
    parser.add_argument("--focal-gamma", type=float, default=2.0)
    parser.add_argument("--eval-episodes", type=int, default=20)
    parser.add_argument("--max-commits", type=int, default=64)
    parser.add_argument("--gpu-sample-interval-seconds", type=float, default=0.5)
    parser.add_argument("--profiler-rows", type=int, default=80)
    parser.add_argument("--profiler-active-steps", type=int, default=10)
    parser.add_argument("--export-chrome-trace", action="store_true", help="Write full chrome traces. Off by default because 8-GPU 200-step traces are multi-GB.")
    args = parser.parse_args()
    run_profile(args)


if __name__ == "__main__":
    main()