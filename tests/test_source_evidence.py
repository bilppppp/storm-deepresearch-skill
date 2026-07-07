from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.source_evidence import (
    SourceEvidenceError,
    capture_retrieval_evidence,
    validate_audit_snapshot,
    validate_candidate_snapshots,
    validate_public_url,
    validate_retrieval_evidence,
    validate_search_request_snapshot,
)
from scripts.harness_io import sha256_file
from tests.governed_fixtures import valid_candidate_record, valid_search_run_record


class SourceEvidenceTests(unittest.TestCase):
    def test_audit_snapshot_hash_must_match(self) -> None:
        record = valid_search_run_record()
        record["raw_artifact"] = "source.txt"
        record["snapshot_sha256"] = "0" * 64
        self.assertIn(
            "snapshot_sha256 does not match audit artifact",
            validate_audit_snapshot(record, self.cache),
        )

    def test_candidate_resolver_snapshot_must_exist(self) -> None:
        candidate = valid_candidate_record()
        candidate["resolver_outcomes"][0]["raw_artifact"] = "missing.json"
        errors = validate_candidate_snapshots(candidate, self.cache)
        self.assertTrue(any("snapshot file is missing" in item for item in errors))

    def test_search_request_snapshot_must_match_declared_query(self) -> None:
        record = valid_search_run_record()
        request = self.cache / str(record["request_artifact"])
        request.write_text(
            '{"query_id":"Q001","surface":"OpenAlex","query":"different",'
            '"aliases":["governed research","auditable research"]}\n',
            encoding="utf-8",
        )
        record["request_sha256"] = sha256_file(request)
        self.assertIn(
            "search request artifact query does not match search_run",
            validate_search_request_snapshot(record, self.cache),
        )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.cache = Path(self.temporary.name)
        (self.cache / "source.txt").write_text(
            "Directly inspectable evidence excerpt. Additional context.",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_reserved_example_domain_is_rejected(self) -> None:
        record = self.valid_input()
        record["url"] = "https://example.com/fake-paper"
        record["final_url"] = record["url"]
        with self.assertRaisesRegex(SourceEvidenceError, "reserved or placeholder domain"):
            capture_retrieval_evidence(record, self.cache)

    def test_internal_placeholder_domain_is_rejected(self) -> None:
        record = self.valid_input()
        record["url"] = "https://local-corpus.internal/movie-transcript"
        record["final_url"] = record["url"]
        with self.assertRaisesRegex(SourceEvidenceError, "reserved or placeholder domain"):
            capture_retrieval_evidence(record, self.cache)

    def test_wikipedia_cannot_be_promoted_to_primary_tier_a(self) -> None:
        record = self.valid_input()
        record["url"] = "https://en.wikipedia.org/wiki/Test_fixture"
        record["final_url"] = record["url"]
        record["source_type"] = "official"
        record["primary_class"] = "primary"
        record["reliability_tier"] = "A"
        with self.assertRaisesRegex(SourceEvidenceError, "Wikipedia sources must use source_type encyclopedia"):
            capture_retrieval_evidence(record, self.cache)

    def test_excerpt_must_exist_in_captured_content(self) -> None:
        record = capture_retrieval_evidence(self.valid_input(), self.cache)
        record["excerpt"] = "invented excerpt"
        errors = validate_retrieval_evidence(record, self.cache)
        self.assertIn("excerpt is absent from captured content", errors)

    def test_search_snippet_cannot_be_strong(self) -> None:
        record = self.valid_input()
        record["capture_level"] = "search_snippet"
        record["evidence_strength_ceiling"] = "strong"
        with self.assertRaisesRegex(SourceEvidenceError, "search snippet cannot be strong evidence"):
            capture_retrieval_evidence(record, self.cache)

    def test_private_network_url_is_rejected(self) -> None:
        errors = validate_public_url("http://127.0.0.1/private")
        self.assertIn("private or reserved network address", errors)

    def test_caller_supplied_hashes_are_recomputed(self) -> None:
        record = self.valid_input()
        record["snapshot_sha256"] = "0" * 64
        record["normalized_text_sha256"] = "0" * 64
        captured = capture_retrieval_evidence(record, self.cache)
        self.assertNotEqual(captured["snapshot_sha256"], "0" * 64)
        self.assertNotEqual(captured["normalized_text_sha256"], "0" * 64)
        self.assertEqual(validate_retrieval_evidence(captured, self.cache), [])

    def test_snapshot_symlink_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            outside_file = Path(outside) / "outside.txt"
            outside_file.write_text("Directly inspectable evidence excerpt.", encoding="utf-8")
            (self.cache / "escape.txt").symlink_to(outside_file)
            record = self.valid_input()
            record["raw_artifact"] = "escape.txt"
            with self.assertRaisesRegex(SourceEvidenceError, "escapes evidence cache"):
                capture_retrieval_evidence(record, self.cache)

    def valid_input(self) -> dict[str, object]:
        return {
            "record_kind": "capture",
            "candidate_id": "K001",
            "search_run_ids": ["SR001"],
            "query_id": "Q001",
            "url": "https://www.nist.gov/test-fixtures/research-report",
            "final_url": "https://www.nist.gov/test-fixtures/research-report",
            "file_ref": None,
            "title": "Official research report",
            "publisher": "National Institute of Standards and Technology",
            "published_at": "2026-05-01",
            "publication_date_status": "known",
            "retrieved_at": "2026-06-23T00:00:00Z",
            "content_excerpt": "Directly inspectable evidence excerpt.",
            "content_locator": "p:1",
            "adapter": "host",
            "adapter_run_id": "host-run-1",
            "capture_level": "full_text",
            "evidence_strength_ceiling": "strong",
            "raw_artifact": "source.txt",
            "observed_status": 200,
            "content_type": "text/plain",
            "source_type": "official",
            "primary_class": "primary",
            "reliability_tier": "A",
            "freshness_status": "current",
            "reliability_notes": "First-party source with inspectable full text.",
        }


if __name__ == "__main__":
    unittest.main()
