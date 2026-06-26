from __future__ import annotations

import unittest

from scripts.report_traceability import (
    body_length,
    citation_index,
    extract_paragraphs,
    generate_references,
    has_handwritten_references,
    mapping_directives,
    quote_limit_errors,
    quoted_length,
    strip_mapping_comments,
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

    def test_chinese_source_key_uses_host_and_hash_fallback(self) -> None:
        source = valid_source_v2()
        source["author_or_org"] = "新华社"
        source["title"] = "中文标题"
        source["canonical_url"] = "https://www.news.cn/politics/2026/example.html"
        key = next(iter(citation_index([source])))
        self.assertNotEqual(key, "source-2026-source")
        self.assertRegex(key, r"^news-cn-2026-[0-9a-f]{6}$")

    def test_body_length_excludes_localized_reference_sections(self) -> None:
        report = (
            "# Title\n\n"
            "## Finding\n\n"
            "Body words only.\n\n"
            "## 参考文献\n\n"
            "reference padding " * 200
        )
        self.assertEqual(body_length(report, "words"), 5)
        self.assertEqual([paragraph.text for paragraph in extract_paragraphs(report)], ["Body words only."])

    def test_handwritten_localized_references_are_rejected(self) -> None:
        draft = "# 标题\n\n## 正文\n\n有效正文。\n\n## 资料来源\n\n[^fake]: invented\n"
        self.assertTrue(has_handwritten_references(draft))

    def test_body_length_excludes_blockquotes_and_limits_quote_padding(self) -> None:
        report = "# T\n\nBody words only.\n\n> " + "quoted padding " * 600
        self.assertEqual(body_length(report, "words"), 4)
        self.assertGreater(quoted_length(report, "words"), 500)
        self.assertTrue(quote_limit_errors(report, "words"))

    def test_storm_map_comments_are_stripped_and_parsed(self) -> None:
        draft = (
            "# T\n\n"
            "<!-- storm-map: claims=C001; sources=S001; citations=nist-2026-report; type=factual -->\n"
            "Mapped paragraph.[^nist-2026-report]\n"
        )
        self.assertNotIn("storm-map", strip_mapping_comments(draft))
        self.assertEqual(mapping_directives(draft)[0]["claim_ids"], ["C001"])
        self.assertEqual(extract_paragraphs(draft)[0].text, "Mapped paragraph.[^nist-2026-report]")


if __name__ == "__main__":
    unittest.main()
