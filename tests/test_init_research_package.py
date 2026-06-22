from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.contract_io import validate_research_package


ROOT = Path(__file__).resolve().parents[1]


class InitResearchPackageTests(unittest.TestCase):
    def test_initializer_creates_contract_valid_empty_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            output = workspace / "output" / "storm-deepresearch" / "test-run"
            result = subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts" / "init_research_package.py"),
                    "--topic",
                    "Test topic",
                    "--question",
                    "What should be verified?",
                    "--workspace",
                    str(workspace),
                    "--output",
                    "test-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(validate_research_package(output), [])
            brief = json.loads((output / "brief.json").read_text(encoding="utf-8"))
            self.assertEqual(brief["package_state"], "initialized")
            self.assertEqual(brief["depth_level"], "full_dossier")
            self.assertEqual(brief["report_language"], "en")
            self.assertEqual(brief["length_contract"]["minimum"], 3500)
            plan = json.loads((output / "research" / "research-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["report_outline"]["status"], "initialized")
            self.assertEqual(plan["report_outline"]["minimum"], 3500)
            self.assertEqual((output / "research" / "source-register.jsonl").read_text(encoding="utf-8"), "")
            self.assertNotIn("S001", (output / "research" / "source-register.md").read_text(encoding="utf-8"))

    def test_initializer_defaults_chinese_full_dossier_to_8000_10000_characters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            output = workspace / "output" / "storm-deepresearch" / "chinese-run"
            result = subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts" / "init_research_package.py"),
                    "--topic",
                    "人工智能研究治理",
                    "--question",
                    "怎样生成有证据的长篇研究报告？",
                    "--workspace",
                    str(workspace),
                    "--output",
                    "chinese-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            brief = json.loads((output / "brief.json").read_text(encoding="utf-8"))
            self.assertEqual(brief["report_language"], "zh-CN")
            self.assertEqual(brief["length_contract"]["unit"], "characters")
            self.assertEqual(brief["length_contract"]["minimum"], 8000)
            self.assertEqual(brief["length_contract"]["maximum"], 10000)

    def test_initializer_refuses_existing_directory_without_touching_ledgers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            output = workspace / "output" / "storm-deepresearch" / "existing-run"
            ledger = output / "research" / "source-register.jsonl"
            ledger.parent.mkdir(parents=True)
            ledger.write_text('{"source_id":"S001"}\n', encoding="utf-8")
            before = ledger.read_bytes()
            result = subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts" / "init_research_package.py"),
                    "--topic",
                    "Test topic",
                    "--question",
                    "What should be verified?",
                    "--workspace",
                    str(workspace),
                    "--output",
                    "existing-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertIn("already exists", result.stderr)
            self.assertEqual(ledger.read_bytes(), before)

    def test_initializer_uses_workspace_default_when_output_is_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts" / "init_research_package.py"),
                    "--topic",
                    "Default path",
                    "--question",
                    "Where is the package written?",
                    "--workspace",
                    str(workspace),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = Path(result.stdout.strip().removeprefix("Initialized "))
            self.assertEqual(output.parent, (workspace / "output" / "storm-deepresearch").resolve())
            self.assertTrue((output / "research" / "source-register.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
