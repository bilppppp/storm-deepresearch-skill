from __future__ import annotations

from pathlib import Path


def valid_brief_v2() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "topic": "Governed research",
        "research_question": "What evidence supports the conclusion?",
        "user_goal": "Produce an auditable dossier",
        "audience": "General reader",
        "depth_level": "full_dossier",
        "report_language": "en",
        "length_contract": {
            "unit": "words",
            "minimum": 3500,
            "target": 5000,
            "maximum": 7000,
            "content_standard": "evidence_led",
        },
        "geography": "global",
        "timeframe": "current",
        "source_policy": "external_allowed",
        "freshness_policy": {"as_of": "2026-06-23", "max_age_days": 365},
        "retrieval_mode": "host",
        "output_mode": "full",
        "uncertainty_tolerance": "low",
        "high_stakes": False,
        "user_materials": [],
        "assumptions": [],
    }


def valid_receipt(stage: str = "init") -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "run_id": "run-test",
        "generation": 1,
        "stage": stage,
        "status": "passed",
        "previous_receipt_sha256": "",
        "skill_package_sha256": "a" * 64,
        "validator_sha256": "b" * 64,
        "input_artifacts": {},
        "output_artifacts": {},
        "checks": [],
        "completed_at": "2026-06-23T00:00:00Z",
        "receipt_sha256": "c" * 64,
    }


def valid_amendment() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "run_id": "run-test",
        "from_generation": 1,
        "to_generation": 2,
        "changes": [{
            "field": "timeframe",
            "before": "current",
            "after": "2025-2026",
            "reason": "User refined the research period",
        }],
        "initiator": "human-reviewer",
        "user_approval_evidence": "approval:conversation-1",
        "invalidation_start_stage": "plan",
        "created_at": "2026-06-23T00:00:00Z",
        "amendment_sha256": "d" * 64,
    }


def valid_research_plan_v2() -> dict[str, object]:
    perspectives = ["historian", "domain_expert", "skeptic", "practitioner", "affected_party"]
    questions = [
        {
            "question_id": f"Q{index:03d}",
            "perspective": perspectives[(index - 1) % len(perspectives)],
            "text": f"What evidence is needed for research question {index}?",
            "status": "planned",
            "claim_ids": [],
            "disposition_note": "Planned for governed retrieval.",
        }
        for index in range(1, 11)
    ]
    return {
        "schema_version": "2.0",
        "status": "planned",
        "perspectives": perspectives,
        "questions": questions,
        "source_priorities": ["primary official evidence", "independent scholarship"],
        "stopping_conditions": ["Every material question has an evidence disposition"],
        "retrieval_budget": {"max_queries": 30, "max_sources": 50},
    }


def valid_source_plan(question_count: int = 10) -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "questions": [
            {
                "query_id": f"Q{index:03d}",
                "question": f"What evidence is needed for research question {index}?",
                "evidence_need": "Directly inspectable primary or authoritative evidence",
                "required_source_classes": ["official-record"],
            }
            for index in range(1, question_count + 1)
        ],
        "source_classes": [{
            "class_id": "official-record",
            "name": "Official record",
            "can_prove": ["The issuing body's recorded position"],
            "cannot_prove": ["Independent causal validity"],
            "priority": 1,
        }],
        "stopping_conditions": ["Every material question has inspectable evidence"],
        "exclusions": ["Search snippets as strong evidence"],
    }


def valid_source_v2(index: int = 1) -> dict[str, object]:
    digit = format(index % 16, "x")
    return {
        "source_id": f"S{index:03d}",
        "title": f"Official source {index}",
        "author_or_org": "NIST",
        "canonical_url": f"https://www.nist.gov/test-fixtures/research-report-{index}",
        "file_ref": None,
        "published_at": "2026-05-01",
        "publication_date_status": "known",
        "retrieved_at": "2026-06-23T00:00:00Z",
        "source_type": "official",
        "primary_class": "primary",
        "reliability_tier": "A",
        "freshness_status": "current",
        "reliability_notes": "First-party source with inspectable full text.",
        "content_hash": digit * 64,
    }


def valid_retrieval_manifest_v2(index: int = 1) -> dict[str, object]:
    manifest = valid_retrieval_evidence()
    digit = format(index % 16, "x")
    manifest.update({
        "source_id": f"S{index:03d}",
        "query_id": f"Q{index:03d}",
        "canonical_url": f"https://www.nist.gov/test-fixtures/research-report-{index}",
        "final_url": f"https://www.nist.gov/test-fixtures/research-report-{index}",
        "snapshot_ref": f"source-{index}.txt",
        "snapshot_sha256": digit * 64,
        "normalized_text_sha256": "a" * 64,
        "excerpt_sha256": "b" * 64,
        "excerpt": f"Directly inspectable evidence excerpt {index}.",
    })
    return manifest


def valid_claim_v2(
    index: int = 1,
    *,
    claim_type: str = "fact",
    status: str = "supported",
    source_index: int | None = None,
) -> dict[str, object]:
    source_index = source_index or min(index, 10)
    source_id = f"S{source_index:03d}"
    premise_ids = [] if claim_type == "fact" else ["C001"]
    return {
        "schema_version": "2.0",
        "claim_id": f"C{index:03d}",
        "claim_text": f"Governed material claim {index} is supported within scope.",
        "claim_type": claim_type,
        "material": True,
        "premise_claim_ids": premise_ids,
        "supporting_source_ids": [source_id],
        "contradicting_source_ids": [],
        "evidence_locators": [{
            "source_id": source_id,
            "locator": "p:1",
            "excerpt": f"Directly inspectable evidence excerpt {source_index}.",
            "snapshot_sha256": format(source_index % 16, "x") * 64,
        }],
        "evidence_strength": "strong",
        "confidence": "high",
        "freshness_required": True,
        "reasoning_note": "The supported premise and scoped evidence justify this step." if claim_type != "fact" else "",
        "conditions": ["The documented scope remains applicable"] if claim_type == "recommendation" else [],
        "tradeoffs": ["Higher assurance requires more review time"] if claim_type == "recommendation" else [],
        "limitation": "The evidence does not establish claims outside the stated scope.",
        "change_condition": "A revised authoritative source or contrary evidence.",
        "status": status,
    }


def valid_report_outline_v2() -> dict[str, object]:
    sections = []
    for index in range(1, 7):
        claim_ids = [f"C{index * 2 - 1:03d}", f"C{index * 2:03d}"]
        question_ids = [f"Q{index:03d}"]
        if index == 6:
            question_ids.extend(["Q007", "Q008", "Q009", "Q010"])
        sections.append({
            "section_id": f"SEC{index:02d}",
            "title": f"Evidence section {index}",
            "purpose": "Synthesize supported and bounded claims.",
            "target_units": 700,
            "question_ids": question_ids,
            "claim_ids": claim_ids,
            "required_elements": ["claim", "evidence", "limitation"],
        })
    return {
        "schema_version": "2.0",
        "status": "complete",
        "unit": "words",
        "minimum": 3500,
        "target": 5000,
        "maximum": 7000,
        "sections": sections,
    }


def valid_contradiction_ledger_v2() -> dict[str, object]:
    return {"schema_version": "2.0", "conflicts": []}


def valid_uncertainty_ledger_v2() -> dict[str, object]:
    return {"schema_version": "2.0", "uncertainties": []}


def valid_storm_lens_artifact(
    prompt_id: str,
    prompt_pack_sha256: str,
    input_artifacts: dict[str, str],
    *,
    target_sha256: str | None = None,
) -> dict[str, object]:
    phases = {
        "P1": "before_retrieval",
        "P2": "after_findings",
        "P3": "after_conflicts",
        "P4": "after_draft",
    }
    outputs: dict[str, dict[str, object]] = {
        "P1": {
            "perspectives": ["historian", "domain_expert", "skeptic", "practitioner", "affected_party"],
            "question_ids": [f"Q{index:03d}" for index in range(1, 11)],
            "source_class_ids": ["official-record"],
            "notes": "Prompt 1 created perspective questions and source needs before retrieval.",
        },
        "P2": {
            "finding_ids": [f"F{index:03d}" for index in range(1, 11)],
            "conflict_claim_ids": [],
            "consensus_candidates": ["Fixture findings agree inside their limited scope."],
            "blind_spots": ["No external blind spot is material in this fixture."],
            "resolver_questions": [],
        },
        "P3": {
            "section_ids": [f"SEC{index:02d}" for index in range(1, 7)],
            "claim_ids": [f"C{index:03d}" for index in range(1, 13)],
            "finding_ids": [f"F{index:03d}" for index in range(1, 11)],
            "contradiction_ids": [],
            "uncertainty_ids": [],
            "length_budget_note": "Each section receives evidence-led expansion from findings and Claims.",
        },
        "P4": {
            "target_kind": "draft",
            "target_sha256": target_sha256 or "0" * 64,
            "weakest_claim_ids": ["C012"],
            "overstated_paragraphs": [],
            "missing_perspectives": [],
            "citation_support_issues": [],
            "repair_actions": [],
        },
    }
    return {
        "schema_version": "2.0",
        "prompt_id": prompt_id,
        "prompt_pack_sha256": prompt_pack_sha256,
        "phase": phases[prompt_id],
        "input_artifacts": input_artifacts,
        "output": outputs[prompt_id],
        "created_at": "2026-06-23T00:00:00Z",
    }


def valid_retrieval_evidence() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "source_id": "S001",
        "query_id": "Q001",
        "canonical_url": "https://www.nist.gov/test-fixtures/research-report",
        "final_url": "https://www.nist.gov/test-fixtures/research-report",
        "file_ref": None,
        "observed_status": 200,
        "content_type": "text/html",
        "retrieved_at": "2026-06-23T00:00:00Z",
        "adapter": "host",
        "adapter_run_id": "host-run-1",
        "capture_level": "full_text",
        "evidence_strength_ceiling": "strong",
        "snapshot_ref": "evidence-cache/Q001/source.html",
        "snapshot_sha256": "e" * 64,
        "normalized_text_sha256": "f" * 64,
        "locator_type": "paragraph",
        "locator": "p:17-19",
        "excerpt": "Directly inspectable evidence excerpt.",
        "excerpt_sha256": "1" * 64,
        "published_at": "2026-05-01",
        "publication_date_status": "known",
        "source_type": "official",
        "primary_class": "primary",
        "reliability_tier": "A",
        "reliability_notes": "First-party publication; scope is limited to recorded facts.",
    }


def valid_adapter_record(index: int = 1) -> dict[str, object]:
    return {
        "query_id": f"Q{index:03d}",
        "url": f"https://www.nist.gov/test-fixtures/research-report-{index}",
        "final_url": f"https://www.nist.gov/test-fixtures/research-report-{index}",
        "file_ref": None,
        "title": f"Official research report {index}",
        "publisher": "National Institute of Standards and Technology",
        "published_at": "2026-05-01",
        "publication_date_status": "known",
        "retrieved_at": "2026-06-23T00:00:00Z",
        "content_excerpt": f"Directly inspectable evidence excerpt {index}.",
        "content_locator": "p:1",
        "locator_type": "paragraph",
        "adapter": "host",
        "adapter_run_id": "host-run-1",
        "capture_level": "full_text",
        "evidence_strength_ceiling": "strong",
        "raw_artifact": f"source-{index}.txt",
        "observed_status": 200,
        "content_type": "text/plain",
        "source_type": "official",
        "primary_class": "primary",
        "reliability_tier": "A",
        "freshness_status": "current",
        "reliability_notes": "First-party source with inspectable full text.",
    }


def valid_paragraph_map_record(
    *,
    paragraph_type: str = "factual",
    claim_ids: list[str] | None = None,
    source_ids: list[str] | None = None,
    citation_keys: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "paragraph_sha256": "2" * 64,
        "paragraph_type": paragraph_type,
        "claim_ids": ["C001"] if claim_ids is None else claim_ids,
        "source_ids": ["S001"] if source_ids is None else source_ids,
        "citation_keys": ["nist-2026-report"] if citation_keys is None else citation_keys,
        "text_locator": "paragraph:1",
    }


def valid_semantic_review_record() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "review_id": "REV001",
        "review_type": "claim_entailment",
        "author_run_id": "author-run-1",
        "reviewer_run_id": "reviewer-run-1",
        "independent": True,
        "target_kind": "claim",
        "target_id": "C001",
        "target_sha256": "3" * 64,
        "material": True,
        "verdict": "supported",
        "reason": "The scoped claim is directly entailed by the captured excerpt.",
        "allowable_scope": None,
        "required_action": "none",
        "findings": [],
        "reviewed_at": "2026-06-23T00:00:00Z",
    }


def valid_human_approval() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "approval_id": "APP001",
        "reviewer": "human-reviewer",
        "scope": "public_release",
        "decision": "approved",
        "reason": "All governed gates and blind review requirements are satisfied.",
        "approved_artifact_sha256": "4" * 64,
        "reviewed_at": "2026-06-23T00:00:00Z",
        "expires_at": None,
    }


def valid_reverification_record() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "source_id": "S001",
        "canonical_url": "https://www.nist.gov/test-fixtures/research-report",
        "checked_at": "2026-06-23T00:00:00Z",
        "status": "current",
        "observed_status": 200,
        "content_sha256": "5" * 64,
        "reason": "The current source remains available and unchanged.",
    }


def valid_governed_trust_evidence() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "status": "verified",
        "skill_package_sha256": "1" * 64,
        "registry_package_sha256": "2" * 64,
        "yao_trust_report": "/host/security-trust-report.json",
        "yao_trust_report_sha256": "3" * 64,
        "skill_directory_read_only": True,
        "registry_read_only": True,
        "trust_report_read_only": True,
        "verified_by": "host",
        "verified_at": "2026-06-23T00:00:00Z",
    }


def valid_release_manifest() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "run_id": "run-test",
        "generation": 1,
        "release_created_at": "2026-06-23T00:00:00Z",
        "validation_receipt_sha256": "6" * 64,
        "skill_package_sha256": "7" * 64,
        "registry_metadata_sha256": "b" * 64,
        "trust_report_sha256": "8" * 64,
        "human_approval_sha256": "9" * 64,
        "reverification_summary": {
            "required_source_ids": [],
            "verified_source_ids": [],
            "record_sha256": None,
        },
        "files": {"report.md": "a" * 64},
    }


def make_run_with_plan_receipt(
    root: Path,
    *,
    package_hash: str = "a" * 64,
    validator_hash: str = "b" * 64,
):
    from scripts.harness_io import atomic_write_json, sha256_file
    from scripts.run_state import RunLayout, Stage, commit_stage_receipt, create_generation

    layout = RunLayout(root)
    create_generation(layout, 1)
    brief = layout.generation_input(1, "brief.json")
    atomic_write_json(brief, {"schema_version": "2.0"})
    commit_stage_receipt(
        layout,
        generation=1,
        stage=Stage.INIT,
        package_hash=package_hash,
        validator_hash=validator_hash,
        input_artifacts={},
        output_paths=[brief],
    )
    plan = layout.artifact(1, "research/research-plan.json")
    atomic_write_json(plan, {"schema_version": "2.0"})
    commit_stage_receipt(
        layout,
        generation=1,
        stage=Stage.PLAN,
        package_hash=package_hash,
        validator_hash=validator_hash,
        input_artifacts={"inputs/brief.json": sha256_file(brief)},
        output_paths=[plan],
    )
    return layout
