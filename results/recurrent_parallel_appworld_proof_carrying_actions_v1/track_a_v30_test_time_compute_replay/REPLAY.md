# EBW Track A v30 Retrospective Test-Time Compute Replay

## Status: **`RPD_EBW_TRACK_A_V30_RETROSPECTIVE_TTC_REPLAY_PASS`**

- Scope: opened-data retrospective replay of the frozen v29b RepairAgent loop
- Held-out/prospective claim: No
- Sealed AppWorld variations 10-12 opened: No
- Model/GPU/Docker/external process actions by replay: No

## Parallel Repair Curve

| Stage | Repair rounds | Model calls | Commit | Abstain | Unsafe |
|---|---:|---:|---:|---:|---:|
| `round0_no_repair` | 0 | 0 | 831 | 16 | 0 |
| `round1_parallel_v29b_repair` | 1 | 5 | 847 | 0 | 0 |

## Claim Boundary

Retrospective opened-data replay validates loop mechanics only; it is not a prospective held-out TTC result.
