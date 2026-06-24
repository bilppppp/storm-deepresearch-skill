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
)


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
            self.assertEqual(brief["briefing_reason"], "user explicitly requested a short briefing")

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
            self.assertTrue((run / "state/generations/g0001/receipts/10-plan.json").is_file())
            current = run / "current/research"
            self.assertEqual((current / "research-plan.json").read_bytes(), (artifacts / "research-plan.json").read_bytes())

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
