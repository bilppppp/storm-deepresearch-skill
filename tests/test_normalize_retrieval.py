from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.normalize_retrieval import (
    canonicalize_url,
    merge_source_ledger,
    normalize_retrieval_records,
)


class RetrievalNormalizationTests(unittest.TestCase):
    def test_canonicalize_url_removes_tracking_and_fragment(self) -> None:
        value = "HTTPS://www.NIST.GOV/report?utm_source=x&year=2026#results"
        self.assertEqual(canonicalize_url(value), "https://www.nist.gov/report?year=2026")

    def test_normalizer_computes_source_and_manifest_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = self.make_cache(Path(tmp))
            sources, manifests = normalize_retrieval_records(
                [valid_retrieval()], mode="host", cache_root=cache
            )
            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0]["source_id"], "S001")
            self.assertEqual(sources[0]["content_hash"], manifests[0]["snapshot_sha256"])
            self.assertEqual(manifests[0]["source_id"], "S001")

    def test_mode_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = self.make_cache(Path(tmp))
            record = valid_retrieval()
            record["adapter"] = "provider"
            with self.assertRaisesRegex(ValueError, "not allowed in host mode"):
                normalize_retrieval_records([record], mode="host", cache_root=cache)

    def test_merge_source_ledger_preserves_existing_ids(self) -> None:
        existing = valid_source("S007", "https://www.nist.gov/existing")
        incoming = valid_source("S001", "https://www.nist.gov/new")
        merged = merge_source_ledger([existing], [incoming])
        self.assertEqual([item["source_id"] for item in merged], ["S007", "S008"])
        self.assertEqual(merged[0], existing)

    def test_internal_cli_writes_only_caller_selected_staging_files(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            cache = self.make_cache(temporary)
            output = temporary / "staging-output"
            input_path = temporary / "retrieval.jsonl"
            input_path.write_text(json.dumps(valid_retrieval()) + "\n", encoding="utf-8")
            result = subprocess.run(
                [
                    str(root / ".venv/bin/python"),
                    str(root / "scripts/normalize_retrieval.py"),
                    str(input_path), "--mode", "host", "--cache-root", str(cache),
                    "--output-dir", str(output),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output / "source-records.jsonl").is_file())
            self.assertTrue((output / "retrieval-manifest.jsonl").is_file())
            self.assertFalse((output / "state").exists())

    def make_cache(self, root: Path) -> Path:
        cache = root / "cache"
        cache.mkdir()
        (cache / "source.txt").write_text(
            "The report states the governed result. Additional inspectable context.",
            encoding="utf-8",
        )
        return cache


def valid_retrieval() -> dict[str, object]:
    return {
        "query_id": "Q001",
        "url": "https://www.nist.gov/test-fixtures/research-report",
        "final_url": "https://www.nist.gov/test-fixtures/research-report",
        "file_ref": None,
        "title": "Official report",
        "publisher": "National Institute of Standards and Technology",
        "published_at": "2026-05-01",
        "publication_date_status": "known",
        "retrieved_at": "2026-06-23T00:00:00Z",
        "content_excerpt": "The report states the governed result.",
        "content_locator": "p:1",
        "locator_type": "paragraph",
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


def valid_source(source_id: str, url: str) -> dict[str, object]:
    return {
        "source_id": source_id,
        "title": "Official source",
        "author_or_org": "NIST",
        "canonical_url": url,
        "file_ref": None,
        "published_at": "2026-05-01",
        "publication_date_status": "known",
        "retrieved_at": "2026-06-23T00:00:00Z",
        "source_type": "official",
        "primary_class": "primary",
        "reliability_tier": "A",
        "freshness_status": "current",
        "reliability_notes": "First-party source with inspectable full text.",
        "content_hash": "a" * 64,
    }


if __name__ == "__main__":
    unittest.main()
