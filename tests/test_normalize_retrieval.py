from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.normalize_retrieval import (
    canonicalize_url,
    merge_source_ledger,
    merge_source_records,
    normalize_retrieval_record,
)


class RetrievalNormalizationTests(unittest.TestCase):
    def test_canonicalize_url_removes_tracking_and_fragment(self) -> None:
        value = "HTTPS://Example.COM/report?utm_source=x&year=2026#results"
        self.assertEqual(canonicalize_url(value), "https://example.com/report?year=2026")

    def test_host_record_requires_provenance_and_retrieval_time(self) -> None:
        record = {
            "query_id": "Q001",
            "title": "Untimed result",
            "publisher": "Example",
            "adapter": "host",
            "content_excerpt": "Evidence",
        }
        with self.assertRaisesRegex(ValueError, "url or file_ref"):
            normalize_retrieval_record(record, "host")

    def test_mode_mismatch_is_rejected(self) -> None:
        record = valid_retrieval()
        record["adapter"] = "provider"
        with self.assertRaisesRegex(ValueError, "not allowed in host mode"):
            normalize_retrieval_record(record, "host")

    def test_merge_deduplicates_and_assigns_stable_ids(self) -> None:
        one = normalize_retrieval_record(valid_retrieval(), "host")
        duplicate_payload = valid_retrieval()
        duplicate_payload["url"] = "https://example.org/report#section-two"
        two = normalize_retrieval_record(duplicate_payload, "host")
        merged = merge_source_records([two, one])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source_id"], "S001")
        self.assertEqual(merged[0]["canonical_url"], "https://example.org/report")

    def test_cli_writes_canonical_source_jsonl(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "package"
            output_path = package / "research" / "source-register.jsonl"
            output_path.parent.mkdir(parents=True)
            output_path.write_text("", encoding="utf-8")
            input_path = Path(tmp) / "retrieval.jsonl"
            input_path.write_text(json.dumps(valid_retrieval()) + "\n", encoding="utf-8")
            result = subprocess.run(
                [
                    str(root / ".venv" / "bin" / "python"),
                    str(root / "scripts" / "normalize_retrieval.py"),
                    str(input_path), "--mode", "host", "--package", str(package),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            record = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(record["source_id"], "S001")

    def test_merge_source_ledger_preserves_existing_ids_and_records(self) -> None:
        existing = {
            "source_id": "S007",
            "title": "Existing source",
            "author_or_org": "Existing Org",
            "canonical_url": "https://example.org/existing",
            "file_ref": "",
            "published_at": "2025-01-01",
            "retrieved_at": "2026-06-20T10:00:00+08:00",
            "source_type": "official",
            "primary_class": "primary",
            "reliability_tier": "A",
            "freshness_status": "current",
            "reliability_notes": "Existing evidence",
            "content_hash": "abc",
        }
        incoming = normalize_retrieval_record(valid_retrieval(), "host")
        merged = merge_source_ledger([existing], [incoming])
        self.assertEqual([item["source_id"] for item in merged], ["S007", "S008"])
        self.assertEqual(merged[0], existing)

    def test_failed_normalization_does_not_change_existing_ledger(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "package"
            ledger = package / "research" / "source-register.jsonl"
            ledger.parent.mkdir(parents=True)
            original = '{"source_id":"S001","canonical_url":"https://example.org/old"}\n'
            ledger.write_text(original, encoding="utf-8")
            input_path = Path(tmp) / "retrieval.jsonl"
            input_path.write_text("not-json\n", encoding="utf-8")
            result = subprocess.run(
                [
                    str(root / ".venv" / "bin" / "python"),
                    str(root / "scripts" / "normalize_retrieval.py"),
                    str(input_path), "--mode", "host", "--package", str(package),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 4)
            self.assertEqual(ledger.read_text(encoding="utf-8"), original)


def valid_retrieval() -> dict[str, object]:
    return {
        "query_id": "Q001",
        "url": "https://example.org/report",
        "title": "Official report",
        "publisher": "Example Org",
        "published_at": "2026-05-01",
        "retrieved_at": "2026-06-21T10:00:00+08:00",
        "content_excerpt": "The report states the result.",
        "content_locator": "section 1",
        "adapter": "host",
        "source_type": "official",
        "primary_class": "primary",
        "reliability_tier": "A",
        "freshness_status": "current",
        "reliability_notes": "First-party source",
    }


if __name__ == "__main__":
    unittest.main()
