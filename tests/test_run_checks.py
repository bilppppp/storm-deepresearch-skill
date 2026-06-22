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
