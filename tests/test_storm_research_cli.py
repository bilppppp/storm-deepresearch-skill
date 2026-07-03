from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from tests.governed_fixtures import (
    valid_adapter_record,
    valid_candidate_record,
    valid_capture_input,
    valid_research_plan_v2,
    valid_source_plan,
    valid_search_run_record,
    valid_storm_lens_artifact,
)
from scripts.harness_io import sha256_file


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
                    "raw_artifact": artifact.name,
                    "snapshot_sha256": sha256_file(artifact),
                    "searched_at": (base + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z"),
                })
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

    def test_briefing_accepts_one_academic_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace, profile="briefing")
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            for row in rows:
                if row.get("record_kind") == "search_run":
                    row["surface"] = "OpenAlex"
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

    def test_version_siblings_do_not_inflate_independent_source_depth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            inputs = self.write_retrieval_inputs(run, workspace)
            rows = [json.loads(line) for line in inputs.read_text(encoding="utf-8").splitlines()]
            for row in rows:
                if row.get("record_kind") == "candidate":
                    row["version_family_id"] = "W001"
                    row["relationship_basis"] = "explicit_metadata"
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
            candidate["resolver_outcomes"][0].update({
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
                    if profile == "critique_deepresearch":
                        self.assertTrue(any("critique_deepresearch profile" in item for item in brief["assumptions"]))

    def test_legacy_strict_profile_normalizes_to_recommended_full_dossier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(
                workspace,
                "--research-profile", "strict_storm_lens",
                "--profile-selection-mode", "user_selected",
                "--profile-selection-evidence", "user selected the former strict option",
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

    def invoke_init(self, workspace: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.invoke(
            "init", "--topic", "Governed research", "--question",
            "What evidence supports the conclusion?", "--workspace", str(workspace),
            "--output", "test-run",
            "--profile-selection-mode", "user_requested_default",
            "--profile-selection-evidence", "test explicitly requested the default full dossier profile",
            *extra,
        )

    def initialized_run(
        self,
        workspace: Path,
        *,
        profile: str = "default_full_dossier",
        high_stakes: bool = False,
    ) -> Path:
        extra = ["--research-profile", profile]
        if profile == "briefing":
            extra.extend(["--briefing-reason", "fixture explicitly requests a short briefing"])
        if high_stakes:
            extra.append("--high-stakes")
        result = self.invoke_init(workspace, *extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return workspace / "output" / "storm-deepresearch" / "test-run"

    def planned_run(
        self,
        workspace: Path,
        *,
        profile: str = "default_full_dossier",
        high_stakes: bool = False,
    ) -> Path:
        run = self.initialized_run(workspace, profile=profile, high_stakes=high_stakes)
        plan_path, source_plan_path = self.write_plans(
            workspace, high_stakes=high_stakes
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

    def write_plans(
        self, workspace: Path, *, high_stakes: bool = False
    ) -> tuple[Path, Path]:
        plan = workspace / "research-plan.json"
        source_plan = workspace / "source-plan.json"
        plan.write_text(json.dumps(valid_research_plan_v2()), encoding="utf-8")
        source_plan_payload = valid_source_plan()
        if high_stakes:
            source_plan_payload["questions"][0]["search_requirements"]["required_surfaces"] = [
                "scholarly_index", "literature_database"
            ]
            source_plan_payload["questions"][1]["search_requirements"]["required_surfaces"] = [
                "scholarly_index", "trial_registry"
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
        lens = workspace / "storm-lens-perspectives.json"
        lens.write_text(json.dumps(valid_storm_lens_artifact(
            "P1",
            sha256_file(ROOT / "references/storm-lens-prompt-pack.md"),
            {"inputs/brief.json": sha256_file(brief)},
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
    ) -> Path:
        cache = run / "work/generations/g0001/evidence-cache"
        brief = json.loads(
            (run / "work/generations/g0001/inputs/brief.json").read_text(encoding="utf-8")
        )
        critique = brief.get("research_profile") == "critique_deepresearch"
        records: list[dict[str, object]] = []
        for index in range(1, 11):
            search = valid_search_run_record(index)
            search["surface"] = "OpenAlex" if index % 2 else "Semantic Scholar"
            candidate = valid_candidate_record(index)
            query_id = f"Q{index:03d}"
            record = (
                valid_adapter_record(index)
                if query_id in official_query_ids
                else valid_capture_input(index)
            )
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
                json.dumps({"results": [candidate["candidate_id"]]}) + "\n",
                encoding="utf-8",
            )
            (cache / f"crossref-{index}.json").write_text(
                json.dumps({"doi": candidate["identifiers"]["doi"]}) + "\n",
                encoding="utf-8",
            )
            search["snapshot_sha256"] = sha256_file(cache / f"search-{index}.json")
            candidate["resolver_outcomes"][0]["snapshot_sha256"] = sha256_file(
                cache / f"crossref-{index}.json"
            )
            records.extend([search, candidate, record])
            extra_surfaces: list[tuple[int, str, str, str]] = []
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
                    json.dumps({"results": [candidate["candidate_id"]]}) + "\n",
                    encoding="utf-8",
                )
                extra_search = valid_search_run_record(index, pass_kind=pass_kind)
                extra_search.update({
                    "search_run_id": run_id,
                    "surface": surface,
                    "surface_class": surface_class,
                    "raw_artifact": artifact.name,
                    "snapshot_sha256": sha256_file(artifact),
                    "result_count": 1,
                })
                candidate["search_run_ids"].append(run_id)
                record["search_run_ids"].append(run_id)
                records.append(extra_search)
            if query_id in gap_fill_query_ids:
                gap_id = f"SR{100 + index:03d}"
                gap_artifact = cache / f"gap-{index}.json"
                zero_results = query_id in zero_result_query_ids
                gap_artifact.write_text(
                    json.dumps({"results": [] if zero_results else [candidate["candidate_id"]]}) + "\n",
                    encoding="utf-8",
                )
                gap = valid_search_run_record(index, pass_kind="gap_fill")
                gap.update({
                    "search_run_id": gap_id,
                    "surface": "Google Scholar",
                    "raw_artifact": gap_artifact.name,
                    "snapshot_sha256": sha256_file(gap_artifact),
                    "execution_status": "zero_results" if zero_results else "completed",
                    "result_count": 0 if zero_results else 1,
                })
                records.append(gap)
        path = workspace / "retrieval-inputs.jsonl"
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        return path

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
            candidate = valid_candidate_record(index)
            candidate.update({
                "adapter": "closed_corpus",
                "url": None,
                "identifiers": {key: None for key in candidate["identifiers"]},
                "version_family_id": None,
                "version_role": None,
                "relationship_basis": None,
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
