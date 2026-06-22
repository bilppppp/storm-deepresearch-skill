#!/usr/bin/env python3
"""Deprecated wrapper for ``storm_research.py init``."""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.storm_research import initialize_at_output, main as orchestrator_main


SCRIPT_INTERFACE = "deprecated-cli"
SCRIPT_INTERFACE_REASON = "Compatibility surface forwarding initialization to the governed orchestrator."


def initialize(
    topic: str,
    question: str,
    output: Path,
    *,
    language: str = "auto",
    depth_level: str = "full_dossier",
    minimum_units: int | None = None,
    maximum_units: int | None = None,
) -> None:
    initialize_at_output(
        topic,
        question,
        output,
        language=language,
        depth_level=depth_level,
        minimum_units=minimum_units,
        maximum_units=maximum_units,
    )


def main() -> int:
    print(
        "Deprecated: use scripts/storm_research.py init; forwarding to governed init.",
        file=sys.stderr,
    )
    return orchestrator_main(["init", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
