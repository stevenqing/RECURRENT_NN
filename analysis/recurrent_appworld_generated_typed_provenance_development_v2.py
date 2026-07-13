"""AppWorld 0.2 constructor-compatibility repair for the frozen v1 runner."""
from __future__ import annotations

import sys
from typing import Any

import appworld
from appworld import AppWorld as AppWorldV02

from analysis import recurrent_appworld_generated_typed_provenance_development as frozen_v1


class AppWorldV01ConstructorAdapter(AppWorldV02):
    """Map the removed 0.1 null-patch flag to the explicit 0.2 safety flag."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        null_patch = kwargs.pop("null_patch_unsafe_execution", None)
        if null_patch is not True:
            raise ValueError("The frozen v1 runner must request null-patched unsafe execution")
        if "raise_on_unsafe_execution" in kwargs:
            raise ValueError("Ambiguous AppWorld safety compatibility arguments")
        kwargs["raise_on_unsafe_execution"] = True
        super().__init__(*args, **kwargs)


def main() -> None:
    appworld.AppWorld = AppWorldV01ConstructorAdapter
    frozen_v1.SHARD_SCHEMA = "recurrent_appworld_generated_typed_provenance_task_shard_v2"
    frozen_v1.RESULT_SCHEMA = "recurrent_appworld_generated_typed_provenance_development_v2"
    if "--contract" not in sys.argv:
        sys.argv.extend(
            [
                "--contract",
                "specs/recurrent_parallel_appworld_generated_typed_provenance_development_v2.json",
            ]
        )
    if "--output-dir" not in sys.argv:
        sys.argv.extend(
            [
                "--output-dir",
                "results/recurrent_parallel_appworld_generated_typed_provenance_development_v2",
            ]
        )
    frozen_v1.main()


if __name__ == "__main__":
    main()
