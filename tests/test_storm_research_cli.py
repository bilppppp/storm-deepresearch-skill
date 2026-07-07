from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.governed_fixtures import (
    valid_adapter_record,
    valid_candidate_record,
    valid_capture_input,
    valid_gap_assessment_record,
    valid_research_plan_v2,
    valid_source_plan,
    valid_search_run_record,
    valid_search_wave_record,
    valid_storm_lens_artifact,
)
from scripts.harness_io import sha256_file
from scripts.storm_research import (
    findings_coverage,
    validate_maximal_saturation,
    validate_plan_bundle,
    validate_retrieval_depth,
)


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "storm_research.py"


class StormResearchCLITests(unittest.TestCase):
    def test_corpus_seeded_search_requires_pass_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            baseline = next(
                row for row in rows
                if row.get("record_kind") == "search_run" and row.get("query_id") == "Q001"
            )
            base = datetime.fromisoformat(str(baseline["searched_at"]).replace("Z", "+00:00"))
            cache = run / "work/generations/g0001/evidence-cache"
            for search_id, pass_kind, offset in (
                ("SR011", "corpus", 2),
                ("SR012", "gap_fill", 3),
            ):
                artifact = cache / f"{search_id}.json"
                artifact.write_text('{"results":[]}\n', encoding="utf-8")
                row = valid_search_run_record(1, pass_kind=pass_kind)
                row.update({
                    "search_run_id": search_id,
                    "request_artifact": f"request-{search_id}.json",
                    "raw_artifact": artifact.name,
                    "snapshot_sha256": sha256_file(artifact),
                    "searched_at": (base + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z"),
                })
                self.bind_search_request(cache, row)
                rows.append(row)
            inputs.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 5)
            self.assertIn("Q001 search passes are out of order", result.stderr)

    def test_closed_corpus_accepts_local_audit_and_rejects_external_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace, profile="closed_corpus")
            inputs = self.write_closed_corpus_inputs(run, workspace)
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace, profile="closed_corpus")
            inputs = self.write_closed_corpus_inputs(run, workspace)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            search = next(row for row in rows if row.get("record_kind") == "search_run")
            search.update({"surface": "OpenAlex", "surface_class": "scholarly_index"})
            self.bind_search_request(
                run / "work/generations/g0001/evidence-cache", search
            )
            inputs.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 5)
            self.assertIn("closed_corpus forbids external search runs", result.stderr)

    def test_full_dossier_requires_academic_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            for row in rows:
                if row.get("record_kind") == "search_run":
                    row["pass_kind"] = "counterevidence"
            inputs.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 5)
            self.assertIn("full_dossier requires a completed academic baseline", result.stderr)

    def test_ingest_rejects_missing_source_plan_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            for row in rows:
                if row.get("surface_class") == "publisher_full_text":
                    row["surface"] = "Unrelated archive"
                    row["surface_class"] = "unrelated_archive"
                    self.bind_search_request(
                        run / "work/generations/g0001/evidence-cache", row
                    )
            inputs.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 5)
            self.assertIn("lacks required source-plan surfaces", result.stderr)

    def test_ingest_accepts_registry_surface_synonyms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.initialized_run(
                workspace, profile="maximal_full_dossier", high_stakes=True
            )
            plan_path, source_plan_path = self.write_plans(
                workspace, profile="maximal_full_dossier", high_stakes=True
            )
            source_plan = json.loads(source_plan_path.read_text(encoding="utf-8"))
            source_plan["questions"][1]["search_requirements"]["required_surfaces"] = [
                "scholarly_index", "clinical trial registry"
            ]
            source_plan["surface_applicability"].append({
                "surface": "clinical trial registry",
                "applicability": "required",
                "reason": "High-stakes medical work must search a clinical trial registry.",
            })
            source_plan["surface_applicability"].append({
                "surface": "literature_database",
                "applicability": "required",
                "reason": "High-stakes medical work must search a literature database.",
            })
            source_plan_path.write_text(json.dumps(source_plan), encoding="utf-8")
            self.register_lens_perspectives(run, workspace)
            result = self.invoke(
                "plan", str(run), "--plan-json", str(plan_path),
                "--source-plan-json", str(source_plan_path),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            cache = run / "work/generations/g0001/evidence-cache"
            for row in rows:
                if row.get("record_kind") != "search_run":
                    continue
                if row.get("query_id") == "Q001" and row.get("pass_kind") == "baseline":
                    row["surface"] = "PubMed"
                    row["surface_class"] = "literature_database"
                    self.bind_search_request(cache, row)
                if row.get("query_id") == "Q002" and row.get("surface_class") == "trial_registry":
                    row["surface"] = "ClinicalTrials.gov registry"
                    row["surface_class"] = "trial_registry"
                    self.bind_search_request(cache, row)
            inputs.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )

            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ingest_rejects_all_include_candidate_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [
                row for row in (json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines())
                if row.get("record_kind") != "candidate" or row.get("disposition") == "include"
            ]
            inputs.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 5)
            self.assertIn("candidate screening cannot be all include", result.stderr)

    def test_diagnostic_ingest_records_blocking_debt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace, run_intent="diagnostic_rehearsal")
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [
                row for row in (json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines())
                if row.get("record_kind") != "candidate" or row.get("disposition") == "include"
            ]
            inputs.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            result = self.invoke(
                "ingest", str(run), "--input-jsonl", str(inputs), "--allow-diagnostic-debt"
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            debt_path = run / "work/generations/g0001/artifacts/research/blocking-debt-ledger.json"
            self.assertTrue(debt_path.is_file())
            debt = json.loads(debt_path.read_text(encoding="utf-8"))
            self.assertEqual(debt["run_intent"], "diagnostic_rehearsal")
            self.assertIn("user_delivery", debt["not_valid_for"])
            self.assertIn(
                "candidate screening cannot be all include",
                "\n".join(debt["debts"][0]["errors"]),
            )
            self.assertTrue(
                (run / "state/generations/g0001/receipts/20-retrieval.json").is_file()
            )

    def test_diagnostic_debt_flag_does_not_relax_user_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [
                row for row in (json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines())
                if row.get("record_kind") != "candidate" or row.get("disposition") == "include"
            ]
            inputs.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            result = self.invoke(
                "ingest", str(run), "--input-jsonl", str(inputs), "--allow-diagnostic-debt"
            )
            self.assertEqual(result.returncode, 5)
            self.assertIn("candidate screening cannot be all include", result.stderr)

    def test_ingest_writes_receipt_bound_retrieval_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            inputs = self.write_retrieval_inputs(run, workspace)
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            audit = run / "work/generations/g0001/artifacts/research/retrieval-audit.jsonl"
            self.assertTrue(audit.is_file())
            receipt = json.loads(
                (run / "state/generations/g0001/receipts/20-retrieval.json").read_text()
            )
            self.assertIn("artifacts/research/retrieval-audit.jsonl", receipt["output_artifacts"])

    def test_captured_max_ingest_rejects_summary_only_search_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            evidence = workspace / "profile-selection-transcript.txt"
            evidence.write_text(
                "用户明确选择 Max 模式和正式 captured host execution。\n",
                encoding="utf-8",
            )
            result = self.invoke_init(
                workspace,
                "--research-profile", "maximal_full_dossier",
                "--profile-selection-mode", "user_selected",
                "--profile-selection-evidence", "user explicitly selected maximal_full_dossier",
                "--assurance-target", "captured_host_execution",
                "--profile-selection-evidence-file", str(evidence),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run = workspace / "output/storm-deepresearch/test-run"
            plan_path, source_plan_path = self.write_plans(
                workspace, profile="maximal_full_dossier"
            )
            self.register_lens_perspectives(run, workspace)
            result = self.invoke(
                "plan", str(run), "--plan-json", str(plan_path),
                "--source-plan-json", str(source_plan_path),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            search = next(row for row in rows if row.get("record_kind") == "search_run")
            cache = run / "work/generations/g0001/evidence-cache"
            raw = cache / str(search["raw_artifact"])
            raw.write_text(
                "Captured search transcript. Results summarized in candidate records.\n",
                encoding="utf-8",
            )
            search["snapshot_sha256"] = sha256_file(raw)
            inputs.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn(
                "search run SR001 response must be structured JSON with inspectable result rows",
                result.stderr,
            )
            self.assertFalse((run / "state/generations/g0001/receipts/20-retrieval.json").exists())

    def test_explain_for_max_captured_retrieval_points_to_preflight_and_prepare(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(
                workspace,
                profile="maximal_full_dossier",
                assurance_target="captured_host_execution",
            )
            result = self.invoke("explain", str(run))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["failed_stage"], "retrieval")
            self.assertIn("retrieval has not been run", payload["failed_checks"])
            suggestions = " ".join(payload.get("suggestions", []))
            self.assertIn("retrieval-preflight", suggestions)
            self.assertIn("retrieval-prepare", suggestions)
            self.assertNotIn("capture-source or ingest-dir", suggestions)

    def test_explain_keeps_generic_retrieval_suggestions_for_default_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace, profile="default_full_dossier")
            result = self.invoke("explain", str(run))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            suggestions = " ".join(payload.get("suggestions", []))
            self.assertIn("capture-source", suggestions)
            self.assertIn("ingest", suggestions)

    def test_retrieval_preflight_reports_expected_record_ids_and_max_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(
                workspace,
                profile="maximal_full_dossier",
                assurance_target="captured_host_execution",
            )
            retrieval = self.write_retrieval_inputs(run, workspace, source_count=2)
            rows = [
                json.loads(line)
                for line in retrieval.read_text(encoding="utf-8").splitlines()
            ]
            rows = [
                row for row in rows
                if row.get("record_kind") != "candidate" or row.get("disposition") == "include"
            ]
            retrieval.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            result = self.invoke("retrieval-preflight", str(run), "--input-jsonl", str(retrieval))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["stage"], "retrieval")
            self.assertIn("expected_record_ids", payload)
            self.assertTrue(any(item.startswith("SR") for item in payload["expected_record_ids"]))
            error_text = " ".join(payload["errors"])
            self.assertIn("requires two independent academic discovery surfaces", error_text)
            self.assertIn("candidate screening cannot be all include", error_text)
            self.assertFalse((run / "state/generations/g0001/receipts/20-retrieval.json").exists())

    def test_retrieval_preflight_passes_for_valid_max_inputs_without_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(
                workspace,
                profile="maximal_full_dossier",
                assurance_target="captured_host_execution",
            )
            retrieval = self.write_retrieval_inputs(run, workspace)
            result = self.invoke("retrieval-preflight", str(run), "--input-jsonl", str(retrieval))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"], payload)
            self.assertGreaterEqual(payload["record_counts"]["search_run"], 20)
            self.assertIn("SR001", payload["expected_record_ids"])
            self.assertIn("GA001", payload["expected_record_ids"])
            self.assertFalse((run / "state/generations/g0001/receipts/20-retrieval.json").exists())

    def test_retrieval_preflight_accepts_access_limited_unreachable_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(
                workspace,
                profile="maximal_full_dossier",
                assurance_target="captured_host_execution",
            )
            retrieval = self.write_retrieval_inputs(run, workspace)
            rows = [
                json.loads(line)
                for line in retrieval.read_text(encoding="utf-8").splitlines()
            ]
            for row in rows:
                if row.get("record_kind") == "search_run" and row.get("search_run_id") == "SR202":
                    row["execution_status"] = "unreachable"
                    row["result_count"] = None
                    row["limitations"] = ["The captured host could not resolve this registry endpoint."]
                if row.get("record_kind") == "gap_assessment" and row.get("assessment_id") == "GA001":
                    row["terminal_state"] = "access_limited_uncertainty"
                    row["uncertainty_id"] = "U001"
                    row["reason"] = (
                        "The gap remains access-limited because one required registry endpoint "
                        "was unreachable in the captured host execution context."
                    )
            retrieval.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            result = self.invoke("retrieval-preflight", str(run), "--input-jsonl", str(retrieval))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"], payload)
            self.assertIn("GA001", payload["expected_record_ids"])
            self.assertFalse((run / "state/generations/g0001/receipts/20-retrieval.json").exists())

    def test_retrieval_prepare_writes_matching_execution_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(
                workspace,
                profile="maximal_full_dossier",
                assurance_target="captured_host_execution",
            )
            retrieval = self.write_retrieval_inputs(run, workspace)
            transcript = workspace / "retrieval-transcript.txt"
            transcript.write_text(
                "host searched PubMed, ClinicalTrials, OpenAlex, Semantic Scholar, publisher full text, and counterevidence surfaces\n"
                "host screened include, exclude, and gap-fill candidates against declared criteria and resolver outcomes\n"
                "host captured full text, search request snapshots, raw result rows, resolver snapshots, and terminal gap evidence\n",
                encoding="utf-8",
            )
            plan_receipt = json.loads(
                (run / "state/generations/g0001/receipts/10-plan.json").read_text(encoding="utf-8")
            )
            started_at = plan_receipt["completed_at"]
            completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            output = workspace / "retrieval-execution.json"
            result = self.invoke(
                "retrieval-prepare", str(run),
                "--input-jsonl", str(retrieval),
                "--transcript", str(transcript),
                "--context-id", "retrieval-context-1",
                "--provider", "openai",
                "--model", "gpt-5.5",
                "--runner", "codex-exec",
                "--execution-id", "retrieval-exec-1",
                "--started-at", started_at,
                "--completed-at", completed_at,
                "--to", str(output),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["stage"], "retrieval")
            self.assertEqual(payload["execution_kind"], "host_execution")
            self.assertEqual(payload["input_artifacts"], {
                "artifacts/research/execution/retrieval-input.jsonl": sha256_file(retrieval)
            })
            self.assertIn("GA001", payload["record_ids"])
            self.assertEqual(payload["transcript_sha256"], sha256_file(transcript))
            result = self.invoke(
                "ingest", str(run),
                "--input-jsonl", str(retrieval),
                "--execution-provenance", str(output),
                "--execution-transcript", str(transcript),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_briefing_accepts_one_academic_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace, profile="briefing")
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            for row in rows:
                if row.get("record_kind") == "search_run":
                    row["surface"] = "OpenAlex"
                    self.bind_search_request(
                        run / "work/generations/g0001/evidence-cache", row
                    )
            inputs.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_critique_profile_accepts_academic_baseline_and_reception_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace, profile="critique_deepresearch")
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            surface_classes = {
                str(row["surface_class"])
                for row in rows
                if row.get("record_kind") == "search_run"
            }
            self.assertGreaterEqual(
                surface_classes,
                {"scholarly_index", "reception_archive", "interview_archive"},
            )
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_high_stakes_profile_accepts_pubmed_and_trial_registry_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace, high_stakes=True)
            brief_path = run / "work/generations/g0001/inputs/brief.json"
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            self.assertTrue(brief["high_stakes"])
            inputs = self.write_retrieval_inputs(run, workspace, high_stakes=True)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            search_runs = [row for row in rows if row.get("record_kind") == "search_run"]
            surfaces = {str(row["surface"]) for row in search_runs}
            surface_classes = {str(row["surface_class"]) for row in search_runs}
            self.assertIn("PubMed", surfaces)
            self.assertIn("ClinicalTrials.gov", surfaces)
            self.assertGreaterEqual(
                surface_classes,
                {"scholarly_index", "literature_database", "trial_registry"},
            )
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_maximal_auto_language_defaults_to_chinese(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(
                workspace,
                "--research-profile", "maximal_full_dossier",
                "--topic", "proton boron capture therapy",
                "--question", "What is the state of evidence?",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            brief = json.loads(
                (workspace / "output/storm-deepresearch/test-run/brief.json").read_text(encoding="utf-8")
            )
            self.assertEqual(brief["report_language"], "zh-CN")
            self.assertEqual(brief["length_contract"]["unit"], "characters")
            self.assertEqual(
                brief["maximal_completeness_contract"]["completion_policy"],
                "coverage_and_saturation",
            )
            self.assertFalse(any(
                key.startswith("min_")
                for key in brief["maximal_completeness_contract"]
            ))

    def test_maximal_plan_requires_open_ended_saturation_budget(self) -> None:
        brief = self.maximal_brief()
        plan = valid_research_plan_v2()
        source_plan = valid_source_plan()
        with self.assertRaisesRegex(Exception, "open ended until saturation"):
            validate_plan_bundle(plan, source_plan, brief)

    def test_maximal_retrieval_depth_does_not_use_source_count_as_stop_condition(self) -> None:
        brief = self.maximal_brief()
        sources = [
            valid_capture_input(index) | {
                "source_id": f"S{index:03d}",
                "canonical_url": f"https://doi.org/10.5555/storm.{index}",
                "content_hash": format(index % 16, "x") * 64,
                "source_type": "peer_reviewed_paper",
                "primary_class": "primary",
                "reliability_tier": "A",
                "freshness_status": "current",
            }
            for index in range(1, 7)
        ]
        errors = validate_retrieval_depth(sources, brief)
        self.assertFalse(any("80" in error or "88" in error for error in errors), errors)

    def test_maximal_retrieval_depth_does_not_accept_or_reject_exact_eighty_eight(self) -> None:
        brief = self.maximal_brief()
        sources = [
            valid_capture_input(index) | {
                "source_id": f"S{index:03d}",
                "canonical_url": f"https://doi.org/10.5555/storm.{index}",
                "content_hash": format(index % 16, "x") * 64,
                "source_type": "peer_reviewed_paper",
                "primary_class": "primary",
                "reliability_tier": "A",
                "freshness_status": "current",
            }
            for index in range(1, 89)
        ]
        errors = validate_retrieval_depth(sources, brief)
        self.assertFalse(any("floor" in error or "88" in error for error in errors), errors)

    def test_maximal_retrieval_depth_does_not_require_a_fixed_candidate_pool(self) -> None:
        brief = self.maximal_brief()
        sources = [
            valid_capture_input(index) | {
                "source_id": f"S{index:03d}",
                "canonical_url": f"https://doi.org/10.5555/storm.{index}",
                "content_hash": format(index % 16, "x") * 64,
                "source_type": "peer_reviewed_paper",
                "primary_class": "primary",
                "reliability_tier": "A",
                "freshness_status": "current",
            }
            for index in range(1, 7)
        ]
        audit = [valid_candidate_record(index) for index in range(1, 8)]
        audit[-1]["disposition"] = "exclude"
        audit[-1]["screening_reason"] = "Outside the declared scope."
        errors = validate_retrieval_depth(sources, brief, audit)
        self.assertFalse(any("120" in error or "candidate pool" in error for error in errors), errors)

    def test_maximal_saturation_requires_two_zero_material_delta_waves(self) -> None:
        tasklets = [{"tasklet_id": "T001"}]
        findings = [{
            "finding_id": "F001", "tasklet_id": "T001", "question_id": "Q001",
            "status": "usable", "source_ids": ["S001"], "claim_ids": ["C001"],
        }]
        manifests = [{"source_id": "S001", "candidate_id": "K001"}]
        audit = [
            {"record_kind": "search_run", "search_run_id": "SR001", "query_id": "Q001", "pass_kind": "gap_fill", "execution_status": "zero_results"},
            {"record_kind": "search_wave", "wave_id": "WAVE001", "gap_id": "G001", "question_ids": ["Q001"], "search_run_ids": ["SR001"], "new_candidate_ids": []},
        ]
        coverage = findings_coverage(tasklets, findings, audit, manifests)
        errors = validate_maximal_saturation(self.maximal_brief(), coverage)
        self.assertIn("G001 lacks a valid terminal gap disposition", errors)
        audit.extend([
            {"record_kind": "search_run", "search_run_id": "SR002", "query_id": "Q001", "pass_kind": "gap_fill", "execution_status": "zero_results"},
            {"record_kind": "search_wave", "wave_id": "WAVE002", "gap_id": "G001", "question_ids": ["Q001"], "search_run_ids": ["SR002"], "new_candidate_ids": []},
            {
                "record_kind": "gap_assessment", "assessment_id": "GA001",
                "gap_id": "G001", "terminal_state": "saturated",
                "supporting_wave_ids": ["WAVE001", "WAVE002"],
                "supporting_search_run_ids": ["SR001", "SR002"],
                "screened_candidate_ids": [], "raw_result_count": 0,
                "deduplicated_candidate_count": 0, "uncertainty_id": None,
                "review_concern_id": None,
                "reason": "Two independent gap-fill waves produced no material novelty.",
            },
        ])
        coverage = findings_coverage(tasklets, findings, audit, manifests)
        self.assertEqual(validate_maximal_saturation(self.maximal_brief(), coverage), [])

    def test_material_delta_counts_new_finding_on_existing_source(self) -> None:
        tasklets = [{"tasklet_id": "T001"}]
        findings = [
            {
                "finding_id": "F001", "tasklet_id": "T001", "question_id": "Q001",
                "status": "usable", "source_ids": ["S001"], "claim_ids": ["C001"],
            },
            {
                "finding_id": "F002", "tasklet_id": "T001", "question_id": "Q001",
                "status": "usable", "source_ids": ["S001"], "claim_ids": ["C002"],
            },
        ]
        audit = [{
            "record_kind": "search_wave", "wave_id": "WAVE001", "gap_id": "G001",
            "question_ids": ["Q001"], "search_run_ids": ["SR001"],
            "new_candidate_ids": [], "new_source_ids": [],
            "new_finding_ids": ["F002"], "new_contradiction_ids": [],
            "new_uncertainty_ids": [], "changed_claim_ids": ["C002"],
            "material_delta": 1,
        }]

        coverage = findings_coverage(
            tasklets, findings, audit, [{"source_id": "S001", "candidate_id": "K001"}]
        )

        wave = coverage["search_waves"][0]
        self.assertEqual(wave["new_usable_finding_ids"], ["F002"])
        self.assertEqual(wave["changed_claim_ids"], ["C002"])
        self.assertEqual(wave["material_delta"], 1)

    def test_submitted_material_delta_mismatch_blocks_saturation(self) -> None:
        tasklets = [{"tasklet_id": "T001"}]
        findings = [{
            "finding_id": "F001", "tasklet_id": "T001", "question_id": "Q001",
            "status": "usable", "source_ids": ["S001"], "claim_ids": ["C001"],
        }]
        audit = [{
            "record_kind": "search_wave", "wave_id": "WAVE001", "gap_id": "G001",
            "question_ids": ["Q001"], "search_run_ids": ["SR001"],
            "new_candidate_ids": [], "new_source_ids": [],
            "new_finding_ids": ["F001"], "new_contradiction_ids": [],
            "new_uncertainty_ids": [], "changed_claim_ids": ["C001"],
            "material_delta": 0,
        }, {
            "record_kind": "gap_assessment", "assessment_id": "GA001", "gap_id": "G001",
            "terminal_state": "saturated", "supporting_wave_ids": ["WAVE001", "WAVE001"],
            "supporting_search_run_ids": ["SR001"], "screened_candidate_ids": [],
            "raw_result_count": 0, "deduplicated_candidate_count": 0,
            "uncertainty_id": None, "review_concern_id": "RC001",
            "reason": "The host incorrectly declared zero novelty for a wave with a new material finding.",
        }]

        coverage = findings_coverage(tasklets, findings, audit, [])
        errors = validate_maximal_saturation(self.maximal_brief(), coverage)

        self.assertIn("WAVE001 submitted material_delta does not recompute", errors)

    def test_maximal_bounded_corpus_can_close_below_a_source_quota(self) -> None:
        tasklets = [{"tasklet_id": "T001"}]
        findings = [{
            "finding_id": "F001", "tasklet_id": "T001", "question_id": "Q001",
            "status": "usable", "source_ids": ["S001"], "claim_ids": ["C001"],
        }]
        audit = [
            {"record_kind": "search_wave", "wave_id": "WAVE001", "gap_id": "G001", "question_ids": ["Q001"], "search_run_ids": ["SR001"], "new_candidate_ids": ["K001"]},
            {
                "record_kind": "gap_assessment", "assessment_id": "GA001",
                "gap_id": "G001", "terminal_state": "bounded_corpus_exhausted",
                "supporting_wave_ids": ["WAVE001"], "supporting_search_run_ids": ["SR001"],
                "screened_candidate_ids": ["K001"], "raw_result_count": 1,
                "deduplicated_candidate_count": 1, "uncertainty_id": None,
                "review_concern_id": "RC001",
                "reason": "The finite corpus returned one deduplicated candidate and it was fully screened.",
                "result_windows_retrieved": 1, "total_result_windows": 1,
                "enumeration_complete": True, "access_limitations": [],
            },
        ]
        coverage = findings_coverage(
            tasklets, findings, audit, [{"source_id": "S001", "candidate_id": "K001"}]
        )
        self.assertEqual(validate_maximal_saturation(self.maximal_brief(), coverage), [])
        self.assertEqual(coverage["saturation_assessments"][0]["terminal_state"], "bounded_corpus_exhausted")

    def test_maximal_bounded_corpus_requires_enumeration_proof(self) -> None:
        tasklets = [{"tasklet_id": "T001"}]
        findings = [{
            "finding_id": "F001", "tasklet_id": "T001", "question_id": "Q001",
            "status": "usable", "source_ids": ["S001"], "claim_ids": ["C001"],
        }]
        audit = [
            {"record_kind": "search_wave", "wave_id": "WAVE001", "gap_id": "G001", "question_ids": ["Q001"], "search_run_ids": ["SR001"], "new_candidate_ids": ["K001"]},
            {
                "record_kind": "gap_assessment", "assessment_id": "GA001",
                "gap_id": "G001", "terminal_state": "bounded_corpus_exhausted",
                "supporting_wave_ids": ["WAVE001"], "supporting_search_run_ids": ["SR001"],
                "screened_candidate_ids": ["K001"], "raw_result_count": 1,
                "deduplicated_candidate_count": 1, "uncertainty_id": None,
                "review_concern_id": "RC001",
                "reason": "The host asserted a finite corpus without proving all result windows were enumerated.",
            },
        ]
        coverage = findings_coverage(
            tasklets, findings, audit, [{"source_id": "S001", "candidate_id": "K001"}]
        )
        self.assertIn(
            "G001 bounded corpus exhaustion requires complete result-window enumeration",
            validate_maximal_saturation(self.maximal_brief(), coverage),
        )

    def test_version_siblings_do_not_inflate_independent_source_depth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            canonical_selected = False
            for row in rows:
                if row.get("record_kind") == "candidate":
                    row["version_family_id"] = "W001"
                    row["relationship_basis"] = "explicit_metadata"
                    row["canonical_version"] = not canonical_selected
                    canonical_selected = True
            inputs.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 5)
            self.assertIn("independent source depth", result.stderr)

    def test_capture_for_excluded_candidate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            candidate = next(row for row in rows if row.get("record_kind") == "candidate")
            candidate.update({
                "disposition": "exclude",
                "screening_reason": "Fails the declared inclusion criteria.",
            })
            inputs.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 5)
            self.assertIn("capture refers to exclude candidate", result.stderr)

    def test_full_dossier_rejects_unverified_academic_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            candidate = next(row for row in rows if row.get("record_kind") == "candidate")
            for outcome in candidate["resolver_outcomes"]:
                outcome.update({
                    "status": "unreachable",
                    "matched_identifier": None,
                    "returned_title": None,
                    "returned_authors": [],
                    "returned_year": None,
                    "metadata_match": False,
                    "reason": "Resolver returned no trustworthy response.",
                })
            inputs.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 5)
            self.assertIn("academic candidate is not bibliographically verified", result.stderr)

    def test_ingest_rejects_future_retrieval_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            inputs = self.write_retrieval_inputs(run, workspace)
            records = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            capture = next(item for item in records if item.get("record_kind") == "capture")
            capture["retrieved_at"] = "2999-01-01T00:00:00Z"
            inputs.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("timestamp is outside the plan-ingest window", result.stderr)
    def test_init_creates_generation_scoped_brief_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(workspace)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run = workspace / "output" / "storm-deepresearch" / "test-run"
            authoritative = run / "work/generations/g0001/inputs/brief.json"
            receipt = run / "state/generations/g0001/receipts/00-init.json"
            self.assertTrue(authoritative.is_file())
            self.assertTrue(receipt.is_file())
            brief = json.loads(authoritative.read_text(encoding="utf-8"))
            self.assertEqual(brief["schema_version"], "2.0")
            self.assertNotIn("package_state", brief)
            self.assertEqual(brief["research_profile"], "default_full_dossier")
            self.assertEqual(brief["storm_lens_mode"], "strict")
            self.assertEqual(brief["profile_selection"]["mode"], "user_requested_default")
            self.assertEqual(brief["profile_selection"]["selected_profile"], "default_full_dossier")
            self.assertEqual((run / "brief.json").read_bytes(), authoritative.read_bytes())

    def test_init_requires_profile_selection_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke(
                "init", "--topic", "Governed research", "--question",
                "What evidence supports the conclusion?", "--workspace", str(workspace),
                "--output", "test-run",
            )
            self.assertEqual(result.returncode, 4)
            self.assertIn("profile selection requires --profile-selection-mode", result.stderr)
            self.assertFalse((workspace / "output/storm-deepresearch/test-run").exists())

    def test_init_requires_explicit_assurance_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke(
                "init", "--topic", "Governed research", "--question",
                "What evidence supports the conclusion?", "--workspace", str(workspace),
                "--output", "test-run",
                "--profile-selection-mode", "user_requested_default",
                "--profile-selection-evidence", "user requested the default profile",
            )
            self.assertEqual(result.returncode, 4)
            self.assertIn("requires --assurance-target", result.stderr)

    def test_init_preserves_scope_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(
                workspace,
                "--user-goal", "Verify a policy-sensitive claim",
                "--audience", "Chinese graduate applicants",
                "--geography", "China and United States",
                "--timeframe", "2020-2026",
                "--as-of", "2026-06-25",
                "--max-age-days", "180",
                "--uncertainty-tolerance", "medium",
                "--high-stakes",
                "--user-material", "quoted user claim",
                "--assumption", "profile confirmed through menu",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            brief = json.loads(
                (workspace / "output/storm-deepresearch/test-run/brief.json").read_text(encoding="utf-8")
            )
            self.assertEqual(brief["user_goal"], "Verify a policy-sensitive claim")
            self.assertEqual(brief["audience"], "Chinese graduate applicants")
            self.assertEqual(brief["geography"], "China and United States")
            self.assertEqual(brief["timeframe"], "2020-2026")
            self.assertEqual(brief["freshness_policy"], {"as_of": "2026-06-25", "max_age_days": 180})
            self.assertEqual(brief["uncertainty_tolerance"], "medium")
            self.assertTrue(brief["high_stakes"])
            self.assertEqual(brief["user_materials"], ["quoted user claim"])
            self.assertEqual(brief["assumptions"], ["profile confirmed through menu"])

    def test_init_rejects_full_dossier_reduced_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(workspace, "--output-mode", "reduced")
            self.assertEqual(result.returncode, 4)
            self.assertIn("full_dossier requires full output", result.stderr)
            self.assertFalse((workspace / "output/storm-deepresearch/test-run").exists())

    def test_init_rejects_briefing_without_explicit_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(workspace, "--depth-level", "briefing")
            self.assertEqual(result.returncode, 4)
            self.assertIn("briefing depth requires --briefing-reason", result.stderr)
            self.assertFalse((workspace / "output/storm-deepresearch/test-run").exists())

    def test_init_accepts_briefing_with_explicit_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(
                workspace,
                "--depth-level", "briefing",
                "--briefing-reason", "user explicitly requested a short briefing",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            brief = json.loads(
                (workspace / "output/storm-deepresearch/test-run/brief.json").read_text(encoding="utf-8")
            )
            self.assertEqual(brief["depth_level"], "briefing")
            self.assertEqual(brief["research_profile"], "briefing")
            self.assertEqual(brief["briefing_reason"], "user explicitly requested a short briefing")

    def test_research_profiles_map_to_governed_init_fields(self) -> None:
        cases = [
            ("default_full_dossier", {"storm_lens_mode": "strict", "depth_level": "full_dossier"}),
            ("maximal_full_dossier", {"storm_lens_mode": "strict", "depth_level": "full_dossier"}),
            ("closed_corpus", {"source_policy": "closed_corpus", "retrieval_mode": "closed_corpus"}),
            ("critique_deepresearch", {"depth_level": "full_dossier", "retrieval_mode": "host", "storm_lens_mode": "strict"}),
        ]
        for profile, expected in cases:
            with self.subTest(profile=profile):
                with tempfile.TemporaryDirectory() as tmp:
                    workspace = Path(tmp)
                    result = self.invoke_init(workspace, "--research-profile", profile)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    brief = json.loads(
                        (workspace / "output/storm-deepresearch/test-run/brief.json").read_text(encoding="utf-8")
                    )
                    self.assertEqual(brief["research_profile"], profile)
                    for key, value in expected.items():
                        self.assertEqual(brief[key], value)
                    expected_policy = "open_ended" if profile == "maximal_full_dossier" else "bounded"
                    self.assertEqual(brief["length_contract"]["policy"], expected_policy)
                    if profile == "maximal_full_dossier":
                        self.assertEqual(brief["report_language"], "zh-CN")
                        contract = brief["maximal_completeness_contract"]
                        self.assertEqual(contract["completion_policy"], "coverage_and_saturation")
                        self.assertEqual(contract["review_policy"], "concern_driven_until_clear")
                        self.assertEqual(contract["material_novelty_window"], 2)
                    if profile == "critique_deepresearch":
                        self.assertTrue(any("critique_deepresearch profile" in item for item in brief["assumptions"]))

    def test_maximal_full_dossier_rejects_unit_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(
                workspace,
                "--research-profile", "maximal_full_dossier",
                "--min-units", "1000",
            )
            self.assertEqual(result.returncode, 4)
            self.assertIn("maximal_full_dossier uses open-ended length", result.stderr)

    def test_legacy_strict_profile_normalizes_to_recommended_full_dossier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(
                workspace,
                "--research-profile", "strict_storm_lens",
                "--profile-selection-mode", "user_selected",
                "--profile-selection-evidence", "user selected the former strict option",
                "--assurance-target", "artifact_contract",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            brief = json.loads(
                (workspace / "output/storm-deepresearch/test-run/brief.json").read_text(encoding="utf-8")
            )
            self.assertEqual(brief["research_profile"], "default_full_dossier")
            self.assertEqual(brief["profile_selection"]["selected_profile"], "default_full_dossier")
            self.assertNotIn("strict_storm_lens", brief["profile_selection"]["available_profiles"])
            self.assertEqual(brief["storm_lens_mode"], "strict")

    def test_research_profile_conflict_fails_at_init(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(
                workspace,
                "--research-profile", "strict_storm_lens",
                "--storm-lens-mode", "advisory",
            )
            self.assertEqual(result.returncode, 4)
            self.assertIn("conflicts with --research-profile default_full_dossier", result.stderr)

    def test_repair_existing_run_profile_is_not_init(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(workspace, "--research-profile", "repair_existing_run")
            self.assertEqual(result.returncode, 4)
            self.assertIn("repair_existing_run uses status/explain/retry", result.stderr)

    def test_plan_refuses_changed_brief_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.initialized_run(workspace)
            plan_path, source_plan_path = self.write_plans(workspace)
            (run / "brief.json").write_text("{}\n", encoding="utf-8")
            result = self.invoke(
                "plan", str(run), "--plan-json", str(plan_path),
                "--source-plan-json", str(source_plan_path),
            )
            self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
            self.assertIn("brief view does not match", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/10-plan.json").exists())

    def test_plan_requires_init_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.initialized_run(workspace)
            (run / "state/generations/g0001/receipts/00-init.json").unlink()
            plan_path, source_plan_path = self.write_plans(workspace)
            result = self.invoke(
                "plan", str(run), "--plan-json", str(plan_path),
                "--source-plan-json", str(source_plan_path),
            )
            self.assertEqual(result.returncode, 8)
            self.assertIn("missing init receipt", result.stderr)

    def test_plan_promotes_validated_inputs_and_commits_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.initialized_run(workspace)
            plan_path, source_plan_path = self.write_plans(workspace)
            self.register_lens_perspectives(run, workspace)
            result = self.invoke(
                "plan", str(run), "--plan-json", str(plan_path),
                "--source-plan-json", str(source_plan_path),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            artifacts = run / "work/generations/g0001/artifacts/research"
            self.assertTrue((artifacts / "research-plan.json").is_file())
            self.assertTrue((artifacts / "source-plan.json").is_file())
            self.assertTrue((artifacts / "storm-tasklets.jsonl").is_file())
            self.assertTrue((run / "state/generations/g0001/receipts/10-plan.json").is_file())
            current = run / "current/research"
            self.assertEqual((current / "research-plan.json").read_bytes(), (artifacts / "research-plan.json").read_bytes())
            tasklets = [json.loads(line) for line in (artifacts / "storm-tasklets.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual({item["question_id"] for item in tasklets}, {f"Q{i:03d}" for i in range(1, 11)})

    def test_strict_lens_mode_requires_p1_before_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(workspace, "--storm-lens-mode", "strict")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run = workspace / "output" / "storm-deepresearch" / "test-run"
            plan_path, source_plan_path = self.write_plans(workspace)
            result = self.invoke(
                "plan", str(run), "--plan-json", str(plan_path),
                "--source-plan-json", str(source_plan_path),
            )
            self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
            self.assertIn("storm-lens-perspectives.json", result.stderr)

            brief = run / "work/generations/g0001/inputs/brief.json"
            lens = workspace / "storm-lens-perspectives.json"
            lens.write_text(json.dumps(valid_storm_lens_artifact(
                "P1",
                sha256_file(ROOT / "references/storm-lens-prompt-pack.md"),
                {"inputs/brief.json": sha256_file(brief)},
            )), encoding="utf-8")
            result = self.invoke(
                "lens-perspectives", str(run), "--input-json", str(lens),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = self.invoke(
                "plan", str(run), "--plan-json", str(plan_path),
                "--source-plan-json", str(source_plan_path),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads((run / "state/generations/g0001/receipts/10-plan.json").read_text(encoding="utf-8"))
            self.assertIn(
                "artifacts/research/storm-lens-perspectives.json",
                receipt["input_artifacts"],
            )

    def test_plan_rejects_full_dossier_closed_transcript_only_source_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.initialized_run(workspace)
            plan_path, source_plan_path = self.write_plans(workspace)
            self.register_lens_perspectives(run, workspace)
            source_plan = json.loads(source_plan_path.read_text(encoding="utf-8"))
            for question in source_plan["questions"]:
                question["required_source_classes"] = ["closed-transcript"]
            source_plan["source_classes"] = [{
                "class_id": "closed-transcript",
                "name": "Closed user transcript",
                "can_prove": ["What the supplied user transcript says"],
                "cannot_prove": ["External theory, history, or criticism claims"],
                "priority": 1,
            }]
            source_plan_path.write_text(json.dumps(source_plan), encoding="utf-8")
            result = self.invoke(
                "plan", str(run), "--plan-json", str(plan_path),
                "--source-plan-json", str(source_plan_path),
            )
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertIn("source classes beyond user, transcript, or closed corpus", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/10-plan.json").exists())

    def test_critique_deepresearch_rejects_shallow_source_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(workspace, "--research-profile", "critique_deepresearch")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run = workspace / "output" / "storm-deepresearch" / "test-run"
            plan_path, source_plan_path = self.write_plans(workspace)
            self.register_lens_perspectives(run, workspace)
            result = self.invoke(
                "plan", str(run), "--plan-json", str(plan_path),
                "--source-plan-json", str(source_plan_path),
            )
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertIn("critique_deepresearch source plan missing search dimension", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/10-plan.json").exists())

    def test_critique_deepresearch_accepts_dimensioned_source_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(workspace, "--research-profile", "critique_deepresearch")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run = workspace / "output" / "storm-deepresearch" / "test-run"
            plan_path, _source_plan_path = self.write_plans(workspace)
            source_plan_path = self.write_critique_source_plan(workspace)
            self.register_lens_perspectives(run, workspace)
            result = self.invoke(
                "plan", str(run), "--plan-json", str(plan_path),
                "--source-plan-json", str(source_plan_path),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((run / "state/generations/g0001/receipts/10-plan.json").is_file())

    def test_ingest_commits_only_when_every_question_has_captured_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            input_path = self.write_retrieval_inputs(run, workspace)
            result = self.invoke("ingest", str(run), "--input-jsonl", str(input_path))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            research = run / "work/generations/g0001/artifacts/research"
            self.assertTrue((research / "source-register.jsonl").is_file())
            self.assertTrue((research / "retrieval-manifest.jsonl").is_file())
            self.assertTrue((run / "state/generations/g0001/receipts/20-retrieval.json").is_file())
            manifests = [json.loads(line) for line in (research / "retrieval-manifest.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual({item["query_id"] for item in manifests}, {f"Q{i:03d}" for i in range(1, 11)})

    def test_capture_source_writes_ingest_input_without_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            snapshot = workspace / "captured-source.txt"
            snapshot.write_text(
                "Directly inspectable evidence excerpt 1. Additional captured context for source validation.",
                encoding="utf-8",
            )
            output = workspace / "retrieval-inputs.jsonl"
            result = self.invoke(
                "capture-source", str(run),
                "--query-id", "Q001",
                "--url", "https://www.nist.gov/test-fixtures/research-report-1",
                "--snapshot", str(snapshot),
                "--title", "Official research report 1",
                "--publisher", "National Institute of Standards and Technology",
                "--published-at", "2026-05-01",
                "--publication-date-status", "known",
                "--content-excerpt", "Directly inspectable evidence excerpt 1.",
                "--content-locator", "p:1",
                "--source-type", "official",
                "--primary-class", "primary",
                "--reliability-tier", "A",
                "--freshness-status", "current",
                "--reliability-notes", "First-party source with inspectable full text.",
                "--to", str(output),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["record_count"], 3)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            capture = next(row for row in rows if row.get("record_kind") == "capture")
            self.assertEqual(capture["query_id"], "Q001")
            self.assertTrue((run / "work/generations/g0001/evidence-cache" / capture["raw_artifact"]).is_file())
            self.assertFalse((run / "state/generations/g0001/receipts/20-retrieval.json").exists())

    def test_capture_source_warns_when_used_for_max_captured_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(
                workspace,
                profile="maximal_full_dossier",
                assurance_target="captured_host_execution",
            )
            snapshot = workspace / "source.txt"
            snapshot.write_text(
                "Directly inspectable evidence excerpt with enough context for capture validation.",
                encoding="utf-8",
            )
            output = workspace / "retrieval-inputs.jsonl"
            result = self.invoke(
                "capture-source", str(run),
                "--query-id", "Q001",
                "--url", "https://www.nist.gov/max-capture",
                "--snapshot", str(snapshot),
                "--title", "Max manual capture",
                "--publisher", "Example Publisher",
                "--content-excerpt", "Directly inspectable evidence excerpt",
                "--source-type", "secondary_synthesis",
                "--primary-class", "secondary",
                "--reliability-tier", "B",
                "--reliability-notes", "Manual capture for one source only.",
                "--to", str(output),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["max_compatibility"], "insufficient_for_max_captured")
            warning_text = json.dumps(payload["warnings"], ensure_ascii=False)
            self.assertIn("retrieval-preflight", warning_text)
            self.assertIn("resolver", warning_text)

    def test_ingest_dir_builds_inputs_that_ingest_can_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace, profile="briefing")
            input_dir = workspace / "source-captures"
            input_dir.mkdir()
            rows = []
            for index in range(1, 11):
                snapshot = input_dir / f"source-{index}.txt"
                snapshot.write_text(
                    f"Directly inspectable evidence excerpt {index}. Additional context for ingest-dir with enough normalized text to avoid a bad-capture warning.",
                    encoding="utf-8",
                )
                row = valid_adapter_record(index)
                row["snapshot"] = snapshot.name
                rows.append(row)
            (input_dir / "sources.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            output = workspace / "retrieval-inputs.jsonl"
            result = self.invoke(
                "ingest-dir", str(run), "--input-dir", str(input_dir), "--to", str(output)
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = self.invoke("ingest", str(run), "--input-jsonl", str(output))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((run / "state/generations/g0001/receipts/20-retrieval.json").is_file())

    def test_capture_source_rejects_bad_capture_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            snapshot = workspace / "blocked.txt"
            snapshot.write_text(
                "Checking if the site connection is secure. Please enable cookies and JavaScript.",
                encoding="utf-8",
            )
            result = self.invoke(
                "capture-source", str(run),
                "--query-id", "Q001",
                "--url", "https://www.nist.gov/test-fixtures/research-report-1",
                "--snapshot", str(snapshot),
                "--title", "Blocked capture",
                "--publisher", "NIST",
                "--content-excerpt", "Checking if the site connection is secure.",
                "--source-type", "official",
                "--primary-class", "primary",
                "--reliability-tier", "A",
                "--reliability-notes", "Fixture should be rejected before use.",
            )
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("bad-capture marker", result.stderr)

    def test_ingest_rejects_placeholder_source_without_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            input_path = self.write_retrieval_inputs(run, workspace, placeholder=True)
            result = self.invoke("ingest", str(run), "--input-jsonl", str(input_path))
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("reserved or placeholder domain", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/20-retrieval.json").exists())

    def test_ingest_rejects_full_dossier_with_only_encyclopedia_external_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            input_path = self.write_retrieval_inputs(run, workspace, encyclopedia_only=True)
            result = self.invoke("ingest", str(run), "--input-jsonl", str(input_path))
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("non-user, non-encyclopedia external sources", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/20-retrieval.json").exists())

    def test_findings_registers_pool_after_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            input_path = self.write_retrieval_inputs(run, workspace)
            result = self.invoke("ingest", str(run), "--input-jsonl", str(input_path))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            findings = self.write_findings_inputs(run, workspace)
            result = self.invoke("findings", str(run), "--findings-jsonl", str(findings))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            research = run / "work/generations/g0001/artifacts/research"
            self.assertTrue((research / "storm-findings-pool.jsonl").is_file())
            coverage = json.loads((research / "finding-coverage.json").read_text(encoding="utf-8"))
            self.assertEqual(coverage["missing_tasklet_ids"], [])

    def test_findings_recomputes_null_search_wave_material_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace, profile="maximal_full_dossier")
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            for row in rows:
                if row.get("record_kind") == "search_wave":
                    row["material_delta"] = None
            inputs.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            findings = self.write_findings_inputs(run, workspace)
            result = self.invoke("findings", str(run), "--findings-jsonl", str(findings))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            coverage = json.loads(
                (run / "work/generations/g0001/artifacts/research/finding-coverage.json")
                .read_text(encoding="utf-8")
            )
            wave = coverage["search_waves"][0]
            self.assertIsNone(wave["submitted_material_delta"])
            self.assertIsInstance(wave["material_delta"], int)

    def test_init_rejects_defaulted_after_prompt_without_prompt_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(
                workspace,
                "--profile-selection-mode", "defaulted_after_prompt",
                "--profile-selection-evidence", "host claims the user defaulted after a menu",
            )
            self.assertEqual(result.returncode, 4)
            self.assertIn("defaulted_after_prompt requires --profile-prompt-file", result.stderr)

    def test_init_binds_profile_prompt_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            prompt = workspace / "profile-menu.txt"
            prompt.write_text(
                "请选择研究方式：完整深度研究（推荐）或短简报。未选择则按完整深度研究继续。\n",
                encoding="utf-8",
            )
            result = self.invoke_init(
                workspace,
                "--profile-selection-mode", "defaulted_after_prompt",
                "--profile-selection-evidence", "user saw the profile menu and accepted the default",
                "--profile-prompt-file", str(prompt),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run = workspace / "output/storm-deepresearch/test-run"
            copied = run / "work/generations/g0001/inputs/profile-selection-prompt.txt"
            self.assertEqual(copied.read_text(encoding="utf-8"), prompt.read_text(encoding="utf-8"))
            brief = json.loads((run / "brief.json").read_text(encoding="utf-8"))
            self.assertEqual(
                brief["profile_selection"]["prompt_sha256"],
                sha256_file(copied),
            )
            receipt = json.loads(
                (run / "state/generations/g0001/receipts/00-init.json").read_text(encoding="utf-8")
            )
            self.assertIn("inputs/profile-selection-prompt.txt", receipt["output_artifacts"])

    def test_captured_init_requires_profile_selection_evidence_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(
                workspace,
                "--assurance-target", "captured_host_execution",
            )
            self.assertEqual(result.returncode, 4)
            self.assertIn(
                "captured_host_execution profile selection requires --profile-selection-evidence-file",
                result.stderr,
            )

    def test_captured_init_binds_profile_selection_evidence_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            evidence = workspace / "profile-selection-transcript.txt"
            evidence.write_text(
                "用户明确选择：使用 Max 模式研究 proton boron capture therapy，默认输出中文。\n",
                encoding="utf-8",
            )
            result = self.invoke_init(
                workspace,
                "--research-profile", "maximal_full_dossier",
                "--profile-selection-mode", "user_selected",
                "--profile-selection-evidence", "user explicitly selected maximal_full_dossier",
                "--assurance-target", "captured_host_execution",
                "--profile-selection-evidence-file", str(evidence),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run = workspace / "output/storm-deepresearch/test-run"
            copied = run / "work/generations/g0001/inputs/profile-selection-evidence.txt"
            self.assertEqual(copied.read_text(encoding="utf-8"), evidence.read_text(encoding="utf-8"))
            brief = json.loads((run / "brief.json").read_text(encoding="utf-8"))
            self.assertEqual(
                brief["profile_selection"]["evidence_sha256"],
                sha256_file(copied),
            )
            self.assertEqual(
                brief["profile_selection"]["evidence_ref"],
                "inputs/profile-selection-evidence.txt",
            )
            receipt = json.loads(
                (run / "state/generations/g0001/receipts/00-init.json").read_text(encoding="utf-8")
            )
            self.assertIn("inputs/profile-selection-evidence.txt", receipt["output_artifacts"])

    def invoke_init(self, workspace: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.invoke(
            "init", "--topic", "Governed research", "--question",
            "What evidence supports the conclusion?", "--workspace", str(workspace),
            "--output", "test-run",
            "--profile-selection-mode", "user_requested_default",
            "--profile-selection-evidence", "test explicitly requested the default full dossier profile",
            "--assurance-target", "artifact_contract",
            *extra,
        )

    def initialized_run(
        self,
        workspace: Path,
        *,
        profile: str = "default_full_dossier",
        high_stakes: bool = False,
        assurance_target: str = "artifact_contract",
        run_intent: str = "user_delivery",
    ) -> Path:
        extra = [
            "--research-profile", profile,
            "--assurance-target", assurance_target,
            "--run-intent", run_intent,
        ]
        if profile == "briefing":
            extra.extend(["--briefing-reason", "fixture explicitly requests a short briefing"])
        if high_stakes:
            extra.append("--high-stakes")
        if assurance_target == "captured_host_execution":
            evidence = workspace / "profile-selection-transcript.txt"
            evidence.write_text(
                f"user explicitly selected {profile} with captured_host_execution\n",
                encoding="utf-8",
            )
            extra.extend([
                "--profile-selection-mode", "user_selected",
                "--profile-selection-evidence", f"user explicitly selected {profile}",
                "--profile-selection-evidence-file", str(evidence),
            ])
        result = self.invoke_init(workspace, *extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return workspace / "output" / "storm-deepresearch" / "test-run"

    def maximal_brief(self) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(workspace, "--research-profile", "maximal_full_dossier")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(
                (workspace / "output/storm-deepresearch/test-run/brief.json").read_text(encoding="utf-8")
            )

    def planned_run(
        self,
        workspace: Path,
        *,
        profile: str = "default_full_dossier",
        high_stakes: bool = False,
        assurance_target: str = "artifact_contract",
        run_intent: str = "user_delivery",
    ) -> Path:
        run = self.initialized_run(
            workspace,
            profile=profile,
            high_stakes=high_stakes,
            assurance_target=assurance_target,
            run_intent=run_intent,
        )
        plan_path, source_plan_path = self.write_plans(
            workspace, profile=profile, high_stakes=high_stakes
        )
        if profile == "critique_deepresearch":
            source_plan_path = self.write_critique_source_plan(workspace)
        self.register_lens_perspectives(run, workspace)
        result = self.invoke(
            "plan", str(run), "--plan-json", str(plan_path),
            "--source-plan-json", str(source_plan_path),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return run

    def retrieved_run(
        self,
        workspace: Path,
        *,
        profile: str = "default_full_dossier",
        register_findings: bool = True,
        gap_fill_query_ids: set[str] | frozenset[str] = frozenset(),
    ) -> Path:
        run = self.planned_run(workspace, profile=profile)
        inputs = self.write_retrieval_inputs(
            run, workspace, gap_fill_query_ids=gap_fill_query_ids
        )
        result = self.invoke("ingest", str(run), "--input-jsonl", str(inputs))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        if register_findings:
            findings = self.write_findings_inputs(run, workspace)
            result = self.invoke("findings", str(run), "--findings-jsonl", str(findings))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return run

    def write_plans(
        self, workspace: Path, *, profile: str = "default_full_dossier",
        high_stakes: bool = False
    ) -> tuple[Path, Path]:
        plan = workspace / "research-plan.json"
        source_plan = workspace / "source-plan.json"
        maximal = profile == "maximal_full_dossier"
        plan.write_text(json.dumps(
            valid_research_plan_v2(
                question_count=10,
                max_queries=30,
                max_sources=50,
                open_ended=maximal,
            )
        ), encoding="utf-8")
        source_plan_payload = valid_source_plan(10, maximal=maximal)
        if high_stakes:
            source_plan_payload["questions"][0]["search_requirements"]["required_surfaces"] = [
                "scholarly_index", "literature_database"
            ]
            source_plan_payload["questions"][1]["search_requirements"]["required_surfaces"] = [
                "scholarly_index", "trial_registry"
            ]
            for question in source_plan_payload["questions"]:
                question["search_requirements"]["aliases"] = [
                    "proton boron capture therapy",
                    "PBCT",
                    "proton boron fusion therapy",
                ]
        source_plan.write_text(json.dumps(source_plan_payload), encoding="utf-8")
        return plan, source_plan

    def write_critique_source_plan(self, workspace: Path) -> Path:
        plan = valid_source_plan()
        dimensions = [
            ("Q001", "Extract the user's supplied interpretation and user claim before background lookup.", "User claim from the supplied critique."),
            ("Q002", "Find supporting evidence for the user's argument.", "Supporting evidence that can confirm or qualify the claim."),
            ("Q003", "Search counterevidence and contradictions against the interpretation.", "Contradicting evidence and alternative reading."),
            ("Q004", "Find academic theory framework or criticism relevant to the concept.", "Theory framework from academic or expert criticism."),
            ("Q005", "Search reception, critic reviews, audience discourse, and debate.", "Reception criticism and review evidence."),
            ("Q006", "Search historical comparison, similar pattern, precedent, and blind spot.", "Historical comparison and blind spot evidence."),
        ]
        for query_id, question, evidence_need in dimensions:
            index = int(query_id[1:]) - 1
            plan["questions"][index]["question"] = question
            plan["questions"][index]["evidence_need"] = evidence_need
        for index in range(6, 10):
            plan["questions"][index]["question"] = (
                f"Deepen critique_deepresearch dimension {index + 1} with source-grounded synthesis."
            )
        path = workspace / "critique-source-plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        return path

    def register_lens_perspectives(self, run: Path, workspace: Path) -> None:
        brief = run / "work/generations/g0001/inputs/brief.json"
        plan_path = workspace / "research-plan.json"
        question_count = 10
        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            question_count = len(plan.get("questions", [])) or question_count
        lens = workspace / "storm-lens-perspectives.json"
        lens.write_text(json.dumps(valid_storm_lens_artifact(
            "P1",
            sha256_file(ROOT / "references/storm-lens-prompt-pack.md"),
            {"inputs/brief.json": sha256_file(brief)},
            question_count=question_count,
        )), encoding="utf-8")
        result = self.invoke("lens-perspectives", str(run), "--input-json", str(lens))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def write_retrieval_inputs(
        self,
        run: Path,
        workspace: Path,
        *,
        placeholder: bool = False,
        encyclopedia_only: bool = False,
        gap_fill_query_ids: set[str] | frozenset[str] = frozenset(),
        zero_result_query_ids: set[str] | frozenset[str] = frozenset(),
        official_query_ids: set[str] | frozenset[str] = frozenset(),
        high_stakes: bool = False,
        source_count: int | None = None,
    ) -> Path:
        cache = run / "work/generations/g0001/evidence-cache"
        brief = json.loads(
            (run / "work/generations/g0001/inputs/brief.json").read_text(encoding="utf-8")
        )
        critique = brief.get("research_profile") == "critique_deepresearch"
        maximal = brief.get("research_profile") == "maximal_full_dossier"
        source_plan = json.loads(
            (run / "work/generations/g0001/artifacts/research/source-plan.json").read_text(encoding="utf-8")
        )
        question_count = len(source_plan["questions"])
        source_count = source_count or (20 if maximal else 10)
        records: list[dict[str, object]] = []
        for index in range(1, source_count + 1):
            query_index = ((index - 1) % question_count) + 1
            query_id = f"Q{query_index:03d}"
            search = valid_search_run_record(index)
            search["query_id"] = query_id
            if maximal:
                if index <= question_count:
                    surface, surface_class, pass_kind = ("OpenAlex", "scholarly_index", "baseline")
                else:
                    surface_cycle = [
                        ("OpenAlex", "scholarly_index", "baseline"),
                        ("ClinicalTrials.gov", "trial_registry", "baseline"),
                        ("Publisher full text", "publisher_full_text", "baseline"),
                        ("Cochrane Reviews", "secondary_synthesis", "baseline"),
                        ("Contradiction search", "counterevidence", "counterevidence"),
                    ]
                    surface, surface_class, pass_kind = surface_cycle[(query_index - 1) % len(surface_cycle)]
                    if surface_class == "scholarly_index":
                        surface = "Semantic Scholar"
                search.update({
                    "surface": surface,
                    "surface_class": surface_class,
                    "pass_kind": pass_kind,
                    "aliases": [
                        "proton boron capture therapy",
                        "PBCT",
                        "proton boron fusion therapy",
                    ],
                })
            else:
                search["surface"] = "OpenAlex" if index % 2 else "Semantic Scholar"
            candidate = valid_candidate_record(index)
            record = (
                valid_adapter_record(index)
                if query_id in official_query_ids
                else valid_capture_input(index)
            )
            record["query_id"] = query_id
            if placeholder and index == 1:
                record["url"] = "https://example.com/fake-paper"
                record["final_url"] = record["url"]
                candidate["url"] = record["url"]
            if encyclopedia_only:
                record["url"] = f"https://en.wikipedia.org/wiki/Research_fixture_{index}"
                record["final_url"] = record["url"]
                record["publisher"] = "Wikipedia"
                record["source_type"] = "encyclopedia"
                record["primary_class"] = "secondary"
                record["reliability_tier"] = "B"
                record["reliability_notes"] = "Secondary encyclopedia fixture."
                candidate["url"] = record["url"]
            (cache / f"source-{index}.txt").write_text(
                f"Directly inspectable evidence excerpt {index}. Additional context.",
                encoding="utf-8",
            )
            (cache / f"search-{index}.json").write_text(
                json.dumps({"results": [self.search_result_row(candidate)]}) + "\n",
                encoding="utf-8",
            )
            (cache / f"crossref-{index}.json").write_text(
                json.dumps({"doi": candidate["identifiers"]["doi"]}) + "\n",
                encoding="utf-8",
            )
            (cache / f"openalex-{index}.json").write_text(
                json.dumps({"id": candidate["identifiers"]["openalex_id"]}) + "\n",
                encoding="utf-8",
            )
            (cache / f"semantic-scholar-{index}.json").write_text(
                json.dumps({"paperId": candidate["identifiers"]["semantic_scholar_id"]}) + "\n",
                encoding="utf-8",
            )
            search["snapshot_sha256"] = sha256_file(cache / f"search-{index}.json")
            self.bind_search_request(cache, search)
            candidate["resolver_outcomes"][0]["snapshot_sha256"] = sha256_file(
                cache / f"crossref-{index}.json"
            )
            candidate["resolver_outcomes"][1]["snapshot_sha256"] = sha256_file(
                cache / f"openalex-{index}.json"
            )
            candidate["resolver_outcomes"][2]["snapshot_sha256"] = sha256_file(
                cache / f"semantic-scholar-{index}.json"
            )
            records.extend([search, candidate, record])
            extra_surfaces: list[tuple[int, str, str, str]] = []
            if not maximal:
                extra_surfaces.append((400 + index, "Publisher full text", "publisher_full_text", "baseline"))
            if critique and index == 5:
                extra_surfaces.append((205, "reception", "reception_archive", "counterevidence"))
            if critique and index == 6:
                extra_surfaces.append((206, "interviews", "interview_archive", "counterevidence"))
            if high_stakes and index == 1:
                extra_surfaces.append((301, "PubMed", "literature_database", "baseline"))
            if high_stakes and index == 2:
                extra_surfaces.append((302, "ClinicalTrials.gov", "trial_registry", "baseline"))
            for run_number, surface, surface_class, pass_kind in extra_surfaces:
                run_id = f"SR{run_number:03d}"
                artifact = cache / f"search-{run_number}.json"
                artifact.write_text(
                    json.dumps({"results": [self.search_result_row(candidate)]}) + "\n",
                    encoding="utf-8",
                )
                extra_search = valid_search_run_record(index, pass_kind=pass_kind)
                extra_search.update({
                    "search_run_id": run_id,
                    "surface": surface,
                    "surface_class": surface_class,
                    "raw_artifact": artifact.name,
                    "request_artifact": f"request-{run_number}.json",
                    "snapshot_sha256": sha256_file(artifact),
                    "result_count": 1,
                })
                self.bind_search_request(cache, extra_search)
                candidate["search_run_ids"].append(run_id)
                record["search_run_ids"].append(run_id)
                records.append(extra_search)
            if query_id in gap_fill_query_ids:
                gap_id = f"SR{100 + index:03d}"
                gap_artifact = cache / f"gap-{index}.json"
                zero_results = query_id in zero_result_query_ids
                gap_artifact.write_text(
                    json.dumps({
                        "results": [] if zero_results else [self.search_result_row(candidate)]
                    }) + "\n",
                    encoding="utf-8",
                )
                gap = valid_search_run_record(index, pass_kind="gap_fill")
                gap.update({
                    "search_run_id": gap_id,
                    "surface": "Google Scholar",
                    "raw_artifact": gap_artifact.name,
                    "request_artifact": f"request-gap-{index}.json",
                    "snapshot_sha256": sha256_file(gap_artifact),
                    "execution_status": "zero_results" if zero_results else "completed",
                    "result_count": 0 if zero_results else 1,
                })
                self.bind_search_request(cache, gap)
                records.append(gap)
        if maximal:
            candidate = valid_candidate_record(source_count + 1)
            candidate.update({
                "search_run_ids": ["SR001"],
                "disposition": "exclude",
                "screening_reason": "Outside the declared scope after title and abstract screening.",
            })
            for outcome in candidate["resolver_outcomes"]:
                outcome.update({
                    "status": "skipped", "matched_identifier": None,
                    "returned_title": None, "returned_authors": [],
                    "returned_year": None, "metadata_match": False,
                    "raw_artifact": None, "snapshot_sha256": None,
                    "reason": "Excluded before resolver capture.",
                })
            records.append(candidate)
            self.append_search_result(cache, records, "SR001", candidate)
            for wave_index, run_number in enumerate((201, 202), start=1):
                artifact = cache / f"search-{run_number}.json"
                artifact.write_text('{"results":[]}\n', encoding="utf-8")
                search = valid_search_run_record(run_number, pass_kind="gap_fill")
                search.update({
                    "query_id": "Q001",
                    "surface": "Gap-fill scholarly search",
                    "surface_class": "scholarly_index",
                    "execution_status": "zero_results",
                    "result_count": 0,
                    "raw_artifact": artifact.name,
                    "request_artifact": f"request-{run_number}.json",
                    "snapshot_sha256": sha256_file(artifact),
                })
                self.bind_search_request(cache, search)
                records.extend([
                    search,
                    valid_search_wave_record(
                        wave_index,
                        search_run_ids=[f"SR{run_number:03d}"],
                        new_candidate_ids=[],
                    ),
                ])
            records.append(valid_gap_assessment_record(
                supporting_search_run_ids=["SR201", "SR202"]
            ))
        elif source_count:
            candidate = valid_candidate_record(source_count + 1)
            candidate.update({
                "search_run_ids": ["SR001"],
                "disposition": "exclude",
                "screening_reason": "Screened out after title/abstract review; useful as candidate-pool audit evidence but not used.",
            })
            for outcome in candidate["resolver_outcomes"]:
                outcome.update({
                    "status": "skipped",
                    "matched_identifier": None,
                    "returned_title": None,
                    "returned_authors": [],
                    "returned_year": None,
                    "metadata_match": False,
                    "raw_artifact": None,
                    "snapshot_sha256": None,
                    "reason": "Excluded during candidate screening before resolver capture.",
                })
            records.append(candidate)
            self.append_search_result(cache, records, "SR001", candidate)
        path = workspace / "retrieval-inputs.jsonl"
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        return path

    def search_result_row(self, candidate: dict[str, object]) -> dict[str, object]:
        return {
            "title": candidate["title"],
            "url": candidate["url"],
            "identifiers": candidate["identifiers"],
        }

    def append_search_result(
        self,
        cache: Path,
        records: list[dict[str, object]],
        search_run_id: str,
        candidate: dict[str, object],
    ) -> None:
        search = next(
            record for record in records
            if record.get("record_kind") == "search_run"
            and record.get("search_run_id") == search_run_id
        )
        artifact = cache / str(search["raw_artifact"])
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        payload.setdefault("results", []).append(self.search_result_row(candidate))
        artifact.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        search["result_count"] = len(payload["results"])
        search["snapshot_sha256"] = sha256_file(artifact)

    def write_closed_corpus_inputs(self, run: Path, workspace: Path) -> Path:
        cache = run / "work/generations/g0001/evidence-cache"
        records: list[dict[str, object]] = []
        for index in range(1, 11):
            snapshot = cache / f"source-{index}.txt"
            snapshot.write_text(
                f"Directly inspectable evidence excerpt {index}. Closed corpus context.",
                encoding="utf-8",
            )
            search_artifact = cache / f"search-{index}.json"
            search_artifact.write_text(
                json.dumps({"local_results": [f"K{index:03d}"]}) + "\n",
                encoding="utf-8",
            )
            search = valid_search_run_record(index, pass_kind="corpus")
            search.update({
                "adapter": "closed_corpus",
                "surface": "supplied-corpus",
                "surface_class": "local_corpus",
                "snapshot_sha256": sha256_file(search_artifact),
            })
            self.bind_search_request(cache, search)
            candidate = valid_candidate_record(index)
            candidate.update({
                "adapter": "closed_corpus",
                "url": None,
                "identifiers": {key: None for key in candidate["identifiers"]},
                "version_family_id": None,
                "version_role": None,
                "relationship_basis": None,
                "canonical_version": True,
            })
            candidate["resolver_outcomes"] = [{
                "resolver": "closed-corpus",
                "status": "skipped",
                "query_basis": "metadata",
                "matched_identifier": None,
                "returned_title": None,
                "returned_authors": [],
                "returned_year": None,
                "metadata_match": False,
                "checked_at": candidate["resolver_outcomes"][0]["checked_at"],
                "raw_artifact": None,
                "snapshot_sha256": None,
                "reason": "External resolution is forbidden in closed-corpus mode.",
            }]
            capture = valid_adapter_record(index)
            capture.pop("url")
            capture.update({
                "adapter": "closed_corpus",
                "final_url": None,
                "file_ref": f"input/source-{index}.txt",
                "observed_status": None,
                "publisher": "User supplied corpus",
                "capture_level": "user_file",
                "source_type": "user_provided_file",
                "reliability_notes": "File-backed fixture from the supplied closed corpus.",
            })
            records.extend([search, candidate, capture])
        path = workspace / "closed-retrieval-inputs.jsonl"
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )
        return path

    def bind_search_request(
        self, cache: Path, search: dict[str, object]
    ) -> None:
        request_path = cache / str(search["request_artifact"])
        request_path.write_text(json.dumps({
            "query_id": search["query_id"],
            "surface": search["surface"],
            "query": search["query"],
            "aliases": search["aliases"],
        }) + "\n", encoding="utf-8")
        search["request_sha256"] = sha256_file(request_path)

    def write_findings_inputs(self, run: Path, workspace: Path) -> Path:
        manifest_path = run / "work/generations/g0001/artifacts/research/retrieval-manifest.jsonl"
        manifests = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
        findings = []
        for index, manifest in enumerate(manifests, start=1):
            question_id = str(manifest["query_id"])
            source_id = str(manifest["source_id"])
            findings.append({
                "schema_version": "2.0",
                "finding_id": f"F{index:03d}",
                "tasklet_id": question_id.replace("Q", "T", 1),
                "question_id": question_id,
                "summary": f"Finding {index} closes a planned STORM tasklet.",
                "source_ids": [source_id],
                "evidence_locators": [{
                    "source_id": source_id,
                    "locator": manifest["locator"],
                    "excerpt": manifest["excerpt"],
                    "snapshot_sha256": manifest["snapshot_sha256"],
                }],
                "claim_ids": [f"C{index:03d}"],
                "status": "usable",
                "confidence": "high",
                "limitations": ["Fixture scope only."],
                "produced_by": "subagent-fixture-1",
                "created_at": "2026-06-23T00:00:00Z",
            })
        path = workspace / "findings.jsonl"
        path.write_text("".join(json.dumps(item) + "\n" for item in findings), encoding="utf-8")
        return path

    def invoke(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
