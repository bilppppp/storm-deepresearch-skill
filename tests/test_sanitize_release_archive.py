from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sanitize_release_archive.py"


class SanitizeReleaseArchiveTests(unittest.TestCase):
    def test_redacts_skill_root_and_home_without_changing_binary_members(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            archive = temp / "release.zip"
            binary = b"\xff\x00\xfe"
            payload = {
                "skill_dir": str(temp),
                "external_tool": str(Path.home() / ".agents" / "tool.py"),
            }
            with zipfile.ZipFile(archive, "w") as target:
                target.writestr("skill/report.json", json.dumps(payload))
                target.writestr("skill/blob.bin", binary)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(archive), "--redact-root", str(temp)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["changed_entry_count"], 1)
            with zipfile.ZipFile(archive, "r") as source:
                text = source.read("skill/report.json").decode("utf-8")
                self.assertIn("$SKILL_ROOT", text)
                self.assertIn("$HOME", text)
                self.assertNotIn(str(temp), text)
                self.assertNotIn(str(Path.home()), text)
                self.assertEqual(source.read("skill/blob.bin"), binary)

    def test_redacts_home_marker_alias_for_redact_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            archive = temp / "release.zip"
            fake_skill_root = Path.home() / "HomeMarkerFixture" / "project" / "skill"
            payload = {
                "already_redacted_root": "$HOME/HomeMarkerFixture/project/skill",
                "already_redacted_child": "$HOME/HomeMarkerFixture/project/skill/reports/a.json",
            }
            with zipfile.ZipFile(archive, "w") as target:
                target.writestr("skill/report.json", json.dumps(payload))

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(archive), "--redact-root", str(fake_skill_root)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with zipfile.ZipFile(archive, "r") as source:
                text = source.read("skill/report.json").decode("utf-8")
                self.assertIn("$SKILL_ROOT", text)
                self.assertNotIn("$HOME/HomeMarkerFixture/project/skill", text)

    def test_rejects_parent_traversal_member(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            archive = temp / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as target:
                target.writestr("../escape.txt", "unsafe")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(archive), "--redact-root", str(temp)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("unsafe member", result.stdout)

    def test_removes_exact_output_prefix_and_ds_store_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            archive = temp / "release.zip"
            with zipfile.ZipFile(archive, "w") as target:
                target.writestr("skill/output/private-run/report.md", "local")
                target.writestr("skill/evals/output/schema.json", "{}")
                target.writestr("skill/.DS_Store", "metadata")
                target.writestr("skill/SKILL.md", "# Skill")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(archive),
                    "--redact-root",
                    str(temp),
                    "--exclude-prefix",
                    "skill/output/",
                    "--exclude-name",
                    ".DS_Store",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["removed_entry_count"], 2)
            with zipfile.ZipFile(archive, "r") as source:
                names = set(source.namelist())
            self.assertNotIn("skill/output/private-run/report.md", names)
            self.assertNotIn("skill/.DS_Store", names)
            self.assertIn("skill/evals/output/schema.json", names)
            self.assertIn("skill/SKILL.md", names)


if __name__ == "__main__":
    unittest.main()
