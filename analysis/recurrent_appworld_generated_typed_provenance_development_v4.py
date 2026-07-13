"""Pristine process-global SafetyGuard restoration for AppWorld 0.2."""
from __future__ import annotations

import sys
from typing import Any

import appworld
from appworld.common.safety_guard import SafetyGuard

from analysis import recurrent_appworld_generated_typed_provenance_development as frozen_v1
from analysis.recurrent_appworld_generated_typed_provenance_development_v3 import (
    AppWorldV02LifecycleAdapter,
)

PRISTINE_SAFETY_GUARD = SafetyGuard()


class AppWorldV02PristineLifecycleAdapter(AppWorldV02LifecycleAdapter):
    """Force restoration from a function table captured before any world exists."""

    @classmethod
    def close_all(cls, *args: Any, **kwargs: Any) -> None:
        try:
            super().close_all(*args, **kwargs)
        finally:
            PRISTINE_SAFETY_GUARD.disable()


def main() -> None:
    appworld.AppWorld = AppWorldV02PristineLifecycleAdapter
    frozen_v1.SHARD_SCHEMA = "recurrent_appworld_generated_typed_provenance_task_shard_v4"
    frozen_v1.RESULT_SCHEMA = "recurrent_appworld_generated_typed_provenance_development_v4"
    if "--contract" not in sys.argv:
        sys.argv.extend(
            [
                "--contract",
                "specs/recurrent_parallel_appworld_generated_typed_provenance_development_v4.json",
            ]
        )
    if "--output-dir" not in sys.argv:
        sys.argv.extend(
            [
                "--output-dir",
                "results/recurrent_parallel_appworld_generated_typed_provenance_development_v4",
            ]
        )
    frozen_v1.main()


if __name__ == "__main__":
    main()
