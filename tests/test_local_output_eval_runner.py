from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LocalOutputEvalRunnerTests(unittest.TestCase):
    def test_runner_has_help_surface(self) -> None:
        result = subprocess.run(
            [str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "scripts" / "local_output_eval_runner.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("deterministic", result.stdout.lower())

    def test_runner_preserves_fixture_and_labels_command_evidence(self) -> None:
        request = {"prompt": "Research this", "fixture_output": "Evidence package"}
        result = subprocess.run(
            [str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "scripts" / "local_output_eval_runner.py")],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["output"], "Evidence package")
        self.assertEqual(payload["execution_kind"], "command")
        self.assertEqual(payload["provider"], "local-deterministic-fixture")
        self.assertTrue(payload["usage"]["estimated"])


if __name__ == "__main__":
    unittest.main()
