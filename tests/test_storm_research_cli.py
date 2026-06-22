from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.governed_fixtures import valid_research_plan_v2, valid_source_plan


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

    def write_plans(self, workspace: Path) -> tuple[Path, Path]:
        plan = workspace / "research-plan.json"
        source_plan = workspace / "source-plan.json"
        plan.write_text(json.dumps(valid_research_plan_v2()), encoding="utf-8")
        source_plan.write_text(json.dumps(valid_source_plan()), encoding="utf-8")
        return plan, source_plan

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
