#!/usr/bin/env python3
"""Compile-check and run host-generated Python runners with a hard timeout."""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path


SCRIPT_INTERFACE = "cli"
SCRIPT_INTERFACE_REASON = (
    "Host agents may generate orchestration runners; this guard fails fast on "
    "syntax corruption and kills long-running children instead of hiding output."
)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_TIMEOUT = 124


def compile_check(runner: Path) -> int:
    try:
        source = runner.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        print(f"RUNNER_SYNTAX_ERROR: {runner}: not valid UTF-8: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as exc:
        print(f"RUNNER_SYNTAX_ERROR: {runner}: cannot read runner: {exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        compile(source, str(runner), "exec")
    except SyntaxError as exc:
        location = f"{runner}:{exc.lineno}:{exc.offset or 0}"
        print(f"RUNNER_SYNTAX_ERROR: {location}: {exc.msg}", file=sys.stderr)
        if exc.text:
            print(exc.text.rstrip(), file=sys.stderr)
            if exc.offset:
                print(" " * max(exc.offset - 1, 0) + "^", file=sys.stderr)
        return EXIT_USAGE
    return EXIT_OK


def terminate_process(process: subprocess.Popen[object]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=2)
    except Exception:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except Exception:
            pass


def run_guarded(args: argparse.Namespace) -> int:
    runner = args.runner.resolve()
    if not runner.is_file():
        print(f"RUNNER_SYNTAX_ERROR: runner does not exist: {runner}", file=sys.stderr)
        return EXIT_USAGE

    code = compile_check(runner)
    if code:
        return code

    command = [str(args.python), str(runner), *args.runner_args]
    print(f"RUNNER_START: {' '.join(command)}", flush=True)
    process = subprocess.Popen(
        command,
        cwd=args.cwd or runner.parent,
        start_new_session=(os.name == "posix"),
    )
    try:
        return process.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        terminate_process(process)
        print(
            f"RUNNER_TIMEOUT: {runner} exceeded {args.timeout:g}s and was terminated",
            file=sys.stderr,
            flush=True,
        )
        return EXIT_TIMEOUT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runner", type=Path, help="Host-generated Python runner to execute.")
    parser.add_argument("runner_args", nargs=argparse.REMAINDER, help="Arguments passed to the runner.")
    parser.add_argument("--python", default=sys.executable, help="Python executable for the runner.")
    parser.add_argument("--cwd", type=Path, help="Working directory for the runner. Defaults to runner parent.")
    parser.add_argument("--timeout", type=float, default=1800.0, help="Hard timeout in seconds.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_guarded(args)


if __name__ == "__main__":
    raise SystemExit(main())
