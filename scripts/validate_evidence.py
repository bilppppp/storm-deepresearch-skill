#!/usr/bin/env python3
"""Enforce claim-evidence closure and freshness rules."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .contract_io import load_json, load_jsonl, validate_claim_record, validate_source_record
except ImportError:
    from contract_io import load_json, load_jsonl, validate_claim_record, validate_source_record


def validate_claim_closure(
    claims: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    report_claim_map: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    source_by_id = {str(source.get("source_id")): source for source in sources}
    claim_by_id = {str(claim.get("claim_id")): claim for claim in claims}
    for source in sources:
        source_id = str(source.get("source_id", ""))
        errors.extend(f"source {source_id}: {item}" for item in validate_source_record(source))
    mapped_ids: set[str] = set()
    mappings = report_claim_map.get("mappings", [])
    if not isinstance(mappings, list):
        errors.append("report claim map mappings must be an array")
        mappings = []
    for mapping in mappings:
        if not isinstance(mapping, dict):
            errors.append("report claim mapping must be an object")
            continue
        if set(mapping) != {"anchor", "fingerprint", "claim_ids"}:
            errors.append("report claim mapping has invalid fields")
        if not str(mapping.get("anchor", "")).strip() or not str(mapping.get("fingerprint", "")).strip():
            errors.append("report claim mapping requires anchor and fingerprint")
        for claim_id in mapping.get("claim_ids", []):
            mapped_ids.add(str(claim_id))
            if str(claim_id) not in claim_by_id:
                errors.append(f"report map references unknown claim_id {claim_id}")
    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        errors.extend(f"claim {claim_id}: {item}" for item in validate_claim_record(claim))
        related = [*claim.get("supporting_source_ids", []), *claim.get("contradicting_source_ids", [])]
        for source_id in related:
            if source_id not in source_by_id:
                errors.append(f"claim {claim_id} references unknown source_id {source_id}")
        if claim.get("material") and claim_id not in mapped_ids:
            errors.append(f"material claim {claim_id} is not mapped to public report text")
        if claim.get("material") and claim.get("status") == "unsupported":
            errors.append(f"unsupported material claim {claim_id} cannot be released")
        if claim.get("status") == "contested" and not claim.get("contradicting_source_ids"):
            errors.append(f"claim {claim_id}: contested claim requires contradicting evidence")
        if claim.get("freshness_required"):
            for source_id in claim.get("supporting_source_ids", []):
                source = source_by_id.get(source_id)
                if source and source.get("freshness_status") != "current":
                    errors.append(f"claim {claim_id} requires current evidence but {source_id} is {source.get('freshness_status')}")
        locator_ids = {
            str(locator.get("source_id"))
            for locator in claim.get("evidence_locators", [])
            if isinstance(locator, dict)
        }
        for source_id in claim.get("supporting_source_ids", []):
            if source_id in source_by_id and source_id not in locator_ids:
                errors.append(f"claim {claim_id} lacks an evidence locator for {source_id}")
    return errors


def compute_coverage(claims: list[dict[str, Any]]) -> dict[str, float | int]:
    material = [claim for claim in claims if claim.get("material")]
    material_facts = [claim for claim in material if claim.get("claim_type") == "fact"]
    closed_facts = [
        claim for claim in material_facts
        if claim.get("status") in {"supported", "qualified", "contested"} and claim.get("supporting_source_ids")
    ]
    contested = [claim for claim in claims if claim.get("status") == "contested"]
    disclosed = [claim for claim in contested if claim.get("contradicting_source_ids")]
    freshness = [claim for claim in claims if claim.get("freshness_required")]
    return {
        "material_claims": len(material),
        "material_facts": len(material_facts),
        "material_fact_closure": len(closed_facts) / len(material_facts) if material_facts else 1.0,
        "contested_claim_disclosure": len(disclosed) / len(contested) if contested else 1.0,
        "freshness_required_claims": len(freshness),
        "unsupported_material_claims": sum(1 for claim in material if claim.get("status") == "unsupported"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    research = args.output_dir / "research"
    claims = load_jsonl(research / "claim-evidence-ledger.jsonl")
    sources = load_jsonl(research / "source-register.jsonl")
    report_map = load_json(research / "report-claim-map.json")
    errors = validate_claim_closure(claims, sources, report_map)
    print(json.dumps({"ok": not errors, "errors": errors, "coverage": compute_coverage(claims)}, ensure_ascii=False, indent=2))
    return 0 if not errors else 5


if __name__ == "__main__":
    raise SystemExit(main())
