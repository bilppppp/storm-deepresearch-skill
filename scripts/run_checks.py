#!/usr/bin/env python3
"""Run the local release gates with non-zero failure propagation."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> int:
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT, check=False)
    return result.returncode


def validate_schema_files() -> int:
    failures = []
    schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
    schema_paths.append(ROOT / "evals" / "output" / "schema.json")
    for path in schema_paths:
        if not path.is_file():
            failures.append(f"{path.relative_to(ROOT)}: required schema is missing")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"{path.name}: {exc}")
            continue
        if payload.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            failures.append(f"{path.name}: wrong JSON Schema dialect")
        if payload.get("additionalProperties") is not False:
            failures.append(f"{path.name}: top-level additionalProperties must be false")
    for failure in failures:
        print(failure, file=sys.stderr)
    return 0 if not failures else 4


def run_all() -> int:
    commands = [
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        [sys.executable, "-m", "compileall", "-q", "scripts", "tests"],
    ]
    for command in commands:
        code = run(command)
        if code:
            return code
    code = validate_schema_files()
    if code:
        return code
    yao = Path.home() / ".agents" / "skills" / "yao-meta-skill" / "scripts" / "yao.py"
    if not yao.is_file():
        print("Yao Meta Skill CLI is unavailable.", file=sys.stderr)
        return 3
    return run([sys.executable, str(yao), "validate", str(ROOT)])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--package", type=Path)
    args = parser.parse_args()
    if args.package:
        return run([sys.executable, str(ROOT / "scripts" / "validate_package.py"), str(args.package)])
    return run_all()


if __name__ == "__main__":
    raise SystemExit(main())
