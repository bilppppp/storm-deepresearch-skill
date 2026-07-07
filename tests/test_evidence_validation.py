from __future__ import annotations

import unittest

from scripts.contract_io import validate_claim_record
from scripts.validate_evidence import (
    compute_coverage,
    validate_absence_searches,
    validate_claim_closure,
    validate_material_capture_depth,
)
from tests.governed_fixtures import (
    valid_claim_v2,
    valid_report_outline_v2,
    valid_retrieval_manifest_v2,
    valid_source_v2,
)


class EvidenceValidationTests(unittest.TestCase):
    def test_maximal_material_claim_rejects_metadata_only_capture(self) -> None:
        claim = valid_claim_v2()
        manifest = valid_retrieval_manifest_v2()
        manifest.update({
            "capture_level": "metadata",
            "evidence_strength_ceiling": "background",
            "locator_type": "title",
            "locator": "title metadata",
        })
        self.assertIn(
            "maximal material claim C001 requires at least abstract-level or full-text evidence",
            validate_material_capture_depth([claim], [manifest]),
        )

    def test_claim_locator_cannot_use_another_candidate_version(self) -> None:
        claim = valid_claim_v2()
        source = valid_source_v2()
        first = valid_retrieval_manifest_v2()
        second = valid_retrieval_manifest_v2(2)
        second["source_id"] = "S001"
        claim["evidence_locators"][0].update({
            "snapshot_sha256": second["snapshot_sha256"],
            "excerpt": second["excerpt"],
        })
        errors = validate_claim_closure(
            [claim], [source], self.outline_for("C001"), [first, second]
        )
        self.assertIn("claim C001 capture candidate does not match source version", errors)

    def test_academic_source_must_be_bibliographically_verified(self) -> None:
        source = valid_source_v2(academic=True)
        source["bibliographic"]["status"] = "unverified"
        errors = validate_claim_closure(
            [valid_claim_v2()], [source], self.outline_for("C001"),
            [valid_retrieval_manifest_v2()],
        )
        self.assertIn("academic source S001 is not bibliographically verified", errors)

    def test_strong_fact_requires_strong_capture(self) -> None:
        claim = valid_claim_v2()
        source = valid_source_v2()
        manifest = valid_retrieval_manifest_v2()
        manifest["evidence_strength_ceiling"] = "medium"
        errors = validate_claim_closure(
            [claim], [source], self.outline_for("C001"), [manifest]
        )
        self.assertIn("claim C001 evidence strength strong exceeds capture ceiling medium", errors)

    def test_absence_claim_requires_bound_multi_surface_search(self) -> None:
        claim = valid_claim_v2()
        claim["claim_text"] = "No clinical trials were found for the intervention."
        claim["evidence_mode"] = "absence_search"
        claim["absence_search_id"] = "AS001"
        sources = [valid_source_v2(1), valid_source_v2(2)]
        manifests = [valid_retrieval_manifest_v2(1), valid_retrieval_manifest_v2(2)]
        search = {
            "schema_version": "2.0", "search_id": "AS001", "claim_id": "C001",
            "scope": "external", "aliases": ["term", "TERM"],
            "queries": [{
                "query_id": "Q001", "alias": "term", "surface": "ClinicalTrials.gov",
                "surface_class": "trial_registry", "source_id": "S001", "result_count": 0,
                "searched_at": manifests[0]["retrieved_at"],
            }],
            "conclusion": "No matching record was returned.",
            "limitations": "One surface cannot establish global absence.",
        }
        errors = validate_absence_searches(
            [claim], [search], sources, manifests,
            {"depth_level": "full_dossier", "retrieval_mode": "host", "high_stakes": False},
        )
        self.assertIn("absence search AS001 requires two independent discovery surfaces", errors)

    def test_unmarked_absence_language_is_rejected(self) -> None:
        claim = valid_claim_v2()
        claim["claim_text"] = "尚无人体临床试验证据。"
        errors = validate_absence_searches(
            [claim], [], [valid_source_v2()], [valid_retrieval_manifest_v2()],
            {"depth_level": "full_dossier", "retrieval_mode": "host", "high_stakes": True},
        )
        self.assertIn("material claim C001 uses absence language without absence_search evidence_mode", errors)

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
