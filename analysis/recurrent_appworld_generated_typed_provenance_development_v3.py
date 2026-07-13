"""Safety-guard lifecycle repair layered on the frozen AppWorld 0.2 adapter."""
from __future__ import annotations

import sys
from typing import Any, ClassVar

import appworld

from analysis import recurrent_appworld_generated_typed_provenance_development as frozen_v1
from analysis.recurrent_appworld_generated_typed_provenance_development_v2 import (
    AppWorldV01ConstructorAdapter,
)


class AppWorldV02LifecycleAdapter(AppWorldV01ConstructorAdapter):
    """Restore the per-world SafetyGuard before global AppWorld cleanup."""

    active_instances: ClassVar[list["AppWorldV02LifecycleAdapter"]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active_instances.append(self)

    @classmethod
    def close_all(cls, *args: Any, **kwargs: Any) -> None:
        for world in reversed(cls.active_instances):
            world.safety_guard.disable()
        cls.active_instances.clear()
        super().close_all(*args, **kwargs)


def main() -> None:
    appworld.AppWorld = AppWorldV02LifecycleAdapter
    frozen_v1.SHARD_SCHEMA = "recurrent_appworld_generated_typed_provenance_task_shard_v3"
    frozen_v1.RESULT_SCHEMA = "recurrent_appworld_generated_typed_provenance_development_v3"
    if "--contract" not in sys.argv:
        sys.argv.extend(
            [
                "--contract",
                "specs/recurrent_parallel_appworld_generated_typed_provenance_development_v3.json",
            ]
        )
    if "--output-dir" not in sys.argv:
        sys.argv.extend(
            [
                "--output-dir",
                "results/recurrent_parallel_appworld_generated_typed_provenance_development_v3",
            ]
        )
    frozen_v1.main()


if __name__ == "__main__":
    main()
