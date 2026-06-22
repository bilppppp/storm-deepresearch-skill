from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import tests.test_render_stage as render_stage_helpers
from scripts.validate_package import RENDER_ARTIFACTS, _structural_checks


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/storm_research.py"


class ValidatePackageTests(unittest.TestCase):
    def validate(self, run: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), "validate", str(run)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_valid_governed_run_commits_reports_and_validation_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            result = self.validate(run)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            artifacts = artifact_root(run)
            payload = json.loads(
                (artifacts / "validation/validation-report.json").read_text(encoding="utf-8")
            )
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["schema_version"], "2.0")
            self.assertEqual(payload["summary"]["failed"], 0)
            self.assertTrue((artifacts / "validation/validation-report.md").is_file())
            self.assertTrue((run / "state/generations/g0001/receipts/70-validation.json").is_file())

    def test_validator_rejects_forged_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            receipt = run / "state/generations/g0001/receipts/30-evidence.json"
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            payload["validator_sha256"] = "0" * 64
            receipt.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            result = self.validate(run)
            self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
            self.assertIn("receipt", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/70-validation.json").exists())

    def test_validator_rejects_markdown_named_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            bad = artifact_root(run) / "research/uncertainty-ledger.json"
            bad.write_text("# not JSON\n", encoding="utf-8")
            result = self.validate(run)
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertIn("valid JSON", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/70-validation.json").exists())

    def test_validator_rejects_undeclared_process_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            extra = artifact_root(run) / "research/claim-updates.jsonl"
            extra.write_text("{}\n", encoding="utf-8")
            result = self.validate(run)
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertIn("undeclared artifact", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/70-validation.json").exists())

    def test_public_local_path_leak_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            report = artifact_root(run) / "report.md"
            report.write_text(
                report.read_text(encoding="utf-8") + "\n/Users/example/private.txt\n",
                encoding="utf-8",
            )
            result = self.validate(run)
            self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
            self.assertIn("local path leak", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/70-validation.json").exists())

    def test_reduced_inventory_may_omit_pdf_but_full_inventory_may_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp)
            for relative in RENDER_ARTIFACTS - {"exports/report.pdf"}:
                path = artifacts / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.suffix == ".json":
                    path.write_text("{}\n", encoding="utf-8")
                elif path.suffix == ".jsonl":
                    path.write_text("{}\n", encoding="utf-8")
                else:
                    path.write_text("fixture\n", encoding="utf-8")
            _, reduced_code = _structural_checks(artifacts, pdf_required=False)
            full_checks, full_code = _structural_checks(artifacts, pdf_required=True)
            self.assertEqual(reduced_code, 0)
            self.assertEqual(full_code, 6)
            self.assertIn("required PDF is missing", full_checks[-1].message)


def artifact_root(run: Path) -> Path:
    return run / "work/generations/g0001/artifacts"


def build_valid_governed_run(parent: Path) -> Path:
    helper = render_stage_helpers.RenderStageTests(methodName="runTest")
    run = helper.reviewed_run(parent)
    result = helper.invoke("render", str(run), "--pdf-renderer", "weasyprint")
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return run


if __name__ == "__main__":
    unittest.main()
