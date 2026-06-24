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
    valid_governed_trust_evidence,
    valid_human_approval,
    valid_paragraph_map_record,
    valid_receipt,
    valid_release_manifest,
    valid_retrieval_evidence,
    valid_reverification_record,
    valid_semantic_review_record,
    valid_source_plan,
)


ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_governed_schema_inventory_is_strict(self) -> None:
        names = {
            "receipt", "amendment", "source-plan", "retrieval-evidence",
            "paragraph-map-record", "semantic-review-record", "human-approval",
            "reverification-record", "release-manifest",
            "governed-trust-evidence",
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
            "minimum": 10000,
            "target": 9000,
            "maximum": 8000,
            "content_standard": "evidence_led",
        }
        self.assertIn("length_contract must satisfy minimum <= target <= maximum", validate_brief(brief))

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
