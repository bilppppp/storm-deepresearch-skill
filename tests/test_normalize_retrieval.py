from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import scripts.normalize_retrieval as normalize_retrieval
from scripts.normalize_retrieval import (
    canonicalize_url,
    derive_bibliographic_status,
    independent_source_identity,
    merge_source_ledger,
    normalize_retrieval_records,
    validate_retrieval_audit,
    validate_version_families,
)
from scripts.harness_io import sha256_file
from tests.governed_fixtures import (
    valid_candidate_record,
    valid_capture_input,
    valid_gap_assessment_record,
    valid_search_run_record,
    valid_search_wave_record,
    valid_source_v2,
    valid_brief_v2,
    valid_source_plan,
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

    def test_normalizer_preserves_search_wave_and_validates_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache, records = self.make_academic_cache(Path(tmp))
            records.append(valid_search_wave_record(
                search_run_ids=["SR001"], new_candidate_ids=["K001"]
            ))
            _sources, _manifests, audit = normalize_retrieval_records(
                records, mode="host", cache_root=cache
            )
            wave = next(row for row in audit if row["record_kind"] == "search_wave")
            self.assertEqual(wave["wave_id"], "WAVE001")
            records[-1]["search_run_ids"] = ["SR999"]
            with self.assertRaisesRegex(ValueError, "unknown search runs"):
                normalize_retrieval_records(records, mode="host", cache_root=cache)

    def test_normalizer_preserves_gap_assessment_and_validates_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache, records = self.make_academic_cache(Path(tmp))
            second = valid_search_run_record(2, pass_kind="gap_fill")
            self.bind_search_request(cache, second)
            (cache / "search-2.json").write_text('{"results":[]}\n', encoding="utf-8")
            second["raw_artifact"] = "search-2.json"
            second["snapshot_sha256"] = sha256_file(cache / "search-2.json")
            first_wave = valid_search_wave_record(1, search_run_ids=["SR001"])
            second_wave = valid_search_wave_record(2, search_run_ids=["SR002"])
            assessment = valid_gap_assessment_record()
            records.extend([second, first_wave, second_wave, assessment])
            _sources, _manifests, audit = normalize_retrieval_records(
                records, mode="host", cache_root=cache
            )
            self.assertTrue(any(row["record_kind"] == "gap_assessment" for row in audit))
            assessment["supporting_wave_ids"] = ["WAVE999"]
            with self.assertRaisesRegex(ValueError, "unknown search waves"):
                normalize_retrieval_records(records, mode="host", cache_root=cache)

    def test_unreachable_is_not_reduced_to_unmatched(self) -> None:
        candidate = valid_candidate_record()
        for outcome in candidate["resolver_outcomes"]:
            outcome.update({
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

    def test_same_bibliographic_identity_cannot_split_across_version_families(self) -> None:
        first = valid_candidate_record(1)
        second = valid_candidate_record(2)
        second["identifiers"]["doi"] = first["identifiers"]["doi"]
        errors = validate_version_families([first, second])
        self.assertIn(
            "bibliographic identity doi:10.5555/storm.1 spans multiple version families",
            errors,
        )

    def test_different_queries_cannot_reuse_one_search_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache, records = self.make_academic_cache(Path(tmp))
            second = valid_search_run_record(2)
            self.bind_search_request(cache, second)
            second["raw_artifact"] = "search-1.json"
            second["snapshot_sha256"] = sha256_file(cache / "search-1.json")
            records.insert(1, second)
            with self.assertRaisesRegex(
                ValueError,
                "search response snapshot is reused across different executed queries",
            ):
                normalize_retrieval_records(records, mode="host", cache_root=cache)

    def test_saturation_cannot_reuse_search_runs_as_two_waves(self) -> None:
        search = valid_search_run_record(1, pass_kind="gap_fill")
        first_wave = valid_search_wave_record(1, search_run_ids=["SR001"])
        second_wave = valid_search_wave_record(2, search_run_ids=["SR001"])
        assessment = valid_gap_assessment_record(
            supporting_search_run_ids=["SR001"],
        )
        errors = validate_retrieval_audit(
            [search, first_wave, second_wave, assessment],
            [],
            [],
            valid_source_plan(),
            valid_brief_v2(),
        )
        self.assertIn(
            "gap assessment GA001 saturation waves must use disjoint search runs",
            errors,
        )

    def test_gap_assessment_accepts_missing_review_concern_at_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            records = [
                valid_search_run_record(1, pass_kind="gap_fill"),
                valid_search_wave_record(1, search_run_ids=["SR001"], new_candidate_ids=[]),
                valid_search_wave_record(2, search_run_ids=["SR001"], new_candidate_ids=[]),
                valid_gap_assessment_record(supporting_search_run_ids=["SR001"]),
            ]
            records[-1].pop("review_concern_id", None)
            for record in records:
                if record.get("record_kind") == "search_run":
                    artifact = workspace / str(record["raw_artifact"])
                    artifact.write_text('{"results":[]}\n', encoding="utf-8")
                    record["snapshot_sha256"] = sha256_file(artifact)
                    request = workspace / str(record["request_artifact"])
                    request.write_text('{"query":"gap"}\n', encoding="utf-8")
                    record["request_sha256"] = sha256_file(request)
            errors = []
            for record in records:
                errors.extend(normalize_retrieval.validate_retrieval_input_record(record))
            self.assertEqual(errors, [])

    def test_search_wave_allows_null_material_delta_for_pre_findings_retrieval(self) -> None:
        record = valid_search_wave_record(1, search_run_ids=["SR001"], new_candidate_ids=["K001"])
        record["material_delta"] = None
        self.assertEqual(normalize_retrieval.validate_retrieval_input_record(record), [])

    def test_saturation_waves_require_sequential_gap_fill_searches(self) -> None:
        first = valid_search_run_record(1)
        second = valid_search_run_record(2)
        first_wave = valid_search_wave_record(1, search_run_ids=["SR001"])
        second_wave = valid_search_wave_record(2, search_run_ids=["SR002"])
        second_wave["created_at"] = first_wave["created_at"]
        assessment = valid_gap_assessment_record()
        errors = validate_retrieval_audit(
            [first, second, first_wave, second_wave, assessment],
            [],
            [],
            valid_source_plan(),
            valid_brief_v2(),
        )
        self.assertIn(
            "gap assessment GA001 saturation requires sequential gap_fill waves",
            errors,
        )

    def test_access_limited_gap_assessment_accepts_unreachable_search_run(self) -> None:
        search = valid_search_run_record(1, pass_kind="gap_fill")
        search["execution_status"] = "unreachable"
        search["result_count"] = None
        search["limitations"] = ["Resolver DNS failed in the captured host context."]
        wave = valid_search_wave_record(1, search_run_ids=["SR001"], new_candidate_ids=[])
        assessment = valid_gap_assessment_record(
            terminal_state="access_limited_uncertainty",
            supporting_wave_ids=["WAVE001"],
            supporting_search_run_ids=["SR001"],
        )
        assessment["raw_result_count"] = 0
        assessment["deduplicated_candidate_count"] = 0
        errors = validate_retrieval_audit(
            [search, wave, assessment],
            [],
            [],
            valid_source_plan(),
            valid_brief_v2(),
        )
        self.assertNotIn(
            "gap assessment GA001 raw result count does not recompute",
            errors,
        )
        self.assertNotIn(
            "gap assessment GA001 lacks an unreachable search run",
            errors,
        )

    def test_captured_execution_rejects_summary_only_search_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            transcript = cache / "search-1.txt"
            transcript.write_text(
                "Captured search transcript. Results summarized in candidate records.\n",
                encoding="utf-8",
            )
            search = valid_search_run_record()
            search["raw_artifact"] = transcript.name
            search["snapshot_sha256"] = sha256_file(transcript)
            validator = getattr(
                normalize_retrieval,
                "validate_captured_retrieval_artifacts",
                lambda *_args, **_kwargs: [],
            )
            errors = validator([search], cache)
            self.assertIn(
                "search run SR001 response must be structured JSON with inspectable result rows",
                errors,
            )

    def test_captured_execution_rejects_resolver_without_returned_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            resolver = cache / "openalex-1.json"
            resolver.write_text(
                json.dumps({"matched": True, "title": "Governed Research Source 1"}),
                encoding="utf-8",
            )
            candidate = valid_candidate_record()
            candidate["resolver_outcomes"] = [candidate["resolver_outcomes"][1]]
            candidate["resolver_outcomes"][0]["raw_artifact"] = resolver.name
            candidate["resolver_outcomes"][0]["snapshot_sha256"] = sha256_file(resolver)
            validator = getattr(
                normalize_retrieval,
                "validate_captured_retrieval_artifacts",
                lambda *_args, **_kwargs: [],
            )
            errors = validator([candidate], cache)
            self.assertIn(
                "candidate K001 resolver openalex raw response does not contain matched_identifier W1",
                errors,
            )

    def test_captured_execution_rejects_result_count_without_candidate_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            response = cache / "search-1.json"
            response.write_text(
                json.dumps({"results": [
                    {"title": "Governed Research Source 1", "url": "https://doi.org/10.5555/storm.1"},
                    {"title": "Unscreened result", "url": "https://doi.org/10.5555/unscreened"},
                ]}),
                encoding="utf-8",
            )
            search = valid_search_run_record()
            search["result_count"] = 2
            search["raw_artifact"] = response.name
            search["snapshot_sha256"] = sha256_file(response)
            candidate = valid_candidate_record()
            errors = normalize_retrieval.validate_captured_retrieval_artifacts(
                [search, candidate], cache
            )
            self.assertIn(
                "search run SR001 returned 2 rows but only 1 candidate records are screened",
                errors,
            )

    def test_captured_execution_requires_public_identity_in_search_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            response = cache / "search-1.json"
            response.write_text(json.dumps({"results": ["K001"]}), encoding="utf-8")
            search = valid_search_run_record()
            search["raw_artifact"] = response.name
            search["snapshot_sha256"] = sha256_file(response)
            candidate = valid_candidate_record()
            errors = normalize_retrieval.validate_captured_retrieval_artifacts(
                [search, candidate], cache
            )
            self.assertIn(
                "search run SR001 raw results do not expose a public identity for candidate K001",
                errors,
            )

    def test_captured_execution_rejects_placeholder_cross_index_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            resolver = cache / "openalex-1.json"
            resolver.write_text(json.dumps({"id": "W000000001"}), encoding="utf-8")
            candidate = valid_candidate_record()
            candidate["identifiers"]["openalex_id"] = "W000000001"
            candidate["resolver_outcomes"] = [candidate["resolver_outcomes"][1]]
            candidate["resolver_outcomes"][0].update({
                "matched_identifier": "W000000001",
                "raw_artifact": resolver.name,
                "snapshot_sha256": sha256_file(resolver),
            })
            errors = normalize_retrieval.validate_captured_retrieval_artifacts(
                [candidate], cache
            )
            self.assertIn(
                "candidate K001 resolver openalex uses an invalid OpenAlex work identifier",
                errors,
            )

    def test_maximal_academic_candidate_requires_cross_index_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache, records = self.make_academic_cache(Path(tmp))
            sources, manifests, audit = normalize_retrieval_records(
                records, mode="host", cache_root=cache
            )
            candidate = next(row for row in audit if row["record_kind"] == "candidate")
            candidate["resolver_outcomes"] = candidate["resolver_outcomes"][:1]
            brief = valid_brief_v2()
            brief.update({
                "research_profile": "maximal_full_dossier",
                "length_contract": {
                    "unit": "chinese_characters",
                    "policy": "open_ended",
                    "content_standard": "evidence_led",
                },
            })
            errors = validate_retrieval_audit(
                audit, manifests, sources, valid_source_plan(), brief
            )
            self.assertIn(
                "maximal academic candidate K001 requires at least two matched independent resolvers",
                errors,
            )
            self.assertIn(
                "maximal academic candidate K001 requires OpenAlex or Semantic Scholar cross-index resolution",
                errors,
            )

    def test_same_source_preserves_multiple_query_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache, records = self.make_academic_cache(root)
            search = valid_search_run_record(2)
            candidate = next(row for row in records if row["record_kind"] == "candidate")
            (cache / "search-2.json").write_text(
                json.dumps({"results": [self.search_result_row(candidate)]}) + "\n",
                encoding="utf-8",
            )
            search["snapshot_sha256"] = sha256_file(cache / "search-2.json")
            self.bind_search_request(cache, search)
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
        candidate = valid_candidate_record()
        (cache / "search-1.json").write_text(
            json.dumps({"results": [self.search_result_row(candidate)]}) + "\n",
            encoding="utf-8",
        )
        (cache / "crossref-1.json").write_text('{"doi":"10.5555/storm.1"}\n', encoding="utf-8")
        (cache / "openalex-1.json").write_text('{"id":"W1"}\n', encoding="utf-8")
        (cache / "semantic-scholar-1.json").write_text(
            json.dumps({"paperId": candidate["identifiers"]["semantic_scholar_id"]}) + "\n",
            encoding="utf-8",
        )
        search = valid_search_run_record()
        capture = valid_capture_input()
        search["snapshot_sha256"] = sha256_file(cache / "search-1.json")
        self.bind_search_request(cache, search)
        candidate["resolver_outcomes"][0]["snapshot_sha256"] = sha256_file(
            cache / "crossref-1.json"
        )
        candidate["resolver_outcomes"][1]["snapshot_sha256"] = sha256_file(
            cache / "openalex-1.json"
        )
        candidate["resolver_outcomes"][2]["snapshot_sha256"] = sha256_file(
            cache / "semantic-scholar-1.json"
        )
        return cache, [search, candidate, capture]

    def search_result_row(self, candidate: dict[str, object]) -> dict[str, object]:
        return {
            "title": candidate["title"],
            "url": candidate["url"],
            "identifiers": candidate["identifiers"],
        }

    def bind_search_request(
        self, cache: Path, search: dict[str, object]
    ) -> None:
        request = cache / str(search["request_artifact"])
        request.write_text(json.dumps({
            "query_id": search["query_id"],
            "surface": search["surface"],
            "query": search["query"],
            "aliases": search["aliases"],
        }) + "\n", encoding="utf-8")
        search["request_sha256"] = sha256_file(request)


if __name__ == "__main__":
    unittest.main()
