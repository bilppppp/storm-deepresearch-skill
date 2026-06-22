#!/usr/bin/env python3
"""Render human-readable audit views from canonical ledgers."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from .contract_io import load_json, load_jsonl
    from .output_paths import OutputPathError, package_child, resolve_package_dir
except ImportError:
    from contract_io import load_json, load_jsonl
    from output_paths import OutputPathError, package_child, resolve_package_dir


def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def render(root: Path) -> None:
    root = resolve_package_dir(root)
    sources = load_jsonl(package_child(root, "research/source-register.jsonl"))
    claims = load_jsonl(package_child(root, "research/claim-evidence-ledger.jsonl"))
    conflicts = load_json(package_child(root, "research/contradiction-ledger.json")).get("conflicts", [])
    source_lines = ["# Source Register", "", "| ID | Title | Organization | Published | Retrieved | Type | Tier | Location | Freshness |", "|---|---|---|---|---|---|---|---|---|"]
    for source in sources:
        location = source.get("canonical_url") or source.get("file_ref")
        source_lines.append("| " + " | ".join(cell(source.get(key, "")) for key in ("source_id", "title", "author_or_org", "published_at", "retrieved_at", "source_type", "reliability_tier")) + f" | {cell(location)} | {cell(source.get('freshness_status', ''))} |")
    if not sources:
        source_lines.extend(["", "No sources registered."])
    source_view = package_child(root, "research/source-register.md")
    source_view.write_text("\n".join(source_lines) + "\n", encoding="utf-8")
    claim_lines = ["# Evidence Map", "", "| Claim | Type | Status | Supports | Contradicts | Strength | Confidence | Limitation |", "|---|---|---|---|---|---|---|---|"]
    for claim in claims:
        values = (
            claim.get("claim_text", ""), claim.get("claim_type", ""), claim.get("status", ""),
            ", ".join(claim.get("supporting_source_ids", [])), ", ".join(claim.get("contradicting_source_ids", [])),
            claim.get("evidence_strength", ""), claim.get("confidence", ""), claim.get("limitation", ""),
        )
        claim_lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    if not claims:
        claim_lines.extend(["", "No claims registered."])
    evidence_view = package_child(root, "research/evidence-map.md")
    evidence_view.write_text("\n".join(claim_lines) + "\n", encoding="utf-8")
    conflict_lines = ["# Contradiction Map", ""]
    for conflict in conflicts:
        conflict_lines.extend([
            f"## {cell(conflict.get('conflict_id', 'Conflict'))}", "",
            f"- Claims: {cell(', '.join(conflict.get('claim_ids', [])))}",
            f"- Cause: {cell(conflict.get('cause', ''))}",
            f"- Resolution evidence: {cell(conflict.get('resolution_evidence', ''))}",
            f"- Current judgment: {cell(conflict.get('judgment', ''))}", "",
        ])
    if not conflicts:
        conflict_lines.append("No conflicts assessed.")
    contradiction_view = package_child(root, "research/contradiction-map.md")
    contradiction_view.write_text("\n".join(conflict_lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        render(args.output_dir)
    except OutputPathError as exc:
        print(f"Unsafe research package path: {exc}", file=sys.stderr)
        return 7
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
