from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

import tests.test_review_stage as review_stage_helpers


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/storm_research.py"


class RenderStageTests(unittest.TestCase):
    def test_render_requires_review_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            helper = review_stage_helpers.ReviewStageTests(methodName="runTest")
            run = helper.drafted_run(workspace)
            result = self.invoke("render", str(run), "--pdf-renderer", "none")
            self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
            self.assertIn("missing review receipt", result.stderr)

    def test_full_dossier_render_failure_cannot_downgrade_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.reviewed_run(workspace)
            brief_before = (run / "brief.json").read_bytes()
            result = self.invoke("render", str(run), "--pdf-renderer", "none")
            self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
            self.assertEqual((run / "brief.json").read_bytes(), brief_before)
            self.assertEqual(json.loads(brief_before)["output_mode"], "full")
            self.assertFalse((run / "state/generations/g0001/receipts/60-render.json").exists())

    def test_render_commits_html_readable_pdf_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.reviewed_run(workspace)
            result = self.invoke("render", str(run), "--pdf-renderer", "weasyprint")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            artifacts = run / "work/generations/g0001/artifacts"
            html = artifacts / "exports/report.html"
            pdf = artifacts / "exports/report.pdf"
            manifest = artifacts / "validation/render-manifest.json"
            self.assertTrue(html.is_file())
            self.assertGreater(len(PdfReader(pdf).pages), 0)
            self.assertTrue(manifest.is_file())
            self.assertTrue((run / "state/generations/g0001/receipts/60-render.json").is_file())

    def reviewed_run(self, workspace: Path) -> Path:
        helper = review_stage_helpers.ReviewStageTests(methodName="runTest")
        return helper.reviewed_run(workspace)

    def invoke(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *arguments], cwd=ROOT,
            capture_output=True, text=True, check=False,
        )


if __name__ == "__main__":
    unittest.main()
