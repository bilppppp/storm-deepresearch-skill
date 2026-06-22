from __future__ import annotations

import unittest

from scripts.contract_io import validate_claim_record
from scripts.validate_evidence import compute_coverage, validate_claim_closure
from tests.governed_fixtures import (
    valid_claim_v2,
    valid_report_outline_v2,
    valid_retrieval_manifest_v2,
    valid_source_v2,
)


class EvidenceValidationTests(unittest.TestCase):
    def test_valid_material_fact_closes(self) -> None:
        errors = validate_claim_closure(
            [valid_claim_v2()],
            [valid_source_v2()],
            self.outline_for("C001"),
            [valid_retrieval_manifest_v2()],
        )
        self.assertEqual(errors, [])

    def test_unknown_source_and_unmapped_material_claim_fail(self) -> None:
        claim = valid_claim_v2()
        claim["supporting_source_ids"] = ["S999"]
        errors = validate_claim_closure(
            [claim], [valid_source_v2()], self.outline_for(), [valid_retrieval_manifest_v2()]
        )
        self.assertTrue(any("unknown source_id S999" in item for item in errors))
        self.assertTrue(any("material claim C001 is not mapped" in item for item in errors))

    def test_current_claim_rejects_stale_support(self) -> None:
        source = valid_source_v2()
        source["freshness_status"] = "stale"
        errors = validate_claim_closure(
            [valid_claim_v2()], [source], self.outline_for("C001"),
            [valid_retrieval_manifest_v2()],
        )
        self.assertTrue(any("requires current evidence" in item for item in errors))

    def test_contested_claim_requires_contradicting_source(self) -> None:
        claim = valid_claim_v2(status="contested")
        errors = validate_claim_closure(
            [claim], [valid_source_v2()], self.outline_for("C001"),
            [valid_retrieval_manifest_v2()],
        )
        self.assertTrue(any("contested claim requires contradicting evidence" in item for item in errors))

    def test_inference_requires_supported_premise_ids(self) -> None:
        claim = valid_claim_v2(2, claim_type="inference", source_index=1)
        claim["premise_claim_ids"] = []
        self.assertIn("inference requires supported premise claims", validate_claim_record(claim))

    def test_locator_must_bind_retrieval_snapshot(self) -> None:
        claim = valid_claim_v2()
        claim["evidence_locators"][0]["snapshot_sha256"] = "f" * 64
        errors = validate_claim_closure(
            [claim], [valid_source_v2()], self.outline_for("C001"),
            [valid_retrieval_manifest_v2()],
        )
        self.assertTrue(any("snapshot hash mismatch" in item for item in errors))

    def test_unsupported_material_claim_fails_and_coverage_reports_it(self) -> None:
        claim = valid_claim_v2(status="unsupported")
        claim["supporting_source_ids"] = []
        claim["evidence_locators"] = []
        errors = validate_claim_closure(
            [claim], [valid_source_v2()], self.outline_for(), [valid_retrieval_manifest_v2()]
        )
        self.assertTrue(any("unsupported material claim" in item for item in errors))
        coverage = compute_coverage([claim])
        self.assertEqual(coverage["unsupported_material_claims"], 1)
        self.assertEqual(coverage["material_fact_closure"], 0.0)

    def outline_for(self, *claim_ids: str) -> dict[str, object]:
        outline = valid_report_outline_v2()
        outline["sections"] = [{
            "section_id": "SEC01",
            "title": "Finding",
            "purpose": "State bounded evidence.",
            "target_units": 500,
            "question_ids": ["Q001"],
            "claim_ids": list(claim_ids),
            "required_elements": ["claim", "evidence", "limitation"],
        }]
        return outline


if __name__ == "__main__":
    unittest.main()
