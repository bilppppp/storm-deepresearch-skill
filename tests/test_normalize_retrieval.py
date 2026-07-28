from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.normalize_retrieval import (
    canonicalize_url,
    derive_bibliographic_status,
    independent_source_identity,
    merge_source_ledger,
    normalize_retrieval_records,
    validate_version_families,
)
from scripts.harness_io import sha256_file
from tests.governed_fixtures import (
    valid_candidate_record,
    valid_capture_input,
    valid_crossref_response,
    valid_search_run_record,
    valid_source_v2,
)


class RetrievalNormalizationTests(unittest.TestCase):
    def test_normalizer_splits_audit_capture_and_source_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache, records = self.make_academic_cache(root)
            sources, manifests, audit = normalize_retrieval_records(
                records, mode="host", cache_root=cache
            )
            self.assertEqual(len(sources), 1)
            self.assertEqual(len(manifests), 1)
            self.assertEqual({row["record_kind"] for row in audit}, {"search_run", "candidate"})
            self.assertEqual(sources[0]["bibliographic"]["status"], "verified")

    def test_unreachable_is_not_reduced_to_unmatched(self) -> None:
        candidate = valid_candidate_record()
        candidate["resolver_outcomes"][0].update({
            "status": "unreachable",
            "metadata_match": False,
            "matched_identifier": None,
            "returned_title": None,
            "returned_authors": [],
            "returned_year": None,
        })
        self.assertEqual(derive_bibliographic_status(candidate), "unverified")

    def test_fuzzy_relationship_cannot_merge_version_family(self) -> None:
        first = valid_candidate_record(1)
        second = valid_candidate_record(2)
        second["version_family_id"] = first["version_family_id"]
        second["relationship_basis"] = "unresolved"
        errors = validate_version_families([first, second])
        self.assertIn("W001 contains an unresolved version relationship", errors)

    def test_same_source_preserves_multiple_query_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache, records = self.make_academic_cache(root)
            search = valid_search_run_record(2)
            (cache / "search-2.json").write_text('{"results":["K001"]}\n', encoding="utf-8")
            search["snapshot_sha256"] = sha256_file(cache / "search-2.json")
            candidate = next(row for row in records if row["record_kind"] == "candidate")
            candidate["search_run_ids"].append("SR002")
            capture = valid_capture_input(2)
            capture["candidate_id"] = "K001"
            capture["url"] = capture["final_url"] = "https://doi.org/10.5555/storm.1"
            (cache / "source-2.txt").write_text(
                "Directly inspectable evidence excerpt 2. Additional context.", encoding="utf-8"
            )
            records.extend([search, capture])
            sources, manifests, audit = normalize_retrieval_records(
                records, mode="host", cache_root=cache
            )
            self.assertEqual(len(sources), 1)
            self.assertEqual({item["query_id"] for item in manifests}, {"Q001", "Q002"})
            self.assertEqual({item["source_id"] for item in manifests}, {"S001"})
            self.assertEqual(len([item for item in audit if item["record_kind"] == "candidate"]), 1)

    def test_canonicalize_url_removes_tracking_and_fragment(self) -> None:
        value = "HTTPS://www.NIST.GOV/report?utm_source=x&year=2026#results"
        self.assertEqual(canonicalize_url(value), "https://www.nist.gov/report?year=2026")

    def test_normalizer_computes_source_and_manifest_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache, records = self.make_academic_cache(Path(tmp))
            sources, manifests, _audit = normalize_retrieval_records(
                records, mode="host", cache_root=cache
            )
            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0]["source_id"], "S001")
            self.assertEqual(sources[0]["content_hash"], manifests[0]["snapshot_sha256"])
            self.assertEqual(manifests[0]["source_id"], "S001")

    def test_mode_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache, records = self.make_academic_cache(Path(tmp))
            records[0]["adapter"] = "provider"
            with self.assertRaisesRegex(ValueError, "not allowed in host mode"):
                normalize_retrieval_records(records, mode="host", cache_root=cache)

    def test_merge_source_ledger_preserves_existing_ids(self) -> None:
        existing = valid_source_v2(7)
        existing["canonical_url"] = "https://www.nist.gov/existing"
        incoming = valid_source_v2(1)
        incoming["canonical_url"] = "https://www.nist.gov/new"
        merged = merge_source_ledger([existing], [incoming])
        self.assertEqual([item["source_id"] for item in merged], ["S007", "S008"])
        self.assertEqual(merged[0], existing)

    def test_internal_cli_writes_only_caller_selected_staging_files(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            cache, records = self.make_academic_cache(temporary)
            output = temporary / "staging-output"
            input_path = temporary / "retrieval.jsonl"
            input_path.write_text(
                "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
            )
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
            self.assertTrue((output / "retrieval-audit.jsonl").is_file())
            self.assertFalse((output / "state").exists())

    def make_academic_cache(
        self, root: Path
    ) -> tuple[Path, list[dict[str, object]]]:
        cache = root / "cache"
        cache.mkdir()
        (cache / "source-1.txt").write_text(
            "Directly inspectable evidence excerpt 1. Additional inspectable context.",
            encoding="utf-8",
        )
        (cache / "search-1.json").write_text('{"results":["K001"]}\n', encoding="utf-8")
        (cache / "crossref-1.json").write_text(
            json.dumps(valid_crossref_response()) + "\n", encoding="utf-8"
        )
        search = valid_search_run_record()
        candidate = valid_candidate_record()
        capture = valid_capture_input()
        search["snapshot_sha256"] = sha256_file(cache / "search-1.json")
        candidate["resolver_outcomes"][0]["snapshot_sha256"] = sha256_file(
            cache / "crossref-1.json"
        )
        return cache, [search, candidate, capture]


if __name__ == "__main__":
    unittest.main()
