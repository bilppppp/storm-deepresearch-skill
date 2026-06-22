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


def valid_source_plan() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "questions": [{
            "query_id": "Q001",
            "question": "What evidence supports the conclusion?",
            "evidence_need": "Directly inspectable primary evidence",
            "required_source_classes": ["official-record"],
        }],
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


def valid_retrieval_evidence() -> dict[str, object]:
    return {
        "schema_version": "2.0",
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


def valid_paragraph_map_record() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "paragraph_sha256": "2" * 64,
        "paragraph_type": "factual",
        "claim_ids": ["C001"],
        "source_ids": ["S001"],
        "citation_keys": ["nist-2026-report"],
        "text_locator": "section:key-findings/paragraph:1",
    }


def valid_semantic_review_record() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "review_id": "REV001",
        "review_type": "claim_entailment",
        "reviewer_id": "independent-reviewer",
        "independent": True,
        "target_sha256": "3" * 64,
        "verdict": "supported",
        "reason": "The scoped claim is directly entailed by the captured excerpt.",
        "allowable_scope": None,
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


def valid_release_manifest() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "run_id": "run-test",
        "generation": 1,
        "release_created_at": "2026-06-23T00:00:00Z",
        "validation_receipt_sha256": "6" * 64,
        "skill_package_sha256": "7" * 64,
        "trust_report_sha256": "8" * 64,
        "human_approval_sha256": "9" * 64,
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
