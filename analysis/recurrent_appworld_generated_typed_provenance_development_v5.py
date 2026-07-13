"""Caller-level AppWorld safety restoration around the frozen task processor."""
from __future__ import annotations

import sys
from typing import Any

import appworld

from analysis import recurrent_appworld_generated_typed_provenance_development as frozen_v1
from analysis.recurrent_appworld_generated_typed_provenance_development_v4 import (
    AppWorldV02PristineLifecycleAdapter,
    PRISTINE_SAFETY_GUARD,
)

FROZEN_PROCESS_TASK = frozen_v1.process_task


def process_task_with_restoration(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Restore process globals even if world construction or close dispatch fails."""

    try:
        return FROZEN_PROCESS_TASK(*args, **kwargs)
    finally:
        PRISTINE_SAFETY_GUARD.disable()


def main() -> None:
    appworld.AppWorld = AppWorldV02PristineLifecycleAdapter
    frozen_v1.process_task = process_task_with_restoration
    frozen_v1.SHARD_SCHEMA = "recurrent_appworld_generated_typed_provenance_task_shard_v5"
    frozen_v1.RESULT_SCHEMA = "recurrent_appworld_generated_typed_provenance_development_v5"
    if "--contract" not in sys.argv:
        sys.argv.extend(
            [
                "--contract",
                "specs/recurrent_parallel_appworld_generated_typed_provenance_development_v5.json",
            ]
        )
    if "--output-dir" not in sys.argv:
        sys.argv.extend(
            [
                "--output-dir",
                "results/recurrent_parallel_appworld_generated_typed_provenance_development_v5",
            ]
        )
    frozen_v1.main()


if __name__ == "__main__":
    main()
