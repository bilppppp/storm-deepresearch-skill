from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_checks
from tests.test_validate_package import artifact_root, build_valid_governed_run


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_checks.py"


class RunChecksTests(unittest.TestCase):
    def test_schema_gate_includes_output_eval_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "schemas").mkdir()
            (root / "evals/output").mkdir(parents=True)
            (root / "schemas/valid.schema.json").write_text(
                '{"$schema":"https://json-schema.org/draft/2020-12/schema","additionalProperties":false}',
                encoding="utf-8",
            )
            (root / "evals/output/schema.json").write_text(
                '{"$schema":"https://json-schema.org/draft/2020-12/schema"}',
                encoding="utf-8",
            )
            with mock.patch.object(run_checks, "ROOT", root):
                self.assertEqual(run_checks.validate_schema_files(), 4)

    def test_package_mode_accepts_valid_governed_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            result = self.invoke_package(run)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_package_mode_propagates_validation_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            (artifact_root(run) / "exports/report.pdf").unlink()
            result = self.invoke_package(run)
            self.assertEqual(result.returncode, 6, result.stdout + result.stderr)

    def test_dist_mode_packages_all_targets_and_verifies_zip(self) -> None:
        with mock.patch.object(run_checks.Path, "is_file", return_value=True):
            with mock.patch.object(run_checks, "run", return_value=0) as runner:
                self.assertEqual(run_checks.run_dist(), 0)
        commands = [call.args[0] for call in runner.call_args_list]
        self.assertEqual(len(commands), 3)
        package_command = commands[0]
        self.assertIn("package", package_command)
        for target in run_checks.PACKAGE_TARGETS:
            self.assertIn(target, package_command)
        self.assertIn("--expectations", package_command)
        self.assertIn("--zip", package_command)
        self.assertIn("sanitize_release_archive.py", commands[1][1])
        self.assertIn("storm-deepresearch-skill.zip", commands[1][2])
        verify_command = commands[2]
        self.assertIn("package-verify", verify_command)
        self.assertIn("--require-zip", verify_command)
        self.assertTrue(any(item.endswith("dist/package_verification.json") for item in verify_command))

    def invoke_package(self, run: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--package", str(run)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
