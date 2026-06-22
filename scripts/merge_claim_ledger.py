#!/usr/bin/env python3
"""Merge full claim records without deleting existing ledger entries."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from .contract_io import ContractError, load_jsonl, validate_claim_record
    from .output_paths import OutputPathError, package_child, resolve_package_dir
except ImportError:
    from contract_io import ContractError, load_jsonl, validate_claim_record
    from output_paths import OutputPathError, package_child, resolve_package_dir


def merge_claim_records(
    existing_claims: list[dict[str, Any]],
    incoming_claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    index_by_id: dict[str, int] = {}
    for label, claims in (("existing", existing_claims), ("incoming", incoming_claims)):
        seen_in_batch: set[str] = set()
        for claim in claims:
            errors = validate_claim_record(claim)
            if errors:
                raise ValueError(f"{label} claim is invalid: {'; '.join(errors)}")
            claim_id = str(claim["claim_id"])
            if claim_id in seen_in_batch:
                raise ValueError(f"{label} claim ledger contains duplicate ID: {claim_id}")
            seen_in_batch.add(claim_id)
            if label == "existing":
                index_by_id[claim_id] = len(output)
                output.append(dict(claim))
                continue
            existing_index = index_by_id.get(claim_id)
            if existing_index is None:
                index_by_id[claim_id] = len(output)
                output.append(dict(claim))
            else:
                output[existing_index] = dict(claim)
    return output


def atomic_write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_jsonl", type=Path, help="Full new or revised claim records.")
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    try:
        package = resolve_package_dir(args.package)
        ledger = package_child(package, "research/claim-evidence-ledger.jsonl")
        if not ledger.is_file():
            raise ValueError("claim ledger is missing; initialize the research package first")
        incoming = load_jsonl(args.input_jsonl)
        existing = load_jsonl(ledger)
        merged = merge_claim_records(existing, incoming)
        atomic_write_jsonl(ledger, merged)
    except (ContractError, OSError, OutputPathError, ValueError) as exc:
        print(f"Claim ledger merge failed: {exc}", file=sys.stderr)
        return 4
    print(f"Merged {len(merged)} claim records into {ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
