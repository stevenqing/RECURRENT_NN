# EBW Track A Model Launch Preflight v1

## Status

`FROZEN_AFTER_EXECUTION_PREFLIGHT_BEFORE_MODEL_LAUNCH`

## Purpose

Check whether the frozen Track A opened-pool model run can be launched. This preflight does not launch a model. It checks the local freeze tag, execution lock, parser smoke, model identity, GPU availability, and output-directory absence.

## Blocking Conditions

- freeze tag missing or not at expected commit;
- execution preflight not ready;
- runner smoke not passed;
- model download record does not match accepted model id;
- no GPU with enough free memory;
- output directory already exists;
- sealed variations opened;
- model launch not explicitly authorized.

## Boundary

No model process is started by this preflight.