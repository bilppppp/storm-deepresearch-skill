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

from scripts.contract_io import validate_retrieval_input_record, validate_source_record
from scripts.harness_io import atomic_write_text, canonical_json_bytes
from scripts.source_evidence import (
    ACADEMIC_SOURCE_TYPES,
    SourceEvidenceError,
    canonicalize_public_url,
    capture_retrieval_evidence,
    validate_audit_snapshot,
    validate_candidate_snapshots,
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


def derive_bibliographic_status(candidate: dict[str, object]) -> str:
    outcomes = [
        item for item in candidate.get("resolver_outcomes", [])
        if isinstance(item, dict)
    ]
    if any(
        item.get("status") == "matched" and item.get("metadata_match") is False
        for item in outcomes
    ):
        return "conflicted"
    identifier_match = any(
        item.get("status") == "matched"
        and item.get("metadata_match") is True
        and item.get("query_basis") in {"doi", "pmid", "arxiv_id"}
        for item in outcomes
    )
    metadata_matches = {
        str(item.get("resolver"))
        for item in outcomes
        if item.get("status") == "matched" and item.get("metadata_match") is True
    }
    if identifier_match or len(metadata_matches) >= 2:
        return "verified"
    return "unverified"


def validate_version_families(candidates: list[dict[str, object]]) -> list[str]:
    families: dict[str, list[dict[str, object]]] = {}
    for candidate in candidates:
        family_id = candidate.get("version_family_id")
        if family_id:
            families.setdefault(str(family_id), []).append(candidate)
    errors: list[str] = []
    for family_id, members in families.items():
        if len(members) < 2:
            continue
        if any(item.get("relationship_basis") == "unresolved" for item in members):
            errors.append(f"{family_id} contains an unresolved version relationship")
    return errors


def independent_source_identity(source: dict[str, object]) -> str:
    bibliographic = source.get("bibliographic")
    if isinstance(bibliographic, dict) and bibliographic.get("version_family_id"):
        return f"family:{bibliographic['version_family_id']}"
    return f"source:{source_identity(source)}"


def _source_from_capture(
    source_id: str,
    adapter_record: dict[str, Any],
    captured: dict[str, object],
    candidate: dict[str, object],
) -> dict[str, object]:
    authors = candidate.get("authors")
    author_or_org = "; ".join(str(item) for item in authors) if isinstance(authors, list) else ""
    if not author_or_org:
        author_or_org = str(adapter_record.get("publisher", "")).strip()
    bibliographic: dict[str, object] | None = None
    if captured.get("source_type") in ACADEMIC_SOURCE_TYPES:
        bibliographic = {
            "identifiers": dict(candidate.get("identifiers", {})),
            "status": derive_bibliographic_status(candidate),
            "version_family_id": candidate.get("version_family_id"),
            "version_role": candidate.get("version_role") or "other",
        }
    source = {
        "source_id": source_id,
        "title": str(adapter_record.get("title", "")).strip(),
        "author_or_org": author_or_org,
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
        "bibliographic": bibliographic,
    }
    errors = validate_source_record(source)
    if errors:
        raise ValueError("invalid source record: " + "; ".join(errors))
    return source


def normalize_retrieval_records(
    records: list[dict[str, object]], *, mode: str, cache_root: Path
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """Return source, capture manifest, and audit records after validation."""
    if mode not in ALLOWED_MODES:
        raise ValueError(f"unknown retrieval mode: {mode}")
    search_runs: dict[str, dict[str, object]] = {}
    candidates: dict[str, dict[str, object]] = {}
    capture_inputs: list[dict[str, object]] = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"retrieval record {index} must be an object")
        contract_errors = validate_retrieval_input_record(record)
        if contract_errors:
            raise ValueError(f"retrieval record {index} is invalid: {'; '.join(contract_errors)}")
        adapter = str(record.get("adapter", ""))
        if adapter != mode:
            raise ValueError(f"adapter {adapter or '<missing>'} is not allowed in {mode} mode")
        kind = record.get("record_kind")
        if kind == "search_run":
            search_run_id = str(record["search_run_id"])
            if search_run_id in search_runs:
                raise ValueError(f"duplicate search_run_id {search_run_id}")
            snapshot_errors = validate_audit_snapshot(record, cache_root)
            if snapshot_errors:
                raise ValueError(f"search run {search_run_id}: {'; '.join(snapshot_errors)}")
            search_runs[search_run_id] = record
        elif kind == "candidate":
            candidate_id = str(record["candidate_id"])
            if candidate_id in candidates:
                raise ValueError(f"duplicate candidate_id {candidate_id}")
            snapshot_errors = validate_candidate_snapshots(record, cache_root)
            if snapshot_errors:
                raise ValueError(f"candidate {candidate_id}: {'; '.join(snapshot_errors)}")
            candidates[candidate_id] = record
        else:
            capture_inputs.append(record)

    family_errors = validate_version_families(list(candidates.values()))
    if family_errors:
        raise ValueError("; ".join(family_errors))
    for candidate_id, candidate in candidates.items():
        unknown = sorted(set(candidate["search_run_ids"]) - set(search_runs))
        if unknown:
            raise ValueError(f"candidate {candidate_id} references unknown search runs: {', '.join(unknown)}")

    by_identity: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = {}
    captured_candidate_ids: set[str] = set()
    for record in capture_inputs:
        candidate_id = str(record["candidate_id"])
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise ValueError(f"capture refers to unknown candidate {candidate_id}")
        if candidate.get("disposition") != "include":
            raise ValueError(f"capture refers to {candidate.get('disposition')} candidate {candidate_id}")
        run_ids = set(record["search_run_ids"])
        unknown = sorted(run_ids - set(search_runs))
        if unknown:
            raise ValueError(f"capture {candidate_id} references unknown search runs: {', '.join(unknown)}")
        query_id = str(record["query_id"])
        if not any(search_runs[run_id].get("query_id") == query_id for run_id in run_ids):
            raise ValueError(f"capture {candidate_id} query_id is not bound to its search runs")
        captured = capture_retrieval_evidence(record, cache_root)
        identity = f"candidate:{candidate_id}"
        by_identity.setdefault(identity, []).append((record, captured))
        captured_candidate_ids.add(candidate_id)

    missing_captures = sorted(
        candidate_id
        for candidate_id, candidate in candidates.items()
        if candidate.get("disposition") == "include" and candidate_id not in captured_candidate_ids
    )
    if missing_captures:
        raise ValueError("included candidates lack captures: " + ", ".join(missing_captures))

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
        candidate = candidates[str(canonical_manifest["candidate_id"])]
        sources.append(_source_from_capture(source_id, adapter_record, canonical_manifest, candidate))
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
    audit = [search_runs[key] for key in sorted(search_runs)] + [
        candidates[key] for key in sorted(candidates)
    ]
    return sources, manifests, audit


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
        sources, manifests, audit = normalize_retrieval_records(
            records, mode=args.mode, cache_root=args.cache_root
        )
        if args.output_dir.exists() or args.output_dir.is_symlink():
            raise ValueError(f"output directory already exists: {args.output_dir}")
        args.output_dir.mkdir(parents=True, exist_ok=False)
        atomic_write_text(args.output_dir / "source-records.jsonl", _jsonl(sources))
        atomic_write_text(args.output_dir / "retrieval-manifest.jsonl", _jsonl(manifests))
        atomic_write_text(args.output_dir / "retrieval-audit.jsonl", _jsonl(audit))
    except (OSError, json.JSONDecodeError, SourceEvidenceError, ValueError) as exc:
        print(f"Retrieval normalization failed: {exc}", file=sys.stderr)
        return 4
    print(f"Normalized {len(sources)} source records into {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
