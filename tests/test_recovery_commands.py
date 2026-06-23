from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import tests.test_render_stage as render_stage_helpers
import tests.test_storm_research_cli as cli_helpers
from tests.governed_fixtures import valid_brief_v2, valid_research_plan_v2, valid_source_plan


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/storm_research.py"


class RecoveryCommandTests(unittest.TestCase):
    def test_amendment_creates_new_generation_and_preserves_old(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.rendered_run(workspace)
            result = self.invoke_amend(run, {"audience": "Expert reviewer"})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(self.generation_input(run, 1, "brief.json").is_file())
            self.assertTrue(self.generation_input(run, 2, "brief.json").is_file())
            self.assertTrue(self.receipt_path(run, "init", generation=2).is_file())
            self.assertFalse(self.receipt_path(run, "plan", generation=2).exists())
            old_brief = json.loads(self.generation_input(run, 1, "brief.json").read_text(encoding="utf-8"))
            new_brief = json.loads(self.generation_input(run, 2, "brief.json").read_text(encoding="utf-8"))
            self.assertEqual(old_brief["audience"], "General reader")
            self.assertEqual(new_brief["audience"], "Expert reviewer")

    def test_pdf_failure_cannot_amend_full_to_reduced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.render_failed_run(workspace)
            result = self.invoke_amend(run, {"output_mode": "reduced"})
            self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
            self.assertIn("full dossier cannot be amended to reduced output", result.stderr)
            self.assertFalse(self.generation_input(run, 2, "brief.json").exists())

    def test_legacy_import_never_creates_passed_retrieval_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            legacy = self.write_legacy_package(workspace)
            result = self.invoke(
                "import-legacy", "--legacy-package", str(legacy),
                "--workspace", str(workspace), "--output", "legacy-run",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run = workspace / "output/storm-deepresearch/legacy-run"
            self.assertTrue(self.receipt_path(run, "init").is_file())
            self.assertTrue(self.receipt_path(run, "plan").is_file())
            self.assertFalse(self.receipt_path(run, "retrieval").exists())
            status = self.status(run)
            self.assertEqual(status["state"], "planned")
            self.assertEqual(status["next_stage"], "retrieval")

    def test_status_reports_first_invalid_receipt_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            plan = run / "work/generations/g0001/artifacts/research/research-plan.json"
            plan.write_text("{}\n", encoding="utf-8")
            status = self.status(run)
            self.assertEqual(status["state"], "invalid")
            self.assertEqual(status["last_valid_stage"], "init")
            self.assertEqual(status["next_stage"], "plan")
            self.assertIn("artifact hash mismatch", status["error"])

    def test_explain_reports_repair_command_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            receipt_before = self.receipt_path(run, "plan").read_bytes()
            plan = run / "work/generations/g0001/artifacts/research/research-plan.json"
            plan.write_text("{}\n", encoding="utf-8")
            result = self.invoke("explain", str(run))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["failed_stage"], "plan")
            self.assertIn("storm-research retry", payload["repair_command"])
            self.assertIn("artifacts/research/research-plan.json", payload["invalidated_artifacts"])
            self.assertEqual(self.receipt_path(run, "plan").read_bytes(), receipt_before)

    def test_retry_accepts_only_current_failed_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            plan = run / "work/generations/g0001/artifacts/research/research-plan.json"
            plan.write_text("{}\n", encoding="utf-8")
            accepted = self.invoke("retry", str(run), "--stage", "plan")
            rejected = self.invoke("retry", str(run), "--stage", "retrieval")
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
            self.assertEqual(rejected.returncode, 8, rejected.stdout + rejected.stderr)

    def rendered_run(self, workspace: Path) -> Path:
        helper = render_stage_helpers.RenderStageTests(methodName="runTest")
        run = helper.reviewed_run(workspace)
        result = helper.invoke("render", str(run), "--pdf-renderer", "weasyprint")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return run

    def render_failed_run(self, workspace: Path) -> Path:
        helper = render_stage_helpers.RenderStageTests(methodName="runTest")
        run = helper.reviewed_run(workspace)
        result = helper.invoke("render", str(run), "--pdf-renderer", "none")
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        return run

    def planned_run(self, workspace: Path) -> Path:
        helper = cli_helpers.StormResearchCLITests(methodName="runTest")
        return helper.planned_run(workspace)

    def write_legacy_package(self, workspace: Path) -> Path:
        legacy = workspace / "legacy-package"
        research = legacy / "research"
        research.mkdir(parents=True)
        (legacy / "brief.json").write_text(json.dumps(valid_brief_v2()) + "\n", encoding="utf-8")
        (research / "research-plan.json").write_text(
            json.dumps(valid_research_plan_v2()) + "\n", encoding="utf-8"
        )
        (research / "source-plan.json").write_text(
            json.dumps(valid_source_plan()) + "\n", encoding="utf-8"
        )
        return legacy

    def invoke_amend(self, run: Path, changes: dict[str, object]) -> subprocess.CompletedProcess[str]:
        changes_path = run.parent / "changes.json"
        changes_path.write_text(json.dumps(changes) + "\n", encoding="utf-8")
        return self.invoke(
            "amend", str(run), "--changes-json", str(changes_path),
            "--initiator", "human-reviewer",
            "--approval-evidence", "approval:explicit-test-command",
        )

    def status(self, run: Path) -> dict[str, object]:
        result = self.invoke("status", str(run))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def invoke(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def generation_input(run: Path, generation: int, name: str) -> Path:
        return run / f"work/generations/g{generation:04d}/inputs/{name}"

    @staticmethod
    def receipt_path(run: Path, stage: str, *, generation: int = 1) -> Path:
        prefixes = {
            "init": "00",
            "plan": "10",
            "retrieval": "20",
            "evidence": "30",
            "draft": "40",
            "review": "50",
            "render": "60",
            "validation": "70",
            "release": "80",
        }
        return run / f"state/generations/g{generation:04d}/receipts/{prefixes[stage]}-{stage}.json"


if __name__ == "__main__":
    unittest.main()
