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


BRIEF_REQUIRED_FIELDS = {
    "schema_version", "topic", "research_question", "user_goal", "audience",
    "research_profile", "profile_selection", "depth_level", "geography", "timeframe", "source_policy",
    "freshness_policy", "retrieval_mode", "output_mode", "uncertainty_tolerance",
    "report_language", "length_contract", "storm_lens_mode", "high_stakes", "user_materials", "assumptions",
}
RESEARCH_PROFILES = {
    "default_full_dossier", "strict_storm_lens", "critique_deepresearch",
    "closed_corpus", "briefing", "custom",
}
PROFILE_SELECTION_MODES = {"user_selected", "user_requested_default", "defaulted_after_prompt"}
PROFILE_SELECTION_FIELDS = {"mode", "selected_profile", "evidence", "available_profiles"}
BRIEF_FIELDS = BRIEF_REQUIRED_FIELDS | {"briefing_reason"}
RESEARCH_PLAN_FIELDS = {
    "schema_version", "status", "perspectives", "questions", "source_priorities",
    "stopping_conditions", "retrieval_budget",
}
QUESTION_FIELDS = {
    "question_id", "perspective", "text", "status", "claim_ids", "disposition_note",
}
OUTLINE_FIELDS = {"schema_version", "status", "unit", "minimum", "target", "maximum", "sections"}
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
    "publication_date_status", "retrieved_at", "source_type", "primary_class",
    "reliability_tier", "freshness_status", "reliability_notes", "content_hash",
}
CLAIM_FIELDS = {
    "schema_version", "claim_id", "claim_text", "claim_type", "material", "premise_claim_ids", "supporting_source_ids",
    "contradicting_source_ids", "evidence_locators", "evidence_strength", "confidence",
    "freshness_required", "reasoning_note", "conditions", "tradeoffs", "limitation", "change_condition", "status",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}")
STAGES = {"init", "plan", "retrieval", "evidence", "draft", "review", "render", "validation", "release"}
RECEIPT_FIELDS = {
    "schema_version", "run_id", "generation", "stage", "status",
    "previous_receipt_sha256", "skill_package_sha256", "validator_sha256",
    "input_artifacts", "output_artifacts", "checks", "completed_at", "receipt_sha256",
}
AMENDMENT_FIELDS = {
    "schema_version", "run_id", "from_generation", "to_generation", "changes",
    "initiator", "user_approval_evidence", "invalidation_start_stage", "created_at",
    "amendment_sha256",
}
SOURCE_PLAN_FIELDS = {"schema_version", "questions", "source_classes", "stopping_conditions", "exclusions"}
RETRIEVAL_EVIDENCE_FIELDS = {
    "schema_version", "source_id", "query_id", "canonical_url", "final_url", "file_ref",
    "observed_status", "content_type", "retrieved_at", "adapter", "adapter_run_id",
    "capture_level", "evidence_strength_ceiling", "snapshot_ref", "snapshot_sha256", "normalized_text_sha256",
    "locator_type", "locator", "excerpt", "excerpt_sha256", "published_at",
    "publication_date_status", "source_type", "primary_class", "reliability_tier",
    "reliability_notes",
}
PARAGRAPH_MAP_FIELDS = {
    "schema_version", "paragraph_sha256", "paragraph_type", "claim_ids", "source_ids",
    "citation_keys", "text_locator",
}
SEMANTIC_REVIEW_FIELDS = {
    "schema_version", "review_id", "review_type", "author_run_id", "reviewer_run_id",
    "independent", "target_kind", "target_id", "target_sha256", "material", "verdict",
    "reason", "allowable_scope", "required_action", "findings", "reviewed_at",
}
TASKLET_FIELDS = {
    "schema_version", "tasklet_id", "question_id", "perspective", "question",
    "evidence_need", "required_source_classes", "status", "output_contract",
}
FINDING_LOCATOR_FIELDS = {"source_id", "locator", "excerpt", "snapshot_sha256"}
FINDING_FIELDS = {
    "schema_version", "finding_id", "tasklet_id", "question_id", "summary",
    "source_ids", "evidence_locators", "claim_ids", "status", "confidence",
    "limitations", "produced_by", "created_at",
}
CONFLICT_REVIEW_FIELDS = {
    "schema_version", "review_id", "author_run_id", "reviewer_run_id",
    "independent", "target_kind", "target_id", "target_sha256", "verdict",
    "reason", "required_action", "reviewed_at",
}
HUMAN_APPROVAL_FIELDS = {
    "schema_version", "approval_id", "reviewer", "scope", "decision", "reason",
    "approved_artifact_sha256", "reviewed_at", "expires_at",
}
REVERIFICATION_FIELDS = {
    "schema_version", "source_id", "canonical_url", "checked_at", "status",
    "observed_status", "content_sha256", "reason",
}
RELEASE_MANIFEST_FIELDS = {
    "schema_version", "run_id", "generation", "release_created_at",
    "validation_receipt_sha256", "skill_package_sha256", "trust_report_sha256",
    "registry_metadata_sha256", "human_approval_sha256", "reverification_summary", "files",
}
GOVERNED_TRUST_FIELDS = {
    "schema_version", "status", "skill_package_sha256", "registry_package_sha256",
    "yao_trust_report", "yao_trust_report_sha256", "skill_directory_read_only",
    "registry_read_only", "trust_report_read_only", "verified_by", "verified_at",
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


def _is_sha256(value: object, *, allow_empty: bool = False) -> bool:
    return bool((allow_empty and value == "") or SHA256_RE.fullmatch(str(value)))


def _strict_record(data: dict[str, Any], fields: set[str]) -> list[str]:
    errors = _unknown_fields(data, fields) + _missing_fields(data, fields)
    if data.get("schema_version") != "2.0":
        errors.append("schema_version must be 2.0")
    return errors


def _validate_hash_map(value: object, field: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{field} must be an object"]
    if not all(isinstance(path, str) and path and _is_sha256(digest) for path, digest in value.items()):
        return [f"{field} must map paths to SHA-256 values"]
    return []


def validate_brief(data: dict[str, Any]) -> list[str]:
    errors = _unknown_fields(data, BRIEF_FIELDS) + _missing_fields(data, BRIEF_REQUIRED_FIELDS)
    if data.get("schema_version") != "2.0":
        errors.append("schema_version must be 2.0")
    for field in ("topic", "research_question", "user_goal", "audience", "geography", "timeframe"):
        if not isinstance(data.get(field), str) or not str(data.get(field)).strip():
            errors.append(f"{field} must be a non-empty string")
    if data.get("depth_level") not in {"briefing", "standard_report", "full_dossier"}:
        errors.append("depth_level is invalid")
    if data.get("depth_level") == "briefing":
        if not isinstance(data.get("briefing_reason"), str) or not str(data.get("briefing_reason", "")).strip():
            errors.append("briefing requires briefing_reason")
    elif "briefing_reason" in data:
        errors.append("briefing_reason is only valid for briefing depth")
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
    if data.get("depth_level") == "full_dossier" and data.get("output_mode") != "full":
        errors.append("full_dossier requires full output")
    if data.get("uncertainty_tolerance") not in {"low", "medium", "high"}:
        errors.append("uncertainty_tolerance is invalid")
    if data.get("storm_lens_mode") not in {"advisory", "strict"}:
        errors.append("storm_lens_mode is invalid")
    profile = data.get("research_profile", "custom")
    if profile not in RESEARCH_PROFILES:
        errors.append("research_profile is invalid")
    elif profile == "default_full_dossier":
        if data.get("depth_level") != "full_dossier" or data.get("output_mode") != "full":
            errors.append("default_full_dossier profile requires full_dossier and full output")
        if data.get("source_policy") != "external_allowed" or data.get("retrieval_mode") != "host":
            errors.append("default_full_dossier profile requires external_allowed host retrieval")
        if data.get("storm_lens_mode") != "strict":
            errors.append("default_full_dossier profile requires strict STORM lens")
    elif profile == "strict_storm_lens":
        if data.get("depth_level") != "full_dossier" or data.get("output_mode") != "full":
            errors.append("strict_storm_lens profile requires full_dossier and full output")
        if data.get("storm_lens_mode") != "strict":
            errors.append("strict_storm_lens profile requires strict STORM lens")
    elif profile == "critique_deepresearch":
        if data.get("depth_level") != "full_dossier" or data.get("output_mode") != "full":
            errors.append("critique_deepresearch profile requires full_dossier and full output")
        if data.get("source_policy") != "external_allowed" or data.get("retrieval_mode") != "host":
            errors.append("critique_deepresearch profile requires external_allowed host retrieval")
        if data.get("storm_lens_mode") != "strict":
            errors.append("critique_deepresearch profile requires strict STORM lens")
    elif profile == "closed_corpus":
        if data.get("source_policy") != "closed_corpus" or data.get("retrieval_mode") != "closed_corpus":
            errors.append("closed_corpus profile requires closed_corpus source policy and retrieval mode")
    elif profile == "briefing" and data.get("depth_level") != "briefing":
        errors.append("briefing profile requires briefing depth")
    selection = data.get("profile_selection")
    if not isinstance(selection, dict):
        errors.append("profile_selection must be an object")
    else:
        errors.extend(_unknown_fields(selection, PROFILE_SELECTION_FIELDS))
        errors.extend(_missing_fields(selection, PROFILE_SELECTION_FIELDS))
        if selection.get("mode") not in PROFILE_SELECTION_MODES:
            errors.append("profile_selection.mode is invalid")
        if selection.get("selected_profile") != profile:
            errors.append("profile_selection.selected_profile must match research_profile")
        if not isinstance(selection.get("evidence"), str) or not str(selection.get("evidence", "")).strip():
            errors.append("profile_selection.evidence must be a non-empty string")
        available = selection.get("available_profiles")
        if not isinstance(available, list) or not available:
            errors.append("profile_selection.available_profiles must be a non-empty array")
        elif not all(isinstance(item, str) and item in RESEARCH_PROFILES for item in available):
            errors.append("profile_selection.available_profiles contains invalid profiles")
        elif profile not in available:
            errors.append("profile_selection.available_profiles must include selected_profile")
    if not isinstance(data.get("high_stakes"), bool):
        errors.append("high_stakes must be boolean")
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
    if data.get("schema_version") != "2.0":
        errors.append("research plan schema_version must be 2.0")
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
            if not claim_ids:
                errors.append(f"answered question {question_id} requires claim_ids")
        if status in {"unresolved", "out_of_scope"} and not str(question.get("disposition_note", "")).strip():
            errors.append(f"question {question_id} requires a disposition_note")

    return errors


def validate_report_outline(
    outline: dict[str, Any],
    brief: dict[str, Any],
    known_question_ids: set[str],
    known_claim_ids: set[str],
) -> list[str]:
    errors = _unknown_fields(outline, OUTLINE_FIELDS) + _missing_fields(outline, OUTLINE_FIELDS)
    if outline.get("schema_version") != "2.0":
        errors.append("report_outline.schema_version must be 2.0")
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
            if question_id not in known_question_ids:
                errors.append(f"outline section {section_id} references unknown question_id {question_id}")
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
    return errors


def validate_source_record(data: dict[str, Any]) -> list[str]:
    errors = _unknown_fields(data, SOURCE_FIELDS) + _missing_fields(data, SOURCE_FIELDS)
    if not re.fullmatch(r"S\d{3}", str(data.get("source_id", ""))):
        errors.append("source_id must match S followed by three digits")
    if not str(data.get("canonical_url", "")).strip() and not str(data.get("file_ref", "")).strip():
        errors.append("source requires canonical_url or file_ref")
    publication_status = data.get("publication_date_status")
    published_at = data.get("published_at")
    if publication_status not in {"known", "unknown"}:
        errors.append("publication_date_status is invalid")
    elif publication_status == "known" and not _valid_iso_date(published_at):
        errors.append("known publication date requires an ISO date")
    elif publication_status == "unknown" and published_at is not None:
        errors.append("unknown publication date requires null published_at")
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
    if not _is_sha256(data.get("content_hash")):
        errors.append("content_hash must be a SHA-256 value")
    return errors


def validate_receipt(data: dict[str, Any]) -> list[str]:
    errors = _strict_record(data, RECEIPT_FIELDS)
    if not isinstance(data.get("run_id"), str) or not data.get("run_id"):
        errors.append("run_id must be a non-empty string")
    if not isinstance(data.get("generation"), int) or data.get("generation", 0) < 1:
        errors.append("generation must be a positive integer")
    if data.get("stage") not in STAGES:
        errors.append("stage is invalid")
    if data.get("status") != "passed":
        errors.append("receipt status must be passed")
    if not _is_sha256(data.get("previous_receipt_sha256"), allow_empty=True):
        errors.append("previous_receipt_sha256 must be empty or a SHA-256 value")
    for field in ("skill_package_sha256", "validator_sha256", "receipt_sha256"):
        if not _is_sha256(data.get(field)):
            errors.append(f"{field} must be a SHA-256 value")
    errors.extend(_validate_hash_map(data.get("input_artifacts"), "input_artifacts"))
    errors.extend(_validate_hash_map(data.get("output_artifacts"), "output_artifacts"))
    if not isinstance(data.get("checks"), list):
        errors.append("checks must be an array")
    if not _valid_iso_datetime(data.get("completed_at")):
        errors.append("completed_at must be an ISO datetime")
    return errors


def validate_amendment(data: dict[str, Any]) -> list[str]:
    errors = _strict_record(data, AMENDMENT_FIELDS)
    if not isinstance(data.get("run_id"), str) or not data.get("run_id"):
        errors.append("run_id must be a non-empty string")
    before, after = data.get("from_generation"), data.get("to_generation")
    if not isinstance(before, int) or not isinstance(after, int) or before < 1 or after != before + 1:
        errors.append("to_generation must immediately follow from_generation")
    changes = data.get("changes")
    required = {"field", "before", "after", "reason"}
    if not isinstance(changes, list) or not changes:
        errors.append("changes must be a non-empty array")
    else:
        for index, change in enumerate(changes, start=1):
            if not isinstance(change, dict) or set(change) != required:
                errors.append(f"change {index} has invalid fields")
            elif not str(change.get("field", "")).strip() or not str(change.get("reason", "")).strip():
                errors.append(f"change {index} requires field and reason")
    for field in ("initiator", "user_approval_evidence"):
        if not isinstance(data.get(field), str) or not data.get(field):
            errors.append(f"{field} must be a non-empty string")
    if data.get("invalidation_start_stage") not in STAGES:
        errors.append("invalidation_start_stage is invalid")
    if not _valid_iso_datetime(data.get("created_at")):
        errors.append("created_at must be an ISO datetime")
    if not _is_sha256(data.get("amendment_sha256")):
        errors.append("amendment_sha256 must be a SHA-256 value")
    return errors


def validate_source_plan(data: dict[str, Any]) -> list[str]:
    errors = _strict_record(data, SOURCE_PLAN_FIELDS)
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        errors.append("questions must be a non-empty array")
    else:
        fields = {"query_id", "question", "evidence_need", "required_source_classes"}
        for index, question in enumerate(questions, start=1):
            if not isinstance(question, dict) or set(question) != fields:
                errors.append(f"source question {index} has invalid fields")
            elif not re.fullmatch(r"Q\d{3}", str(question.get("query_id", ""))):
                errors.append(f"source question {index} has invalid query_id")
            elif not all(str(question.get(field, "")).strip() for field in ("question", "evidence_need")):
                errors.append(f"source question {index} requires question and evidence_need")
            elif not isinstance(question.get("required_source_classes"), list) or not question["required_source_classes"]:
                errors.append(f"source question {index} requires source classes")
    classes = data.get("source_classes")
    if not isinstance(classes, list) or not classes:
        errors.append("source_classes must be a non-empty array")
    else:
        fields = {"class_id", "name", "can_prove", "cannot_prove", "priority"}
        for index, source_class in enumerate(classes, start=1):
            if not isinstance(source_class, dict) or set(source_class) != fields:
                errors.append(f"source class {index} has invalid fields")
                continue
            if not all(str(source_class.get(field, "")).strip() for field in ("class_id", "name")):
                errors.append(f"source class {index} requires class_id and name")
            if not all(isinstance(source_class.get(field), list) and source_class[field] for field in ("can_prove", "cannot_prove")):
                errors.append(f"source class {index} requires proof boundaries")
            if not isinstance(source_class.get("priority"), int) or source_class["priority"] < 1:
                errors.append(f"source class {index} requires positive priority")
    for field in ("stopping_conditions", "exclusions"):
        value = data.get(field)
        if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
            errors.append(f"{field} must be a non-empty string array")
    return errors


def validate_retrieval_evidence(data: dict[str, Any]) -> list[str]:
    errors = _strict_record(data, RETRIEVAL_EVIDENCE_FIELDS)
    if not re.fullmatch(r"S\d{3}", str(data.get("source_id", ""))):
        errors.append("source_id must match S followed by three digits")
    if not re.fullmatch(r"Q\d{3}", str(data.get("query_id", ""))):
        errors.append("query_id must match Q followed by three digits")
    url = data.get("canonical_url")
    file_ref = data.get("file_ref")
    if bool(url) == bool(file_ref):
        errors.append("exactly one of canonical_url or file_ref is required")
    if url and not data.get("final_url"):
        errors.append("URL evidence requires final_url")
    observed_status = data.get("observed_status")
    if url and (not isinstance(observed_status, int) or not 100 <= observed_status <= 599):
        errors.append("URL evidence requires an HTTP observed_status")
    if file_ref and observed_status is not None:
        errors.append("file evidence requires null observed_status")
    for field in ("content_type", "adapter_run_id", "snapshot_ref", "locator_type", "locator", "excerpt", "source_type", "reliability_notes"):
        if not isinstance(data.get(field), str) or not data.get(field):
            errors.append(f"{field} must be a non-empty string")
    if data.get("adapter") not in {"host", "provider", "closed_corpus"}:
        errors.append("adapter is invalid")
    if data.get("capture_level") not in {"full_text", "official_data", "user_file", "search_snippet"}:
        errors.append("capture_level is invalid")
    if data.get("evidence_strength_ceiling") not in {"strong", "medium", "weak", "background"}:
        errors.append("evidence_strength_ceiling is invalid")
    for field in ("snapshot_sha256", "normalized_text_sha256", "excerpt_sha256"):
        if not _is_sha256(data.get(field)):
            errors.append(f"{field} must be a SHA-256 value")
    if not _valid_iso_datetime(data.get("retrieved_at")):
        errors.append("retrieved_at must be an ISO datetime")
    date_status, published_at = data.get("publication_date_status"), data.get("published_at")
    if date_status == "known" and not _valid_iso_date(published_at):
        errors.append("known publication date requires an ISO date")
    elif date_status == "unknown" and published_at is not None:
        errors.append("unknown publication date requires null published_at")
    elif date_status not in {"known", "unknown"}:
        errors.append("publication_date_status is invalid")
    if data.get("primary_class") not in {"primary", "secondary"}:
        errors.append("primary_class is invalid")
    if data.get("reliability_tier") not in {"A", "B", "C", "D"}:
        errors.append("reliability_tier is invalid")
    return errors


def validate_paragraph_map_record(data: dict[str, Any]) -> list[str]:
    errors = _strict_record(data, PARAGRAPH_MAP_FIELDS)
    if not _is_sha256(data.get("paragraph_sha256")):
        errors.append("paragraph_sha256 must be a SHA-256 value")
    paragraph_type = data.get("paragraph_type")
    if paragraph_type not in {"factual", "inference", "recommendation", "transition"}:
        errors.append("paragraph_type is invalid")
    patterns = (("claim_ids", r"C\d{3}"), ("source_ids", r"S\d{3}"))
    for field, pattern in patterns:
        value = data.get(field)
        if not isinstance(value, list) or not all(re.fullmatch(pattern, str(item)) for item in value):
            errors.append(f"{field} contains invalid IDs")
    keys = data.get("citation_keys")
    if not isinstance(keys, list) or not all(isinstance(item, str) and item for item in keys):
        errors.append("citation_keys must be a string array")
    if paragraph_type == "factual" and not all(data.get(field) for field in ("claim_ids", "source_ids", "citation_keys")):
        errors.append("factual paragraph requires claim, source, and citation mappings")
    if not isinstance(data.get("text_locator"), str) or not data.get("text_locator"):
        errors.append("text_locator must be a non-empty string")
    return errors


def validate_semantic_review_record(data: dict[str, Any]) -> list[str]:
    errors = _strict_record(data, SEMANTIC_REVIEW_FIELDS)
    if not re.fullmatch(r"REV\d{3}", str(data.get("review_id", ""))):
        errors.append("review_id is invalid")
    if data.get("review_type") not in {"claim_entailment", "report_assertion"}:
        errors.append("review_type is invalid")
    for field in ("author_run_id", "reviewer_run_id", "target_id"):
        if not isinstance(data.get(field), str) or not data.get(field):
            errors.append(f"{field} must be a non-empty string")
    if not isinstance(data.get("independent"), bool):
        errors.append("independent must be boolean")
    if data.get("author_run_id") == data.get("reviewer_run_id") or data.get("independent") is not True:
        errors.append("reviewer must be independent")
    if data.get("target_kind") not in {"claim", "paragraph"}:
        errors.append("target_kind is invalid")
    if data.get("review_type") == "claim_entailment" and data.get("target_kind") != "claim":
        errors.append("claim_entailment review must target a claim")
    if data.get("review_type") == "report_assertion" and data.get("target_kind") != "paragraph":
        errors.append("report_assertion review must target a paragraph")
    if not _is_sha256(data.get("target_sha256")):
        errors.append("target_sha256 must be a SHA-256 value")
    if data.get("verdict") not in {"supported", "overstated", "not_supported", "unclear"}:
        errors.append("verdict is invalid")
    if not isinstance(data.get("material"), bool):
        errors.append("material must be boolean")
    if not isinstance(data.get("reason"), str) or not data.get("reason"):
        errors.append("reason must be a non-empty string")
    if data.get("allowable_scope") is not None and not isinstance(data.get("allowable_scope"), str):
        errors.append("allowable_scope must be null or string")
    if data.get("required_action") not in {"none", "qualify", "remove", "rewrite", "add_evidence"}:
        errors.append("required_action is invalid")
    if data.get("verdict") != "supported" and data.get("required_action") == "none":
        errors.append("non-supported verdict requires an action")
    if not isinstance(data.get("findings"), list):
        errors.append("findings must be an array")
    if not _valid_iso_datetime(data.get("reviewed_at")):
        errors.append("reviewed_at must be an ISO datetime")
    return errors


def validate_tasklet_record(data: dict[str, Any]) -> list[str]:
    errors = _strict_record(data, TASKLET_FIELDS)
    if not re.fullmatch(r"T\d{3}", str(data.get("tasklet_id", ""))):
        errors.append("tasklet_id must match T followed by three digits")
    if not re.fullmatch(r"Q\d{3}", str(data.get("question_id", ""))):
        errors.append("question_id must match Q followed by three digits")
    for field in ("perspective", "question", "evidence_need"):
        if not isinstance(data.get(field), str) or not str(data.get(field, "")).strip():
            errors.append(f"{field} must be a non-empty string")
    if not isinstance(data.get("required_source_classes"), list) or not all(
        isinstance(item, str) and item.strip() for item in data.get("required_source_classes", [])
    ):
        errors.append("required_source_classes must be a non-empty string array")
    if data.get("status") not in {"planned", "covered", "unresolved"}:
        errors.append("tasklet status is invalid")
    if not isinstance(data.get("output_contract"), list) or not all(
        isinstance(item, str) and item.strip() for item in data.get("output_contract", [])
    ):
        errors.append("output_contract must be a non-empty string array")
    return errors


def validate_finding_record(data: dict[str, Any]) -> list[str]:
    errors = _strict_record(data, FINDING_FIELDS)
    if not re.fullmatch(r"F\d{3}", str(data.get("finding_id", ""))):
        errors.append("finding_id must match F followed by three digits")
    if not re.fullmatch(r"T\d{3}", str(data.get("tasklet_id", ""))):
        errors.append("tasklet_id must match T followed by three digits")
    if not re.fullmatch(r"Q\d{3}", str(data.get("question_id", ""))):
        errors.append("question_id must match Q followed by three digits")
    if not isinstance(data.get("summary"), str) or not str(data.get("summary", "")).strip():
        errors.append("summary must be a non-empty string")
    if not isinstance(data.get("source_ids"), list) or not all(
        re.fullmatch(r"S\d{3}", str(item)) for item in data.get("source_ids", [])
    ):
        errors.append("source_ids must contain source IDs")
    locators = data.get("evidence_locators")
    if not isinstance(locators, list):
        errors.append("evidence_locators must be an array")
    else:
        for index, locator in enumerate(locators, start=1):
            if not isinstance(locator, dict) or set(locator) != FINDING_LOCATOR_FIELDS:
                errors.append(f"finding locator {index} has invalid fields")
                continue
            if not re.fullmatch(r"S\d{3}", str(locator.get("source_id", ""))):
                errors.append(f"finding locator {index} has invalid source_id")
            if not str(locator.get("locator", "")).strip() or not str(locator.get("excerpt", "")).strip():
                errors.append(f"finding locator {index} requires locator and excerpt")
            if not _is_sha256(locator.get("snapshot_sha256")):
                errors.append(f"finding locator {index} snapshot_sha256 must be a SHA-256 value")
    if not isinstance(data.get("claim_ids"), list) or not all(
        re.fullmatch(r"C\d{3}", str(item)) for item in data.get("claim_ids", [])
    ):
        errors.append("claim_ids must contain Claim IDs")
    if data.get("status") not in {"usable", "needs_more_evidence", "rejected"}:
        errors.append("finding status is invalid")
    if data.get("confidence") not in {"high", "medium", "low"}:
        errors.append("finding confidence is invalid")
    if not isinstance(data.get("limitations"), list) or not all(
        isinstance(item, str) for item in data.get("limitations", [])
    ):
        errors.append("limitations must be a string array")
    if not isinstance(data.get("produced_by"), str) or not data.get("produced_by"):
        errors.append("produced_by must be a non-empty string")
    if not _valid_iso_datetime(data.get("created_at")):
        errors.append("created_at must be an ISO datetime")
    if data.get("status") == "usable" and (not data.get("source_ids") or not data.get("evidence_locators")):
        errors.append("usable finding requires source_ids and evidence_locators")
    return errors


def validate_conflict_review_record(data: dict[str, Any]) -> list[str]:
    errors = _strict_record(data, CONFLICT_REVIEW_FIELDS)
    if not re.fullmatch(r"CRV\d{3}", str(data.get("review_id", ""))):
        errors.append("conflict review_id must match CRV followed by three digits")
    for field in ("author_run_id", "reviewer_run_id", "target_id", "reason"):
        if not isinstance(data.get(field), str) or not data.get(field):
            errors.append(f"{field} must be a non-empty string")
    if not isinstance(data.get("independent"), bool):
        errors.append("independent must be boolean")
    if data.get("author_run_id") == data.get("reviewer_run_id") or data.get("independent") is not True:
        errors.append("conflict reviewer must be independent")
    if data.get("target_kind") not in {"contradiction_ledger", "conflict"}:
        errors.append("target_kind is invalid")
    if not _is_sha256(data.get("target_sha256")):
        errors.append("target_sha256 must be a SHA-256 value")
    if data.get("verdict") not in {"supported", "not_supported", "unclear"}:
        errors.append("verdict is invalid")
    if data.get("required_action") not in {"none", "qualify", "remove", "rewrite", "add_evidence"}:
        errors.append("required_action is invalid")
    if data.get("verdict") != "supported" and data.get("required_action") == "none":
        errors.append("non-supported conflict review requires an action")
    if not _valid_iso_datetime(data.get("reviewed_at")):
        errors.append("reviewed_at must be an ISO datetime")
    return errors


def validate_human_approval(data: dict[str, Any]) -> list[str]:
    errors = _strict_record(data, HUMAN_APPROVAL_FIELDS)
    if not re.fullmatch(r"APP\d{3}", str(data.get("approval_id", ""))):
        errors.append("approval_id is invalid")
    for field in ("reviewer", "reason"):
        if not isinstance(data.get(field), str) or not data.get(field):
            errors.append(f"{field} must be a non-empty string")
    if data.get("scope") not in {"internal_high_stakes", "public_release"}:
        errors.append("scope is invalid")
    if data.get("decision") not in {"approved", "rejected"}:
        errors.append("decision is invalid")
    if not _is_sha256(data.get("approved_artifact_sha256")):
        errors.append("approved_artifact_sha256 must be a SHA-256 value")
    if not _valid_iso_datetime(data.get("reviewed_at")):
        errors.append("reviewed_at must be an ISO datetime")
    if data.get("expires_at") is not None and not _valid_iso_datetime(data.get("expires_at")):
        errors.append("expires_at must be null or an ISO datetime")
    return errors


def validate_reverification_record(data: dict[str, Any]) -> list[str]:
    errors = _strict_record(data, REVERIFICATION_FIELDS)
    if not re.fullmatch(r"S\d{3}", str(data.get("source_id", ""))):
        errors.append("source_id must match S followed by three digits")
    if not isinstance(data.get("canonical_url"), str) or not data.get("canonical_url"):
        errors.append("canonical_url must be a non-empty string")
    if not _valid_iso_datetime(data.get("checked_at")):
        errors.append("checked_at must be an ISO datetime")
    if data.get("status") not in {"current", "changed", "unavailable", "error"}:
        errors.append("status is invalid")
    if data.get("observed_status") is not None and not isinstance(data.get("observed_status"), int):
        errors.append("observed_status must be null or integer")
    if data.get("content_sha256") is not None and not _is_sha256(data.get("content_sha256")):
        errors.append("content_sha256 must be null or a SHA-256 value")
    if not isinstance(data.get("reason"), str) or not data.get("reason"):
        errors.append("reason must be a non-empty string")
    return errors


def validate_release_manifest(data: dict[str, Any]) -> list[str]:
    errors = _strict_record(data, RELEASE_MANIFEST_FIELDS)
    if not isinstance(data.get("run_id"), str) or not data.get("run_id"):
        errors.append("run_id must be a non-empty string")
    if not isinstance(data.get("generation"), int) or data.get("generation", 0) < 1:
        errors.append("generation must be a positive integer")
    if not _valid_iso_datetime(data.get("release_created_at")):
        errors.append("release_created_at must be an ISO datetime")
    for field in ("validation_receipt_sha256", "skill_package_sha256", "registry_metadata_sha256", "trust_report_sha256", "human_approval_sha256"):
        if not _is_sha256(data.get(field)):
            errors.append(f"{field} must be a SHA-256 value")
    summary = data.get("reverification_summary")
    if not isinstance(summary, dict) or set(summary) != {"required_source_ids", "verified_source_ids", "record_sha256"}:
        errors.append("reverification_summary has invalid fields")
    else:
        for field in ("required_source_ids", "verified_source_ids"):
            value = summary.get(field)
            if not isinstance(value, list) or not all(re.fullmatch(r"S\d{3}", str(item)) for item in value):
                errors.append(f"reverification_summary.{field} must contain source IDs")
        if summary.get("record_sha256") is not None and not _is_sha256(summary.get("record_sha256")):
            errors.append("reverification_summary.record_sha256 must be null or a SHA-256 value")
    errors.extend(_validate_hash_map(data.get("files"), "files"))
    return errors


def validate_governed_trust_evidence(data: dict[str, Any]) -> list[str]:
    errors = _unknown_fields(data, GOVERNED_TRUST_FIELDS) + _missing_fields(data, GOVERNED_TRUST_FIELDS)
    if data.get("schema_version") != "1.0":
        errors.append("governed trust schema_version must be 1.0")
    if data.get("status") != "verified":
        errors.append("governed trust status must be verified")
    for field in ("skill_package_sha256", "registry_package_sha256", "yao_trust_report_sha256"):
        if not _is_sha256(data.get(field)):
            errors.append(f"{field} must be a SHA-256 value")
    if not isinstance(data.get("yao_trust_report"), str) or not data.get("yao_trust_report"):
        errors.append("yao_trust_report must be a non-empty path")
    for field in ("skill_directory_read_only", "registry_read_only", "trust_report_read_only"):
        if data.get(field) is not True:
            errors.append("read-only trust boundary is missing evidence")
    if not isinstance(data.get("verified_by"), str) or not data.get("verified_by"):
        errors.append("verified_by must be a non-empty string")
    if not _valid_iso_datetime(data.get("verified_at")):
        errors.append("verified_at must be an ISO datetime")
    return list(dict.fromkeys(errors))


def validate_claim_record(data: dict[str, Any]) -> list[str]:
    errors = _unknown_fields(data, CLAIM_FIELDS) + _missing_fields(data, CLAIM_FIELDS)
    if data.get("schema_version") != "2.0":
        errors.append("claim schema_version must be 2.0")
    if not re.fullmatch(r"C\d{3}", str(data.get("claim_id", ""))):
        errors.append("claim_id must match C followed by three digits")
    claim_type = data.get("claim_type")
    premises = data.get("premise_claim_ids")
    support = data.get("supporting_source_ids")
    contradict = data.get("contradicting_source_ids")
    if claim_type not in {"fact", "inference", "recommendation"}:
        errors.append("claim_type is invalid")
    if not isinstance(premises, list) or not all(re.fullmatch(r"C\d{3}", str(item)) for item in premises):
        errors.append("premise_claim_ids must contain stable claim IDs")
        premises = []
    if not isinstance(support, list) or not all(re.fullmatch(r"S\d{3}", str(item)) for item in support):
        errors.append("supporting_source_ids must contain stable source IDs")
        support = []
    if not isinstance(contradict, list) or not all(re.fullmatch(r"S\d{3}", str(item)) for item in contradict):
        errors.append("contradicting_source_ids must contain stable source IDs")
    if claim_type == "fact" and not support and data.get("status") not in {"unsupported", "out_of_scope"}:
        errors.append("fact requires supporting evidence")
    if claim_type in {"inference", "recommendation"} and not premises:
        errors.append(f"{claim_type} requires supported premise claims")
    if claim_type in {"inference", "recommendation"} and not str(data.get("reasoning_note", "")).strip():
        errors.append(f"{claim_type} requires a reasoning_note")
    if claim_type == "recommendation":
        if not data.get("conditions"):
            errors.append("recommendation requires conditions")
        if not data.get("tradeoffs"):
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
    locators = data.get("evidence_locators")
    if not isinstance(locators, list):
        errors.append("evidence_locators must be an array")
    else:
        locator_fields = {"source_id", "locator", "excerpt", "snapshot_sha256"}
        for index, locator in enumerate(locators, start=1):
            if not isinstance(locator, dict) or set(locator) != locator_fields:
                errors.append(f"evidence locator {index} has invalid fields")
                continue
            if not re.fullmatch(r"S\d{3}", str(locator.get("source_id", ""))):
                errors.append(f"evidence locator {index} has invalid source_id")
            if not str(locator.get("locator", "")).strip() or not str(locator.get("excerpt", "")).strip():
                errors.append(f"evidence locator {index} requires locator and excerpt")
            if not _is_sha256(locator.get("snapshot_sha256")):
                errors.append(f"evidence locator {index} requires snapshot_sha256")
    for field in ("conditions", "tradeoffs"):
        if not isinstance(data.get(field), list) or not all(isinstance(item, str) and item.strip() for item in data.get(field, [])):
            errors.append(f"{field} must be an array of non-empty strings")
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
