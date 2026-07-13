# AppWorld Multi-App Census v1

- Frozen date: 2026-07-12
- Status: frozen before model outcomes
- Parent: `recurrent_parallel_appworld_v1`

## Observed schema facts

Official no-Docker verification completed before this census lock: 1,553 app tests passed, 138 package tests passed, and 147/147 train/dev validation tasks passed.

Programmatic aggregate-only schema discovery found:

- train: 90 episodes, 30 independent task types; 30 episodes/10 types require at least two apps; 6 episodes/2 types require three apps;
- dev: 57 episodes, 19 independent task types; 21 episodes/7 types require two apps; no dev episode requires three apps.

No test task instruction, ground truth, evaluator report, or task-wise outcome was inspected.

## Candidate rule

Select every train/dev episode whose protected `required_apps` list has length at least two. Use all three official task variations, but cluster statistical intervals and tests by the shared task-type prefix so variations are not treated as independent task types.

The model-visible manifest contains only task ID, split, task-family prefix, variation index, and deterministic selection hash. Required app names, app sets, official API calls, solutions, instructions, and evaluator details are never exported. A separate adjudication manifest stores only aggregate counts and irreversible hashes, not protected content.

## Development split

- train multi-app tasks: prompt/interface development and demonstrations;
- dev multi-app tasks: locked mechanism and signal development confirmation;
- test_normal/test_challenge: untouched until a later end-to-end contract is frozen.

## Agent-count interpretation

A two-app task supports two parallel app specialists plus a coordinator. A three-app task supports three specialists plus a coordinator. Oracle required-app routing is allowed only for no-LLM mechanism and diagnostic tracks and must be labeled as oracle routing. End-to-end agents must infer app relevance from public instruction/API documentation, and all router calls count toward budget.

## A1 gates

- pinned AppWorld 0.1.3.post1 under Python 3.11.15;
- data version 0.1.0;
- official no-Docker verification passes;
- exact source cardinalities 90 train and 57 dev;
- exact candidate cardinalities 30 train and 21 dev;
- exact independent candidate types 10 train and 7 dev;
- all exported rows omit protected app names and solution/evaluator content;
- deterministic hashes and replay;
- test ground truth remains unread.

A pass authorizes only the no-LLM recurrent controller implementation, not Qwen or test evaluation.
