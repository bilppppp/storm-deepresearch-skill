#!/usr/bin/env python3
"""Validate and merge full Claim records without committing run authority."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contract_io import ContractError, load_jsonl, validate_claim_record
from scripts.harness_io import atomic_write_text, canonical_json_bytes


SCRIPT_INTERFACE = "internal-worker-cli"
SCRIPT_INTERFACE_REASON = "Returns a merged Claim set; only storm_research may commit stage receipts."


def merge_claim_records(
    existing_claims: list[dict[str, Any]], incoming_claims: list[dict[str, Any]]
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


def _jsonl(records: list[dict[str, Any]]) -> str:
    return b"".join(canonical_json_bytes(record) for record in records).decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_jsonl", type=Path, help="Full new or revised Claim records.")
    parser.add_argument("--existing-jsonl", type=Path)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    args = parser.parse_args()
    try:
        incoming = load_jsonl(args.input_jsonl)
        existing = load_jsonl(args.existing_jsonl) if args.existing_jsonl else []
        merged = merge_claim_records(existing, incoming)
        if args.output_jsonl.exists() or args.output_jsonl.is_symlink():
            raise ValueError(f"output already exists: {args.output_jsonl}")
        atomic_write_text(args.output_jsonl, _jsonl(merged))
    except (ContractError, OSError, ValueError) as exc:
        print(f"Claim ledger merge failed: {exc}", file=sys.stderr)
        return 4
    print(f"Merged {len(merged)} Claim records into {args.output_jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
