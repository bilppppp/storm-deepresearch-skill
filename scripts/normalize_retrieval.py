#!/usr/bin/env python3
"""Normalize captured adapter records without committing authoritative run state."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contract_io import validate_source_record
from scripts.harness_io import atomic_write_text, canonical_json_bytes
from scripts.source_evidence import (
    SourceEvidenceError,
    canonicalize_public_url,
    capture_retrieval_evidence,
)


SCRIPT_INTERFACE = "internal-worker-cli"
SCRIPT_INTERFACE_REASON = "Produces validated staging records; only storm_research may commit receipts."
ALLOWED_MODES = {"host", "provider", "closed_corpus"}


def canonicalize_url(value: str) -> str:
    return canonicalize_public_url(value)


def source_identity(record: dict[str, Any]) -> str:
    identity = record.get("canonical_url") or record.get("file_ref")
    if not isinstance(identity, str) or not identity:
        raise ValueError("source record has no canonical URL or file reference")
    return identity


def _source_from_capture(
    source_id: str, adapter_record: dict[str, Any], captured: dict[str, object]
) -> dict[str, object]:
    source = {
        "source_id": source_id,
        "title": str(adapter_record.get("title", "")).strip(),
        "author_or_org": str(adapter_record.get("publisher", "")).strip(),
        "canonical_url": captured["canonical_url"],
        "file_ref": captured["file_ref"],
        "published_at": captured["published_at"],
        "publication_date_status": captured["publication_date_status"],
        "retrieved_at": captured["retrieved_at"],
        "source_type": captured["source_type"],
        "primary_class": captured["primary_class"],
        "reliability_tier": captured["reliability_tier"],
        "freshness_status": str(adapter_record.get("freshness_status", "unknown")),
        "reliability_notes": captured["reliability_notes"],
        "content_hash": captured["snapshot_sha256"],
    }
    errors = validate_source_record(source)
    if errors:
        raise ValueError("invalid source record: " + "; ".join(errors))
    return source


def normalize_retrieval_records(
    records: list[dict[str, object]], *, mode: str, cache_root: Path
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return source and manifest records after deterministic evidence validation."""
    if mode not in ALLOWED_MODES:
        raise ValueError(f"unknown retrieval mode: {mode}")
    by_identity: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = {}
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"retrieval record {index} must be an object")
        adapter = str(record.get("adapter", ""))
        if adapter != mode:
            raise ValueError(f"adapter {adapter or '<missing>'} is not allowed in {mode} mode")
        captured = capture_retrieval_evidence(record, cache_root)
        identity = source_identity(captured)
        by_identity.setdefault(identity, []).append((record, captured))
    sources: list[dict[str, object]] = []
    manifests: list[dict[str, object]] = []
    for index, identity in enumerate(sorted(by_identity), start=1):
        captures = by_identity[identity]
        adapter_record, captured = max(
            captures, key=lambda item: str(item[1].get("retrieved_at", ""))
        )
        source_id = f"S{index:03d}"
        canonical_manifest = dict(captured)
        canonical_manifest["source_id"] = source_id
        sources.append(_source_from_capture(source_id, adapter_record, canonical_manifest))
        seen: set[tuple[str, str, str, str]] = set()
        for _record, item in sorted(
            captures,
            key=lambda pair: (
                str(pair[1].get("query_id", "")),
                str(pair[1].get("snapshot_sha256", "")),
                str(pair[1].get("locator", "")),
            ),
        ):
            identity_key = (
                str(item.get("query_id", "")),
                str(item.get("snapshot_sha256", "")),
                str(item.get("locator", "")),
                str(item.get("excerpt_sha256", "")),
            )
            if identity_key in seen:
                continue
            seen.add(identity_key)
            manifest = dict(item)
            manifest["source_id"] = source_id
            manifests.append(manifest)
    return sources, manifests


def source_record(record: dict[str, Any], source_id: str) -> dict[str, Any]:
    result = dict(record)
    result["source_id"] = source_id
    return result


def merge_source_ledger(
    existing_sources: list[dict[str, Any]], incoming_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge sources monotonically while preserving every existing source ID."""
    output: list[dict[str, Any]] = []
    index_by_identity: dict[str, int] = {}
    used_ids: set[str] = set()
    maximum_id = 0
    for source in existing_sources:
        source_id = str(source.get("source_id", ""))
        if not re.fullmatch(r"S\d{3}", source_id) or source_id in used_ids:
            raise ValueError(f"existing source ledger has invalid or duplicate ID: {source_id or '<missing>'}")
        identity = source_identity(source)
        if identity in index_by_identity:
            raise ValueError(f"existing source ledger has duplicate identity: {identity}")
        errors = validate_source_record(source)
        if errors:
            raise ValueError(f"existing source {source_id} is invalid: {'; '.join(errors)}")
        used_ids.add(source_id)
        maximum_id = max(maximum_id, int(source_id[1:]))
        index_by_identity[identity] = len(output)
        output.append(dict(source))

    incoming_by_identity: dict[str, dict[str, Any]] = {}
    for record in incoming_records:
        identity = source_identity(record)
        current = incoming_by_identity.get(identity)
        if current is None or str(record.get("retrieved_at", "")) > str(current.get("retrieved_at", "")):
            incoming_by_identity[identity] = record

    for identity in sorted(incoming_by_identity):
        record = incoming_by_identity[identity]
        existing_index = index_by_identity.get(identity)
        if existing_index is not None:
            existing = output[existing_index]
            if str(record.get("retrieved_at", "")) > str(existing.get("retrieved_at", "")):
                output[existing_index] = source_record(record, str(existing["source_id"]))
            continue
        if maximum_id >= 999:
            raise ValueError("source ledger exhausted the S001-S999 ID range")
        maximum_id += 1
        output.append(source_record(record, f"S{maximum_id:03d}"))
    return output


def merge_source_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return merge_source_ledger([], records)


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"line {line_number} is not a JSON object")
        records.append(payload)
    return records


def _jsonl(records: list[dict[str, object]]) -> str:
    return b"".join(canonical_json_bytes(record) for record in records).decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_jsonl", type=Path)
    parser.add_argument("--mode", choices=sorted(ALLOWED_MODES), required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        records = _load_jsonl(args.input_jsonl)
        sources, manifests = normalize_retrieval_records(
            records, mode=args.mode, cache_root=args.cache_root
        )
        if args.output_dir.exists() or args.output_dir.is_symlink():
            raise ValueError(f"output directory already exists: {args.output_dir}")
        args.output_dir.mkdir(parents=True, exist_ok=False)
        atomic_write_text(args.output_dir / "source-records.jsonl", _jsonl(sources))
        atomic_write_text(args.output_dir / "retrieval-manifest.jsonl", _jsonl(manifests))
    except (OSError, json.JSONDecodeError, SourceEvidenceError, ValueError) as exc:
        print(f"Retrieval normalization failed: {exc}", file=sys.stderr)
        return 4
    print(f"Normalized {len(sources)} source records into {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
