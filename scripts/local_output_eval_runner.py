#!/usr/bin/env python3
"""Exercise Yao's deterministic runner contract without claiming model execution."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / 4)) if text else 0


def run_single_request(request: dict[str, object]) -> dict[str, object]:
    prompt = str(request.get("prompt", ""))
    output = str(request.get("fixture_output", ""))
    input_tokens = estimate_tokens(prompt)
    output_tokens = estimate_tokens(output)
    return {
        "output": output,
        "execution_kind": "command",
        "provider": "local-deterministic-fixture",
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "estimated": True,
        },
    }


def load_cases(path: Path) -> list[dict[str, object]]:
    cases = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected JSON object")
        cases.append(value)
    return cases


def run_batch(cases_path: Path, out_dir: Path, timeout: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = load_cases(cases_path)
    summary = {
        "schema_version": "2.0",
        "case_count": len(cases),
        "passed": 0,
        "failed": 0,
        "timed_out": 0,
        "cases": [],
    }
    for case in cases:
        case_id = str(case.get("id", "case")).replace("/", "_")
        request = {
            "prompt": case.get("prompt", ""),
            "fixture_output": case.get("with_skill_output", ""),
        }
        result_path = out_dir / f"{case_id}.result.json"
        log_path = out_dir / f"{case_id}.log"
        try:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve())],
                input=json.dumps(request, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            log_path.write_text(result.stderr, encoding="utf-8")
            status = "passed" if result.returncode == 0 else "failed"
            payload = json.loads(result.stdout) if result.stdout.strip() else {}
            result_path.write_text(json.dumps({
                "case_id": case_id,
                "status": status,
                "returncode": result.returncode,
                "payload": payload,
            }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            summary[status] += 1
        except subprocess.TimeoutExpired as exc:
            status = "timed_out"
            log_path.write_text(str(exc), encoding="utf-8")
            result_path.write_text(json.dumps({
                "case_id": case_id,
                "status": status,
                "returncode": None,
                "payload": {},
            }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            summary["timed_out"] += 1
        summary["cases"].append({
            "case_id": case_id,
            "status": status,
            "result": result_path.name,
            "log": log_path.name,
        })
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["failed"] == 0 and summary["timed_out"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-jsonl", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    if args.cases_jsonl:
        if args.out_dir is None:
            print("--cases-jsonl requires --out-dir", file=sys.stderr)
            return 2
        return run_batch(args.cases_jsonl, args.out_dir, args.timeout)
    try:
        request = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(f"invalid JSON request: {exc}", file=sys.stderr)
        return 2
    if not isinstance(request, dict):
        print("runner request must be a JSON object", file=sys.stderr)
        return 2
    print(json.dumps(run_single_request(request), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
