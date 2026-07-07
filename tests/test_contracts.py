from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import scripts.contract_io as contract_io
from scripts.contract_io import (
    ContractError,
    load_json,
    load_jsonl,
    validate_brief,
    validate_claim_record,
    validate_research_plan,
    validate_research_package,
    validate_source_record,
)
from tests.governed_fixtures import (
    valid_amendment,
    valid_brief_v2,
    valid_candidate_record,
    valid_capture_input,
    valid_governed_trust_evidence,
    valid_gap_assessment_record,
    valid_human_approval,
    valid_paragraph_map_record,
    valid_receipt,
    valid_release_manifest,
    valid_research_plan_v2,
    valid_retrieval_evidence,
    valid_search_run_record,
    valid_search_wave_record,
    valid_reverification_record,
    valid_semantic_review_record,
    valid_source_plan,
)


ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_storm_lens_schema_rejects_unstructured_p4_output(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/storm-lens-artifact.schema.json").read_text(encoding="utf-8")
        )
        p4_rules = schema.get("allOf")
        self.assertIsInstance(p4_rules, list)
        encoded = json.dumps(p4_rules, ensure_ascii=False)
        for field in (
            "target_sha256", "weakest_claim_ids", "missing_perspectives",
            "citation_support_issues", "repair_actions",
        ):
            self.assertIn(field, encoded)

    def test_retrieval_input_union_accepts_all_record_kinds(self) -> None:
        for record in (
            valid_search_run_record(),
            valid_candidate_record(),
            valid_capture_input(),
            valid_search_wave_record(),
            valid_gap_assessment_record(),
        ):
            self.assertEqual(contract_io.validate_retrieval_input_record(record), [])

    def test_terminal_gap_assessment_can_defer_independent_review_binding(self) -> None:
        for terminal_state in (
            "saturated", "bounded_corpus_exhausted",
            "access_limited_uncertainty", "out_of_scope",
        ):
            with self.subTest(terminal_state=terminal_state):
                record = valid_gap_assessment_record(
                    terminal_state=terminal_state,
                    supporting_wave_ids=["WAVE001"],
                    supporting_search_run_ids=["SR001"],
                )
                self.assertEqual(contract_io.validate_retrieval_input_record(record), [])
                record["review_concern_id"] = None
                self.assertEqual(contract_io.validate_retrieval_input_record(record), [])
                record["review_concern_id"] = "not-a-review-concern"
                self.assertIn(
                    "review_concern_id must match RC followed by three digits",
                    contract_io.validate_retrieval_input_record(record),
                )

    def test_maximal_brief_uses_saturation_contract_without_numeric_quotas(self) -> None:
        brief = valid_brief_v2()
        brief.update({
            "research_profile": "maximal_full_dossier",
            "length_contract": {
                "unit": "words",
                "policy": "open_ended",
                "content_standard": "evidence_led",
            },
            "maximal_completeness_contract": {
                "completion_policy": "coverage_and_saturation",
                "discovery_surface_policy": "domain_adaptive_with_mandatory_counterevidence",
                "surface_applicability_required": True,
                "tasklet_closure_required": True,
                "storm_gap_closure_required": True,
                "material_novelty_window": 2,
                "final_integrity_required": True,
                "review_policy": "concern_driven_until_clear",
            },
        })
        brief["profile_selection"]["selected_profile"] = "maximal_full_dossier"
        self.assertEqual(validate_brief(brief), [])
        self.assertFalse(any(
            key.startswith("min_") for key in brief["maximal_completeness_contract"]
        ))

    def test_maximal_research_plan_accepts_open_ended_retrieval_budget(self) -> None:
        brief = valid_brief_v2()
        brief.update({
            "research_profile": "maximal_full_dossier",
            "length_contract": {
                "unit": "words", "policy": "open_ended", "content_standard": "evidence_led",
            },
            "maximal_completeness_contract": {
                "completion_policy": "coverage_and_saturation",
                "discovery_surface_policy": "domain_adaptive_with_mandatory_counterevidence",
                "surface_applicability_required": True,
                "tasklet_closure_required": True,
                "storm_gap_closure_required": True,
                "material_novelty_window": 2,
                "final_integrity_required": True,
                "review_policy": "concern_driven_until_clear",
            },
        })
        brief["profile_selection"]["selected_profile"] = "maximal_full_dossier"
        plan = contract_io.validate_research_plan
        payload = valid_research_plan_v2()
        payload["retrieval_budget"] = {
            "policy": "open_ended_until_saturation",
            "max_queries": None,
            "max_sources": None,
            "stop_conditions": [
                "tasklet_closure", "storm_gap_closure",
                "material_novelty_saturation", "reviewer_no_material_omission",
            ],
        }
        self.assertEqual(plan(payload, brief, set()), [])

    def test_abstract_capture_is_explicit_and_cannot_claim_strong_evidence(self) -> None:
        capture = valid_capture_input()
        capture.update({
            "capture_level": "abstract",
            "locator_type": "abstract",
            "content_locator": "abstract",
            "evidence_strength_ceiling": "medium",
        })
        self.assertEqual(contract_io.validate_adapter_capture_record(capture), [])
        capture["evidence_strength_ceiling"] = "strong"
        self.assertIn(
            "abstract capture cannot exceed medium evidence",
            contract_io.validate_adapter_capture_record(capture),
        )

    def test_full_text_capture_rejects_abstract_locator(self) -> None:
        capture = valid_capture_input()
        capture.update({"locator_type": "abstract", "content_locator": "abstract"})
        self.assertIn(
            "full_text capture cannot use an abstract or metadata locator",
            contract_io.validate_adapter_capture_record(capture),
        )

    def test_unreachable_resolver_cannot_claim_metadata_match(self) -> None:
        candidate = valid_candidate_record()
        outcome = candidate["resolver_outcomes"][0]
        outcome["status"] = "unreachable"
        outcome["metadata_match"] = True
        self.assertIn(
            "unreachable resolver cannot claim a metadata match",
            contract_io.validate_candidate_record(candidate),
        )

    def test_excluded_candidate_requires_screening_reason(self) -> None:
        candidate = valid_candidate_record()
        candidate["disposition"] = "exclude"
        candidate["screening_reason"] = ""
        self.assertIn(
            "candidate disposition requires screening_reason",
            contract_io.validate_candidate_record(candidate),
        )

    def test_resolver_identifier_must_match_candidate_identifier(self) -> None:
        candidate = valid_candidate_record()
        candidate["resolver_outcomes"][0]["matched_identifier"] = "10.5555/other"
        self.assertIn(
            "resolver matched_identifier conflicts with candidate doi",
            contract_io.validate_candidate_record(candidate),
        )

    def test_source_plan_requires_search_requirements(self) -> None:
        plan = valid_source_plan()
        del plan["questions"][0]["search_requirements"]
        self.assertIn("source question 1 has invalid fields", contract_io.validate_source_plan(plan))

    def test_governed_schema_inventory_is_strict(self) -> None:
        names = {
            "receipt", "amendment", "source-plan", "retrieval-evidence",
            "paragraph-map-record", "semantic-review-record", "human-approval",
            "reverification-record", "release-manifest",
            "governed-trust-evidence",
            "review-request", "review-provenance", "absence-search-record",
            "execution-provenance",
        }
        for name in names:
            path = ROOT / "schemas" / f"{name}.schema.json"
            self.assertTrue(path.is_file(), name)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertFalse(payload["additionalProperties"], name)

    def test_full_dossier_cannot_select_reduced_output(self) -> None:
        brief = valid_brief_v2()
        brief["output_mode"] = "reduced"
        self.assertIn("full_dossier requires full output", validate_brief(brief))

    def test_brief_requires_explicit_assurance_target(self) -> None:
        brief = valid_brief_v2()
        del brief["assurance_target"]
        self.assertIn("missing fields: assurance_target", validate_brief(brief))
        brief["assurance_target"] = "real_host_execution"
        self.assertIn("assurance_target is invalid", validate_brief(brief))

    def test_brief_accepts_diagnostic_rehearsal_intent(self) -> None:
        brief = valid_brief_v2()
        brief["run_intent"] = "diagnostic_rehearsal"
        self.assertEqual(validate_brief(brief), [])
        brief["run_intent"] = "release_anyway"
        self.assertIn("run_intent is invalid", validate_brief(brief))

    def test_captured_host_brief_requires_bound_profile_selection_evidence(self) -> None:
        brief = valid_brief_v2()
        brief["assurance_target"] = "captured_host_execution"
        self.assertIn(
            "profile_selection.evidence_ref is required for captured_host_execution",
            validate_brief(brief),
        )
        brief["profile_selection"]["evidence_ref"] = "inputs/profile-selection-evidence.txt"
        brief["profile_selection"]["evidence_sha256"] = "a" * 64
        self.assertNotIn(
            "profile_selection.evidence_ref is required for captured_host_execution",
            validate_brief(brief),
        )

    def test_briefing_requires_explicit_reason(self) -> None:
        brief = valid_brief_v2()
        brief["depth_level"] = "briefing"
        self.assertIn("briefing requires briefing_reason", validate_brief(brief))
        brief["briefing_reason"] = "user explicitly asked for a short briefing"
        self.assertNotIn("briefing requires briefing_reason", validate_brief(brief))

    def test_non_briefing_rejects_briefing_reason(self) -> None:
        brief = valid_brief_v2()
        brief["briefing_reason"] = "host defaulted to short mode"
        self.assertIn("briefing_reason is only valid for briefing depth", validate_brief(brief))

    def test_research_profile_consistency_is_validated(self) -> None:
        brief = valid_brief_v2()
        brief["research_profile"] = "strict_storm_lens"
        brief["profile_selection"]["selected_profile"] = "strict_storm_lens"
        brief["storm_lens_mode"] = "advisory"
        self.assertIn("strict_storm_lens profile requires strict STORM lens", validate_brief(brief))
        brief["storm_lens_mode"] = "strict"
        self.assertNotIn("strict_storm_lens profile requires strict STORM lens", validate_brief(brief))

        brief = valid_brief_v2()
        brief["storm_lens_mode"] = "advisory"
        self.assertIn("default_full_dossier profile requires strict STORM lens", validate_brief(brief))

        brief = valid_brief_v2()
        brief["research_profile"] = "closed_corpus"
        brief["profile_selection"]["selected_profile"] = "closed_corpus"
        self.assertIn(
            "closed_corpus profile requires closed_corpus source policy and retrieval mode",
            validate_brief(brief),
        )

        brief = valid_brief_v2()
        brief["research_profile"] = "maximal_full_dossier"
        brief["profile_selection"]["selected_profile"] = "maximal_full_dossier"
        self.assertIn("maximal_full_dossier profile requires open_ended length", validate_brief(brief))
        brief["length_contract"] = {
            "unit": "words",
            "policy": "open_ended",
            "content_standard": "evidence_led",
        }
        self.assertNotIn("maximal_full_dossier profile requires open_ended length", validate_brief(brief))

    def test_profile_selection_is_required_and_matches_profile(self) -> None:
        brief = valid_brief_v2()
        del brief["profile_selection"]
        self.assertIn("missing fields: profile_selection", validate_brief(brief))

        brief = valid_brief_v2()
        brief["profile_selection"]["selected_profile"] = "briefing"
        self.assertIn("profile_selection.selected_profile must match research_profile", validate_brief(brief))

        brief = valid_brief_v2()
        brief["profile_selection"]["evidence"] = ""
        self.assertIn("profile_selection.evidence must be a non-empty string", validate_brief(brief))

        brief = valid_brief_v2()
        brief["profile_selection"]["mode"] = "defaulted_after_prompt"
        self.assertIn(
            "profile_selection.prompt_ref is required for defaulted_after_prompt",
            validate_brief(brief),
        )
        brief["profile_selection"]["prompt_ref"] = "inputs/profile-selection-prompt.txt"
        brief["profile_selection"]["prompt_sha256"] = "a" * 64
        self.assertNotIn(
            "profile_selection.prompt_ref is required for defaulted_after_prompt",
            validate_brief(brief),
        )
        brief["profile_selection"]["mode"] = "user_requested_default"
        self.assertIn(
            "profile_selection prompt fields are only valid for defaulted_after_prompt",
            validate_brief(brief),
        )

    def test_governed_record_validators_are_strict(self) -> None:
        cases = {
            "receipt": valid_receipt,
            "amendment": valid_amendment,
            "source_plan": valid_source_plan,
            "retrieval_evidence": valid_retrieval_evidence,
            "paragraph_map_record": valid_paragraph_map_record,
            "semantic_review_record": valid_semantic_review_record,
            "human_approval": valid_human_approval,
            "reverification_record": valid_reverification_record,
            "release_manifest": valid_release_manifest,
            "governed_trust_evidence": valid_governed_trust_evidence,
        }
        for name, builder in cases.items():
            with self.subTest(name=name):
                validator = getattr(contract_io, f"validate_{name}", None)
                self.assertTrue(callable(validator), name)
                payload = builder()
                self.assertEqual(validator(payload), [])
                payload["unexpected"] = True
                self.assertIn("unknown fields: unexpected", validator(payload))

    def test_semantic_review_requires_evidence_locator_and_acceptance_test(self) -> None:
        review = valid_semantic_review_record()
        del review["evidence_or_locator"]
        del review["acceptance_test"]
        errors = contract_io.validate_semantic_review_record(review)
        self.assertIn("missing fields: acceptance_test, evidence_or_locator", errors)
        self.assertIn("evidence_or_locator must be a non-empty string", errors)
        self.assertIn("acceptance_test must be a non-empty string", errors)

    def test_schema_files_are_strict_draft_2020_contracts(self) -> None:
        names = (
            "brief",
            "research-plan",
            "retrieval-record",
            "source-record",
            "claim-evidence-record",
            "report-claim-map",
            "report-outline",
            "validation-report",
        )
        for name in names:
            payload = json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertFalse(payload["additionalProperties"], name)
            self.assertTrue(payload["required"], name)

    def test_load_json_rejects_non_object_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("[]\n", encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "JSON object"):
                load_json(path)

    def test_load_jsonl_reports_line_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jsonl"
            path.write_text('{"source_id":"S001"}\nnot-json\n', encoding="utf-8")
            with self.assertRaisesRegex(ContractError, r"bad\.jsonl:2"):
                load_jsonl(path)

    def test_brief_rejects_unknown_fields(self) -> None:
        brief = valid_brief()
        brief["mystery"] = True
        self.assertIn("unknown fields: mystery", validate_brief(brief))

    def test_brief_rejects_invalid_length_contract(self) -> None:
        brief = valid_brief()
        brief["length_contract"] = {
            "unit": "characters",
            "policy": "bounded",
            "minimum": 10000,
            "target": 9000,
            "maximum": 8000,
            "content_standard": "evidence_led",
        }
        self.assertIn("length_contract must satisfy minimum <= target <= maximum", validate_brief(brief))

        brief = valid_brief_v2()
        brief["length_contract"] = {
            "unit": "words",
            "policy": "open_ended",
            "minimum": 1,
            "content_standard": "evidence_led",
        }
        self.assertIn("length_contract has invalid fields", validate_brief(brief))

    def test_research_plan_rejects_answered_question_without_claims(self) -> None:
        brief = valid_brief()
        plan = valid_research_plan()
        plan["questions"].append({
            "question_id": "Q002",
            "perspective": "skeptic",
            "text": "What could falsify the finding?",
            "status": "answered",
            "claim_ids": [],
            "disposition_note": "Used to test the conclusion.",
        })
        errors = validate_research_plan(plan, brief, set())
        self.assertIn("answered question Q002 requires claim_ids", errors)

    def test_fact_without_support_is_rejected(self) -> None:
        record = valid_claim()
        record["supporting_source_ids"] = []
        self.assertIn("fact requires supporting evidence", validate_claim_record(record))

    def test_source_requires_stable_id_and_provenance(self) -> None:
        source = valid_source()
        source["source_id"] = "source-one"
        source["canonical_url"] = ""
        errors = validate_source_record(source)
        self.assertIn("source_id must match S followed by three digits", errors)
        self.assertIn("source requires canonical_url or file_ref", errors)

    def test_package_rejects_duplicate_and_unknown_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "research").mkdir()
            (root / "brief.json").write_text(json.dumps(valid_brief()), encoding="utf-8")
            (root / "research" / "research-plan.json").write_text(
                json.dumps(valid_research_plan()), encoding="utf-8"
            )
            source = valid_source()
            (root / "research" / "source-register.jsonl").write_text(
                json.dumps(source) + "\n" + json.dumps(source) + "\n", encoding="utf-8"
            )
            claim = valid_claim()
            claim["supporting_source_ids"] = ["S999"]
            (root / "research" / "claim-evidence-ledger.jsonl").write_text(json.dumps(claim) + "\n", encoding="utf-8")
            (root / "research" / "report-claim-map.json").write_text(
                json.dumps({"schema_version": "1.0", "mappings": []}), encoding="utf-8"
            )
            errors = validate_research_package(root)
            self.assertTrue(any("duplicate source_id S001" in item for item in errors))
            self.assertTrue(any("unknown source_id S999" in item for item in errors))


def valid_brief() -> dict[str, object]:
    brief = valid_brief_v2()
    brief["topic"] = "Test topic"
    brief["research_question"] = "What evidence answers the question?"
    brief["user_goal"] = "Understand the evidence"
    brief["depth_level"] = "standard_report"
    return brief


def valid_research_plan() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "status": "complete",
        "perspectives": ["academic"],
        "questions": [{
            "question_id": "Q001",
            "perspective": "academic",
            "text": "What evidence supports the finding?",
            "status": "answered",
            "claim_ids": ["C001"],
            "disposition_note": "Used in Key Findings.",
        }],
        "source_priorities": ["official"],
        "stopping_conditions": ["material claim closure reaches 100%"],
        "retrieval_budget": {"max_queries": 20, "max_sources": 40},
    }


def valid_source() -> dict[str, object]:
    return {
        "source_id": "S001",
        "title": "Official source",
        "author_or_org": "Example Org",
        "canonical_url": "https://www.nist.gov/test-fixtures/research-report",
        "file_ref": "",
        "published_at": "2026-05-01",
        "publication_date_status": "known",
        "retrieved_at": "2026-06-21T10:00:00+08:00",
        "source_type": "official",
        "primary_class": "primary",
        "reliability_tier": "A",
        "freshness_status": "current",
        "reliability_notes": "First-party publication",
        "content_hash": "a" * 64,
    }


def valid_claim() -> dict[str, object]:
    return {
        "claim_id": "C001",
        "claim_text": "The official source reports the result.",
        "claim_type": "fact",
        "material": True,
        "supporting_source_ids": ["S001"],
        "contradicting_source_ids": [],
        "evidence_locators": [{"source_id": "S001", "locator": "section 1", "excerpt": "reported result"}],
        "evidence_strength": "strong",
        "evidence_mode": "direct",
        "absence_search_id": None,
        "confidence": "high",
        "freshness_required": True,
        "reasoning_note": "",
        "tradeoffs": [],
        "limitation": "",
        "change_condition": "A revised official result",
        "status": "supported",
    }


if __name__ == "__main__":
    unittest.main()
