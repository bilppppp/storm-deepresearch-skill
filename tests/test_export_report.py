from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
SCRIPT = ROOT / "scripts" / "export_report.py"
REPORT = ROOT / "tests" / "fixtures" / "export" / "report.md"
TEMPLATE = ROOT / "templates" / "report.html.j2"


class ExportReportTests(unittest.TestCase):
    def make_package(self, root: Path) -> Path:
        package = root / "research-run"
        package.mkdir()
        shutil.copyfile(REPORT, package / "report.md")
        return package

    def run_export(self, package: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(PYTHON), str(SCRIPT), str(package),
                "--template", str(TEMPLATE), "--title", "Evidence-Grounded Research Fixture", *extra,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_full_export_renders_html_pdf_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = self.make_package(Path(tmp))
            output = package / "exports"
            result = self.run_export(package, "--require-pdf")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            html = (output / "report.html").read_text(encoding="utf-8")
            pdf = (output / "report.pdf").read_bytes()
            manifest = json.loads((package / "validation" / "render-manifest.json").read_text(encoding="utf-8"))
            self.assertIn("<table", html)
            self.assertIn("<pre", html)
            self.assertIn("中文内容", html)
            self.assertIn("<nav", html)
            self.assertIn('href="#executive-summary"', html)
            self.assertIn("overflow-wrap: anywhere", html)
            self.assertIn("nav, .footnote-back { display: none; }", html)
            self.assertNotIn("Generated from the canonical Markdown report at", html)
            self.assertNotIn("{{", html)
            self.assertNotIn("{%", html)
            self.assertTrue(pdf.startswith(b"%PDF-"))
            self.assertGreater(len(pdf), 10_000)
            self.assertEqual(manifest["title"], "Evidence-Grounded Research Fixture")
            self.assertEqual(manifest["pdf_renderer"], "weasyprint")
            self.assertEqual(len(manifest["section_fingerprints"]), 10)

    def test_missing_pandoc_exits_three(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = self.make_package(Path(tmp))
            result = self.run_export(package, "--pandoc", "/missing/pandoc", "--require-pdf")
            self.assertEqual(result.returncode, 3)
            self.assertIn("Pandoc is unavailable", result.stderr)

    def test_required_pdf_cannot_use_none_renderer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = self.make_package(Path(tmp))
            result = self.run_export(package, "--pdf-renderer", "none", "--require-pdf")
            self.assertEqual(result.returncode, 6)
            self.assertIn("required PDF", result.stderr)

    def test_reduced_mode_can_skip_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = self.make_package(Path(tmp))
            output = package / "exports"
            result = self.run_export(package, "--pdf-renderer", "none")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output / "report.html").exists())
            self.assertFalse((output / "report.pdf").exists())

    def test_strict_template_rejects_unknown_variable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = self.make_package(root)
            template = root / "broken.j2"
            template.write_text("<html><body>{{ missing_value }}</body></html>", encoding="utf-8")
            result = subprocess.run(
                [
                    str(PYTHON), str(SCRIPT), str(package),
                    "--template", str(template), "--title", "Broken", "--pdf-renderer", "none",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 6)
            self.assertIn("template rendering failed", result.stderr)

    def test_export_rejects_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            package = self.make_package(Path(tmp))
            (package / "exports").symlink_to(Path(outside), target_is_directory=True)
            result = self.run_export(package, "--pdf-renderer", "none")
            self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
            self.assertIn("escapes the research package", result.stderr)
            self.assertFalse((Path(outside) / "report.html").exists())


if __name__ == "__main__":
    unittest.main()
