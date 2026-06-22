#!/usr/bin/env python3
"""Normalize adapter output into deterministic source records."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    from .output_paths import OutputPathError, package_child, resolve_package_dir
except ImportError:
    from output_paths import OutputPathError, package_child, resolve_package_dir


TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
ALLOWED_MODES = {"host", "provider", "closed_corpus"}


def canonicalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("url must be absolute HTTP or HTTPS")
    host = parsed.hostname.lower()
    if parsed.port:
        host = f"{host}:{parsed.port}"
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_KEYS
    ]
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or "/", urlencode(sorted(query)), ""))


def normalize_retrieval_record(record: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode not in ALLOWED_MODES:
        raise ValueError(f"unknown retrieval mode: {mode}")
    url = str(record.get("url", "")).strip()
    file_ref = str(record.get("file_ref", "")).strip()
    if not url and not file_ref:
        raise ValueError("retrieval record requires url or file_ref")
    adapter = str(record.get("adapter", ""))
    if adapter != mode:
        raise ValueError(f"adapter {adapter or '<missing>'} is not allowed in {mode} mode")
    required = ("query_id", "title", "publisher", "retrieved_at", "content_excerpt", "content_locator")
    missing = [field for field in required if not str(record.get(field, "")).strip()]
    if missing:
        raise ValueError(f"retrieval record missing: {', '.join(missing)}")
    try:
        datetime.fromisoformat(str(record["retrieved_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("retrieved_at must be an ISO datetime") from exc
    if file_ref and Path(file_ref).is_absolute():
        raise ValueError("file_ref must be relative to the approved corpus root")
    raw_artifact = record.get("raw_artifact")
    if isinstance(raw_artifact, str) and Path(raw_artifact).is_absolute():
        raise ValueError("raw_artifact must be relative")
    return {
        "query_id": str(record["query_id"]),
        "canonical_url": canonicalize_url(url) if url else "",
        "file_ref": file_ref,
        "title": str(record["title"]).strip(),
        "author_or_org": str(record["publisher"]).strip(),
        "published_at": str(record.get("published_at", "")),
        "retrieved_at": str(record["retrieved_at"]),
        "content_excerpt": str(record["content_excerpt"]).strip(),
        "content_locator": str(record["content_locator"]).strip(),
        "adapter": adapter,
        "source_type": str(record.get("source_type", "web")),
        "primary_class": str(record.get("primary_class", "secondary")),
        "reliability_tier": str(record.get("reliability_tier", "C")),
        "freshness_status": str(record.get("freshness_status", "unknown")),
        "reliability_notes": str(record.get("reliability_notes", "")),
        "content_hash": str(record.get("content_hash", "")),
    }


def merge_source_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_identity: dict[str, dict[str, Any]] = {}
    for record in records:
        identity = str(record.get("canonical_url") or record.get("file_ref") or "")
        if not identity:
            raise ValueError("normalized retrieval record has no identity")
        existing = by_identity.get(identity)
        if existing is None or str(record.get("retrieved_at", "")) > str(existing.get("retrieved_at", "")):
            by_identity[identity] = record
    output = []
    for index, identity in enumerate(sorted(by_identity), start=1):
        record = by_identity[identity]
        output.append({
            "source_id": f"S{index:03d}",
            "title": record["title"],
            "author_or_org": record["author_or_org"],
            "canonical_url": record.get("canonical_url", ""),
            "file_ref": record.get("file_ref", ""),
            "published_at": record.get("published_at", ""),
            "retrieved_at": record["retrieved_at"],
            "source_type": record.get("source_type", "web"),
            "primary_class": record.get("primary_class", "secondary"),
            "reliability_tier": record.get("reliability_tier", "C"),
            "freshness_status": record.get("freshness_status", "unknown"),
            "reliability_notes": record.get("reliability_notes", ""),
            "content_hash": record.get("content_hash", ""),
        })
    return output


def source_identity(record: dict[str, Any]) -> str:
    identity = str(record.get("canonical_url") or record.get("file_ref") or "")
    if not identity:
        raise ValueError("source record has no canonical URL or file reference")
    return identity


def source_record(record: dict[str, Any], source_id: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "title": record["title"],
        "author_or_org": record["author_or_org"],
        "canonical_url": record.get("canonical_url", ""),
        "file_ref": record.get("file_ref", ""),
        "published_at": record.get("published_at", ""),
        "retrieved_at": record["retrieved_at"],
        "source_type": record.get("source_type", "web"),
        "primary_class": record.get("primary_class", "secondary"),
        "reliability_tier": record.get("reliability_tier", "C"),
        "freshness_status": record.get("freshness_status", "unknown"),
        "reliability_notes": record.get("reliability_notes", ""),
        "content_hash": record.get("content_hash", ""),
    }


def merge_source_ledger(
    existing_sources: list[dict[str, Any]],
    incoming_records: list[dict[str, Any]],
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
        new_source = source_record(record, f"S{maximum_id:03d}")
        index_by_identity[identity] = len(output)
        output.append(new_source)
    return output


def load_existing_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"existing source ledger line {line_number} is not a JSON object")
        records.append(payload)
    return records


def atomic_write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    parser.add_argument("input_jsonl", type=Path)
    parser.add_argument("--mode", choices=sorted(ALLOWED_MODES), required=True)
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    try:
        records = []
        for line_number, raw in enumerate(args.input_jsonl.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number} is not a JSON object")
            records.append(normalize_retrieval_record(payload, args.mode))
        package = resolve_package_dir(args.package)
        output = package_child(package, "research/source-register.jsonl")
        if not output.is_file():
            raise ValueError("source register is missing; initialize the research package first")
        existing = load_existing_ledger(output)
        sources = merge_source_ledger(existing, records)
        atomic_write_jsonl(output, sources)
    except (OSError, json.JSONDecodeError, OutputPathError, ValueError) as exc:
        print(f"Retrieval normalization failed: {exc}", file=sys.stderr)
        return 4
    print(f"Merged {len(sources)} source records into {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
