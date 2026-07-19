# EBW Track A v30 Test-Time Compute Freeze

## Status: **`RPD_EBW_TRACK_A_V30_TEST_TIME_COMPUTE_FREEZE_READY`**

- Scope: freeze protocol and artifacts before prospective held-out TTC outcomes
- Sealed AppWorld variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Claim Boundary

v30 retrospective replay can validate the frozen loop mechanics, but only a preregistered held-out run can support a test-time compute claim.

## Frozen Files

| File | SHA256 |
|---|---|
| `analysis/ebw_track_a_model_run_from_manifest.py` | `5f53e39d15c8fc7ab179a831b584301a31dba6dd76a02838ba20c9a045c69988` |
| `analysis/ebw_track_a_rescore_from_raw.py` | `9773bea331703e08619a6d539b1682de141bb4e0cf07bb8dcbdfd9cce480fbc3` |
| `analysis/ebw_track_a_v29_frontier_closure_repair_policy.py` | `ffbcecb39396487016b3b22c90477672672634b425e9f680ccdc2de678e606b4` |
| `analysis/ebw_track_a_v29_frontier_selection_eval.py` | `1e2e169126c3de47da6dd403cabb54c5bf01654c46e6aa0cc345f43ab1fb0d4b` |
| `analysis/ebw_track_a_v29_frontier_selection_prompt_manifest.py` | `f7f1d47760de98e46b28c013a185872f9b6e38872c2c8066b7d97bb0648e7650` |
| `experiments/ebw_obligation_sketch.py` | `a6e32da97e55fd4be4a582b512813338cf260d9baf2e00c5a157318d145d2456` |
| `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v29b_frontier_selection_merged/results.json` | `e82d4f54e845de7ba4967083e15dbdae0477b2a181ab7a6cd9e1a95ad4d14d9c` |
| `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v17_merged/results.json` | `98c6f38defd90bc6d3b5920c619238fe3e2f735a4abbe67feb9aaee8a3a14dfe` |
| `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v28_prior_effect_merged/results.json` | `88b5549b9645ffc11203ad627939684d17af6be8581b08c4d0d474f0fc94b7f1` |
| `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29_frontier_closure_repair_policy/primitive_library.json` | `04b5f343f2cfedc795f25255ae4d146b03f3088ee9e9ccdbfac3eea83552724d` |
| `specs/recurrent_parallel_ebw_test_time_compute_v1.json` | `89e79215320e8b01ffe3e4df86139f80d07593d1047e11ef5b678c7cd39e40cf` |
| `specs/recurrent_parallel_ebw_test_time_compute_v1.md` | `088f9c31730ed09f7cc99b44e6fd544687cc3a30e4933ef0162daba92fd3da8c` |
