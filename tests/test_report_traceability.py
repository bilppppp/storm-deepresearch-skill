from __future__ import annotations

import unittest

from scripts.report_traceability import (
    citation_index,
    extract_paragraphs,
    generate_references,
    validate_paragraph_hashes,
    validate_paragraph_record,
    validate_report_traceability,
)
from tests.governed_fixtures import (
    valid_claim_v2,
    valid_paragraph_map_record,
    valid_source_v2,
)


class ReportTraceabilityTests(unittest.TestCase):
    def test_references_are_generated_only_from_registered_sources(self) -> None:
        report = "# Title\n\n## Finding\n\nFact.[^fake]\n\n## References\n\n[^fake]: invented\n"
        paragraph = extract_paragraphs(report)[0]
        mapping = valid_paragraph_map_record(citation_keys=["fake"])
        mapping["paragraph_sha256"] = paragraph.sha256
        errors = validate_report_traceability(
            report, [mapping], [valid_claim_v2()], [valid_source_v2()]
        )
        self.assertIn("citation key fake is absent from source register", errors)

    def test_factual_paragraph_requires_claim_and_citation(self) -> None:
        mapping = valid_paragraph_map_record(
            paragraph_type="factual", claim_ids=[], citation_keys=[]
        )
        self.assertIn(
            "factual paragraph requires claims and citations",
            validate_paragraph_record(mapping),
        )

    def test_changed_paragraph_invalidates_mapping_hash(self) -> None:
        original = extract_paragraphs("# T\n\nOriginal fact.")[0]
        mapping = valid_paragraph_map_record()
        mapping["paragraph_sha256"] = original.sha256
        errors = validate_paragraph_hashes("# T\n\nChanged fact.", [mapping])
        self.assertIn("paragraph hash mismatch: paragraph:1", errors)

    def test_generated_references_use_stable_source_key(self) -> None:
        source = valid_source_v2()
        key = next(iter(citation_index([source])))
        draft = f"# Title\n\n## Finding\n\nSupported fact.[^{key}]\n"
        report = generate_references(draft, [source])
        self.assertIn("## References", report)
        self.assertIn(f"[^{key}]:", report)
        self.assertEqual(report, generate_references(draft, [source]))


if __name__ == "__main__":
    unittest.main()
