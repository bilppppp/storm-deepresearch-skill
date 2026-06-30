#!/usr/bin/env python3
"""Run the local release gates with non-zero failure propagation."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_TARGETS = ("openai", "claude", "generic", "vscode")


def run(command: list[str]) -> int:
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT, check=False)
    return result.returncode


def project_python() -> str:
    candidate = ROOT / ".venv" / "bin" / "python"
    return str(candidate) if candidate.is_file() else sys.executable


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
    python = project_python()
    commands = [
        [python, "-m", "unittest", "discover", "-s", "tests", "-v"],
        [python, "-m", "compileall", "-q", "scripts", "tests"],
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
    return run([python, str(yao), "validate", str(ROOT)])


def run_dist() -> int:
    python = project_python()
    dist = ROOT / "dist"
    expectations = ROOT / "evals" / "packaging_expectations.json"
    yao = Path.home() / ".agents" / "skills" / "yao-meta-skill" / "scripts" / "yao.py"
    if not yao.is_file():
        print("Yao Meta Skill CLI is unavailable.", file=sys.stderr)
        return 3
    package_command = [
        python,
        str(yao),
        "package",
        str(ROOT),
    ]
    for target in PACKAGE_TARGETS:
        package_command.extend(["--platform", target])
    package_command.extend([
        "--expectations", str(expectations),
        "--output-dir", str(dist),
        "--zip",
    ])
    for command in (
        package_command,
        [
            python,
            str(ROOT / "scripts" / "sanitize_release_archive.py"),
            str(dist / "storm-deepresearch-skill.zip"),
            "--redact-root",
            str(ROOT),
            "--exclude-prefix",
            "storm-deepresearch-skill/output/",
            "--exclude-name",
            ".DS_Store",
        ],
        [
            python,
            str(yao),
            "package-verify",
            str(ROOT),
            "--package-dir", str(dist),
            "--expectations", str(expectations),
            "--registry-json", str(ROOT / "reports" / "registry_audit.json"),
            "--output-json", str(dist / "package_verification.json"),
            "--output-md", str(dist / "package_verification.md"),
            "--require-zip",
        ],
    ):
        code = run(command)
        if code:
            return code
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--package", type=Path)
    mode.add_argument("--dist", action="store_true")
    args = parser.parse_args()
    if args.package:
        return run([project_python(), str(ROOT / "scripts" / "validate_package.py"), str(args.package)])
    if args.dist:
        return run_dist()
    return run_all()


if __name__ == "__main__":
    raise SystemExit(main())
