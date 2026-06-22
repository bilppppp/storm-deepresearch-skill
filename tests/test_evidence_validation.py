from __future__ import annotations

import unittest

from scripts.validate_evidence import compute_coverage, validate_claim_closure
from tests.test_contracts import valid_claim, valid_source


class EvidenceValidationTests(unittest.TestCase):
    def test_valid_material_fact_closes(self) -> None:
        errors = validate_claim_closure(
            [valid_claim()],
            [valid_source()],
            {"schema_version": "1.0", "mappings": [{"anchor": "finding-1", "fingerprint": "abc", "claim_ids": ["C001"]}]},
        )
        self.assertEqual(errors, [])

    def test_unknown_source_and_unmapped_material_claim_fail(self) -> None:
        claim = valid_claim()
        claim["supporting_source_ids"] = ["S999"]
        errors = validate_claim_closure([claim], [valid_source()], {"schema_version": "1.0", "mappings": []})
        self.assertTrue(any("unknown source_id S999" in item for item in errors))
        self.assertTrue(any("material claim C001 is not mapped" in item for item in errors))

    def test_current_claim_rejects_stale_support(self) -> None:
        source = valid_source()
        source["freshness_status"] = "stale"
        errors = validate_claim_closure(
            [valid_claim()],
            [source],
            {"schema_version": "1.0", "mappings": [{"anchor": "finding-1", "fingerprint": "abc", "claim_ids": ["C001"]}]},
        )
        self.assertTrue(any("requires current evidence" in item for item in errors))

    def test_contested_claim_requires_contradicting_source(self) -> None:
        claim = valid_claim()
        claim["status"] = "contested"
        errors = validate_claim_closure(
            [claim],
            [valid_source()],
            {"schema_version": "1.0", "mappings": [{"anchor": "finding-1", "fingerprint": "abc", "claim_ids": ["C001"]}]},
        )
        self.assertTrue(any("contested claim requires contradicting evidence" in item for item in errors))

    def test_unsupported_material_claim_fails_and_coverage_reports_it(self) -> None:
        claim = valid_claim()
        claim["status"] = "unsupported"
        claim["supporting_source_ids"] = []
        errors = validate_claim_closure([claim], [valid_source()], {"schema_version": "1.0", "mappings": []})
        self.assertTrue(any("unsupported material claim" in item for item in errors))
        coverage = compute_coverage([claim])
        self.assertEqual(coverage["unsupported_material_claims"], 1)
        self.assertEqual(coverage["material_fact_closure"], 0.0)


if __name__ == "__main__":
    unittest.main()
