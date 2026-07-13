"""Protected-output stream compatibility for AppWorld 0.2 faulthandler."""
from __future__ import annotations

import sys

import appworld

from analysis import recurrent_appworld_generated_typed_provenance_development as frozen_v1
from analysis.recurrent_appworld_generated_typed_provenance_development_v4 import (
    AppWorldV02PristineLifecycleAdapter,
)
from analysis.recurrent_appworld_generated_typed_provenance_development_v5 import (
    process_task_with_restoration,
)


def null_writer_fileno(self: frozen_v1.NullWriter) -> int:
    """Expose the real stderr descriptor without retaining protected text."""

    if sys.__stderr__ is None:
        raise RuntimeError("No underlying stderr descriptor is available")
    return sys.__stderr__.fileno()


def install_v6_compatibility() -> None:
    appworld.AppWorld = AppWorldV02PristineLifecycleAdapter
    frozen_v1.NullWriter.fileno = null_writer_fileno
    frozen_v1.process_task = process_task_with_restoration
    frozen_v1.SHARD_SCHEMA = "recurrent_appworld_generated_typed_provenance_task_shard_v6"
    frozen_v1.RESULT_SCHEMA = "recurrent_appworld_generated_typed_provenance_development_v6"


def main() -> None:
    install_v6_compatibility()
    if "--contract" not in sys.argv:
        sys.argv.extend(
            [
                "--contract",
                "specs/recurrent_parallel_appworld_generated_typed_provenance_development_v6.json",
            ]
        )
    if "--output-dir" not in sys.argv:
        sys.argv.extend(
            [
                "--output-dir",
                "results/recurrent_parallel_appworld_generated_typed_provenance_development_v6",
            ]
        )
    frozen_v1.main()


if __name__ == "__main__":
    main()
