from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "agent_run_guard.py"


class AgentRunGuardTests(unittest.TestCase):
    def run_guard(self, runner: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GUARD), *args, str(runner)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_syntax_error_fails_before_running_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = Path(tmp) / "broken_runner.py"
            runner.write_text('payload = """unterminated\nprint("must not run")\n', encoding="utf-8")

            result = self.run_guard(runner)

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("RUNNER_SYNTAX_ERROR", result.stderr)
        self.assertNotIn("must not run", result.stdout)

    def test_timeout_terminates_long_running_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = Path(tmp) / "slow_runner.py"
            runner.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")
            started = time.monotonic()

            result = self.run_guard(runner, "--timeout", "0.2")

        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
        self.assertLess(elapsed, 3)
        self.assertIn("RUNNER_TIMEOUT", result.stderr)

    def test_valid_runner_streams_and_returns_child_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = Path(tmp) / "ok_runner.py"
            runner.write_text('print("runner ok")\n', encoding="utf-8")

            result = self.run_guard(runner, "--timeout", "3")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUNNER_START", result.stdout)
        self.assertIn("runner ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
