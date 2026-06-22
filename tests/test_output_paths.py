from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.output_paths import OutputPathError, package_child, select_new_output_dir


class OutputPathTests(unittest.TestCase):
    def test_default_output_is_created_under_workspace_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            output = select_new_output_dir(
                "Hannah Arendt and the Banality of Evil",
                workspace=workspace,
                now=datetime(2026, 6, 22, 8, 30, tzinfo=timezone.utc),
            )
            expected_root = (workspace / "output" / "storm-deepresearch").resolve()
            self.assertEqual(output.parent, expected_root)
            self.assertEqual(
                output.name,
                "hannah-arendt-and-the-banality-of-evil-20260622-083000",
            )

    def test_explicit_output_must_remain_inside_resolved_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            with self.assertRaisesRegex(OutputPathError, "outside the approved output root"):
                select_new_output_dir(
                    "Topic",
                    workspace=workspace,
                    output=workspace / "elsewhere" / "run",
                )

    def test_workspace_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            with self.assertRaisesRegex(OutputPathError, "workspace directory does not exist"):
                select_new_output_dir("Topic", workspace=missing)

    def test_symlink_escape_is_rejected_after_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            workspace = Path(tmp)
            output_root = workspace / "output" / "storm-deepresearch"
            output_root.mkdir(parents=True)
            (output_root / "escape").symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaisesRegex(OutputPathError, "outside the approved output root"):
                select_new_output_dir(
                    "Topic",
                    workspace=workspace,
                    output="escape/run",
                )

    def test_package_child_rejects_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            package = Path(tmp)
            (package / "exports").symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaisesRegex(OutputPathError, "escapes the research package"):
                package_child(package, "exports/report.html")


if __name__ == "__main__":
    unittest.main()
