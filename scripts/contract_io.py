#!/usr/bin/env python3
"""Load and validate the canonical research package contracts."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Shared contract loading and validation functions imported by package CLIs."


class ContractError(ValueError):
    """Raised when a contract file cannot be decoded safely."""


BRIEF_FIELDS = {
    "schema_version", "package_state", "topic", "research_question", "user_goal", "audience",
    "decision_context", "depth_level", "geography", "timeframe", "source_policy",
    "freshness_policy", "retrieval_mode", "output_mode", "uncertainty_tolerance",
    "report_language", "length_contract", "user_materials", "assumptions",
}
RESEARCH_PLAN_FIELDS = {
    "schema_version", "status", "perspectives", "questions", "source_priorities",
    "stopping_conditions", "retrieval_budget", "report_outline",
}
QUESTION_FIELDS = {
    "question_id", "perspective", "text", "status", "claim_ids", "disposition_note",
}
OUTLINE_FIELDS = {"status", "unit", "minimum", "target", "maximum", "sections"}
OUTLINE_SECTION_FIELDS = {
    "section_id", "title", "purpose", "target_units", "question_ids", "claim_ids",
    "required_elements",
}
REQUIRED_ELEMENTS = {
    "claim", "mechanism", "evidence", "counterevidence", "example", "implication",
    "limitation", "change_condition",
}
SOURCE_FIELDS = {
    "source_id", "title", "author_or_org", "canonical_url", "file_ref", "published_at",
    "retrieved_at", "source_type", "primary_class", "reliability_tier", "freshness_status",
    "reliability_notes", "content_hash",
}
CLAIM_FIELDS = {
    "claim_id", "claim_text", "claim_type", "material", "supporting_source_ids",
    "contradicting_source_ids", "evidence_locators", "evidence_strength", "confidence",
    "freshness_required", "reasoning_note", "tradeoffs", "limitation", "change_condition", "status",
}
PACKAGE_STATES = {
    "initialized", "planned", "retrieving", "evidence_ready", "drafted", "reviewed", "rendered",
    "validated", "released", "blocked_input", "blocked_retrieval", "bounded_partial", "validation_failed",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"{path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"{path}: expected a JSON object")
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ContractError(f"{path}: {exc}") from exc
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContractError(f"{path.name}:{line_number}: {exc.msg}") from exc
        if not isinstance(record, dict):
            raise ContractError(f"{path.name}:{line_number}: expected a JSON object")
        records.append(record)
    return records


def _unknown_fields(data: dict[str, Any], allowed: set[str]) -> list[str]:
    unknown = sorted(set(data) - allowed)
    return [f"unknown fields: {', '.join(unknown)}"] if unknown else []


def _missing_fields(data: dict[str, Any], required: set[str]) -> list[str]:
    missing = sorted(required - set(data))
    return [f"missing fields: {', '.join(missing)}"] if missing else []


def _valid_iso_date(value: object) -> bool:
    try:
        date.fromisoformat(str(value))
    except ValueError:
        return False
    return True


def _valid_iso_datetime(value: object) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def validate_brief(data: dict[str, Any]) -> list[str]:
    errors = _unknown_fields(data, BRIEF_FIELDS) + _missing_fields(data, BRIEF_FIELDS)
    if data.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if data.get("package_state") not in PACKAGE_STATES:
        errors.append("package_state is invalid")
    for field in ("topic", "research_question", "user_goal", "audience", "geography", "timeframe"):
        if not isinstance(data.get(field), str) or not str(data.get(field)).strip():
            errors.append(f"{field} must be a non-empty string")
    if data.get("depth_level") not in {"briefing", "standard_report", "full_dossier"}:
        errors.append("depth_level is invalid")
    if not isinstance(data.get("report_language"), str) or len(str(data.get("report_language", "")).strip()) < 2:
        errors.append("report_language must be a language tag")
    length_contract = data.get("length_contract")
    if not isinstance(length_contract, dict):
        errors.append("length_contract must be an object")
    else:
        expected = {"unit", "minimum", "target", "maximum", "content_standard"}
        if set(length_contract) != expected:
            errors.append("length_contract has invalid fields")
        if length_contract.get("unit") not in {"characters", "words"}:
            errors.append("length_contract.unit is invalid")
        values = [length_contract.get(key) for key in ("minimum", "target", "maximum")]
        if not all(isinstance(value, int) and value > 0 for value in values):
            errors.append("length_contract sizes must be positive integers")
        elif not values[0] <= values[1] <= values[2]:
            errors.append("length_contract must satisfy minimum <= target <= maximum")
        if length_contract.get("content_standard") != "evidence_led":
            errors.append("length_contract.content_standard must be evidence_led")
    if data.get("source_policy") not in {"external_allowed", "closed_corpus", "primary_only"}:
        errors.append("source_policy is invalid")
    if data.get("retrieval_mode") not in {"host", "provider", "closed_corpus"}:
        errors.append("retrieval_mode is invalid")
    if data.get("output_mode") not in {"full", "reduced"}:
        errors.append("output_mode is invalid")
    if data.get("uncertainty_tolerance") not in {"low", "medium", "high"}:
        errors.append("uncertainty_tolerance is invalid")
    freshness = data.get("freshness_policy")
    if not isinstance(freshness, dict):
        errors.append("freshness_policy must be an object")
    else:
        if set(freshness) != {"as_of", "max_age_days"}:
            errors.append("freshness_policy requires only as_of and max_age_days")
        if not _valid_iso_date(freshness.get("as_of")):
            errors.append("freshness_policy.as_of must be an ISO date")
        if not isinstance(freshness.get("max_age_days"), int) or freshness.get("max_age_days", -1) < 0:
            errors.append("freshness_policy.max_age_days must be a non-negative integer")
    for field in ("user_materials", "assumptions"):
        if not isinstance(data.get(field), list) or not all(isinstance(item, str) for item in data.get(field, [])):
            errors.append(f"{field} must be an array of strings")
    return errors


def validate_research_plan(
    data: dict[str, Any], brief: dict[str, Any], known_claim_ids: set[str]
) -> list[str]:
    errors = _unknown_fields(data, RESEARCH_PLAN_FIELDS) + _missing_fields(data, RESEARCH_PLAN_FIELDS)
    if data.get("schema_version") != "1.0":
        errors.append("research plan schema_version must be 1.0")
    if data.get("status") not in {"initialized", "planned", "complete"}:
        errors.append("research plan status is invalid")
    perspectives = data.get("perspectives")
    if not isinstance(perspectives, list) or not all(isinstance(item, str) and item.strip() for item in perspectives):
        errors.append("perspectives must be an array of non-empty strings")
    for field in ("source_priorities", "stopping_conditions"):
        value = data.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append(f"{field} must be an array of strings")
    budget = data.get("retrieval_budget")
    if not isinstance(budget, dict) or set(budget) != {"max_queries", "max_sources"}:
        errors.append("retrieval_budget requires only max_queries and max_sources")
    elif not all(isinstance(budget.get(key), int) and budget[key] > 0 for key in budget):
        errors.append("retrieval_budget values must be positive integers")

    questions = data.get("questions")
    question_ids: set[str] = set()
    answered_ids: set[str] = set()
    if not isinstance(questions, list):
        errors.append("questions must be an array")
        questions = []
    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            errors.append(f"question {index} must be an object")
            continue
        errors.extend(f"question {index}: {item}" for item in _unknown_fields(question, QUESTION_FIELDS))
        errors.extend(f"question {index}: {item}" for item in _missing_fields(question, QUESTION_FIELDS))
        question_id = str(question.get("question_id", ""))
        if not re.fullmatch(r"Q\d{3}", question_id):
            errors.append(f"question {index}: question_id must match Q followed by three digits")
        elif question_id in question_ids:
            errors.append(f"duplicate question_id {question_id}")
        question_ids.add(question_id)
        if not str(question.get("perspective", "")).strip() or not str(question.get("text", "")).strip():
            errors.append(f"question {question_id}: perspective and text are required")
        status = question.get("status")
        if status not in {"planned", "answered", "unresolved", "out_of_scope"}:
            errors.append(f"question {question_id}: status is invalid")
        claim_ids = question.get("claim_ids")
        if not isinstance(claim_ids, list) or not all(re.fullmatch(r"C\d{3}", str(item)) for item in claim_ids):
            errors.append(f"question {question_id}: claim_ids must contain stable claim IDs")
            claim_ids = []
        for claim_id in claim_ids:
            if claim_id not in known_claim_ids:
                errors.append(f"question {question_id} references unknown claim_id {claim_id}")
        if status == "answered":
            answered_ids.add(question_id)
            if not claim_ids:
                errors.append(f"answered question {question_id} requires claim_ids")
        if status in {"unresolved", "out_of_scope"} and not str(question.get("disposition_note", "")).strip():
            errors.append(f"question {question_id} requires a disposition_note")

    outline = data.get("report_outline")
    used_question_ids: set[str] = set()
    if not isinstance(outline, dict):
        errors.append("report_outline must be an object")
        return errors
    errors.extend(f"report_outline: {item}" for item in _unknown_fields(outline, OUTLINE_FIELDS))
    errors.extend(f"report_outline: {item}" for item in _missing_fields(outline, OUTLINE_FIELDS))
    if outline.get("status") not in {"initialized", "planned", "complete"}:
        errors.append("report_outline.status is invalid")
    length_contract = brief.get("length_contract", {}) if isinstance(brief.get("length_contract"), dict) else {}
    for field in ("unit", "minimum", "target", "maximum"):
        if outline.get(field) != length_contract.get(field):
            errors.append(f"report_outline.{field} must match brief.length_contract.{field}")
    sections = outline.get("sections")
    if not isinstance(sections, list):
        errors.append("report_outline.sections must be an array")
        sections = []
    section_ids: set[str] = set()
    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            errors.append(f"outline section {index} must be an object")
            continue
        errors.extend(f"outline section {index}: {item}" for item in _unknown_fields(section, OUTLINE_SECTION_FIELDS))
        errors.extend(f"outline section {index}: {item}" for item in _missing_fields(section, OUTLINE_SECTION_FIELDS))
        section_id = str(section.get("section_id", ""))
        if not re.fullmatch(r"SEC\d{2}", section_id):
            errors.append(f"outline section {index}: section_id must match SEC followed by two digits")
        elif section_id in section_ids:
            errors.append(f"duplicate outline section_id {section_id}")
        section_ids.add(section_id)
        if not str(section.get("title", "")).strip() or not str(section.get("purpose", "")).strip():
            errors.append(f"outline section {section_id}: title and purpose are required")
        if not isinstance(section.get("target_units"), int) or section.get("target_units", 0) < 1:
            errors.append(f"outline section {section_id}: target_units must be positive")
        section_question_ids = section.get("question_ids")
        if not isinstance(section_question_ids, list) or not all(re.fullmatch(r"Q\d{3}", str(item)) for item in section_question_ids):
            errors.append(f"outline section {section_id}: question_ids must contain stable question IDs")
            section_question_ids = []
        for question_id in section_question_ids:
            if question_id not in question_ids:
                errors.append(f"outline section {section_id} references unknown question_id {question_id}")
            used_question_ids.add(question_id)
        section_claim_ids = section.get("claim_ids")
        if not isinstance(section_claim_ids, list) or not all(re.fullmatch(r"C\d{3}", str(item)) for item in section_claim_ids):
            errors.append(f"outline section {section_id}: claim_ids must contain stable claim IDs")
            section_claim_ids = []
        for claim_id in section_claim_ids:
            if claim_id not in known_claim_ids:
                errors.append(f"outline section {section_id} references unknown claim_id {claim_id}")
        elements = section.get("required_elements")
        if not isinstance(elements, list) or len(set(elements)) < 3 or not set(elements) <= REQUIRED_ELEMENTS:
            errors.append(f"outline section {section_id}: required_elements must contain at least three valid elements")
    for question_id in sorted(answered_ids - used_question_ids):
        errors.append(f"answered question {question_id} is not used by report_outline")
    return errors


def validate_source_record(data: dict[str, Any]) -> list[str]:
    errors = _unknown_fields(data, SOURCE_FIELDS) + _missing_fields(data, SOURCE_FIELDS)
    if not re.fullmatch(r"S\d{3}", str(data.get("source_id", ""))):
        errors.append("source_id must match S followed by three digits")
    if not str(data.get("canonical_url", "")).strip() and not str(data.get("file_ref", "")).strip():
        errors.append("source requires canonical_url or file_ref")
    for field in ("title", "author_or_org", "source_type"):
        if not isinstance(data.get(field), str) or not str(data.get(field)).strip():
            errors.append(f"{field} must be a non-empty string")
    if data.get("primary_class") not in {"primary", "secondary"}:
        errors.append("primary_class is invalid")
    if data.get("reliability_tier") not in {"A", "B", "C", "D"}:
        errors.append("reliability_tier is invalid")
    if data.get("freshness_status") not in {"current", "stale", "historical", "unknown"}:
        errors.append("freshness_status is invalid")
    if not _valid_iso_datetime(data.get("retrieved_at")):
        errors.append("retrieved_at must be an ISO datetime")
    return errors


def validate_claim_record(data: dict[str, Any]) -> list[str]:
    errors = _unknown_fields(data, CLAIM_FIELDS) + _missing_fields(data, CLAIM_FIELDS)
    if not re.fullmatch(r"C\d{3}", str(data.get("claim_id", ""))):
        errors.append("claim_id must match C followed by three digits")
    claim_type = data.get("claim_type")
    support = data.get("supporting_source_ids")
    contradict = data.get("contradicting_source_ids")
    if claim_type not in {"fact", "inference", "recommendation"}:
        errors.append("claim_type is invalid")
    if not isinstance(support, list) or not all(re.fullmatch(r"S\d{3}", str(item)) for item in support):
        errors.append("supporting_source_ids must contain stable source IDs")
        support = []
    if not isinstance(contradict, list) or not all(re.fullmatch(r"S\d{3}", str(item)) for item in contradict):
        errors.append("contradicting_source_ids must contain stable source IDs")
    if claim_type == "fact" and not support and data.get("status") not in {"unsupported", "out_of_scope"}:
        errors.append("fact requires supporting evidence")
    if claim_type in {"inference", "recommendation"} and not str(data.get("reasoning_note", "")).strip():
        errors.append(f"{claim_type} requires a reasoning_note")
    if claim_type == "recommendation" and not data.get("tradeoffs"):
        errors.append("recommendation requires tradeoffs")
    if data.get("status") not in {"supported", "qualified", "contested", "unsupported", "out_of_scope"}:
        errors.append("status is invalid")
    if data.get("evidence_strength") not in {"strong", "medium", "weak", "unknown"}:
        errors.append("evidence_strength is invalid")
    if data.get("confidence") not in {"high", "medium", "low"}:
        errors.append("confidence is invalid")
    if not isinstance(data.get("material"), bool):
        errors.append("material must be boolean")
    if not isinstance(data.get("freshness_required"), bool):
        errors.append("freshness_required must be boolean")
    if not isinstance(data.get("evidence_locators"), list):
        errors.append("evidence_locators must be an array")
    return errors


def validate_research_package(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        brief = load_json(root / "brief.json")
        plan = load_json(root / "research" / "research-plan.json")
        sources = load_jsonl(root / "research" / "source-register.jsonl")
        claims = load_jsonl(root / "research" / "claim-evidence-ledger.jsonl")
        report_map = load_json(root / "research" / "report-claim-map.json")
    except ContractError as exc:
        return [str(exc)]
    errors.extend(f"brief: {item}" for item in validate_brief(brief))
    source_ids: set[str] = set()
    for index, source in enumerate(sources, start=1):
        errors.extend(f"source record {index}: {item}" for item in validate_source_record(source))
        source_id = str(source.get("source_id", ""))
        if source_id in source_ids:
            errors.append(f"duplicate source_id {source_id}")
        source_ids.add(source_id)
    claim_ids: set[str] = set()
    for index, claim in enumerate(claims, start=1):
        errors.extend(f"claim record {index}: {item}" for item in validate_claim_record(claim))
        claim_id = str(claim.get("claim_id", ""))
        if claim_id in claim_ids:
            errors.append(f"duplicate claim_id {claim_id}")
        claim_ids.add(claim_id)
        for source_id in [*claim.get("supporting_source_ids", []), *claim.get("contradicting_source_ids", [])]:
            if source_id not in source_ids:
                errors.append(f"claim {claim_id} references unknown source_id {source_id}")
    errors.extend(f"research plan: {item}" for item in validate_research_plan(plan, brief, claim_ids))
    if set(report_map) != {"schema_version", "mappings"} or report_map.get("schema_version") != "1.0":
        errors.append("report-claim-map has invalid top-level contract")
    if not isinstance(report_map.get("mappings"), list):
        errors.append("report-claim-map.mappings must be an array")
    else:
        for mapping in report_map["mappings"]:
            for claim_id in mapping.get("claim_ids", []) if isinstance(mapping, dict) else []:
                if claim_id not in claim_ids:
                    errors.append(f"report map references unknown claim_id {claim_id}")
    return errors
