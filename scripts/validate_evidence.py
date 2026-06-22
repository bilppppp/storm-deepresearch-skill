#!/usr/bin/env python3
"""Enforce Claim, source, snapshot, premise, and outline closure."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contract_io import (
    load_json,
    load_jsonl,
    validate_claim_record,
    validate_retrieval_evidence,
    validate_source_record,
)


SCRIPT_INTERFACE = "internal-worker-cli"
SCRIPT_INTERFACE_REASON = "Deterministic evidence closure used by the governed evidence stage."
CLOSED_STATUSES = {"supported", "qualified", "contested"}


def validate_claim_closure(
    claims: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    report_outline: dict[str, Any],
    retrieval_manifests: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    source_by_id: dict[str, dict[str, Any]] = {}
    for source in sources:
        source_id = str(source.get("source_id", ""))
        if source_id in source_by_id:
            errors.append(f"duplicate source_id {source_id}")
        source_by_id[source_id] = source
        errors.extend(f"source {source_id}: {item}" for item in validate_source_record(source))

    manifest_by_source: dict[str, dict[str, Any]] = {}
    for manifest in retrieval_manifests:
        source_id = str(manifest.get("source_id", ""))
        if source_id in manifest_by_source:
            errors.append(f"duplicate retrieval manifest source_id {source_id}")
        manifest_by_source[source_id] = manifest
        errors.extend(
            f"retrieval manifest {source_id}: {item}"
            for item in validate_retrieval_evidence(manifest)
        )
        source = source_by_id.get(source_id)
        if source and source.get("content_hash") != manifest.get("snapshot_sha256"):
            errors.append(f"source {source_id} content hash does not match retrieval snapshot")

    claim_by_id: dict[str, dict[str, Any]] = {}
    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        if claim_id in claim_by_id:
            errors.append(f"duplicate claim_id {claim_id}")
        claim_by_id[claim_id] = claim

    mapped_ids: set[str] = set()
    sections = report_outline.get("sections", [])
    if not isinstance(sections, list):
        errors.append("report outline sections must be an array")
        sections = []
    for section in sections:
        if not isinstance(section, dict):
            errors.append("report outline section must be an object")
            continue
        for claim_id in section.get("claim_ids", []):
            mapped_ids.add(str(claim_id))
            if str(claim_id) not in claim_by_id:
                errors.append(f"report outline references unknown claim_id {claim_id}")

    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        errors.extend(f"claim {claim_id}: {item}" for item in validate_claim_record(claim))
        for premise_id in claim.get("premise_claim_ids", []):
            premise = claim_by_id.get(str(premise_id))
            if premise is None:
                errors.append(f"claim {claim_id} references unknown premise claim {premise_id}")
            elif premise_id == claim_id:
                errors.append(f"claim {claim_id} cannot use itself as a premise")
            elif premise.get("status") not in CLOSED_STATUSES:
                errors.append(f"claim {claim_id} premise {premise_id} is not supported")
        related = [
            *claim.get("supporting_source_ids", []),
            *claim.get("contradicting_source_ids", []),
        ]
        for source_id in related:
            if source_id not in source_by_id:
                errors.append(f"claim {claim_id} references unknown source_id {source_id}")
        if claim.get("material") and claim_id not in mapped_ids:
            errors.append(f"material claim {claim_id} is not mapped to report outline")
        if claim.get("material") and claim.get("status") == "unsupported":
            errors.append(f"unsupported material claim {claim_id} cannot enter the report")
        if claim.get("status") == "contested" and not claim.get("contradicting_source_ids"):
            errors.append(f"claim {claim_id}: contested claim requires contradicting evidence")
        if claim.get("freshness_required"):
            for source_id in claim.get("supporting_source_ids", []):
                source = source_by_id.get(source_id)
                if source and source.get("freshness_status") != "current":
                    errors.append(
                        f"claim {claim_id} requires current evidence but {source_id} "
                        f"is {source.get('freshness_status')}"
                    )
        locators = {
            str(locator.get("source_id")): locator
            for locator in claim.get("evidence_locators", [])
            if isinstance(locator, dict)
        }
        for source_id in claim.get("supporting_source_ids", []):
            if source_id not in source_by_id:
                continue
            locator = locators.get(source_id)
            if locator is None:
                errors.append(f"claim {claim_id} lacks an evidence locator for {source_id}")
                continue
            manifest = manifest_by_source.get(source_id)
            if manifest is None:
                errors.append(f"claim {claim_id} has no retrieval manifest for {source_id}")
                continue
            if locator.get("snapshot_sha256") != manifest.get("snapshot_sha256"):
                errors.append(f"claim {claim_id} locator snapshot hash mismatch for {source_id}")
            if str(locator.get("excerpt", "")).strip() not in str(manifest.get("excerpt", "")):
                errors.append(f"claim {claim_id} locator excerpt is not bound to {source_id}")
    return list(dict.fromkeys(errors))


def compute_coverage(claims: list[dict[str, Any]]) -> dict[str, float | int]:
    material = [claim for claim in claims if claim.get("material")]
    material_facts = [claim for claim in material if claim.get("claim_type") == "fact"]
    closed_facts = [
        claim for claim in material_facts
        if claim.get("status") in CLOSED_STATUSES and claim.get("supporting_source_ids")
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
        "unsupported_material_claims": sum(
            1 for claim in material if claim.get("status") == "unsupported"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_root", type=Path)
    args = parser.parse_args()
    research = args.artifact_root / "research"
    claims = load_jsonl(research / "claim-evidence-ledger.jsonl")
    sources = load_jsonl(research / "source-register.jsonl")
    outline = load_json(research / "report-outline.json")
    manifests = load_jsonl(research / "retrieval-manifest.jsonl")
    errors = validate_claim_closure(claims, sources, outline, manifests)
    print(json.dumps({"ok": not errors, "errors": errors, "coverage": compute_coverage(claims)}, ensure_ascii=False, indent=2))
    return 0 if not errors else 5


if __name__ == "__main__":
    raise SystemExit(main())
