from __future__ import annotations

import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from scripts import run_checks
from tests.test_validate_package import build_valid_package


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
SCRIPT = ROOT / "scripts" / "run_checks.py"


class RunChecksTests(unittest.TestCase):
    def test_schema_gate_includes_output_eval_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "schemas").mkdir()
            (root / "evals" / "output").mkdir(parents=True)
            (root / "schemas" / "valid.schema.json").write_text(
                '{"$schema":"https://json-schema.org/draft/2020-12/schema","additionalProperties":false}',
                encoding="utf-8",
            )
            (root / "evals" / "output" / "schema.json").write_text(
                '{"$schema":"https://json-schema.org/draft/2020-12/schema"}',
                encoding="utf-8",
            )
            with mock.patch.object(run_checks, "ROOT", root):
                self.assertEqual(run_checks.validate_schema_files(), 4)

    def test_package_mode_accepts_valid_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_valid_package(Path(tmp))
            result = subprocess.run(
                [str(PYTHON), str(SCRIPT), "--package", str(package)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_package_mode_propagates_validation_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_valid_package(Path(tmp))
            (package / "exports" / "report.pdf").unlink()
            result = subprocess.run(
                [str(PYTHON), str(SCRIPT), "--package", str(package)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 6)


if __name__ == "__main__":
    unittest.main()
