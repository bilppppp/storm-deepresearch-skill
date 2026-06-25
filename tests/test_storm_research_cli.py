from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.governed_fixtures import (
    valid_adapter_record,
    valid_research_plan_v2,
    valid_source_plan,
    valid_storm_lens_artifact,
)
from scripts.harness_io import sha256_file


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "storm_research.py"


class StormResearchCLITests(unittest.TestCase):
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
            self.assertEqual((run / "brief.json").read_bytes(), authoritative.read_bytes())

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
            ("strict_storm_lens", {"storm_lens_mode": "strict", "depth_level": "full_dossier"}),
            ("closed_corpus", {"source_policy": "closed_corpus", "retrieval_mode": "closed_corpus"}),
            ("critique_deepresearch", {"depth_level": "full_dossier", "retrieval_mode": "host"}),
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

    def test_research_profile_conflict_fails_at_init(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.invoke_init(
                workspace,
                "--research-profile", "strict_storm_lens",
                "--storm-lens-mode", "advisory",
            )
            self.assertEqual(result.returncode, 4)
            self.assertIn("conflicts with --research-profile strict_storm_lens", result.stderr)

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
            "--output", "test-run", *extra,
        )

    def initialized_run(self, workspace: Path) -> Path:
        result = self.invoke_init(workspace)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return workspace / "output" / "storm-deepresearch" / "test-run"

    def planned_run(self, workspace: Path) -> Path:
        run = self.initialized_run(workspace)
        plan_path, source_plan_path = self.write_plans(workspace)
        result = self.invoke(
            "plan", str(run), "--plan-json", str(plan_path),
            "--source-plan-json", str(source_plan_path),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return run

    def write_plans(self, workspace: Path) -> tuple[Path, Path]:
        plan = workspace / "research-plan.json"
        source_plan = workspace / "source-plan.json"
        plan.write_text(json.dumps(valid_research_plan_v2()), encoding="utf-8")
        source_plan.write_text(json.dumps(valid_source_plan()), encoding="utf-8")
        return plan, source_plan

    def write_retrieval_inputs(
        self,
        run: Path,
        workspace: Path,
        *,
        placeholder: bool = False,
        encyclopedia_only: bool = False,
    ) -> Path:
        cache = run / "work/generations/g0001/evidence-cache"
        records = []
        for index in range(1, 11):
            record = valid_adapter_record(index)
            if placeholder and index == 1:
                record["url"] = "https://example.com/fake-paper"
                record["final_url"] = record["url"]
            if encyclopedia_only:
                record["url"] = f"https://en.wikipedia.org/wiki/Research_fixture_{index}"
                record["final_url"] = record["url"]
                record["publisher"] = "Wikipedia"
                record["source_type"] = "encyclopedia"
                record["primary_class"] = "secondary"
                record["reliability_tier"] = "B"
            (cache / f"source-{index}.txt").write_text(
                f"Directly inspectable evidence excerpt {index}. Additional context.",
                encoding="utf-8",
            )
            records.append(record)
        path = workspace / "retrieval-inputs.jsonl"
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
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
