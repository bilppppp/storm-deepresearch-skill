#!/usr/bin/env python3
"""Enforce Claim, source, snapshot, premise, and outline closure."""
from __future__ import annotations

import argparse
import json
import re
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
from scripts.source_evidence import ACADEMIC_SOURCE_TYPES


SCRIPT_INTERFACE = "internal-worker-cli"
SCRIPT_INTERFACE_REASON = "Deterministic evidence closure used by the governed evidence stage."
CLOSED_STATUSES = {"supported", "qualified", "contested"}
STRENGTH_RANK = {"unknown": 0, "background": 0, "weak": 1, "medium": 2, "strong": 3}
ABSENCE_CLAIM_RE = re.compile(
    r"(?:\b(?:no|none|without|not\s+found|lack(?:s|ing)?)\s+(?:human|clinical|evidence|trials?|stud(?:y|ies)|records?|data)\b|未发现|尚无|没有.{0,8}(?:证据|试验|研究|数据)|不存在)",
    re.IGNORECASE,
)


def validate_absence_searches(
    claims: list[dict[str, Any]],
    searches: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    retrieval_manifests: list[dict[str, Any]],
    brief: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    source_ids = {str(item.get("source_id")) for item in sources}
    manifest_pairs = {
        (str(item.get("source_id")), str(item.get("query_id")))
        for item in retrieval_manifests
    }
    by_id: dict[str, dict[str, Any]] = {}
    for index, search in enumerate(searches, start=1):
        fields = {"schema_version", "search_id", "claim_id", "scope", "aliases", "queries", "conclusion", "limitations"}
        if not isinstance(search, dict) or set(search) != fields:
            errors.append(f"absence search {index} has invalid fields")
            continue
        search_id = str(search.get("search_id", ""))
        if not re.fullmatch(r"AS\d{3}", search_id) or search_id in by_id:
            errors.append(f"absence search {index} has invalid or duplicate search_id")
        by_id[search_id] = search
        aliases = search.get("aliases")
        queries = search.get("queries")
        if not isinstance(aliases, list) or not aliases or not all(isinstance(item, str) and item.strip() for item in aliases):
            errors.append(f"absence search {search_id} requires aliases")
            aliases = []
        if not isinstance(queries, list) or not queries:
            errors.append(f"absence search {search_id} requires queries")
            queries = []
        surface_classes: set[str] = set()
        surfaces: set[str] = set()
        for query_index, query in enumerate(queries, start=1):
            query_fields = {"query_id", "alias", "surface", "surface_class", "source_id", "result_count", "searched_at"}
            if not isinstance(query, dict) or set(query) != query_fields:
                errors.append(f"absence search {search_id} query {query_index} has invalid fields")
                continue
            source_id = str(query.get("source_id", ""))
            query_id = str(query.get("query_id", ""))
            if source_id not in source_ids or (source_id, query_id) not in manifest_pairs:
                errors.append(f"absence search {search_id} query {query_index} is not bound to retrieval evidence")
            if query.get("alias") not in aliases:
                errors.append(f"absence search {search_id} query {query_index} uses an unregistered alias")
            if not isinstance(query.get("result_count"), int) or int(query.get("result_count", -1)) < 0:
                errors.append(f"absence search {search_id} query {query_index} result_count is invalid")
            if not str(query.get("searched_at", "")).strip():
                errors.append(f"absence search {search_id} query {query_index} searched_at is required")
            surface_classes.add(str(query.get("surface_class", "")))
            surfaces.add(str(query.get("surface", "")))
        if search.get("scope") == "closed_corpus":
            if brief.get("retrieval_mode") != "closed_corpus" or surface_classes - {"closed_corpus"}:
                errors.append(f"absence search {search_id} has invalid closed-corpus scope")
        else:
            if brief.get("retrieval_mode") == "closed_corpus":
                errors.append(f"absence search {search_id} cannot claim external absence in closed corpus mode")
            if brief.get("depth_level") == "full_dossier" and len(surfaces) < 2:
                errors.append(f"absence search {search_id} requires two independent discovery surfaces")
            if brief.get("high_stakes"):
                if len(set(aliases)) < 3:
                    errors.append(f"high-stakes absence search {search_id} requires at least three aliases")
                if not {"trial_registry", "bibliographic_database"} <= surface_classes:
                    errors.append(f"high-stakes absence search {search_id} requires trial registry and bibliographic database")
        for field in ("conclusion", "limitations"):
            if not str(search.get(field, "")).strip():
                errors.append(f"absence search {search_id} requires {field}")
    for claim in claims:
        if not claim.get("material"):
            continue
        claim_id = str(claim.get("claim_id", ""))
        mode = claim.get("evidence_mode")
        suspicious = bool(ABSENCE_CLAIM_RE.search(str(claim.get("claim_text", ""))))
        if suspicious and mode != "absence_search":
            errors.append(f"material claim {claim_id} uses absence language without absence_search evidence_mode")
        if mode == "absence_search":
            search_id = str(claim.get("absence_search_id", ""))
            search = by_id.get(search_id)
            if search is None:
                errors.append(f"claim {claim_id} lacks absence search {search_id}")
            elif search.get("claim_id") != claim_id:
                errors.append(f"absence search {search_id} is bound to the wrong claim")
    used_ids = {str(claim.get("absence_search_id")) for claim in claims if claim.get("evidence_mode") == "absence_search"}
    unused = sorted(set(by_id) - used_ids)
    if unused:
        errors.append("unreferenced absence searches: " + ", ".join(unused))
    return list(dict.fromkeys(errors))


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

    manifests_by_source: dict[str, list[dict[str, Any]]] = {}
    for manifest in retrieval_manifests:
        source_id = str(manifest.get("source_id", ""))
        manifests_by_source.setdefault(source_id, []).append(manifest)
        errors.extend(
            f"retrieval manifest {source_id}: {item}"
            for item in validate_retrieval_evidence(manifest)
        )
    candidate_by_source: dict[str, str] = {}
    for source_id, source in source_by_id.items():
        source_manifests = manifests_by_source.get(source_id, [])
        canonical_manifests = [
            item for item in source_manifests
            if source.get("content_hash") == item.get("snapshot_sha256")
        ]
        if source_manifests and not canonical_manifests:
            errors.append(f"source {source_id} content hash does not match any retrieval snapshot")
        canonical_candidates = {
            str(item.get("candidate_id")) for item in canonical_manifests
        }
        if len(canonical_candidates) == 1:
            candidate_by_source[source_id] = next(iter(canonical_candidates))
        elif len(canonical_candidates) > 1:
            errors.append(f"source {source_id} canonical snapshot spans multiple candidate versions")

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
        if claim.get("material"):
            for source_id in claim.get("supporting_source_ids", []):
                source = source_by_id.get(str(source_id))
                if not source or source.get("source_type") not in ACADEMIC_SOURCE_TYPES:
                    continue
                bibliographic = source.get("bibliographic")
                if not isinstance(bibliographic, dict) or bibliographic.get("status") != "verified":
                    errors.append(f"academic source {source_id} is not bibliographically verified")
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
            source_manifests = manifests_by_source.get(source_id, [])
            if not source_manifests:
                errors.append(f"claim {claim_id} has no retrieval manifest for {source_id}")
                continue
            matching = [
                manifest for manifest in source_manifests
                if locator.get("snapshot_sha256") == manifest.get("snapshot_sha256")
                and str(locator.get("excerpt", "")).strip() in str(manifest.get("excerpt", ""))
            ]
            if not matching:
                errors.append(f"claim {claim_id} locator snapshot hash mismatch for {source_id}")
                errors.append(f"claim {claim_id} locator excerpt is not bound to {source_id}")
                continue
            expected_candidate = candidate_by_source.get(str(source_id))
            if expected_candidate and any(
                str(manifest.get("candidate_id")) != expected_candidate
                for manifest in matching
            ):
                errors.append(f"claim {claim_id} capture candidate does not match source version")
            declared = str(claim.get("evidence_strength", "unknown"))
            ceiling = max(
                (str(item.get("evidence_strength_ceiling", "background")) for item in matching),
                key=lambda item: STRENGTH_RANK.get(item, 0),
            )
            if STRENGTH_RANK.get(declared, 0) > STRENGTH_RANK.get(ceiling, 0):
                errors.append(
                    f"claim {claim_id} evidence strength {declared} exceeds capture ceiling {ceiling}"
                )
        if claim.get("claim_type") in {"inference", "recommendation"} and claim.get("premise_claim_ids"):
            premise_strengths = [
                str(claim_by_id[str(item)].get("evidence_strength", "unknown"))
                for item in claim.get("premise_claim_ids", [])
                if str(item) in claim_by_id
            ]
            if premise_strengths:
                weakest = min(premise_strengths, key=lambda item: STRENGTH_RANK.get(item, 0))
                declared = str(claim.get("evidence_strength", "unknown"))
                if STRENGTH_RANK.get(declared, 0) > STRENGTH_RANK.get(weakest, 0):
                    errors.append(
                        f"claim {claim_id} evidence strength {declared} exceeds weakest premise {weakest}"
                    )
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
