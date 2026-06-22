#!/usr/bin/env python3
"""Exercise Yao's deterministic runner contract without claiming model execution."""
from __future__ import annotations

import argparse
import json
import sys


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / 4)) if text else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        request = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(f"invalid JSON request: {exc}", file=sys.stderr)
        return 2
    if not isinstance(request, dict):
        print("runner request must be a JSON object", file=sys.stderr)
        return 2
    prompt = str(request.get("prompt", ""))
    output = str(request.get("fixture_output", ""))
    input_tokens = estimate_tokens(prompt)
    output_tokens = estimate_tokens(output)
    print(json.dumps({
        "output": output,
        "execution_kind": "command",
        "provider": "local-deterministic-fixture",
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "estimated": True,
        },
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
