from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.contract_io import validate_brief
from scripts.harness_io import compute_skill_package_hash
from scripts.run_state import RunLayout, Stage, verify_receipt_chain


ROOT = Path(__file__).resolve().parents[1]


class InitResearchPackageTests(unittest.TestCase):
    def test_initializer_forwards_to_governed_init(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            output = workspace / "output" / "storm-deepresearch" / "test-run"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "init_research_package.py"),
                    "--topic",
                    "Test topic",
                    "--question",
                    "What should be verified?",
                    "--workspace",
                    str(workspace),
                    "--output",
                    "test-run",
                    "--profile-selection-mode",
                    "user_requested_default",
                    "--profile-selection-evidence",
                    "test explicitly requested the default full dossier profile",
                    "--assurance-target",
                    "artifact_contract",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Deprecated", result.stderr)
            authoritative = output / "work/generations/g0001/inputs/brief.json"
            brief = json.loads(authoritative.read_text(encoding="utf-8"))
            self.assertEqual(validate_brief(brief), [])
            self.assertNotIn("package_state", brief)
            self.assertEqual(brief["depth_level"], "full_dossier")
            self.assertEqual(brief["profile_selection"]["mode"], "user_requested_default")
            self.assertEqual(brief["report_language"], "en")
            self.assertEqual(brief["length_contract"]["policy"], "bounded")
            self.assertEqual(brief["length_contract"]["minimum"], 3500)
            self.assertFalse((output / "current/research/research-plan.json").exists())
            verify_receipt_chain(
                RunLayout(output), 1, Stage.INIT, compute_skill_package_hash(ROOT)
            )

    def test_initializer_defaults_chinese_full_dossier_to_8000_10000_characters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            output = workspace / "output" / "storm-deepresearch" / "chinese-run"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "init_research_package.py"),
                    "--topic",
                    "人工智能研究治理",
                    "--question",
                    "怎样生成有证据的长篇研究报告？",
                    "--workspace",
                    str(workspace),
                    "--output",
                    "chinese-run",
                    "--profile-selection-mode",
                    "user_requested_default",
                    "--profile-selection-evidence",
                    "test explicitly requested the default full dossier profile",
                    "--assurance-target",
                    "artifact_contract",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            brief = json.loads((output / "brief.json").read_text(encoding="utf-8"))
            self.assertEqual(brief["report_language"], "zh-CN")
            self.assertEqual(brief["length_contract"]["unit"], "characters")
            self.assertEqual(brief["length_contract"]["policy"], "bounded")
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
                    sys.executable,
                    str(ROOT / "scripts" / "init_research_package.py"),
                    "--topic",
                    "Test topic",
                    "--question",
                    "What should be verified?",
                    "--workspace",
                    str(workspace),
                    "--output",
                    "existing-run",
                    "--profile-selection-mode",
                    "user_requested_default",
                    "--profile-selection-evidence",
                    "test explicitly requested the default full dossier profile",
                    "--assurance-target",
                    "artifact_contract",
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
                    sys.executable,
                    str(ROOT / "scripts" / "init_research_package.py"),
                    "--topic",
                    "Default path",
                    "--question",
                    "Where is the package written?",
                    "--workspace",
                    str(workspace),
                    "--profile-selection-mode",
                    "user_requested_default",
                    "--profile-selection-evidence",
                    "test explicitly requested the default full dossier profile",
                    "--assurance-target",
                    "artifact_contract",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = Path(result.stdout.strip().removeprefix("Initialized "))
            self.assertEqual(output.parent, (workspace / "output" / "storm-deepresearch").resolve())
            self.assertTrue((output / "work/generations/g0001/inputs/brief.json").is_file())
            self.assertTrue((output / "state/generations/g0001/receipts/00-init.json").is_file())

    def test_deprecated_initializer_does_not_bypass_profile_selection_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = subprocess.run(
                [
                    sys.executable,
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
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertIn("profile selection requires --profile-selection-mode", result.stderr)
            self.assertFalse((workspace / "output/storm-deepresearch/test-run").exists())


if __name__ == "__main__":
    unittest.main()
