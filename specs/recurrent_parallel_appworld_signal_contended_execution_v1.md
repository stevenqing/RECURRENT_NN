# AppWorld A3 — Contended Quality-Only Execution Addendum v1

- Frozen date: 2026-07-12
- Status: frozen before model outcomes
- User authorization: sharing the occupied card is explicitly authorized
- Parent: `recurrent_parallel_appworld_signal_anchor_v1`

The parent protocol requires an empty compute-process list so signal quality and latency can be measured together. GPUs 2–7 remain occupied by an external DPO job, while GPUs 0–1 host an external VLLM service. This addendum permits one short quality-only run on physical GPU 2 without stopping, signaling, or reconfiguring the external process.

## Resource guard

- expose only physical GPU 2 as logical `cuda:0`;
- require at least 35,000 MiB free before model import;
- require at least one pre-existing compute PID and record it;
- cap this process to 25% of physical GPU memory;
- retain frozen batch size 8 and all generation/prompt/model hashes;
- abort on OOM or any parent-lock mismatch; no CPU fallback;
- verify the pre-existing PID still exists after inference.

## Claim boundary

The deterministic model outputs, parse rate, false-positive/false-negative rates, balanced accuracy, paired outcomes, and task-type-clustered intervals are authorized. Wall-clock latency, throughput, and any GPU speedup or clean query-cost estimate are explicitly non-authoritative under contention. Token counts remain valid.

The original empty-GPU protocol and fail-closed artifact remain unchanged. This addendum is a separately locked execution route and cannot retroactively authorize latency claims.
