#!/usr/bin/env python3
"""Validate research package data contracts without claiming release readiness."""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .contract_io import validate_research_package
except ImportError:
    from contract_io import validate_research_package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    errors = validate_research_package(args.output_dir)
    if errors:
        for error in errors:
            print(error)
        return 4
    print("Research package contracts are valid. Release readiness was not evaluated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
