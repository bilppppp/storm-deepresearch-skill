from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LocalOutputEvalRunnerTests(unittest.TestCase):
    def test_output_eval_cases_match_yao_contract(self) -> None:
        cases_root = ROOT / "evals" / "output"
        cases_path = cases_root / "cases.jsonl"
        cases = [
            json.loads(line)
            for line in cases_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertGreaterEqual(len(cases), 5)
        self.assertTrue(any(case.get("input_files") for case in cases))
        self.assertTrue(any(case.get("metadata", {}).get("case_type") == "near_neighbor" for case in cases))
        self.assertTrue(any(case.get("metadata", {}).get("case_type") == "boundary" for case in cases))
        for case in cases:
            with self.subTest(case=case.get("id")):
                for key in ("id", "prompt", "baseline_output", "with_skill_output", "assertions"):
                    self.assertIn(key, case)
                    self.assertTrue(case[key])
                self.assertIsInstance(case["assertions"], list)
                self.assertTrue(case["assertions"])
                for assertion in case["assertions"]:
                    self.assertTrue(assertion.get("id"))
                    self.assertTrue(assertion.get("description"))
                for raw_path in case.get("input_files", []):
                    self.assertFalse(Path(raw_path).is_absolute())
                    self.assertTrue((cases_root / raw_path).exists(), raw_path)

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

    def test_runner_batch_isolates_cases_in_subprocess_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = root / "cases.jsonl"
            out = root / "out"
            cases.write_text(
                "\n".join([
                    json.dumps({"id": "case-a", "prompt": "A", "with_skill_output": "Output A"}),
                    json.dumps({"id": "case-b", "prompt": "B", "with_skill_output": "Output B"}),
                ]) + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    str(ROOT / ".venv" / "bin" / "python"),
                    str(ROOT / "scripts" / "local_output_eval_runner.py"),
                    "--cases-jsonl", str(cases),
                    "--out-dir", str(out),
                    "--timeout", "10",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["case_count"], 2)
            self.assertEqual(summary["passed"], 2)
            self.assertTrue((out / "case-a.result.json").is_file())
            self.assertTrue((out / "case-b.log").is_file())


if __name__ == "__main__":
    unittest.main()
